**Review of the S27 harness robustness candidate**

I read the guard, the reconcile cases, the abort route, the done and ready hooks, the positives verdicts, the push binding, the harvest links and the chain scan. I could not run anything, because no shell was available. All "confirmed" below means traced in the source, and no finding was reproduced by running code. Spec and ledger sections (§3, §4.2, §5.x) refer to `docs/specs/s27-harness-robustness.md` v1.4 and the three design ledgers.

**Process kill authority and records.** In the code I traced, the guard kills only a process that is tracked, in the ancestry of a tracked process, in the probe's session (only if the probe leads it), or whose readable environment carries the run's hermetic HOME or XDG values. Path-only matches go to `foreign_new` and are never killed. `hermetic_markers` filters env markers to values under the run directory at the source, so a hand run's real HOME never becomes a marker. I found no path where a foreign process is killed. Owned processes can still escape in two ways. One is the accepted residual (C372). The other is a process the chain scan silently skips, described in P7.

**Findings**

**P1 — Stale lifecycle stage mis-routes an abort to the previous item as an accounting fault.**
- **Location:** `bench/arm_runner.py:1428` and `:1470`, with `bench/chain_core.py:2882–2932`.
- **Severity:** major. **Evidence:** confirmed in source; the consequence in the last two sentences is a hypothesis.
- **Problem:** `ctx["stage"] = "done"` is set when an item's row is committed and is never reset. `_run_item` sets it back to `"generation"` only at line 476. Two aborts can happen between those points: a `BarrierTimeout` at `barrier.ready(k+1)` (line 1364), and a cleanup-uncertain from the `_DiscoveryGuard` before the item. Both are stamped `stage="done"` and `outcome_present=True`.
- **Failure scenario:** `p426_abort_route` takes `outcome = True` and `failing = ids[-1]`, which is the previous, clean item. It writes an accounting sidecar for that item and flags it `accounting_fault`, which excludes its tokens and latency from aggregates and marks it speed-invalid. The fault that really happened, on item k+1, is never counted by `p426_record_fault`. The cap is therefore never reached, and a persistent ready-barrier failure would relaunch the probe indefinitely, each time re-flagging item k. The tests pass `stage="done"` explicitly, so none covers this.
- **Proposed change:** reset `ctx["stage"] = "ready"` before `barrier.ready(k)`, and also at the top of each item iteration and in `_DiscoveryGuard`. Add a red test for a `BarrierTimeout` at ready on item two.

**P2 — The interrupt positive cannot run, but v8 requires it.**
- **Location:** `benchmark/run_tg1_probe.py:69,104`, `run_tg2_probe.py:71,106` and `run_oc_probe.py:71,114`. These are fed by `chains/c147/run_inject.py:38`. The requirement is in `bench/p426_freeze.py:973–977`.
- **Severity:** major (blocks acceptance item 10.3). **Evidence:** confirmed; the implementer also reports it under "Not satisfied".
- **Problem:** `--tg1-inject` and `--tg2-inject` accept only `stall|loop|alloc`. `run_inject.py` passes `--tg1-inject interrupt`, which argparse rejects. `positives_problems` and `inject_verify`'s suite both require exactly one interrupt PASS.
- **Failure scenario:** no sealed tg2 positives record can reach v8 on the new identity, so the restart from the gate stops.
- **Proposed change:** add `interrupt` to the three `choices=` tuples, as part of the same identity rotation. This needs the operator's approval, since these files were outside the implementer's brief. Then run one live fake-item end to end.

**P3 — `inflight_evidence` is still decided by the order of two independent events (ledger L1).**
- **Location:** `bench/p426_reconcile.py:421–427` and `:596`.
- **Severity:** major. **Evidence:** confirmed in source.
- **Problem:** with `|C| == expected` and one trailing STREAM_CLOSED failed line, `inflight_possible` comes from the `/metrics` sample taken before SIGTERM. If the sample reads 0 and the client then opens its next request, the check fails. `inflight_evidence` is not in the §5.9 accounting table, so the item is integrity and the leg is INVALID. This is the same family as D1, and the implementer left it unchanged.
- **Failure scenario:** the stop lands in the gap between a tool finishing and the next request starting. The leg is lost to a race the bundle exists to remove.
- **Proposed change:** also accept the stream's own open-step evidence (a trailing `step_start` with no `step_finish`) together with the worker deltas `started == |C|+1` and `failed == 1`. This needs the operator's approval to amend the frozen B2 test that pins the current behaviour. The alternative is to record the design-level justification explicitly as a settled item.

**P4 — Sidecar `FileExistsError` is treated as "already sealed", so an unwritable sidecar continues.**
- **Location:** `bench/chain_core.py:3270`.
- **Severity:** minor (it is the test-writer's reported defect, and the frozen test fails). **Evidence:** confirmed.
- **Problem:** `except FileExistsError: return True` also catches the `mkdir` failing because `items` is a file.
- **Proposed change:** return True only when the sidecar path itself `is_file()` and its sha matches. Otherwise return False and PAUSE (§5.3).

**P5 — Grader-fault classification matches substrings of text that embeds agent output.**
- **Location:** `bench/token_turn_gate.py:54–87`, fed by `bench/tg2_grade.py:1462, 1470, 1481, 1447`.
- **Severity:** minor. **Evidence:** confirmed for the embedding; the scenario is a hypothesis.
- **Problem:** messages such as `tg2 compile: start marker absent: {_text(comp)[-300:]}` include the last 300 characters of the item's compile or run output. The markers "Connection refused", "connection reset" and "Broken pipe" can therefore be matched by agent text.
- **Failure scenario:** such an item is regraded three times and scored as a `grade_fault` DNF. A leg abort becomes a DNF that depends on agent-controlled text.
- **Proposed change:** classify by exception type or a structured field set where the grader raises, not by substring. Or match markers only against the prefix before the first `:`.

**P6 — Also a hook-infra error at `done` becomes an accounting fault when the ready checks could not run.**
- **Location:** `bench/chain_core.py:3198–3204`.
- **Severity:** minor. **Evidence:** confirmed; spec §5.3 sanctions it.
- **Problem:** `_ready_problems()` can raise `HookInfrastructureError` in `after_attempt`. The registry-sha, lifecycle and worktree-clean checks then never ran for that item. The leg continues, and only the next `ready` re-checks.
- **Proposed change:** record in the sidecar that the ready checks were not evaluated, and make the next item's `ready` mandatory. It already is, so this is a recording change.

**P7 — The chain scan re-implements ownership and has no identity guard.**
- **Location:** `bench/chain_ops.py:979–1059`.
- **Severity:** minor (also the heavier-than-needed item). **Evidence:** confirmed.
- **Problem:**
  - It duplicates the guard's rules, so the two can drift.
  - Session membership is by bare `getsid == sid`, with no age or identity bound. A reused pid that leads its own session would match.
  - A process whose `uids()` read is denied is skipped silently and never listed.
- **Failure scenario:** the scan runs right after the probe exits, so a pid-reuse hit is unlikely.
- **Proposed change:** share one classifier with the guard, such as a `classify(listing, session, markers)` function the chain calls. Require that session members started at or after the probe's recorded start time. List skipped unreadable processes.

**P8 — Recording argv of unrelated processes in public rows.**
- **Location:** `proc_guard._record_foreign` (argv scrubbed), landing in `row.cleanup_status`.
- **Severity:** minor. **Evidence:** hypothesis.
- **Problem:** `foreign_new` stores up to 64 arbitrary same-uid command lines per item. The PII scrub does not cover tokens or flags. The harvest then quarantines the row or refuses the "scrub would change this main record" check, which blocks publishing the leg's rows.
- **Proposed change:** record `{pid, create_time, sid, flags, basename(argv[0]), argc}` instead of the full argv. That is enough for "record, never act", and the receipt gets lighter.

**P9 — The `unpublished` shape waives the message-id equality when `last_step_start` is missing.**
- **Location:** `bench/p426_reconcile.py:378`.
- **Severity:** minor. **Evidence:** confirmed.
- **Problem:** spec §4.2 requires the id to equal the stream's last `step_start`, but the code reads `last_id is None or …`.
- **Proposed change:** require `last_id` when `step_starts == n`.

**P10 — Verification is incomplete.**
- **Location:** the broad run.
- **Severity:** major until run. **Evidence:** hypothesis.
- **Problem:**
  - `test_p585…::test_the_scan_skips_a_process_it_cannot_construct…` and `test_proc_guard::test_real_rapid_fork_detach_chdir_is_attributed_or_diagnostic` fail in the broad run and pass alone. They sit in the sensitive hunk and are unexplained. The second asserts attribution that S27 changes to `foreign_new`.
  - 309 failures from the missing submodule mask frozen B2 tests, including `test_fix_the_done_hook_invalidates_a_server_count_that_differs_from_the_client`, which S27 contradicts.
  - The implementer edited the frozen `s26_frozen`, `p586_frozen` and `test_b2_*` files.
- **Proposed change:** check out the submodule and run the full suite on the baseline and on the candidate. Have a cold reader approve each edit to a frozen test.

**P11 — Minor items beyond the specification.**
- **Cleanup receipt fails closed too broadly.** `cleanup()` raises `CleanupUncertain` whenever the last 3-attempt scan killed anything, because `survivors` keeps pids that were already verified gone. It never passes wrongly. It could still abort a leg over a fork storm that was cleaned up.
- **Dead `session_id` parameter.** `ProcessGuard` and `_run_item` have a `session_id` parameter that no caller passes.
- **Test-double code in `Chain`.** `Chain.__getattr__` and its class-level defaults exist only for test doubles.
- **JS lock omission rests on an unproven premise.** For Rust, the grader regenerates the lock (`tg2_grade.py:551`). For JavaScript, no grader code deletes or ignores `package-lock.json`. The omission's comment, "as Cargo.lock", is unsupported.

**Status of the design-review findings**

| Finding | Status |
|---|---|
| R1/R2 (no post-outcome rerun) | resolved, except P1's mis-attribution |
| R3 (second scan, else paused) | resolved |
| R4 (offset proof) | resolved; see P9 |
| R5, R13 (receipt schema), R14 (C365), R15 (links, as built; P11 for the JS lock premise) | resolved |
| R6, R7, R12 | resolved by design; not traced in the watcher or hold paths |
| R8 (rerun machinery) | resolved, but P1 breaks stage routing |
| R9 (positives) | resolved |
| R10, R11 (§3.2/3.3 ownership order) | resolved; traced |
| R16 (`setsid` residual) | accepted (C372) |
| V1 (accounting sidecar) | resolved, except P4 |
| V2 (closed table) | implemented; P3 is an order-dependent integrity check outside the table |
| V3, V6, V7, V8, V9 (settle check) | resolved |
| V4 (typed abort route, chain scan) | not resolved: P1 |
| V5 (regrade, not regenerate) | resolved in form; P5 |
| V10 (push binding) | resolved; I found no regression and no refusal lost |
| W1 (stage routing) | not resolved: P1 |
| W2 (in-probe regrade with one snapshot) | resolved |
| W3 (storage) | resolved |
| W4 (chain scan authority) | resolved in effect, with P7 |
| W5 (protected-path constant) | resolved |
| W6 (independent caps) | not traced |
| C373 interrupt positive | not resolved: P2 |
| v1.4 second `kill_boundary_late_record` shape | resolved; P9 |

I did not find a verdict that now passes where it was refused before, other than the spec-sanctioned changes. I did not trace the watcher, the hold deadline suspension, or the corpus-side `interrupt` stop path.