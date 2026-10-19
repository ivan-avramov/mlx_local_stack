# P369 phase-2 harness — Cursor gpt-5.6-sol-high CODE review round 5 (fork `p369-mtp` `62f4f00c..db825821`, 2026-10-19)

Prompt: `code-round5.prompt-head.md` + the round-4 output + `git diff 62f4f00c..db825821` + plan v7; workspace `../mlx-vlm` at `24551869`. Attempts 1–2 (`--output-format text`) printed nothing; attempt 3 (`--output-format stream-json`) — the `result` event text, verbatim:

P1 — Verification

Read-only review of `62f4f00c..db825821`; tests were not run.

- `4e6d0e03..db825821` has no production diff under `mlx_vlm` excluding tests.
- Red-test commit `dbe2b115` directly precedes implementation commit `db825821`.
- The checkout remains at base `24551869`.

P2 — Round-4 findings

H9 — RESOLVED  
`orchestrate.py:128-138,321-343,1705-1727`; `worker.py:56-92,863-871`  
Workers are forced offline, snapshots are re-resolved and re-hashed, and the bound stack tree and bundle hashes are checked before and after reconstruction. The disclosed concurrent symlink-swap residual remains outside the stated threat model.

H12 — PARTIALLY RESOLVED — MEDIUM — `.github/workflows/tests.yml:17-18,46-49`; `test_p369_phase2_oracle.py:35-44,65-70`  
CI remains shallow and does not set `MLX_REQUIRE_P369_ORACLE=1`; history-backed oracle tests may skip. The P394 deferral remains non-blocking for this branch.

H22 — PARTIALLY RESOLVED — HIGH — `orchestrate.py:1016-1028,1133-1137`  
Tracked workers and descendants are now repeatedly extinguished, but H31 accepts an untracked early exit without proving cleanup. The disclosed spawn-and-escape-between-polls residual also remains.

H23 — PARTIALLY RESOLVED — MEDIUM — `orchestrate.py:1279-1297,1314-1317,1757-1791,1942-1944`  
Problem: `prepare()` is inside `execute()`’s persistence boundary, but `Campaign(args)` still reads and parses the registry before entering it. A signal before `prepare()` creates the output directory is likewise not persistable.

Scenario: malformed `main_models.yaml`, a missing generation default, or SIGTERM during construction exits without `summary.json`.

Fix: make construction side-effect-free; create the run directory and enter the persistence boundary before registry loading and parameter derivation.

H24 — PARTIALLY RESOLVED — LOW — `test_p369_phase2_procs.py:38-68`; `test_p369_phase2_orchestrate.py:1071-1078,1096-1121`  
The new escaper records itself before `setsid()` and teardown kills each test PGID. The older fixture still relies on the parent writing `child.pid`; it can leak a child if the parent dies after the child escapes but before writing the PID.

Fix: use the child-side handshake in the older fixture too, and validate recorded identities during teardown.

H27 — PARTIALLY RESOLVED — HIGH — `orchestrate.py:806-824,1097-1132`  
The inherited signal mask defect is fixed and the first TERM/INT is deferred through tracker creation. Cleanup remains interruptible by a subsequent signal; see H32.

H28 — RESOLVED  
`orchestrate.py:827-869` applies a fixed locale, timeout, strict parsing, retries command failures, requires the supervisor PID, and raises on unknown state. Unknown state no longer means extinction.

H29 — PARTIALLY RESOLVED — MEDIUM — `orchestrate.py:979-994`  
Tracked identities are re-scanned, re-signalled, and awaited. The promised bounded deadline is not enforced around `ps_table()`; see H33.

H30 — PARTIALLY RESOLVED — MEDIUM — `orchestrate.py:916-928,931-935,1025-1028`  
Problem: live roots are start-validated, but `proc.poll()` reaps the leader before cleanup. Once the root PID is absent, `group_members()` trusts every process with the numeric PGID.

Scenario: the root PID is reused to create a foreign group and that new leader exits before the next scan. Its remaining members are enrolled and killed despite no validated root identity. This is broader than the disclosed same-second `lstart` collision.

Fix: observe leader exit without reaping it, for example using `waitid(..., WNOWAIT)`, until group cleanup completes; never discover members from an unanchored PGID.

P3 — New findings

H31 — HIGH — `dev/p369_phase2/orchestrate.py:1016-1022,1133-1155`  
Problem: failure to create a tracker is converted to ordinary `exited` when the worker has already terminated. `run_job()` then skips `reap()` and may accept `result.json`.

Scenario: a worker writes a successful result, spawns a group member, and exits before either tracker attempt observes its root. The result passes and the survivor overlaps the next GPU worker.

Fix: an untracked exit must be `HARNESS_ERROR`; while the leader remains unreaped, kill and verify extinction of its newly created group before waiting on it.

H32 — HIGH — `dev/p369_phase2/orchestrate.py:1102-1132`  
Problem: restored TERM/INT handlers can interrupt `_stop()` itself. A second signal raises from inside cleanup and replaces the first interruption before extinction is established.

Scenario: TERM is deferred during spawn; while its replay is stopping the worker, a launcher sends another TERM. `_stop()` aborts and the GPU worker survives the campaign’s `INTERRUPTED` exit.

Fix: defer repeated TERM/INT throughout cleanup, preserve the primary interruption, finish reaping, then replay or exit.

H33 — MEDIUM — `dev/p369_phase2/orchestrate.py:830-869,985-994`  
Problem: `reap(wait_s=10)` starts its deadline before calling `ps_table()`, but one table request can consume approximately 30 seconds across retries.

Scenario: three `ps` timeouts make a nominal ten-second reap exceed thirty seconds before it checks its deadline.

Fix: pass the remaining deadline into `ps_table()` and cap retries, timeout, and backoff to that remainder.

H34 — MEDIUM — `dev/p369_phase2/orchestrate.py:436-451,586-594`  
Problem: absent or non-boolean `rows.pass` or `states.pass` is interpreted as established non-neutrality instead of malformed harness evidence.

Scenario: a comparator schema regression omits `pass`; the worker still returns `status: ok`, and the pick becomes E1c `FAIL`, reporting a harness defect as an MTP finding.

Fix: validate comparator schemas and require exact booleans before classification; malformed evidence must raise `HARNESS_ERROR`.

P4 — Claim integrity

H31 can still permit PASS without process extinction, and H34 can misreport harness failure as MTP non-neutrality. No additional snapshot or stack-binding false-PASS path was found within the disclosed single-operator threat model.

VERDICT: NOT CLEARED H31 H32