P1 — X2 not resolved  
Location: `benchmark/bench/p426_reconcile.py:393-413,453-458`  
Severity: major  
Evidence: confirmed (source trace)  
Problem: `_open_step_at_signal()` never requires `termination.in_flight_at_kill` to be the recorded integer `0`. Missing or malformed values make `inflight_possible` false and enter the new acceptance path.  
Failure scenario: Remove `in_flight_at_kill` from the otherwise valid X2 case; the trailing failed request is still accepted despite the required `/metrics` observation being absent.  
Proposed change: Require `_is_int(in_flight_at_kill) and in_flight_at_kill == 0`; add absent, `None`, boolean and string refusal cases.

P2 — X6 not fully resolved  
Location: `benchmark/bench/structured_grade.py:390-399`; `benchmark/bench/proc_guard.py:1051-1057`  
Severity: major  
Evidence: confirmed (source trace)  
Problem: tg1 Go grader infrastructure failures remain untyped. A Docker launch `OSError` becomes plain `TransportAbort`, while `container_oom()` treats failed Docker inspection as “not OOM.” Neither follows the new `GraderInfraError` path.  
Failure scenario: macOS returns transient `EAGAIN` spawning Docker, or Docker inspection fails after grading. The item is not regraded as a grader infrastructure fault; the latter can even be scored with unverified OOM state.  
Proposed change: Type Go Docker launch failures as `spawn`, and make failed/invalid OOM inspection raise typed `transport` infrastructure errors.

P3 — X10/X22 not resolved  
Location: `benchmark/bench/chain_ops.py:995-1059`; `benchmark/bench/arm_runner.py:1337-1341`  
Severity: major  
Evidence: confirmed (source trace)  
Problem: The lower start-time bound does not defend against session-ID reuse. A new unrelated session reusing the probe’s former PID/SID necessarily starts after `not_before`, so it is classified as owned and killed.  
Failure scenario: After a delayed resume, the probe PID is reused by an unrelated same-UID session leader. The second scan sees the recorded SID and newer start time and kills a process the harness did not spawn.  
Proposed change: Prove continuity with the original session—record an end bound and require an original-era member/leader identity. If reuse cannot be excluded, pause without killing.

P4 — Accounting refusal is lost in freeze and harvest  
Location: `benchmark/bench/p426_freeze.py:411-443`; `benchmark/bench/p426_harvest.py:726-748`  
Severity: major  
Evidence: confirmed (source trace)  
Problem: Consumers do not validate the sidecar contract established by X4. Freeze accepts any self-sealed sidecar whose `item_record_sha256` is `None`; harvest checks only that the expected file exists and is self-sealed. Neither binds it to slot, rerun, row SHA or disposition.  
Failure scenario: An accounting ledger entry with no item record and a sealed sidecar containing only `item_record_sha256: null` passes freeze and can be harvested.  
Proposed change: Share a strict accounting-sidecar validator across collision handling, freeze and harvest; verify disposition, slot, rerun index, row SHA, failed checks and item-record SHA/allowed absence.
