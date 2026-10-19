# P369 phase-2 harness — Cursor gpt-5.6-sol-high CODE review round 1 (fork `p369-mtp` `4e6d0e03..c10205ae`, 2026-10-19)

Prompt: `code-round1.prompt-head.md` + the diff + plan v7 inline; workspace `../mlx-vlm` at `24551869`. Output verbatim:

Verified: `4e6d0e03..c10205ae` has no production diff; only the declared harness/tests changed. No committed home paths or usernames found.

H1 — BLOCKER — `dev/p369_phase2/observe.py:84-101`  
Problem: `state_hash()` is not complete. `ArraysCache.state` omits `left_padding`, `lengths`, and `metadata_revision`; TurboQuant split-codec coordinates (`low_idx`/`high_idx`) are also absent from `meta_state`.  
Scenario: ON and OFF have identical arrays/offsets but different recurrent metadata or codec coordinates. Their SHA values match, and a fixed one-token probe may also match, producing a false E1c state PASS.  
Fix: Serialize type-specific logical metadata canonically, including all `ArraysCache` metadata and TurboQuant codec snapshots; add mutation positives for every deployed cache type.

H2 — BLOCKER — `dev/p369_phase2/telemetry.py:237-278`  
Problem: The verdict does not reconcile runtime calls with the static manifest or require the deployed successful families. It allows `fallback_singletons`, `fallback_timewise`, and any quantized family for any quantized module; grouped `_target_verify_linears` fallbacks also lose per-module attribution.  
Scenario: Optimized affine kernels decline and every projection uses singleton/timewise fallback. All calls remain “consistent” with a quantized manifest and the smoke passes despite never proving the expected verifier kernels ran. A missed consuming alias likewise remains invisible if some other verify calls exist.  
Fix: Pre-register expected entry/family/module coverage per tuple, require every expected projection, reject unapproved fallbacks, and classify tuple fallbacks per module. Add a test where optimized kernels decline and the verdict must fail.

H3 — BLOCKER — `dev/p369_phase2/orchestrate.py:34-44,110-117`  
Problem: `worker_env()` preserves almost the entire shell environment instead of clearing all `MLX_VLM_*`, `KV_*`, and related generation knobs as required.  
Scenario: A stale `MLX_EPICACHE_BUDGET`, `MIN_OUTPUT_TOKENS`, `MLX_VLM_SPEC_BATCH_COALESCE_MS`, or future knob changes cache architecture or generation while `assert_served()` still passes. Results no longer describe the deployed tuple.  
Fix: Build the worker environment from an explicit allowlist, then add only reviewed argv-derived settings and `MLX_VLM_CACHE_SESSION_MAX=1`; record behavior-affecting values in the manifest.

H4 — HIGH — `dev/p369_phase2/worker.py:583-607,792-800`; `dev/p369_phase2/orchestrate.py:153-156`  
Problem: C1 does not verify that OFF1 and OFF2 each captured the complete ON offset set. It compares OFF2 only against offsets present in OFF1.  
Scenario: A recorder defect makes both OFF replays miss the same ON commit offset. C1 passes; ON-vs-OFF1 reports `missing_off`, so precedence labels this an E1c FAIL instead of the required C1 ABORT, misreporting a harness failure as MTP non-neutrality.  
Fix: Pass the expected ON offsets into `c1_acceptance()` and require each replay’s state keys to equal them exactly before comparing values.

H5 — HIGH — `dev/p369_phase2/worker.py:831-873`; `dev/p369_phase2/orchestrate.py:780-797`  
Problem: E7 counts every completed request in its denominator without requiring positive MTP engagement. The worker calculates a telemetry verdict, but the orchestrator ignores it.  
Scenario: A request stops on its first token or silently follows plain decoding. It contributes an event-free E7 observation, biasing incidence downward even though no MTP round occurred.  
Fix: Record round count per turn and require positive verifier/MTP activity; censor or abort non-engaged requests rather than counting them event-free.

H6 — HIGH — `dev/p369_phase2/orchestrate.py:704-722`  
Problem: C84 reconstruction validates only prompt-token counts. It neither records nor compares the required token-ID SHA-256.  
Scenario: Dataset or prompt-builder drift produces different token IDs with the same count. Reconstruction passes and E2 exercises the wrong corpus.  
Fix: Have count mode return the exact templated IDs or their digest, persist the digest, and compare it with the pinned bundle metadata.

H7 — HIGH — `dev/p369_phase2/orchestrate.py:819-832`  
Problem: E7b continuity is only `cached_tokens > previous prompt_tokens`; it does not prove reuse through the previous assistant response or check the session hash chain.  
Scenario: One token of the prior assistant turn is reused while the remainder is re-prefilled or mismatched. The session is reported continuous instead of censored.  
Fix: Check the exact expected assistant boundary, accounting for cache lag, and verify the server session’s recorded turn-hash chain against the constructed conversation.

H8 — HIGH — `dev/p369_phase2/worker.py:242-255`; `dev/p369_phase2/orchestrate.py:338-356,547-564,296-335`  
Problem: There is no enforceable per-request watchdog or total campaign watchdog. Passing `timeout=` to in-process `TestClient` does not independently interrupt the ASGI application; only the aggregate worker subprocess timeout is enforced.  
Scenario: One E7 request hangs until the entire multi-request job deadline, killing the worker and losing the remaining observations rather than recording that request as censored. The full campaign can also exceed 3.5 hours because the monitor only logs elapsed time.  
Fix: Add an orchestrator-observed per-request heartbeat/deadline and a hard campaign deadline; write explicit timeout/censor artifacts before terminating a worker.

H9 — HIGH — `dev/p369_phase2/orchestrate.py:234-251,518-544,919-924`  
Problem: The run is not bound to the reviewed harness. Preflight checks tracked production differences only; modified/untracked `dev/p369_phase2` content is accepted. A full run trusts any JSON containing `smoke_gate.pass_` and `fits`, without matching production, harness, picks, argv, overlays, or weights.  
Scenario: An old or edited smoke summary authorizes a full run using changed harness code or different model artifacts.  
Fix: Hash the reviewed harness/tests, require a clean tracked/untracked scope, and bind the smoke summary to the current manifest and selected picks.

H10 — MEDIUM — `dev/p369_phase2/orchestrate.py:724-778,838-864`  
Problem: Full-run E2 has no explicit verdict. `all_identical`, `control_identical`, and kernel status are recorded but never incorporated into a phase status; the process exits successfully.  
Scenario: ON/OFF identity fails or the OFF reload control differs, yet the only named outcome remains `e1c=PASS`.  
Fix: Report `E2=PASS|FAIL|INFORMATIVE_ONLY`, apply the control precedence, and produce an explicit overall phase status.

H11 — MEDIUM — `dev/p369_phase2/orchestrate.py:45-54,203-213`  
Problem: Preflight does not reject generic `mlx_vlm` or benchmark processes required by the plan, while substring matching can reject unrelated processes.  
Scenario: A concurrent `python -m mlx_vlm.generate` or benchmark consumes GPU resources and causes timeouts or allocator differences that appear to be harness/MTP findings.  
Fix: Inspect argv structurally and reject the complete reviewed executable set, including generic generation and benchmark commands.

H12 — MEDIUM — `mlx_vlm/tests/test_p369_phase2_oracle.py:24-37`  
Problem: Missing pre-fix objects skip the entire oracle module, including independent classifier tests. A shallow CI checkout therefore passes without proving the M3/M4 binding.  
Scenario: Oracle integration breaks while CI reports only skips.  
Fix: Fail closed in the gating job or fetch the required objects; split non-git unit tests so they always execute.

H13 — LOW — `dev/p369_phase2/worker.py:207-239`; `mlx_vlm/tests/test_p369_phase2_worker.py:357-379`  
Problem: Production session entries are dictionaries containing `entry["state"]`, but retirement calls `state.clear()` on the dictionary. The test inserts a bare `PromptCacheState`, masking the mismatch.  
Scenario: Explicit `PromptCacheState.clear()` and snapshot-ring retirement are not exercised as claimed; release currently relies on reference dropping and GC.  
Fix: Pop the production-shaped entry, call `entry["state"].clear()`, then drop references; make the test use the real entry shape.

H14 — LOW — `dev/p369_phase2/orchestrate.py:931-938`  
Problem: The exclusive lock has no stale-owner recovery.  
Scenario: `SIGKILL` or power loss leaves `.lock`, causing every later run to refuse until manual intervention.  
Fix: Store PID/start metadata and reclaim only after proving the owner is dead.

VERDICT: NOT CLEARED H1 H2 H3 H4 H5 H6 H7 H8 H9
