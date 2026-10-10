**S1 — Medium: the entry fence omits precomputed rotary work.**

At [language.py:1383]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1383), the non-fused rotary path constructs `position_embeddings`. The entry fence at [language.py:1395]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1395) evaluates `position_ids` but omits those cosine/sine arrays.

When `fused_apply=False`, their lazy computation therefore executes at the first attention preparation fence. Setup time is reported as `attn_prep`, contrary to Amendment 1.2. This does not affect the usual fused path, but the amendment is not satisfied across supported configurations.

**Fix:** include existing `position_embeddings` in the entry fence. Add a CPU test forcing the non-fused path and checking that cosine/sine evaluation completes before any layer mark.

**S2 — Medium: slicing the embeddings does not establish chunk-local evaluation.**

The full-prompt embedding graph is created at [ar.py:555]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:555), sliced at [ar.py:696]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:696), and evaluated through `h` at [language.py:1395]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1395). The actual text embedding producer consumes the complete input at [qwen3_5.py:77]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/qwen3_5.py:77).

Evaluating that slice still traverses the full embedding producer; a slice is not a guarantee that only its corresponding input tokens are computed. Vision embeddings can likewise depend on the complete vision/merge graph. Consequently, the first window’s `other` can contain preparation for subsequent windows.

This is an **Amendment 1.2 scope failure**, not proof of additional work relative to unprofiled production: production inherits the same dependency graph.

**Fix:** explicitly account for shared prompt preparation separately and obtain a corresponding specification amendment, or provide genuinely chunk-local producers. Do not claim slice-limited evaluation from the shape of the array passed to `mx.eval`. Add a dependency-sensitive test.

**S3 — Medium: EpiCache observation work crosses phase boundaries.**

The observation hook executes after `kv_update` and before the `sdpa` mark at [language.py:1016]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1016). However, [epicache.py:227]($HOME/ws/mlx-vlm/mlx_vlm/models/epicache.py:227) merely builds lazy `_scores`; evaluating the SDPA output does not evaluate those independent scores.

For an over-budget cache:

- Observation graph construction is charged to `sdpa`—or `other` for terminal attention.
- Observation computation runs through eviction under `cache_post`.
- Terminal query preparation can also move into `cache_post`, because queries were excluded from terminal `attn_prep`.

The claim at [prefill_profile.py:21]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:21) that `sdpa` includes observation is therefore false; the specification also requires `sdpa` to cover only attention.

**Fix:** give observation an explicit boundary, close it on its score arrays, and charge it consistently outside `sdpa`. Treat terminal queries as live when observation consumes them. Test an over-budget cache.

**S4 — Medium: the “lazy sentinel” test cannot detect evaluated dead computation.**

[Test line 397]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:397) records only the identities of arrays supplied directly to `mx.eval`. Assertions at [line 430]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:430) then check whether final logits and terminal layer outputs appear in that set.

Two concrete regressions can pass:

- Evaluating a transformation of a forbidden output evaluates its dependency without passing the original array directly.
- Evaluating terminal SDPA, `o_proj`, or GatedDeltaNet output before constructing the final terminal layer result leaves that final result absent from the set.

Thus Amendment 1.1’s execution sentinel is **only nominally covered**.

**Fix:** use execution-sensitive lazy sentinels on the forbidden intermediate computations, with positive controls proving they trigger when consumed. Separately assert that terminal KV updates and terminal recurrent/conv states are evaluated before their phase closes.

**S5 — Low: the disabled-mode “no output” assertion is ineffective.**

At [test_prefill_profile.py:233]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:233), `_err_lines(capsys)` is called twice. The first call drains stderr. If it contains an erroneous profiler line, the second call normally returns nothing and `not any(...)` passes.

**Consequence:** the test does not establish the specification’s no-reporting guarantee.

**Fix:** capture stderr once, then inspect the saved lines.

**S6 — Amendment 1 audit**

| Item | Branch-tip assessment |
|---|---|
| **1. Production graph only** | Ordinary terminal handling is structurally correct: terminal KV updates remain evaluated; terminal GatedDeltaNet closes on cache state while excluding `r`; dead SDPA/output/MLP marks become array-free fences. Execution proof is missing—S4—and EpiCache invalidates the unconditional “queries are dead” assumption—S3. |
| **2. Entry fence** | **Incomplete:** S1 and S2. |
| **3. State closure** | Implemented for GatedDeltaNet state, nonterminal array masks, and post-eviction cache state. Tests do not establish those closure boundaries. |
| **4. Request-local handle** | Implemented using thread-local storage and owner-checked clearing at [prefill_profile.py:123]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:123). No leak found in the present generation control flow: the model call has a `finally`, profiler failure clears the handle, and no generator yield occurs while it is published. |
| **5. Decoder-layer scope** | Guard implemented; foreign-layer reuse is exercised by a fake layer. |
| **6. Reports/finalization** | Window/remainder/total arithmetic is consistent. `keys` is the final cumulative offset, including the initial cache offset—not physical cache occupancy after eviction. Broken/aborted partial records avoid `final=1`; finalization surrounds the loop. |
| **7. CPU placement** | The fixture resets the lazy generation-stream cache and asserts CPU placement inside model calls. The authorized tests passed those assertions. |
| **8. Fork markers** | Changed upstream-file hunks carry or sit beneath `# Fork (M57)` markers. |

The inherited timer’s no-argument `mx.synchronize()` is **not a wrong-stream defect here**: [ar.py:544]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:544) establishes the generation stream as the current default stream/device, which is what synchronization uses.

I found no demonstrated switch-unset behavioral regression in the changed computation. That conclusion is from inspection; the tests do not exercise every requested path.

**S7 — Genuine versus nominal test coverage**

| Requirement | Actual coverage |
|---|---|
| Unset: zero synchronization, inactive handle, no reporting | Synchronization and handle assertions are real for the tiny generation path. No-reporting assertion is defective—S5. |
| Three chunks, fields, counts, nonnegative phases | Covered. Nonnegative `other` cannot validate accounting because implementation clamps it to zero. |
| Exact logits/cache equivalence | Compares sampled token, **log-probabilities**, and cache state after the final unchunked step; it does not compare raw logits or per-chunk states. Both terminal layer kinds are exercised. |
| Raising `mark` preserves generation | Covered for immediate and delayed failures, including broken partial reporting. |
| Handle cleared after success/exception | Covered, including an exception during the second model call. Generator close occurs after prefill has already finalized. |
| Window/remainder/total means | Covered with unequal synthetic durations and shortened window sizes. |
| Thread isolation and ownership | Covered, including overlapping generations. |
| Foreign attention reuse | Covered using a fake foreign layer. |
| Lazy terminal exclusion | Nominal only—S4. |
| Entry/state boundary correctness | Missing execution-sensitive tests for embeddings, rotary setup, masks, recurrent state and eviction. |

The suite also lacks switch-unset integration coverage for actual MTP verification, left-padded/batched execution, vision prompts, preallocated session-cache reuse, and snapshot/retention captures. Test-first development history cannot be established from these tests.

**S8 — Verdict: FIX-THEN-SHIP.**

The remaining blockers concern attribution and proving the evaluated graph. Passing counts and output-equivalence tests do not establish those properties.

Executed exactly:

```sh
cd ../mlx-vlm && TMPDIR=$TMPDIR PYTHONPATH=$PWD .venv/bin/python -m pytest mlx_vlm/tests/test_prefill_profile.py mlx_vlm/tests/test_mtp_profile.py -q -p no:cacheprovider
```

**Result: 34 passed, 2 warnings in 1.40s.** Reviewed tip: `aef10c6e`. No source changes, real model loads, servers, or GPU workloads.