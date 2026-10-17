Commit: `2333ec5f` — G1 round 3

Round-2 verification: P6–P8 are resolved. P9 is incomplete as P10.

P10 — medium — `benchmark/bench/proc_guard.py:1052-1066`  
Failure: lateness is sampled before reconciliation. If `_reconcile_unreadable()` crosses the deadline and returns an unchanged clean state, cleanup certifies success. The new test advances time only during `scan()`.  
Fix: check the deadline after reconciliation, immediately before accepting confirmation; add a clock advance inside `_resolve()`.

P11 — high — `benchmark/bench/proc_guard.py:361-365,448-451`  
Failure: parent revalidation maps `AccessDenied`/`NoSuchProcess` to ordinary mismatch. A listed child of a tracked parent is then left untracked; after the parent exits or is killed, the child can survive cleanup.  
Fix: use tri-state parent validation and preserve the captured child as a descendant obligation when validation is unknown or the parent raced away.

P12 — high — `benchmark/bench/proc_guard.py:982-1015`  
Failure: after identity and eligibility succeed, `AccessDenied` from `cwd()`, `cmdline()`, or another later classification read is silently ignored for untracked processes. A persistent owned process can therefore clear cleanup. Existing tests exercise `cwd()` only through `_resolve()`, not this production scan path.  
Fix: record the exact identity through `_note_unreadable()` and reconcile it fail-closed.

P13 — high — `benchmark/bench/proc_guard.py:374-382`  
Failure: `_processes()` silently drops a same-UID process when `status()` raises `AccessDenied`. It consequently disappears from ancestry, descendant, and cleanup scans. The fakes cannot reproduce this because `Exiting` does not support failing `status()` or `uids()`.  
Fix: separate UID and status reads; once same UID is established, retain status-denied entries as unreadable obligations. Add psutil-shaped fake coverage.

Read-only review; tests were not executed.

VERDICT: NOT CLEARED
