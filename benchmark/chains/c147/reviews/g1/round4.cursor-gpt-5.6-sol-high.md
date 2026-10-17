Commit: `4d04d2b7` — G1 round 4

P10–P12 are resolved on their original paths. P13 remains incomplete.

P14 — high — `benchmark/bench/proc_guard.py:402-412,431-479,1012-1073`  
Failure scenario: `uids()` denial always skips the process, including an already tracked or exact protected identity whose ownership is known. Its children never enter the ancestry graph; after the tracked parent is killed or a protected daemon keeps running, a young child can survive a clean cleanup. The table’s “not known same-uid” premise is false for these identities.  
Fix: skip only genuinely unknown processes. Retain known tracked/protected/recorded identities as unreadable roots and capture their descendants.

P15 — high — `benchmark/bench/proc_guard.py:402-420,431-479,728-731,1012-1029`  
Failure scenario: P13’s status-denied obligation is delayed through shared `_live_denied`. A protected root bypasses it because `_protected()` runs first; a subsequent `NoSuchProcess` drops it; concurrent `descendants_alive()` can overwrite the set. Captured young children then remain unrecorded and can survive cleanup.  
Fix: return denied-status identities as scan-local data and materialize their root/descendant obligations immediately after constructing edges. Resolve a protected root independently without deleting its child obligations.

P16 — high — `benchmark/bench/proc_guard.py:783-796,848-861`  
Failure scenario: descendant evidence is lost in two races. `_listing_edges()` forgets a one-shot `AccessDenied` when its retry succeeds, and `_refresh_descendants()` collapses `AccessDenied`/`NoSuchProcess` to `None`, skipping children captured immediately before an exact root exits. A detached child can consequently clear as an unattributed diagnostic. The table misclassifies the first site and omits the unsafe refresh behavior.  
Fix: preserve every post-UID denial as an obligation. Refresh an existing exact root from captured edges when its identity becomes unknown or vanishes; skip only a proven different occupant.

P17 — high — `benchmark/bench/proc_guard.py:402-420,783-796,1012-1054`  
Failure scenario: `psutil.process_iter()` caches `Process` objects. After PID reuse, `uids()` and `status()` can read the replacement while identity-checking `ppid()` raises `NoSuchProcess` for the cached original. Cleanup treats that as disappearance, performs no confirming scan, and can clear while the replacement remains. `Flaky` cannot model this mixed old-object/new-occupant behavior.  
Fix: after post-UID `NoSuchProcess`, check the PID through a fresh process object and classify any occupant, or force another convergent full scan. Add a stale-psutil-object PID-reuse test.

P18 — medium — `benchmark/bench/proc_guard.py:1029-1073`  
Failure scenario: after `key = (pid, start_time)` is known, a later denial discards it: tracked processes become sticky `(pid, None)` uncertainty, while untracked processes reread identity. A transient denial followed by exit or reuse can misattribute the replacement and cause a false abort, violating exact-identity reconciliation.  
Fix: pass the captured `key` into `_note_unreadable()` and derive uncertainty from final exact reconciliation/audit results.

P19 — medium — `benchmark/bench/proc_guard.py:728-731`  
Failure scenario: `descendants_alive()` is absent from the table and does not handle `start_time()` exceptions. An ordinary exit between listing and identity read raises `NoSuchProcess`; `AccessDenied` also escapes instead of conservatively preserving the descendant possibility. Either can abort a long probe during silence sampling.  
Fix: let `NoSuchProcess` vanish, handle `AccessDenied` conservatively, and add this site to the table and parametrized tests.

VERDICT: NOT CLEARED
