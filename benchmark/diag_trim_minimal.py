"""Definitive, real-cache test of 'block + trim + continue' (no monkeypatching).

  ref  : sequential single-token greedy decode, N tokens.
  test : prefill; ONE multi-token forward of [seq[0..15], W1, W2] (2 bogus trailing
         tokens); trim(2) to drop W1,W2; then continue single-token from seq[16].
         Compare continuation to ref.

  diverges => trim genuinely corrupts the kept cache region (the bug).
  matches  => trim is fine; the loop bug is elsewhere (proposer / miss-after-verify).
"""
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.models.cache import make_prompt_cache
from bench.run_convergence import CODING_PROMPT

HF = "mlx-community/gemma-4-26b-a4b-it-8bit"
N = 60
B = 16


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

    c = make_prompt_cache(lm)
    o = lm(input_ids, cache=c); mx.eval(lg(o))
    y = int(mx.argmax(lg(o)[0, -1]).item()); ref = [y]
    for _ in range(N - 1):
        o = lm(mx.array([[y]]), cache=c); mx.eval(lg(o))
        y = int(mx.argmax(lg(o)[0, -1]).item()); ref.append(y)

    # test: prefill, block [ref[0..B-1], W1, W2], trim 2, continue from ref[B]
    c2 = make_prompt_cache(lm)
    o = lm(input_ids, cache=c2); mx.eval(lg(o))
    W1, W2 = ref[30], ref[31]  # arbitrary bogus trailing tokens (will be trimmed)
    block = mx.array(ref[:B] + [W1, W2])[None]
    ob = lm(block, cache=c2); mx.eval(lg(ob))
    pre = [cc.offset for cc in c2 if cc is not None]
    for cc in c2:
        if cc is not None and hasattr(cc, "trim"):
            cc.trim(2)
    post = [cc.offset for cc in c2 if cc is not None]
    print(f"offsets after block: {pre[:3]}... after trim(2): {post[:3]}...", flush=True)

    got = list(ref[:B])
    y = ref[B]  # the bonus (prediction after ref[0..B-1]) == ref[B]
    got.append(y)
    for _ in range(N - B - 1):
        o = lm(mx.array([[y]]), cache=c2); mx.eval(lg(o))
        y = int(mx.argmax(lg(o)[0, -1]).item()); got.append(y)

    M = min(len(ref), len(got))
    mism = [i for i in range(M) if ref[i] != got[i]]
    print(f"\nblock+trim(2)+continue vs ref: first_mismatch={mism[0] if mism else None} num={len(mism)}/{M}", flush=True)
    print("VERDICT:", "TRIM corrupts kept cache region (the bug)" if mism
          else "trim is FINE -> loop bug is elsewhere (proposer/miss interaction)", flush=True)


if __name__ == "__main__":
    main()
