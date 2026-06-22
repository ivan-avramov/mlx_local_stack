"""Validate the suffix-decode rollback fix hypothesis BEFORE touching the fork.

Bug: RotatingKVCache.trim (sliding-window layers) only decrements offset/_idx pointers,
leaving keys/values arrays at full length -> after a speculative rollback, the array length
disagrees with _idx/offset, and the next update corrupts the rotating layout -> drift.

A/B (gemma-8bit, fp16, temp0, N=140), each suffix loop vs the sequential reference:
  (baseline)  default RotatingKVCache.trim                  -> expect DIVERGE (~token 89)
  (control)   all layers use KVCache (no rotation)          -> expect LOSSLESS (proves it's rotating)
  (fix)       RotatingKVCache.trim also truncates arrays    -> expect LOSSLESS (proves the fix)
"""
import mlx.core as mx
import mlx_vlm.models.cache as vcache
from mlx_vlm import load
from mlx_vlm.models.cache import make_prompt_cache, KVCache, RotatingKVCache
from mlx_vlm.speculative.suffix_decoding import SuffixDecodingProposer, run_suffix_decoding_rounds
from mlx_lm.sample_utils import make_sampler
from bench.run_convergence import CODING_PROMPT

HF = "mlx-community/gemma-4-26b-a4b-it-8bit"
N = 140


def logits_of(o):
    return o.logits if hasattr(o, "logits") else o


def sequential(lm, input_ids):
    c = make_prompt_cache(lm)
    o = lm(input_ids, cache=c); lg = logits_of(o); mx.eval(lg)
    y = int(mx.argmax(lg[0, -1]).item()); seq = [y]
    for _ in range(N - 1):
        o = lm(mx.array([[y]]), cache=c); lg = logits_of(o); mx.eval(lg)
        y = int(mx.argmax(lg[0, -1]).item()); seq.append(y)
    return seq


def suffix_loop(model, lm, input_ids, ids, cache):
    o = lm(input_ids, cache=cache); lg = logits_of(o); mx.eval(lg)
    first = int(mx.argmax(lg[0, -1]).item())
    sampler = make_sampler(temp=0.0)
    proposer = SuffixDecodingProposer(min_match=2, max_match=8, cooldown=2)
    spec = [first]
    for _t, _ in run_suffix_decoding_rounds(
        model, proposer, cache, ids, first_bonus=first, max_tokens=N,
        sampler=sampler, draft_block_size=16, token_dtype=input_ids.dtype,
        thinking_budget_criteria=None,
    ):
        spec.append(int(_t))
        if len(spec) >= N:
            break
    return spec


def report(label, spec, seq):
    M = min(len(spec), len(seq))
    mism = [i for i in range(M) if spec[i] != seq[i]]
    print(f"[{label}] len={len(spec)} first_mismatch={mism[0] if mism else None} "
          f"num_mismatch={len(mism)}/{M}  => {'LOSSLESS' if not mism else 'DIVERGES'}", flush=True)
    return not mism


def main():
    print(f"loading {HF} ...", flush=True)
    model, processor = load(HF)
    lm = model.language_model
    tok = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    prompt = tok.apply_chat_template([{"role": "user", "content": CODING_PROMPT}],
                                     add_generation_prompt=True, tokenize=False)
    ids = tok.encode(prompt, add_special_tokens=False)
    input_ids = mx.array(ids)[None]

    seq = sequential(lm, input_ids)

    # baseline (default rotating trim)
    report("baseline default-trim", suffix_loop(model, lm, input_ids, ids, make_prompt_cache(lm)), seq)

    # control: all KVCache (no rotation)
    orig_make = type(lm).make_cache
    n_layers = len(lm.layers) if hasattr(lm, "layers") else len(lm.model.layers)
    all_kv = [KVCache() for _ in range(len(make_prompt_cache(lm)))]
    report("control all-KVCache", suffix_loop(model, lm, input_ids, ids, all_kv), seq)

    # fix: monkeypatch RotatingKVCache.trim to also truncate arrays (pre-wrap temporal order)
    orig_trim = RotatingKVCache.trim

    def fixed_trim(self, n):
        n = min(self.offset, n)
        self.offset -= n
        self._idx -= n
        if self.keys is not None and 0 <= self._idx <= self.keys.shape[2]:
            self.keys = self.keys[..., : self._idx, :]
            self.values = self.values[..., : self._idx, :]
        return n

    RotatingKVCache.trim = fixed_trim
    try:
        report("FIX truncate-trim", suffix_loop(model, lm, input_ids, ids, make_prompt_cache(lm)), seq)
    finally:
        RotatingKVCache.trim = orig_trim


if __name__ == "__main__":
    main()
