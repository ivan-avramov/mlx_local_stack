"""CLI: run the reasoning ladder (variable-tracking) for one model on the box under test.

  cd benchmark && uv run python -m bench.run_reasoning --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/reasoning.json."""
import argparse
import json
import os

from .driver import MlxServeDriver
from .instrument import MemorySampler, await_model_pid, system_used_gb
from .model_params import params_for
from .reasoning import run_reasoning_ladder, REASONING_GRID

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    """Calibrate chars-per-token for the model."""
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    chars = len(_CAL_FILLER * 200)
    pt = out.get("prompt_tokens") or 1
    return chars / pt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Reasoning ladder (variable-tracking multi-hop probe)."
    )
    ap.add_argument("--model", required=True)
    ap.add_argument("--grid", default=",".join(str(g) for g in REASONING_GRID))
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--chain-len", type=int, default=4)
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Override production max_tokens (default: use model's production value)")
    ap.add_argument("--thinking-budget", type=int, default=None,
                    help="Override production thinking_budget (default: use model's production value)")
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)

    grid = tuple(int(x) for x in args.grid.split(","))

    driver = MlxServeDriver()

    if not args.no_preload:
        driver.preload(args.model)

    # Find the model server subprocess (best-effort; reasoning doesn't gate on memory)
    model_pid = await_model_pid()
    if model_pid is None:
        print("[reasoning] WARNING: model server process not found; "
              "memory sampling disabled", flush=True)

    cpt = calibrate_cpt(driver, args.model)

    # Build production params; apply any CLI overrides
    params = params_for(args.model)
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    if args.thinking_budget is not None:
        params["thinking_budget"] = args.thinking_budget

    print(f"[reasoning] {args.model} cpt={cpt:.2f} grid={grid} "
          f"threshold={args.threshold} samples={args.samples} "
          f"chain_len={args.chain_len}", flush=True)
    print(f"[reasoning] params: temp={params.get('temperature')} "
          f"top_p={params.get('top_p')} "
          f"thinking_budget={params.get('thinking_budget')} "
          f"max_tokens={params.get('max_tokens')}", flush=True)

    records = run_reasoning_ladder(
        driver, args.model, cpt,
        model_pid=model_pid,
        params=params,
        grid=grid,
        threshold=args.threshold,
        samples=args.samples,
        chain_len=args.chain_len,
        sampler_factory=MemorySampler,
    )

    for r in records:
        print(
            f"[reasoning] ctx={r['ctx']} acc={r['accuracy']} "
            f"samples={r['samples']} errors={r['errors']}",
            flush=True,
        )

    # Compute reasoning_effective_ctx: largest ctx with accuracy >= threshold
    passing = [r["ctx"] for r in records if r["accuracy"] >= args.threshold]
    reasoning_effective_ctx = max(passing) if passing else None

    result = {
        "model": args.model,
        "axis": "reasoning",
        "task": "vartrack",
        "threshold": args.threshold,
        "grid": list(grid),
        "records": records,
        "reasoning_effective_ctx": reasoning_effective_ctx,
    }

    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "reasoning.json"), "w") as f:
        json.dump(result, f, indent=2)

    print(f"[reasoning] REASONING_EFFECTIVE_CTX={reasoning_effective_ctx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
