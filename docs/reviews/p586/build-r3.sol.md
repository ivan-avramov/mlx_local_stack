P1 — resolved  
Location: `benchmark/bench/p426_reconcile.py:160-186,397-444`  
Severity: blocker  
Evidence: confirmed — source, amended frozen tests, and offline replay.  
Problem: Closed. Continuity now uses export wall time minus worker monotonic elapsed; local stamps are diagnostic only.  
Failure scenario: The DST-pause case now exceeds 120 seconds and invalidates.  
Proposed change: None.

P2 — resolved  
Location: `benchmark/bench/p426_reconcile.py:413-421`  
Severity: major  
Evidence: confirmed — source and foreign-export tests.  
Problem: Closed. Export session identity and ordered pre-abort assistant IDs are verified.  
Failure scenario: A foreign export with a recomputed SHA now fails provenance.  
Proposed change: None.

P3 — resolved  
Location: `benchmark/bench/p426_reconcile.py:160-170,399-415,476-483`  
Severity: major  
Evidence: confirmed — source and malformed-time tests.  
Problem: Closed. Both timestamps require ordered integer values; the provenance block uses only validated values.  
Failure scenario: Missing, textual, boolean, floating, or reversed timestamps invalidate without raising.  
Proposed change: None.

P4 — resolved  
Location: `benchmark/bench/p426_freeze.py:40,299-308`  
Severity: major  
Evidence: confirmed — source and both client-abort variants tested.  
Problem: Closed within the adopted scope. R3 accepts only the three probe-kill cases.  
Failure scenario: An R3 tree containing only `kill_client_aborted` is refused.  
Proposed change: None.

P5 — not resolved; retained as the declined residual  
Location: `benchmark/bench/p426_harvest.py:890-904`  
Severity: major  
Evidence: confirmed — traced in source.  
Problem: Dry-run still exits immediately for missing/malformed `leg.json`, an unknown state, or an attempt-name mismatch, contrary to the stated “every problem” behavior.  
Failure scenario: A malformed leg record hides independent classifier and secret-gate findings, although publication remains fail-closed.  
Proposed change: Accumulate structural errors during dry-run and continue checks whose prerequisites remain available.

P6 — resolved  
Location: `benchmark/bench/p426_leg.py:426-432`  
Severity: major  
Evidence: confirmed — source and hermetic subprocess test.  
Problem: Closed. `subprocess.run` is resolved at call time.  
Failure scenario: The patched runner now receives `pmset`; no host process starts.  
Proposed change: None.

P7 — not resolved as a literal requirement; runtime impact remains unsubstantiated  
Location: `benchmark/bench/p426_reconcile.py:73-80`; `docs/specs/p586-relaunch-build.md:64-68`  
Severity: minor  
Evidence: confirmed — `dataclasses.asdict(ItemReport)` still gains `client_abort: None`; no production serializer was found.  
Problem: The code contradicts the build spec’s “byte-identical reports” wording, although serialized item records remain unchanged.  
Failure scenario: A direct `asdict()` consumer or golden comparison sees an extra key.  
Proposed change: Clarify the spec to permit the optional internal field, or keep client-abort provenance outside `ItemReport`.

X6 — resolved  
Location: `benchmark/bench/p426_leg.py:248-266`  
Severity: major  
Evidence: confirmed — source and DST tests.  
Problem: Closed. Receipt stamps are marked UTC and unmarked text is refused.  
Failure scenario: Local and UTC meanings can no longer silently share one format.  
Proposed change: None.

X7 — resolved  
Location: `benchmark/bench/p426_harvest.py:835-860,922-979`  
Severity: blocker  
Evidence: confirmed — source, frozen tests, and clean dry-runs over all three real attempts.  
Problem: Closed. Public `HARVEST.json` contains only folded directory metadata; per-file private-state names remain evidence-only and pass through the evidence scrub/secret gate.  
Failure scenario: Go’s email-shaped telemetry filenames no longer reach public `main`; credentials, operator addresses, or private-state contents still cannot be published there.  
Proposed change: None.

X8 — resolved  
Location: `benchmark/bench/p426_harvest.py:184-189,863-880,1014-1118,1164-1210`  
Severity: major  
Evidence: confirmed — source and namespace tests.  
Problem: Closed. Namespace validation covers attempt destinations, published paths, dossiers, run records, and CLI harvests.  
Failure scenario: The superseded v8 can publish under `wave2.v8-af0711cf` without colliding with the relaunch.  
Proposed change: None.

P8  
Location: `docs/specs/p586-relaunch-build.md:42-56`; `docs/specs/p426-b2-tg1-wave2.md:170-181`  
Severity: major  
Evidence: confirmed — both specs still prescribe local-stamp subtraction and `0 ≤ gap`, contrary to the fixed implementation and amended acceptance tests.  
Problem: The authoritative documentation retains the DST-unsafe algorithm P1 removed.  
Failure scenario: A future conformance change follows the spec and reintroduces the fallback-hour false acceptance.  
Proposed change: Specify `close_gap_s = assistant wall_s − last telemetry elapsed_s`, validated message times, no local-stamp input, and the `[-5,120]` bound.

P9  
Location: `docs/specs/p426-b2-tg1-wave2.md:391-392`; `benchmark/bench/p426_harvest.py:835-860`  
Severity: minor  
Evidence: confirmed — traced in source.  
Problem: The harvest spec still says `HARVEST.json` maps every file individually, but X7 deliberately folds private-state files and places their listing in evidence.  
Failure scenario: A consumer or later maintainer treats the intentional folded records as incomplete.  
Proposed change: Document the folded private-directory entry and evidence-only listing.
