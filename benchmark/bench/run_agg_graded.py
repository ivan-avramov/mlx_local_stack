"""Graded aggregation probe — the DIFFERENTIATING version of the CWE task.

The full CWE probe (find top-5 among ~2000 distinct words) makes EVERY model blow the
thinking budget — it cannot enumerate that many, so it gives no differentiating signal
("none of them do it"). This probe instead ladders the ENUMERATION LOAD (number of distinct
distractor words) from small to large at a FIXED context-modest setup + fixed budget, to
find each model's "enumeration cliff": the n_distinct at which it stops converging / loses
accuracy.

Interpretation:
  - A model that SHORTCUTS (recognizes the frequent words without enumerating) converges +
    stays accurate across the whole ladder — best.
  - A model that ENUMERATES exhaustively has a cliff: converged_rate drops (budget hit) once
    n_distinct exceeds what fits in budget; accuracy may persist (forced answer) or degrade.
  - The cliff location + accuracy curve differentiates models / quants / archs.

converged = finish=="stop" AND completion_tokens < thinking_budget (the run_convergence rule).
Targets appear 12x, distractors 3x (clear top-5). Total words stay modest (60 + 3*n_distractor,
~0.1-1.6K words across the default ladder) so this isolates enumeration load, not raw context.

  cd benchmark && PYTHONPATH=. <py> -m bench.run_agg_graded --model X
     [--loads 15,30,60,120,250,500] [--samples 2] [--temperature 0.7] [--budget 16384]

Writes benchmark/results/<model>/agg_graded.json."""
import argparse
import json
import os

from .driver import MlxServeDriver
from .model_params import params_for
from .aggregation import build_cwe, score_cwe

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
DEFAULT_LOADS = (15, 30, 60, 120, 250, 500)  # n_distractor; n_distinct = +K
FREQ_COMMON = 12
FREQ_UNCOMMON = 3
K = 5


def run_rung(driver, model, params, n_distractor, samples, seed0):
    budget = params.get("thinking_budget")
    recs = []
    for t in range(samples):
        ctx, targets, q = build_cwe(0, 4.6, k=K, freq_common=FREQ_COMMON,
                                    freq_uncommon=FREQ_UNCOMMON, seed=seed0 + t,
                                    n_distractor=n_distractor)
        r = driver.complete(model, [{"role": "user", "content": ctx + "\n\n" + q}], params)
        ct = r.get("completion_tokens")
        bh = budget is not None and ct is not None and ct >= budget
        recs.append({
            "n_distractor": n_distractor,
            "n_distinct": n_distractor + K,
            "total_words": K * FREQ_COMMON + n_distractor * FREQ_UNCOMMON,
            "finish_reason": r.get("finish_reason"),
            "budget_hit": bh,
            "converged": (r.get("finish_reason") == "stop") and not bh,
            "completion_tokens": ct,
            "accuracy": round(score_cwe(r.get("content", ""), targets), 3),
            "decode_tps": r.get("decode_tps"),
            "wall_s": r.get("wall_s"),
        })
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Graded CWE aggregation probe (enumeration-load ladder).")
    ap.add_argument("--model", required=True)
    ap.add_argument("--loads", default=",".join(str(x) for x in DEFAULT_LOADS),
                    help="comma list of n_distractor (enumeration load) rungs")
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--budget", type=int, default=16384, help="thinking_budget for the probe")
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)

    loads = [int(x) for x in args.loads.split(",") if x.strip()]
    driver = MlxServeDriver()
    if not args.no_preload:
        print(f"[graded] preloaded {args.model} in {driver.preload(args.model)}s", flush=True)
    params = params_for(args.model)
    params["thinking_budget"] = args.budget
    if args.temperature is not None:
        params["temperature"] = args.temperature

    print(f"[graded] {args.model} temp={params['temperature']} budget={args.budget} "
          f"loads(n_distractor)={loads}", flush=True)

    records, summary = [], []
    for nd in loads:
        recs = run_rung(driver, args.model, params, nd, args.samples, seed0=nd * 1000)
        records.extend(recs)
        n = len(recs)
        conv = sum(1 for r in recs if r["converged"]) / n
        bh = sum(1 for r in recs if r["budget_hit"]) / n
        acc = sum(r["accuracy"] for r in recs) / n
        comps = sorted(r["completion_tokens"] or 0 for r in recs)
        row = {"n_distractor": nd, "n_distinct": nd + K,
               "total_words": K * FREQ_COMMON + nd * FREQ_UNCOMMON,
               "converged_rate": round(conv, 3), "budget_hit_rate": round(bh, 3),
               "mean_accuracy": round(acc, 3), "median_completion_tokens": comps[n // 2]}
        summary.append(row)
        print(f"[graded] n_distinct={nd + K:<4} words={row['total_words']:<5} "
              f"converged={row['converged_rate']} budget_hit={row['budget_hit_rate']} "
              f"acc={row['mean_accuracy']} med_tok={row['median_completion_tokens']}", flush=True)

    # The enumeration cliff: largest n_distinct that still fully converges.
    converged_loads = [s["n_distinct"] for s in summary if s["converged_rate"] >= 1.0]
    cliff = max(converged_loads) if converged_loads else None
    result = {"model": args.model, "axis": "agg_graded", "params": params,
              "loads": loads, "records": records, "summary": summary,
              "enumeration_cliff_n_distinct": cliff}
    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "agg_graded.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[graded] ENUMERATION_CLIFF(n_distinct fully-converged)={cliff}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
