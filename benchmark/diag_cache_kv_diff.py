"""Direct KV-level pinpoint: which committed token's cached KV does the suffix loop
corrupt, vs a plain reference holding the same tokens?

Compares only the full-attention KVCache layers (strictly linear layout -> reliable
position alignment). The first position whose KV differs identifies the corrupted token.
"""
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.models.cache import make_prompt_cache, KVCache
from mlx_vlm.speculative.suffix_decoding import SuffixDecodingProposer, run_suffix_decoding_rounds
from mlx_lm.sample_utils import make_sampler
from bench.run_convergence import CODING_PROMPT

HF = "mlx-community/gemma-4-26b-a4b-it-8bit"
N = 120


def lg(o):
    return o.logits if hasattr(o, "logits") else o


def main():
    print(f"loading {HF} ...", flush=True)
    model, processor = load(HF)
    lm = model.language_model
    tok = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    ids = tok.encode(tok.apply_chat_template([{"role": "user", "content": CODING_PROMPT}],
                     add_generation_prompt=True, tokenize=False), add_special_tokens=False)
    input_ids = mx.array(ids)[None]
    P = len(ids)
    sampler = make_sampler(temp=0.0)

    # plain seq
    cp = make_prompt_cache(lm)
    o = lm(input_ids, cache=cp); mx.eval(lg(o))
    y = int(mx.argmax(lg(o)[0, -1]).item()); seq = [y]
    for _ in range(N - 1):
        o = lm(mx.array([[y]]), cache=cp); mx.eval(lg(o))
        y = int(mx.argmax(lg(o)[0, -1]).item()); seq.append(y)

    # suffix loop, capture its final cache (cl)
    cl = make_prompt_cache(lm)
    o = lm(input_ids, cache=cl); mx.eval(lg(o))
    first = int(mx.argmax(lg(o)[0, -1]).item())
    prop = SuffixDecodingProposer(min_match=2, max_match=8, cooldown=2)
    loop = [first]
    for _t, _ in run_suffix_decoding_rounds(model, prop, cl, ids, first_bonus=first, max_tokens=N,
                                            sampler=sampler, draft_block_size=16,
                                            token_dtype=input_ids.dtype, thinking_budget_criteria=None):
        loop.append(int(_t))
        if len(loop) >= N:
            break
    fm = next((i for i in range(min(len(loop), len(seq))) if loop[i] != seq[i]), None)
    print(f"token first_mismatch={fm}", flush=True)
    if fm is None:
        print("loop matched seq -> no divergence in this run"); return
    K = fm  # committed tokens 0..K-1 are identical between loop and seq

    # reference cache holding prompt + seq[0..K-1]
    ref = make_prompt_cache(lm)
    lm(mx.array([ids + seq[:K]]), cache=ref);
    # compare full-attention KVCache layers' KV at positions P..P+K
    print(f"comparing committed KV for positions 0..{K-1} (full-attn KVCache layers):", flush=True)
    found = False
    for li, (a, b) in enumerate(zip(cl, ref)):
        if not (isinstance(a, KVCache) and isinstance(b, KVCache)):
            continue
        ka = a.keys[..., P:P + K, :]; kb = b.keys[..., P:P + K, :]
        d = mx.max(mx.abs(ka - kb), axis=tuple(i for i in range(ka.ndim) if i != 2))  # per-pos
        mx.eval(d); dl = d.tolist()
        bad = [i for i, v in enumerate(dl) if v > 1e-2]
        if bad:
            found = True
            print(f"  layer {li}: first corrupted KV at committed pos {bad[0]} "
                  f"(token={seq[bad[0]]}) maxdiff={dl[bad[0]]:.4f}  (#bad={len(bad)})", flush=True)
    if not found:
        print("  no KV diff > 1e-2 in full-attn layers -> corruption is in sliding/rotating layers "
              "(or sub-threshold accumulation)", flush=True)


if __name__ == "__main__":
    main()
