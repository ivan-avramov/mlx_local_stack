Disposition verification: R1–R7 and R9–R16 are resolved by v1.1. R8 is not resolved because the terminal-DNF and abort-path machinery remains incomplete. The new §12 push binding is sound against the current `local_gate` flow.

P1
- Location: spec §5.2, §5.6; `p426_hooks.py:245-296`; `chain_core.py:2899-2943`; `chain_rows.py:350-417`
- Severity: major
- Evidence: confirmed
- Problem: `accounting_fault` has no disposition or durable row-annotation path. Reconciliation runs after the probe has written the row. The named new dispositions are only `harness_fault` and `hold`; an accounting mismatch can therefore only remain `invalidate` or be silently accepted without the required flag.
- Concrete failure scenario: a completed row has a genuine request-count mismatch. `P426Hooks.after_attempt` records failed checks and returns `invalidate`, making the leg INVALID instead of keeping the outcome as C372 requires.
- Proposed change: add a sealed accounting-fault sidecar/list bound to slot, row hash and item record; return an explicit `accounting_fault` disposition that continues without rerun. Have `chain_rows` expose the logical row with that flag, and make harvest/reporting exclude its telemetry aggregates.

P2
- Location: spec §5.1, §5.5–§5.6; `chain_rows.py:54-59,180-217,350-417`; `chain_core.py:1467-1479`
- Severity: major
- Evidence: confirmed
- Problem: the second harness fault’s strict-fail DNF has no schema, sidecar, ledger kind, or slot-table branch. The stated consumer rule—exactly one accepted attempt with earlier `harness_fault` attempts—also excludes a terminal DNF and mixed cheat/fault histories. A shared absolute rerun index capped by `MAX_RERUNS` cannot represent two permitted cheats plus the separately capped harness-fault rerun.
- Concrete failure scenario: an item faults twice. No accepted row exists, so consumers reject it rather than score a harness-fault DNF. Separately, two cheats followed by one harness fault require rerun index 3, which current validation rejects.
- Proposed change: define a synthetic `harness_fault_dnf` row/list, sidecar and ledger kind; score it as strict failure. Validate cheat and harness-fault caps independently, allowing any valid ordering, and update freeze/harvest rules accordingly.

P3
- Location: spec §5.1, §5.3, §5.6; `chain_core.py:2598-2687,2864-2923`
- Severity: major
- Evidence: confirmed
- Problem: the specified `harness_fault` disposition only covers item barriers, but grader failures and uncertain cleanup arrive through the incomplete-invocation/abort path. P426 currently treats an abort without an allowed transport-DNF cause—and every hook infrastructure exception—as systemic invalidation. No second-cleanup-scan route is specified.
- Concrete failure scenario: grading raises an infrastructure error before a row is written. The manifest has no P426 transport-DNF cause, so `handle_p426_incomplete` aborts the leg instead of rerunning the item once.
- Proposed change: define typed abort stamps and a classifier in `handle_p426_incomplete` for grader faults and cleanup uncertainty. Persist the independent rescan evidence, require unchanged worker identity and zero in-flight work, then enqueue `harness_fault`; otherwise HOLD. Route hook infrastructure failures through the same state machine.
