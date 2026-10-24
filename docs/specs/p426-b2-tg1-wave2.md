# P426 B2 — tg1 legs for Wave 2 (A7) — SPEC v2, 2026-10-24 (four-eyes STRICT, C228)

Authority: P426 plan v4 §2 / §3 / §6 / §9, C205, C209 (P433), C214 (G4), C217 (P455), C218–C228, C232, C234, AGENTS.md.
v1 → v2: design review round 1 of 3 (`gpt-5.6-sol-high`, `glm-5.2-high`, Claude Sonnet; dispositions in
`docs/reviews/p426-b2/design-round1.dispositions.md`). v1 assumed the tg1 chain could host the P426 checks through its existing hook
and incident paths; it cannot (tg1 runs `item_barrier="off"`, `abort_restart`; the `transport_dnf` path exists only in M64's per-arm
layout and retries first). v2 defines a P426 mode with its own evidence policy, transport policy, disposition and records.

## Goal

Run the P426 Wave 2 — the tg1 agentic coding benchmark (opencode solving 43 Python / Go tasks), MTP ON vs OFF, for
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` — through the shipped stack (C218: each arm a stack commit served as committed), so that every
leg provably differs from its pair only in the entry's MTP state, every item's requests are reconciled against two independent sources and its
engagement proven, systemic problems stop the run at once while an isolated item incident is recorded and the run continues, and every
citable byte is harvested — producing the per-session paired evidence the pair verifier (B8) and the signals sheet (B6) need for the
operator's ship call (C204). The chain is the proven tg1 runner; B2 adds what P426 needs and changes nothing an earlier chain relied on
except where a ruling says so (C221: the hard-coded pick pair and overlay generation are retired).

## 1. Legs and gates

One leg = ONE `run_tg1_chain.py --p426` invocation for ONE entry and ONE session, from the arm's frozen worktree, launched by the
Wave-2 sequencer (`bench.p426_wave2`), ≥ 600 s idle before each.

| # | Leg | Arm worktree | Chain argv (besides §6's common flags) | Items |
|---|---|---|---|---|
| 1 | `tg1-p426-off-pilot` | `stack-p426-off` | `pilot` | first 5 of s1's Python order (seed 1001) |
| 2 | `tg1-p426-on-pilot` | `stack-p426-on` | `pilot` | same 5 |
| 3 | `tg1-p426-off-s1` | off | `chain s1` | all 22 Python then all 21 Go, s1 order (§7) |
| 4 | `tg1-p426-on-s1` | on | `chain s1` | same |
| 5 | `tg1-p426-on-s2` | on | `chain s2` | all 21 Go then all 22 Python, s2 order (§7) |
| 6 | `tg1-p426-off-s2` | off | `chain s2` | same |
| 7 | `tg1-p426-on-reload` | on | `chain reload` | the pilot's 5 items |
| 8 | `tg1-p426-off-reload` | off | `chain reload` | same |
| 9–10 | `tg1-p426-{off,on}-makeup` | off, on | `makeup --items <file>` | §5.5; only on the operator's call |

- **Pilot gate (after legs 1–2):** both legs VALID (§5.1), 5 / 5 items reconciled, zero DNF, ON engagement proven on every
  eligible request (§4.4), both speed-valid (§8), and the leg timeouts derived (§10.2). Otherwise the sequencer stops for the operator.
  Pilot rows never enter pairs or signals.
- **Pre-freeze rehearsal (before v8):** the B2 commit plus a throwaway ON commit, `--smoke` scale (1 + 2 items per arm), through the
  real topology (router, worker, opencode, docker grader, item barrier, reconciliation, watcher, harvest into a scratch stage).
  Rehearsal output is never graded, paired or published. It is the barrier's first production run and must show: every barrier fires,
  reconciliation exact, ON counters present, OFF absent, the injected-mismatch red case (§13) stops the leg.
- A systemic failure stops the leg and the sequencer (§5.1). A rerun is an operator decision, labelled, on a fresh out-root.

## 2. P426 mode

- `--p426` selects the ChainConfig `tg1-p426` (config_id distinct from `tg1`) and refuses: `--smoke` outside the rehearsal root,
  `--pred-s`, `--generation-sha`, `C147_OVERLAY`, `--frozen-date-from`, a missing `--models` / `--out-root` / `--campaign-core` /
  `--frozen-prompt-date` / `--probe-code-sha` / `--policy-sha` / `--frozen-record`, an out-root that exists, more than one model.
- Without `--p426` the tg1 chain behaves exactly as at the B2 base commit except C221 (§6): the serialized `tg1` ChainConfig, its
  schedule and its `schedule_sha256` for the M63 / P223 argv are byte-identical to golden values recorded from the base commit (test).
- The chain owns router start, load, A4, M50, worker tripwires, unload and stop (A+, C219). The P426 checks run inside the chain;
  the sequencer only launches, supervises (§10.3) and harvests (§11).

## 3. Checkpoints

| Checkpoint | Checks (any failure → the class in §5) |
|---|---|
| Entry (before the router) | frozen record v8 self-hash + live re-verification (§10.1); worktree HEAD == the record's arm commit, `git status` clean incl. submodules at their gitlinks; registry sha; `--predictor` assertion (§6); the gate lock not held and the leg lock taken (§9); no foreign busy process, no `:8000` listener, zero `session_cache_probe` / `opencode run` survivors; power (§8) |
| After load | worker argv exact (§6.3); effective router / worker environment receipt (§6.4); A4 gate PASS; A4 window reconciliation (§4.3) |
| Before every invocation | the entry checks except router absence; owned router / worker identities (pid + start time) unchanged; no foreign busy process (owned pids exempt by identity, §9) |
| Item `ready` barrier | registry sha, lifecycle hash, worktree clean, owned identities unchanged |
| Item `done` barrier | the `ready` checks + per-item reconciliation and engagement (§4) |
| WATCH tick | power (§8, speed only) |
| Exit | §5.1 VALID conditions; build drift (entry == exit); owned processes stopped and verified; `:8000` free |

The item barrier is enabled by a P426 evidence policy: `tg1_runner` gains `TG1_P426_EVIDENCE` (= `TG1_EVIDENCE` with `item_barrier="on"`),
selected by the probe flag `--evidence p426` that the chain passes only in P426 mode; `TG1_EVIDENCE` and the default stay `off`.
The evidence policy is not in the generation identity (`run_config`); `probe_code_sha256` moves once (new epoch, already moved by P476)
and is equal across arms (v8). The chain verifies the manifest's `runtime.evidence_policy` equals `TG1_P426_EVIDENCE` before item one.

The `done` hook receives: the slot, the `.done` payload, the item's full row (incl. `session_id`, `request_usage`, outcome fields), the
log cursor at the item's `ready`, the load context (A4 receipt, owned identities) and the invocation context.

## 4. Per-item reconciliation and engagement (C225)

### 4.1 Sources
- **Client:** the row's `request_usage` (`token_turn_gate` records `(j, output_tokens, prompt_tokens, budget)` per completed request from
  opencode's stream; the client-side source) and its outcome (`nonconv_kind`, `gate.requests_at_kill`).
- **Server log:** `logs/mlx_vlm.log` `Request started` / `Request completed` / `Request failed` lines after the item's cursor.
- **Worker counters:** `GET /metrics` on the owned worker (`ChainOps.worker_metrics`) at `ready` and at `done`: `summary.requests_started /
  requests_completed / requests_failed / in_flight / prompt_tokens_total / generated_tokens_total`, and decode time
  `D = generated_tokens_total / avg_decode_tok_s` (0 when no tokens).

### 4.2 Settle
At `done` the chain polls (≤ 60 s, 1 s interval) until `in_flight == 0` and the log has no `Request started` without its terminal line.
Not settled → systemic.

### 4.3 Equalities (all exact)
- Every `Request completed` line after the cursor carries `session=` == the row's `session_id`, `backend=cached_session`; their count,
  per-request `prompt_tokens` and `generated_tokens` (as charged by the client: `output_tokens`) equal `request_usage` in order.
- Worker deltas (`done − ready`): `requests_completed` == the completed lines == `len(request_usage)`; `requests_started` ==
  completed + failed; `prompt_tokens_total` / `generated_tokens_total` deltas == the sums over the completed lines.
- `Request failed` lines after the cursor: zero, except an item whose outcome is a probe-initiated termination (`client_inactivity`,
  stall / loop / budget / turn / exec kill — the gate's kill kinds): then exactly one failed line with
  `error=stream_closed_before_completion`, it is the last request of the window, `requests_started` delta == completed + 1, and the
  row records the kill (`requests_at_kill == len(request_usage)`). Anything else → systemic.
- Per load, before the first item: the A4 window's 3 `anon:*` requests + its own 4-request `ses_*` session equal the A4 receipt.
- Any line in the window not attributable by these rules, or unparseable → systemic.

### 4.4 Engagement
- ON: every completed request with `generated_tokens ≥ 2` carries `draft_kind=mtp`, `draft_rounds ≥ 1`, `0 ≤ draft_n_accepted ≤ draft_n`.
  Basis (code-read, fork `0f30522c`): the first token comes from prefill (`speculative/mtp.py` `emitted = 1  # caller already yielded
  the first bonus`); `speculative_stats_since` returns null when no round ran (`speculative/common.py`), so a 1-token request has no
  counters. Requests with `generated_tokens ≤ 1` are counted and listed, not judged. The pilot is the known positive.
- OFF: no `draft_*` field on any request.
- Violation → systemic (the leg stops after this item; the barrier answers `.stop`).

### 4.5 Persisted per item (`items/<slot>.json`, written before the barrier answer)
The log slice (raw lines, byte offsets, sha256), the worker snapshots at `ready` / `done`, the derived per-item totals (requests,
prompt / generated tokens, decode time `D` delta, accepted / proposed sums), the reconciliation verdict and every check's result.
The log carries counts only, no prompt text.

## 5. Failure policy (C220)

### 5.1 Classes

| Class | Conditions | Effect |
|---|---|---|
| NOT_STARTED | an entry check fails before the router starts | nothing launched; leg record `NOT_STARTED` |
| Systemic | served-config / M50 / registry / lifecycle / frozen-record drift at any checkpoint; owned router or worker gone or replaced; any server-side `Request failed` outside §4.3's rule; reconciliation or engagement failure; settle timeout; unparseable line; uncertain cleanup (survivors, containers); a foreign busy process; > 2 DNF in the leg | stop at once (the barrier answers `.stop`; between invocations no relaunch); leg `INVALID`; sequencer stops |
| Item DNF | the probe aborts an item with a client-side transport cause (`connection`, `dropped_stream`, `timeout`, `client_timeout`) AND owned router and worker identities unchanged and healthy, `in_flight == 0` after settle, zero server `Request failed` in the window, certain empty cleanup | a `p426_dnf` record (§5.3); the leg continues on the same load (§5.2) |
| Scored strict fail | in-probe non-convergence (budget hit, turn cap, exec timeout, `client_inactivity`, kills) | a normal row, `acc_strict = 0`, as today |
| Speed-invalid | an in-run power / watcher failure (§8) | quality continues; the leg's speed block is excluded (§8) |

VALID = chain rc 0, status `finished`, no `running` / quarantined record, the realized ledger (§7) == the plan (rows + DNF in order),
every `done` reconciled, verified teardown, `:8000` free. A leg with a DNF is VALID with DNF.

### 5.2 Mechanism: transport policy `p426_continue`
A third `TRANSPORT_POLICIES` member, used only by `tg1-p426`: a classified item incident writes the `p426_dnf` record (chain.json
first, then the sidecar), then the chain relaunches the probe for the remaining items of the leg in order, on the same loaded instance
(no cache reset beyond what every invocation does, no reload, retries 0). `abort_restart` and `incident_retry` are unchanged
(their tests pinned). The hook vocabulary gains `invalidate(reason)` (after-barrier only): the chain persists it, answers `.stop`,
waits for the probe's cleanup-only exit, verifies cleanup, records the leg `INVALID` and exits rc 2. A legacy tg1 hook returning a
non-accept still aborts as today.

### 5.3 `p426_dnf` record
Slot, item, session, language, seed, arm, the probe's abort stamp (cause, evidence files with sha256), the worker / router identities
at the incident and after, the settle result, the log slice. `graded: false`; never a row, never scored; B8 / B6 report DNF counts per arm
and session beside `acc_strict`. An ON DNF absent in OFF is an attention flag.

### 5.4 Cause table
The probe stamps the client cause in P426 mode (`adapter.transport_cause`); a worker / router identity change is checked by the chain
first and is systemic regardless of the stamp; a stamp outside the DNF causes, or none, with an incomplete invocation → systemic.

### 5.5 Make-up legs (operator's call)
One fresh-load leg per arm (OFF then ON, ≥ 600 s idle), over the ordered union of every DNF occurrence of both arms and both sessions;
each item runs with its original session seed; own out-root namespace `makeup`; excluded from the per-session pairs; a repeat DNF is a
finding. Same checkpoints and classes.

## 6. Models and arms (C221, C218)

1. **`--models`** REQUIRED, comma-separated, ≥ 1, no duplicates or empty names, each a `models:` entry of the served committed
   registry; recorded in the ChainConfig / `chain.json`. P426 mode requires exactly one. Generic schedule: s1 in the given order, s2
   reversed, reload the first model; tested with 1, 2 and 3 models. The frozen M59 / M61 / M62 / M64 / inject runners are untouched.
2. **Served config:** the chain serves `<worktree>/main_models.yaml` verbatim (`MLX_SERVE_CONFIG`), no overlay generation (C221). `--predictor
   off|mtp` keeps selecting the out-root family, the tripwire branch and the ON / OFF out-root isolation, and is additionally an assertion:
   the served entry has all three C177 keys (mtp) or none (off), else refused.
3. **Worker argv:** the complete argv equals the one mlx-serve builds from the entry; ON = OFF + exactly `--draft-kind mtp --draft-model
   caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter --mtp-verify-scan joint_v1`.
4. **Arm-equality receipt (after load, every leg):** normalized router and worker environment (keys + values with the worktree root
   replaced by `<WT>`; values of keys matching the secret patterns of §11.3 recorded as sha256 only), the interpreter path and the sha256 of
   `uv.lock` / `benchmark/requirements-bench.lock` in the worktree, the resolved `mlx_vlm` / `mlx_serve` import paths (under `<WT>/src/`)
   and `git -C <WT>/src/<sub> status --porcelain` empty. B8 requires the receipts of a pair equal except the three argv items and
   the arm identity fields (commit, worktree path).
5. **Arms:** OFF = the v8 frozen commit; ON = it + exactly the §11 restore on local branch `p426-on`. Commit diff = the three registry lines,
   the `PROVISIONAL P426` note, `benchmark/bench/tests/test_opencode_probe_seeding.py` (not on the serving path); served diff = the
   entry's three keys. v8 asserts both.
6. Common flags: `--p426 --models Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --predictor <arm> --out-root $STACK_WORKDIR/p426/wave2/<leg>
   --probe-code-sha <v8> --policy-sha <v8> --frozen-prompt-date <v8> --campaign-core <arm commit> --frozen-record <v8 path>`; the
   sequencer generates the argv per leg; tests pin it.

## 7. Schedule and order (C223)

- P426 mode: each language's items in `random.Random(seed).sample(sorted(pool), len(pool))` order (s1 1001, s2 2002), no later sort;
  s1 Python then Go; s2 Go then Python (the language order reversed in `schedules.tg1` under `p426=True` only); reload and pilot = the
  first 5 of s1's Python order; makeup = the given list. A session leg's first invocation is the in-load pilot phase (the first 5 items of
  its first language) as today, then the remaining items.
- The schedule is frozen in `chain.json` before launch (`schedule_sha256`, `freezes_schedule` true for `tg1-p426`). The chain keeps
  an ordered realized ledger (slot, outcome row | DNF, invocation); `check_realized` requires it == the plan in order. Tests: both
  orders reach the probe's `--items` exactly, the ledger order, a reordered or duplicated row refuses.

## 8. Monitoring and speed validity (C224, P469)

- `bench_watch` gains `--chain-json <path> --driver-pid <pid>`: binds the driver by pid + start time; per 5-min tick writes one receipt
  line (time, `pmset -g ac` watts / volts, battery, the driver alive, progress from `chain.json` `progress` = realized ledger length / planned,
  rows, DNF, current item, ETA from the mean item wall vs the prediction, errors, convergence and token distribution, correction-vs-finish
  note); at the driver's exit it finalizes the `pmset -g log` battery intervals over the leg window and writes `exit_state`.
- Speed-valid iff every tick 140 W / 28 V / battery > 20 %, no tick gap > 2 × interval, no on-battery interval in the window, the receipt
  finalized. Watcher death or a missing receipt → speed-invalid (fail closed). Power at entry is an entry check (NOT_STARTED); in-run
  power never stops a leg.
- Pair rule: if either leg of an s1 (or s2) ON / OFF pair is speed-invalid, that session's speed comparison leaves inference; with one
  valid session the ratio is reported descriptive, "not order-balanced". Quality is unaffected.
- P469: `Chain.watch_rows` counts the leg's earlier validated invocations' rows plus the running one's; red test = the rehearsal shape
  (validated pilot invocation 1 row, full invocation running with 0) must read 1, not 0. The chain's WATCH lines stay informational.

## 9. Exclusion (C227)

- `bench.local_gate run` holds `flock(LOCK_EX)` on `$STACK_WORKDIR/gate/RUNNING` for its lifetime and refuses when
  `$STACK_WORKDIR/p426/SEQUENCER.lock` or `$STACK_WORKDIR/p426/LEG.lock` is held (non-blocking try).
- The sequencer holds `SEQUENCER.lock` for its whole lifetime (idle gaps, PAUSE, overrun supervision); a second sequencer refuses.
- A P426 chain takes `LEG.lock` for its whole lifetime and refuses when `gate/RUNNING` is held. Lock fds are close-on-exec (no
  child inherits a lock; tested with a spawned child).
- Busy census after load: the owned router and worker (pid + start time) and the chain's own descendants are exempt by identity; any
  other model worker, benchmark driver or `opencode run` is foreign.

## 10. Freeze, timeouts, supervision

### 10.1 v8 (`bench.p426_freeze`, C226)
After B2 + P476 land: derives and verifies both arm commits / worktrees (§6.5 diffs), identical gitlinks and fork production tree ==
S's, equal `probe_code_sha256` / `scaffold_policy_sha256` / `generation_identity_sha256` across arms (`--print-identity`), pins.json
sha, grader image id, the REQUIRED frozen prompt date, the leg timeouts slot (filled after the pilot gate, §10.2, by an append-only
amendment record with its own hash); runs its preconditions (venvs synced to their locks in both worktrees, real entry points, K3, a
stack suite receipt); exclusive-creates the self-hashed record. Sequencer and every leg re-verify it against the live state.

### 10.2 Timeouts (C228)
Per-item limits are the probe's, identical in both arms (probe identity). Leg deadline, one value for both arms of a session:
`T = 1.5 × Σ_lang n_lang × max(w_lang) + 1800 s`, with `w_lang` = the largest per-item wall over both pilots (Python) and, for Go
(not piloted), the largest per-item wall of this entry's Go items in the P456 rehearsal and M63 rows; recorded in the amendment.

### 10.3 Overrun
At `T` the sequencer writes `OVERRUN_PAUSED` (and notifies), keeps holding both locks, keeps supervising the chain and the watcher, never
kills; the operator decides. When the chain exits the sequencer classifies and harvests as usual.

## 11. Harvest (C228, P437; data boundary)

### 11.1 Entry point
`bench.p426_harvest wave2 <leg-root>` (the Wave-1 path unchanged) runs after the chain and watcher exited, for EVERY leg state
(VALID, VALID-with-DNF, INVALID, NOT_STARTED, OVERRUN); the leg's dossier is labelled with its state. Nothing in a leg root is deleted
before its harvest is committed.

### 11.2 Closure and destinations
A typed recursive closure from `chain.json`: rows, manifests, sidecars, DNF records, `items/*.json`, A4 receipts and logs, grader reports,
per-item code diffs, final-tree manifests and every object they reference, web-evidence files, transcripts / events / stderr, the
watcher receipt, `RUNLOG.md`, `schedule.json`, stdout. Any referenced file missing → the harvest fails. `HARVEST.json` maps every file:
original path, original sha256, destination (`main` | `evidence`), published path, published sha256, compression. `main`:
`benchmark/results/p426/wave2/<leg>/` — everything except transcripts / events / stderr / fetched pages, which go to the `evidence`
stage (xz when > 8 MB). B8 / B6 resolve files only through `HARVEST.json`. Harvested bytes are re-verified before each `data(bench)` commit.

### 11.3 Scrub and secret gate (before compression)
P437 scrub rules (paths, user, host via `SCRUB_MANIFEST.json`), then a refusal scan over every staged byte: the exact values of the box's
configured secrets (read from the machine config / token files, compared in memory, never printed or logged), common credential formats
(`hf_…`, `sk-…`, `ghp_…`, `github_pat_…`, `AKIA…`, PEM private-key headers, `Authorization: Bearer`), email addresses. A hit
quarantines that file (not staged; listed by path and pattern name only) and fails the harvest for the operator.

### 11.4 Pushes
None automatic. `main` and `evidence` pushes each need the operator's in-turn approval.

## 12. Contract to B8 / B6

Per leg: `HARVEST.json`, the leg record (state, class, reason), the realized ledger, rows, `p426_dnf` records, `items/*.json` (§4.5), the
arm-equality receipt (§6.4), the watcher receipt (§8), the frozen record id. Pair keys: (session, language, item, seed). Decode rate per
item = Σ generated tokens ÷ Σ `D` deltas; acceptance = Σ accepted ÷ Σ proposed within a session.

## 13. Tests (test-first) and review

Red first; mocked ops / fake probe with the item barrier ON, plus one UNMOCKED production-topology test (sequencer → chain `--p426` →
fake probe, real argv / env / `chain.json`, real locks). Cover: argv per leg; refusals of §2; legacy `tg1` config / schedule goldens
byte-identical; `--models` (1 / 2 / 3, duplicate, empty, unknown); both orders and s2's language order at the probe; the probe's
`--evidence p426` manifest and its rejection when absent; the done hook receives row + cursor + load context; every §4.3 equality red
(count, tokens, session, backend, failed line, worker delta, A4 window) and the probe-kill trailing-request case green; §4.4 ON missing /
OFF present / 1-token exemption; settle timeout; every §5.1 class (each systemic kind stops; a DNF continues on the same worker with the
remaining items in order; the third DNF → systemic; worker replaced with a DNF-class stamp → systemic); `invalidate` writes `.stop` and
exits rc 2 after verified cleanup; legacy policies unchanged; arm-equality receipt mismatch; locks both directions + close-on-exec;
busy census owned vs foreign; watcher receipt, death, gap, pair rule; P469; timeout formula and `OVERRUN_PAUSED` (never kills); harvest
closure (a missing final-tree object fails), every leg state harvested, `HARVEST.json`, scrub, each secret pattern quarantines without
printing the value, size cap; sequencer order, the pilot gate, PAUSE, resume skips only VALID + harvested legs.

Four-eyes STRICT (P468): change review names the sensitive hunks (harvest / scrub / secret gate, chain-core policy and disposition,
locks).

## 14. Acceptance criteria

1. Every test in §13 passes; full stack suite green with `STACK_WORKDIR` set; legacy tg1 / M63 / M64 goldens byte-identical.
2. The pre-freeze rehearsal (§1) passes every listed check; its injected reconciliation mismatch stops the leg after that item.
3. v8 creates only when all §10.1 checks pass; a mutated arm diff, registry, gitlink, lock file or probe identity refuses.
4. A harvest of the rehearsal stage produces a complete `HARVEST.json`, zero secret hits, and every cited file resolvable.
5. No push, no change to production serving code (fork / mlx-serve), no change to the M59 / M61 / M62 / M64 / inject runners.

## 15. Non-goals, assumptions, residuals

- Non-goals: server code changes (C225); KV formats (C232); B6 / B8 / B3 builds; `Qwen3.8-27B-mlx-uniform-4bit` and later entries
  (the harness is entry-agnostic: only the §6.3 argv delta and the §11 restore are per entry).
- Assumptions: opencode 2.0.20 `request_usage` and `session=` attribution as in the P456 rehearsal (17 / 17); the serial cached-session
  path (one request at a time) makes worker counter deltas per item exact; the barrier mechanism works on real hardware as on the fake
  probe (verified by the rehearsal before v8).
- Residuals: a transcript can contain third-party text the secret gate cannot classify (fetched pages stay on `evidence`, never `main`);
  the Go timeout input is historical, not piloted (mitigated: overrun only pauses).
