"""Prefill split micro-benchmark (P14 item 2): where does prefill time go on a qwen3_5 hybrid?
Times each decoder layer's sub-blocks by category (GatedDeltaNet mixer / full attention / MLP-MoE)
with an mx.eval after each, on a synthetic prompt of N tokens. Serializing evals inflates the
absolute numbers a little but the CATEGORY SPLIT is what we want. Run only with the box quiet
(one resident model rule): PYTHONPATH=$STACK_REPO/src/mlx-vlm $STACK_REPO/.venv/bin/python prefill_split.py <model_path> <n_tokens>
"""
import sys, time, collections
import mlx.core as mx
mx.set_cache_limit(int(4e9))  # MANDATORY in bare-process MLX runs: default cache limit is 65 GB on this 64 GB box (2026-08-31 RCA)
from mlx_vlm.utils import load

path, n = sys.argv[1], int(sys.argv[2])
model, processor = load(path, lazy=True)  # lazy: materialize per-layer, avoid the double-resident load that swapped the box on 2026-08-31
lm = model.language_model
layers = lm.model.layers if hasattr(lm, "model") else lm.layers
stats = collections.defaultdict(float); counts = collections.Counter()

class Timed:
    """Attribute-replacement wrapper: `obj(...)` resolves __call__ on the TYPE, so assigning
    `mod.__call__` on an instance never intercepts — replace the parent's attribute instead."""
    def __init__(self, mod, cat): self.mod, self.cat = mod, cat
    def __call__(self, *a, **k):
        mx.synchronize(); t0 = time.perf_counter()
        out = self.mod(*a, **k); mx.eval(out); mx.synchronize()
        stats[self.cat] += time.perf_counter() - t0; counts[self.cat] += 1
        return out
    def __getattr__(self, n): return getattr(self.mod, n)

for i, layer in enumerate(layers):
    for name in ("linear_attn", "self_attn", "mlp", "input_layernorm", "post_attention_layernorm"):
        sub = getattr(layer, name, None)
        if sub is not None:
            cat = {"linear_attn": "gdn", "self_attn": "attn", "mlp": "mlp"}.get(name, "norm")
            object.__setattr__(layer, name, Timed(sub, cat))

tokens = mx.random.randint(1000, 20000, (1, n))
cache = lm.make_cache() if hasattr(lm, "make_cache") else None
mx.synchronize(); t0 = time.perf_counter()
step = 512
for s in range(0, n, step):
    out = lm(tokens[:, s:s+step], cache=cache); mx.eval(out.logits if hasattr(out, "logits") else out)
mx.synchronize(); total = time.perf_counter() - t0
print(f"model={path} n={n} prefill_step={step} total={total:.1f}s -> {n/total:.0f} tok/s")
for cat, t in sorted(stats.items(), key=lambda kv: -kv[1]):
    print(f"  {cat:5s} {t:7.1f}s  {100*t/total:5.1f}%  calls={counts[cat]}")
print("peak_mem_gb", mx.get_peak_memory()/1e9)
