"""M57 follow-up, no model: (1) GatedDeltaNet recurrence — Metal per-token kernel vs chunk-parallel form; (2) MLP-shaped
quantized matmul vs dense. First pick's shapes: hidden 5120, intermediate 17408, linear heads Hk=16/Hv=48, dims 128."""
import json, statistics, sys, time
import mlx.core as mx
from mlx_vlm.models.qwen3_5 import gated_delta as gd
mx.set_cache_limit(4 * 1024**3)
bf = mx.bfloat16
def timeit(fn, reps=7, warm=3):
    for _ in range(warm): mx.eval(fn())
    ts = []
    for _ in range(reps):
        t = time.perf_counter(); mx.eval(fn()); ts.append(time.perf_counter() - t)
    return round(min(ts) * 1e3, 3), round(statistics.median(ts) * 1e3, 3)
out = {"mlx": mx.__version__, "gdn": [], "mlp": []}
mx.random.seed(0)
Hk, Hv, Dk, Dv = 16, 48, 128, 128
for T in (512, 1024):
    q = mx.random.normal((1, T, Hk, Dk)).astype(bf) * 0.05; k = mx.random.normal((1, T, Hk, Dk)).astype(bf) * 0.09
    v = mx.random.normal((1, T, Hv, Dv)).astype(bf)
    g = mx.random.uniform(0.9, 1.0, (1, T, Hv)).astype(mx.float32); beta = mx.random.uniform(0.0, 1.0, (1, T, Hv)).astype(mx.float32)
    state = mx.zeros((1, Hv, Dv, Dk), dtype=mx.float32); mx.eval(q, k, v, g, beta, state)
    row = {"T": T}
    try:
        row["metal_kernel_ms"] = timeit(lambda: gd.gated_delta_kernel(q, k, v, g, beta, state))
    except Exception as e: row["metal_kernel_err"] = repr(e)[:300]
    try:
        row["chunk_parallel_ms"] = timeit(lambda: gd.gated_delta_chunked(q, k, v, g, beta, state))
        a = gd.gated_delta_kernel(q, k, v, g, beta, state)[0].astype(mx.float32); b = gd.gated_delta_chunked(q, k, v, g, beta, state)[0].astype(mx.float32)
        row["rel_rms_diff"] = round((mx.sqrt(mx.mean((a - b) ** 2)) / mx.sqrt(mx.mean(a * a))).item(), 6)
    except Exception as e: row["chunk_parallel_err"] = repr(e)[:300]
    out["gdn"].append(row); print("gdn", json.dumps(row), flush=True)
H, I = 5120, 17408
W = mx.random.normal((I, H)) * 0.02; mx.eval(W)
Wd = W.astype(bf); mx.eval(Wd)
q4 = mx.quantize(W, group_size=64, bits=4); q8 = mx.quantize(W, group_size=64, bits=8); mx.eval(*q4, *q8)
for T in (512, 1024):
    x = mx.random.normal((1, T, H)).astype(bf); mx.eval(x)
    row = {"T": T, "gflop": round(2 * T * H * I / 1e9, 1),
           "dense_bf16_ms": timeit(lambda: x @ Wd.T),
           "qmm4_ms": timeit(lambda: mx.quantized_matmul(x, *q4, transpose=True, group_size=64, bits=4)),
           "qmm8_ms": timeit(lambda: mx.quantized_matmul(x, *q8, transpose=True, group_size=64, bits=8))}
    for kname in ("dense_bf16_ms", "qmm4_ms", "qmm8_ms"):
        row[kname.replace("_ms", "_tflops")] = round(row["gflop"] / row[kname][0], 1)
    out["mlp"].append(row); print("mlp", json.dumps(row), flush=True)
json.dump(out, open(sys.argv[1], "w"), indent=1)
