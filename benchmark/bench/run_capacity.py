"""CLI: run the capacity+retrieval ladder for one model on the box under test.

  cd benchmark && uv run python -m bench.run_capacity --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/capacity_retrieval.json (+ capacity_ladder.jsonl)."""
import argparse
import json
import os

from .driver import MlxServeDriver
from .instrument import MemorySampler
from .capacity_ladder import run_ladder, DEFAULT_GRID, GATE_GB
from .scorecard import capacity_retrieval_scorecard

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    chars = len(_CAL_FILLER * 200)
    pt = out.get("prompt_tokens") or 1
    return chars / pt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--grid", default=",".join(str(g) for g in DEFAULT_GRID))
    ap.add_argument("--gate-gb", type=float, default=GATE_GB)
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)
    grid = tuple(int(x) for x in args.grid.split(","))

    driver = MlxServeDriver()
    if not args.no_preload:
        driver.preload(args.model)
    cpt = calibrate_cpt(driver, args.model)
    print(f"[capacity] {args.model} cpt={cpt:.2f} grid={grid} gate={args.gate_gb}GB", flush=True)

    records = run_ladder(driver, args.model, cpt, grid=grid, gate_gb=args.gate_gb,
                         sampler_factory=MemorySampler)
    for r in records:
        print(f"[capacity] ctx={r['ctx']} footprint={r['model_footprint_gb']}GB "
              f"sys_peak={r['system_peak_gb']}GB acc={r['retrieval_acc']:.2f} "
              f"prefill={r['prefill_tps']}tok/s decode={r['decode_tps']}tok/s fits={r['fits']}",
              flush=True)

    sc = capacity_retrieval_scorecard(args.model, records, gate_gb=args.gate_gb)
    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "capacity_ladder.jsonl"), "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(out_dir, "capacity_retrieval.json"), "w") as f:
        json.dump(sc, f, indent=2)
    print(f"[capacity] GATE_PASS={sc['capacity_gate_pass']} "
          f"max_fitting_ctx={sc['max_fitting_ctx']} "
          f"retrieval_effective_ctx={sc['retrieval_effective_ctx']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
