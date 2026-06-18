"""
Spike A — simdgroup_matrix (MMA) viability + throughput inside mx.fast.metal_kernel.

Questions:
  A0. Does simdgroup_matrix<float,8,8> compile & run at all inside mx.fast.metal_kernel?
  A1. Does the half-input / fp32-accumulate variant compile (the spec's target)?
  A2. Tiled QK^T MMA: correct vs mx.matmul? GFLOP/s vs a scalar simd_sum baseline
      (the codebase's reduction style) and vs mx.matmul (the optimized ceiling).
  A3. Same for the AV matmul (scores[M,T] @ V[T,D]).

All matmuls at Qwen prefill dims: head_dim D=256, GQA R=6.
Throwaway probe — not production code. Run:
  PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_a_mma.py
"""
import time
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


def gflops(M, N, K, sec):
    return 2.0 * M * N * K / sec / 1e9


# --------------------------------------------------------------------------
# A0/A1: minimal MMA compile + correctness, float and half-in/float-acc
# --------------------------------------------------------------------------
def minimal_mma(acc_dtype, in_dtype):
    """One simdgroup, single 8x8 = 8x8 @ 8x8 tile. Returns (ok, maxdiff or err)."""
    in_t = "half" if in_dtype == mx.float16 else "float"
    acc_t = "half" if acc_dtype == mx.float16 else "float"
    src = f"""
        uint g = threadgroup_position_in_grid.x;
        (void)g;
        simdgroup_matrix<{acc_t},8,8> c = simdgroup_matrix<{acc_t},8,8>(0);
        simdgroup_matrix<{in_t},8,8> a, b;
        simdgroup_load(a, A, 8, ulong2(0,0), false);
        simdgroup_load(b, B, 8, ulong2(0,0), false);
        simdgroup_multiply_accumulate(c, a, b, c);
        simdgroup_store(c, out, 8, ulong2(0,0), false);
    """
    try:
        kern = mx.fast.metal_kernel(
            name=f"min_mma_{acc_t}_{in_t}",
            input_names=["A", "B"],
            output_names=["out"],
            source=src,
            header=HDR,
        )
        A = mx.random.normal((8, 8)).astype(in_dtype)
        B = mx.random.normal((8, 8)).astype(in_dtype)
        out = kern(
            inputs=[A, B],
            grid=(32, 1, 1),
            threadgroup=(32, 1, 1),
            output_shapes=[(8, 8)],
            output_dtypes=[acc_dtype],
        )[0]
        ref = (A.astype(mx.float32) @ B.astype(mx.float32))
        mx.eval(out)
        diff = mx.max(mx.abs(out.astype(mx.float32) - ref)).item()
        return True, diff
    except Exception as e:  # noqa
        return False, str(e)[:300]


# --------------------------------------------------------------------------
# A2: tiled QK^T  —  score[M,N] = Q[M,K] @ Kmat[N,K]^T
# --------------------------------------------------------------------------
def mma_qkt_kernel(in_dtype, acc_dtype):
    in_t = "half" if in_dtype == mx.float16 else "float"
    acc_t = "half" if acc_dtype == mx.float16 else "float"
    src = f"""
        uint tile = threadgroup_position_in_grid.x;
        uint tiles_n = (N + 7) / 8;
        uint m0 = (tile / tiles_n) * 8;
        uint n0 = (tile % tiles_n) * 8;
        simdgroup_matrix<{acc_t},8,8> acc = simdgroup_matrix<{acc_t},8,8>(0);
        for (uint k0 = 0; k0 < K; k0 += 8) {{
            simdgroup_matrix<{in_t},8,8> a, b;
            simdgroup_load(a, Q + m0 * K + k0, K, ulong2(0,0), false);
            simdgroup_load(b, Kmat + n0 * K + k0, K, ulong2(0,0), true);
            simdgroup_multiply_accumulate(acc, a, b, acc);
        }}
        simdgroup_store(acc, out + m0 * N + n0, N, ulong2(0,0), false);
    """
    return mx.fast.metal_kernel(
        name=f"mma_qkt_{in_t}_{acc_t}",
        input_names=["Q", "Kmat"],
        output_names=["out"],
        source=src,
        header=HDR,
    )


def scalar_qkt_kernel():
    """Codebase-style baseline: one simdgroup per output score, 32-lane simd_sum over K."""
    src = """
        uint tile = threadgroup_position_in_grid.x;
        uint m = tile / N;
        uint n = tile % N;
        uint lane = thread_index_in_simdgroup;
        float acc = 0.0f;
        for (uint k = lane; k < K; k += 32) {
            acc += static_cast<float>(Q[m * K + k]) * static_cast<float>(Kmat[n * K + k]);
        }
        acc = simd_sum(acc);
        if (lane == 0) out[m * N + n] = acc;
    """
    return mx.fast.metal_kernel(
        name="scalar_qkt",
        input_names=["Q", "Kmat"],
        output_names=["out"],
        source=src,
    )


def run_qkt(M, N, K):
    print(f"\n--- QK^T  M={M} N={N} K={K}  (FLOPs={2*M*N*K/1e9:.2f} G) ---")
    Qh = mx.random.normal((M, K)).astype(mx.float16)
    Kh = mx.random.normal((N, K)).astype(mx.float16)
    ref = Qh.astype(mx.float32) @ Kh.astype(mx.float32).T
    mx.eval(ref)

    results = {}
    # MMA half-in / float-acc (target)
    for in_t, acc_t, label in [
        (mx.float16, mx.float32, "MMA half->fp32"),
        (mx.float32, mx.float32, "MMA fp32->fp32"),
    ]:
        try:
            kern = mma_qkt_kernel(in_t, acc_t)
            Qi = Qh.astype(in_t)
            Ki = Kh.astype(in_t)
            ntiles = ((M + 7) // 8) * ((N + 7) // 8)

            def call():
                return kern(
                    inputs=[Qi, Ki],
                    template=[("M", M), ("N", N), ("K", K)],
                    grid=(ntiles * 32, 1, 1),
                    threadgroup=(32, 1, 1),
                    output_shapes=[(M, N)],
                    output_dtypes=[acc_t],
                )[0]

            out = call()
            mx.eval(out)
            diff = mx.max(mx.abs(out.astype(mx.float32) - ref)).item()
            sec = bench(call)
            print(f"  {label:18s} ok  maxdiff={diff:.4f}  {sec*1e3:7.3f} ms  {gflops(M,N,K,sec):8.1f} GFLOP/s")
            results[label] = (sec, diff)
        except Exception as e:  # noqa
            print(f"  {label:18s} FAILED: {str(e)[:200]}")

    # scalar simd_sum baseline
    try:
        sk = scalar_qkt_kernel()

        def scall():
            return sk(
                inputs=[Qh, Kh],
                template=[("M", M), ("N", N), ("K", K)],
                grid=(M * N * 32, 1, 1),
                threadgroup=(32, 1, 1),
                output_shapes=[(M, N)],
                output_dtypes=[mx.float32],
            )[0]

        out = scall()
        mx.eval(out)
        diff = mx.max(mx.abs(out.astype(mx.float32) - ref)).item()
        sec = bench(scall)
        print(f"  {'scalar simd_sum':18s} ok  maxdiff={diff:.4f}  {sec*1e3:7.3f} ms  {gflops(M,N,K,sec):8.1f} GFLOP/s")
        results["scalar"] = (sec, diff)
    except Exception as e:  # noqa
        print(f"  {'scalar simd_sum':18s} FAILED: {str(e)[:200]}")

    # mx.matmul ceiling (fp16)
    def mmcall():
        return Qh @ Kh.T
    sec = bench(mmcall)
    print(f"  {'mx.matmul fp16':18s} (ceiling)        {sec*1e3:7.3f} ms  {gflops(M,N,K,sec):8.1f} GFLOP/s")
    results["mx.matmul"] = (sec, 0.0)

    if "MMA half->fp32" in results and "scalar" in results:
        sp = results["scalar"][0] / results["MMA half->fp32"][0]
        print(f"  >> MMA half->fp32 is {sp:.2f}x vs scalar simd_sum")
    return results


# --------------------------------------------------------------------------
# A3: AV  —  out[M,D] = scores[M,T] @ V[T,D]   (no transpose)
# --------------------------------------------------------------------------
def mma_av_kernel(in_dtype, acc_dtype):
    in_t = "half" if in_dtype == mx.float16 else "float"
    acc_t = "half" if acc_dtype == mx.float16 else "float"
    src = f"""
        uint tile = threadgroup_position_in_grid.x;
        uint tiles_d = (D + 7) / 8;
        uint m0 = (tile / tiles_d) * 8;
        uint d0 = (tile % tiles_d) * 8;
        simdgroup_matrix<{acc_t},8,8> acc = simdgroup_matrix<{acc_t},8,8>(0);
        for (uint t0 = 0; t0 < T; t0 += 8) {{
            simdgroup_matrix<{in_t},8,8> a, b;
            simdgroup_load(a, S + m0 * T + t0, T, ulong2(0,0), false);
            simdgroup_load(b, V + t0 * D + d0, D, ulong2(0,0), false);
            simdgroup_multiply_accumulate(acc, a, b, acc);
        }}
        simdgroup_store(acc, out + m0 * D + d0, D, ulong2(0,0), false);
    """
    return mx.fast.metal_kernel(
        name=f"mma_av_{in_t}_{acc_t}",
        input_names=["S", "V"],
        output_names=["out"],
        source=src,
        header=HDR,
    )


def run_av(M, T, D):
    print(f"\n--- AV  M={M} T={T} D={D}  (FLOPs={2*M*T*D/1e9:.2f} G) ---")
    Sh = mx.random.normal((M, T)).astype(mx.float16)
    Vh = mx.random.normal((T, D)).astype(mx.float16)
    ref = Sh.astype(mx.float32) @ Vh.astype(mx.float32)
    mx.eval(ref)
    try:
        kern = mma_av_kernel(mx.float16, mx.float32)
        ntiles = ((M + 7) // 8) * ((D + 7) // 8)

        def call():
            return kern(
                inputs=[Sh, Vh],
                template=[("M", M), ("T", T), ("D", D)],
                grid=(ntiles * 32, 1, 1),
                threadgroup=(32, 1, 1),
                output_shapes=[(M, D)],
                output_dtypes=[mx.float32],
            )[0]

        out = call()
        mx.eval(out)
        diff = mx.max(mx.abs(out.astype(mx.float32) - ref)).item()
        sec = bench(call)
        print(f"  {'MMA half->fp32':18s} ok  maxdiff={diff:.4f}  {sec*1e3:7.3f} ms  {gflops(M,T,D,sec):8.1f} GFLOP/s")
    except Exception as e:  # noqa
        print(f"  MMA AV FAILED: {str(e)[:200]}")

    def mmcall():
        return Sh @ Vh
    sec = bench(mmcall)
    print(f"  {'mx.matmul fp16':18s} (ceiling)        {sec*1e3:7.3f} ms  {gflops(M,T,D,sec):8.1f} GFLOP/s")


if __name__ == "__main__":
    print("=" * 70)
    print("SPIKE A — simdgroup_matrix MMA viability in mx.fast.metal_kernel")
    print(f"device: {mx.device_info()['device_name']}")
    print("=" * 70)

    print("\n[A0/A1] minimal 8x8 MMA compile + correctness")
    for acc, inp, name in [
        (mx.float32, mx.float32, "fp32-in  fp32-acc"),
        (mx.float16, mx.float16, "fp16-in  fp16-acc"),
        (mx.float32, mx.float16, "fp16-in  fp32-acc  <- spec target"),
    ]:
        ok, info = minimal_mma(acc, inp)
        status = f"OK   maxdiff={info:.4f}" if ok and isinstance(info, float) else f"FAIL {info}"
        print(f"  {name:32s}: {status}")

    # A2: QK^T at prefill dims
    run_qkt(M=384, N=2048, K=256)    # R*L=6*64, K-tile 2048, head_dim 256
    run_qkt(M=1536, N=2048, K=256)   # R*L=6*256 (full prefill query block)
    run_qkt(M=256, N=8192, K=256)    # larger T-tile

    # A3: AV
    run_av(M=384, T=2048, D=256)
    run_av(M=1536, T=2048, D=256)
    print("\nDONE")
