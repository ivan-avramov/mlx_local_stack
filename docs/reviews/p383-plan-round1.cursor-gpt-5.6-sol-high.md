Reviewed `4849a2ae`; current `HEAD` is `d2ec4be6`, but the relevant files are unchanged between them.

R1 — Severity: BLOCKER; Section: §1 retry coverage  
Problem: Crash-resume bypasses A7. `prepare_resume()` hydrates a running invocation, then `salvage_hook_stops()` validates only the row prefix. A persisted pre-spawn incident or cheat disposition can therefore launch its retry/rerun with `uncertain`, survivors, `unknown`, incomplete cleanup, or malformed schema.  
Fix: Before salvaging any stop that implies retry/rerun, apply the same M64 cleanup validator to the hydrated receipt and persist the result before another invocation starts.

R2 — Severity: HIGH; Section: §1 evidence persistence  
Problem: `persist_pre_spawn()` creates its incident before cleanup exists. Neither the live path nor resume backfills that incident, so C180’s requirement that orphans be recorded “in the incident” is unmet. Adding a duplicate field to `attempts[]` is unnecessary because its full `cleanup_status` is already durable. Also, `chain.json.progress` is not where attempts live.  
Fix: Add orphans to ordinary incidents in `record_incident()` and backfill matching pre-spawn incidents after the cleanup gate, including resume. Persist before recovery/retry. DNF rows will then inherit both incident records automatically. If cryptographic binding is claimed, add a canonical cleanup-receipt hash; the existing invocation SHA covers rows, not cleanup.

R3 — Severity: HIGH; Section: §1 fail-closed validation  
Problem: Every currently completed production receipt with a reason-bearing orphan also sets `uncertain=True`; reasonless detached orphans are the only safe-to-proceed class. But the proposed validator accepts any dictionary containing `pid`, allowing an inconsistent receipt such as `{"pid": 2, "reason": "scan did not converge"}` with `uncertain=False`.  
Fix: Reason-bearing orphans must always block independently of `uncertain`. Require at least `type(pid) is int and pid > 0`; preferably validate the real reasonless shape (`pid`, `create_time`, `argv`). Define invalid behavior for `cleanup_orphans()` explicitly rather than conflating malformed input with `[]`.

R4 — Severity: LOW; Section: §1 policy scope  
Problem: Relaxing `cleanup_problems()` globally also changes policy-agnostic `require_certain_cleanup()`, including its `abort_restart` branch. Current tg1 configuration cannot reach that hook path, but “tg1 unchanged” would depend on that incidental topology. The A7 specification still says every list must be empty.  
Fix: Make orphan allowance explicit for `incident_retry`, or use a separately named M64 validator. Amend `docs/specs/p371-shared-runner-core.md` A7 and the helper docstring. There are no other unrelated production readers; the second-incident DNF and fallback restart uses are in scope.

R5 — Severity: MEDIUM; Section: §1 tests  
Problem: The proposed matrix misses the paths most likely to conceal defects: crash-resume after persisted pre-spawn/cheat stops, pre-spawn incident backfill, second-incident DNF and sidecar propagation, archive persistence, reason-bearing orphans with false `uncertain`, missing/invalid/zero PID, and tg1 blocking when the orphan reason is accompanied by `uncertain=True`. The fake `{"pid": 2}` is weaker than a real guard record.  
Fix: Add those cases and assert the exact incident, attempt, DNF, sidecar, archive, and log-count evidence—not merely that another invocation starts.

R6 — Severity: BLOCKER; Section: §2 measurement fidelity  
Problem: 200 five-second cycles do not exercise the target races. They provide only about 1,000 guard-seconds and roughly ten monitor ticks per cycle, while real tg1 items can run about 60 minutes. The generator’s 1.5-second readable processes vanish well before the 10-second reconciliation deadline. It does not exercise persistent unreadability, non-convergence, overflow, child-of-vanished obligations, tracked audit, or production `kill_role()` behavior. Provoked Spotlight workers are expected mainly to produce reasonless orphans.  
Fix: Treat this design only as a light screen, or use item-shaped guard lifetimes/tick cadence and production cleanup. Include varied process lifetimes spanning the reconciliation deadline, known foreign path-attributed processes, parent/child exit churn, and production cleanup operations. Use deterministic fault-injection controls for denied-read paths that cannot reliably be provoked on the real box.

R7 — Severity: BLOCKER; Section: §2 decision rule  
Problem: The ≈3/200 rule-of-three bound assumes independent, identically distributed trials. Serial cycles on one box share Spotlight activity and are not independent, and a five-second-cycle probability is not a tg1 item or chain probability. Even the nominal one-sided bound of about 1.5% per cycle could imply an unacceptable probability of abort over a long chain. No acceptable chain-level false-abort threshold is registered.  
Fix: Pre-register the operational unit and risk threshold, report exposure in guard-hours and production-equivalent items, account for blocked/correlated observation windows, and translate the bound to whole-chain risk. Zero events may document this harness’s residual; it cannot by itself close the tg1 decision.

R8 — Severity: HIGH; Section: §2 attribution and controls  
Problem: “Caused by a non-ours process” is not operationally decidable from the receipt after the process exits. The receipt lacks session, ancestry, tracked status, root overlap, and observation history. An indeterminate event could therefore be omitted and let the study pass. A pytest implementation could also silently inherit the autouse hermetic scan and hide all ambient processes.  
Fix: Use a standalone harness or explicit real `psutil.process_iter` seam, record known generator PID/create-time identities plus contemporaneous lineage/session/path snapshots, and classify every event as ours/non-ours/indeterminate. Any indeterminate event must prevent closure. Add known-positive controls proving ambient visibility and classifier sensitivity.

R9 — Severity: MEDIUM; Section: §2 mechanism analysis  
Problem: The residual-path summary is incomplete. A `TransportAbort` during the sweep creates immediate `"identity unreadable"` uncertainty without C157 reconciliation; `"child of vanished unreadable process"` is distinct; tracked `unknown` is principally an ours-path, not a normal ambient path. Also, a readable ambient process is uncertain when path-attributed—only a readable, young, detached, non-path-attributed process becomes a reasonless orphan. File indexing under scratch does not exercise path-only attribution because `_attributed_path()` examines process cwd/argv, not files accessed.  
Fix: Correct the preregistered taxonomy and report each mechanism separately, including immediate versus reconciled identity failures. Add a foreign process whose cwd or argv names the guard root as the path-only positive control.

VERDICT: AGREE WITH CHANGES R1,R2,R3,R4,R5,R6,R7,R8,R9
