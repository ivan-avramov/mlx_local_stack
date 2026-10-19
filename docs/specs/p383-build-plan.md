# P383 build (C180 option a) + P389 (resume bypasses A7) + the tg1 side (P388) — PLAN v2, 2026-10-18

Status: v2 → Cursor plan review round 2. v1 → round 1 `AGREE WITH CHANGES R1–R9`
(`docs/reviews/p383-plan-round1.cursor-gpt-5.6-sol-high.md`; the first run printed only R8, the re-run printed all nine);
R2–R5, R9 applied; R1 is a pre-existing bug → its own proposal P389 (§2, operator); R6–R8 make the v1 P388 measurement
unable to decide → P388 reframed (§3, operator). Ruling: C180. No GPU. Branch / worktree: `p383-build` in
`$STACK_WORKDIR/worktrees/p383` from `main`; one suite at a time.

## 1. P383 build (M64 `incident_retry` only)

Today A7 (`bench/chain_incident.py::cleanup_problems`) requires the exact six-key `ProcessGuard.status()` receipt with every
list EMPTY, incl. `orphans_unattributed`, before every M64 retry / restart. The guard cannot tell a `setsid`-escaped leak from
an ambient box process (P383), so a Spotlight indexer starting during a failed attempt aborts the chain.

- **Validator (R3, R4):** `cleanup_problems(receipt, *, allow_reasonless_orphans=False)` keeps today's behaviour by default
  (tg1 and every policy-agnostic caller unchanged by construction). With `allow_reasonless_orphans=True` (passed only where
  the chain's `transport_policy == "incident_retry"`), `orphans_unattributed` may be nonempty iff EVERY record has exactly the
  real reasonless detached-orphan shape `{pid: int > 0, create_time: number, argv: list of str}` and NO `reason` key; any
  reason-bearing record blocks independently of `uncertain` (an inconsistent receipt `{"pid": 2, "reason": "scan did not
  converge"}` with `uncertain: false` refuses). Everything else unchanged: exact schema; `survivors`, `containers_remaining`,
  `unknown` empty lists; `uncertain is False`; `completed is True`. `cleanup_orphans(receipt)` returns the validated records
  and RAISES on a malformed list (never conflates malformed with `[]`).
- **Evidence (R2):** `record_incident()` stores `cleanup_orphans_unattributed` and `cleanup_status_sha256` (sha256 of the
  canonical JSON of the receipt) in the incident before recovery / retry; a pre-spawn incident (created by
  `persist_pre_spawn()` before any cleanup exists) is BACKFILLED with the same two fields after its cleanup gate passes —
  live and on resume — and persisted before the retry starts. Attempts are not duplicated (`attempts[].cleanup_status` is
  already durable). DNF rows inherit both incident records unchanged.
- **Spec (R4):** `docs/specs/p371-shared-runner-core.md` A7 amended ("under `incident_retry`, reasonless detached orphans
  are recorded, not blocking — C180"); the helper docstrings say the same.
- **Tests (R5, red first):** valid reasonless orphans → incident retry proceeds, the incident (and a pre-spawn incident after
  backfill, live and after resume) carries the orphan list and the receipt sha; the same for a hook re-run and a
  hook-stopped restart under `incident_retry`; a second incident → `transport_dnf` with both incidents' evidence in the DNF
  sidecar; archive keeps the evidence; reason-bearing orphan with `uncertain: false` → refuse; `pid` missing / zero /
  non-int, `create_time` missing, `argv` not a list, a non-dict entry → refuse; survivors / containers / `unknown` nonempty,
  `uncertain: true`, `completed: false`, missing / extra key → refuse (existing R5 tests keep passing; the one asserting
  that reasonless orphans refuse is inverted, citing C180); tg1 (`abort_restart`) with reasonless orphans follows C147
  unchanged, and with a reason-bearing orphan + `uncertain: true` still refuses; orphan counts in the chain log line.
  Fixture records are real-guard shaped (from a recorded `ProcessGuard.status()`), not `{"pid": 2}`.
- Scope: `chain_incident.py`, `chain_core.py`, the P371 spec, tests. No probe-closure module changes (generation identities
  unchanged); the M64 chain lifecycle closure moves (no M64 chain exists).

## 2. P389 — resume bypasses A7 (pre-existing, found by round 1 R1; operator approval needed)

`prepare_resume()` (`new_segment`, M64) hydrates a crashed `running` invocation, then `salvage_hook_stops()` finalizes it
from a persisted cheat / unclear disposition or pre-spawn record after validating ONLY the rows prefix; the leg loop then
launches the rerun / retry with no A7 check of the hydrated cleanup receipt (it may be uncertain, carry survivors or
`unknown`, be incomplete, or be missing). Proposal (in the same branch, its own red tests and commits): before salvaging any
stop that implies a rerun / retry, apply the same validator (`allow_reasonless_orphans` per policy) to the hydrated
receipt; a receipt that fails, or a missing receipt (the probe died without cleaning up), refuses the resume with the
listing (operator action: verify the box and clear by hand) instead of starting another invocation; the result is persisted
before any invocation starts. Tests: crash after a persisted cheat disposition / pre-spawn record with each failing receipt
kind → resume refuses; with a clean (or reasonless-orphan, M64) receipt → resume proceeds exactly as today.

## 3. P388 — the tg1 side, reframed (operator decision)

Round 1 (R6–R8) showed the v1 measurement cannot decide: 5-s cycles do not exercise item-length lifetimes or the
reconciliation-deadline races; serial cycles are correlated, so the ≈ 3/200 bound is not a per-item or per-chain risk; and an
`uncertain` event cannot be attributed to "not ours" from the receipt after the process exits. A decisive study (item-shaped
guard lifetimes, deterministic fault injection for the denied-read paths, lineage snapshots, a registered chain-level risk
threshold) would need on the order of thousands of item-equivalents to bound a per-chain false-abort rate usefully.

Corrected mechanism taxonomy (R9), after C157: a non-ours process makes a tg1 cleanup `uncertain` only through (i) path-only
attribution (its cwd / argv names a guard root — file indexing does NOT trigger it, `_attributed_path()` reads cwd / argv),
(ii) an immediate `identity unreadable` (`TransportAbort` during the sweep, NOT reconciled), (iii) an unreadable record still
unresolved at `RECONCILE_DEADLINE_S` (incl. a child of a vanished unreadable process), (iv) non-convergence or overflow. A
readable, young, detached, non-path-attributed process is a reasonless orphan (diagnostic under C147).

Recommendation: do NOT build the study. A false tg1 abort is fail-closed — it costs an operator resume, never a wrong row —
and the only recorded case (the M63 `mdworker`) is fixed by C157. Instead: (a) record the residual with the taxonomy above;
(b) chain-side only (no probe identity change): when a tg1 restart is refused for `uncertain` cleanup, the abort listing
captures a contemporaneous snapshot (pid, create time, ppid, session id, cwd / argv when readable, still-alive) of every
uncertain pid, so a recurrence is attributable; (c) a recurrence reopens P388 with that evidence for a probe-side design.
Alternative: the decisive study above (≈ 1–2 sessions of CPU build + many hours of box time).

## 4. Order

Cursor plan review round 2 → (operator: P389 in this branch; P388 reframing) → build §1 (+ §2) test-first in the worktree →
targeted tests → Cursor code review (commit hash named) → full stack suite from the worktree alone → merge when no chain from
main is live; P388 (b) is a separate small chain-side change after the merge, its own test-first commit and review.
