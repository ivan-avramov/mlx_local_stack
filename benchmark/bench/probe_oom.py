"""L1-vs-L2 OOM attribution probe (perf+convergence plan, L3).

Sends N SEQUENTIAL long-context requests to the live router and reports, per request,
finish_reason / completion / peak_mem_gb / wall + any error (OOM/disconnect). This is an
infra/memory probe, so it uses the no-think retrieval config (max_tokens small,
thinking_budget 0) — the OOM is a PREFILL-memory event, independent of thinking.

Attribution (vary the ROUTER env between runs, no fork edit):
  - N=1  -> isolates L1 (single-request prefill scratch at the configured prefill_step).
            Only one session ever exists, so L2 accumulation cannot occur.
  - N>=3 with MLX_VLM_CACHE_SESSION_MAX=8 (default, anon on) -> each request makes a new
            anon session -> exposes L2 accumulation (peak climbs, eventually OOM).
  - same N with MLX_VLM_CACHE_SESSION_MAX=0/1 -> no accumulation; survives if L2 was it.

  cd benchmark && PYTHONPATH=. ../.venv/bin/python -m bench.probe_oom \
      --model Qwen3.6-27B-UD-MLX-6bit --ctx 262144 --samples 5

Prints a line per request; writes nothing (read the stdout log)."""
import argparse
import json
import time

from .driver import MlxServeDriver
from .model_params import params_for
from .retrieval import build_context, make_question, hits

_CAL = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    out = driver.complete(model, [{"role": "user", "content": _CAL * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    return len(_CAL * 200) / (out.get("prompt_tokens") or 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="L1/L2 OOM attribution probe.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--ctx", type=int, default=262144)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--thinking-budget", type=int, default=0)
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)

    driver = MlxServeDriver()
    if not args.no_preload:
        print(f"[oom] preloading {args.model} ...", flush=True)
        print(f"[oom] preloaded in {driver.preload(args.model)}s", flush=True)
    cpt = calibrate_cpt(driver, args.model)
    params = params_for(args.model)
    params["max_tokens"] = args.max_tokens
    params["thinking_budget"] = args.thinking_budget
    print(f"[oom] {args.model} ctx={args.ctx} cpt={cpt:.2f} samples={args.samples} "
          f"max_tokens={args.max_tokens} thinking_budget={args.thinking_budget}", flush=True)

    for trial in range(args.samples):
        seed = args.ctx * 1000 + trial
        ctx, needles = build_context(args.ctx, cpt, seed=seed)
        msgs = [{"role": "user", "content": ctx + "\n\n" + make_question(needles)}]
        t0 = time.perf_counter()
        try:
            r = driver.complete(args.model, msgs, params, timeout=3600)
            n_hit = sum(hits(r.get("content", ""), needles))
            print(f"[oom] t{trial} OK finish={r.get('finish_reason')} "
                  f"prompt_tok={r.get('prompt_tokens')} comp_tok={r.get('completion_tokens')} "
                  f"peak_mem_gb={r.get('peak_mem_gb')} hits={n_hit}/{len(needles)} "
                  f"prefill_s={r.get('prefill_s')} wall={r.get('wall_s')}s", flush=True)
        except Exception as e:  # noqa: BLE001
            dt = round(time.perf_counter() - t0, 1)
            print(f"[oom] t{trial} ERROR after {dt}s: {type(e).__name__}: "
                  f"{str(e)[:200]}", flush=True)
    print("[oom] DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
