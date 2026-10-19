# P369 phase-2 harness — Cursor gpt-5.6-sol-high CODE review round 4 (fork `p369-mtp` `a004a922..62f4f00c`, 2026-10-19)

Prompt: `code-round4.prompt-head.md` + the round-3 output + `git diff a004a922..62f4f00c` + plan v7; workspace `../mlx-vlm` at `24551869`. Attempt 1 printed nothing; attempt 2 verbatim:

P1 — Verification

Read-only review of `a004a922..62f4f00c`; tests were not run.

- `4e6d0e03..62f4f00c` has no production diff under `mlx_vlm` excluding tests.
- Fixture payload SHA-256 remains `1d07c9dd0ebf5058b526e1d78fee2a88f8e92976323ddf0e8d5503dcaa18253d`.
- Each fix has a preceding red-test commit.
- The visible launch command and `--out` enforcement agree on `$STACK_WORKDIR/p369/phase2/<run-id>`.

P2 — Round-3 findings

H8 — RESOLVED  
`worker.py:105-114` persists the request and `after` heartbeat before cleanup. `orchestrate.py:964-970` writes the timeout decision before signalling.

H20 — RESOLVED  
`orchestrate.py:951-970` promotes a durable `req-N.json` with stale request heartbeat to `hang_after`; `975-995` retains that entry without censoring. Worker entries are atomically written at `worker.py:95-109`. The interleaving test is at `test_p369_phase2_orchestrate.py:1131-1143`.

H9 — PARTIALLY RESOLVED — HIGH — `dev/p369_phase2/worker.py:56-91,860-871`; `dev/p369_phase2/orchestrate.py:1110-1122,1245-1267,1631-1638`  
Problem: full commit resolution and XDG precedence are fixed, and persistent mutations of attested files are detected. But the worker boots and loads the models before calling `_hf_snapshot`; it therefore re-resolves and hashes the cache’s current symlink targets, not necessarily the paths/inodes loaded by MLX. The stack check similarly verifies only that the current worktree is clean, not that its current HEAD and bundle bytes still equal the manifest.

Scenario: an HF snapshot reference or blob symlink points at different bytes while `boot()` loads the model, then returns to the attested target before `check_snapshots()`. Alternatively, the stack checkout moves cleanly after `prepare()`; the second pick passes `git status` and reconstructs against a different clean benchmark tree while the manifest still records the original tree. Either run can PASS with unattested weights or prompts.

Fix: stage or otherwise pin an immutable worker-private snapshot while retaining repo-ID production loading, and verify the exact resolved file identities used. Reconstruct C84 from a detached read-only stack worktree and bind the canonical reconstructed-item artifact; at minimum verify stack HEAD/tree and bundle hashes before and after reconstruction.

H12 — PARTIALLY RESOLVED — MEDIUM — `.github/workflows/tests.yml:17-18,46-49`  
Problem: CI still uses a shallow checkout and does not set `MLX_REQUIRE_P369_ORACLE=1`.

Scenario: oracle history or integration breaks while ordinary CI skips the required gate.

Fix: as deferred to P394, enable the oracle and full history in the fork-main merge. This accepted deferral does not block this branch review independently.

H16 — RESOLVED  
E7a is persisted before E7b starts at `orchestrate.py:1657-1663`.

H23 — PARTIALLY RESOLVED — MEDIUM — `dev/p369_phase2/orchestrate.py:1223-1248,1666-1697`  
Problem: smoke binding, execution, interruption, and final tree failures are now persisted, but `prepare()` remains before the persistence `try`.

Scenario: dirty stack inputs raise `SystemExit` at line 1248 after creating the run directory, or SIGTERM arrives during preparation. No `summary.json` records `REFUSED` or `INTERRUPTED`.

Fix: place preparation and binding creation inside the persistence boundary; raise `Refused` for preparation refusals and persist the corresponding status before propagation.

H17 — RESOLVED  
The original process group is signalled and killed through `orchestrate.py:769-827`; normal exit also invokes `reap()` at `1045-1046`.

H22 — PARTIALLY RESOLVED — MEDIUM — `dev/p369_phase2/orchestrate.py:830-912,1011-1044`  
Problem: polling now discovers ordinary escaped descendants, but cleanup ownership and extinction are not established under the signal-mask, `ps`, escaped-process, and PID-identity defects detailed in H27–H30.

Scenario: termination interrupts publication through the monitor thread, `ps` fails open, or an escaped helper remains alive after the original group disappears. A later GPU worker can launch with a survivor.

Fix: apply H27–H30 while retaining the disclosed helper-that-spawns-and-escapes-between-polls residual.

H19 — RESOLVED  
`test_mtp_verify_scan.py:1760-1762,1800-1827` reads decoded raw bytes without newline translation. CRLF and lone-CR files are exercised through `live_registry()` at lines 2533-2547.

H21 — RESOLVED  
The canonical lock is `$STACK_WORKDIR/p369/phase2/.lock` at `orchestrate.py:339-343,1838-1840`, and `out_problems()` requires a strict run subdirectory at lines 346-354. The documented launch at lines 4-5 agrees.

H24 — PARTIALLY RESOLVED — LOW — `mlx_vlm/tests/test_p369_phase2_orchestrate.py:919-960,1093-1116,1169-1187`  
Problem: normal-exit coverage was added and new fixtures kill recorded children, but teardown still depends on successfully reading `child.pid`. The older group test also signals individual known PIDs rather than always killing its PGID.

Scenario: a helper calls `setsid()` and the test worker dies before writing or flushing `child.pid`; teardown cannot identify the escaped child and leaves it running.

Fix: use a handshake that records the child before allowing it to escape, and always kill the test PGID in `finally`.

H25 — RESOLVED  
The fixture and test comments at `stack_registry_golden.yaml:1-3` and `test_mtp_verify_scan.py:1727-1729` now accurately describe `7021bdbb` as the last registry-changing commit before C177 and byte-identical to `78a730fe^`.

H26 — RESOLVED  
`test_mtp_verify_scan.py:1807-1813` distinguishes an absent variable from an empty value and fails the latter. Coverage is at lines 2550-2557.

P3 — New findings

H27 — HIGH — `dev/p369_phase2/orchestrate.py:693-738,1011-1044`  
Problem: `pthread_sigmask` is thread-local and its mask is inherited across `fork`/`exec`. The monitor thread is already running and remains unblocked, while the spawned worker inherits blocked SIGTERM/SIGINT because only the parent restores its mask.

Scenario: SIGTERM is delivered to the monitor thread and Python raises `SystemExit` in the main thread after `Popen` but before tracker publication; the first exception handler restores the mask and propagates without stopping the worker. On ordinary stops, the worker cannot receive SIGTERM and always consumes the grace period before SIGKILL.

Fix: replace masking with temporary main-process handlers that defer and record TERM/INT until `proc`, PGID, and tracker are published, then restore and replay the interruption. Do not use `preexec_fn` in this multithreaded process.

H28 — HIGH — `dev/p369_phase2/orchestrate.py:830-840,875-885`  
Problem: both `ps` calls ignore nonzero return codes and silently discard malformed or partial output. Unknown process state is treated as no descendants or group extinction.

Scenario: transient `ps` failure returns empty stdout. `_group_alive()` reports false and `reap()` returns while a worker-group member remains, allowing the next GPU launch and potentially a false PASS under contaminated resources.

Fix: use `check=True`, controlled locale, timeout and strict parsing; retry transient failures and treat unresolved process state as `HARNESS_ERROR`, never extinction.

H29 — HIGH — `dev/p369_phase2/orchestrate.py:863-912`; `mlx_vlm/tests/test_p369_phase2_orchestrate.py:1183-1187`  
Problem: tracked escaped descendants receive one SIGKILL but are never awaited. The extinction loop checks only the original process group. The test itself performs the missing `_wait_dead(child)` after `reap()`.

Scenario: a tracked `setsid()` GPU helper has SIGKILL pending or is temporarily uninterruptible. The original group is empty, so `reap()` returns and the next worker starts before the helper releases GPU state.

Fix: repeatedly verify every tracked non-zombie identity has disappeared, re-signal as necessary, and raise `HARNESS_ERROR` after a shared bounded deadline.

H30 — MEDIUM — `dev/p369_phase2/orchestrate.py:830-870,896-910`  
Problem: historical PIDs remain ancestry frontiers without validating their recorded start time. macOS `lstart` is locale-formatted with only one-second precision, and the root has no stored identity. Cached leadership also continues using a numeric PGID after reaping.

Scenario: a tracked PID is reused by an unrelated process; its children are enrolled and killed. Conversely, a worker descendant reusing a stale PID keeps the old `setdefault` identity and is skipped. Rapid reuse within one displayed second defeats the kill-time comparison entirely.

Fix: store and validate the root and every frontier as a kernel-backed identity, preferably Darwin `proc_pidinfo` start seconds/microseconds; exclude stale identities from traversal and verify original membership before signalling a cached PGID.

P4 — Claim integrity

No additional path was found that deliberately converts a detected snapshot, tree, worker, or reaping failure into an MTP non-neutrality finding: those paths normally become `HARNESS_ERROR`, ABORT, INCOMPLETE, or censored evidence. The remaining silent PASS risks are H9’s unattested inputs and H28/H29’s unestablished process extinction. P394’s one-valid-observation E7 rule remains intentionally implemented and is not re-raised.

VERDICT: NOT CLEARED H9 H27 H28 H29
