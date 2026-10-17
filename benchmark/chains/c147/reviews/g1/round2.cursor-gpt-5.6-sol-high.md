Commit: `a93d83c6` — G1 round 2

Round-1 verification: P1’s exact second-order-read case is fixed; P2–P4 remain incomplete through P6–P9 below. P5’s global deadline override was removed, but its tests still miss P9.

P6 — high — `benchmark/bench/proc_guard.py:761-768`  
Failure: `_refresh_descendants()` skips every recorded `(pid, None)` root. If that root becomes readable/pre-existing, then spawns a young child, cleanup can resolve the root while never recording the child. The child is ignored while parented to the protected root and can survive cleanup. This violates independent descendant obligations.  
Fix: conservatively refresh unknown-identity roots. At minimum, refresh when the occupant is proven pre-existing under judgement (a); otherwise retain/expand the obligation fail-closed.

P7 — high — `benchmark/bench/proc_guard.py:386-400`, `942-968`  
Failure: after proving a process young and eligible, `ppid()` raising `AccessDenied` falls into the broad transient handler and is not recorded. A tracked parent can then be killed, leaving this untracked child detached; persistent denial is silently skipped, while recovered `ppid==1` is merely diagnostic.  
Fix: distinguish `NoSuchProcess` from `AccessDenied`; record post-eligibility parent/identity uncertainty through the unreadable-obligation path. Add a parent-killed-between-ticks test using the existing psutil-like `Exiting(fail=("ppid",))` fake.

P8 — high — `benchmark/bench/proc_guard.py:284-286`, `339-340`, `842-847`  
Failure: protection is PID-only. If a protected router/worker exits and its PID is reused, the replacement is skipped by scans. For `(pid, None)`, `_resolve()` also calls it resolved solely because the PID remains in `excluded_pids`, even if the occupant is young. This is broader than judgement (a) and violates exact identities.  
Fix: store protected `(pid, start_time)` identities. An unknown recorded identity may resolve through temporal continuity only when the current occupant is independently proven older than the guard—not merely because its PID is excluded.

P9 — medium — `benchmark/bench/proc_guard.py:912-1017`; `benchmark/bench/tests/test_g1_round2_proc_guard.py:240-280`  
Failure: a confirming outer scan may start before the deadline and finish after it. If reconciliation then reports no state change, line 1013 clears without setting `non_converged`. Retry sleeps at lines 971 and 998 are also not capped by remaining time. The fake-clock tests never exercise these production paths.  
Fix: check the deadline before and after every post-reconciliation scan/audit round, fail closed when a required confirmation finishes late, and route all retry sleeps through a remaining-time-capped helper.

Opinion (a): Sound only when “started before the guard” is proven from a stable, monotonic start-order read and revalidated for the same occupant. Ordinary exceptions should remain unresolved. It breaks when a read returns a wrong-but-plausible old value—stale prior-occupant caching or non-monotonic wall-clock fallback—or when PID-only protection substitutes for the age proof, as in P8. Darwin’s raw monotonic start-order path substantially reduces the timestamp risk.

Opinion (b): Do not add a general parent-chain exemption. Protected daemons are brokers: Docker can spawn children both independently and on behalf of the probe, so ancestry under the exact daemon does not prove non-ownership and creates a laundering path. Address false aborts with service-specific evidence such as container identity/inventory and verified removal.

Read-only review; tests were not executed.

VERDICT: NOT CLEARED
