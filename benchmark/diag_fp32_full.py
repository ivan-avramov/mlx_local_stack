"""Disambiguator: is the suffix divergence PURELY bf16 batched-vs-sequential
precision, or a genuine batch-handling LOGIC bug (mask / rotating cache / router
expert-selection) that survives even in fp32?

Casts the ENTIRE language model to fp32 (every matmul, norm, router, SDPA, gather
runs fp32 -> every op is batch-independent per the primitive test) and measures:
  - multi-vs-single KV maxdiff at full-attn layers
  - clean block-forward vs sequential argmax mismatch (verify-logit divergence)
  - suffix-loop vs sequential token mismatch

  KVdiff ~0 AND lossless  => divergence is PURELY bf16 precision (inherent;
                             no logic bug). The fix is a precision/perf tradeoff.
  KVdiff > 0 OR diverges  => a real batch-handling LOGIC bug persists in fp32
                             (router selection / rotating-cache / mask) -> fixable.

Run with server stopped (loads ~26GB, fp32 activations on top).
"""
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.models.cache import make_prompt_cache, KVCache
from mlx_vlm.speculative.suffix_decoding import (
    SuffixDecodingProposer, run_suffix_decoding_rounds,
)
from mlx_lm.sample_utils import make_sampler
from bench.run_convergence import CODING_PROMPT

HF = "mlx-community/gemma-4-26b-a4b-it-8bit"
N = 140
K = 90


def lg(o):
    return o.logits if hasattr(o, "logits") else o


def main():
    print(f"loading {HF} ...", flush=True)
    model, processor = load(HF)
    lm = model.language_model
    print("casting language model to fp32 ...", flush=True)
    lm.set_dtype(mx.float32)
    mx.eval(lm.parameters())

    tok = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    ids = tok.encode(tok.apply_chat_template(
        [{"role": "user", "content": CODING_PROMPT}],
        add_generation_prompt=True, tokenize=False), add_special_tokens=False)
    input_ids = mx.array(ids)[None]
    P = len(ids)

    # sequential greedy decode
    cseq = make_prompt_cache(lm)
    o = lm(input_ids, cache=cseq); mx.eval(lg(o))
    y = int(mx.argmax(lg(o)[0, -1]).item()); seq = [y]
    for _ in range(N - 1):
        o = lm(mx.array([[y]]), cache=cseq); mx.eval(lg(o))
        y = int(mx.argmax(lg(o)[0, -1]).item()); seq.append(y)

    # KV diff: single-token vs multi-token forward of seq[0:K]
    cs = make_prompt_cache(lm); lm(input_ids, cache=cs)
    for t in seq[:K]:
        lm(mx.array([[t]]), cache=cs)
    cm = make_prompt_cache(lm); lm(mx.array([ids + seq[:K]]), cache=cm)
    worst = 0.0
    for a, b in zip(cs, cm):
        if isinstance(a, KVCache) and isinstance(b, KVCache):
            d = float(mx.max(mx.abs(a.keys[..., P:P + K, :] - b.keys[..., P:P + K, :])).item())
            worst = max(worst, d)

    # clean block-forward verify vs sequential argmax
    cblk = make_prompt_cache(lm); lm(input_ids, cache=cblk)
    ob = lm(mx.array(seq)[None], cache=cblk); lgb = lg(ob); mx.eval(lgb)
    blk = [int(x) for x in mx.argmax(lgb[0], axis=-1).tolist()]
    blk_mism = [i for i in range(N - 1) if blk[i] != seq[i + 1]]

    # suffix loop
    sampler = make_sampler(temp=0.0)
    c = make_prompt_cache(lm)
    o = lm(input_ids, cache=c); mx.eval(lg(o))
    first = int(mx.argmax(lg(o)[0, -1]).item())
    prop = SuffixDecodingProposer(min_match=2, max_match=8, cooldown=2)
    loop = [first]
    for _t, _ in run_suffix_decoding_rounds(
        model, prop, c, ids, first_bonus=first, max_tokens=N, sampler=sampler,
        draft_block_size=16, token_dtype=input_ids.dtype, thinking_budget_criteria=None):
        loop.append(int(_t))
        if len(loop) >= N:
            break
    M = min(len(loop), len(seq))
    loop_mism = [i for i in range(M) if loop[i] != seq[i]]

    print(f"\n=== FULL fp32 forward ===", flush=True)
    print(f"KV maxdiff (multi vs single, K={K}) = {worst:.6f}", flush=True)
    print(f"block-forward argmax mismatch vs sequential = {len(blk_mism)}/{N-1} "
          f"first@{blk_mism[0] if blk_mism else None}", flush=True)
    print(f"suffix-loop token mismatch vs sequential = {len(loop_mism)}/{M} "
          f"first@{loop_mism[0] if loop_mism else None}", flush=True)
    pure = worst < 1e-3 and not blk_mism and not loop_mism
    print("VERDICT:", "PURELY bf16 precision (fp32 is lossless; no logic bug)" if pure
          else "LOGIC BUG persists in fp32 (router-selection / rotating-cache / mask)",
          flush=True)


if __name__ == "__main__":
    main()
