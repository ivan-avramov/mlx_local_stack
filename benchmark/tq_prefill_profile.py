"""Profile what dominates Qwen3.6-27B TQ prefill at large context, to decide if
interactive 200K is fixable.

Real arch (config): 64 layers = 16 full-attn (TQ quantized_attention, O(T^2))
+ 48 GatedDeltaNet (linear, O(T)) + 64 MLP (O(T)). hidden 5120, inter 17408,
n_q 24 / n_kv 4, head_dim 256. prefill_step L=512.

Strategy: time the per-512-chunk cost of each component at real dims:
  - quantized_attention vs context depth d  -> the O(d) attention term
  - MLP forward (x64 layers)                -> fixed O(T) term
  - TQ quantize of a 512-token chunk (x16)  -> fixed O(T) term
Then total_prefill(T) = sum_over_chunks[ 16*attn(d) + fixed_per_chunk ] + GDN.
GDN(+overhead) is backed out from a measured end-to-end prefill anchor.
"""
import time

import mlx.core as mx
import mlx.nn as nn

from mlx_vlm.models.cache import KVCache
from mlx_vlm.turboquant import TurboQuantKVCache

HIDDEN, N_Q, N_KV, HEAD_DIM, INTER = 5120, 24, 4, 256, 17408
N_FULL_ATTN, N_MLP = 16, 64
L = 512
SCALE = HEAD_DIM ** -0.5
mx.random.seed(0)


def timed(fn, iters=3):
    fn(); mx.eval  # build
    out = fn(); mx.eval(out)
    best = 1e9
    for _ in range(iters):
        t0 = time.perf_counter()
        o = fn(); mx.eval(o)
        best = min(best, time.perf_counter() - t0)
    return best * 1000  # ms


# --- attention vs depth ---
def attn_at_depth(T):
    fp = KVCache()
    fp.update_and_fetch(mx.random.normal((1, N_KV, T, HEAD_DIM)),
                        mx.random.normal((1, N_KV, T, HEAD_DIM)))
    turbo = TurboQuantKVCache.from_cache(fp, bits=3)
    turbo.prefill_query_block_size = 256
    tk, tv = turbo.state
    q = mx.random.normal((1, N_Q, L, HEAD_DIM))
    return timed(lambda: turbo.quantized_attention(q, tk, tv, scale=SCALE, mask="causal"))


# --- MLP (one layer), QUANTIZED 6-bit like the real UD-MLX-6bit weights ---
GS, BITS = 64, 6
def q(w):  # w in [out, in] (Linear) layout
    return mx.quantize(w, group_size=GS, bits=BITS)
wg_q, wg_s, wg_b = q(mx.random.normal((INTER, HIDDEN)) * 0.02)   # gate [17408,5120]
wu_q, wu_s, wu_b = q(mx.random.normal((INTER, HIDDEN)) * 0.02)   # up
wd_q, wd_s, wd_b = q(mx.random.normal((HIDDEN, INTER)) * 0.02)   # down [5120,17408]
x = mx.random.normal((1, L, HIDDEN))
def mlp():
    g = mx.quantized_matmul(x, wg_q, wg_s, wg_b, transpose=True, group_size=GS, bits=BITS)
    u = mx.quantized_matmul(x, wu_q, wu_s, wu_b, transpose=True, group_size=GS, bits=BITS)
    h = nn.silu(g) * u
    return mx.quantized_matmul(h, wd_q, wd_s, wd_b, transpose=True, group_size=GS, bits=BITS)
mlp_ms = timed(mlp)

# --- TQ quantize of one 512-chunk (one full-attn layer) ---
def quant_chunk():
    fp = KVCache()
    fp.update_and_fetch(mx.random.normal((1, N_KV, L, HEAD_DIM)),
                        mx.random.normal((1, N_KV, L, HEAD_DIM)))
    return TurboQuantKVCache.from_cache(fp, bits=3).state[0].norms
quant_ms = timed(quant_chunk)

depths = [8192, 16384, 32768, 65536, 131072, 196608]
attn = {d: attn_at_depth(d) for d in depths}

print(f"\nMLP/layer={mlp_ms:.2f}ms  ->  x{N_MLP} = {mlp_ms*N_MLP:.1f}ms/chunk")
print(f"TQ-quant/layer={quant_ms:.2f}ms -> x{N_FULL_ATTN} = {quant_ms*N_FULL_ATTN:.1f}ms/chunk")
print(f"fixed (MLP+quant)/chunk = {mlp_ms*N_MLP + quant_ms*N_FULL_ATTN:.1f}ms\n")
print(f"{'depth':>8} {'attn/layer_ms':>14} {'attn x16_ms':>12}")
for d in depths:
    print(f"{d:>8} {attn[d]:>14.2f} {attn[d]*N_FULL_ATTN:>12.1f}")

# integrate attention over a full prefill to context T (trapezoid over depths)
def attn_total_ms(T):
    # chunks at depths 0..T step L; attn(d) ~ linear in d -> integral / L
    pts = sorted([d for d in depths if d <= T] + [T])
    # sample attn(d) linearly; use measured points, linear-interp/extrapolate
    import bisect
    ks = sorted(attn)
    def a(d):
        if d <= ks[0]: return attn[ks[0]] * d / ks[0]
        if d >= ks[-1]: return attn[ks[-1]] * d / ks[-1]
        i = bisect.bisect_left(ks, d)
        lo, hi = ks[i-1], ks[i]
        f = (d - lo) / (hi - lo)
        return attn[lo] + f * (attn[hi] - attn[lo])
    # sum over chunk depths
    tot = 0.0
    d = 0
    while d < T:
        tot += a(d)
        d += L
    return tot * N_FULL_ATTN  # x16 layers, ms

mlp_chunk = mlp_ms * N_MLP
quant_chunk_ms = quant_ms * N_FULL_ATTN
N_GDN = 48
print(f"\nMLP(6-bit)/layer={mlp_ms:.2f}ms x{N_MLP} = {mlp_chunk:.0f}ms/chunk; "
      f"quant x16 = {quant_chunk_ms:.0f}ms/chunk")

# Anchor non-attention cost to MEASURED end-to-end prefill (reliable):
MEASURED = {16000: 171.0, 64000: 845.0}  # seconds (needle wall - decode)
for T, wall in MEASURED.items():
    at = attn_total_ms(T) / 1000
    nchunks = T / L
    non_attn = wall - at                      # GDN + MLP + quant + norms + overhead
    gdn_chunk = (non_attn * 1000) / nchunks - mlp_chunk - quant_chunk_ms
    print(f"\nT={T}: measured={wall:.0f}s  attn={at:.0f}s ({at/wall*100:.0f}%)  "
          f"non-attn={non_attn:.0f}s ({non_attn/wall*100:.0f}%)")
    print(f"   non-attn/chunk={non_attn*1000/nchunks:.0f}ms = "
          f"MLP {mlp_chunk:.0f} + quant {quant_chunk_ms:.0f} + GDN(48)+norms ~{gdn_chunk:.0f}ms")

# Project 200K using non-attn/chunk from the 64K anchor (O(T), constant/chunk)
na_per_chunk = (845.0 - attn_total_ms(64000) / 1000) / (64000 / L)
at200 = attn_total_ms(200000) / 1000
na200 = na_per_chunk * (200000 / L)
print(f"\nPROJECT T=200000: attn={at200:.0f}s + non-attn={na200:.0f}s "
      f"= {at200+na200:.0f}s (~{(at200+na200)/60:.0f} min); attn share={at200/(at200+na200)*100:.0f}%")
