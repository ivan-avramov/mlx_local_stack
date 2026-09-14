"""Run a capacity ladder; memory targets describe observations, never eligibility.

Use a fresh --out-tag for every run. Schema v2 keeps request completion, memory
and bounded retrieval co-scores separate. Redirect stdout to the detached run log.
"""
import argparse
import json
import math
import os
from pathlib import Path

from .driver import MlxServeDriver
from .instrument import MemorySampler, await_model_pid, system_used_gb
from .model_params import params_for, profile_names, registry_context_limit
from .capacity_ladder import run_ladder, DEFAULT_GRID, validate_completion
from .capacity_monitor import CapacityMonitor
from .convergence import resolved_thinking_budget, is_converged
from .scorecard import capacity_retrieval_scorecard, MEMORY_TARGET_GB

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    chars = len(_CAL_FILLER * 200)
    try:
        validate_completion(out)
    except ValueError as exc:
        raise ValueError("invalid calibration response") from exc
    cpt = chars / out["prompt_tokens"]
    if not 0.5 <= cpt <= 16:
        raise ValueError("implausible calibration chars/token for the fixed ASCII filler")
    return cpt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--grid", default=",".join(str(g) for g in DEFAULT_GRID))
    ap.add_argument("--memory-target-gb", "--gate-gb", dest="memory_target_gb",
                    type=float, default=MEMORY_TARGET_GB,
                    help="rough target only (default 48); --gate-gb is a deprecated spelling, not a stop rule")
    ap.add_argument("--sampling-profile", required=True, choices=profile_names())
    ap.add_argument("--out-tag", help="fresh suffix for ladder, scorecard and manifest; never overwrite")
    ap.add_argument("--expected-rung-seconds",
                    help="comma-separated matched baseline durations in grid order, for daemon rate/ETA assessment")
    ap.add_argument("--request-timeout", type=float, default=7200.0,
                    help="derived per-request timeout: 262K prefill precedent ~2200s plus headroom")
    ap.add_argument("--no-preload", action="store_true")
    ap.add_argument("--seed", type=int, default=0, help="explicit seed shared across the capacity rungs")
    args = ap.parse_args(argv)
    try:
        grid = tuple(int(x) for x in args.grid.split(","))
        expected = ([float(x) for x in args.expected_rung_seconds.split(",")]
                    if args.expected_rung_seconds else None)
        if not grid or any(x <= 0 for x in grid) or list(grid) != sorted(set(grid)):
            raise ValueError("grid must be positive and strictly increasing")
        if any(not math.isfinite(x) or x <= 0 for x in (args.memory_target_gb, args.request_timeout)):
            raise ValueError("memory target and request timeout must be positive finite values")
        if expected is not None and (len(expected) != len(grid) or
                                    any(not math.isfinite(x) or x <= 0 for x in expected)):
            raise ValueError("baseline must contain one positive finite duration per rung")
        if args.out_tag and (Path(args.out_tag).name != args.out_tag or args.out_tag in (".", "..")):
            raise ValueError("out-tag must be a filename suffix")
    except ValueError as exc:
        ap.error(str(exc))
    out_dir = Path(RESULTS) / args.model
    cl = "capacity_ladder" + (f".{args.out_tag}" if args.out_tag else "")
    cr = "capacity_retrieval" + (f".{args.out_tag}" if args.out_tag else "")
    destinations = [out_dir / f"{cl}.jsonl", out_dir / f"{cr}.json", out_dir / f"{cl}.manifest.json"]
    if any(p.exists() for p in destinations):
        ap.error("capacity output already exists; preserve it and use a fresh --out-tag")
    out_dir.mkdir(parents=True, exist_ok=True)

    with CapacityMonitor(len(grid), expected) as monitor:
        # Reserve the ladder before any model calls; flush every rung, including errors.
        with destinations[0].open("x") as journal:
            driver = MlxServeDriver()
            idle_baseline = system_used_gb()
            print(f"[capacity] idle baseline = {idle_baseline:.2f} GB", flush=True)
            monitor.stage("preload")
            if not args.no_preload:
                driver.preload(args.model)
            model_pid = await_model_pid()
            if model_pid is None:
                print("[capacity] ERROR: model process not found; cannot sample its RSS", flush=True)
                return 1
            monitor.stage("calibration")
            cpt = calibrate_cpt(driver, args.model)
            print(f"[capacity] {args.model} cpt={cpt:.2f} grid={grid} "
                  f"memory_target={args.memory_target_gb}GB (guideline)", flush=True)
            params = {**params_for(args.model, profile=args.sampling_profile),
                      "max_tokens": 256, "thinking_budget": 256, "seed": args.seed}
            context_limit = registry_context_limit(args.model)

            def save(row):
                row["thinking_budget"] = params["thinking_budget"]
                row["resolved_thinking_budget"] = resolved_thinking_budget(
                    row, context_limit=context_limit, max_tokens=params["max_tokens"])
                row["converged"] = (is_converged(row)
                                    if row["resolved_thinking_budget"] is not None else None)
                journal.write(json.dumps(row, allow_nan=False) + "\n")
                journal.flush()
                monitor.record(row)

            records = run_ladder(driver, args.model, cpt, idle_baseline_gb=idle_baseline,
                                 model_pid=model_pid, params=params, grid=grid,
                                 memory_target_gb=args.memory_target_gb,
                                 sampler_factory=MemorySampler, request_timeout=args.request_timeout,
                                 on_start=lambda ctx: monitor.stage(f"rung {ctx}"), on_record=save)
        monitor.stage("reporting")
        sc = capacity_retrieval_scorecard(args.model, records, memory_target_gb=args.memory_target_gb)
        sc["idle_baseline_gb"] = round(idle_baseline, 2)
        sc["requested_grid"] = list(grid)
        sc["grid_completed"] = len(records) == len(grid) and sc["execution_status"] == "completed"
        with destinations[1].open("x") as f:
            json.dump(sc, f, indent=2, allow_nan=False)
        manifest_ok = True
        try:
            from . import provenance
            man = provenance.gather(args.model, profile=args.sampling_profile,
                                    overrides={"max_tokens": 256, "thinking_budget": 256, "seed": args.seed},
                                    runtime={"probe": "capacity_ladder", "grid": list(grid),
                                             "capacity_schema_version": 2,
                                             "memory_target_gb": args.memory_target_gb,
                                             "expected_rung_seconds": expected,
                                             "idle_baseline_gb": round(idle_baseline, 2)})
            with destinations[2].open("x") as f:
                json.dump(man, f, indent=2, allow_nan=False)
        except Exception as exc:
            # Preserve completed rows, but do not label a provenance failure successful.
            manifest_ok = False
            print(f"[capacity] ERROR: manifest not written: {exc}", flush=True)
        print(f"[capacity] execution={sc['execution_status']} grid_completed={sc['grid_completed']} "
              f"max_completed_ctx={sc['max_completed_ctx']} "
              f"max_within_memory_target_ctx={sc['max_within_memory_target_ctx']} "
              f"retrieval_coscore_max_passing_ctx={sc['retrieval_coscore_max_passing_ctx']}", flush=True)
        monitor.exit_code = 0 if sc["grid_completed"] and manifest_ok else 1
        return monitor.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
