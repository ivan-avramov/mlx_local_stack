"""CLI: run the capacity+retrieval ladder for one model on the box under test.

  cd benchmark && uv run python -m bench.run_capacity --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/capacity_retrieval.json (+ capacity_ladder.jsonl)."""
import argparse
import json
import os
import time

from .driver import MlxServeDriver
from .instrument import MemorySampler, system_used_gb, find_model_server_pid
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
    idle_baseline = system_used_gb()
    print(f"[capacity] idle baseline = {idle_baseline:.2f} GB", flush=True)
    if not args.no_preload:
        driver.preload(args.model)
    # Find the model server subprocess so we sample its ACTUAL RSS (the gate metric).
    model_pid = None
    for _ in range(10):
        model_pid = find_model_server_pid()
        if model_pid is not None:
            break
        time.sleep(1)
    if model_pid is None:
        print("[capacity] ERROR: model server process not found; cannot RSS-gate", flush=True)
        return 1
    print(f"[capacity] model server pid={model_pid}", flush=True)
    cpt = calibrate_cpt(driver, args.model)
    print(f"[capacity] {args.model} cpt={cpt:.2f} grid={grid} gate={args.gate_gb}GB", flush=True)

    records = run_ladder(driver, args.model, cpt, idle_baseline_gb=idle_baseline,
                         model_pid=model_pid, grid=grid, gate_gb=args.gate_gb,
                         sampler_factory=MemorySampler)
    for r in records:
        mp = r.get("server_peak_gb")
        mp = round(mp, 1) if isinstance(mp, (int, float)) else mp
        print(f"[capacity] ctx={r['ctx']} tok={r['prompt_tokens']} "
              f"MLXpeak={mp}GB/{args.gate_gb} (gate,spike) RSS={r['peak_rss_gb']}GB (steady) "
              f"sys={r['system_peak_gb']}GB acc={r['retrieval_acc']:.2f} "
              f"prefill={r['prefill_tps']} decode={r['decode_tps']} fits={r['fits']}"
              + (f" ERR={r['error']}" if r.get("error") else ""), flush=True)

    sc = capacity_retrieval_scorecard(args.model, records, gate_gb=args.gate_gb)
    sc["idle_baseline_gb"] = round(idle_baseline, 2)
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
