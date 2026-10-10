"""M57 step-1 follow-up: (1) validate the memory instrument; (2) serving-like chunk: clear_cache, then 16 dependent
attention layers in ONE eval, pool limit 9 GiB (as the worker derives at step 512)."""
import json, statistics, sys, time
import mlx.core as mx
HQ, HKV, D = 24, 4, 256; SCALE = D ** -0.5; GIB = 1024 ** 3
sdpa = mx.fast.scaled_dot_product_attention
bf = mx.bfloat16
mx.set_cache_limit(9 * GIB); mx.set_memory_limit(44 * GIB)
out = {}
def snap(): return {"active": round(mx.get_active_memory()/1e9, 3), "cache": round(mx.get_cache_memory()/1e9, 3), "peak": round(mx.get_peak_memory()/1e9, 3)}
# (1) instrument
mx.clear_cache(); mx.reset_peak_memory(); s0 = snap()
x = mx.zeros((HQ, 512, 131072), dtype=bf) + mx.array(1.0, dtype=bf); mx.eval(x); s1 = snap()
del x; s2 = snap(); mx.clear_cache(); s3 = snap()
out["instrument"] = {"before": s0, "after_eval_3.22GB": s1, "after_del": s2, "after_clear": s3}
print("instrument", json.dumps(out["instrument"]), flush=True)
mx.random.seed(0)
K = mx.random.normal((1, HKV, 262144, D)).astype(bf); V = mx.random.normal((1, HKV, 262144, D)).astype(bf); mx.eval(K, V)
def chunk(qL, kL, forced, layers=16):
    k, v = K[:, :, :kL], V[:, :, :kL]
    x = mx.random.normal((1, HQ, qL, D)).astype(bf)
    for _ in range(layers):
        o = sdpa(x, k, v, scale=SCALE, mask="causal", **({"force_fused": True} if forced else {}))
        x = x + o * mx.array(1e-3, dtype=bf)
    return x
rows = []
for qL, kL in ((512, 65536), (512, 131072), (512, 262144), (1024, 131072), (1024, 262144)):
    for forced in (False, True):
        if qL >= 1024 and forced: continue
        mx.eval(chunk(qL, kL, forced, layers=2))  # compile
        ts, peaks = [], []
        for _ in range(4):
            mx.clear_cache(); base = mx.get_active_memory(); mx.reset_peak_memory()
            t = time.perf_counter(); r = chunk(qL, kL, forced); mx.eval(r); ts.append(time.perf_counter() - t)
            peaks.append(mx.get_peak_memory() - base); del r
        row = {"qL": qL, "kL": kL, "path": "forced" if forced else "auto",
               "ms_per_layer_min": round(min(ts)/16*1e3, 2), "ms_per_layer_med": round(statistics.median(ts)/16*1e3, 2),
               "transient_peak_gb": round(max(peaks)/1e9, 3), "one_score_tensor_gb": round(HQ*qL*kL*2/1e9, 3)}
        rows.append(row); print("chunk", json.dumps(row), flush=True)
out["serving_like"] = rows
json.dump(out, open(sys.argv[1], "w"), indent=1)
