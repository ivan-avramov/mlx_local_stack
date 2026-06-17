"""Speed-gain ceiling: fused dense SDPA (the fp16-KV path) vs the current manual
quantized_attention, at Qwen3.6 full-attn dims (n_q=24, n_kv=4, D=256, L=512).

mx.fast.scaled_dot_product_attention is the FUSED flash kernel used for fp16 KV
(no scores materialised). quantized_attention is the manual K-tile loop used for
TQ/uniform-quantized KV. The ratio is the UPPER BOUND on what a fused
quantized-KV kernel could approach (a real one sits between: dense-fused speed
minus dequant overhead).
"""
import time

import mlx.core as mx

from mlx_vlm.models.cache import KVCache
from mlx_vlm.turboquant import TurboQuantKVCache

N_Q, N_KV, D, L = 24, 4, 256, 512
SCALE = D ** -0.5
mx.random.seed(0)


def timed(fn, iters=3):
    o = fn(); mx.eval(o)
    best = 1e9
    for _ in range(iters):
        t0 = time.perf_counter(); o = fn(); mx.eval(o)
        best = min(best, time.perf_counter() - t0)
    return best * 1000


print(f"{'depth':>8} {'fused_ms':>9} {'TQ_ms':>9} {'TQ/fused':>9}")
for T in (8192, 32768, 65536, 131072, 196608):
    kf = mx.random.normal((1, N_KV, T, D)).astype(mx.bfloat16)
    vf = mx.random.normal((1, N_KV, T, D)).astype(mx.bfloat16)
    qf = mx.random.normal((1, N_Q, L, D)).astype(mx.bfloat16)
    fused = lambda: mx.fast.scaled_dot_product_attention(qf, kf, vf, scale=SCALE, mask="causal")

    fp = KVCache()
    fp.update_and_fetch(kf.astype(mx.float32), vf.astype(mx.float32))
    turbo = TurboQuantKVCache.from_cache(fp, bits=3)
    turbo.prefill_query_block_size = 256
    tk, tv = turbo.state
    qq = qf.astype(mx.float32)
    tq = lambda: turbo.quantized_attention(qq, tk, tv, scale=SCALE, mask="causal")

    fm, tm = timed(fused), timed(tq)
    print(f"{T:>8} {fm:>9.2f} {tm:>9.2f} {tm/fm:>8.1f}x")
