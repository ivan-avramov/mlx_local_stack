# P383 build (C180 option a) + P389 (resume bypasses A7) + the tg1 side (P388) — PLAN v3, 2026-10-19

Status: v3 → Cursor plan review round 3 (narrow). v2 → round 2 `AGREE WITH CHANGES R1 R10–R14` (R2–R9 closed; all applied here;
`docs/reviews/p383-plan-round2.cursor-gpt-5.6-sol-high.md`). v1 → round 1 `AGREE WITH CHANGES R1–R9`
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
  real reasonless detached-orphan shape of its sole emitter (`proc_guard.py` ~1069–1072) — exactly the keys `pid`,
  `create_time`, `argv`; `type(pid) is int and pid > 0`; `type(create_time) in (int, float)`, finite and > 0;
  `type(argv) is list` with every element exactly `str` (R10) — and NO `reason` key; any
  reason-bearing record blocks independently of `uncertain` (an inconsistent receipt `{"pid": 2, "reason": "scan did not
  converge"}` with `uncertain: false` refuses). Everything else unchanged: exact schema; `survivors`, `containers_remaining`,
  `unknown` empty lists; `uncertain is False`; `completed is True`. `cleanup_orphans(receipt)` returns the validated records
  and RAISES on a malformed list (never conflates malformed with `[]`).
- **Evidence (R2, R11):** `record_incident()` validates and stores `cleanup_orphans_unattributed` and
  `cleanup_status_sha256` (sha256 of `json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False)`, R10) in
  the incident before it is appended / written; a pre-spawn incident (created by `persist_pre_spawn()` before any cleanup
  exists) is BACKFILLED with the same two fields — live: after `require_certain_cleanup()` (~line 1777) and before
  `recover()` (~1778); on resume: by the P389 gate (§2) — and persisted before the retry starts; the backfill asserts
  exactly one matching incident (invocation, slot, load, load generation, `pre_spawn=True`). Attempts are not duplicated (`attempts[].cleanup_status` is
  already durable). DNF rows inherit both incident records unchanged.
- **Spec (R4):** `docs/specs/p371-shared-runner-core.md` A7 amended ("under `incident_retry`, reasonless detached orphans
  are recorded, not blocking — C180"); the helper docstrings say the same.
- **Tests (R5, red first):** valid reasonless orphans → incident retry proceeds, the incident (and a pre-spawn incident after
  backfill, live and after resume) carries the orphan list and the receipt sha; the same for a hook re-run and a
  hook-stopped restart under `incident_retry`; a second incident → `transport_dnf` with both incidents' evidence in the DNF
  sidecar; archive keeps the evidence; reason-bearing orphan with `uncertain: false` → refuse; `pid` missing / zero /
  non-int, `create_time` missing, `argv` not a list, a non-dict entry → refuse; survivors / containers / `unknown` nonempty,
  `uncertain: true`, `completed: false`, missing / extra key, `create_time` boolean / non-finite / ≤ 0, an `argv` element
  not a `str` → refuse (existing R5 tests keep passing; the one asserting
  that reasonless orphans refuse is inverted, citing C180); tg1 (`abort_restart`) with reasonless orphans follows C147
  unchanged, and with a reason-bearing orphan + `uncertain: true` still refuses; orphan counts in the chain log line.
  Fixture records are real-guard shaped (from a recorded `ProcessGuard.status()`), not `{"pid": 2}`.
- Scope: `chain_incident.py`, `chain_core.py`, the P371 spec, tests. No probe-closure module changes (generation identities
  unchanged); the M64 chain lifecycle closure moves (no M64 chain exists).

## 2. P389 — resume bypasses A7 (pre-existing, found by round 1 R1; operator approval needed)

`prepare_resume()` (`new_segment`, M64) hydrates a crashed `running` invocation, then `salvage_hook_stops()` finalizes it
from a persisted disposition after validating ONLY the rows prefix, and the leg loop launches the next invocation (the rerun
/ retry, the tail of a partial accepted / exhausted stop, or the next leg) with no A7 check of the hydrated receipt.

Fix (R11): in `prepare_resume()`, AFTER `hydrate_running()` (~line 1023) and BEFORE `salvage_hook_stops()` (~1026), every
`running` record with a persisted stop OTHER than `unclear` — pre-spawn, cheat, and the F9 accepted / exhausted decisions —
passes the same validator (`allow_reasonless_orphans` per policy) on its hydrated receipt, whether or not the row-prefix
salvage later succeeds (a quarantined invocation still leads to another launch); a resumed pre-spawn incident is backfilled
there (§1). The result is persisted before any invocation starts. `unclear` keeps blocking for the operator as today.

Missing receipt (R12), pre-registered: absence is never treated as clean — the resume refuses with the listing, and the
out-root is ABANDONED (the chain restarts in a fresh out-root; the abandoned root's files stay as evidence). An
operator-authorized clearance transaction (durable record of the invocation identity, the missing receipt, a box
leftover / lineage snapshot and the acknowledgement) is NOT built now; it is proposed only if this case ever occurs.

Tests (red first): crash after a persisted pre-spawn / cheat / accepted (partial and full) / exhausted stop, each with a
failing receipt kind (uncertain, survivors, `unknown`, incomplete, malformed, missing) → resume refuses and starts nothing;
the same with an unsalvageable prefix (quarantine path) → refuses; with a clean receipt (and, under `incident_retry`, a
reasonless-orphan receipt) → resume proceeds exactly as today, the pre-spawn incident backfilled once; `unclear` unchanged.

## 3. P388 — the tg1 side, reframed (operator decision)

Round 1 (R6–R8) showed the v1 measurement cannot decide: 5-s cycles do not exercise item-length lifetimes or the
reconciliation-deadline races; serial cycles are correlated, so the ≈ 3/200 bound is not a per-item or per-chain risk; and an
`uncertain` event cannot be attributed to "not ours" from the receipt after the process exits. A decisive study would need item-shaped guard lifetimes, deterministic fault injection for the denied-read paths, lineage
snapshots and a registered chain-level risk threshold (R14: no sample-size claim is made here).

Corrected mechanism taxonomy (R9), after C157: a non-ours process makes a tg1 cleanup `uncertain` only through (i) path-only
attribution (its cwd / argv names a guard root — file indexing does NOT trigger it, `_attributed_path()` reads cwd / argv),
(ii) an immediate `identity unreadable` (`TransportAbort` during the sweep, NOT reconciled), (iii) an unreadable record still
unresolved at `RECONCILE_DEADLINE_S` (incl. a child of a vanished unreadable process), (iv) non-convergence or overflow. A
readable, young, detached, non-path-attributed process is a reasonless orphan (diagnostic under C147).

Recommendation: do NOT build the study. A false tg1 abort is fail-closed — it costs an operator resume, never a wrong row —
and the only recorded case (the M63 `mdworker`) is fixed by C157. Instead: (a) record the residual with the taxonomy above;
(b) chain-side only (no probe identity change), BEST-EFFORT evidence (R13): when a tg1 restart is refused for `uncertain`
cleanup, the abort listing records for every orphan / uncertain record the receipt's identity and its CURRENT state —
`same` (pid alive with the recorded create time), `gone`, `reused` (alive, different create time), `unreadable`, or
`sentinel` (pid 0 / no create time) — and captures ppid, session id, cwd / argv ONLY for `same`; (c) ANY recurrence,
including an indeterminate one, reopens P388 with that evidence for a probe-side design.
Alternative: the decisive study above (several sessions of build plus long box time; not sized).

## 4. Order

Cursor plan review round 2 → (operator: P389 in this branch; P388 reframing) → build §1 (+ §2) test-first in the worktree →
targeted tests → Cursor code review (commit hash named) → full stack suite from the worktree alone → merge when no chain from
main is live; P388 (b) is a separate small chain-side change after the merge, its own test-first commit and review.
