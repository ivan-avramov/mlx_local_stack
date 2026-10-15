Review of commit `b06a01a5` against parent `9067da52`. Read-only; tests were not executed.

Round-3 disposition:
- P1: not closed.
- P2: closed.
- P3: narrowly closed for identity-aware storage.
- P4: not closed.
- P5: closed.
- No `_ppid_history` exists; parent-edge maps are tick-local.

P1 — blocker — occupied-but-unreadable PID still aliases “absent”  
File: `benchmark/bench/proc_guard.py:739-744, 893-901`

Failure scenario: reconciliation first observes the original identity absent as `("gone", None)`, then performs another scan while the PID is empty. A replacement takes the PID afterward, but its `create_time()` raises `AccessDenied`. `_created_or_none()` returns `None`, so `_existence()` again returns `("gone", None)`. No state change is detected, no subsequent scan examines the replacement, and cleanup can report clean while a process from this run survives.

The new gone→reused test only covers a replacement whose creation time is readable.

Fix: never interpret failure to read an occupant’s identity as an identity mismatch. Represent occupied-but-identity-unknown distinctly—conservatively `"present"`—and force uncertainty or another scan.

P2 — blocker — descendant PID reuse does not participate in convergence  
File: `benchmark/bench/proc_guard.py:770-784, 893-901`

Failure scenario: a recorded descendant identity exits. After the final process-table scan, a path-attributed replacement takes its PID. `_identity_state()` reports the old identity `"gone"`, so reconciliation drops it. Only root states are returned in `states`; descendant occupancy changes therefore do not set `changed`. Cleanup exits without scanning the replacement.

The P3 test verifies that both descendant identities are stored, but never exercises cleanup or this scan/reconcile race.

Fix: include identity-sensitive observations for every recorded descendant in convergence state. Any absent→occupied, identity change, or unreadable occupancy must force another bounded full scan.

P3 — should-fix — the advertised retained-state cap does not cap storage or work  
File: `benchmark/bench/proc_guard.py:364-391, 700-724, 817-827`; `benchmark/bench/tests/test_c157_proc_guard.py:320-325`

Failure scenario: `_note_unreadable()` inserts every descendant and only afterward sets `_unreadable_overflow`. It never stops additions. Existing roots can accumulate new identities indefinitely on subsequent 0.5-second ticks. Each call also recomputes the total size and traverses a closure under `self.lock`, yielding unbounded monitor delay, cleanup work, and memory.

The new “capped” test explicitly asserts that retained children exceed 2048, so it passes while proving the cap is ineffective.

Fix: stop retaining identities at the limit, leave a permanent overflow sentinel, avoid further closure traversal after overflow, and compute shared listing closure once per tick. Assert retained size stays within the bound and cannot grow afterward.

Verdict: **not cleared**.
