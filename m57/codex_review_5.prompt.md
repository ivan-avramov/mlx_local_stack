Cold adversarial CODE review of a three-repo change. Read-only: modify nothing, load no real models, run no Metal/GPU workload and
no servers. You may run the CPU test commands given at the end.

SPEC (authoritative): docs/specs/m57-attention-policy.md in this repo (policy `fused_v1`, sections Fork / Router / Stack,
acceptance criteria AC1-AC12). Background and measurements: docs/proposal-flash-attention.md (E1-E15).

UNDER REVIEW
1. Fork ../mlx-vlm, branch `m57-attention-policy`: commits 7619beb3 (policy) and c1504381 (lazy per-chunk prompt embeddings) on top
   of 21d62fe6 (an already-reviewed profiler branch — out of scope). `git -C ../mlx-vlm diff 21d62fe6 m57-attention-policy`.
2. Router ../mlx-serve, branch `m57-attention-policy`, commit 30be27c. `git -C ../mlx-serve diff main m57-attention-policy`.
3. Stack (this repo), worktree branch `worktree-agent-a6011ca833d3e6e68`, commit ddd278f (fingerprint v7).
   `git diff 4f2663e ddd278f -- benchmark/`.

This serves a production model (27B qwen3_5 hybrid, native bf16 KV cache preallocated to 262144 tokens, MTP speculative decoding
with a separate verifier, session caches with prompt-end retention/snapshot captures, chunked prefill at 512 tokens). MLX 0.32.2:
`force_fused=True` RAISES when no fused kernel exists (query lengths 6-8 at this model's 24 query / 4 KV heads; any CPU stream).

A LIVE SMOKE on the real server already ran (router + worker from these branches, registry `attention_policy: fused_v1`): the worker
received `--attention-policy fused_v1`, logged `attention_policy=fused_v1`, and 20 requests with varied tail lengths and short
cached continuations returned 200. BUT the `sdpa_forced` / `sdpa_auto` counters were ABSENT from the `timings` object of every
non-streaming /v1/chat/completions response (session-cache backend), so there is currently NO positive evidence that any call was
forced. Find out why (worker envelope not populated on that path? router rebuilding `timings`? counters only on streaming?) and
say exactly where.

WHAT MATTERS, most important first
(A) Default inertness: with the policy absent/`auto` every path is byte-identical to before — MLX call keywords, evaluation order,
    object lifetimes, the worker command line, the lazy-embedding change for prompts it does not apply to.
(B) Correctness of `fused_v1`: the decision rule exactly as specified; never forces a call that can raise in production (query
    lengths 1-8; qL > key length with a causal mask; float32; sinks; non-native caches); reaches ONLY `Qwen3_5Attention.__call__`;
    the verifier, left-padded/ragged batch paths, vision towers and other families (including qwen3_5_moe / qwen4_exp which reuse
    the attention class) never see it; resolved once per model instance, no env read on the hot path, no cross-instance leak.
(C) The lazy-embedding commit is the riskiest piece: is the cache state really identical to the eager path in ALL the flows the
    chunk loop supports — MTP/speculative prefill captures, snapshot landing and prompt-end retention (chunk sizes shrink to land on
    offsets), checkpoint lengths, a warm session cache with an initial offset, the final single-token `_step`, prompts with image
    features (must take the old path), embedding scaling/positions that depend on absolute offsets? Any path where the embedding of
    a token could differ, be skipped, or be computed twice?
(D) Loud failure and self-test: is "exit nonzero before READY" real end to end? Does the self-test exercise what the policy forces at
    the real head counts / dtype, within its time bound, and is it skipped safely off-GPU?
(E) Router: validation cannot be bypassed by the existing early return; command line identical when unset.
(F) Stack provenance: v7 resolution and source, the worker/registry mismatch refusal, pre-v7 normalisation in `is_compatible`,
    `compare.py` refusal, the parametrised must-differ rule in `compare_predictor.py` (no other rule relaxed). Three implementer
    choices to judge: a model missing from the registry reads as `unknown` (wildcard) rather than `auto`; `compare.py` WARNS instead
    of refusing when a v7 row's policy was not observed; the key is version-gated rather than added to `_FINGERPRINT_RUNTIME`.
(G) Tests that pass without exercising their claim (the fork implementer saw all new tests fail only at collection).

DELIVER (markdown, ids U1, U2, ... most severe first, each with repo + file:line): what is wrong, concrete scenario, consequence,
fix. Then a table AC1-AC11 → genuinely covered / nominal / missing. Verdict per repo: SHIP / FIX-THEN-SHIP / REWORK. Under 1400 words.
No praise.

TESTS (optional): fork `cd ../mlx-vlm && TMPDIR=$TMPDIR PYTHONPATH=$PWD .venv/bin/python -m pytest mlx_vlm/tests/test_attention_policy.py mlx_vlm/tests/test_lazy_embeddings.py -q -p no:cacheprovider`;
router `cd ../mlx-serve && TMPDIR=$TMPDIR .venv/bin/python -m pytest tests -q`.
