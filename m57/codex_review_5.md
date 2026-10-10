**U1 — High: ragged prefill receives the policy.** Fork: [language.py:927]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:927), [language.py:1369]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1369). Left-padded prefill extracts individual rows and recursively calls the same model, retaining its stamped attention modules. A remaining row length ≥128 therefore forces SDPA. Excluding `_qwen3_5_left_padded_attention` only excludes that helper, not the ragged execution path. This violates AC5 and changes explicitly excluded numerics. **Fix:** propagate an explicit exclusion through row recursion; test an actual padded batch with eligible row lengths.

**U2 — High: unsupported execution contexts remain forceable.** Fork: [attention_policy.py:38]($HOME/ws/mlx-vlm/mlx_vlm/attention_policy.py:38), [attention_policy.py:161]($HOME/ws/mlx-vlm/mlx_vlm/attention_policy.py:161). CPU startup skips the kernel test but leaves the policy installed; a subsequent bf16, 128-query call forces a nonexistent CPU kernel. Likewise, `qL=128`, `key_length=64`, causal masking forces because neither mask nor device reaches the decision. I found no route producing that latter shape in the stated ordinary full-KV append flow, but the requested safety invariant is absent. **Fix:** reject unsupported serving devices before READY and enforce the causal-length invariant. The authoritative four-rule spec omits these eligibility constraints; resolve that contract explicitly.

**U3 — High: the missing HTTP counters are a worker serialization omission.** Fork: [schemas.py:489]($HOME/ws/mlx-vlm/mlx_vlm/server/schemas.py:489), [openai.py:3009]($HOME/ws/mlx-vlm/mlx_vlm/server/openai.py:3009). The precise path is:

- `_process_cached_request` snapshots at `generation.py:1715` and populates the final token at `:1869`.
- `GenerationMetrics.record_chunk()` transfers them through `record_result()`.
- `_build_metrics_envelope()` receives them at `openai.py:3041`, but that envelope goes to internal metrics.
- The returned response uses `GenerationTimings.from_metrics()`, whose schema and constructor omit both counters.
- Router [router.py:567]($HOME/ws/mlx-serve/src/mlx_serve/router.py:567) forwards the JSON unchanged.

They are **not streaming-only**; `StreamingTimings` also lacks them. **Fix:** add conditional response serialization preserving absence under `auto`, then test the complete cached-request HTTP response. The existing “timings envelope” test exercises the wrong object.

**U4 — High: unknown provenance permits mixed-policy pooling and comparison.** Stack: [provenance.py:596]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/provenance.py:596), [compare.py:311]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/compare.py:311). A missing registry model becomes `unknown`; runtime compatibility treats that as a wildcard against `fused_v1`, and comparison merely warns. A malformed v7 manifest missing the key has the same weakness. Representing ignorance as `unknown` is more accurate than inventing `auto`, but authorizing pooling from it defeats the new provenance boundary. **Fix:** refuse new runs, resumes and comparisons with unresolved v7 policy; preserve existing artifacts without pooling or deleting them.

**U5 — High: v1 manifests bypass pre-v7 normalization.** Stack: [provenance.py:411]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/provenance.py:411). `is_compatible()` returns for negotiated version 1 before injecting normalized policy. Otherwise matching v1 and v7/fused manifests therefore compare compatible. Tests cover versions 5/6, not this branch. **Fix:** compare normalized policy before that return. Version-gating the fingerprint key is viable, but the existing `_FINGERPRINT_RUNTIME` classification tests cannot see it; audit the actual versioned fingerprint keys.

**U6 — Medium: the A/B tool relaxes the requirement for known predictor state.** Stack: [compare_predictor.py:108]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/compare_predictor.py:108), [compare_predictor.py:180]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/compare_predictor.py:180). With `must_differ="attention_policy"`, two missing—or two `unknown`—`draft_kind` values pass equality. Previously missing predictor state was refused. Such a comparison cannot establish that only attention changed. **Fix:** require both selectable controls to be known, then enforce exactly one differing control. Existing sampling, KV, code and timeout checks otherwise remain in place.

**U7 — Medium: lazy-embedding acceptance is materially under-tested.** Fork: [test_lazy_embeddings.py:94]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_lazy_embeddings.py:94). Every helper run creates a fresh cache. There are no MTP capture, warm-offset, snapshot-landing or retention-boundary comparisons. The purported logits test compares **log probabilities**, and cache inspection occurs after the generator’s lookahead decode step, not at prompt end. The multimodal test substitutes text embeddings rather than merging image features.

I found no concrete skipped or duplicated token in the slicing logic: IDs and lazy suffix advance by the same adjusted chunk length; the remainder is materialized before `_step`; text position metadata follows the eager helper. That does not establish all requested flows. **Fix:** compare raw logits, prompt-end cache arrays and offset metadata, speculative captures, and real multimodal merging against the eager path across those boundaries.

**U8 — Medium: the self-test has no enforceable 30-second deadline.** Fork: [attention_policy.py:185]($HOME/ws/mlx-vlm/mlx_vlm/attention_policy.py:185). Elapsed time is checked only after all synchronous evaluations return. A stalled evaluation prevents both failure and READY indefinitely. **Fix:** enforce a worker startup deadline with termination on expiry. At the specified bf16 head counts and 4096 keys, only lengths 128/512 actually execute forced calls; 9/127 are skipped by the rule. Ordinary raised startup errors do propagate through `wait_until_ready`, lifespan and Uvicorn’s nonzero startup exit, but AC6’s test stops at `_initialize_model`.

**U9 — Medium: worker attribution is not model-specific.** Stack: [provenance.py:580]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/provenance.py:580). The reused lookup returns the first process containing `mlx_vlm.server`; the new resolver then substring-matches `hf_path`. An unrelated worker encountered first hides the relevant worker’s disagreement; overlapping model paths can misattribute it. **Fix:** inspect all candidate argv arrays and match the exact `--model` argument and serving worker identity.

Coverage below describes **test substance, not successful execution**.

| AC | Coverage |
|---|---|
| AC1 | Genuinely covered: native keyword assertions and router golden argv. Broader evaluation/lifetime preservation unverified. |
| AC2 | Genuinely covered: specified mocked decision grid; eligibility gaps remain in U2. |
| AC3 | Nominal: component plumbing tested; returned HTTP timings missing. |
| AC4 | Nominal: dispatch spies; required existing quantized suites not verified. |
| AC5 | Nominal: source inspection misses ragged recursion. |
| AC6 | Nominal: exceptions tested; process exit/deadline not exercised. |
| AC7 | Genuinely covered: instance separation and post-load environment mutation. |
| AC8 | Genuinely covered: verifier spy and CPU equality design for blocks 2/3. |
| AC9 | Genuinely covered: default formula, policy formula and explicit override. |
| AC10 | Nominal; production cache/speculative flows missing, U7. |
| AC11 | Nominal: normal cases tested; wildcard behavior enshrined, v1 bypass missed. |

Both supplied test commands initially failed because the read-only sandbox provided no writable temporary directory. Retrying the fork with in-memory capture aborted during MLX import (`duplicate key "cpu"`), before tests executed. No test pass is claimed; collection failures do not establish a meaningful TDD red phase. No files were modified, models loaded, servers started or GPU workloads run.

**Verdicts:** fork **FIX-THEN-SHIP**; router **SHIP**; stack **FIX-THEN-SHIP**. Router validation escapes the former early return, and unset/`auto` command construction remains unchanged by inspection.

