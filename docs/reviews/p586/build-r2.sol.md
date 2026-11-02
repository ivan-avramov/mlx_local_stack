P1  
Location: `benchmark/bench/p426_reconcile.py:177-187,420-436`  
Severity: blocker  
Evidence: confirmed — traced in source  
Problem: Continuity depends on subtracting local timestamps. A DST rollback can conceal a long worker stall, so the check is not fail-safe.  
Concrete failure scenario: A request begins at 01:59:36 PDT, emits one telemetry line at 01:59:59 PDT, then stalls. The client cuts it about 3645 seconds later at 02:00:21 PST. The real telemetry-to-close gap is ~3622 seconds, but `_stamp_gap_s` reports ~22 seconds. With one telemetry line there is no consecutive elapsed-gap check, so the stalled request is accepted as `kill_client_aborted`.  
Proposed change: Derive the close gap from monotonic/epoch evidence, not local stamps—for example, validated assistant wall time versus telemetry elapsed—or add an epoch to telemetry. Keep local timestamps diagnostic only. Add this stall-across-fallback case.

P2  
Location: `benchmark/bench/p426_reconcile.py:389-418`; `benchmark/bench/p426_hooks.py:222-238`  
Severity: major  
Evidence: confirmed — traced in source  
Problem: Client provenance never verifies that the export belongs to `row.session_id`. The SHA only proves correspondence to the row’s declared export hash; it does not establish session identity.  
Concrete failure scenario: Session A supplies the worker window and row, but its `transcript_path` and export SHA point to session B, whose final assistant has the required abort and matching time. Completed lines still identify A, while the trailing failed line has no session field. All checks pass and B’s abort is attributed to A.  
Proposed change: Require `export.info.id == row.session_id`; also reconcile export assistant IDs with `request_usage` where available. Add a failed-variant foreign-export test—the existing test covers only a foreign completed worker line.

P3  
Location: `benchmark/bench/p426_reconcile.py:399-418,468-476`  
Severity: major  
Evidence: confirmed — traced in source  
Problem: Condition (a) validates `time.completed` but not `time.created`; `_client_abort_block` later indexes both directly.  
Concrete failure scenario: An otherwise valid export lacking `time.created` passes (a)–(e), then raises `KeyError` instead of producing a clean systemic INVALID. A future `created` value instead yields an accepted record with negative `wall_s`.  
Proposed change: Include finite numeric `created`, `completed`, and `created <= completed` in provenance; construct the block only from validated values. Add missing, nonnumeric, and reversed-time tests.

P4  
Location: `benchmark/bench/p426_freeze.py:40,299-308`  
Severity: major  
Evidence: confirmed — traced in source  
Problem: Importing all of `p426_reconcile.KILL_CASES` widens R3’s rehearsal check to the two client-abort cases. R3 is required to prove the injected stall-kill path.  
Concrete failure scenario: The stall injection fails to act; after an hour, opencode’s inactivity cut produces `kill_client_aborted`. The R3 leg is VALID and the freeze accepts it, despite never exercising the stall kill.  
Proposed change: Give R3 a dedicated accepted-case set excluding client-abort cases, ideally also verify the injected first-Python slot and `stalled` outcome. The frozen tests currently assert the unsafe widening instead of rejecting it.

P5  
Location: `benchmark/bench/p426_harvest.py:850-861`  
Severity: major  
Evidence: confirmed — traced in source  
Problem: `--dry-run` still exits immediately on malformed/missing `leg.json`, an invalid state, or an attempt-name mismatch, so it does not collect every classification, scrub, and secret problem.  
Concrete failure scenario: A tree has an invalid leg state, three unclassified files, and a credential in `RUNLOG.md`. Dry-run reports only the state error and never runs the secret scan.  
Proposed change: In dry-run mode, append structural errors and continue all independent inventory/gate checks; skip only checks whose prerequisites are unavailable. Add malformed-leg plus independent classifier/secret problems to the frozen tests.

P6  
Location: `benchmark/bench/p426_leg.py:422-427`; frozen test `test_p586_dst.py:72-74`  
Severity: major  
Evidence: confirmed — traced in source  
Problem: `run=subprocess.run` is bound at module import, so monkeypatching `p426_leg.subprocess.run` does not intercept `pmset`. The supposedly hermetic DST test executes the host command.  
Concrete failure scenario: The test passes or fails based on the machine’s real power log; on a host without `pmset` it errors, and on macOS it reads nondeterministic system state.  
Proposed change: Default `run=None` and resolve `subprocess.run` inside `battery_window`, or inject the runner through the production closure. Add a no-real-I/O assertion.

P7  
Location: `benchmark/bench/p426_reconcile.py:72-80`  
Severity: minor  
Evidence: confirmed — traced in source and reported by the frozen suite  
Problem: Adding `client_abort=None` to `ItemReport` changes `dataclasses.asdict()` for every non-client row, violating the byte-identical-report requirement.  
Concrete failure scenario: Existing/golden consumers receive an additional top-level key on ordinary completed and probe-kill reports; 18 frozen invariant cases fail for this reason.  
Proposed change: Keep client-abort provenance outside the baseline `ItemReport` shape and add it only while constructing the two affected item records.
