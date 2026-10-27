# P426 B2 — tg1 legs for Wave 2 (A7) — SPEC v3.1, 2026-10-24 (four-eyes STRICT, C228)

**v3 → v3.1 applies design review round 3 of 3 (the last) and is NOT re-reviewed** (`docs/reviews/p426-b2/design-round3.dispositions.md`).
Round-3 changes are marked [r3].

Authority: P426 plan v4 §2 / §3 / §6 / §9, C205, C209 (P433), C214 (G4), C217 (P455), C218–C228, C232, C234, P481, AGENTS.md.
v1 → v2: design review round 1 of 3; v2 → v3: round 2 of 3 (`gpt-5.6-sol-high`, `glm-5.2-high`, Claude Sonnet; dispositions in
`docs/reviews/p426-b2/design-round{1,2}.dispositions.md`). v2 defined a P426 mode with its own evidence policy, transport policy,
disposition and records; v3 makes its interfaces exact (freeze lifecycle, failure truth table, ready records, real-adapter cause stamp,
pair gate, raw logs on `evidence`, leg-root inventory, lock order).

## Goal

Run the P426 Wave 2 — the tg1 agentic coding benchmark (opencode solving 43 Python / Go tasks), MTP ON vs OFF, for
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` — through the shipped stack (C218: each arm a stack commit served as committed), so that every
leg provably differs from its pair only in the entry's MTP state, every item's requests are reconciled against two independent sources and its
engagement proven, systemic problems stop the run at once while an isolated item incident is recorded and the run continues, and every
citable byte is harvested — producing the per-session paired evidence the pair verifier (B8) and the signals sheet (B6) need for the
operator's ship call (C204). The chain is the proven tg1 runner; B2 adds what P426 needs and changes nothing an earlier chain relied on
except where a ruling says so (C221: the hard-coded pick pair and overlay generation are retired).

## 1. Legs, gates, records

One leg = ONE `run_tg1_chain.py --p426` invocation for ONE entry and ONE session, from the arm's frozen worktree, launched by the
Wave-2 sequencer (`bench.p426_wave2`). The sequencer records each leg's end time in `$STACK_WORKDIR/p426/LAST_LEG_END`; the chain refuses
to start before 600 s have passed since it.

| # | Leg | Arm worktree | Chain argv (besides §6.6's common flags) | Items | Record required |
|---|---|---|---|---|---|
| R1 | `tg1-p426-rehearsal-{off,on}` | B2 commit / throwaway ON commit | `chain s1 --rehearsal` | 1 + 2 (smoke shape) | rehearsal manifest |
| R2 | `tg1-p426-rehearsal-mismatch` [r3] | ON rehearsal commit | `chain s1 --rehearsal --inject reconcile-mismatch` | 2 | rehearsal manifest |
| R3 | `tg1-p426-rehearsal-kill` [r3] | OFF rehearsal commit | `chain s1 --rehearsal --inject stall-kill` | 2 | rehearsal manifest |
| 1 | `tg1-p426-off-pilot` | `stack-p426-off` | `pilot` | first 5 of s1's Python order (seed 1001) | v8 base |
| 2 | `tg1-p426-on-pilot` | `stack-p426-on` | `pilot` | same 5 | v8 base |
| 3 | `tg1-p426-off-s1` | off | `chain s1` | all 22 Python then all 21 Go, s1 order (§7) | v8 base + timeout amendment |
| 4 | `tg1-p426-on-s1` | on | `chain s1` | same | same |
| 5 | `tg1-p426-on-s2` | on | `chain s2` | all 21 Go then all 22 Python, s2 order (§7) | same |
| 6 | `tg1-p426-off-s2` | off | `chain s2` | same | same |
| 7 | `tg1-p426-on-reload` | on | `chain reload` | the pilot's 5 items | same |
| 8 | `tg1-p426-off-reload` | off | `chain reload` | same | same |
| 9–10 | `tg1-p426-{off,on}-makeup` | off, on | `makeup --occurrences <file>` | §5.5; operator-triggered only, when DNFs exist; the sequencer stops after leg 8 [r3] | same |

- **Records (hash-linked, immutable, exclusive-created):** the rehearsal manifest (written by `bench.p426_freeze rehearsal`: the two
  commits, worktrees, scratch out-root, `rehearsal: true`; never accepted by legs 1–10); **v8 base** (§10.1); the **timeout amendment**
  (§10.2; carries v8 base's sha256). `--rehearsal` accepts only a rehearsal manifest and writes only under
  `$STACK_WORKDIR/p426/rehearsal/`; legs 1–2 require v8 base; legs 3–10 require v8 base + the amendment.
- **Pre-freeze rehearsal:** through the real topology (router, worker, opencode, docker grader, item barrier, reconciliation, watcher,
  harvest into a scratch stage); never graded, paired or published; each run on a fresh root [r3]. R1 (positive pair) must show: every
  barrier fires and its ready / item records exist, reconciliation exact, ON counters present and OFF absent, the pair gate passes, the
  harvest is complete. R2 (negative): the injected reconciliation mismatch stops the leg after that item, `INVALID`. R3: one real probe
  kill (a lowered stall limit on one item; `--inject` exists only with `--rehearsal`) is classified as a scored strict fail with its
  failed-line case recorded. R2 / R3 are excluded from the pair gate; v8 requires R1 VALID, R2 INVALID for exactly that reason, R3 VALID.
- **Pilot gate (after legs 1–2):** both legs VALID (§5.1), 5 / 5 items reconciled, zero DNF, ON engagement proven on every eligible
  request (§4.4), both speed-valid (§8), the pair gate passed (§6.5); then the sequencer writes the timeout amendment. Otherwise it stops
  for the operator. Pilot rows never enter pairs or signals.
- A systemic failure stops the leg and the sequencer (§5.1). A rerun is an operator decision, labelled, on a fresh out-root.

## 2. P426 mode

- `--p426` selects the ChainConfig `tg1-p426` (config_id distinct from `tg1`, flat record layout) and refuses: `--smoke`, `--pred-s`,
  `--generation-sha`, the `C147_OVERLAY` environment override, `--frozen-date-from`, a missing `--models` / `--out-root` /
  `--campaign-core` / `--frozen-prompt-date` / `--probe-code-sha` / `--policy-sha` / `--frozen-record`, an out-root that exists, more
  than one model, a record of the wrong kind for the leg (§1).
- C221 applies to EVERY tg1 mode [r3]: the required `--models` list, the committed `<WT>/main_models.yaml` served verbatim, no overlay
  generation, `--predictor` as an assertion, per-model predictions from the pilot mean else a recorded generic default
  (`chain_core.PRED_S` retired from the tg1 path). Without `--p426` everything else is as at the B2 base commit: the item order and
  `schedule_sha256` for the M63 / P223 argv are byte-identical to golden values recorded from the base commit; the serialized `tg1`
  ChainConfig differs only in the C221 fields, its golden refreshed with old → new recorded (test).
- The chain owns router start, load, A4, M50, worker tripwires, unload and stop (A+, C219). The P426 checks run inside the chain; the
  sequencer launches, gates pairs (§6.5), supervises (§10.3) and harvests (§11).
- Probe-code edits (all in the probe closure; `probe_code_sha256` moves once, equal across arms, v8): `tg1_runner.TG1_P426_EVIDENCE`
  (= `TG1_EVIDENCE` with `item_barrier="on"`); `run_tg1_probe.py --evidence p426` selecting it; `arm_opencode.OpencodeArm.transport_cause`
  returns the cause when `m64 or p426` (today `m64` only); [r3] in P426 mode an abort manifest carries the gate report WITH the full
  `request_usage` list, the `session_id`, whether a request was in flight (message id) and the termination evidence
  (`report_gate_on_abort` extended to p426). Defaults unchanged.
- Chain-core edits, enumerated [r3]: every site that branches on `transport_policy` (`chain_core.py` at the `incident_retry` tests near
  lines 526, 1318, 1353, 1774, 1906, 2000 at the base commit) gets an explicit `p426_continue` branch; none falls through to the
  `abort_restart` side. `chain_hooks`: `invalidate` joins `KINDS`, `BEFORE_KINDS`, `AFTER_KINDS`, `from_dict` and the disposition
  vocabulary; `after_attempt` / `before_attempt` gain a context argument (row, ready record, load context) with legacy hooks unchanged;
  in P426 mode a `HookInfrastructureError` (e.g. `/metrics` unreadable, a record write failing) is systemic, never `pre_spawn_incident`.
  One test per site.

## 3. Checkpoints

| Checkpoint | Checks (any failure → the class in §5) |
|---|---|
| Entry (before the router) | record kind + self-hash + live re-verification (§10.1); worktree HEAD == the record's arm commit, `git status` clean incl. submodules at their gitlinks; registry sha; the probe's live `--print-identity` from the worktree == the record; the target (and, ON, drafter) snapshot revisions and files hashed against fork `dev/p369_phase2/pins.json` (as Wave 1's B10) [r3]; `--predictor` assertion (§6.2); locks (§9); ≥ 600 s since `LAST_LEG_END`; no foreign busy process, no `:8000` listener, zero `session_cache_probe` / `opencode run` survivors; power (§8); then the whole-leg log boundaries are exclusive-created (§4.2) [r3] |
| After load | worker argv exact (§6.3); arm-equality receipt (§6.4), and for the second leg of a pair the receipt compared with the first leg's (§6.5) BEFORE item one [r3]; A4 gate PASS; A4 window reconciliation (§4.3) |
| Before every invocation | the entry checks except router absence, the idle gap and power (power here only marks speed, §8) [r3]; owned router / worker identities (pid + start time) unchanged; no foreign busy process (owned pids exempt by identity, §9) |
| Manifest (before item one of every invocation) | `runtime.evidence_policy` == `TG1_P426_EVIDENCE` — unconditional for `tg1-p426` (today's check is `per_arm` only) |
| Item `ready` barrier | registry sha, lifecycle hash, worktree clean, owned identities unchanged; then the ready record (§4.2) is written before `.go` |
| Item `done` barrier | the `ready` checks + per-item reconciliation and engagement (§4) |
| WATCH tick | power (§8, speed only) |
| Exit | §5.1 VALID conditions; build drift (entry == exit); owned processes stopped and verified; `:8000` free |

Hooks: the P426 `ChainHooks` returns `invalidate(reason)` from `before_attempt` (a `ready` check failed) or `after_attempt` (a `done`
check failed); both are persisted, answered with `.stop`, followed by the probe's cleanup-only exit, verified cleanup, leg `INVALID`,
rc 2. A transport incident never reaches `after_attempt` (the probe aborted; no `.done`); it is classified in `handle_incomplete` (§5.2).
The `done` hook receives the slot, the `.done` payload, the item's full row, the item's ready record and the load context.
`ChainOps.overlay` in P426 mode is `<WT>/main_models.yaml` (the served file; `overlay_sha` = the registry sha); `ensure_overlay` is skipped.

## 4. Per-item reconciliation and engagement (C225)

### 4.1 Sources
- **Client:** the row's `request_usage` — a list of `[message_id, output_tokens, prompt_tokens, budget]`, one per completed request
  (`token_turn_gate`, from opencode's stream) — and its outcome (`nonconv_kind`, `stop_reason`, `gate.requests_completed`,
  `gate.requests_completed_at_kill`, `termination`).
- **Server log:** `<WT>/logs/mlx_vlm.log` (append-only across legs; read from the byte cursor) `Request started` / `Request completed` /
  `Request failed` lines. The `Request completed` line is the per-request source of the draft counters: `_build_metrics_envelope`
  merges `draft_counters` into the payload and `_format_verify_counters` appends every `draft_*` key (fork `0f30522c`,
  `server/generation.py`) [r3].
- **Worker counters:** `GET /metrics` on the owned worker: `summary.requests_started / requests_completed / requests_failed / in_flight /
  prompt_tokens_total / generated_tokens_total`, and decode time `D = generated_tokens_total / avg_decode_tok_s` (= the worker's
  `Σ decode_elapsed_s`; 0 when no tokens).
- The field pairing between `request_usage` and the log line (which client count equals which server count) is the one the P456
  rehearsal matched 17 / 17; a test pins it on a committed rehearsal row + log-slice fixture.

### 4.2 Ready record and settle
- At `ready`, before `.go`: `items/<slot>.ready.json` (log byte cursor, worker snapshot, owned identities, time). Missing at `done` or at a
  DNF → systemic.
- Settle (at `done`, and after an aborted invocation): poll every 2 s until `in_flight == 0` and every `Request started` after the cursor
  has its terminal line; bound 900 s in v8 base (a disconnect during a long prefill is noticed only when prefill ends), raised in the
  timeout amendment to max(900 s, 2 × the largest single-request elapsed over both pilots) [r3]. Not settled → systemic.
- Whole-leg log boundaries [r3]: before the router starts, `log_bounds.json` is exclusive-created with path, device, inode and byte offset of
  `<WT>/logs/mlx_vlm.log` and `<WT>/logs/main_model.log`; finalized after teardown; a truncated or replaced file → systemic (in the run) or a
  failed harvest (after). The harvest takes exactly these ranges.
- The next item's window starts at its own ready record, written after the previous item's settle; a DNF's lines are bounded by its
  ready record and the post-settle cursor.

### 4.3 Equalities
Let `F` = the `Request failed` lines in the window, `C` = the completed lines, `S` = the started lines, `Δ` = worker deltas.
- Serial: every `Request started` line shows `in_flight=1`, and no start precedes the previous request's terminal line.
- Every line in `C` carries `session=` == the row's `session_id` and `backend=cached_session`; `C` equals `request_usage` in count and
  order on the pinned field pairing; `Δrequests_completed == |C|`; `Δrequests_started == |S| == |C| + |F|`; `Δrequests_failed == |F|`;
  `Δprompt_tokens_total` / `Δgenerated_tokens_total` == the sums over `C`.
- Allowed `F`, all other cases systemic:

| Item outcome (structured evidence) | `|F|` | Condition |
|---|---|---|
| completed normally | 0 | — |
| probe kill or `client_inactivity` (scored strict fail), at a request boundary | 0 | `gate.requests_completed_at_kill == |C|` (null for `client_inactivity` → `gate.requests_completed == |C|`) |
| the same, with a request in flight | 1 | the last line of the window, `error=stream_closed_before_completion`, `|S| == |C| + 1` |
| DNF (any DNF cause), the abort at a request boundary | 0 | `|C| == len(request_usage)` from the abort manifest [r3] |
| DNF, a request in flight that the server failed | 1 | the trailing `stream_closed_before_completion` line as above |
| DNF, a request in flight that the server completed before the client lost it | 0 | exactly one trailing `C` line absent from `request_usage` (the abort manifest's in-flight message), its session == the row's, recorded as `completed_unaccounted` [r3] |

The DNF rows are decided by observed started / completed / failed state, not by the cause name (`connection` also covers
established-stream resets) [r3].

- Per load, before the first item: the A4 window's 3 `anon:*` requests + its own 4-request `ses_*` session equal the A4 receipt.
- A line in the window not attributable by these rules, or unparseable → systemic.

### 4.4 Engagement
- ON: every completed request with `generated_tokens ≥ 2` carries integer `draft_rounds ≥ 1`, integer `draft_n ≥ 1`, integer
  `0 ≤ draft_n_accepted ≤ draft_n`, `draft_kind=mtp`. Basis (code-read, fork `0f30522c`): the first token comes from prefill
  (`speculative/mtp.py` `emitted = 1  # caller already yielded the first bonus`); `speculative_stats_since` returns null when no round ran
  (`speculative/common.py`). Requests with `generated_tokens ≤ 1` are counted and listed, not judged. The pilot is the known positive.
  Fields read from the item's `Request completed` lines (§4.1); `generated_tokens` is the reconciled value [r3]. Scope: item requests are
  judged; the A4 window's requests are recorded, not judged [r3].
- OFF: no `draft_*` field on any request.
- Violation → systemic (`invalidate`).

### 4.5 Item record (`items/<slot>.json`, written before the barrier answer; DNF: `items/<slot>.dnf.json`)
The ready record's sha256, the log slice's byte range and sha256 (raw lines go to `evidence`, §11.2), the worker snapshots, the parsed
per-request table (session, backend, prompt / generated tokens, decode rate as logged, draft counters, failed-line errors), the per-item
totals (requests, tokens, `ΔD`, accepted / proposed sums), every check's result and the verdict.

## 5. Failure policy (C220)

### 5.1 Classes

| Class | Conditions | Effect |
|---|---|---|
| NOT_STARTED | an entry check fails before the router starts | nothing launched; leg record `NOT_STARTED` |
| Systemic | record / registry / lifecycle / probe-identity / M50 drift at any checkpoint; owned router or worker gone or replaced; §4.3 or §4.4 violated; settle timeout; a missing ready record; unparseable line; uncertain cleanup (survivors, containers); a foreign busy process; an abort without a DNF cause; > 2 DNF in the leg; a pair-gate mismatch (§6.5) | stop at once (`invalidate` at a barrier; between invocations no relaunch); leg `INVALID`; sequencer stops |
| Item DNF | the probe aborts an item with `transport_abort.cause` ∈ {`connection`, `dropped_stream`, `timeout`, `client_timeout`} AND owned router and worker identities unchanged and healthy, settled, §4.3's DNF row holds, certain empty cleanup | a `p426_dnf` record (§5.3); the leg continues on the same load (§5.2) |
| Scored strict fail | in-probe non-convergence (budget hit, turn cap, exec timeout, `client_inactivity`, kills) | a normal row, `acc_strict = 0` |
| Speed-invalid | an in-run power / watcher failure (§8) | quality continues; the leg's speed block is excluded (§8) |

VALID = chain rc 0, status `finished`, no `running` / quarantined record, the per-item realized ledger (§7) == the plan, every `done`
reconciled, every DNF settled, verified teardown, `:8000` free. A leg with a DNF is VALID-with-DNF.

### 5.2 Mechanism: transport policy `p426_continue`
A third `TRANSPORT_POLICIES` member, used only by `tg1-p426`, with its own leg loop in the flat layout (the shape of M64's
`run_block_leg`: derive the remaining slots from the per-item ledger, run one invocation over them, re-derive): an incomplete invocation
goes to `handle_incomplete`, which checks owned identities first (changed → systemic), settles, classifies the stamped cause, writes the
`p426_dnf` record (chain.json first, then the sidecar) and returns to the loop, which relaunches the probe for the remaining slots of
the leg in order on the same loaded instance (no reload, retries 0). `abort_restart` and `incident_retry` are unchanged (their tests pinned).

### 5.3 `p426_dnf` record
Slot, item, session, language, seed, arm, the abort stamp (cause, evidence files with sha256), owned identities at the incident and after,
the settle result, the item record. Not a row; never graded; never labelled a model failure.

### 5.4 Scoring of DNF slots — RULED C235 (G1)
B2 records every planned slot as a row or a DNF. AGENTS.md ranks by `acc_strict@budget` "DNF included"; C220 says a transport DNF is
"never graded, never a strict fail". Ruling: `acc_strict@budget` over ALL planned slots with a DNF counted as
a non-success (AGENTS.md; no denominator shrink), labelled `transport_dnf` (not a model failure, C220's intent), DNF counts and causes per
arm and session beside it with an attention flag when they differ between arms [r3], the make-up result reported as a sensitivity line.

### 5.5 Make-up legs (operator's call)
Input: an occurrences file — records `(session, language, item, seed, arm_of_dnf, occurrence)`, duplicates across sessions allowed — the
ordered union of every DNF occurrence of both arms and both sessions; BOTH make-up legs run the whole union (C220: "for BOTH arms", so
every rerun item has a pair). One fresh-load leg per arm (OFF then ON); inside a leg, one invocation per (session, seed, language) group
[r3] in s1-then-s2 and original language order, items in their original order; own out-root namespace `makeup`; excluded from the
per-session pairs; a repeat DNF is a finding. Same checkpoints and classes.

## 6. Models and arms (C221, C218)

1. **`--models`** REQUIRED, comma-separated, ≥ 1, no duplicates or empty names, each a `models:` entry of the served committed
   registry; recorded in the ChainConfig / `chain.json`. P426 mode requires exactly one. Generic schedule (legacy two-pick semantics):
   s1 models in the given order, s2 models reversed, reload the first model; tested with 1, 2 and 3 models. In P426 mode s2 additionally
   reverses the LANGUAGE order (§7). The frozen M59 / M61 / M62 / M64 / inject runners are untouched.
2. **Served config:** `<WT>/main_models.yaml` verbatim (`MLX_SERVE_CONFIG`), no overlay generation. `--predictor off|mtp` keeps selecting
   the out-root family, the tripwire branch and the ON / OFF out-root isolation, and is an assertion: the served entry has all three
   C177 keys (mtp) or none (off), else refused.
3. **Worker argv:** the complete argv equals the one mlx-serve builds from the entry; ON = OFF + exactly `--draft-kind mtp --draft-model
   caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter --mtp-verify-scan joint_v1`.
4. **Arm-equality receipt (after load, every leg):** with `<WT>` (worktree root) and `<OUT>` (out-root) canonicalized in every path value:
   router and worker argv; the full environment of the router, the worker and the probe: every non-secret value after canonicalization
   [r3], except a closed list of volatile keys (`_`, `OLDPWD`, `PWD`, `SHLVL`, `TERM_SESSION_ID`, `SECURITYSESSIONID`, `__CF*`) recorded as
   keys only; values of credential keys (§11.3's classifier) NEVER recorded (not even hashed) — compared in memory across the pair,
   recorded as `same` / `different`; per distinct interpreter the router, worker and probe use (resolved from their pids) [r3]: its path
   and a verified content inventory — for every non-editable distribution, name, version and its `RECORD` entries each re-verified
   against the installed bytes (a mismatch is systemic), hashed as sorted `(path, digest)`; editable distributions (`mlx-vlm`,
   `mlx-serve`) are identified by their resolved source tree (`<WT>/src/<sub>`, at the gitlink, `status --porcelain` empty), their
   editable metadata excluded [r3]; the native libraries the worker actually loaded (`vmmap` / `lsof -p <worker>`: the loaded paths of
   `libmlx.dylib`, `mlx.metallib`) and the sha256 of each loaded file [r3]; the probe entry's resolved path; the target / drafter
   snapshot revisions and file hashes (§3) [r3].
5. **Pair gate:** for the second leg of each pair (pilots, s1, s2, reload, make-up) the sequencer passes the first leg's receipt path; the
   chain compares at its after-load checkpoint, before item one [r3] — allowed differences: the three §6.3 argv items, the drafter
   snapshot (ON only), the arm commit and the canonicalized roots; any other difference, or a credential value `different` → systemic. The
   sequencer re-checks after the leg and writes an immutable pair dossier (`pairs/<pair>.json`: both receipts' sha256, both legs'
   `HARVEST.json` sha256, the verdict) [r3]. Credential equality lives only in memory: a sequencer restart between the two legs of a pair
   voids the pair — both legs run again on fresh roots [r3].
6. **Arms:** OFF = the v8 commit; ON = it + exactly the §11 restore on local branch `p426-on`. Commit diff = the three registry lines, the
   `PROVISIONAL P426` note, `benchmark/bench/tests/test_opencode_probe_seeding.py` (not on the serving path); served diff = the entry's
   three keys. v8 asserts both.
7. Common flags: `--p426 --models Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --predictor <arm> --out-root $STACK_WORKDIR/p426/wave2/<leg>
   --probe-code-sha <v8> --policy-sha <v8> --frozen-prompt-date <v8> --campaign-core <arm commit> --frozen-record <record path>`; the
   sequencer generates the argv per leg; tests pin it.

## 7. Schedule, order, ledger (C223)

- P426 mode: each language's items in `random.Random(seed).sample(sorted(pool), len(pool))` order (s1 1001, s2 2002), no later sort;
  s1 Python then Go; s2 Go then Python; pilot and reload = the first 5 of s1's Python order; makeup = the occurrences file.
- A session leg's first invocation is the in-load pilot phase (the first 5 items of its first language: Python in s1, Go in s2) as today;
  the phase only splits invocations — its rows are ordinary rows of the leg, in pairs, with the barrier and all checks. A pilot leg and
  a reload leg are 5 items, which is exactly one in-load pilot phase [r3].
- The schedule is frozen in `chain.json` before launch (`schedule_sha256`, `freezes_schedule` true for `tg1-p426`). The per-item realized
  ledger (slot → row | DNF, invocation, order index) is persisted at each barrier answer and DNF; `check_realized` requires it == the plan
  slot for slot in order. Tests: s2's first language is Go at the probe's `--items`; both orders exact; a reordered, missing or duplicated
  slot refuses; after a DNF the remaining items ran in order.

## 8. Monitoring and speed validity (C224, P469)

- `bench_watch` gains `--chain-json <path> --driver-pid <pid>`: binds the driver by pid + start time; per 5-min tick writes one receipt
  line (time, `pmset -g ac` watts / volts, battery, the driver alive, progress = realized-ledger length / planned, rows, DNF, current item,
  ETA from the mean item wall vs the prediction, errors, convergence and token distribution, correction-vs-finish note); at the driver's
  exit it finalizes the `pmset -g log` battery intervals over the leg window and writes `exit_state`.
- Speed-valid iff every tick 140 W / 28 V / battery > 20 %, no tick gap > 2 × interval, no on-battery interval in the window, the receipt
  finalized. Watcher death or a missing receipt → speed-invalid. Power at entry is an entry check (NOT_STARTED); in-run power never stops a
  leg (C235 G2).
- Pair rule: if either leg of an s1 (or s2) ON / OFF pair is speed-invalid, that session's speed comparison leaves inference; with one
  valid session the ratio is descriptive, "not order-balanced". Quality is unaffected.
- Decode-rate estimator (B6 / B8 input, plan §6 T2): per item, `Σ max(generated_tokens_i − 1, 0) / ΔD` over its completed requests [r3]
  (`decode_elapsed_s` spans first to last token, so the first token is excluded from the numerator; ≤ 1-token requests contribute 0 tokens
  and a negligible `D`, listed). Same definition in both arms; the barrier's between-item waits are outside every request.
- The sequencer polls the watcher's pid + start time at every tick; a dead watcher marks the leg speed-invalid in the leg record [r3].
- P469: `Chain.watch_rows` counts the leg's earlier validated invocations' rows plus the running one's; red test = the rehearsal shape
  (validated pilot invocation 1 row, full invocation running with 0) reads 1. The chain's WATCH lines stay informational.

## 9. Exclusion (C227)

Locks are `flock(LOCK_EX | LOCK_NB)` on files under `$STACK_WORKDIR`, fds close-on-exec, held for the holder's lifetime. Acquisition
is serialized by an arbiter [r3]: every actor takes `$STACK_WORKDIR/locks/ARBITER.lock` (`LOCK_EX`, blocking, bounded 30 s, held only for
the acquisition step), then tries the opposing locks, then takes its OWN lock, then releases the arbiter; an opposing lock held → release
the arbiter, refuse. So of two simultaneous starters exactly one runs. The sequencer never takes `LEG.lock`; each chain it launches does.
- `bench.local_gate run`: own `gate/RUNNING`; opposing `p426/SEQUENCER.lock`, `p426/LEG.lock`.
- Wave-2 sequencer: own `p426/SEQUENCER.lock` (idle gaps, PAUSE, overrun supervision included); opposing `gate/RUNNING`.
- P426 chain: own `p426/LEG.lock`; opposing `gate/RUNNING`. ("Both locks" in §10.3 = `SEQUENCER.lock` + `LEG.lock`.)
- Busy census after load: the owned router and worker (pid + start time) and the chain's descendants are exempt by identity; any other
  model worker, benchmark driver or `opencode run` is foreign.
- Tests: each direction refuses; a simultaneous start of the gate and a chain (barrier-synchronized threads / processes) lets exactly one
  run; a spawned child holds no lock.

## 10. Freeze, timeouts, supervision

### 10.1 v8 base (`bench.p426_freeze`, C226)
After B2 + P476 land and the rehearsal passed: derives and verifies both arm commits / worktrees (§6.6 diffs), identical gitlinks and fork
production tree == the serving build's (S′ since C236: the stack commit that takes the fork's current main and mlx 0.32.4), equal `probe_code_sha256` / `scaffold_policy_sha256` / `generation_identity_sha256` across arms (`--print-identity`),
pins.json sha, grader image id, the REQUIRED frozen prompt date, the pilot deadline (§10.2); runs its preconditions (venvs synced to their
locks in both worktrees, real entry points, K3, a stack suite receipt); exclusive-creates the self-hashed record. The sequencer and every
leg re-verify it against the live state.

### 10.2 Deadlines (C228)
Per-item limits are the probe's, identical in both arms. A leg deadline is `T = 1.5 × Σ_lang n_lang × w_lang + 1800 s`, one value for both
arms of a session. Pilot deadline (in v8 base): `w_python` = the largest per-item wall of this entry's Python items in the P456 rehearsal
and M63 rows. Timeout amendment (after the pilot gate): `w_python` = the largest per-item wall over both pilots and the historical value;
`w_go` = the largest of this entry's Go items in the P456 rehearsal and M63 rows (not piloted; historical walls had no barrier waits —
covered by the 1.5 × + 1800 s allowance, and an overrun only pauses).

### 10.3 Overrun
At `T` the sequencer writes `OVERRUN_PAUSED` (and notifies), keeps holding `SEQUENCER.lock` (the chain keeps `LEG.lock`), keeps
supervising the chain and the watcher, never kills; the operator decides. When the chain exits the sequencer classifies and harvests.

## 11. Harvest (C228, P437; data boundary)

### 11.1 Entry point
`bench.p426_harvest wave2 <leg-root>` (the Wave-1 path unchanged) runs after the chain and watcher exited, for EVERY leg state
(VALID, VALID-with-DNF, INVALID, NOT_STARTED, OVERRUN); the dossier is labelled with its state. Nothing in a leg root is deleted before its
harvest is committed.

### 11.2 Inventory and destinations
- Every regular file under the leg root (and the leg's server-log byte range) is inventoried; each gets a destination or a recorded
  exclusion reason from a closed rule table; an unmatched file fails the harvest. References are resolved transitively (rows, manifests,
  sidecars, DNF records, ready / item records, A4 receipts, grader reports, final-tree manifests and every object they reference, web
  evidence, the watcher receipt); a referenced file missing fails the harvest. Barrier and control files (`.ready`, `.go`, `.done`,
  `.continue`, `.stop`, ack / cancel files, `STOP`) are harvested; their presence is checked against the leg state (e.g. a `.stop` for every
  `invalidate`).
- Symlinks [r3]: every file is examined with `lstat`; a symlink or non-regular file (anywhere, incl. final trees) is never followed or
  copied — it is recorded (path, link target string) and the harvest fails for the operator; every source path must resolve inside the
  leg root or the leg's log ranges.
- `main` (`benchmark/results/p426/wave2/<leg>/`): parsed and structured artifacts only — the leg record, `chain.json`, `schedule.json`,
  the realized ledger, rows, manifests, sidecars, DNF / ready / item records, grader reports, per-item code diffs, final-tree manifests,
  the arm-equality receipt, the watcher receipt, `HARVEST.json`.
- `evidence` stage: raw logs and streams — server-log slices, A4 logs, `RUNLOG.md`, stdout, stderr, transcripts, events, fetched pages,
  barrier / control files (xz when > 8 MB).
- `HARVEST.json` maps every file: original path, original sha256, destination, published path, published sha256, compression, exclusion
  reason. B8 / B6 resolve files only through it. Harvested bytes are re-verified before each `data(bench)` commit.

### 11.3 Scrub and secret gate (before compression)
- P437 scrub rules (paths, user, host via `SCRUB_MANIFEST.json`), then a refusal scan over the original AND the scrubbed bytes of every
  staged file.
- Exact secret values, compared in memory, never printed, logged or hashed into any output. Credential-key classifier [r3]: a key whose
  name matches `*TOKEN*`, `*KEY*`, `*SECRET*`, `*PASSWORD*`, `*CREDENTIAL*`, `*AUTH*` (case-insensitive) and is not on the committed
  non-secret allowlist (e.g. `TOKENIZERS_PARALLELISM`, the `KV_*` / `TQ_*` / `MLX_*` configuration keys the stack defines); a credential
  value shorter than 12 characters or a placeholder (`true`, `false`, `none`, `null`, `0`, `1`, empty, `changeme`) is not used for exact
  matching (the format scan still applies). Sources: those keys in the machine config (`${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh`),
  `<WT>/.env` of both arms, the sequencer's environment, and the whole content of the token files `~/.hftoken`, `~/.cache/huggingface/token`.
  A listed file that exists but cannot be read → the harvest refuses; absent files are recorded as absent. Each leg is harvested right after
  it ends (a rotation between leg and harvest is the residual, with the format scan as the backstop).
- Credential formats: `hf_…`, `sk-…`, `ghp_…`, `github_pat_…`, `AKIA…`, PEM private-key headers, `Authorization: Bearer`.
- Email addresses: the operator's address and domain (from `SCRUB_MANIFEST.json`) are refusals; any other address is listed for the
  operator before the `evidence` push, not a refusal.
- A refusal quarantines that file (not staged; listed by path and pattern name only) and fails the harvest for the operator.

### 11.4 Pushes
None automatic. `main` and `evidence` pushes each need the operator's in-turn approval.

## 12. Contract to B8 / B6

Per leg via `HARVEST.json`: the leg record (state, class, reason), the realized ledger, rows, `p426_dnf` records, ready / item records
(§4.5), the arm-equality receipt, the watcher receipt (§8), the record ids; per pair the immutable pair dossier (§6.5) [r3]. Pair keys:
(session, language, item, seed). Decode rate per §8; acceptance = Σ accepted ÷ Σ proposed within a session. DNF scoring (C235 G1): `acc_strict@budget`
over ALL planned slots, a DNF counted as a non-success labelled `transport_dnf`; per-arm DNF counts and causes; make-up as sensitivity.

## 13. Tests (test-first) and review

Red first; mocked ops / fake probe with the item barrier ON, plus one UNMOCKED production-topology test (sequencer → chain `--p426` →
fake probe, real argv / env / `chain.json`, real locks), plus real-adapter tests where the fake cannot speak for production
(`OpencodeArm(mode="tg1", p426)` stamps `dropped_stream` / `connection` / `timeout` through manifest creation; the `request_usage` ↔ log
pairing on the committed rehearsal fixture). Cover: argv per leg and record kinds; §2 refusals; legacy goldens byte-identical; `--models`
(1 / 2 / 3, duplicate, empty, unknown); s2 Go first at the probe; the chain refuses a manifest without `TG1_P426_EVIDENCE`; ready records
before `.go`; every §4.3 equality red (count, tokens, session, backend, overlap, worker delta, A4 window) and every row of the failed-line
table green, plus its off-table variants red; settle bound; §4.4 ON missing / `draft_n = 0` / non-integer red, OFF present red, 1-token
exemption; every §5.1 class; a DNF followed by a normal item (windows, re-baseline); remaining items run in order after a DNF; the third DNF
→ systemic; a changed worker with a DNF-class stamp → systemic; a transport DNF never triggers `invalidate` and an engagement failure never a
DNF; `invalidate` at `ready` and at `done`; legacy policies unchanged; arm-equality receipt fields, the pair gate (each allowed difference
passes, any other refuses, secrets never written); locks (§9 incl. the race); busy census owned vs foreign; watcher receipt, death, gap,
pair rule; decode estimator; P469; deadlines and `OVERRUN_PAUSED` (never kills); harvest inventory (unmatched file fails, missing reference
fails, every leg state, control-file presence rules, destinations), `HARVEST.json`, scrub, each secret source and pattern quarantines
without printing the value, an unreadable secret file refuses, foreign emails listed only; make-up occurrences across both sessions run
under their own seeds; sequencer order, the pilot gate, PAUSE, resume skips only VALID + harvested legs. [r3] Also: the P426 abort
manifest carries `request_usage` / session / in-flight message (real adapter, boundary and in-flight aborts); each `transport_policy`
branch site; `invalidate` round-trips `from_dict`; a P426 hook infrastructure error is systemic; the `completed_unaccounted` DNF case; the
pair comparison before item one; a sequencer restart between paired legs voids the pair; the verified content inventory (an installed
file mutated without its `RECORD` refuses; editable metadata differing only in worktree path passes); loaded-library paths from the live
worker; snapshot hashes; the volatile-key list; the credential classifier (`TOKENIZERS_PARALLELISM=false` and a `1`-valued `*KEY*`
variable never quarantine anything; a 40-character token in a transcript does); a symlink in a final tree fails the harvest without
being read; whole-leg log boundaries (truncation / replacement detected); the arbiter (two simultaneous starters → exactly one runs);
the watcher-death poll; make-up grouping by (session, seed, language); the decode estimator with a 0-token request; R2 / R3 rehearsal
injections refuse without `--rehearsal`.

Four-eyes STRICT (P468): the change review names the sensitive hunks (harvest / inventory / scrub / secret gate, the pair gate, chain-core
policy, ledger and dispositions, locks, the probe-code edits).

## 14. Acceptance criteria

1. Every test in §13 passes; full stack suite green with `STACK_WORKDIR` set; legacy tg1 / M63 / M64 goldens byte-identical.
2. The pre-freeze rehearsal runs R1 VALID, R2 INVALID for exactly the injected mismatch, R3 VALID with the kill scored (§1) [r3].
3. `bench.p426_freeze` creates the rehearsal manifest, v8 base and the timeout amendment only when their checks pass; a mutated arm diff,
   registry, gitlink, lock state or probe identity refuses; a leg refuses a record of the wrong kind.
4. A harvest of the rehearsal stage produces a complete `HARVEST.json`, zero refusals, every file inventoried and every reference resolvable.
5. No push; no change to production serving code (fork / mlx-serve); no change to the M59 / M61 / M62 / M64 / inject runners.

## 15. Non-goals, assumptions, residuals

- Non-goals: server code changes (C225); KV formats (C232); B6 / B8 / B3 builds; `Qwen3.8-27B-mlx-uniform-4bit` and later entries (the
  harness is entry-agnostic: only the §6.3 argv delta and the §11 restore are per entry).
- Assumptions: opencode 2.0.20 `request_usage` and `session=` attribution as in the P456 rehearsal (17 / 17); the serial cached-session path
  (checked per request, §4.3); the barrier mechanism works on real hardware as on the fake probe (shown by the rehearsal before v8).
- Residuals: third-party text in transcripts the secret gate cannot classify (on `evidence` only, listed emails reviewed before its push);
  the Go deadline input is historical, not piloted (an overrun only pauses).
