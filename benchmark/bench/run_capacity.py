"""CLI: run the capacity+retrieval ladder for one model on the box under test.

  cd benchmark && uv run python -m bench.run_capacity --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/capacity_retrieval.json (+ capacity_ladder.jsonl)."""
import argparse
import json
import os

from .driver import MlxServeDriver
from .instrument import MemorySampler, await_model_pid, system_used_gb
from .model_params import params_for
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
    model_pid = await_model_pid()
    if model_pid is None:
        print("[capacity] ERROR: model server process not found; cannot RSS-gate", flush=True)
        return 1
    print(f"[capacity] model server pid={model_pid}", flush=True)
    cpt = calibrate_cpt(driver, args.model)
    print(f"[capacity] {args.model} cpt={cpt:.2f} grid={grid} gate={args.gate_gb}GB", flush=True)

    # Build production sampling params, then bound generation for the memory probe.
    # The gate is the MLX prefill spike, which is independent of decode length;
    # we don't pay for a long thinking decode here.
    params = {**params_for(args.model), "max_tokens": 256, "thinking_budget": 256}

    records = run_ladder(driver, args.model, cpt, idle_baseline_gb=idle_baseline,
                         model_pid=model_pid, params=params, grid=grid, gate_gb=args.gate_gb,
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
    # Provenance beside the ladder (operator-approved 2026-08-17): before this, NO capacity
    # artifact in the corpus carried a manifest, so every published memory-gate number had
    # unrecorded box/sha/KV provenance. Profile "production" is what params_for defaults to
    # above — recorded as used, with the probe's bounded-generation overrides.
    try:
        from . import provenance
        # gather + write into THIS module's out_dir, not provenance.write (which resolves its
        # own results root and therefore bypassed the RESULTS override — the full test suite
        # was writing real files into benchmark/results/ on every run until the D3 worker
        # caught it, 2026-08-17).
        man = provenance.gather(args.model, profile="production",
                                overrides={"max_tokens": 256, "thinking_budget": 256},
                                runtime={"probe": "capacity_ladder", "grid": list(grid),
                                         "gate_gb": args.gate_gb,
                                         "idle_baseline_gb": round(idle_baseline, 2)})
        with open(os.path.join(out_dir, "capacity_ladder.manifest.json"), "w") as f:
            json.dump(man, f, indent=2)
    except Exception as e:  # noqa: BLE001 — never lose a finished ladder to provenance
        print(f"[capacity] WARNING: manifest not written: {e}", flush=True)
    print(f"[capacity] GATE_PASS={sc['capacity_gate_pass']} "
          f"max_fitting_ctx={sc['max_fitting_ctx']} "
          f"retrieval_effective_ctx={sc['retrieval_effective_ctx']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
