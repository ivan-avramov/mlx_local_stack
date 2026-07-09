"""Micro-bench: 2-pass fused MSE decode kernel (long-T, GQA tile-reuse).

Task 3 apples-to-apples baseline. Drives the real
``TurboQuantKVCache.decode_attention`` 2-pass path (total_tokens > 2048) at
distill/Qwen-like dims (head_dim=256, kv_heads=4, R=6) for long T, and compares
three configs on the SAME box/session:

  * legacy   -> R x-redundant kv read (one simdgroup per q-head)  [baseline]
  * tilereuse-> GQA tile-reuse pass 1 (G heads/simdgroup, contiguous block split)
  * fp16 SDPA-> mx.fast.scaled_dot_product_attention on fp16-dequant KV  [the bar]

Both TQ configs go through the identical rotation/prep/pass-2/inverse-rotation,
so the delta is purely the pass-1 kernel + its grid. Records ms/token + tok/s +
max-abs-diff vs a full-fp32 dequant reference. The 262144 cell is guarded (M2 is
capacity-unreliable >192K co-resident).

Run from the stack dir:
  PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/bench_decode_2pass.py
"""
import time

import mlx.core as mx

import mlx_vlm.turboquant as tq
from mlx_vlm.models.base import scaled_dot_product_attention
from mlx_vlm.models.cache import KVCache
from mlx_vlm.turboquant import TurboQuantKVCache

# ---- track which pass-1 kernel actually ran (confirm the path under test) ----
_orig_new = tq._fused_mse_decode_2pass_1_kernel
_orig_legacy = tq._fused_mse_decode_2pass_1_kernel_legacy
_calls = {"new": 0, "legacy": 0}


def _tracked_new(*a, **k):
    _calls["new"] += 1
    return _orig_new(*a, **k)


def _tracked_legacy(*a, **k):
    _calls["legacy"] += 1
    return _orig_legacy(*a, **k)


tq._fused_mse_decode_2pass_1_kernel = _tracked_new
tq._fused_mse_decode_2pass_1_kernel_legacy = _tracked_legacy


def bench(fn, iters=30, warmup=8):
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


def run(dim=256, n_kv=4, gqa=6, bits=3, T=40000):
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
    mx.eval(ref)

    # fp16 dequant KV for the SDPA bar (same T, L=1 decode).
    k16 = deq_k.astype(mx.float16)
    v16 = deq_v.astype(mx.float16)

    results = {}
    for tag, legacy in (("legacy", True), ("tilereuse", False)):
        cache._decode_2pass_use_legacy = legacy
        _calls["new"] = _calls["legacy"] = 0

        def call():
            return scaled_dot_product_attention(
                q, tk, tv, cache, scale=scale, mask=None
            )

        out = call()
        mx.eval(out)
        diff = mx.max(mx.abs(out.astype(mx.float32) - ref)).item()
        sec = bench(call)
        path_ok = _calls["legacy"] > 0 if legacy else _calls["new"] > 0
        results[tag] = (sec, diff, path_ok)

    def call_fp16():
        return mx.fast.scaled_dot_product_attention(
            q, k16, v16, scale=scale, mask=None
        )

    mx.eval(call_fp16())
    sec_fp16 = bench(call_fp16)

    leg_s, leg_d, leg_ok = results["legacy"]
    new_s, new_d, new_ok = results["tilereuse"]
    print(
        f"  dim={dim} n_kv={n_kv} R={gqa} bits={bits} T={T:>7}"
        f"  legacy {1.0/leg_s:8.1f} tok/s | tilereuse {1.0/new_s:8.1f} tok/s"
        f" | fp16 {1.0/sec_fp16:8.1f} tok/s"
        f"  || vs-legacy {leg_s/new_s:5.2f}x  vs-fp16 {sec_fp16/new_s:5.2f}x"
        f"  diff(new) {new_d:.4f}"
        f"  [{'OK' if (leg_ok and new_ok) else 'PATH?!'}]"
    )
    del cache, tk, tv, deq_k, deq_v, k16, v16, ref
    mx.clear_cache()


if __name__ == "__main__":
    print("=" * 118)
    print(f"2-pass fused MSE decode micro-bench  ({mx.device_info()['device_name']})")
    print("=" * 118)
    for bits in (3, 4):
        for T in (40000, 131072, 262144):
            try:
                run(dim=256, n_kv=4, gqa=6, bits=bits, T=T)
            except Exception as e:  # noqa: BLE001
                print(f"  T={T} bits={bits}: SKIP ({str(e)[:80]})")
        print("  --")
    print("DONE")
