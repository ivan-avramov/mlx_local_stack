"""Micro-bench: single-pass fused MSE decode kernel (_fused_mse_decode_kernel).

Times the CURRENT vs GQA tile-reuse single-pass decode at Qwen-like dims
(head_dim=256, kv_heads=4, R=6, 3-bit) for T <= 2048 (single-pass regime).

It drives the real `TurboQuantKVCache.decode_attention` dispatch (which routes
to the single-pass kernel when total_tokens <= 2048), verifies output against a
full-fp32 dequant reference, and records ms/token + decode tok/s.

Run from the stack dir:
  PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/bench_decode_singlepass.py
"""
import time

import mlx.core as mx

import mlx_vlm.turboquant as tq
from mlx_vlm.models.base import scaled_dot_product_attention
from mlx_vlm.models.cache import KVCache
from mlx_vlm.turboquant import TurboQuantKVCache

# ---- track single-pass kernel invocation (confirm the path under test) -------
_orig_singlepass = tq._fused_mse_decode_kernel
_calls = {"singlepass": 0}


def _tracked_singlepass(*a, **k):
    _calls["singlepass"] += 1
    return _orig_singlepass(*a, **k)


tq._fused_mse_decode_kernel = _tracked_singlepass


def bench(fn, iters=50, warmup=10):
    for _ in range(warmup):
        mx.eval(fn())
    mx.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        mx.eval(fn())
    mx.synchronize()
    return (time.perf_counter() - t0) / iters


def build_cache(dim, n_kv, gqa, bits, T, seed=0):
    mx.random.seed(seed)
    keys = mx.random.normal((1, n_kv, T, dim)).astype(mx.float16)
    values = mx.random.normal((1, n_kv, T, dim)).astype(mx.float16)
    fp_cache = KVCache()
    fp_cache.update_and_fetch(keys, values)
    cache = TurboQuantKVCache.from_cache(fp_cache, bits=float(bits))
    tk, tv = cache.state
    return cache, tk, tv


def run(dim=256, n_kv=4, gqa=6, bits=3, T=2048):
    n_q = n_kv * gqa
    cache, tk, tv = build_cache(dim, n_kv, gqa, bits, T)
    q = mx.random.normal((1, n_q, 1, dim)).astype(mx.float16)
    scale = dim**-0.5

    deq_k, deq_v = cache.dequantize(tk, tv)
    ref = mx.fast.scaled_dot_product_attention(
        q.astype(mx.float32),
        deq_k.astype(mx.float32),
        deq_v.astype(mx.float32),
        scale=scale,
        mask=None,
    )

    _calls["singlepass"] = 0

    def call():
        return scaled_dot_product_attention(q, tk, tv, cache, scale=scale, mask=None)

    out = call()
    mx.eval(out)
    diff = mx.max(mx.abs(out.astype(mx.float32) - ref)).item()
    sec = bench(call)
    path = "single-pass" if _calls["singlepass"] > 0 else "OTHER(!)"
    print(
        f"  dim={dim} n_kv={n_kv} R={gqa} bits={bits} T={T:>5}  "
        f"{sec*1e3:8.4f} ms/tok  {1.0/sec:8.1f} tok/s  diff {diff:.5f}  [{path}]"
    )
    return sec, diff, path


if __name__ == "__main__":
    print("=" * 88)
    print(
        f"single-pass fused MSE decode micro-bench  ({mx.device_info()['device_name']})"
    )
    print("=" * 88)
    for T in (512, 1024, 2048):
        run(dim=256, n_kv=4, gqa=6, bits=3, T=T)
    print("  --")
    run(dim=256, n_kv=4, gqa=6, bits=4, T=2048)
    run(dim=128, n_kv=4, gqa=6, bits=3, T=2048)
    run(dim=256, n_kv=8, gqa=1, bits=3, T=2048)  # R=1 control (no tile-reuse)
    print("\nDONE")
