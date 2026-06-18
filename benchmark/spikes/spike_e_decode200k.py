"""
Spike E — real production TurboQuant decode_attention baseline at long context.

Drives the ACTUAL fork decode path (2-pass fused MSE flash kernel + block ladder)
on a TurboQuantKVCache populated to T tokens, kv_bits=3, Qwen dims. Reports the
attention-step latency and implied bandwidth, judged against:
  - the ~310 GB/s practical peak (Spike D),
  - fp16 dense mx.fast SDPA decode (Spike D: 3.52 ms @ 200K, 233 GB/s),
  - the R=6x GQA-redundancy hypothesis.

Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_e_decode200k.py
"""
import time
import mlx.core as mx
from mlx_vlm.turboquant import TurboQuantKVCache

B, N_Q, N_KV, D = 1, 24, 4, 256
R = N_Q // N_KV
BITS = 3
PW = (D * BITS + 31) // 32
scale = 1.0 / (D ** 0.5)


def bench(fn, iters=25, warmup=8):
    for _ in range(warmup):
        mx.eval(fn())
    mx.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        mx.eval(fn())
    mx.synchronize()
    return (time.perf_counter() - t0) / iters


def build_cache(T):
    cache = TurboQuantKVCache(bits=BITS, seed=0)
    step = 32768
    t = 0
    while t < T:
        n = min(step, T - t)
        k = mx.random.normal((B, N_KV, n, D)).astype(mx.float16)
        v = mx.random.normal((B, N_KV, n, D)).astype(mx.float16)
        cache.update_and_fetch(k, v)
        mx.eval(cache.keys, cache.values)
        t += n
    return cache


print("=" * 76)
print(f"SPIKE E — real TurboQuant decode_attention  ({mx.device_info()['device_name']})")
print(f"  B={B} n_q={N_Q} n_kv={N_KV} R={R} D={D} kv_bits={BITS}  peak~310GB/s")
print("=" * 76)
print(f"{'T':>8} {'attn ms':>9} {'tok/s(attn)':>11} {'min-BW':>9} {'Rx-BW':>9}   vs fp16-SDPA")

fp16_ref = {16384: 0.642, 65536: 1.327, 131072: 2.339, 200000: 3.520}  # from Spike D

for T in (16384, 65536, 131072, 200000):
    cache = build_cache(T)
    q = mx.random.normal((B, N_Q, 1, D)).astype(mx.float16)
    mx.eval(q)
    ks, vs = cache.state

    def call():
        return cache.decode_attention(q, ks, vs, scale=scale, mask="causal")

    try:
        out = call(); mx.eval(out)
        sec = bench(call)
        kv_min = 2 * N_KV * T * PW * 4 / 1e9 + 2 * N_KV * T * 2 / 1e9   # read K+V once
        kv_rx = kv_min * R                                              # read per q-head (R x)
        ref = fp16_ref.get(T)
        vs_ref = f"{ref/(sec*1e3):.2f}x {'faster' if ref> sec*1e3 else 'SLOWER'}" if ref else "-"
        print(f"{T:>8} {sec*1e3:9.3f} {1.0/sec:11.0f} {kv_min/sec:8.1f}G {kv_rx/sec:8.1f}G   {vs_ref}")
    except Exception as e:  # noqa
        print(f"{T:>8}  FAILED: {str(e)[:120]}")
    del cache
    mx.clear_cache()

print("\nInterpretation: if min-BW << 310 and Rx-BW ~ 310, the kernel is reading R x"
      "\n(the GQA redundancy). If min-BW ~ 310, it's already bandwidth-efficient.")
print("DONE")
