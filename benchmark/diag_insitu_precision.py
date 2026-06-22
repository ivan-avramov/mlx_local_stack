"""IN-SITU causal test: does upcasting attention (and/or MoE) precision eliminate
the suffix-decoding divergence in the REAL gemma-4-26b-a4b-it-8bit model?

Loads ONCE, then for each precision variant measures:
  (A) multi-vs-single KV maxdiff at full-attn layers (the sensitive probe), and
  (B) suffix-loop vs sequential first_mismatch / count  (the real losslessness test).

Variant is selected by monkeypatching the gemma4 attention (and optionally MoE)
to upcast q/k/v (and x) to a higher dtype, compute, then downcast. The SEQUENTIAL
reference uses the SAME patch, so a variant that makes multi==single proves the
suffix loop is lossless under that precision.

  baseline (bf16)  -> reproduces the divergence
  attn=fp32        -> attention computed in fp32 (decode & verify identical)
  attn=fp16        -> cheaper alternative
  attn+moe=fp32    -> both upcast

Run with the server stopped (loads its own ~26GB):
  cd benchmark && PYTHONPATH=../mlx-vlm:. \
      ../.venv/bin/python diag_insitu_precision.py
"""
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.models.cache import make_prompt_cache, KVCache
import mlx_vlm.models.gemma4.language as G
from mlx_vlm.speculative.suffix_decoding import (
    SuffixDecodingProposer, run_suffix_decoding_rounds,
)
from mlx_lm.sample_utils import make_sampler
from bench.run_convergence import CODING_PROMPT

HF = "mlx-community/gemma-4-26b-a4b-it-8bit"
N = 140
K = 90  # KV-diff probe length

_ORIG_SDPA = G.scaled_dot_product_attention
_ORIG_EXPERTS_CALL = G.Experts.__call__


def install_patches(attn_dt=None, moe_dt=None):
    """attn_dt / moe_dt: an mx dtype to upcast to, or None to leave bf16."""
    if attn_dt is None:
        G.scaled_dot_product_attention = _ORIG_SDPA
    else:
        def sdpa_hi(queries, keys, values, cache, scale, mask, sinks=None):
            m = mask.astype(attn_dt) if isinstance(mask, mx.array) else mask
            s = sinks.astype(attn_dt) if isinstance(sinks, mx.array) else sinks
            o = _ORIG_SDPA(queries.astype(attn_dt), keys.astype(attn_dt),
                           values.astype(attn_dt), cache, scale, m, s)
            return o.astype(queries.dtype)
        G.scaled_dot_product_attention = sdpa_hi

    if moe_dt is None:
        G.Experts.__call__ = _ORIG_EXPERTS_CALL
    else:
        def experts_hi(self, x, top_k_indices, top_k_weights):
            w = mx.expand_dims(top_k_weights.astype(moe_dt), -1)
            y = self.switch_glu(x.astype(moe_dt), top_k_indices)
            return ((w * y.astype(moe_dt)).sum(-2)).astype(x.dtype)
        G.Experts.__call__ = experts_hi


def lg(o):
    return o.logits if hasattr(o, "logits") else o


def decode_seq(lm, input_ids, n):
    c = make_prompt_cache(lm)
    o = lm(input_ids, cache=c); mx.eval(lg(o))
    y = int(mx.argmax(lg(o)[0, -1]).item()); seq = [y]
    for _ in range(n - 1):
        o = lm(mx.array([[y]]), cache=c); mx.eval(lg(o))
        y = int(mx.argmax(lg(o)[0, -1]).item()); seq.append(y)
    return seq


def kv_diff(lm, ids, seq, k):
    P = len(ids)
    cs = make_prompt_cache(lm); lm(mx.array(ids)[None], cache=cs)
    for t in seq[:k]:
        lm(mx.array([[t]]), cache=cs)
    cm = make_prompt_cache(lm); lm(mx.array([ids + seq[:k]]), cache=cm)
    worst = 0.0
    for a, b in zip(cs, cm):
        if not (isinstance(a, KVCache) and isinstance(b, KVCache)):
            continue
        ka = a.keys[..., P:P + k, :]; kb = b.keys[..., P:P + k, :]
        d = float(mx.max(mx.abs(ka - kb)).item())
        worst = max(worst, d)
    return worst


def suffix_loop(model, lm, ids, n):
    sampler = make_sampler(temp=0.0)
    c = make_prompt_cache(lm)
    o = lm(mx.array(ids)[None], cache=c); mx.eval(lg(o))
    first = int(mx.argmax(lg(o)[0, -1]).item())
    prop = SuffixDecodingProposer(min_match=2, max_match=8, cooldown=2)
    loop = [first]
    for _t, _ in run_suffix_decoding_rounds(
        model, prop, c, ids, first_bonus=first, max_tokens=n, sampler=sampler,
        draft_block_size=16, token_dtype=mx.array(ids).dtype,
        thinking_budget_criteria=None,
    ):
        loop.append(int(_t))
        if len(loop) >= n:
            break
    return loop


def main():
    print(f"loading {HF} ...", flush=True)
    model, processor = load(HF)
    lm = model.language_model
    tok = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    ids = tok.encode(tok.apply_chat_template(
        [{"role": "user", "content": CODING_PROMPT}],
        add_generation_prompt=True, tokenize=False), add_special_tokens=False)

    variants = [
        ("baseline bf16", None, None),
        ("moe=fp32 only", None, mx.float32),
        ("moe=fp16 only", None, mx.float16),
        ("attn+moe=fp16", mx.float16, mx.float16),
    ]
    for name, adt, mdt in variants:
        install_patches(adt, mdt)
        seq = decode_seq(lm, mx.array(ids)[None], N)
        kvd = kv_diff(lm, ids, seq, K)
        loop = suffix_loop(model, lm, ids, N)
        M = min(len(loop), len(seq))
        mism = [i for i in range(M) if loop[i] != seq[i]]
        fm = mism[0] if mism else None
        verdict = "LOSSLESS" if not mism else "DIVERGES"
        print(f"\n[{name:14s}] KVmaxdiff(K={K})={kvd:.5f}  "
              f"suffix-loop: first_mismatch={fm} num={len(mism)}/{M}  -> {verdict}", flush=True)
        mx.clear_cache()

    install_patches(None, None)


if __name__ == "__main__":
    main()
