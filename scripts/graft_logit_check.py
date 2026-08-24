"""Text-path equivalence: bit-identical logits between original and grafted checkpoints."""
import gc, sys
import mlx.core as mx
from mlx_vlm.utils import load_model
from pathlib import Path

ORIG = Path(sys.argv[1]); GRAFT = Path(sys.argv[2])
TOKENS = list(range(1000, 1032))  # fixed arbitrary 32-token sequence

def logits_for(path):
    model = load_model(path, lazy=False)
    lm = model.language_model
    x = mx.array([TOKENS])
    out = lm(x)
    logits = out.logits if hasattr(out, "logits") else out
    mx.eval(logits)
    arr = logits.astype(mx.float32)
    mx.eval(arr)
    return arr

a = logits_for(ORIG)
mx.clear_cache(); gc.collect()
b = logits_for(GRAFT)
same = bool(mx.array_equal(a, b))
print("LOGITS BIT-IDENTICAL:", same)
if not same:
    d = mx.abs(a - b)
    print("max abs diff:", float(d.max()), "argmax rows equal:",
          bool(mx.array_equal(a.argmax(-1), b.argmax(-1))))
sys.exit(0 if same else 1)
