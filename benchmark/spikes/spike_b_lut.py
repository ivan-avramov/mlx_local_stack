"""
Spike B — LUT scoring vs MMA at 3-bit (and 4-bit) for the QK^T scoring step.

All three compute score[M,T] = norm_t * sum_d q[m,d] * codebook[idx[t,d]]
from a *packed* low-bit K, and are checked against an fp32 dequant reference.

  scalar : codebase style — per (m,t) simdgroup, bit-extract + FMA + simd_sum.
  LUT    : precompute table[m,d,level]=q[m,d]*cb[level] (per query block, once),
           load table into threadgroup memory, replace per-key multiply with a gather.
  MMA    : dequant the K tile (norm folded) -> fp16 in device scratch, then the
           Spike-A simdgroup_matrix QK^T.  (cost = dequant pass + matmul)

Verdict wanted: does LUT beat MMA at 3-bit by enough to justify a 2nd code path?
Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_b_lut.py
"""
import time
import numpy as np
import mlx.core as mx

HDR = "#include <metal_simdgroup_matrix>\n"


def bench(fn, iters=30, warmup=5):
    for _ in range(warmup):
        mx.eval(fn())
    mx.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        mx.eval(fn())
    mx.synchronize()
    return (time.perf_counter() - t0) / iters


def gflops(M, T, D, sec):
    return 2.0 * M * T * D / sec / 1e9


def make_packed_k(T, D, bits, seed=0):
    """Build packed low-bit K in the d*bits bit-layout, plus norms + codebook."""
    rng = np.random.default_rng(seed)
    levels = 1 << bits
    cb = np.linspace(-1.0, 1.0, levels).astype(np.float32)          # [levels]
    unit = rng.standard_normal((T, D)).astype(np.float32)
    unit /= np.linalg.norm(unit, axis=-1, keepdims=True)
    # nearest codebook index per element
    idx = np.abs(unit[..., None] - cb[None, None, :]).argmin(-1).astype(np.uint32)  # [T,D]
    norms = np.linalg.norm(rng.standard_normal((T, D)), axis=-1).astype(np.float16)  # arbitrary per-token scale
    # pack: d-th index at bit d*bits
    pw = (D * bits + 31) // 32
    packed = np.zeros((T, pw), dtype=np.uint64)
    for d in range(D):
        bit = d * bits
        w = bit // 32
        off = bit % 32
        packed[:, w] |= (idx[:, d].astype(np.uint64) << off)
        if off + bits > 32:
            packed[:, w + 1] |= (idx[:, d].astype(np.uint64) >> (32 - off))
    packed = packed.astype(np.uint32)
    return (mx.array(idx), mx.array(packed), mx.array(norms),
            mx.array(cb), mx.array(unit))


def reference(q, idx, norms, cb):
    deq = cb[idx] * norms[:, None].astype(mx.float32)   # [T,D]
    return q.astype(mx.float32) @ deq.T                 # [M,T]


# ---- scalar (codebase style) ----
def scalar_score_kernel(bits):
    src = f"""
        constexpr int bits = {bits};
        constexpr uint mask = {(1<<bits)-1}u;
        uint tile = threadgroup_position_in_grid.x;
        uint m = tile / T;
        uint t = tile % T;
        uint lane = thread_index_in_simdgroup;
        const device uint* kp = Kpacked + t * PW;
        float acc = 0.0f;
        for (uint d = lane; d < D; d += 32) {{
            uint bit = d * bits;
            uint w = bit >> 5; uint off = bit & 31;
            uint v = kp[w] >> off;
            if (off + bits > 32) v |= kp[w+1] << (32 - off);
            v &= mask;
            acc += Q[m * D + d] * codebook[v];
        }}
        acc = simd_sum(acc);
        if (lane == 0) out[m * T + t] = acc * static_cast<float>(norms[t]);
    """
    return mx.fast.metal_kernel(name=f"scalar_score_{bits}",
                                input_names=["Q", "Kpacked", "norms", "codebook"],
                                output_names=["out"], source=src)


# ---- LUT (table in threadgroup memory) ----
def lut_score_kernel(bits, D):
    levels = 1 << bits
    # one threadgroup per m; 32 simdgroups stride over T; table[D*levels] in tgmem.
    src = f"""
        constexpr int bits = {bits};
        constexpr uint mask = {levels-1}u;
        constexpr int LEVELS = {levels};
        constexpr int TBL = {D * levels};
        uint m = threadgroup_position_in_grid.x;
        uint simd_gid = simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;
        uint lid = thread_position_in_threadgroup.x;

        threadgroup float tbl[TBL];           // table[d*LEVELS + level] = q[m,d]*cb[level]
        for (uint i = lid; i < TBL; i += 1024) {{
            uint d = i / LEVELS; uint lv = i % LEVELS;
            tbl[i] = Q[m * D + d] * codebook[lv];
        }}
        threadgroup_barrier(mem_flags::mem_threadgroup);

        for (uint t = simd_gid; t < T; t += 32) {{
            const device uint* kp = Kpacked + t * PW;
            float acc = 0.0f;
            for (uint d = lane; d < D; d += 32) {{
                uint bit = d * bits;
                uint w = bit >> 5; uint off = bit & 31;
                uint v = kp[w] >> off;
                if (off + bits > 32) v |= kp[w+1] << (32 - off);
                v &= mask;
                acc += tbl[d * LEVELS + v];          // gather, no multiply
            }}
            acc = simd_sum(acc);
            if (lane == 0) out[m * T + t] = acc * static_cast<float>(norms[t]);
        }}
    """
    return mx.fast.metal_kernel(name=f"lut_score_{bits}_{D}",
                                input_names=["Q", "Kpacked", "norms", "codebook"],
                                output_names=["out"], source=src)


# ---- dequant 3-bit -> fp16 (norm folded), feeds MMA ----
def dequant_kernel(bits):
    src = f"""
        constexpr int bits = {bits};
        constexpr uint mask = {(1<<bits)-1}u;
        uint gid = thread_position_in_grid.x;
        uint t = gid / D; uint d = gid % D;
        if (t >= T) return;
        const device uint* kp = Kpacked + t * PW;
        uint bit = d * bits;
        uint w = bit >> 5; uint off = bit & 31;
        uint v = kp[w] >> off;
        if (off + bits > 32) v |= kp[w+1] << (32 - off);
        v &= mask;
        out[t * D + d] = static_cast<half>(codebook[v] * static_cast<float>(norms[t]));
    """
    return mx.fast.metal_kernel(name=f"dequant_{bits}",
                                input_names=["Kpacked", "norms", "codebook"],
                                output_names=["out"], source=src)


def mma_qkt_kernel():
    src = """
        uint tile = threadgroup_position_in_grid.x;
        uint tiles_n = (T + 7) / 8;
        uint m0 = (tile / tiles_n) * 8;
        uint n0 = (tile % tiles_n) * 8;
        simdgroup_matrix<float,8,8> acc = simdgroup_matrix<float,8,8>(0);
        for (uint k0 = 0; k0 < D; k0 += 8) {
            simdgroup_matrix<half,8,8> a, b;
            simdgroup_load(a, Q + m0 * D + k0, D, ulong2(0,0), false);
            simdgroup_load(b, Kf + n0 * D + k0, D, ulong2(0,0), true);
            simdgroup_multiply_accumulate(acc, a, b, acc);
        }
        simdgroup_store(acc, out + m0 * T + n0, T, ulong2(0,0), false);
    """
    return mx.fast.metal_kernel(name="mma_qkt_b", input_names=["Q", "Kf"],
                                output_names=["out"], source=src, header=HDR)


def run(bits, M, T, D):
    print(f"\n--- bits={bits}  M={M} T={T} D={D}  (useful FLOPs={2*M*T*D/1e9:.2f} G) ---")
    idx, packed, norms, cb, unit = make_packed_k(T, D, bits)
    PW = packed.shape[-1]
    q = mx.random.normal((M, D)).astype(mx.float16)
    ref = reference(q, idx, norms, cb); mx.eval(ref)

    # scalar
    sk = scalar_score_kernel(bits)
    def scall():
        return sk(inputs=[q, packed, norms, cb], template=[("M", M), ("T", T), ("D", D), ("PW", PW)],
                  grid=(M*T*32, 1, 1), threadgroup=(32, 1, 1),
                  output_shapes=[(M, T)], output_dtypes=[mx.float32])[0]
    o = scall(); mx.eval(o); d_s = mx.max(mx.abs(o - ref)).item(); t_s = bench(scall)
    print(f"  {'scalar simd_sum':16s} maxdiff={d_s:.4f}  {t_s*1e3:7.3f} ms  {gflops(M,T,D,t_s):8.1f} GFLOP/s")

    # LUT
    lk = lut_score_kernel(bits, D)
    def lcall():
        return lk(inputs=[q, packed, norms, cb], template=[("M", M), ("T", T), ("D", D), ("PW", PW)],
                  grid=(M*1024, 1, 1), threadgroup=(1024, 1, 1),
                  output_shapes=[(M, T)], output_dtypes=[mx.float32])[0]
    o = lcall(); mx.eval(o); d_l = mx.max(mx.abs(o - ref)).item(); t_l = bench(lcall)
    print(f"  {'LUT gather':16s} maxdiff={d_l:.4f}  {t_l*1e3:7.3f} ms  {gflops(M,T,D,t_l):8.1f} GFLOP/s")

    # MMA = dequant pass + matmul
    dk = dequant_kernel(bits); mk = mma_qkt_kernel()
    def mcall():
        Kf = dk(inputs=[packed, norms, cb], template=[("T", T), ("D", D), ("PW", PW)],
                grid=(T*D, 1, 1), threadgroup=(256, 1, 1),
                output_shapes=[(T, D)], output_dtypes=[mx.float16])[0]
        ntiles = ((M + 7)//8) * ((T + 7)//8)
        return mk(inputs=[q, Kf], template=[("M", M), ("T", T), ("D", D)],
                  grid=(ntiles*32, 1, 1), threadgroup=(32, 1, 1),
                  output_shapes=[(M, T)], output_dtypes=[mx.float32])[0]
    o = mcall(); mx.eval(o); d_m = mx.max(mx.abs(o - ref)).item(); t_m = bench(mcall)
    print(f"  {'dequant+MMA':16s} maxdiff={d_m:.4f}  {t_m*1e3:7.3f} ms  {gflops(M,T,D,t_m):8.1f} GFLOP/s")

    best = min(t_s, t_l, t_m)
    print(f"  >> LUT {t_m/t_l:.2f}x vs MMA | LUT {t_s/t_l:.2f}x vs scalar | MMA {t_s/t_m:.2f}x vs scalar"
          f" | winner={'LUT' if best==t_l else 'MMA' if best==t_m else 'scalar'}")


if __name__ == "__main__":
    print("=" * 70)
    print(f"SPIKE B — LUT vs MMA scoring  ({mx.device_info()['device_name']})")
    print("=" * 70)
    for bits in (3, 4):
        for M in (6, 32, 256):          # decode-R, small block, large prefill block
            run(bits, M=M, T=16384, D=256)
    print("\nDONE")
