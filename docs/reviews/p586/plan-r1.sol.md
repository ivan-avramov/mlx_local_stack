1. Location: `material/plan.md:17-22` (P586)  
Severity: blocker  
Evidence: confirmed — the supplied row has no client-side close provenance; the only causal evidence is the server’s `stream_closed_before_completion` line.  
Problem: The proposed predicate cannot distinguish an intentional client close from a client crash, transport disconnect, server-side abort, or harness kill whose record was lost. Accepting it violates the requirement that unexplained client/server mismatches invalidate.  
Concrete failure scenario: Request 3 is interrupted by a proxy failure or client-process crash. The server records the same trailing failure; the probe later reports `client_inactivity` with empty termination fields. P586 classifies the infrastructure fault as a scored model failure.  
Proposed change: Require durable client-side close provenance tied to the request, plus a kill-intent record written before any harness kill. Without affirmative provenance, keep the item systemic/DNF. The historical record cannot safely be reclassified from the supplied evidence alone.

2. Location: `material/plan.md:17-22`; `material/p426_reconcile_item.py.txt:52-70`  
Severity: major  
Evidence: confirmed — P586 omits existing kill marker `gate.requests_completed_at_kill` and never checks `requests_observed`.  
Problem: The textual predicate accepts both a partially recorded harness kill and a request the client did not observe.  
Concrete failure scenario: `requests_completed_at_kill=2` is persisted, but termination writing fails; alternatively, the row says `requests_observed=2` while the server window contains two completions and a foreign third start/failure. Both satisfy P586 as written.  
Proposed change: Require every kill marker, including `requests_completed_at_kill`, to be null; require `requests_observed == |S|`; and add red tests for both deviations.

3. Location: `material/plan.md:17-22`; `material/spec_4.3.md:13-18`; `material/p426_reconcile_item.py.txt:25-29,64-70`  
Severity: major  
Evidence: confirmed — §4.3 permits `client_inactivity` with a trailing completed-but-unaccounted request, but current reconciliation requires `in_flight_at_kill ≥ 1`; P586 only adds the failed-line variant.  
Problem: A legitimate race remains systemic when the server completes after the client closes but before noticing the disconnect.  
Concrete failure scenario: Request 3 is started and completed server-side, while `request_usage` and the gate retain only two observed completions and termination remains empty.  
Proposed change: Add a provenance-backed `kill_client_closed_completed_unaccounted` case with `|C|=len(request_usage)+1`, trailing completion, matching session, `requests_observed==|S|`, and equivalent negative tests.

4. Location: `material/plan.md:28-31`; `material/chain_core_web_evidence.py.txt:31-47`  
Severity: major  
Evidence: confirmed — existing `after_invocation` reuses `rec["web_evidence"]` and then unconditionally appends `disposition="accepted"`.  
Problem: Merely recording the invalidated slot’s extraction can turn that invalidated slot into an accepted attempt during reuse.  
Concrete failure scenario: The barrier stores crypto-square’s path/hash; `after_invocation` reuses it, appends an accepted slot attempt, and later consumers or reruns treat the invalidated item as already accepted.  
Proposed change: Persist an explicit invalidated-slot tombstone that both later passes skip. Test final `slot_attempts` contents and assert that no accepted entry is created.

5. Location: `material/plan.md:33-36,42-44`; `material/spec_1.md:9-12,30-33`  
Severity: major  
Evidence: confirmed — R2 invalidates and stops on its first Python item, before the newly appended Go items; R1/R3 exercise Go only on non-systemic paths.  
Problem: The actual P588 shape—an invalidated Go slot with already-extracted web evidence—is not rehearsed. Adding Go after R2’s stopping item cannot exercise it.  
Concrete failure scenario: Unit tests pass, but the first invalidated Go row still mishandles its `go__*.web.jsonl` record and aborts the long run.  
Proposed change: Add a dedicated rehearsal invalidation on a Go item after web extraction, or move/add an injection so that this path reaches a clean `INVALID` result.

6. Location: `material/plan.md:44-50`; `material/spec_1.md:37-40`  
Severity: major  
Evidence: confirmed — changing the runtime out-base to `wave2b/` does not change the specified attempt names or public harvest destination `benchmark/results/p426/wave2/<leg>.a<n>/`.  
Problem: The superseded and new runs can both produce names such as `tg1-p426-off-pilot.a1`, causing harvest-path and dossier-reference collisions.  
Concrete failure scenario: Harvesting the old attempts creates the public paths first; harvesting the new v8 is then refused or resolves dossier references to old records.  
Proposed change: Include a unique run/v8 identifier in attempt identity, harvest paths, and dossier references, or continue globally unique attempt numbers. Specify that old harvesting completes under its distinct namespace before publishing the new run.
