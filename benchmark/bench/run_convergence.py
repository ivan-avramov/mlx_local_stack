"""W0 thinking-convergence probe (perf+convergence plan, 2026-06-21).

For ONE model at REALISTIC params (params_for ≡ opencode.json), run aggregation@8K +
a real coding prompt and record, per sample:
  - finish_reason + budget_hit  (the convergence signal: CONVERGED = finish=="stop" AND
    NOT budget_hit. A thinking_budget hit force-closes <think>, so the model still emits
    an answer and EOSes with finish=="stop" — which MASKS non-convergence. completion_tokens
    is the TOTAL generated (reasoning + answer) and on these short-answer tasks total ~ the
    reasoning length, so we ALSO flag completion_tokens >= thinking_budget as a FAILURE.
    "length" (max_tokens hit) stays a failure too — it just isn't finish=="stop".)
  - completion_tokens, reasoning/content char split, has_answer
  - accuracy (aggregation only) so we see whether rambling also costs correctness

Convergence is judged by converged_rate (finish=="stop" AND completion_tokens < budget) +
the budget_hit rate + completion-length distribution. Hitting the budget is NEVER a fix —
the cap stays high; we want a clean EARLY EOS. Per-model temp ladder via --temperature
(drop 0.1 per budget_hit); escalation levers (min_p / presence_penalty / repetition_penalty)
via --set KEY=VAL.

  cd benchmark && PYTHONPATH=. ../.venv/bin/python -m bench.run_convergence --model <id>

Writes benchmark/results/<model>/convergence.json."""
import argparse
import json
import os
import time

from .driver import MlxServeDriver
from .model_params import params_for
from .aggregation import build_cwe, score_cwe
from .reasoning import build_vartrack, score_vartrack

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "

# A real opencode-style coding task: small, well-specified, needs a little reasoning
# (interval scheduling). A converging model gives brief reasoning + code and stops; a
# rambler loops in <think> to the budget.
CODING_PROMPT = (
    "You are a coding assistant. Implement a Python function "
    "`def min_meeting_rooms(intervals: list[tuple[int, int]]) -> int` that returns the "
    "minimum number of meeting rooms required so no two meetings overlap in the same room. "
    "Each interval is (start, end) with start < end and end exclusive (a meeting ending at "
    "t does not conflict with one starting at t). Briefly explain your approach, then give "
    "the final code with a docstring. Handle the empty-list case."
)


def calibrate_cpt(driver, model: str) -> float:
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    return len(_CAL_FILLER * 200) / (out.get("prompt_tokens") or 1)


def run_one(driver, model, params, messages, targets=None, score_fn=None) -> dict:
    r = driver.complete(model, messages, params)
    fr = r.get("finish_reason")
    ct = r.get("completion_tokens")
    # completion_tokens is the TOTAL generated (reasoning + answer). A thinking_budget hit
    # forces </think> -> the model answers and EOSes (finish=="stop"), so finish_reason alone
    # would FALSE-PASS a budget-capped ramble as converged. On these short-answer tasks
    # total ~ reasoning length, so total >= budget means the thinking ran into the cap = a
    # convergence FAILURE regardless of finish_reason. (Validated: gemma 16402>=16384,
    # distill 49175>=49152 were both budget hits mis-scored as converged; Qwen 11708<49152
    # was a true converge.)
    budget = params.get("thinking_budget")
    budget_hit = budget is not None and ct is not None and ct >= budget
    rec = {
        "finish_reason": fr,
        "budget_hit": budget_hit,
        "thinking_budget": budget,
        "converged": (fr == "stop") and not budget_hit,
        "completion_tokens": ct,
        "reasoning_chars": len(r.get("reasoning") or ""),
        "content_chars": len(r.get("content") or ""),
        "has_answer": bool((r.get("content") or "").strip()),
        "decode_tps": r.get("decode_tps"),
        "wall_s": r.get("wall_s"),
    }
    if targets is not None:
        rec["accuracy"] = round((score_fn or score_cwe)(r.get("content", ""), targets), 3)
    return rec


def _summ(records, task) -> dict:
    rs = [r for r in records if r["task"] == task]
    if not rs:
        return {}
    converged = sum(1 for r in rs if r["converged"]) / len(rs)
    budget_hit = sum(1 for r in rs if r.get("budget_hit")) / len(rs)
    eos = sum(1 for r in rs if r["finish_reason"] == "stop") / len(rs)
    comps = sorted((r["completion_tokens"] or 0) for r in rs)
    out = {"n": len(rs),
           "converged_rate": round(converged, 3),
           "budget_hit_rate": round(budget_hit, 3),
           "eos_rate": round(eos, 3),  # raw finish=="stop"; > converged_rate iff budget hits
           "median_completion_tokens": comps[len(comps) // 2],
           "max_completion_tokens": comps[-1]}
    accs = [r["accuracy"] for r in rs if "accuracy" in r]
    if accs:
        out["mean_accuracy"] = round(sum(accs) / len(accs), 3)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="W0 thinking-convergence probe.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--samples", type=int, default=3, help="aggregation samples")
    ap.add_argument("--coding-samples", type=int, default=2)
    ap.add_argument("--agg-ctx", type=int, default=8000)
    ap.add_argument("--task", choices=["aggregation", "vartrack"], default="aggregation",
                    help="reasoning task: 'aggregation' (CWE — enumeration-heavy) or 'vartrack' "
                         "(variable-tracking multi-hop — NO enumeration; isolates whether the "
                         "model rambles on reasoning that doesn't require tallying)")
    ap.add_argument("--chain-len", type=int, default=4, help="vartrack hop count")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="time-bound cap; converging samples stop well under it, ramblers hit it")
    ap.add_argument("--temperature", type=float, default=None,
                    help="override production temperature (the convergence temp ladder: "
                         "drop 0.1 per budget_hit, floor ~0.4 — never greedy)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VAL",
                    help="override any param (escalation levers, e.g. --set min_p=0.02 "
                         "--set repetition_penalty=1.0 --set presence_penalty=1.0)")
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)

    driver = MlxServeDriver()
    if not args.no_preload:
        t = driver.preload(args.model)
        print(f"[conv] preloaded {args.model} in {t}s", flush=True)
    params = params_for(args.model)
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    if args.temperature is not None:
        params["temperature"] = args.temperature
    for kv in args.set:
        k, v = kv.split("=", 1)
        for cast in (int, float):
            try:
                v = cast(v)
                break
            except ValueError:
                pass
        params[k] = v
    cpt = calibrate_cpt(driver, args.model)
    print(f"[conv] {args.model} cpt={cpt:.2f} temp={params['temperature']} "
          f"max_tokens={params['max_tokens']} thinking_budget={params.get('thinking_budget')} "
          f"min_p={params.get('min_p')} pres_pen={params.get('presence_penalty')} "
          f"freq_pen={params.get('frequency_penalty')} rep_pen={params.get('repetition_penalty')} "
          f"ctx(rep/pres/freq)={params.get('repetition_context_size')}/"
          f"{params.get('presence_context_size')}/{params.get('frequency_context_size')}", flush=True)

    records = []
    for trial in range(args.samples):
        seed = args.agg_ctx * 1000 + trial
        if args.task == "vartrack":
            ctx, target, q = build_vartrack(args.agg_ctx, cpt, chain_len=args.chain_len, seed=seed)
            score_fn = score_vartrack
        else:
            ctx, target, q = build_cwe(args.agg_ctx, cpt, k=5, seed=seed)
            score_fn = score_cwe
        rec = run_one(driver, args.model, params,
                      [{"role": "user", "content": ctx + "\n\n" + q}],
                      targets=target, score_fn=score_fn)
        rec.update({"task": args.task, "ctx": args.agg_ctx, "trial": trial})
        records.append(rec)
        print(f"[conv] {args.task} t{trial} finish={rec['finish_reason']} conv={rec['converged']} "
              f"budget_hit={rec['budget_hit']} "
              f"comp_tok={rec['completion_tokens']}/{rec['thinking_budget']} "
              f"reas_ch={rec['reasoning_chars']} cont_ch={rec['content_chars']} "
              f"acc={rec.get('accuracy')} wall={rec['wall_s']}s tps={rec['decode_tps']}",
              flush=True)

    for trial in range(args.coding_samples):
        rec = run_one(driver, args.model, params,
                      [{"role": "user", "content": CODING_PROMPT}])
        rec.update({"task": "coding", "trial": trial})
        records.append(rec)
        print(f"[conv] code t{trial} finish={rec['finish_reason']} conv={rec['converged']} "
              f"budget_hit={rec['budget_hit']} "
              f"comp_tok={rec['completion_tokens']}/{rec['thinking_budget']} "
              f"reas_ch={rec['reasoning_chars']} cont_ch={rec['content_chars']} "
              f"wall={rec['wall_s']}s tps={rec['decode_tps']}", flush=True)

    summary = {args.task: _summ(records, args.task),
               "coding": _summ(records, "coding")}
    result = {"model": args.model, "axis": "convergence", "task": args.task, "params": params,
              "agg_ctx": args.agg_ctx, "records": records, "summary": summary}
    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    fname = "convergence.json" if args.task == "aggregation" else f"convergence_{args.task}.json"
    with open(os.path.join(out_dir, fname), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[conv] SUMMARY {json.dumps(summary)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
