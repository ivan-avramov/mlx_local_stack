"""One-off instrumented prefill to diagnose the gemma-4-31b long-context peak.

Loads gemma-4-31b-it-4bit standalone (no server), runs a real chunked prefill
to ~96K tokens on the uniform-4bit path, and measures where the memory goes:

  - weights (fixed)
  - per-chunk attention working set at long context  (intra-chunk co-residency)
  - active high-water (get_peak_memory)              (the "true" peak)
  - buffer pool retained, not returned to OS         (get_cache_memory ~ RSS gap)
  - effect of mx.clear_cache()                        (cheap RSS fix candidate)

Run: .venv/bin/python memtest_prefill.py 2>&1 | tee logs/memtest_prefill.log
"""
import sys, time
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.generate.common import maybe_quantize_kv_cache

MODEL = "mlx-community/gemma-4-31b-it-4bit"
TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 96256
STEP = 512
GB = 1e9

def snap():
    return (mx.get_active_memory()/GB, mx.get_cache_memory()/GB, mx.get_peak_memory()/GB)

def log(msg):
    print(msg, flush=True)

log(f"[load] {MODEL}")
t0 = time.time()
model, _ = load(MODEL)
mx.eval(model.language_model.parameters())
a, c, p = snap()
log(f"[load] done in {time.time()-t0:.0f}s | weights active={a:.1f}G cache={c:.1f}G")
W = a

lm = model.language_model
cache = lm.make_cache()
log(f"[cache] {len(cache)} layers: {sum(1 for x in cache if type(x).__name__=='KVCache')} full / "
    f"{sum(1 for x in cache if 'Rotating' in type(x).__name__)} sliding")

ids = mx.random.randint(0, 262000, (1, TARGET))
mx.eval(ids)

processed = 0
t0 = time.time()
single_chunk_peak = None
while processed < TARGET - 1:
    n = min(STEP, TARGET - 1 - processed)
    # Capture the working set of ONE chunk at the LONGEST context (last chunk):
    last = (processed + n >= TARGET - 1)
    if last:
        mx.clear_cache(); mx.reset_peak_memory()
        a_before, _, _ = snap()
    chunk = ids[:, processed:processed + n]
    lm.model(inputs=chunk, cache=cache)          # inner forward = hidden states, no lm_head
    maybe_quantize_kv_cache(cache, quantized_kv_start=0, kv_group_size=64,
                            kv_bits=4, kv_quant_scheme="uniform")
    mx.eval([c.state for c in cache])
    if last:
        a_after, _, p_after = snap()
        single_chunk_peak = p_after - a_before
    processed += n
    if processed % (STEP*20) == 0 or last:
        a, c, p = snap()
        log(f"[prefill] {processed:>7}/{TARGET} tok | active={a:5.1f}G cache={c:5.1f}G "
            f"peak={p:5.1f}G | {processed/(time.time()-t0):.0f} tok/s")

a1, c1, p1 = snap()
log("")
log(f"=== RESULT @ ctx={processed} (uniform 4-bit, step={STEP}) ===")
log(f"weights (fixed)............... {W:5.1f} G")
log(f"active high-water (true peak). {p1:5.1f} G   <- get_peak_memory")
log(f"active now (post-prefill)..... {a1:5.1f} G")
log(f"buffer pool retained.......... {c1:5.1f} G   <- get_cache_memory")
log(f"approx RSS (active+pool)...... {a1+c1:5.1f} G   <- ~ Activity Monitor")
log(f"single-chunk working set...... {single_chunk_peak:5.1f} G   <- intra-chunk co-residency at long ctx")
mx.clear_cache()
a2, c2, _ = snap()
log(f"after mx.clear_cache()........ active={a2:.1f}G cache={c2:.1f}G  (reclaimed {(a1+c1)-(a2+c2):.1f}G)")
log("")
log("READ: if single-chunk working set ~= 1 global layer (~3.4G@96K) -> MLX frees per-layer,")
log("      high RSS is POOL retention -> mx.clear_cache() during prefill is the cheap fix.")
log("      if single-chunk working set is many GB -> intra-chunk co-residency -> per-layer eval.")
