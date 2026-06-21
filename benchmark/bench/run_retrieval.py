"""CLI: run the dedicated retrieval ladder (multi-needle NIAH) for one model on the box
under test, at PRODUCTION params (full thinking budget — the clean retrieval curve, not
the capacity probe's bounded co-signal).

  cd benchmark && uv run python -m bench.run_retrieval --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/retrieval.json."""
import argparse
import json
import os
import time

from .driver import MlxServeDriver
from .instrument import MemorySampler, system_used_gb, find_model_server_pid
from .model_params import params_for
from .retrieval import run_retrieval_ladder, RETRIEVAL_GRID, DEPTHS

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    chars = len(_CAL_FILLER * 200)
    pt = out.get("prompt_tokens") or 1
    return chars / pt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Retrieval ladder (multi-needle NIAH curve at production params).")
    ap.add_argument("--model", required=True)
    ap.add_argument("--grid", default=",".join(str(g) for g in RETRIEVAL_GRID))
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Override production max_tokens (default: model's production value)")
    ap.add_argument("--thinking-budget", type=int, default=None,
                    help="Override production thinking_budget (default: model's production value)")
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)

    grid = tuple(int(x) for x in args.grid.split(","))

    driver = MlxServeDriver()
    if not args.no_preload:
        driver.preload(args.model)

    # Find the model server subprocess (best-effort; retrieval doesn't gate on memory).
    model_pid = None
    for _ in range(10):
        model_pid = find_model_server_pid()
        if model_pid is not None:
            break
        time.sleep(1)
    if model_pid is None:
        print("[retrieval] WARNING: model server process not found; "
              "memory sampling disabled", flush=True)

    cpt = calibrate_cpt(driver, args.model)

    # Production params verbatim; apply explicit CLI overrides only.
    params = params_for(args.model)
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    if args.thinking_budget is not None:
        params["thinking_budget"] = args.thinking_budget

    print(f"[retrieval] {args.model} cpt={cpt:.2f} grid={grid} "
          f"threshold={args.threshold} samples={args.samples}", flush=True)
    print(f"[retrieval] params: temp={params.get('temperature')} "
          f"top_p={params.get('top_p')} "
          f"thinking_budget={params.get('thinking_budget')} "
          f"max_tokens={params.get('max_tokens')}", flush=True)

    records = run_retrieval_ladder(
        driver, args.model, cpt, model_pid=model_pid, params=params,
        grid=grid, threshold=args.threshold, samples=args.samples,
        sampler_factory=MemorySampler)

    for r in records:
        print(f"[retrieval] ctx={r['ctx']} acc={r['accuracy']} "
              f"per_depth={r['per_depth_acc']} errors={r['errors']}", flush=True)

    passing = [r["ctx"] for r in records if r["accuracy"] >= args.threshold]
    retrieval_effective_ctx = max(passing) if passing else None

    result = {
        "model": args.model,
        "axis": "retrieval",
        "task": "multi_needle_niah",
        "threshold": args.threshold,
        "grid": list(grid),
        "depths": list(DEPTHS),
        "records": records,
        "retrieval_effective_ctx": retrieval_effective_ctx,
    }

    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "retrieval.json"), "w") as f:
        json.dump(result, f, indent=2)

    print(f"[retrieval] RETRIEVAL_EFFECTIVE_CTX={retrieval_effective_ctx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
