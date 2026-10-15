Review of commit `bfede506` against parent `b5b4cd53`.

P1 — blocker — Round-1 P2 is not closed  
File: `benchmark/bench/proc_guard.py:366-389`; `benchmark/bench/tests/test_c157_proc_guard.py:185-198`

Failure scenario: a child is created after the preceding tick. During `kill_role()`’s tick, its unreadable parent exits and reparents it. `_listing_edges()` runs only after that event, so it sees the new PID-1 parent; `_ppid_history` lacks the fresh child. The local pre-exit `ppids` observation is not added to `_note_unreadable()`. Cleanup therefore records no child and can return clean while it survives.

The P2 test passes because it explicitly calls `g.tick()` first, seeding `_ppid_history`; that prerequisite is not guaranteed in production.

Fix: capture listing edges before start-order reads can observe disappearance, or merge current-tick pre-event `ppids` into the unreadable record.

P2 — blocker — Round-1 P3 remains open after a readable transition  
File: `benchmark/bench/proc_guard.py:742-758,881-890`; `benchmark/bench/tests/test_c157_proc_guard.py:200-217`

Failure scenario: an unreadable identity becomes readable, so its key enters `cleared` and triggers one full scan. After that scan but before reconciliation, its PID is reused by a path-attributed process. `_existence()` now returns `gone`, but the key is already in `cleared`, so `newly` is empty and no further scan examines the replacement. Cleanup can report clean.

The test covers unreadable→replacement, but not unreadable→readable→replacement.

Fix: track reconciliation state/epoch rather than a permanent cleared set. Every relevant state transition, including readable→gone/reused, must force another full scan.

P3 — blocker — Round-1 P4/P5 are only partially closed  
File: `benchmark/bench/proc_guard.py:683-716`; `benchmark/bench/tests/test_c157_proc_guard.py:220-245`

Failure scenario: A is unreadable, B’s `ppid()` is unreadable, and readable edge C→B exists. `_note_unreadable()` traverses known edges before adding B from `unknown`, so C is never added. If A and B vanish and C reparents to PID 1, reconciliation proves B gone and can clear while C survives.

Additionally, a stale `_ppid_history` edge can mark a reused PID as seen and suppress the current unknown-parent identity.

The tests separately cover a fully readable A→B→C chain and an unreadable-parent leaf, but not their composition.

Fix: add unknown-parent candidates before computing closure, use an identity-aware adjacency graph, and prefer current-listing identities over historical edges.

P4 — blocker — stale unreadable observations cause false uncertainty  
File: `benchmark/bench/proc_guard.py:313-314,366-389,698-716,800-801`

Failure scenario: an unrelated process flickers unreadable, later becomes fully readable, and subsequently exits before cleanup. Its `_unreadable_seen` entry is never removed. Cleanup treats its historical children—or every historically unknown-parent process—as children of a vanished unreadable process and aborts despite the intervening readable state having resolved the ambiguity.

Fix: retire an unreadable observation after a complete readable classification pass, while preserving race-safe state needed until that pass completes.

P5 — should-fix — monitor work and retained state are unbounded  
File: `benchmark/bench/proc_guard.py:366-379,683-716`

`_note_unreadable()` repeatedly scans the complete edge list for every frontier node: O(N²) per unreadable root and O(U·N²) per tick, all under `self.lock`. `_unreadable_seen` is never pruned and can retain O(events·N) descendants; cleanup repeatedly reconciles the accumulated history. A 0.5-second monitor interval does not bound tick duration, so spawn and cleanup can block behind this lock.

Fix: build adjacency maps and traverse each graph in O(N+E), prune resolved entries, and impose a fail-closed work/state bound.

Round-1 disposition: P2 not closed; P3 not closed; P4 and P5 partially implemented but not closed.

Verdict: **not cleared**.
