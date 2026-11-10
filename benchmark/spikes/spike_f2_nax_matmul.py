#!/usr/bin/env python3
"""M72 spike F2 (S20-P13 / C311 P2'): Neural Accelerator matmul inside mx.fast.metal_kernel via MLX's own NAX fragment.

Spike F (benchmark/results/m72/probe/spike-f-tensorops.log) drove `mpp::tensor_ops::matmul2d` on device tensors and hit
"Unsupported type" (half x half -> float destination). MLX 0.32.4's working NAX kernels (steel/gemm/nax.h) run matmul2d per
simdgroup on register cooperative tensors, descriptor (16, 32, 16). This spike includes that header in the JIT and:
  stage 1  correctness: one simdgroup, C(16x32) = A(16x256) . B(256x32), half in, fp32 accumulate, vs numpy
  stage 2  throughput on the verify-shaped product S = Q . K^T (32 query rows x N tokens x D = 256; one KV head's worth per
           threadgroup row tile), NAX matmul2d vs the same tiling on simdgroup_multiply_accumulate (8x8), K read from device
Run (quiet box): PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_f2_nax_matmul.py [--n 260096]
"""

import argparse
import statistics
import time

import mlx.core as mx
import numpy as np


def _nax_header():
    """MLX's steel NAX fragment (defines.h + integral_constant.h + gemm/nax.h) inlined: the metal_kernel JIT sees system
    frameworks but not MLX's kernel include tree. Read from the installed MLX package, mlx-relative includes stripped.
    """
    import re
    from pathlib import Path

    import mlx

    root = Path(list(mlx.__path__)[0]) / "include" / "mlx" / "backend" / "metal" / "kernels" / "steel"
    parts = []
    for rel in ("defines.h", "utils/type_traits.h", "utils/integral_constant.h", "gemm/nax.h"):
        txt = (root / rel).read_text()
        txt = re.sub(r'^#include "mlx/[^"]+"\s*$', "", txt, flags=re.M)
        txt = txt.replace("#pragma once", "")
        parts.append(f"// ---- inlined from MLX steel/{rel}\n{txt}")
    return "\n".join(parts) + "\nusing namespace mlx::steel;\n"


HEADER = _nax_header()

# ---- stage 1: one 16x32 tile over K = 256 -----------------------------------------------------------------------------
SRC_TILE = """
    using F = BaseNAXFrag;
    typedef F::dtype_frag_t<half> HF;
    typedef F::dtype_frag_t<float> FF;
    FF c0 = FF(0), c1 = FF(0);
    for (int kk = 0; kk < KD; kk += 16) {
        HF a, b0, b1;
        F::load(a, A + kk, Int<KD>{}, Int<1>{});                 // A row-major (16 x KD): rows stride KD
        F::load(b0, B + kk * 32, Int<32>{}, Int<1>{});           // B row-major (KD x 32): rows stride 32
        F::load(b1, B + kk * 32 + 16, Int<32>{}, Int<1>{});
        F::mma(c0, c1, a, metal::bool_constant<false>{}, b0, b1, metal::bool_constant<false>{});
    }
    uint lane = thread_index_in_simdgroup;
    for (short i = 0; i < F::kElemsPerFrag; i++) {
        short2 rc = F::get_coord(i);                              // (col, row) of element i of this lane
        C[rc.y * 32 + rc.x] = c0[i];
        C[rc.y * 32 + 16 + rc.x] = c1[i];
    }
"""

# ---- stage 2: S = Q . K^T, 32 rows x N tokens x 256 ------------------------------------------------------------------
# Each threadgroup = 4 simdgroups; each simdgroup computes a 32 x 32 tile of S (2 row frags x 1 n-pair) over D = 256,
# Q from threadgroup memory (loaded once), K straight from device (row-major tokens x D: B = K^T, so element (d, n) is
# K[n * D + d] -> str_x = 1, str_y = D).
SRC_NAX = """
    using F = BaseNAXFrag;
    typedef F::dtype_frag_t<half> HF;
    typedef F::dtype_frag_t<float> FF;
    threadgroup half Qs[32 * 256];
    uint tid = thread_position_in_threadgroup.x;
    for (uint i = tid; i < 32 * 256; i += 128) Qs[i] = Q[i];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    uint sg = simdgroup_index_in_threadgroup;
    uint n0 = (threadgroup_position_in_grid.x * 4 + sg) * 32;
    if (n0 >= N) return;
    FF c00 = FF(0), c01 = FF(0), c10 = FF(0), c11 = FF(0);
    const device half* Kp = K + (ulong)n0 * 256;
    for (int kk = 0; kk < 256; kk += 16) {
        HF a0, a1, b0, b1;
        F::load(a0, Qs + kk, Int<256>{}, Int<1>{});
        F::load(a1, Qs + 16 * 256 + kk, Int<256>{}, Int<1>{});
        F::load(b0, Kp + kk, Int<1>{}, Int<256>{});
        F::load(b1, Kp + 16 * 256 + kk, Int<1>{}, Int<256>{});
        F::mma(c00, c01, a0, metal::bool_constant<false>{}, b0, b1, metal::bool_constant<false>{});
        F::mma(c10, c11, a1, metal::bool_constant<false>{}, b0, b1, metal::bool_constant<false>{});
    }
    for (short i = 0; i < F::kElemsPerFrag; i++) {
        short2 rc = F::get_coord(i);
        S[(ulong)rc.y * N + n0 + rc.x] = c00[i];
        S[(ulong)rc.y * N + n0 + 16 + rc.x] = c01[i];
        S[(ulong)(16 + rc.y) * N + n0 + rc.x] = c10[i];
        S[(ulong)(16 + rc.y) * N + n0 + 16 + rc.x] = c11[i];
    }
"""

SRC_SG = """
    threadgroup half Qs[32 * 256];
    uint tid = thread_position_in_threadgroup.x;
    for (uint i = tid; i < 32 * 256; i += 128) Qs[i] = Q[i];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    uint sg = simdgroup_index_in_threadgroup;
    uint n0 = (threadgroup_position_in_grid.x * 4 + sg) * 32;
    if (n0 >= N) return;
    simdgroup_matrix<float, 8, 8> acc[4][4];
    for (int i = 0; i < 4; i++) for (int j = 0; j < 4; j++) acc[i][j] = simdgroup_matrix<float, 8, 8>(0);
    const device half* Kp = K + (ulong)n0 * 256;
    for (int kk = 0; kk < 256; kk += 8) {
        simdgroup_matrix<half, 8, 8> a[4], b[4];
        for (int i = 0; i < 4; i++) simdgroup_load(a[i], Qs + i * 8 * 256 + kk, 256);
        for (int j = 0; j < 4; j++) simdgroup_load(b[j], Kp + j * 8 * 256 + kk, 256, ulong2(0, 0), true);
        for (int i = 0; i < 4; i++) for (int j = 0; j < 4; j++) simdgroup_multiply_accumulate(acc[i][j], a[i], b[j], acc[i][j]);
    }
    for (int i = 0; i < 4; i++) for (int j = 0; j < 4; j++)
        simdgroup_store(acc[i][j], S + (ulong)(i * 8) * N + n0 + j * 8, N);
"""


# ---- stage 3: pure in-register MMA throughput (compute-bound), full GPU --------------------------------------------------
SRC_C_NAX = """
    using F = BaseNAXFrag;
    typedef F::dtype_frag_t<half> HF;
    typedef F::dtype_frag_t<float> FF;
    uint lane = thread_index_in_simdgroup;
    HF a, b0, b1;
    for (short i = 0; i < F::kElemsPerFrag; i++) { a[i] = half(0.001h * (lane + i)); b0[i] = half(0.002h * i); b1[i] = half(0.001h); }
    FF c0 = FF(0), c1 = FF(0), c2 = FF(0), c3 = FF(0);
    for (int it = 0; it < ITERS; it++) {
        F::mma(c0, c1, a, metal::bool_constant<false>{}, b0, b1, metal::bool_constant<false>{});
        F::mma(c2, c3, a, metal::bool_constant<false>{}, b1, b0, metal::bool_constant<false>{});
    }
    float s = 0; for (short i = 0; i < F::kElemsPerFrag; i++) s += c0[i] + c1[i] + c2[i] + c3[i];
    out[thread_position_in_grid.x] = s;
"""
SRC_C_SG = """
    uint lane = thread_index_in_simdgroup;
    simdgroup_matrix<half, 8, 8> a = simdgroup_matrix<half, 8, 8>(half(0.001h * lane));
    simdgroup_matrix<half, 8, 8> b = simdgroup_matrix<half, 8, 8>(half(0.002h));
    simdgroup_matrix<float, 8, 8> c[8];
    for (int j = 0; j < 8; j++) c[j] = simdgroup_matrix<float, 8, 8>(0);
    for (int it = 0; it < ITERS; it++) {
        for (int r = 0; r < 4; r++) {                 // 4 x 8 calls of 8x8x8 = 16384 MACs = the NAX body (2 x 16x32x16)
            for (int j = 0; j < 8; j++) simdgroup_multiply_accumulate(c[j], a, b, c[j]);
        }
    }
    float s = 0; for (int j = 0; j < 8; j++) s += c[j].thread_elements()[0] + c[j].thread_elements()[1];
    out[thread_position_in_grid.x] = s;
"""


def stage3():
    tg, n_tg, iters = 128, 4096, 256
    res = {}
    for name, src in (("nax", SRC_C_NAX), ("simdgroup", SRC_C_SG)):
        kern = mx.fast.metal_kernel(
            name=f"f2c_{name}", input_names=["dummy"], output_names=["out"], header=HEADER, source=src
        )
        call = lambda kern=kern: kern(
            inputs=[mx.zeros((1,))],
            template=[("ITERS", iters)],
            grid=(tg * n_tg, 1, 1),
            threadgroup=(tg, 1, 1),
            output_shapes=[(tg * n_tg,)],
            output_dtypes=[mx.float32],
        )[0]
        ms = timeit(call, n=20)
        macs = (tg * n_tg // 32) * iters * 2 * 16 * 32 * 16  # per simdgroup per iteration: 2 calls of 16x32x16
        res[name] = ms
        print(
            f"[stage 3 {name}] in-register MMA: {ms:.3f} ms, {2 * macs / ms / 1e9:.1f} TFLOPS (half in, fp32 acc)",
            flush=True,
        )
    print(f"[stage 3] simdgroup / nax time ratio (compute-bound): {res['simdgroup'] / res['nax']:.2f}x")


def timeit(fn, n=50):
    for _ in range(3):
        mx.eval(fn())
    mx.synchronize()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        mx.eval(fn())
        mx.synchronize()
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts) * 1e3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=260096)
    a = ap.parse_args()
    print(f"spike F2 — MLX {mx.__version__}, {mx.device_info().get('architecture')}", flush=True)

    # stage 1
    rng = np.random.default_rng(0)
    A = rng.standard_normal((16, 256)).astype(np.float16)
    B = rng.standard_normal((256, 32)).astype(np.float16)
    k1 = mx.fast.metal_kernel(
        name="f2_tile", input_names=["A", "B"], output_names=["C"], header=HEADER, source=SRC_TILE
    )
    try:
        C = k1(
            inputs=[mx.array(A), mx.array(B)],
            template=[("KD", 256)],
            grid=(32, 1, 1),
            threadgroup=(32, 1, 1),
            output_shapes=[(16, 32)],
            output_dtypes=[mx.float32],
        )[0]
        mx.eval(C)
    except Exception as exc:
        print(f"[stage 1] FAIL: {str(exc)[:3000]}")
        return 1
    ref = A.astype(np.float32) @ B.astype(np.float32)
    err = float(np.max(np.abs(np.array(C) - ref)) / np.max(np.abs(ref)))
    print(f"[stage 1] NAX matmul2d tile 16x32x256: rel err {err:.2e} -> {'OK' if err < 1e-3 else 'WRONG'}", flush=True)
    if err >= 1e-3:
        return 2

    # stage 2
    N = a.n - a.n % 128
    Q = mx.array(rng.standard_normal((32, 256)).astype(np.float16))
    K = mx.array(rng.standard_normal((N, 256)).astype(np.float16))
    mx.eval(Q, K)
    grid = ((N // 128) * 128, 1, 1)  # one threadgroup (128 threads = 4 simdgroups) per 128 tokens
    out = {}
    for name, src in (("nax", SRC_NAX), ("simdgroup", SRC_SG)):
        kern = mx.fast.metal_kernel(
            name=f"f2_{name}", input_names=["Q", "K"], output_names=["S"], header=HEADER, source=src
        )
        call = lambda kern=kern: kern(
            inputs=[Q, K],
            template=[("N", N)],
            grid=grid,
            threadgroup=(128, 1, 1),
            output_shapes=[(32, N)],
            output_dtypes=[mx.float32],
        )[0]
        try:
            S = call()
            mx.eval(S)
        except Exception as exc:
            print(f"[stage 2 {name}] FAIL: {str(exc)[:2000]}")
            return 3
        refS = np.array(Q.astype(mx.float32)) @ np.array(K[:4096].astype(mx.float32)).T
        e = float(np.max(np.abs(np.array(S[:, :4096]) - refS)) / np.max(np.abs(refS)))
        ms = timeit(call)
        flops = 2 * 32 * N * 256
        out[name] = ms
        print(
            f"[stage 2 {name}] S = Q.K^T 32 x {N} x 256: {ms:.3f} ms, {flops / ms / 1e9:.1f} TFLOPS, "
            f"{N * 256 * 2 / ms / 1e6:.0f} GB/s K read, rel err {e:.2e}",
            flush=True,
        )
    print(f"[stage 2] simdgroup / nax time ratio: {out['simdgroup'] / out['nax']:.2f}x")
    stage3()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
