"""W0 thinking-convergence probe (perf+convergence plan, 2026-06-21).

For ONE model at REALISTIC params (params_for ≡ opencode.json), run aggregation@8K +
a real coding prompt and record, per sample:
  - finish_reason  (the convergence signal: "stop" = closed thinking + emitted EOS on its
    own = CONVERGED; "length" = ran into thinking_budget/max_tokens = FAILURE)
  - completion_tokens, reasoning/content char split, has_answer
  - accuracy (aggregation only) so we see whether rambling also costs correctness

Convergence is judged by EOS rate (fraction finish_reason=="stop") + completion-length
distribution. Hitting the budget is NEVER a fix — the cap stays high; we want clean EOS.

  cd benchmark && PYTHONPATH=. ../.venv/bin/python -m bench.run_convergence --model <id>

Writes benchmark/results/<model>/convergence.json."""
import argparse
import json
import os
import time

from .driver import MlxServeDriver
from .model_params import params_for
from .aggregation import build_cwe, score_cwe

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


def run_one(driver, model, params, messages, targets=None) -> dict:
    r = driver.complete(model, messages, params)
    fr = r.get("finish_reason")
    rec = {
        "finish_reason": fr,
        "converged": fr == "stop",
        "completion_tokens": r.get("completion_tokens"),
        "reasoning_chars": len(r.get("reasoning") or ""),
        "content_chars": len(r.get("content") or ""),
        "has_answer": bool((r.get("content") or "").strip()),
        "decode_tps": r.get("decode_tps"),
        "wall_s": r.get("wall_s"),
    }
    if targets is not None:
        rec["accuracy"] = round(score_cwe(r.get("content", ""), targets), 3)
    return rec


def _summ(records, task) -> dict:
    rs = [r for r in records if r["task"] == task]
    if not rs:
        return {}
    eos = sum(1 for r in rs if r["converged"]) / len(rs)
    comps = sorted((r["completion_tokens"] or 0) for r in rs)
    out = {"n": len(rs), "eos_rate": round(eos, 3),
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
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="time-bound cap; converging samples stop well under it, ramblers hit it")
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)

    driver = MlxServeDriver()
    if not args.no_preload:
        t = driver.preload(args.model)
        print(f"[conv] preloaded {args.model} in {t}s", flush=True)
    params = params_for(args.model)
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    cpt = calibrate_cpt(driver, args.model)
    print(f"[conv] {args.model} cpt={cpt:.2f} temp={params['temperature']} "
          f"max_tokens={params['max_tokens']} thinking_budget={params.get('thinking_budget')}",
          flush=True)

    records = []
    for trial in range(args.samples):
        seed = args.agg_ctx * 1000 + trial
        ctx, targets, q = build_cwe(args.agg_ctx, cpt, k=5, seed=seed)
        rec = run_one(driver, args.model, params,
                      [{"role": "user", "content": ctx + "\n\n" + q}], targets=targets)
        rec.update({"task": "aggregation", "ctx": args.agg_ctx, "trial": trial})
        records.append(rec)
        print(f"[conv] agg t{trial} finish={rec['finish_reason']} "
              f"comp_tok={rec['completion_tokens']} reas_ch={rec['reasoning_chars']} "
              f"cont_ch={rec['content_chars']} acc={rec.get('accuracy')} "
              f"wall={rec['wall_s']}s tps={rec['decode_tps']}", flush=True)

    for trial in range(args.coding_samples):
        rec = run_one(driver, args.model, params,
                      [{"role": "user", "content": CODING_PROMPT}])
        rec.update({"task": "coding", "trial": trial})
        records.append(rec)
        print(f"[conv] code t{trial} finish={rec['finish_reason']} "
              f"comp_tok={rec['completion_tokens']} reas_ch={rec['reasoning_chars']} "
              f"cont_ch={rec['content_chars']} wall={rec['wall_s']}s tps={rec['decode_tps']}",
              flush=True)

    summary = {"aggregation": _summ(records, "aggregation"),
               "coding": _summ(records, "coding")}
    result = {"model": args.model, "axis": "convergence", "params": params,
              "agg_ctx": args.agg_ctx, "records": records, "summary": summary}
    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "convergence.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[conv] SUMMARY {json.dumps(summary)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
