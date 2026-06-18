"""
Spike D — roofline: peak achievable DRAM bandwidth, and where a decode-shaped
read sits relative to it. Also: does a 3-bit fused read beat fp16 dense SDPA?

Establishes the ceiling that Spike C/E numbers are judged against.
M2 Max theoretical peak DRAM BW ~= 400 GB/s.
Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_d_roofline.py
"""
import time
import mlx.core as mx


def bench(fn, iters=30, warmup=8):
    for _ in range(warmup):
        mx.eval(fn())
    mx.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        mx.eval(fn())
    mx.synchronize()
    return (time.perf_counter() - t0) / iters


print("=" * 72)
print(f"SPIKE D — roofline  ({mx.device_info()['device_name']})")
print("max_recommended_working_set:", mx.device_info()["max_recommended_working_set_size"] / 1e9, "GB")
print("=" * 72)

# ---- 1. peak read bandwidth via mx.sum over a large buffer (well-optimized) ----
print("\n[1] peak DRAM read bandwidth (mx.sum over large fp16 buffer)")
for gb in (0.5, 1.0, 2.0):
    n = int(gb * 1e9 / 2)
    x = mx.ones((n,), dtype=mx.float16); mx.eval(x)
    sec = bench(lambda: mx.sum(x))
    print(f"  {gb:.1f} GB  ->  {sec*1e3:7.3f} ms   {gb/sec:7.1f} GB/s")

# ---- 2. custom full-occupancy read kernel (grid-strided sum of uint32) ----
print("\n[2] custom full-occupancy read kernel (uint32 grid-stride sum)")
read_src = """
    uint gid = thread_position_in_grid.x;
    uint nthreads = threads_per_grid.x;
    uint acc = 0;
    for (uint i = gid; i < N; i += nthreads) acc += data[i];
    // reduce within simdgroup then one atomic-ish write per group slot
    acc = simd_sum(acc);
    if (thread_index_in_simdgroup == 0) out[gid / 32 % 4096] = acc;
"""
rk = mx.fast.metal_kernel(name="readbw", input_names=["data"], output_names=["out"], source=read_src)
for gb in (1.0, 2.0):
    n = int(gb * 1e9 / 4)
    x = mx.zeros((n,), dtype=mx.uint32); mx.eval(x)
    NT = 1 << 20  # ~1M threads -> high occupancy
    def call():
        return rk(inputs=[x], template=[("N", n)], grid=(NT, 1, 1), threadgroup=(256, 1, 1),
                  output_shapes=[(4096,)], output_dtypes=[mx.uint32])[0]
    sec = bench(call)
    print(f"  {gb:.1f} GB  ->  {sec*1e3:7.3f} ms   {gb/sec:7.1f} GB/s")

# ---- 3. fp16 dense SDPA (mx.fast) decode at long T vs the 3-bit budget ----
print("\n[3] fp16 dense mx.fast.scaled_dot_product_attention — decode (L=1), GQA")
n_q, n_kv, Dh = 24, 4, 256
scale = 1.0 / (Dh ** 0.5)
for T in (16384, 65536, 131072, 200000):
    q = mx.random.normal((1, n_q, 1, Dh)).astype(mx.float16)
    k = mx.random.normal((1, n_kv, T, Dh)).astype(mx.float16)
    v = mx.random.normal((1, n_kv, T, Dh)).astype(mx.float16)
    mx.eval(q, k, v)
    def call():
        return mx.fast.scaled_dot_product_attention(q, k, v, scale=scale)
    try:
        sec = bench(call, iters=15, warmup=5)
        kv_gb = 2 * n_kv * T * Dh * 2 / 1e9          # fp16 K+V read once
        kv3_gb = 2 * n_kv * T * Dh * 3 / 8 / 1e9     # 3-bit K+V equivalent
        print(f"  T={T:>7}  {sec*1e3:8.3f} ms  fp16-KV={kv_gb:.3f}GB ({kv_gb/sec:6.1f} GB/s) | "
              f"3-bit-KV would be {kv3_gb:.3f}GB (~{kv_gb/kv3_gb:.1f}x less traffic)")
    except Exception as e:  # noqa
        print(f"  T={T:>7}  SDPA failed: {str(e)[:80]}")
print("\nDONE")
