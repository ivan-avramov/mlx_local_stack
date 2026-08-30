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
    ap.add_argument("--sampling-profile", required=True,
                    choices=["coding", "deployed", "official", "production"],
                    help="params profile (O36: explicit on every run; 'deployed' for all new axes)")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Override profile max_tokens (default: use the profile's value)")
    ap.add_argument("--thinking-budget", type=int, default=None,
                    help="Override profile thinking_budget (default: use the profile's value)")
    ap.add_argument("--request-timeout", type=float, default=9600.0,
                    help="per-request HTTP timeout, DERIVED not SDK-default (O41): 81920-token "
                         "budget at ~12 tok/s at depth + ~20 min prefill at 156K, with headroom")
    ap.add_argument("--no-preload", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="reuse rungs persisted in reasoning.partial.jsonl by an earlier attempt of "
                         "the SAME design (grid/profile/samples/chain/threshold/params key)")
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

    # Build profile params; apply any CLI overrides
    params = params_for(args.model, profile=args.sampling_profile)
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

    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    partial_path = os.path.join(out_dir, "reasoning.partial.jsonl")
    design_key = json.dumps({
        "grid": list(grid), "profile": args.sampling_profile, "samples": args.samples,
        "chain_len": args.chain_len, "threshold": args.threshold,
        "params": {k: params.get(k) for k in ("temperature", "top_p", "top_k", "min_p",
                                              "max_tokens", "thinking_budget")},
    }, sort_keys=True)
    resume = None
    if args.resume and os.path.exists(partial_path):
        resume = {}
        with open(partial_path) as f:
            for line in f:
                row = json.loads(line)
                if row.get("key") == design_key:
                    resume[row["record"]["ctx"]] = row["record"]
        print(f"[reasoning] resume: {sorted(resume)} rungs persisted for this design", flush=True)

    def persist(rec):
        with open(partial_path, "a") as f:
            f.write(json.dumps({"key": design_key, "record": rec}) + "\n")
        print(f"[reasoning] rung done ctx={rec['ctx']} acc={rec['accuracy']} errors={rec['errors']}",
              flush=True)

    records = run_reasoning_ladder(
        driver, args.model, cpt,
        model_pid=model_pid,
        params=params,
        grid=grid,
        threshold=args.threshold,
        samples=args.samples,
        chain_len=args.chain_len,
        sampler_factory=MemorySampler,
        request_timeout=args.request_timeout,
        on_rung=persist,
        resume=resume,
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

    with open(os.path.join(out_dir, "reasoning.json"), "w") as f:
        json.dump(result, f, indent=2)

    print(f"[reasoning] REASONING_EFFECTIVE_CTX={reasoning_effective_ctx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
