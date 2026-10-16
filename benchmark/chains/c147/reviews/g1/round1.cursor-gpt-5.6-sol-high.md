Commit: `5f9fdbc4` — `fix(bench): G1 — guard reconciliation: one 10 s monotonic deadline; recovered readability alone discharges no recorded unreadable obligation …`

P1 — HIGH — later tick read failures are never recorded  
`benchmark/bench/proc_guard.py:374-391`

`_protected(p)` reads start order once, then line 386 reads it again. If that second read raises `AccessDenied`, the outer handler merely removes `alive`/`ppids`; it never calls `_note_unreadable`. Once readable, the process becomes a never-recorded G2-style orphan and can clear despite having been live and order-unreadable, violating G1.

Fix: after eligibility is established, route any `AccessDenied` from identity/order classification through `_note_unreadable`; only `NoSuchProcess` may disappear silently. Add a fake that succeeds on the first order read and denies the second.

P2 — HIGH — descendant obligations are still lost  
`benchmark/bench/proc_guard.py:392-398`, `829-835`, `892-905`

Three paths violate independent descendant reconciliation:

- `tick()` deletes the entire root entry when the root proves protected, including its recorded children.
- `_reconcile_unreadable()` skips every child when the root is protected.
- Cleanup only adds descendants when the root is currently unreadable. A child spawned after the last tick is never added if the root has recovered readability. If the root exits during reconciliation and the child reparents, it becomes a reasonless G2 orphan and cleanup can clear.

The tests miss this: the protected-root test has no child, while the descendant test creates the child before `tick()`.

Fix: retain root and descendant obligations separately; refresh descendants from every cleanup listing for every exact recorded root, readable or not; reconcile each child independently. Add protected-root-with-young-child and child-spawned-after-last-tick tests.

P3 — HIGH — unknown and raced identities can be discharged by another occupant  
`benchmark/bench/proc_guard.py:792-808`, `820-835`

For `(pid, None)`, `_existence()` can report a readable current occupant and `_readable_root_resolved(pid)` can classify that occupant as protected/tracked/path-attributed. With no children, the unknown original obligation clears. That contradicts exact identities and “unknown fail-closed.”

For known identities, the helper performs a second unbound `get(pid)` without rechecking against the recorded start time. PID reuse between the two reads can classify the replacement. Additionally, `_is_protected()` converts inspection exceptions to `False`, permitting fall-through to attribution rather than uncertainty.

Fix: resolve against `(pid, expected_start_time)`, revalidate identity on every decisive read, and use tri-state results. An occupied `(pid, None)` remains unresolved until the PID is absent; a replacement resolves only the original as gone and must still be scanned independently.

P4 — MEDIUM — the deadline does not govern all rounds  
`benchmark/bench/proc_guard.py:884-980`

The deadline is correctly created once immediately before the first reconciliation, but:

- A state change observed at or after expiry starts another full round.
- Up to four rounds can therefore run after expiry—up to roughly 1.2 seconds of explicit retry sleeps, plus scans/system calls.
- Conversely, five rapid state-changing rounds produce `scan did not converge` before the deadline.

Fix: make the monotonic deadline control the outer scan/reconcile loop. At expiry, any state change still requiring a confirming scan is unresolved. Bound sleeps by remaining time.

P5 — MEDIUM — tests conceal production deadline behavior  
`benchmark/bench/tests/conftest.py:341-346`, `benchmark/bench/tests/test_c157_proc_guard.py:591-672`

The autouse 0.2-second class override means no ordinary test constructs a production-default guard. The expiry test only asserts elapsed time is below five seconds, so an immediate abort would pass. Missing cases include P1–P3, cross-round expiry, and the required after-last-tick descendant.

Fix: remove the global override, inject clock/sleep for deterministic deadline tests, assert the production default is exactly 10 seconds, and retain one bounded real-time lower/upper-bound test.

False-abort risk

For a benign young same-UID system process that flickers order-unreadable once, then remains alive/readable, untracked and path-negative, G1 makes the conditional abort probability 100%: its obligation cannot be attributed and cleanup waits ten seconds before aborting.

At the 0.5-second tick interval, a one-hour item has about 7,200 observation opportunities. If `q` is the aggregate independent per-tick probability of such a lasting event:

`P(abort) = 1 - (1 - q)^7200`

Illustratively: `q=10⁻⁴ → 51.3%`, `10⁻⁵ → 6.95%`, `10⁻⁶ → 0.72%`. These are mechanism bounds, not measured rates. Reducing this risk requires stronger ownership evidence; silently retiring the record would violate G1.

I did not execute tests during this read-only review.

not cleared
