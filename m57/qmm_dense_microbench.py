"""M57 follow-up, no model: is 'dequantize a layer's weight, then dense GEMM' faster than quantized matmul at prefill chunk sizes,
and what does it do to accuracy? MLP shape of the first pick (5120 -> 17408), group size 64."""
import json, statistics, sys, time
import mlx.core as mx
mx.set_cache_limit(6 * 1024**3)
def timeit(fn, reps=5, warm=2):
    for _ in range(warm): mx.eval(fn())
    ts = []
    for _ in range(reps):
        t = time.perf_counter(); mx.eval(fn()); ts.append(time.perf_counter() - t)
    return round(min(ts) * 1e3, 3)
H, I = 5120, 17408
mx.random.seed(0)
W = mx.random.normal((I, H)) * 0.02; mx.eval(W)
out = []
for bits in (4, 8):
    qw = mx.quantize(W, group_size=64, bits=bits); mx.eval(*qw)
    Wref = mx.dequantize(*qw, group_size=64, bits=bits); mx.eval(Wref)  # fp32 exact dequantized weight
    deq = {}
    for name, dt in (("bf16", mx.bfloat16), ("fp16", mx.float16), ("fp32", mx.float32)):
        deq[name] = timeit(lambda: mx.dequantize(*qw, group_size=64, bits=bits).astype(dt))
    for T in (512, 2048, 4096):
        x = mx.random.normal((1, T, H)).astype(mx.bfloat16); mx.eval(x)
        gflop = 2 * T * H * I / 1e9
        ref = mx.matmul(x.astype(mx.float32), Wref.T, stream=mx.cpu); mx.eval(ref)
        rms = mx.sqrt(mx.mean(ref * ref)).item()
        def err(y): return round(mx.sqrt(mx.mean((y.astype(mx.float32) - ref) ** 2)).item() / rms, 6)
        row = {"bits": bits, "T": T, "gflop": round(gflop, 1), "dequantize_ms": deq}
        y = mx.quantized_matmul(x, *qw, transpose=True, group_size=64, bits=bits); mx.eval(y)
        row["qmm"] = {"ms": timeit(lambda: mx.quantized_matmul(x, *qw, transpose=True, group_size=64, bits=bits)), "rel_rms_err": err(y)}
        for name, dt in (("bf16", mx.bfloat16), ("fp16", mx.float16), ("fp32", mx.float32)):
            Wd = Wref.astype(dt); mx.eval(Wd); xd = x.astype(dt) if dt != mx.bfloat16 else x; mx.eval(xd)
            y = xd @ Wd.T; mx.eval(y)
            row["dense_" + name] = {"ms": timeit(lambda: xd @ Wd.T), "rel_rms_err": err(y),
                                    "ms_incl_dequant": round(timeit(lambda: xd @ mx.dequantize(*qw, group_size=64, bits=bits).astype(dt).T), 3)}
            del Wd
        for k in ("qmm", "dense_bf16", "dense_fp16", "dense_fp32"):
            row[k]["tflops"] = round(gflop / row[k]["ms"], 1)
        out.append(row); print(json.dumps(row), flush=True)
        mx.clear_cache()
json.dump(out, open(sys.argv[1], "w"), indent=1)
