"""Is the KV difference a SUFFIX logic bug, or just multi-token vs single-token matmul
numerics (8-bit weights)?  No suffix decoding involved here.

  cache_single : prefill prompt, then process seq[0..K-1] ONE TOKEN AT A TIME.
  cache_multi  : process prompt+seq[0..K-1] in ONE multi-token forward.
  Compare full-attn KVCache layers' KV at the generated positions.

  differ ~0.01  => it's batched-vs-single matmul numerics (8-bit) — NOT suffix-specific;
                   suffix only inherits it (verify forwards are multi-token).
  identical     => multi==single; the suffix loop's corruption is a real logic bug.
"""
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.models.cache import make_prompt_cache, KVCache
from bench.run_convergence import CODING_PROMPT

HF = "mlx-community/gemma-4-26b-a4b-it-8bit"
K = 90


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

    # generate seq (single-token greedy) to get known tokens
    c0 = make_prompt_cache(lm)
    o = lm(input_ids, cache=c0); mx.eval(lg(o))
    y = int(mx.argmax(lg(o)[0, -1]).item()); seq = [y]
    for _ in range(K - 1):
        o = lm(mx.array([[y]]), cache=c0); mx.eval(lg(o))
        y = int(mx.argmax(lg(o)[0, -1]).item()); seq.append(y)

    # cache_single: prefill prompt, then feed seq[0..K-1] one at a time
    cs = make_prompt_cache(lm)
    lm(input_ids, cache=cs)
    for t in seq[:K]:
        lm(mx.array([[t]]), cache=cs)
    # cache_multi: one forward of prompt + seq[0..K-1]
    cm = make_prompt_cache(lm)
    lm(mx.array([ids + seq[:K]]), cache=cm)

    print(f"comparing PLAIN single-token vs multi-token KV, positions 0..{K-1} (full-attn):", flush=True)
    any_bad = False
    for li, (a, b) in enumerate(zip(cs, cm)):
        if not (isinstance(a, KVCache) and isinstance(b, KVCache)):
            continue
        ka = a.keys[..., P:P + K, :]; kb = b.keys[..., P:P + K, :]
        d = mx.max(mx.abs(ka - kb), axis=tuple(i for i in range(ka.ndim) if i != 2))
        mx.eval(d); dl = d.tolist()
        bad = [i for i, v in enumerate(dl) if v > 1e-2]
        mxd = max(dl)
        if bad:
            any_bad = True
            print(f"  layer {li}: maxdiff={mxd:.4f} #bad(>1e-2)={len(bad)} first@{bad[0]}", flush=True)
        else:
            print(f"  layer {li}: maxdiff={mxd:.5f} (clean)", flush=True)
    print("VERDICT:", "multi-vs-single matmul NUMERICS (8-bit) — not suffix-specific" if any_bad
          else "multi==single -> suffix loop corruption is a real LOGIC bug", flush=True)


if __name__ == "__main__":
    main()
