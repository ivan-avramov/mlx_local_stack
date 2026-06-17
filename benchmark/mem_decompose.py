#!/usr/bin/env python
"""benchmark/mem_decompose.py — decompose where MLX memory actually goes during
long-context prefill, to explain/validate the eval's `peak_memory` numbers.

WHY THIS EXISTS
---------------
The mlx-serve eval reports `timings.peak_memory` = mx.get_peak_memory(), which the
server NEVER resets (it only calls mx.clear_cache()). So that number is a *lifetime
high-water* of the subprocess and conflates four very different things:

  (a) the model-load transient,
  (b) KV pre-allocation to max_kv_cache_size (256K/192K) — not the ctx actually used,
  (c) the FP32 KV-quantization compilation spike (see mlx-vlm memory.md #7; the
      `--serialize-kv-quantization` mitigation defaults to OFF), and
  (d) the real per-context inference footprint.

This runner separates those phases IN-PROCESS (the only way to reset the peak counter
and isolate phases) and runs a serialize on/off A/B. It measures MLX allocator behavior
directly, not the HTTP path — the load/prealloc/quant-spike/pool phenomena are identical;
only the (small, constant) server overhead is excluded.

HYPOTHESES TESTED
  H1 KV pre-allocates to max_kv   -> kv_bytes ~constant across ctx (≈ full max-ctx KV)
  H2 peak conflates load+inference-> load_peak vs inference_peak differ
  H3 FP32 quant spike inflates    -> inference_peak(serialize=on) << (serialize=off)
  H4 D-6Q outlier is transient    -> its extra shows in load_peak / serialize=off only

USAGE
  uv run python benchmark/mem_decompose.py \
      --models mlx-community/gemma-4-31B-it-qat-6bit,mlx-community/gemma-4-26b-a4b-it-4bit \
      --ctxs 8000,32000 --serialize both

NOTE ON RUNTIME: dense prefill is ~50-60 tok/s, so 32K ≈ ~10 min, 128K ≈ ~35 min PER
(ctx × serialize × model). Start small; add 128000/196608/262144 only when you want the
true max-context footprint. Results stream to benchmark/results/mem_decompose.jsonl.
"""
import argparse
import json
import os
import time

import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.generate.common import maybe_quantize_kv_cache

GB = 1e9
RESULTS = os.path.join(os.path.dirname(__file__), "results")


def rss_gb():
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / GB
    except Exception:
        import resource

        m = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # macOS: bytes
        return (m if m > 1e9 else m * 1024) / GB


def _nbytes(o):
    if isinstance(o, mx.array):
        return o.nbytes
    if isinstance(o, (tuple, list)):
        return sum(_nbytes(x) for x in o)
    return 0


def cache_nbytes(cache):
    """Sum bytes held by all KV cache layers (handles fp16 KVCache, quantized tuples,
    RotatingKVCache, hybrid/linear state)."""
    return sum(_nbytes(getattr(c, "state", None)) for c in cache) / GB


def lookup_yaml(hf_path):
    """Pull max_kv_cache_size / prefill_step_size / kv_bits from main_models.yaml so the
    pre-allocation matches the deployed config. Falls back to sane defaults."""
    try:
        import yaml

        path = os.path.join(os.path.dirname(__file__), "..", "main_models.yaml")
        for m in yaml.safe_load(open(path))["models"]:
            if hf_path in (m.get("hf_path"), m.get("name")):
                return (
                    int(m.get("max_kv_cache_size", 262144)),
                    int(m.get("prefill_step_size", 512)),
                    int(m.get("kv_bits", 4)),
                )
    except Exception:
        pass
    return 262144, 512, 4


def lm_forward(model, chunk, cache):
    """Inner language-model forward (hidden states; skips lm_head) — matches what a
    prefill chunk does. Falls back to the full LanguageModel call if there's no `.model`."""
    lm = model.language_model
    inner = getattr(lm, "model", None)
    if inner is not None:
        return inner(inputs=chunk, cache=cache)
    return lm(inputs=chunk, cache=cache)


def prefill(model, ids, cache, step, kv_bits, serialize):
    n = ids.shape[1]
    done = 0
    while done < n:
        c = min(step, n - done)
        lm_forward(model, ids[:, done : done + c], cache)
        maybe_quantize_kv_cache(
            cache,
            quantized_kv_start=0,
            kv_group_size=64,
            kv_bits=kv_bits,
            kv_quant_scheme="uniform",
            serialize_kv_quantization=serialize,
        )
        mx.eval([cc.state for cc in cache])
        done += c


def log(msg):
    print(msg, flush=True)


def run_model(hf_path, ctxs, serialize_variants, out):
    max_kv, step, kv_bits = lookup_yaml(hf_path)
    log(f"\n{'='*78}\n# {hf_path}\n#   max_kv={max_kv}  prefill_step={step}  kv_bits={kv_bits}\n{'='*78}")

    # ---- phase 1: load (capture the load transient before any reset) ----
    mx.clear_cache()
    mx.reset_peak_memory()
    t0 = time.time()
    model, _ = load(hf_path)
    mx.eval(model.language_model.parameters())
    load_s = time.time() - t0
    load_peak = mx.get_peak_memory() / GB
    weights = mx.get_active_memory() / GB
    log(f"[load] {load_s:4.0f}s | weights_active={weights:5.1f}G | load_peak={load_peak:5.1f}G "
        f"| load_transient={load_peak-weights:+4.1f}G | rss={rss_gb():5.1f}G")
    out.write(json.dumps({"model": hf_path, "phase": "load", "load_s": round(load_s, 1),
                          "weights_active_gb": round(weights, 2), "load_peak_gb": round(load_peak, 2),
                          "rss_gb": round(rss_gb(), 2)}) + "\n"); out.flush()

    lm = model.language_model

    # ---- phase 2: KV pre-allocation probe (one tiny chunk) ----
    mx.reset_peak_memory()
    cache = lm.make_cache()
    ids1 = mx.random.randint(0, 200000, (1, step)); mx.eval(ids1)
    prefill(model, ids1, cache, step, kv_bits, False)
    kv1 = cache_nbytes(cache)
    log(f"[kv-prealloc] after 1 chunk ({step} tok): kv_bytes={kv1:5.2f}G "
        f"-> if this ≈ full-{max_kv//1000}K KV, the cache PRE-ALLOCATES (H1)")
    out.write(json.dumps({"model": hf_path, "phase": "kv_prealloc", "chunk_tokens": step,
                          "kv_bytes_gb": round(kv1, 3)}) + "\n"); out.flush()
    del cache; mx.clear_cache()

    # ---- phase 3: per (ctx × serialize) inference footprint ----
    log(f"\n{'ctx':>7} {'ser':>4} | {'inf_peak':>8} {'active':>7} {'pool':>6} {'rss':>6} "
        f"{'kv_bytes':>8} {'pf_tok/s':>8}")
    for ctx in ctxs:
        ctx = min(ctx, max_kv)
        ids = mx.random.randint(0, 200000, (1, ctx)); mx.eval(ids)
        for ser in serialize_variants:
            cache = lm.make_cache()
            mx.clear_cache()
            mx.reset_peak_memory()  # isolate inference from the load high-water (H2)
            t = time.time()
            prefill(model, ids, cache, step, kv_bits, ser)
            dt = time.time() - t
            inf_peak = mx.get_peak_memory() / GB
            active = mx.get_active_memory() / GB
            pool = mx.get_cache_memory() / GB
            rss = rss_gb()
            kvb = cache_nbytes(cache)
            tps = ctx / dt if dt else 0
            log(f"{ctx:>7} {str(ser):>4} | {inf_peak:7.1f}G {active:6.1f}G {pool:5.1f}G "
                f"{rss:5.1f}G {kvb:7.2f}G {tps:8.0f}")
            out.write(json.dumps({
                "model": hf_path, "phase": "infer", "ctx": ctx, "serialize_kv": ser,
                "inference_peak_gb": round(inf_peak, 2), "active_after_gb": round(active, 2),
                "pool_gb": round(pool, 2), "rss_gb": round(rss, 2), "kv_bytes_gb": round(kvb, 3),
                "prefill_tps": round(tps, 1), "weights_active_gb": round(weights, 2),
            }) + "\n"); out.flush()
            del cache; mx.clear_cache()

    del model
    mx.clear_cache()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", required=True, help="comma-separated HF paths")
    ap.add_argument("--ctxs", default="8000,32000", help="comma-separated context lengths")
    ap.add_argument("--serialize", default="both", choices=["off", "on", "both"],
                    help="--serialize-kv-quantization A/B (tests the FP32 quant-spike, H3)")
    ap.add_argument("--mem-limit-frac", type=float, default=0.9,
                    help="crash-guard: set MLX total-memory limit to this fraction of physical RAM")
    args = ap.parse_args()

    # crash guard so a heavy model at high ctx degrades (pool eviction) instead of OOM
    try:
        phys = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        mx.set_memory_limit(int(args.mem_limit_frac * phys))
    except Exception:
        pass

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    ctxs = [int(c) for c in args.ctxs.split(",")]
    ser = {"off": [False], "on": [True], "both": [False, True]}[args.serialize]

    os.makedirs(RESULTS, exist_ok=True)
    out_path = os.path.join(RESULTS, "mem_decompose.jsonl")
    with open(out_path, "w") as out:
        for m in models:
            run_model(m, ctxs, ser, out)
    log(f"\nwrote {out_path}")
    log("READ: H1 kv_bytes flat across ctx => pre-alloc | H2 load_peak vs inf_peak | "
        "H3 inf_peak(on)<<(off) => FP32 quant spike | H4 D-6Q extra in load/off only")


if __name__ == "__main__":
    main()
