Review of commit `9067da52` against parent `bfede506`. Read-only review; tests were not executed.

Round-2 disposition:
- P1: closed for the reported pre-cleanup interleaving.
- P2: not closed.
- P3: not closed; traversal ordering is fixed, identity handling is not.
- P4: not closed.
- P5: not closed.

P1 — blocker — PID reuse can preserve the same reconciliation state  
File: `benchmark/bench/proc_guard.py:722-744,884-895`

Failure scenario: an unreadable identity disappears, producing state `"gone"` and causing another scan. It is absent during that scan. Before reconciliation, a path-attributed replacement takes the same PID. `_existence()` also reports `"gone"` for PID reuse, so the state remains `"gone"` and no further scan examines the replacement. Cleanup can return clean while it survives.

The new test covers readable→reused, where the state changes. It does not cover gone→reused, where it does not.

Fix: make reconciliation observations identity-sensitive—distinguish absent from a currently occupied PID and include the observed replacement identity. Every occupancy/identity change must force a bounded subsequent scan.

P2 — blocker — `tick()` retires unreadable records without a complete or matching classification  
File: `benchmark/bench/proc_guard.py:380-391`

Failure scenario: `readable[p.pid]` is set immediately after `_protected()`. If the later `ppid()`, `start_time()`, or `start_order()` operation raises transiently, the outer handler removes `alive` but leaves `readable`; the historical record is then deleted despite an incomplete pass.

Worse, a record with identity `(pid, None)` is removed whenever any readable process occupies that PID because `None` is treated as a wildcard. A replacement can therefore erase the vanished original’s recorded descendants, allowing a reparented child to survive cleanly.

Fix: mark an identity resolved only after every required classification operation succeeds. Match exact identities; never clear a `created=None` record merely because its PID is readable. Add partial-read and unknown-identity PID-reuse tests.

P3 — blocker — descendant storage is still not identity-aware  
File: `benchmark/bench/proc_guard.py:706-719,762-777`

Failure scenario: an unknown-parent candidate is stored as `children[pid] = created`. If it exits and another unknown-parent process reuses that PID, line 713 refuses to update the existing entry. Reconciliation checks the old identity, finds it gone, and clears it. The live replacement is skipped by the ordinary scan when its `ppid()` remains unreadable.

Thus round-2 P3’s requested identity-aware graph was not implemented.

Fix: store candidate identities rather than one value per PID, update observations from each listing, and reconcile current PID occupancy conservatively.

P4 — should-fix — retained state and monitor work remain unbounded  
File: `benchmark/bench/proc_guard.py:369-378,700-720`

The 128 limit caps unreadable roots only. Every root’s `children` dictionary can accumulate distinct PIDs indefinitely. Each tick also traverses the complete adjacency graph separately for every retained unreadable root, under `self.lock`.

Consequences:
- memory up to `128 × distinct candidate PIDs over the run`;
- tick work up to `128 × O(N+E)`;
- unbounded cleanup reconciliation over accumulated children;
- delayed spawn/cleanup behind the monitor lock.

Fix: impose a total retained-identity/work bound that fails closed, and compute shared closure rather than traversing the graph independently per root.

P5 — should-fix — the composed-descendant test can pass for the wrong reason  
File: `benchmark/bench/tests/test_c157_proc_guard.py:271-289`

`test_r2p3_a_child_of_an_unknown_parent_process_is_a_candidate_descendant` accepts any `"cleanup uncertain"` result. It does not prove PID 52 was retained with reason `"child of vanished unreadable process"`; uncertainty from A or B would also pass.

Fix: assert the expected PID and reason in both the exception and published status. Add regressions for P1–P3 above. The overflow test should also exercise accumulating descendants, not only 130 roots with no children.

Verdict: **not cleared**.
