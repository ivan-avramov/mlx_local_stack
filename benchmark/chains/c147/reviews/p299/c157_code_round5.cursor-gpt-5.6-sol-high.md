Reviewed commit `8f392494` against parent `b06a01a5` read-only. Tests were not executed.

Round-4 disposition:
- P1 closed: occupied but identity-unreadable PIDs remain present.
- P2 closed: descendant occupancy now participates in convergence.
- P3 operationally closed: storage and closure traversal are bounded.

1. P1 — should-fix — protected recovered child remains falsely uncertain  
   File: `benchmark/bench/proc_guard.py:789-795`

   Failure scenario: a candidate child was recorded as `(pid, None)` while its identity was transiently unreadable. It later becomes fully readable and proves pre-existing/protected. The cleanup scan correctly excludes it, but reconciliation treats every occupied `child_created is None` PID as unresolved without checking `_protected()`. Cleanup therefore fails despite the process being demonstrably unrelated.

   Fix: distinguish readable-and-protected occupancy for unknown identities and clear it; retain uncertainty for readable but unprotected/ambiguous occupants. Add a recovered protected-child regression test.

2. P2 — nit — the stated 2048-identity cap excludes roots  
   File: `benchmark/bench/proc_guard.py:704-715`; `benchmark/bench/tests/test_c157_proc_guard.py:320-330`

   Failure scenario: `room` counts only child entries. The store can retain 32 roots plus 2048 children, although the round-4 contract said 2048 identities in all. The test also counts only children and merely asserts `<= 2048`, so accidental under-retention would pass.

   Fix: include roots in the identity budget and test the exact boundary, first overflow, and unchanged state after overflow.

No new false-clear was found. `_unreadable_seen` is bounded; `_ppid_history` does not exist. Tick/cleanup mutations are serialized by the existing lock, and monitor exceptions are captured and surfaced during cleanup.

Verdict: cleared after fixes P1
