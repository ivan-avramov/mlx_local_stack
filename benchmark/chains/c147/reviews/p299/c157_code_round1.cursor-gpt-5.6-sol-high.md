Review of commit `b5b4cd53` against parent `da269033`.

P2 — blocker — pre-cleanup `kill_role()` can consume the race and discard ancestry  
File: `benchmark/bench/proc_guard.py:365-376,525`; `benchmark/bench/tests/test_c157_proc_guard.py:14-18`

Failure scenario: `kill_role()` calls `tick()` before the new reconciliation logic. If an unreadable parent exits during that tick and reparents its child, `tick()` silently drops the parent on `AccessDenied`. The later cleanup scan sees only a young PID-1 orphan, records it without a reason, and can report clean while the child survives.

The tests explicitly stub `kill_role()` because it would consume this event, so the production path is untested.

Fix: preserve unreadable-process identities and ancestry edges observed by `tick()` and merge them into cleanup reconciliation. Add an end-to-end test using real `kill_role()`.

P3 — blocker — final reconciliation can clear a PID replacement without rescanning it  
File: `benchmark/bench/proc_guard.py:833-840`; `benchmark/bench/tests/test_c157_proc_guard.py:66-83`

Failure scenario: the round reconciliation sees an unreadable process still present and exits the round loop. The separate “authoritative” reconciliation then observes its disappearance or PID reuse. `_existence()` clears the original identity, but no subsequent process-table scan examines the replacement. A path-attributed replacement can therefore survive with clean status.

`test_exiting_after_the_first_recheck_still_clears_the_reason` passes specifically through this unsafe final-only transition.

Fix: every newly vanished identity must trigger another complete scan. Remove the unpaired final reconciliation; if the retry bound is reached after a new disappearance, publish non-convergence uncertainty.

P4 — blocker — only direct children are retained  
File: `benchmark/bench/proc_guard.py:701-717,765-768,781-784`

Failure scenario: unreadable parent A has child B and grandchild C. A and B exit during cleanup; C reparents to PID 1. Reconciliation records only B, proves B gone, and clears A. C is merely a reasonless orphan, which does not make cleanup uncertain, so C survives a clean result.

Fix: preserve the transitive descendant closure—or the complete parent-edge graph—from the listing. Reconcile every descendant independently. Add a three-generation regression test.

P5 — blocker — transient `ppid()` failure silently removes a direct child from reconciliation  
File: `benchmark/bench/proc_guard.py:751-755`

Failure scenario: a listed child’s `ppid()` raises transiently while `parent_of` is built. The edge is silently discarded. When its unreadable parent vanishes, the child is absent from reconciliation and can later appear only as a non-blocking reasonless orphan.

Fix: retry or retain an unresolved-parent record. Cleanup must remain uncertain until that listed process is gone or independently classified.

The four-round/three-attempt structure is bounded. Container precedence, monitor-before-uncertainty ordering, status publication before raises, path-only attribution, tracked audit, survivor raising, and the unchanged identity/access-denied handlers otherwise remain consistent with prior semantics.

Verdict: **not cleared**.
