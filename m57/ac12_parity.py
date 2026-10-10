"""M57 AC12 GPU parity gate (no model): fused vs unfused vs fp32 CPU reference, bf16, first pick's attention shape."""
import json, sys
import mlx.core as mx
HQ, HKV, D = 24, 4, 256; SCALE = D ** -0.5; bf = mx.bfloat16
sdpa = mx.fast.scaled_dot_product_attention
mx.set_cache_limit(4 * 1024**3)
mx.random.seed(0)
K = mx.random.normal((1, HKV, 262144, D)).astype(bf); V = mx.random.normal((1, HKV, 262144, D)).astype(bf); mx.eval(K, V)
def ref(q, k, v, rows=128):
    q32, k32, v32 = (a.astype(mx.float32) for a in (q, k, v)); qL, kL = q.shape[2], k.shape[2]; outs = []
    for i in range(0, qL, rows):
        j = min(i + rows, qL)
        m = mx.arange(kL)[None, :] <= (mx.arange(i, j)[:, None] + (kL - qL))
        o = sdpa(q32[:, :, i:j], k32, v32, scale=SCALE, mask=m, stream=mx.cpu); mx.eval(o); outs.append(o)
    return mx.concatenate(outs, axis=2)
def err(a, r):
    d = a.astype(mx.float32) - r
    return round(mx.sqrt(mx.mean(d * d)).item() / mx.sqrt(mx.mean(r * r)).item(), 6), bool(mx.any(mx.isnan(a.astype(mx.float32))).item())
rows, ok = [], True
for gain in (1.0, 4.0):
    for qL in (9, 127, 128, 512):
        mx.random.seed(100 + qL); q = (mx.random.normal((1, HQ, qL, D)) * gain).astype(bf); mx.eval(q)
        for kL in (4096, 131072, 262144):
            k, v = K[:, :, :kL], V[:, :, :kL]; r = ref(q, k, v)
            u = sdpa(q, k, v, scale=SCALE, mask="causal"); f = sdpa(q, k, v, scale=SCALE, mask="causal", force_fused=True); mx.eval(u, f)
            (eu, nu), (ef, nf) = err(u, r), err(f, r)
            row = {"gain": gain, "qL": qL, "kL": kL, "unfused_rel_rms": eu, "fused_rel_rms": ef, "nan": nu or nf, "pass": (ef <= eu) and not nf}
            ok &= row["pass"]; rows.append(row); print(json.dumps(row), flush=True); mx.clear_cache()
json.dump({"mlx": mx.__version__, "rows": rows, "all_pass": ok}, open(sys.argv[1], "w"), indent=1); print("AC12 all_pass =", ok)
