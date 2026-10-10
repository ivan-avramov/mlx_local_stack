"""Memory-mechanism debug (2026-08-31 night): why did a bare-process 32K prefill of a 17 GB model show ~49 GB?
Hypothesis: MLX allocator cache bloat (default cache_limit = 65 GB on this box; get_peak_memory EXCLUDES the pool).
Runs prefill in 512-token steps, logs mx active/cache/peak + process RSS every 4 steps, aborts at a hard RSS cap.
Usage: memdebug.py <model> <n_tokens> <cache_limit_gb or 0> <rss_abort_gb>"""
import sys, time, os, subprocess
import mlx.core as mx
from mlx_vlm.utils import load
path, n, cap_gb, abort_gb = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
if cap_gb > 0: mx.set_cache_limit(int(cap_gb * 1e9))
def rss_gb(): return int(subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout) / 1e6
def report(tag):
    print(f"{tag:>10s}  active={mx.get_active_memory()/1e9:5.1f}  cache={mx.get_cache_memory()/1e9:5.1f}  peak={mx.get_peak_memory()/1e9:5.1f}  RSS={rss_gb():5.1f} GB", flush=True)
t0 = time.time(); report("start")
model, processor = load(path, lazy=True); mx.eval(model.parameters()); report("loaded")
lm = model.language_model
tokens = mx.random.randint(1000, 20000, (1, n)); cache = lm.make_cache()
step = 512
for i, s in enumerate(range(0, n, step)):
    out = lm(tokens[:, s:s+step], cache=cache); mx.eval(out.logits if hasattr(out, "logits") else out)
    if i % 4 == 0: report(f"tok {s+step}")
    if (mx.get_active_memory()+mx.get_cache_memory())/1e9 > abort_gb: report("ABORT"); print(f"active+cache exceeded {abort_gb} GB -> aborting (ps RSS is BLIND to Metal buffers)"); sys.exit(9)
report("end"); print(f"total {time.time()-t0:.1f}s  -> {n/(time.time()-t0):.0f} tok/s (incl. load)")
