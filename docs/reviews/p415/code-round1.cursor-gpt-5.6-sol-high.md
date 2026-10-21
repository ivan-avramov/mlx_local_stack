# P415 — code review round 1 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p369-v13` `3ae8770e..3b84a211`

Production code is unchanged across the requested range. I’m now tracing each hook through the exact `7207179b` call path; the main risk area is whether the instrumentation sees the real cache and phase transitions rather than merely producing plausible records.Production-code check passed: `git diff 7207179b 3b84a211 -- mlx_vlm ':!mlx_vlm/tests'` is empty.

D1 — High — `dev/p369_phase2/qualify.py:126-133`, `dev/p369_phase2/worker.py:165-170,334-361`  
Problem: The default MTP verification policy is represented inconsistently. `expected_config()` calls an omitted `mtp_verify_scan` `"per_query"`, while production represents that default as no policy object, so `served_state()` records `None`.  
Failure scenario: The MTP-ON Qwen3.8 uniform and Qwen3.6 entries omit `mtp_verify_scan`; both fail `assert_served()` before qualification starts. Only Fable’s explicit `joint_v1` can pass. CPU tests cover explicit `joint_v1` and miss this.  
Fix: Normalize the live default to `"per_query"` or expect `None` for the omitted/default policy; add an MTP-ON fixture without `mtp_verify_scan`.

D2 — High — `dev/p369_phase2/worker.py:1251-1272`, `dev/p369_phase2/qualify.py:307-321`  
Problem: `request_problems()` requires `memory["memory_limit_frac"]`, but `record_memory_limits()` never records that key.  
Failure scenario: Every real GPU record reports `None != 0.85`, so every entry fails. The synthetic test record invents the missing field at `mlx_vlm/tests/test_p415_qualify.py:272-278`, giving false confidence.  
Fix: Record the value actually consumed by the CLI, or remove this redundant check and rely on the independently checked argv plus exact `set_memory_limit` call. Test the real record producer.

D3 — High — `dev/p369_phase2/worker.py:1352-1360`, `dev/p369_phase2/qualify.py:283-292`  
Problem: Qualification never runs `kvmanifest.manifest_problems()` against the measured request’s cache. It checks only recognized class names and `capacity >= prealloc`, without paths, codec, widths, mode, missing leaves, extra leaves, or exact capacity.  
Failure scenario: A TurboQuant entry can leave one or more layers native/affine or otherwise construct the wrong leaf layout and still be COMPLETED. The existing exact-manifest machinery is used later in other worker modes (`worker.py:1633-1648`) but qualification returns at `1575-1583` before it.  
Fix: Capture the exact boundary manifest and compare it with `lm.make_cache()` plus the independent registry-derived KV expectation; require exact capacities.

D4 — High — `dev/p369_phase2/qualify.py:168-177,442-487`, `dev/p369_phase2/worker.py:134-157`  
Problem: The shipping `mlx_vlm.server` executable is checked only as a pathname. Qualification then bypasses it and boots `mlx_vlm.server.cli` in-process using the fork venv. The console script’s entry point, interpreter, installed distribution, and resolved source are never verified.  
Failure scenario: The stack executable can launch a stale or different mlx-vlm installation while qualification uses the reviewed fork and reports COMPLETED.  
Fix: Validate the console script/shebang and installed entry point under the stack venv, and prove `mlx_vlm.server.cli` resolves into the attested fork tree.

D5 — High — `dev/p369_phase2/qualify.py:524-540,577-579,638-670`  
Problem: Source/config binding is neither pinned nor checked at all required boundaries. The fork HEAD is merely recorded; there is no reviewed `--ref`. Fork cleanliness is checked once, stack HEAD is never compared, binding checks run only before jobs, and there is no exit check.  
Failure scenario: Any clean commit with unchanged production code but altered qualification code can run; sources, stack HEAD, registry, or submodule may also change during the final job without invalidating its result.  
Fix: Require the reviewed harness ref, attest fork and stack HEAD/index before every entry and at exit, and repeat registry/submodule/executable checks after each job.

D6 — High — `dev/p369_phase2/qualify.py:639-668`  
Problem: `state.update()` assigns COMPLETED before capacity/reference finalization and before the atomic terminal write. The interruption cleanup changes only PENDING/RUNNING states.  
Failure scenario: SIGINT/SIGTERM after line 646 but before line 657 writes a final report retaining COMPLETED, potentially without capacity/reference evidence. The interruption test raises inside `run_job`, before this window.  
Fix: Keep the state RUNNING until all evidence is finalized, then atomically transition to COMPLETED; add interruption injection around every transition.

D7 — Medium — `dev/p369_phase2/worker.py:1397-1406,1448-1456`  
Problem: The MTP phase boundary fires at `draft_block`, but production first performs `_buffer_mtp_target_cache`, `reset`, and a full `prefill_from_target_hidden` drafter pass.  
Failure scenario: Significant MTP decode/drafter work is charged to the prefill peak, yet `boundary_seen=True`; the reported phase peaks are wrong. CPU tests fabricate boundary fields rather than executing this path.  
Fix: Place the boundary immediately after the target prompt step and before any speculative setup/drafter work.

D8 — Medium — `dev/p369_phase2/qualify.py:61-62,520-523,544`  
Problem: A valid `--p369-summary` does not add the gated Qwen3.6 entry to the default run. `default_entries()` always returns six entries.  
Failure scenario: After P369 passes, the operator can run the apparent full default qualification with its summary, receive exit code 0, and never run the seventh required arm. The test explicitly blesses six defaults at `test_p415_qualify.py:136-151`.  
Fix: Introduce explicit smoke/full modes; full mode must require valid P369 evidence and all seven entries.

D9 — Medium — `dev/p369_phase2/qualify.py:323-328`  
Problem: An auto-derived cache limit is accepted if it is merely one positive value. It is not checked against mlx-vlm’s reviewed heads × prefill-step × context derivation.  
Failure scenario: A regression setting the cache limit to an unsafe positive value still permits COMPLETED and changes the memory result.  
Fix: Independently derive and compare the exact expected byte limit, recording all derivation inputs.

D10 — Medium — `dev/p369_phase2/qualify.py:65-79`  
Problem: The Qwen3.6 gate accepts any JSON with four PASS fields and ignores P369’s available `manifest.production` and `manifest.fork_head`.  
Failure scenario: A stale, unrelated, or fabricated P369 summary unlocks the MTP-ON qualification. The test’s “good” summary intentionally contains no provenance.  
Fix: Require and validate the P369 production revision, reviewed harness revision, phase, complete pick identity, and durable successful outcome.

D11 — Medium — `dev/p369_phase2/qualify.py:343-391,674-699`  
Problem: The comparison fingerprint omits required model revision/file hashes, fork revision, actual cache limit, and other resolved limits. `rec["versions"]` and `rec["snapshot"]` are never populated, while `source_blob` is never validated.  
Failure scenario: Reference differences can be omitted from labels, or a future reference can be declared comparable despite different weights/harness/limits.  
Fix: Carry worker snapshot attestations, hashes, actual versions, harness ref, and observed limits into the fingerprint; validate `source_blob` and compare the complete mandatory schema.

D12 — Medium — `dev/p369_phase2/orchestrate.py:1294-1339`, `dev/p369_phase2/qualify.py:547-556,669`  
Problem: The monitor thread has no exception capture or liveness check. A failed tick terminates the thread silently, while qualification can still complete.  
Failure scenario: The required five-minute power log stops mid-entry, but before/after checks pass and the entry is COMPLETED.  
Fix: Record monitor exceptions, check thread health before terminal status, and fail closed when ticks are missing.

D13 — Low — `dev/p369_phase2/qualify.py:524-557`  
Problem: The lock is acquired before the cleanup `try/finally` begins. Preflight, registry/reference loading, report creation, or monitor startup failures bypass explicit lock release.  
Failure scenario: A caller that catches the exception retains the descriptor and lock; an ordinary CLI exit releases it only incidentally and leaves the output directory behind.  
Fix: Start the outer cleanup scope immediately after acquisition and cover all initialization and monitor-entry paths.

VERDICT: NOT CLEARED D1,D2,D3,D4,D5,D6,D7,D8,D9,D10,D11,D12,D13