**Y1–Y6 are all resolved, and I found no blocker or major.** Two minor residuals remain, F1 and F2. I traced the diff and call chains in the source but ran no tests.

**Y1, resolved.** `p426_reconcile.py:394` returns None unless `in_flight_at_kill` is an int equal to 0. Absent, None, bool, str and float are all refused, so the anchored case can no longer stand in for a sample that was never read.

**Y2, resolved.**
- `structured_grade.py:398` types a Go docker launch `OSError` as `GraderInfraError(kind="spawn")`. Python keeps the untyped abort, which is correct because a regrade can't fix a missing interpreter.
- `container_oom` is now tri-state, and `structured_grade.py:403` is its only production caller.
- An unverified OOM state raises before scoring, and the `finally` at `:436` still removes the container.
- The container is created without `--rm` and removed afterwards, so inspection after exit is sound.

**Y3, resolved with F1 below.**
- `owned_scan` reads the leader's start before claiming anything.
- A live leader whose start differs from the recorded probe start is a reused session. Nothing is claimed or killed, and the reuse is recorded.
- An exited leader leaves members claimed, bounded by the probe's start.
- An unreadable leader makes the scan uncertain and claims nothing.
- A live probe session is still claimed. The recorded start and the scan's read both come from `pg.start_time`, as the probe's `_own_start_time` (`arm_runner.py:1022`) and the chain's read do. The probe's `leader` flag gates `sid` at `chain_core.py:2955`, so `owner` is only ever a pid the probe led.
- I found no path where a live probe session's owned survivor goes unclaimed.
- The one conflicting frozen v3 test is `test_s27_fe_r1.py::test_x10_a_session_member_started_after_the_probe_is_ours_and_is_killed`. It encodes the pre-Y3 behaviour, so I agree it is the test to re-stage.

**Y4, resolved.**
- One contract (`ph.accounting_problems`) is used by the chain, freeze and harvest. It binds the sidecar's seal, disposition, slot, rerun index (an exact int), row sha and item record.
- A missing row now fails, where before `None == None` passed.
- Freeze applies the "no item record" path only when the record file is absent (`lexists`), so a corrupt record is refused.
- Harvest reads the row and record only from inventoried regular files.
- The dropped reason-text match is correct. The binding that protects the data is still exact.

**Y5, resolved.** `_record_finish` is used on both join paths, and `setdefault` keeps an earlier recorded fault.

**Y6, resolved.** The `foreign_new` basename is scrubbed, then capped at 64 characters. The `path_only` basename is capped with the same constant.

**Clarification 1 (`path_only` cap), resolved.** The cap is a size limit, not a content filter, so up to 64 characters of a title-style argv[0] can still reach public data. That matches the Y6 intent, so I raise no finding.

**Clarification 2 (faulted interim boundary), resolved for the capture in grading, with F2 below.** `finish()` discharges `self.grading` from `gate.pending` and `stall_wait` under the lock and records no grade. `trajectory` and the nonconvergence flags are unchanged. The discharge sits after the thread join, so it doesn't race the worker. It runs only after the client has exited, so a pre-outcome fault still reruns through `check()`.

**F1 — `chain_ops.py:1014–1016` and `:1020`. Minor, confirmed by trace.**
- **Problem:** a reused session leaves `owner = None`, so `listed()` adds no problem for unreadable would-be members, and `certain` stays True. The ledger says "recorded", and `session_reused` is recorded.
- **Scenario:** the probe's session-only survivors, with no hermetic HOME or XDG variable, are neither killed nor flagged. The scan reports certain and the leg proceeds. This needs the old leader dead, its process group gone and the pid wrapped, so it is rare.
- **Proposed change:** when `session_reused` is set and any other same-uid process still reports `getsid == sid`, add a problem so the scan is uncertain and the leg pauses. If you judge the rarity too low to be worth pausing a leg, keep the current behaviour and state in the docstring that `certain` excludes session-only survivors in the reuse case. <!-- allow-shorthand: plain English, not a model name -->

**F2 — `arm_runner.py:318–327`. Minor, hypothesis.**
- **Problem:** `finish()` discharges only `self.grading`. A capture queued by `notify()` after the worker died, between the fault and the client's exit, stays in `gate.pending`, and `cancel()` clears that case but `finish()` does not.
- **Scenario:** the stall rule at the terminal decision still waits on a boundary that will never be graded, which is the same change to the nonconvergence flag that clarification 2 removed for the faulted capture. The window is narrow.
- **Proposed change:** in the same block, also discard `self.queued` from `gate.pending` and `stall_wait`, then set it to None.

I found nothing else broken by the diff.