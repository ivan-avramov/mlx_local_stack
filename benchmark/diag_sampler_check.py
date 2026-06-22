"""Disambiguate: is the suffix-loop divergence a sampler-mismatch artifact, or a real bug?

  seq_argmax  : sequential decode using mx.argmax
  seq_sampler : sequential decode using make_sampler(temp=0)  (what the loop uses)
  loop        : real suffix loop using make_sampler(temp=0)

  seq_argmax == seq_sampler ?  -> is make_sampler(temp=0) the same as argmax
  loop == seq_sampler ?        -> apples-to-apples: real loop (non-)losslessness
"""
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.models.cache import make_prompt_cache
from mlx_vlm.speculative.suffix_decoding import SuffixDecodingProposer, run_suffix_decoding_rounds
from mlx_lm.sample_utils import make_sampler
from bench.run_convergence import CODING_PROMPT

HF = "mlx-community/gemma-4-26b-a4b-it-8bit"
N = 140


def lg_of(o):
    return o.logits if hasattr(o, "logits") else o


def main():
    print(f"loading {HF} ...", flush=True)
    model, processor = load(HF)
    lm = model.language_model
    tok = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    ids = tok.encode(tok.apply_chat_template([{"role": "user", "content": CODING_PROMPT}],
                     add_generation_prompt=True, tokenize=False), add_special_tokens=False)
    input_ids = mx.array(ids)[None]
    sampler = make_sampler(temp=0.0)

    def seq(use_sampler):
        c = make_prompt_cache(lm)
        o = lm(input_ids, cache=c); lg = lg_of(o); mx.eval(lg)
        def pick(last):  # last: [1, V]
            return int(sampler(last).reshape(-1)[0].item()) if use_sampler else int(mx.argmax(last[0]).item())
        y = pick(lg[:, -1, :]); out = [y]
        for _ in range(N - 1):
            o = lm(mx.array([[y]]), cache=c); lg = lg_of(o); mx.eval(lg)
            y = pick(lg[:, -1, :]); out.append(y)
        return out

    seq_argmax = seq(False)
    seq_sampler = seq(True)

    # suffix loop with make_sampler; first token also via sampler for consistency
    c = make_prompt_cache(lm)
    o = lm(input_ids, cache=c); lg = lg_of(o); mx.eval(lg)
    first = int(sampler(lg[:, -1, :]).reshape(-1)[0].item())
    prop = SuffixDecodingProposer(min_match=2, max_match=8, cooldown=2)
    loop = [first]
    for _t, _ in run_suffix_decoding_rounds(model, prop, c, ids, first_bonus=first, max_tokens=N,
                                            sampler=sampler, draft_block_size=16,
                                            token_dtype=input_ids.dtype, thinking_budget_criteria=None):
        loop.append(int(_t))
        if len(loop) >= N:
            break

    def cmp(a, b):
        M = min(len(a), len(b)); m = [i for i in range(M) if a[i] != b[i]]
        return (m[0] if m else None), len(m), M

    fa, na, Ma = cmp(seq_argmax, seq_sampler)
    fl, nl, Ml = cmp(loop, seq_sampler)
    print(f"\nseq_argmax vs seq_sampler: first_mismatch={fa} num={na}/{Ma} "
          f"=> {'make_sampler==argmax' if fa is None else 'make_sampler != argmax (artifact source)'}", flush=True)
    print(f"loop vs seq_sampler (apples-to-apples): first_mismatch={fl} num={nl}/{Ml} "
          f"=> {'SUFFIX LOOP LOSSLESS' if fl is None else 'SUFFIX LOOP REALLY DIVERGES'}", flush=True)


if __name__ == "__main__":
    main()
