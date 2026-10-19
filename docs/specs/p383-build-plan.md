# P383 build (C180 option a) + the tg1 side (P388) — PLAN v1, 2026-10-18

Status: v1 → Cursor `gpt-5.6-sol-high` plan review. Ruling: C180 (operator: "p383: go with your rec"). No GPU.
Branch / worktree: `p383-build` in `$STACK_WORKDIR/worktrees/p383` from `main`. One suite at a time (none while the fork
suite runs).

## 1. P383 build (chain side; M64 `incident_retry` only)

Today A7 (`bench/chain_incident.py::cleanup_problems`) requires the exact six-key `ProcessGuard.status()` receipt with every
list EMPTY, incl. `orphans_unattributed`, before any M64 retry / restart (`chain_core.record_incident`,
`require_certain_cleanup` — hook re-run, pre-spawn retry, restart of a hook-stopped invocation — and
`check_restart_eligible` under `incident_retry`). The guard's sweep cannot tell a `setsid`-escaped leak from an ambient box
process (P383), so a Spotlight indexer starting during a failed attempt aborts the chain.

Change (minimal):
- `cleanup_problems`: unchanged exact schema; `survivors`, `containers_remaining`, `unknown` must be EMPTY lists;
  `orphans_unattributed` must be a LIST of records (each a dict with `pid`; malformed → problem) but may be nonempty;
  `uncertain is False`, `completed is True` unchanged.
- New pure `cleanup_orphans(receipt) -> list` (the validated orphan records, `[]` when none).
- Recording: `record_incident` stores `cleanup_orphans_unattributed` in the incident record; `require_certain_cleanup` and
  `check_restart_eligible` store it on the invocation / attempt record they already persist (`chain.json.progress`), so every
  retry or restart that proceeded past orphans carries them; the chain log line names the count.
- tg1 (`abort_restart`) unchanged: C147 rule (orphans are diagnostics; `uncertain` blocks).
- Scope: `chain_incident.py`, `chain_core.py` and tests; no probe-closure module changes (the generation identities do not
  move); the M64 chain lifecycle closure moves (no M64 chain exists).

Tests (red first): nonempty valid orphans → incident retry proceeds and the incident record carries them (end to end through
the fake M64 chain, `fake_arm_probe` with orphans); the same for a hook re-run, a pre-spawn retry and a hook-stopped restart;
survivors / containers / `unknown` nonempty, `uncertain` true, `completed` false, missing / extra key, `orphans_unattributed`
not a list or holding a non-dict → each still refuses (existing R5 tests keep passing, the one asserting that orphans refuse is
inverted with this plan as its reason); tg1 config unchanged (a restart with orphans still follows C147).

## 2. The tg1 side (P388 — proposal, evidence first)

Handoff claim to check: an ambient process can still make a tg1 probe cleanup `uncertain`, refusing the one block restart
(C147) and aborting a tg1 chain. Facts:
- The recorded case (M63 abort, `p297-uncertain-gone` fixture: a Spotlight `mdworker` vanished between listing and its
  start-order read) is FIXED by C157 (2026-10-15): unreadable start / order is resolved against the final process table.
- After C157 a READABLE ambient process lands in `orphans_unattributed` (diagnostic under C147), never in `uncertain`.
- Remaining `uncertain` paths for a process that is not ours: `path-only attribution` (its cwd / argv names our paths),
  `identity unreadable` (start time unreadable after listing), an unreadable record still unresolved at the reconciliation
  deadline, scan non-convergence, overflow.
- Survey on this box (2026-10-18): 511 same-uid processes, none denies `cwd` / `cmdline` / `create_time` / `ppid` /
  `status`; the live Spotlight workers are fully readable. So the residual needs a mid-exit read race that persists through
  `RECONCILE_DEADLINE_S`, or an ambient process touching our paths.

Proposal: measure before changing the probe (a probe change rotates the tg1 identity, P377). A diagnostic (no production
change): the REAL guard (unpatched scan) runs N = 200 start → idle (5 s) → cleanup cycles on this box while (a) the P383
ambient generator churns foreign-session short-lived processes and (b) a writer creates and deletes files under a
non-`.noindex` scratch dir to provoke real Spotlight indexing; every receipt is classified (clean / orphans only / uncertain
by reason). Decision rule (pre-registered): zero `uncertain` outcomes caused by a non-ours process → the tg1 side is closed
as a documented residual (upper bound ≈ 3/200 per cycle), no probe change; any → a probe-side design (likely: a
session-foreign, launchd-parented process never observed in the probe's tree whose identity read fails is recorded as an
orphan with its reason instead of `uncertain`), Cursor plan review, test-first, as a tg1 epoch change.

## 3. Order

Cursor plan review → build §1 test-first in the worktree → targeted tests → Cursor code review (commit hash named) → full
stack suite from the worktree alone → merge when no chain from main is live; §2 diagnostic after the §1 suite (never two at
once), results recorded in P388.
