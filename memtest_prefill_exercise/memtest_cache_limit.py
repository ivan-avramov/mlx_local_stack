"""Validate the set_cache_limit fix: does capping the MLX buffer pool bound RSS
without hurting prefill tok/s?

A/B in one process (controls for machine/thermal state):
  Phase A: default cache limit (as MLX ships)
  Phase B: mx.set_cache_limit(6 GB)
Each runs a real uniform-4bit chunked prefill to ~16K on gemma-4-31b, logging
per-interval tok/s, active mem, buffer pool, and peak. Baseline runs first so
any thermal throttling penalizes the CAPPED phase (conservative for the cap).
"""
import time
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.generate.common import maybe_quantize_kv_cache

MODEL = "mlx-community/gemma-4-31b-it-4bit"
TARGET, STEP, LOG_EVERY = 16384, 512, 4096
GB = 1024**3

def log(m): print(m, flush=True)

log(f"[load] {MODEL}")
model, _ = load(MODEL)
mx.eval(model.language_model.parameters())
lm = model.language_model
log(f"[load] weights active={mx.get_active_memory()/1e9:.1f}G")
ids = mx.random.randint(0, 262000, (1, TARGET)); mx.eval(ids)

def run(label, cache_limit):
    if cache_limit is None:
        mx.set_cache_limit(64 * GB)         # effectively unlimited (default-like)
    else:
        mx.set_cache_limit(cache_limit)
    mx.clear_cache(); mx.reset_peak_memory()
    cache = lm.make_cache()
    log(f"\n--- {label} (cache_limit={'~unlimited' if cache_limit is None else f'{cache_limit/GB:.0f}G'}) ---")
    log(f"{'tok':>7} | {'tok/s(interval)':>15} | {'active':>7} {'pool':>7} {'peak':>7} {'RSS':>7}")
    processed, t_iv, tok_iv = 0, time.time(), 0
    rows = []
    while processed < TARGET - 1:
        n = min(STEP, TARGET - 1 - processed)
        lm.model(inputs=ids[:, processed:processed + n], cache=cache)
        maybe_quantize_kv_cache(cache, quantized_kv_start=0, kv_group_size=64,
                                kv_bits=4, kv_quant_scheme="uniform")
        mx.eval([c.state for c in cache])
        processed += n; tok_iv += n
        if processed % LOG_EVERY == 0:
            dt = time.time() - t_iv
            a, c, p = mx.get_active_memory()/1e9, mx.get_cache_memory()/1e9, mx.get_peak_memory()/1e9
            tps = tok_iv / dt
            log(f"{processed:>7} | {tps:>15.0f} | {a:6.1f}G {c:6.1f}G {p:6.1f}G {a+c:6.1f}G")
            rows.append((tps, a, c, a + c, p))
            t_iv, tok_iv = time.time(), 0
    # steady-state = mean of all but the first interval (warmup)
    steady = rows[1:] if len(rows) > 1 else rows
    avg_tps = sum(r[0] for r in steady) / len(steady)
    max_rss = max(r[3] for r in rows); max_peak = max(r[4] for r in rows)
    log(f"  -> steady tok/s={avg_tps:.0f} | max RSS={max_rss:.1f}G | max peak={max_peak:.1f}G")
    return avg_tps, max_rss, max_peak

a_tps, a_rss, a_peak = run("PHASE A: baseline", None)
b_tps, b_rss, b_peak = run("PHASE B: capped", 6 * GB)

log("\n==================== SUMMARY ====================")
log(f"{'':18} {'tok/s':>8} {'maxRSS':>8} {'maxPeak':>8}")
log(f"{'baseline':18} {a_tps:>8.0f} {a_rss:>7.1f}G {a_peak:>7.1f}G")
log(f"{'capped @6G':18} {b_tps:>8.0f} {b_rss:>7.1f}G {b_peak:>7.1f}G")
log(f"{'delta':18} {(b_tps-a_tps)/a_tps*100:>7.1f}% {b_rss-a_rss:>+7.1f}G {b_peak-a_peak:>+7.1f}G")
log("\nREAD: RSS should drop sharply with the cap; tok/s delta is the speed cost.")
