"""Diagnostic: is the suffix-decode VERIFY block-forward lossless vs sequential decode?

Loads the model directly (no server). Greedy-decodes N tokens sequentially, then runs ONE
clean block forward over the same tokens (the verify-style multi-position-with-cache pass,
WITHOUT any rollback) and compares per-position argmax.

  pos 0 is a fidelity self-check — it MUST match (same computation as sequential's 1st step).
  first mismatch at i>0  => the block forward itself is non-lossless (H-A: mask/RoPE/MoE).
  all match              => forward is lossless => the bug is rollback_speculative_cache (H-B).

Run AFTER unloading the server's copy (this loads its own ~26GB).
  cd benchmark && PYTHONPATH=. ../.venv/bin/python diag_verify_forward.py <hf_path>
"""
import sys
import mlx.core as mx
from mlx_vlm import load
from mlx_vlm.models.cache import make_prompt_cache
from mlx_vlm.speculative.suffix_decoding import (
    SuffixDecodingProposer, run_suffix_decoding_rounds,
)
from mlx_lm.sample_utils import make_sampler
from bench.run_convergence import CODING_PROMPT

HF = sys.argv[1] if len(sys.argv) > 1 else "mlx-community/gemma-4-26b-a4b-it-8bit"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 140


def logits_of(o):
    return o.logits if hasattr(o, "logits") else o


def main():
    print(f"loading {HF} ...", flush=True)
    model, processor = load(HF)
    lm = model.language_model
    tok = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    prompt = tok.apply_chat_template(
        [{"role": "user", "content": CODING_PROMPT}],
        add_generation_prompt=True, tokenize=False,
    )
    ids = tok.encode(prompt, add_special_tokens=False)
    input_ids = mx.array(ids)[None]
    print(f"prompt tokens={input_ids.shape[1]} ; decoding {N} greedy tokens sequentially...", flush=True)

    # --- sequential greedy decode ---
    cseq = make_prompt_cache(lm)
    o = lm(input_ids, cache=cseq); lg = logits_of(o); mx.eval(lg)
    y = int(mx.argmax(lg[0, -1]).item()); seq = [y]
    for _ in range(N - 1):
        o = lm(mx.array([[y]]), cache=cseq); lg = logits_of(o); mx.eval(lg)
        y = int(mx.argmax(lg[0, -1]).item()); seq.append(y)

    # --- one clean block forward (verify-style, no rollback) ---
    cblk = make_prompt_cache(lm)
    o0 = lm(input_ids, cache=cblk); mx.eval(logits_of(o0))
    blk_in = mx.array(seq)[None]
    ob = lm(blk_in, cache=cblk); lgb = logits_of(ob); mx.eval(lgb)
    blk = [int(x) for x in mx.argmax(lgb[0], axis=-1).tolist()]  # blk[i] = pred after prefix+seq[0..i]

    # blk[i] should equal seq[i+1] for i in 0..N-2
    mism = [i for i in range(N - 1) if blk[i] != seq[i + 1]]
    pos0_ok = (blk[0] == seq[1])
    print(f"\nRESULT: N={N} pos0_selfcheck={'MATCH' if pos0_ok else 'FAIL(harness infidelity)'} "
          f"first_mismatch={mism[0] if mism else None} num_mismatch={len(mism)}/{N-1}", flush=True)
    if mism:
        i = mism[0]
        print(f"  first divergence at block position {i}: block argmax={blk[i]} "
              f"({tok.decode([blk[i]])!r}) vs sequential={seq[i+1]} ({tok.decode([seq[i+1]])!r})", flush=True)
    print("forward-only verdict:", "block-forward NON-LOSSLESS (H-A)" if (pos0_ok and mism)
          else ("forward lossless" if pos0_ok else "HARNESS INFIDELITY - ignore"),
          flush=True)

    # --- REAL suffix loop (with rollback), fp16 KV: lossless vs sequential? ---
    # fp16-loop lossless  => the bug is the quantized-KV x speculative interaction.
    # fp16-loop diverges  => the bug is rollback_speculative_cache (H-B), quant-independent.
    print("\nrunning REAL suffix loop (fp16 KV, real sampler) ...", flush=True)
    cspec = make_prompt_cache(lm)
    osp = lm(input_ids, cache=cspec); lgs = logits_of(osp); mx.eval(lgs)
    first = int(mx.argmax(lgs[0, -1]).item())
    sampler = make_sampler(temp=0.0)  # real greedy sampler (argmax)
    proposer = SuffixDecodingProposer(min_match=2, max_match=8, cooldown=2)
    spec = [first]
    for _t, _ in run_suffix_decoding_rounds(
        model, proposer, cspec, ids, first_bonus=first, max_tokens=N,
        sampler=sampler, draft_block_size=16, token_dtype=input_ids.dtype,
        thinking_budget_criteria=None,
    ):
        spec.append(int(_t))
        if len(spec) >= N:
            break
    M = min(len(spec), len(seq))
    sp_mism = [i for i in range(M) if spec[i] != seq[i]]
    print(f"SUFFIX-LOOP (fp16): len(spec)={len(spec)} len(seq)={len(seq)} "
          f"first_mismatch={sp_mism[0] if sp_mism else None} num_mismatch={len(sp_mism)}/{M}", flush=True)
    if sp_mism:
        i = sp_mism[0]
        print(f"  first loop divergence at token {i}: suffix={spec[i]} ({tok.decode([spec[i]])!r}) "
              f"vs sequential={seq[i]} ({tok.decode([seq[i]])!r})", flush=True)
    print("FINAL VERDICT:",
          "ROLLBACK is the bug (H-B) — fp16 suffix loop diverges from sequential" if sp_mism
          else "fp16 suffix loop LOSSLESS -> bug is QUANTIZED-KV x speculative interaction",
          flush=True)


if __name__ == "__main__":
    main()
