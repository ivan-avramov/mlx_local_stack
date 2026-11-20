Verification dispositions:

- Y1 — resolved. `_reconcile()` reaches `_open_step_at_signal()`, which requires `in_flight_at_kill` to be an exact integer zero (`p426_reconcile.py:386-396`).
- Y2 — not resolved end-to-end; see P1.
- Y3 — not fully resolved. Stable live-leader and unreadable-leader cases fail closed, and no stable path leaves an old live probe-session survivor unclaimed. A reuse race remains; see P2.
- Y4 — not resolved; see P3.
- Y5 — resolved. Both post-client join paths call `_record_finish()` (`arm_runner.py:788,968-1018`); abort handling separately records pre-cancel faults.
- Y6 — the 64-character cap is resolved (`proc_guard.py:912-922`), but executable identity is not guaranteed; see P5.
- Clarification 1 — the `path_only` cap is resolved (`chain_ops.py:1060-1067`), with the same identity defect in P5.
- Clarification 2 — resolved. `GradeWorker.finish()` removes the faulted boundary from `pending` and `stall_wait` without adding trajectory evidence, before final grading (`arm_runner.py:318-326,788,846-852`). The final grade—not the interim fault—determines convergence.
- Push/harvest refusal propagation remains fail-closed apart from P3 and P6. No additional over-heavy mechanism was found.

P1 — Docker cleanup masks the typed Y2 fault

- Location: `benchmark/bench/structured_grade.py:395-437`; `benchmark/bench/proc_guard.py:1053-1091,1366-1374`
- Severity: major
- Evidence: confirmed by call-chain tracing.
- Problem: `_grade()` raises the new typed `GraderInfraError`, but its `finally` calls `remove_container()`. An `OSError`, timeout, or plain `TransportAbort` there replaces the primary typed fault. `final_grade()` therefore cannot apply item regrading or harness-fault routing.
- Failure scenario: Docker is unavailable during inspection and removal. `container_oom()` raises `GraderInfraError`, then removal raises `OSError`; the leg aborts on the latter instead of regrading that item.
- Proposed change: preserve the primary exception and attach cleanup failure as evidence. When cleanup is the primary failure, normalize it to the typed cleanup-uncertain route.

P2 — Session reuse can occur after Y3’s one-time leader check

- Location: `benchmark/bench/chain_ops.py:1002-1081`
- Severity: major
- Evidence: confirmed by source tracing.
- Problem: `owned_scan()` validates the recorded session leader before obtaining `psutil.pids()`. If the leader was absent, its PID can be reused between those operations; the replacement session then satisfies `getsid(pid) == owner` and the start lower bound and is killed.
- Failure scenario: the old session has ended; the initial lookup reports no leader. During a slow process-table scan, an unrelated same-UID process reuses that PID as a session leader. The scan kills it and its listed members.
- Proposed change: capture the process-list snapshot first, then validate the leader identity represented by that snapshot before making session claims. Any newly present mismatching or unreadable leader must disable session ownership and pause.

P3 — Y4’s null-record exception is authorized by any accounting entry

- Location: `benchmark/bench/p426_hooks.py:92-125,145-163`; producers at `benchmark/bench/chain_core.py:2906-2918,3188-3211`; consumers in `p426_freeze.py:413-465` and `p426_harvest.py:701-769`
- Severity: major
- Evidence: confirmed by source tracing.
- Problem: `recorded_accounting()` returns both ordinary accounting faults and done-hook infrastructure failures. Consequently, any nonempty reason permits `item_record_sha256: null`, although that exception is specified only when the done-step failure prevented the item record.
- Failure scenario: an ordinary boundary-count fault has an existing item record and chain accounting entry, but its sealed sidecar accidentally names no record. Chain validation, freeze, and harvest all accept it.
- Proposed change: record typed provenance such as `record_missing_allowed` or `source: done_hook_failure`, and permit null only for that typed route. Also require the referenced item record to be regular and self-sealed in the shared validator.

P4 — A transient identity read can turn a reused PID into killable ancestry

- Location: `benchmark/bench/proc_guard.py:935-970,1382-1435`
- Severity: major
- Evidence: confirmed by source tracing.
- Problem: `_ancestry()` seeds ownership by bare PID when the tracked identity’s start time is unreadable. If `_classify()` subsequently reads a different, reused identity, membership in the PID-only ancestry set still classifies it as owned.
- Failure scenario: a tracked process exits and its PID is reused. The first start-time read transiently fails; the second succeeds for the unrelated occupant, which is then killed as ancestry.
- Proposed change: retain expected identity/provenance in the ancestry closure. A later readable identity mismatch must become foreign or uncertain, never owned.

P5 — Capped `argv[0]` is not necessarily executable identity

- Location: `benchmark/bench/proc_guard.py:912-922`; `benchmark/bench/chain_ops.py:1060-1067`
- Severity: major
- Evidence: confirmed by source tracing.
- Problem: both records derive “identity” from `cmdline()[0]`. A title-style `argv[0]` can contain customer text, credentials, or status content; truncating it does not make it executable identity.
- Failure scenario: a daemon sets its title to a customer or token-bearing string. Up to 64 bytes are persisted into public `foreign_new` or `path_only` data.
- Proposed change: derive identity from `Process.exe()` or another verified executable name. Persist only that basename plus `argc`; use an empty/unknown identity if it cannot be read.

P6 — Watcher public records persist insufficiently scrubbed arguments

- Location: `benchmark/m1/bench_watch.py:489-503,540-568`; publication at `benchmark/bench/p426_harvest.py:1075-1090`
- Severity: major
- Evidence: confirmed by source tracing.
- Problem: `BoxSampler` records six complete arguments. Its default scrub only makes paths portable and replaces the username, while `watch.jsonl` is a main/public record subject to stronger PII and secret checks.
- Failure scenario: a normal high-CPU background daemon has an email address or credential in an argument. Harvest either refuses the leg because of unrelated environmental noise or publishes content not recognized by the scanner.
- Proposed change: comprehensively redact before persistence; when sanitization cannot be proven, retain executable identity, ownership, and argument count only.No follow-up needed; both reviews were already incorporated.
