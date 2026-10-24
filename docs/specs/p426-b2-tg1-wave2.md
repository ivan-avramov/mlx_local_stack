# P426 B2 — tg1 legs for Wave 2 (A7) — DRAFT v1, 2026-10-23 (deliberation with the operator; not reviewed)

Authority: P426 plan v4 §2 / §3 / §6 / §9 (B2), C205, C214 (G4 marker), C209 (P433), C217 (P455), **C218** (arms are stack
commits served as shipped), P457 = A+ (operator, 2026-10-23), P476 (registry pruned before v8). v1 changes from v0: §2 (A+),
§4 (arm commits replace the served-registry flags), §3 (P459 revised per the operator's fail-early guidance — C220), §6 (rehearsal facts), §7 (P469). Still open for the operator: P461–P469 as recommended below (P460 → C221).
Ordering: the P475 KV matrix for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` runs before Wave 2 (a KV change would void it).

## 1. Scope

One P426 Wave-2 leg = ONE `run_tg1_chain.py` invocation for ONE entry and ONE session, from the arm's frozen worktree,
sequenced by an outer Wave-2 sequencer. Legs (plan §6), ≥ 600 s idle before each:

| # | Leg | Arm worktree | Chain argv (besides §4's common flags) | Items |
|---|---|---|---|---|
| 1 | `tg1-p426-off-pilot` | `stack-p426-off` | `pilot` | 5 Python, seed 1001 sample |
| 2 | `tg1-p426-on-pilot` | `stack-p426-on` | `pilot` | same 5 |
| 3 | `tg1-p426-off-s1` | off | `chain s1` | 22 Python + 21 Go, seed 1001 |
| 4 | `tg1-p426-on-s1` | on | `chain s1` | same |
| 5 | `tg1-p426-on-s2` | on | `chain s2` | 43, seed 2002, reversed order (§5) |
| 6 | `tg1-p426-off-s2` | off | `chain s2` | same |
| 7 | `tg1-p426-on-reload` | on | `chain reload` | the pilot's 5 Python items, seed 1001 |
| 8 | `tg1-p426-off-reload` | off | `chain reload` | same |

Gate after legs 1–2: both VALID (incl. ON engagement / `cached_session`) and the estimate recalibrated from their walls; else
stop for the operator. A systemic failure stops the run (§3); a rerun is an operator decision, labelled.

## 2. Router ownership — A+ (P457, ruled)

The chain owns router start, load, A4 gate, M50, worker tripwires, unload and stop. P426's checks run INSIDE the chain at its
existing checkpoints, as a P426 configuration of the chain (no outer wrapper around the router):
- **Entry and before every invocation:** arm commit / frozen record v8 / serving pins / registry sha, nothing busy, the G4
  marker, power + orphan gate (a failure before the first launch → `NOT_STARTED`; later → systemic, §3).
- **Per item, at the `done` barrier (a P426 `ChainHooks`):** the item's server-log records (§6) reconcile and, ON, carry
  drafter counters; a missing engagement on ON or drafter activity on OFF is systemic (stop after that item).
- **Per WATCH tick:** power (§7).
- **Exit:** chain status `finished`, `check_realized`, rows == the planned items in the planned order, per-item seeds,
  build drift (entry == exit), `:8000` free; then a thin outer step writes the P426 receipt and harvests (§9).
- Chain modes P426 does not use (two-pick schedules, archive / restart, `incident_retry` retries, smoke) are refused in P426
  mode. The hook lives outside the probe closure (the probe identity is unchanged).

## 3. Failure policy (P459, revised — RULED C220)

Operator guidance: fail early when the remaining work would be thrown away; when one item out of many fails, keep testing the
rest and come back for the outliers.
- **Systemic → stop the leg at once, INVALID:** served-config / M50 drift, router or worker death or identity change, the
  frozen record or build drifting, an engagement failure (§2), uncertain cleanup (survivors / containers), power-gate failure.
- **Item-level transport incident** (the item's HTTP / connection error or client timeout while the worker passes the health
  checks — nothing in flight, same pid / create time, certain cleanup): the item gets a `transport_dnf` record (never graded,
  never a strict fail); the leg continues with the remaining items on the same loaded instance; retries 0 in the leg.
- **More than 2 DNF items in one leg** → systemic.
- **Make-up leg** after the wave (operator's call, labelled): the DNF items for BOTH arms on a fresh load, same seeds; reported
  separately, outside the per-session pairs. A DNF in ON absent in OFF is an attention flag; a repeat on the make-up is a finding.
- In-probe non-convergence (budget hit, turn cap, exec timeout, `client_inactivity`) is a scored strict fail, as today.
- Reuses the chain's `chain_incident` classification / `transport_dnf` rows (M64) without its in-leg retry.

## 4. Models and arms as commits (P460 → C221; C218 replaces P458)

- **Models (C221):** a REQUIRED `--models a[,b…]` list (≥ 1, no default) replaces the hard-coded pair; recorded in the ChainConfig /
  `chain.json`; every name validated against the served committed registry; s2 runs the list reversed; time predictions from the
  pilot mean, else a recorded default. The frozen M59 / M61 / M62 / M64 / inject runners keep their constants (untouched).
- **No overlay generation (C221 / C218):** the tg1 chain serves the worktree's committed `main_models.yaml`; `--predictor off|mtp` is
  an assertion of the entry's committed state, refused on mismatch.
- **Arms are stack commits** (C218): OFF = the v8 frozen commit; ON = it + exactly the §11 restore (three lines, `PROVISIONAL
  P426` note, the seeding test) on local branch `p426-on`; worktrees `$STACK_WORKDIR/worktrees/stack-p426-{off,on}`. The
  chain serves its worktree's own `main_models.yaml` verbatim (`MLX_SERVE_CONFIG=<worktree>/main_models.yaml`; no overlay
  generation in P426 mode). Worker tripwire: the argv mlx-serve builds from that entry — ON the three predictor flags exactly,
  OFF none. v8 asserts the two commits differ in exactly those paths and that the parsed registries differ in exactly the
  entry's three keys.
- Common flags every leg: `--models Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --p426 --out-root
  $STACK_WORKDIR/p426/wave2/<leg> --probe-code-sha <frozen> --policy-sha <frozen> --frozen-prompt-date <frozen>
  --campaign-core <frozen commit of the arm>`. The exact argv per leg is generated by the sequencer and pinned in tests.

## 5. s2 item order (P461)

s2 runs each cell's items in REVERSE sorted order: the Python cell's in-load pilot (seed 2002's 5) first, reversed, then the
rest reversed; then Go reversed. Language order stays Python → Go. `schedules.tg1(order="reversed")` for s2 only; recorded in
the schedule and `chain.json`; tests assert both orders and that the probe receives `--items` in that order.

## 6. Server-log reconciliation and engagement (P463)

From the P456 rehearsal (17 items, 152 requests): opencode requests carry `session=ses_*` == the row `session_id`; per item
the completed requests == `gate.requests_completed` == `requests_observed`; each A4 gate adds 3 `anon:*` requests AND one
4-request `ses_*` session of its own; every request `backend=cached_session`.
- Per item (at `done`): its `ses_*` records started == completed == `gate.requests_completed`, zero `Request failed`.
- Per load: the A4 window's 3 `anon:*` + its one `ses_*` session match the A4 receipt.
- ON: every item request carries B1 counters `draft_kind=mtp`, 0 ≤ accepted ≤ proposed, rounds > 0 when
  `generated_tokens ≥ 2` (confirm 1-token behaviour in the pilot); OFF: no draft fields on any request.
- B2 persists the per-item slice; B6 computes decode rate (plan §6 T2) and acceptance from it.

## 7. Speed / power validity (P462)

The chain's own 5-minute `WATCH` lines are the AGENTS.md daemon; P469 (progress undercount) is fixed test-first in B2. Any
tick not 140 W / 28 V / battery > 20 %, an unparsable tick, or a gap > 2 × 300 s while an invocation runs → speed INVALID;
plus `pmset -g log` battery intervals over the leg window. Quality survives a speed-invalid leg (labelled).

## 8. G4 marker and P433

- `bench.local_gate run` creates `$STACK_WORKDIR/gate/RUNNING` exclusively (pid, repo, sha, started; refuses if present) and
  removes it in `finally`. The P426 entry checks (Wave 1 leg wrapper and the Wave-2 chain) refuse while it exists; a stale
  marker is the operator's to remove.
- P433 (C209): the v2 pre-check's plugin-load proof comes from the activation call for every scaffold that requires the plugin.

## 9. Frozen record v8, timeouts, harvest (P464, P466, P467)

- **v8** (after B2 + P476 land): the two arm commits and worktrees, serving pins (fork / mlx-serve gitlinks) identical in both,
  `probe_code_sha256` / `scaffold_policy_sha256` / `generation_identity_sha256` from `--print-identity` in each worktree (equal
  across arms), pins.json sha, both registry shas, ONE frozen prompt date for all 8 legs, the grader image id. Written only
  after: venvs synced in both worktrees, the frozen entry points run, K3 passes. Every leg refuses on drift.
- **Timeouts:** sequencer leg timeout 10 h for s1 / s2 legs, 2 h for pilot / reload; never killed on overrun.
- **Harvest** (`p426_harvest`, P437 rules, scrubbed): `benchmark/results/p426/wave2/<leg>/` on `main` — receipt, `chain.json`,
  `RUNLOG.md`, `schedule.json`, rows + manifests + sidecars, grader reports, A4 receipts / logs, the per-item log slices,
  stdout; transcripts / events / stderr → the `evidence` stage (xz > 8 MB), pushed separately with approval.

## 10. Tests (test-first) and review

Red first, mocked ops / fake probe plus one UNMOCKED production-topology test (sequencer → chain in P426 mode → fake probe,
real argv / env / `chain.json`): argv per leg; single-entry schedule; old two-pick config byte-identical; s2 order reaches the
probe; fresh-root refusal; the P426 hook (engagement missing ON / present OFF → stop after the item; reconciliation
mismatches); failure policy (each systemic kind stops; an item incident → DNF + continue; a third DNF → systemic); arm-commit
checks (wrong commit / diff / registry sha refuse); WATCH power + P469; G4; P433; harvest layout + scrub + size cap;
sequencer order, the pilot gate, PAUSE, resume skip only VALID + harvested.

Four-eyes STRICT (P468: the harvest publishes model transcripts to the public repo — a data boundary; the chain-core change
is architecture); cast shown at Go. Then the v8 freeze, a smoke-scale dry leg per arm, and Wave 2 (≈ 12.5 h [16.3 h]).
