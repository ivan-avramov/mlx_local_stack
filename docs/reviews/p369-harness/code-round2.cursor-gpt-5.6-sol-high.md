# P369 phase-2 harness — Cursor gpt-5.6-sol-high CODE review round 2 (fork `p369-mtp` `c10205ae..dec95d95`, 2026-10-19)

Prompt: `code-round2.prompt-head.md` + the round-1 output + `git diff c10205ae..dec95d95` + plan v7; workspace `../mlx-vlm` at `24551869`. Attempt 1 printed nothing; attempt 2 verbatim (its trailing "No further action needed…" is tool noise after the VERDICT):

Verified: `4e6d0e03..dec95d95` has no production diff. Changes are confined to the declared harness and tests. No committed home paths or usernames found. Read-only review; tests were not run.

P2 — H1 — RESOLVED  
`observe.py:56-77,115-134` hashes effective `ArraysCache` masking metadata and TurboQuant mode, codec type, bits, and snapshot coordinates. `ArraysCache.metadata_revision` is deliberately excluded, and active deployed recurrent transactions are rejected. The deployed picks do not use the other speculative pooling-cache classes.

P3 — H2 — PARTIALLY RESOLVED — BLOCKER  
`telemetry.py:285-301` derives expected families per module but does not model the production tuple predicate at `quantized_verifier.py:1790-1807`. It permits both `quantized_linears_optimized` and per-module `quantized_affine_optimized` whenever each module is individually eligible.

Scenario: `_target_verify_quantized_linears` declines for an otherwise tuple-eligible group, but each nested projection succeeds through `quantized_affine_optimized`. `telemetry.py:383-389` accepts every attribution and the run passes without establishing the expected fused tuple family. The regression test at `test_p369_phase2_telemetry.py:286-294` misses this because it disables both tuple and individual optimized kernels.

Fix: make the manifest call-site/group-aware and require `quantized_linears_optimized` for tuple-compatible groups; add a tuple-only-decline test.

P4 — H3 — RESOLVED  
`orchestrate.py:38-59,127-140` constructs an explicit allowlisted environment and adds only `MLX_VLM_CACHE_SESSION_MAX=1`. The argv, including generation defaults, is recorded per pick.

P5 — H4 — RESOLVED  
`worker.py:709-740,942-951` requires both OFF replay offset sets to equal the ON offset list before C1 can pass. A common replay recorder omission now produces C1 ABORT rather than E1c non-neutrality.

P6 — H5 — RESOLVED  
`orchestrate.py:314-339` excludes zero-round requests from E7a’s denominator, while preserving first-token M4b exposure as the documented special case. Censored and non-engaged requests are disclosed separately.

P7 — H6 — PARTIALLY RESOLVED — HIGH  
Prompt IDs are correctly digested at `worker.py:147-160,182-186,405-428`, and E2 digest mismatches make E2 incomplete through `orchestrate.py:1152-1168`. E7 mismatches, however, are only recorded at `orchestrate.py:1192-1197,1226-1231`; they do not invalidate E7 or overall PASS.

Scenario: ON templating drifts from the count reconstruction. E7 measures a different corpus, records `prompt_digest_problems`, yet `overall_status()` still returns PASS.

Fix: mark affected E7 requests invalid/censored and make unresolved digest mismatches prevent overall phase PASS.

P8 — H7 — RESOLVED  
`worker.py:321-380,991-1040` echoes content, reasoning content, and tool calls; snapshots the explicit session’s cached token sequence and current request hash chain; requires the new prompt to reproduce the complete cached sequence; and requires reuse through `boundary - 1`. This matches the stated explicit-session design; production’s unused assistant-hash helper is not required for it.

P9 — H8 — PARTIALLY RESOLVED — MEDIUM  
The separate supervisor now enforces boot, request, job, and optional wall deadlines at `orchestrate.py:599-642`. Two residual defects remain:

- `worker.py:1042-1059` writes `phase="after"` only after session release, telemetry, and artifact creation. A cleanup hang is therefore misclassified as a request timeout and E7 censors a completed request.
- `orchestrate.py:638-641` writes `timeout.json` after terminating the worker, contrary to the requested durable-before-kill ordering.

Fix: switch to the after phase immediately after request completion and atomically write the timeout decision before signalling the worker.

P10 — H9 — PARTIALLY RESOLVED — HIGH  
The current binding remains self-referential and incomplete:

- `orchestrate.py:887-915` records the current `HEAD` and harness tree but never compares them with the reviewed `dec95d95` commit/tree.
- Cleanliness is checked once at `orchestrate.py:461-485`; later workers import mutable worktree files at `orchestrate.py:680-690`.
- `binding()` at `orchestrate.py:200-240` omits dependency versions, retained environment values, and the stack/benchmark revision.
- Worker environments may use `HF_HUB_CACHE` or `HUGGINGFACE_HUB_CACHE` (`orchestrate.py:48-53`), while `weights_record()` hashes only `HF_HOME/hub` (`orchestrate.py:765-777`).

Scenario: a committed but unreviewed harness, a mid-campaign edit, a changed MLX build, or an alternate Hugging Face cache runs while the manifest still claims an acceptable smoke/full binding or attests different weights.

Fix: pin the reviewed commit/tree and test hashes; execute an immutable checkout/archive; bind versions, retained environment, stack/benchmark revisions, and reconstruction data; attest the actual worker-resolved model snapshots.

P11 — H10 — PARTIALLY RESOLVED — HIGH  
E2 now has an explicit verdict at `orchestrate.py:300-308,1157-1168`. However, `overall_status()` at `orchestrate.py:375-388` considers only E1c and E2.

Scenario: all E7 requests are censored or unengaged, E7b has no MTP rounds, or E7 prompt digests fail, yet the run exits zero with status `PASS`.

Fix: add explicit E7 coverage/binding statuses and require them for overall phase PASS, or name the current result narrowly as `E1C_E2_PASS`.

P12 — H11 — RESOLVED  
`orchestrate.py:143-174,430-440` structurally detects the reviewed executable, module, and script-path forms without substring false positives. The ordinary deployed generation and benchmark forms are covered.

P13 — H12 — PARTIALLY RESOLVED — MEDIUM  
The classifier unit tests now run independently, and `_oracle_gate()` can fail closed. But no gating job sets `MLX_REQUIRE_P369_ORACLE=1`; `.github/workflows/tests.yml:17-18` uses the default shallow checkout and lines 46-49 run pytest without the variable.

Scenario: CI lacks the historical objects, skips all pre/post-fix oracle integration tests, and still passes.

Fix: checkout full history or fetch the two commits, and set `MLX_REQUIRE_P369_ORACLE=1` in CI.

P14 — H13 — RESOLVED  
`worker.py:275-289` pops the production-shaped entry and clears its `PromptCacheState`; `worker.py:253-272` then drops recorder references and weak-reference-checks every cache leaf.

P15 — H14 — PARTIALLY RESOLVED — HIGH  
`orchestrate.py:1360-1367` performs stale-check-then-unlink without protecting the pathname.

Scenario: two processes read the same stale lock. The first removes it and acquires a new live lock; the second then unlinks that replacement and also acquires the lock. Both GPU campaigns run concurrently and invalidate timing and allocator evidence. Final cleanup at `orchestrate.py:1410-1412` similarly unlinks by pathname without proving ownership.

Fix: use a stable file descriptor with `fcntl.flock()`, retain ownership metadata only for diagnostics, and never reclaim by unlinking a pathname after a separate check.

P16 — H15 — HIGH — `dev/p369_phase2/orchestrate.py:288-297,391-417`  
Problem: kernel-conformance invalidity is converted into E1c `FAIL`, the same status used for measured ON/OFF non-neutrality.

Scenario: rows and state are identical, but telemetry reports an unexpected fallback. `e1c_verdict()` adds `"kernels"`, then `pick_outcome()` reports E1c FAIL and invites a bounded-non-neutrality interpretation even though no distribution or state mismatch occurred.

Fix: separate evidence validity from neutrality. Any kernel/engagement/coverage failure must produce ABORT or INCOMPLETE; reserve E1c FAIL for an established ON/OFF row or state difference.

P17 — H16 — MEDIUM — `dev/p369_phase2/orchestrate.py:1187-1232,1242-1271`  
Problem: C184 persistence is only stage-coarse. `e7()` completes E7a and then E7b before returning; `run_pick()` saves only afterward.

Scenario: E7a finishes, then E7b raises an ordinary worker or harness error. E1c/E2 remain in `summary.json`, but the completed E7a result is absent despite the ruling that each finished step be persisted.

Fix: persist E7a and E7b separately and write a top-level `HARNESS_ERROR` status before re-raising ordinary exceptions.

P18 — H17 — MEDIUM — `dev/p369_phase2/orchestrate.py:590-596,680-700`  
Problem: workers are not launched in their own process groups, and timeout cleanup signals only the direct PID. The tests exercise only childless sleepers.

Scenario: a dependency spawns a helper during model loading or request setup. Killing the worker leaves the descendant alive, potentially retaining GPU memory, files, or ports and contaminating the relaunched worker.

Fix: use `start_new_session=True`, terminate/kill the process group, add parent signal handlers, and test a worker with a stubborn descendant.

P19 — H18 — MEDIUM — `dev/p369_phase2/orchestrate.py:342-358,1217-1225`  
Problem: E7b continuity ignores MTP engagement. `mtp_rounds` is reported but never used to censor the session or validate its observations.

Scenario: all three turns use plain fallback with zero rounds, while token continuity succeeds. The session is reported uncensored with no events even though it established no MTP incident exposure.

Fix: require positive MTP activity on each eligible turn, with the documented first-token-terminal exception, and require the per-entry kernel verdict before treating the session as observed.

VERDICT: NOT CLEARED H2 H6 H9 H10 H14 H15No further action needed; the completed review already incorporated these results.
