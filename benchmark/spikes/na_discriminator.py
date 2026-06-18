"""
NA discriminator — run with a source-built mlx (Metal-4) on M5 to test whether
the Neural Accelerators activate.

Signal: NA accelerates fp16/bf16/int matmul, NOT fp32. So if NA is live, the
fp16/fp32 (and bf16/fp32) matmul throughput ratio jumps to ~3-4x, and/or
quantized_matmul (the op the 6-bit model uses) jumps well above the ~50 TFLOP/s
seen with the non-NA wheel.

Baseline (mlx 0.31.2 PyPI wheel, NA NOT active, M5 Max):
  plain matmul fp16 ~57000 GFLOP/s, fp16/fp32 = 1.35x, quantized_matmul ~50000.

  .venv/bin/python benchmark/spikes/na_discriminator.py
"""
import time
import mlx.core as mx


def bench(fn, it=30, wu=10):
    for _ in range(wu):
        mx.eval(fn())
    mx.synchronize()
    t = time.perf_counter()
    for _ in range(it):
        mx.eval(fn())
    mx.synchronize()
    return (time.perf_counter() - t) / it


print("=" * 64)
print(f"mlx {mx.__version__}  |  {mx.device_info()['device_name']}")
print("=" * 64)
for (M, N, K) in [(4096, 4096, 4096), (8192, 8192, 8192)]:
    print(f"\n--- matmul {M}x{N}x{K} ---")
    g = {}
    for dt, name in [(mx.float16, "fp16"), (mx.bfloat16, "bf16"), (mx.float32, "fp32")]:
        a = mx.random.normal((M, K)).astype(dt)
        w = mx.random.normal((K, N)).astype(dt)
        mx.eval(a, w)
        s = bench(lambda: a @ w)
        g[name] = 2 * M * N * K / s / 1e9
        print(f"  matmul {name}: {g[name]:8.0f} GFLOP/s")
    print(f"  >> fp16/fp32 = {g['fp16']/g['fp32']:.2f}x   bf16/fp32 = {g['bf16']/g['fp32']:.2f}x   "
          f"(NA LIVE if >= ~3x; was 1.35x without NA)")
    x = mx.random.normal((M, K)).astype(mx.float16)
    for bits in (4, 6, 8):
        w = mx.random.normal((N, K)).astype(mx.float16)
        wq, sc, bi = mx.quantize(w, 64, bits)
        mx.eval(x, wq, sc, bi)
        s = bench(lambda: mx.quantized_matmul(x, wq, sc, bi, transpose=True, group_size=64, bits=bits))
        print(f"  quantized_matmul {bits}-bit: {2*M*N*K/s/1e9:8.0f} GFLOP/s  (was ~50000 without NA)")
print("\nVERDICT: fp16/fp32 >= ~3x OR quantized_matmul >> 50000 => NA is active.")
print("DONE")
