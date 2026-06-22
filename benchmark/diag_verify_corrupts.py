"""Isolate: does a MULTI-TOKEN forward (the verify block) corrupt the cache for
subsequent SINGLE-TOKEN decode — independent of trim/accept?

  ref           : sequential single-token greedy decode, N tokens
  blockthencont : prefill, do ONE multi-token forward of seq[0:B] (the verify block,
                  ALL tokens correct so no trim needed), then continue single-token
                  decode for the rest. Compare to ref.

  diverges => the multi-token cache update leaves a state inconsistent with single-token
              decode (root cause of suffix non-losslessness; trim is innocent).
  matches  => multi-token update is fine; the bug is specifically the trim/rollback.
"""
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.models.cache import make_prompt_cache
from bench.run_convergence import CODING_PROMPT

HF = "mlx-community/gemma-4-26b-a4b-it-8bit"
N = 60
B = 16  # block size for the one multi-token forward


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

    # reference: sequential single-token
    c = make_prompt_cache(lm)
    o = lm(input_ids, cache=c); mx.eval(lg(o))
    y = int(mx.argmax(lg(o)[0, -1]).item()); ref = [y]
    for _ in range(N - 1):
        o = lm(mx.array([[y]]), cache=c); mx.eval(lg(o))
        y = int(mx.argmax(lg(o)[0, -1]).item()); ref.append(y)

    # blockthencont: prefill, ONE multi-token forward of ref[0:B], then single-token continue
    c2 = make_prompt_cache(lm)
    o = lm(input_ids, cache=c2); mx.eval(lg(o))   # prefill; predicts ref[0]
    block = mx.array(ref[:B])[None]                # ref[0..B-1] as one block
    ob = lm(block, cache=c2); mx.eval(lg(ob))       # multi-token forward
    got = ref[:B]                                   # these are by construction == ref
    y = int(mx.argmax(lg(ob)[0, -1]).item())        # prediction after ref[0..B-1] => should be ref[B]
    got.append(y)
    for _ in range(N - B - 1):
        o = lm(mx.array([[y]]), cache=c2); mx.eval(lg(o))
        y = int(mx.argmax(lg(o)[0, -1]).item()); got.append(y)

    M = min(len(ref), len(got))
    mism = [i for i in range(M) if ref[i] != got[i]]
    print(f"\nblockthencont vs ref: B={B} N={N} first_mismatch={mism[0] if mism else None} "
          f"num={len(mism)}/{M}", flush=True)
    print("VERDICT:", "MULTI-TOKEN forward corrupts subsequent decode (trim innocent)" if mism
          else "multi-token forward is fine -> bug is specifically the TRIM/rollback", flush=True)
    if mism:
        i = mism[0]
        print(f"  first divergence at index {i} (block ends at {B-1}): got={got[i]} ref={ref[i]}", flush=True)


if __name__ == "__main__":
    main()
