# P426 B2 — tg1 legs for Wave 2 (A7) — SPEC v3.2, 2026-10-27 (four-eyes STRICT, C228)

**v3.1 → v3.2 applies the design opinion of the reset review budget (the operator reset the rounds, 2026-10-27; four-eyes 0.7.0)
once and is NOT re-reviewed** (`docs/reviews/p426-b2/design-opinion-r4.dispositions.md`); its changes are marked [o4]. C238 (2026-10-27)
drops the cross-pair credential comparison (§6.4–6.5); the round-2 delta review of [o4], §16 and C238 is applied once, marked [d2], NOT
re-reviewed (`docs/reviews/p426-b2/design-round2-delta.dispositions.md`).

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

| # | Leg | Arm worktree | Chain argv (besides §6.7's common flags [o4]) | Items | Record required |
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
  harvest is complete; it records the pair's full environment diff (§6.4) and every ON request's `(generated_tokens, draft_rounds)`
  (§4.4) [o4]. R2 (negative): the injected reconciliation mismatch stops the leg after that item, `INVALID`. R3: one real probe
  kill (a lowered stall limit on one item; `--inject` exists only with `--rehearsal`) is classified as a scored strict fail with its
  failed-line case recorded. R2 / R3 are excluded from the pair gate; v8 requires R1 VALID, R2 INVALID for exactly that reason, R3 VALID.
- **Pilot gate (after legs 1–2):** both legs VALID (§5.1), 5 / 5 items reconciled, zero DNF, ON engagement proven on every eligible
  request (§4.4), both speed-valid (§8), the pair gate passed (§6.5); then the sequencer writes the timeout amendment. Otherwise it stops
  for the operator. Pilot rows never enter pairs or signals.
- A systemic failure stops the leg and the sequencer (§5.1). A rerun is an operator decision, labelled, on a fresh out-root.
- **Attempts and pairs** [o4]: each launch of a leg is an attempt `<leg>.a<n>` (n from 1) with its own out-root
  `$STACK_WORKDIR/p426/wave2/<leg>.a<n>` and harvest destination `benchmark/results/p426/wave2/<leg>.a<n>/` (§11.2's `<leg>` is the attempt name); nothing of an earlier
  attempt is reused or overwritten. A pair is bound by its dossier (§6.5), which names its two attempts; B8 / B6 consume only attempts a
  dossier names. 
  Pushes go per pair, after its dossier (§11.4).

## 2. P426 mode

- `--p426` selects the ChainConfig `tg1-p426` (config_id distinct from `tg1`, flat record layout) and refuses: `--smoke`, `--pred-s`,
  `--generation-sha`, the `C147_OVERLAY` environment override, `--frozen-date-from`, a missing `--models` / `--out-root` /
  `--campaign-core` / `--frozen-prompt-date` / `--probe-code-sha` / `--policy-sha` / `--frozen-record`, an out-root that exists, more
  than one model, a record of the wrong kind for the leg (§1).
- C221 applies to EVERY tg1 mode [r3]: the required `--models` list, the committed `<WT>/main_models.yaml` served verbatim, no overlay
  generation, `--predictor` as an assertion, per-model predictions from the pilot mean else a recorded generic default
  (`generic_pred_s` = 250 s, today's fallback, recorded in `chain.json`) [o4]
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
  `abort_restart` side. `chain_hooks`: `invalidate` joins the hook vocabulary — `KINDS`, `BEFORE_KINDS`, `AFTER_KINDS`, `from_dict` — and, like `pre_spawn_incident`, has no
  slot disposition (the chain handles it before any `slot_disposition` call) [d2]; `after_attempt` / `before_attempt` gain a context argument (row, ready record, load context) with legacy hooks unchanged;
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
  `server/generation.py`; unchanged at S′ `c688e722`, `generation.py:661, 777–789`) [r3] [o4].
- **Worker counters:** `GET /metrics` on the owned worker: `summary.requests_started / requests_completed / requests_failed / in_flight /
  prompt_tokens_total / generated_tokens_total`, and decode time `D` = the worker's `Σ decode_elapsed_s`, computed as
  `generated_tokens_total / avg_decode_tok_s` from the unrounded snapshot values, and 0 when `avg_decode_tok_s == 0` [o4].
- The pairing between `request_usage` and the log lines is positional [o4]: the k-th `Request completed` line of the window pairs with the
  k-th `request_usage` entry, and per pair the line's prompt / generated tokens equal the entry's `prompt_tokens` / `output_tokens` (the
  fields the P456 rehearsal matched 17 / 17); a test pins it on a committed rehearsal row + log-slice fixture.

### 4.2 Ready record and settle
- At `ready`, before `.go`: `items/<slot>.ready.json` (log byte cursor, worker snapshot, owned identities, time). Missing at `done` or at a
  DNF → systemic; an abort before the slot's `.ready` (no ready record) is systemic [o4].
- Settle (at `done`, and after an aborted invocation): poll every 2 s until `in_flight == 0` and every `Request started` after the cursor
  has its terminal line; bound in v8 base: max(900 s, 2 × the largest single-request elapsed of this entry's Python and Go items in the
  P499 rehearsal on S′ and the M63 / P456 rows) [o4] (a disconnect during a long prefill is noticed only when prefill ends), raised in the
  timeout amendment to max(that, 2 × the largest single-request elapsed over both pilots) [r3]. Not settled → systemic.
- Whole-leg log boundaries [r3]: before the router starts, `log_bounds.json` is exclusive-created with path, device, inode and byte offset of
  `<WT>/logs/mlx_vlm.log` and `<WT>/logs/main_model.log`; finalized after teardown; a truncated or replaced file → systemic (in the run) or a
  failed harvest (after). The harvest takes exactly these ranges.
- The next item's window starts at its own ready record, written after the previous item's settle; a DNF's lines are bounded by its
  ready record and the post-settle cursor.

### 4.3 Equalities
Let `F` = the `Request failed` lines in the window, `C` = the completed lines, `S` = the started lines, `Δ` = worker deltas.
- Serial: every `Request started` line shows `in_flight=1`, and no start precedes the previous request's terminal line.
- Every line in `C` carries `session=` == the item's session (the row's `session_id`; for a DNF, which has no row, the abort manifest's
  session id [o4]) and `backend=cached_session`; `C` pairs positionally with `request_usage` (§4.1), equal in count — except in the
  `completed_unaccounted` rows below, where `C[:-1]` pairs with `request_usage` and the last line is the unaccounted one [o4];
  `Δrequests_completed == |C|`; `Δrequests_started == |S| == |C| + |F|`; `Δrequests_failed == |F|`; `Δprompt_tokens_total` /
  `Δgenerated_tokens_total` == the sums over `C` (the client's sums follow from the per-request pairing and are not compared again [o4]).
- Allowed `F`, all other cases systemic:

| Item outcome (structured evidence) | `|F|` | Condition |
|---|---|---|
| completed normally | 0 | — |
| probe kill or `client_inactivity` (scored strict fail), at a request boundary | 0 | `gate.requests_completed_at_kill == |C|` (null for `client_inactivity` → `gate.requests_completed == |C|`) |
| the same, with a request in flight | 1 | the last line of the window, `error=stream_closed_before_completion`, `|S| == |C| + 1` |
| the same, a request in flight that the server completed before the client lost it [o4] | 0 | exactly one trailing `C` line absent from `request_usage`, its session == the row's, recorded `completed_unaccounted` |
| DNF (any DNF cause), the abort at a request boundary | 0 | `|C| == len(request_usage)` from the abort manifest [r3] |
| DNF, a request in flight that the server failed | 1 | the trailing `stream_closed_before_completion` line as above |
| DNF, a request in flight that the server completed before the client lost it | 0 | exactly one trailing `C` line absent from `request_usage` (the abort manifest's in-flight message), its session == the abort manifest's `session_id` [d2], recorded as `completed_unaccounted` [r3] |

The DNF rows are decided by observed started / completed / failed state, not by the cause name (`connection` also covers
established-stream resets) [r3].

- Per load, before the first item: the A4 window's 3 `anon:*` requests equal the A4 run's `gate.json` and its own 4-request `ses_*`
  session equals the A4 receipt (`a4_v2` receipt) [o4].
- A line in the window not attributable by these rules, or unparseable → systemic.

### 4.4 Engagement
- ON: every completed request with `generated_tokens ≥ 2` carries integer `draft_rounds ≥ 1`, integer `draft_n ≥ 1`, integer
  `0 ≤ draft_n_accepted ≤ draft_n`, `draft_kind=mtp`. Basis (code-read, fork `0f30522c`): the first token comes from prefill
  (`speculative/mtp.py` `emitted = 1  # caller already yielded the first bonus`); `speculative_stats_since` returns null when no round ran
  (`speculative/common.py`). Unchanged at S′ `c688e722` (`mtp.py:716`, `common.py:399–401`) [o4]. Requests with `generated_tokens ≤ 1`
  are counted and listed, not judged. The pilot is the known positive; R1 records every ON request's `(generated_tokens, draft_rounds)`,
  and a request there with `generated_tokens ≥ 2` and no round stops v8 for the operator [o4].
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
Input: an occurrences file — records `(session, language, item, seed, arm_of_dnf, occurrence)`, duplicates across sessions allowed — the ordered union of every DNF occurrence of the VALID-with-DNF legs of both arms and both sessions (an INVALID leg is rerun, not made
up) [o4]; BOTH make-up legs run the whole union (C220: "for BOTH arms", so
every rerun item has a pair). One fresh-load leg per arm (OFF then ON); inside a leg, one invocation per (session, seed, language) group
[r3] in s1-then-s2 and original language order, items in their original order; own out-root namespace `makeup`; excluded from the
per-session pairs; a repeat DNF is a finding. Same checkpoints and classes; a make-up leg that stops early records its unrun occurrences
`not_run`, and the sensitivity line names them [o4].

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
   keys only; credential keys (§11.3's classifier) recorded as keys only, per process — never their values or any hash of them (C238) [d2]; per distinct interpreter the router, worker and probe use (resolved from their pids) [r3]: its path
   and a verified content inventory — for every non-editable distribution, name, version and its `RECORD` entries each re-verified
   against the installed bytes (a mismatch is systemic), hashed as sorted `(path, digest)`; editable distributions (`mlx-vlm`,
   `mlx-serve`) are identified by their resolved source tree (`<WT>/src/<sub>`, at the gitlink, `status --porcelain` empty), their
   editable metadata excluded [r3]; the native libraries the worker actually loaded (`vmmap <worker>`; `lsof` lists descriptors, not loaded images [o4]: the loaded paths of
   `libmlx.dylib`, `mlx.metallib`) and the sha256 of each loaded file [r3]; the probe entry's resolved path; the target / drafter
   snapshot revisions and file hashes (§3) [r3].
5. **Pair gate:** for the second leg of each pair (pilots, s1, s2, reload, make-up) the sequencer passes the first leg's receipt path; the
   chain compares at its after-load checkpoint, before item one [r3] — allowed differences: the three §6.3 argv items, the drafter
   snapshot (ON only), the arm commit, the canonicalized roots, and the keys of §6.4's closed volatile list; nothing else — the allowed list is closed here and R1 only
   confirms that its observed difference is a subset of it (a difference R1 reveals outside it is a finding for the operator, never an
   automatic allowance) [d2]; any other difference (including a credential key present in one process of one leg only) → systemic. The
   sequencer re-checks after the leg and writes an immutable pair dossier per pair attempt, `pairs/<pair>__off-a<n>__on-a<m>.json`, keyed by arm (§16.1) [d2], published by
   `p426_harvest.publish_dossier` to `benchmark/results/p426/wave2/pairs/` (§11.2) [d2]; `sequence.json` names each pair's selected dossier. A sequencer restart between the two legs of a pair resumes the pair: the second leg compares with the first leg's persisted receipt
   (C238).
6. **Arms:** OFF = the v8 commit; ON = it + exactly the P426 plan's §11 restore (the three C177 lines, the `PROVISIONAL P426` note, the seeding test) [o4] on local branch
   `p426-on`. Commit diff = the three registry lines, the
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
  and the worker's own `D` for them, listed; §16.3) [o4]. Same definition in both arms; the barrier's between-item waits are outside every request.
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
- Every regular file under the attempt's leg root, under each run and evidence directory the attempt's own manifests name (the probe
  writes its run directory and transcripts under `$STACK_WORKDIR`; each named directory must carry a run id of this attempt) [o4], and
  the leg's server-log byte range, is inventoried; each gets a destination or a recorded
  exclusion reason from a closed rule table; an unmatched file fails the harvest. References are resolved transitively (rows, manifests,
  sidecars, DNF records, ready / item records, A4 receipts, grader reports, final-tree manifests and every object they reference, web
  evidence, the watcher receipt); a referenced file missing fails the harvest. Barrier and control files (`.ready`, `.go`, `.done`,
  `.continue`, `.stop`, ack / cancel files, `STOP`) are harvested; their presence is checked against the leg state (e.g. a `.stop` for every
  `invalidate`).
- Symlinks [r3] [o4]: every file is examined with `lstat`; a symlink or non-regular file is never followed or copied. Inside a model's
  final tree it is recorded in the final-tree manifest (path, link target string) and excluded with reason `symlink`; anywhere else, or
  when a required artifact references it, the harvest fails for the operator. Every source path must resolve inside the roots above or
  the leg's log ranges.
- Staged publication [o4] [d2]: the attempt's files are copied to a staging directory beside each destination, verified, and published
  evidence first, then `main`; the `main` destination carries `HARVEST.json`, and its rename into place is the single commit point. A retry
  verifies the attempt's `main` destination: with a verifying `HARVEST.json` it is done (idempotent); otherwise it deletes that attempt's
  incomplete destinations and stages (never another attempt's) and restarts. The pair dossier (`publish_dossier`) and the run records
  (`publish_run_files`: the frozen-record directory, the sequencer's `sequence.json`, to `wave2/run/`) are published the same way [d2].
- Structured records are portable at creation [d2]: every path in a record destined for `main` is written as `$STACK_WORKDIR/…`,
  `<WT>/…` or `<OUT>/…`, never absolute, so the scrub is byte-identity on them; a scrub change to a `main` record fails the harvest.
- `main` (`benchmark/results/p426/wave2/<leg>.a<n>/`) [o4]: parsed and structured artifacts only — the leg record, `chain.json`, `schedule.json`,
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
None automatic. `main` and `evidence` pushes each need the operator's in-turn approval, and go per pair, after its dossier [o4].

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
  harness is entry-agnostic: only the §6.3 argv delta and the P426 plan's §11 restore are per entry).
- Assumptions: opencode 2.0.20 `request_usage` and `session=` attribution as in the P456 rehearsal (17 / 17); the serial cached-session path
  (checked per request, §4.3); the barrier mechanism works on real hardware as on the fake probe (shown by the rehearsal before v8).
- Residuals: third-party text in transcripts the secret gate cannot classify (on `evidence` only, listed emails reviewed before its push);
  the Go deadline input is historical, not piloted (an overrun only pauses).

## 16. Interfaces — the testable seams [o4]

Named so the tests can be written blind (the first test delivery found G1–G15 unnamed). A name already built in s1–s3 is kept. All
records are JSON. Three classes [d2]: **immutable records** — exclusive-created and self-hashed (`sha256` = sha256 of the canonical JSON,
`sort_keys`, separators `,` `:`, UTF-8, of the record without its `sha256` field): the rehearsal manifest, v8 base, timeout amendment,
ready, item and `p426_dnf` records, the receipt, the pair dossier, the leg record, `HARVEST.json`; **two-phase records** — exclusive-created,
then finalized once by atomic replace and immutable after: `log_bounds.json`; **state files and journals** — `sequence.json`
(atomic replace, `sha256` of each version recorded in the next), `watch.jsonl` (append-only, one JSON line per event). Every refusal prints one stderr line `REFUSED: <reason>` naming the offending
flag, file or field, and exits 2.

### 16.1 Records
- **`--frozen-record <path>`** (s1): read once at entry; its `kind` must fit the mode — `--rehearsal` → `p426_rehearsal`; `pilot` →
  `p426_v8_base`; `chain` / `makeup` → `p426_timeout_amendment`, whose `v8_base_sha256` must equal the `sha256` (self-hash) field of `v8_base.json` in the same directory; a bad self-hash, a wrong kind or a missing file refuses.
- **Rehearsal manifest** `{kind: "p426_rehearsal", off_commit, on_commit, off_worktree, on_worktree, out_root, rehearsal: true, created,
  sha256}`.
- **v8 base** `v8_base.json` `{kind: "p426_v8_base", build, off_commit, on_commit, off_worktree, on_worktree, gitlinks: {mlx_vlm,
  mlx_serve}, production_ref, probe_code_sha256, scaffold_policy_sha256, generation_identity_sha256, pins_sha256, grader_image_id,
  frozen_prompt_date, pilot_deadline_s, settle_bound_s, generic_pred_s, volatile_env_keys (= §6.4's closed list), r1_env_difference (R1's observed pair difference,
  a subset of §6.5's allowed list) [d2],
  rehearsal_manifest_sha256, stack_suite_receipt_sha256, created, sha256}`.
- **Timeout amendment** `{kind: "p426_timeout_amendment", v8_base_sha256, w_python_s, w_go_s, leg_deadline_s: {"<session>": s},
  settle_bound_s, created, sha256}`.
- **Leg record** `<out-root>/leg.json` `{leg, attempt, state: VALID|VALID_WITH_DNF|INVALID|NOT_STARTED|OVERRUN, class, reason,
  chain_rc, started, ended}` (written by the sequencer).
- **Slot file names**: `chain_rows.slot_file(slot)` = the slot with `|` → `__` and `/` → `--`.
- **Ready record** `items/<slot_file>.ready.json` `{slot, item, k, log_cursor: {path, device, inode, offset}, worker_snapshot: <the
  /metrics summary dict>, owned: {router: {pid, start}, worker: {pid, create_time}}, at}`.
- **Item record** `items/<slot_file>.json` (DNF: `.dnf.json`) `{slot, ready_sha256, log_range: {start, end, sha256}, worker_before,
  worker_after, case, requests: [{session, backend, prompt_tokens, generated_tokens, decode_tok_s, draft_rounds, draft_n,
  draft_n_accepted, draft_kind, error}], totals: {requests, prompt_tokens, generated_tokens, decode_s, accepted, proposed}, checks:
  {<name>: {ok, detail}}, verdict: "reconciled"|"invalid"}`; `case` ∈ {`completed`, `kill_boundary`, `kill_inflight_failed`,
  `kill_completed_unaccounted`, `dnf_boundary`, `dnf_inflight_failed`, `dnf_completed_unaccounted`}.
- **`p426_dnf` record** (`pick` = the leg's one model; `load_gen` = the load generation of the aborted invocation; `invocation` = its
  index in `chain.json` `progress.invocations`; `attempt` = the `n` of the out-root's name `<leg>.a<n>`, which the chain requires in
  P426 mode [d2]) (the chain's record of a DNF, as built in s3; its `item_record` names the DNF's item record
  `items/<slot_file>.dnf.json`, which holds the §4 reconciliation of the DNF window — two linked records; sidecar `<out-root>/<session>/p426_dnf/<slot_file>.json`) `{slot, item, session, language, seed,
  arm, pick, load, load_gen, invocation, attempt, abort: {cause, error, evidence}, owned_at_incident, owned_after, settle: {in_flight,
  settled}, item_record, at}`.
- **Abort manifest** (s2, as built): `transport_abort = {cause, error, evidence, termination, gate: {…, request_usage}, session_id,
  in_flight: {in_flight, message_id (null at a boundary), requests_started}}`.
- **`log_bounds.json`** `{files: [{path, device, inode, offset_start, offset_end (null until finalized)}], created, finalized}`.
- **Arm-equality receipt** `<out-root>/receipt.json` `{argv: {router, worker}, env: {router, worker, probe}: {key: value | "<volatile>"},
  credential_keys: {router: [key], worker: [key], probe: [key]} [d2], interpreters: [{path, inventory_sha256, editables: {name: {tree, gitlink, clean}}}], loaded_images:
  [{path, sha256}], probe_entry, snapshots: {target, drafter}, sha256}`.
- **Pair dossier** `{pair, arms: {off: {attempt, receipt_sha256, harvest_sha256}, on: {…}}, differences: [..], verdict, at, sha256}`
  [d2].
- **`HARVEST.json`** `{leg, attempt, state, files: [{source, sha256, destination: "main"|"evidence"|"excluded", published,
  published_sha256, compression, exclusion_reason}], created, sha256}`.
- **Watcher receipt** `<out-root>/watch.jsonl` (one line per tick, then one `exit_state` line).

### 16.2 Modules
- **`bench.p426_reconcile`** (s4): `parse_log(data: bytes) -> list[LogLine]` (`LogLine.kind` ∈ started / completed / failed, `.fields`
  dict, `.offset`); `reconcile_item(row, lines, before, after) -> ItemReport` and `reconcile_dnf(abort_manifest, lines, before, after) ->
  ItemReport` (`.ok`, `.case`, `.problems`, `.requests`, `.totals`); `engagement_problems(requests, arm) -> list[str]`;
  `settle(read_metrics, read_log, cursor, *, bound_s, clock, sleep) -> SettleResult(settled, in_flight, waited_s)`;
  `decode_time(snapshot) -> float` (§4.1); `decode_rate(requests, delta_d) -> float | None` (§8); `a4_window_problems(lines, a4_receipt, a4_gate) -> list[str]` (`a4_gate`: the A4 run's `gate.json`) [o4].
- **`bench.p426_hooks.P426Hooks(ChainHooks)`** (s4): `__init__(*, ops, out_root, arm, settle_bound_s, clock=time.time,
  sleep=time.sleep)`; `before_attempt(slot, context=None)` writes the ready record, returns `accept`; `after_attempt(slot, done, context=None)` [d2]
  settles, reconciles, writes the item record, returns `accept` or `invalidate(reason)`. The chain installs it in P426 mode.
- **`bench.p426_receipt`** (s5): `arm_receipt(ops, *, worktree, out_root, pids) -> dict`; `pair_problems(first, second, *,
  allowed, volatile) -> list[str]`; `write_dossier(path, *, pair, attempts, receipts, harvests, verdict) -> dict`.
- **`bench.p426_secrets`** (s5, used by s9): `credential_values(*, home, config_path, environ) -> dict[str, str]` (in memory only);
  `is_credential_key(name) -> bool`; `scan(text) -> list[Finding(kind, start, end)]` (never carries the matched value);
  `exact_hits(text, values) -> list[Finding]`.
- **`bench.p426_freeze`** (s8): CLI `rehearsal --off-worktree --on-worktree --out-root --out`; `v8 --off-worktree --on-worktree
  --rehearsal-manifest --r1 --r2 --r3 --out`; `amend --v8 --pilot-off --pilot-on --out`; `main(argv, *, ops=None, checks=None)` with
  `checks` the injectable precondition runner.
- **`bench.p426_wave2`** (s8): `leg_argv(leg, attempt, *, worktrees, record_path, out_base) -> list[str]`; `deadline_s(session, langs,
  amendment) -> float` (§10.2); `makeup_groups(occurrences) -> list[dict]` (§5.5); `main(argv, *, ops=None, clock=None, sleep=None)`.
- **`bench.p426_harvest wave2 --leg-root <dir> --main-root <checkout> --evidence-stage <dir>`** (s9), with `p426_harvest.Scrub` (P437)
  for the scrub; `harvest_wave2(leg_root, *, main_root, evidence_stage, scrub, secrets) -> dict` (the `HARVEST.json`).
- **`bench_watch.main(argv, *, power=None, clock=None)`** (s6): `power()` returns `{watts, volts, battery, on_battery_intervals}`.
- **`OpencodeArm(mode="tg1", p426=True)`** (s2, as built).
- **ChainOps seams** (s4 / s5; `FakeOps` implements them, with those of §16.4–§16.6 — the union [d2]): `proc_argv(pid) -> list[str]`,
  `server_log_path() -> Path`, `read_log(path, start, end=None) -> bytes`,
  `worker_metrics()` (existing), `proc_environ(pid) -> dict`, `interpreter_inventory(pid) -> dict`, `loaded_images(pid) -> list[dict]`,
  `snapshot_hashes(model) -> dict`.

### 16.3 Clarifications
- In P426 mode the chain passes `--evidence p426` to the probe.
- `--rehearsal` selects the smoke shape: one pilot item, then two full items, of s1's P426 Python order (§7); `--smoke` stays refused.
- The P426 pilot is the first five of s1's P426 Python order (`Random(seed).sample(sorted(pool), n)`, §7), not the legacy pilot's
  `sorted(Random(seed).sample(pool, 5))`.
- `ΔD` per item = `decode_time(after) − decode_time(before)`, the worker's aggregate decode time over all the item's requests, 1-token
  ones included as the worker counts them; §8's numerator excludes their single token [d2].
- §14.5 "no change to production serving code" is B2's own diff; B2's base moves to S′ with T3 (C236).
- `test_b2_frozen_s0_*` validates fixtures on the baseline; it is a record, not part of the committed suite.

### 16.4 Seams named after the second test delivery [o4]
- **Chain entry re-verification (§3)** through ChainOps: `worktree_state() -> {head, clean, gitlinks: {path: sha}}`,
  `last_leg_end() -> float | None` (epoch seconds from `LAST_LEG_END`), the existing `power_state()`, the probe identity through
  `--print-identity` of the configured `--probe` (the fake probe answers it), the locks under the configured `$STACK_WORKDIR`
  (`tmp_path` in tests). A hermetic positive `--p426` leg is FakeOps (these seams + §16.2's) + the fake probe + records written with the
  §16.1 recipe.
- **Hook context** (as built in s3): `{stage: "ready"|"done", slot, item, k, ready: <the ready record>, row: <the full row at done, else
  None>, load: {idx, load_gen, worker, session, model, arm}}`.
- **`p426_receipt.arm_receipt(ops, *, worktree, out_root, pids: {router, worker, probe})`**; argv and environment via
  `ops.proc_argv(pid) -> list[str]` and `ops.proc_environ(pid)` (C238: no key, no `--hmac-fd`).
- **Arm spellings**: `engagement_problems(requests, arm)` and every P426 API take `arm` ∈ {`off`, `on`}.
- **`p426_reconcile` inputs**: `before` / `after` / `decode_time(snapshot)` take the `/metrics` summary dict (as the ready record stores
  it); `settle`'s `read_log(start, end=None) -> bytes` and `read_metrics() -> dict`; its `cursor` is the ready record's `log_cursor`;
  `parse_log` returns no entry for a trailing partial line (no newline) and raises `ValueError` on an unparseable complete line; `fields`
  values are strings as logged.
- **s8 shapes**: `leg_argv(..., worktrees={"off": path, "on": path}, ...)`; `deadline_s(session, langs={lang: n}, amendment)`;
  `makeup_groups(...)` items `{session, seed, language, items}`; `p426_freeze.main(argv, *, ops=None, checks=None)` where `checks(kind,
  **inputs) -> list[str]` returns the failed preconditions and `ops` provides `worktree_state(path)`; the rehearsal manifest's two
  commits differ by exactly the restore diff, as v8's do. `p426_wave2.main(argv, *, ops=None, clock=None, sleep=None)` where `ops`
  provides `launch(argv, *, cwd, pass_fds) -> handle`, `wait(handle) -> rc`, `alive(pid, start) -> bool`, `power() -> dict`,
  `harvest(leg_root) -> rc`.
- **`bench_watch --chain-json <path> --driver-pid <pid> --out <out-root>/watch.jsonl`**.
- **Harvest**: a `HARVEST.json` entry is keyed by a typed `source` [d2]: `leg:<path relative to the leg root>`, `run:<run-id>/<rel>`,
  `evidence:<run-id>/<rel>`, `record:<rel>` (sequencer-level run files) or `log:<file>:<start>-<end>`;
  the scrub is `p426_harvest.Scrub` as Wave 1 constructs it (no manifest file); `credential_values(*, home, config_path, environ,
  env_files=())` (the sequencer passes `<WT>/.env` when present); foreign emails go to `HARVEST.json` `review.emails`.

### 16.5 Seams named after the third test delivery [o4]
- **Sequencer CLI** `python -m bench.p426_wave2`:
  - `run --record-dir <dir> --worktree-off <WT> --worktree-on <WT> --out-base <dir> [--through <leg>]`: legs 1–8 in order from the records
    in `<dir>` (`v8_base.json`, then `amendment.json`);
  - `makeup --record-dir … --worktree-off … --worktree-on … --out-base … --occurrences <file>`;
  - `rehearsal --manifest <path> --worktree-off … --worktree-on … --out-base …`: R1 (a pair), R2, R3;
  - `--pause-file <path>` (default `<out-base>/PAUSE`).
  Resume = the same command; the sequencer reads its own `<out-base>/sequence.json` (`{legs: [{leg, attempt, state}], pairs: [..]}`).
- **Pair receipt flag**: the second chain of a pair gets `--pair-receipt <first leg's receipt.json>`; the chain compares at its after-load
  checkpoint (§6.5) through `p426_receipt.pair_problems`.
- **After-load busy census**: `ChainOps.busy_procs()` lists processes; the chain exempts the owned router / worker by `(pid, start)` and
  its own descendants by `ChainOps.descendants(pid) -> set[int]`.
- **Ledger key**: `chain.json` `p426_ledger` = `[{slot, kind: "row"|"dnf", invocation, index}]` (as built in s3); `p426_dnf` and
  `p426_invalid` likewise.
- **Pins and expected worker argv**: the chain reads the fork's pins from `<WT>/src/mlx-vlm/dev/p369_phase2/pins.json` and the expected
  worker argv from `ChainOps.expected_worker_argv(registry_path, model) -> list[str]` (mlx-serve's own builder).
- **ON argv comparison (§6.3)**: ON's argv is OFF's with the three flag pairs inserted where mlx-serve builds them; compared as OFF's
  tokens in order plus exactly the three pairs, position-free.
- **Operator email**: `p426_harvest.Scrub(..., emails=(…))`; the sequencer passes the main checkout's `git config user.email`.
- **`RECORD` re-verification**: through `ChainOps.interpreter_inventory`; its mutated-file refusal is tested on a fixture
  `site-packages` tree (`interpreter_inventory(pid, site_packages=<path>)` for tests); the live check runs in R1.
- **Rehearsal ON commit**: R1's ON commit differs from its OFF commit by exactly the P426 plan's §11 restore, as v8's do.

### 16.6 Sequencer details named after the fourth test delivery [o4]
- `ops.launch(...)` returns a handle with `pid`, `start` (process start time as `ChainOps` reports it) and `argv`; liveness is
  `ops.alive(handle.pid, handle.start)`; `ops.harvest(leg_root, *, emails) -> {rc, harvest_json, harvest_sha256}` [d2]; `ops.publish_dossier(path, *, emails)` and
  `ops.publish_run_files(paths, *, emails)` likewise.
- The sequencer classifies a leg from the chain's rc, its `chain.json` (`status`, `p426_ledger`, `p426_dnf`, `p426_invalid`), the item
  records' draft counters, and `watch.jsonl`'s `exit_state`; pilot walls come from the rows (`wall_s`) of the invocations
  `chain.json` `progress.invocations` names.
- `OVERRUN_PAUSED` is `<out-base>/OVERRUN_PAUSED` (`{leg, attempt, deadline_s, at}`); the leg record carries `speed_valid` and
  `speed_reason`; the occurrences file is JSON lines of the §5.5 records, an unordered set the sequencer canonicalizes (§5.5 order) [d2]; pair dossiers
  are `<out-base>/pairs/<pair>__off-a<n>__on-a<m>.json` before their publication.
- `harvest_wave2` refuses by raising `p426_harvest.HarvestError` (the CLI prints `REFUSED: …`, rc 2) and publishes nothing.
- The census's owned-worker identity is `(pid, ChainOps.create_time(pid))`; fakes answer the owned worker's own start time.

### 16.7 Names pinned after delivery 1f [d2]
- **R1 subset check**: `p426_freeze v8 … --r1-off <leg root> --r1-on <leg root>` (R1 is a pair); the dossier's `differences` is a list of
  `{process: router|worker|probe|-, field, off, on}` (canonicalized; a credential entry names the key only, no value); v8 records it as
  `r1_env_difference` and refuses when an entry lies outside §6.5's closed list.
- `p426_receipt.pair_problems(first, second) -> list[str]` (the closed and volatile lists are module constants, not parameters);
  `write_dossier(path, *, pair, off: {attempt, receipt, harvest}, on: {attempt, receipt, harvest}, differences, verdict) -> dict`.
- `<pair>` ∈ {`r1`, `pilot`, `s1`, `s2`, `reload`, `makeup`}; `arms.<arm>.attempt` is the attempt name `<leg>.a<n>`.
- `sequence.json` carries `previous_sha256` (the sha256 of the version it replaces; null for the first).
- The sequencer writes the canonical occurrences per arm to `<out-base>/makeup/occurrences.<arm>.jsonl` and passes that file as each
  make-up chain's `--occurrences`.
- `p426_harvest.publish_dossier(path, *, main_root, evidence_stage, scrub) -> dict` and `publish_run_files(paths, *, main_root, scrub)
  -> dict` (`paths` are files; the sequencer expands the frozen-record directory to its files); the `ops` methods wrap them.
- `P426Hooks` called with `context=None` raises `HookInfrastructureError` (in P426 mode the chain always passes it).
- Credential keys are absent from the receipt's `env` maps; they appear only in `credential_keys`.
- (after delivery 1g) Every record path field (`off_worktree`, `on_worktree`, `out_root`, …) is written in the portable form
  (`$STACK_WORKDIR/…`); readers expand it before comparing. `p426_freeze` takes the v8 inputs it cannot derive from the worktrees
  (build label, production ref, grader image id) from `ops.build_inputs() -> dict`. `write_dossier`'s `receipt` / `harvest` are paths;
  `receipt_sha256` / `harvest_sha256` are the files' sha256. A `differences` entry's `field` is the dotted receipt path (`argv.worker`,
  `env.<KEY>`, `snapshots.drafter`, …). `publish_dossier` / `publish_run_files` return `{published: [{source, destination, sha256}],
  harvest_sha256}`.
- (after the s4 / s5 reviews) `log_bounds.json` is a `main` record: its paths are portable (`<WT>/logs/…`). The receipt's probe
  environment is the chain's probe launch environment — the exact base environment it passes to every probe invocation of the leg —
  with the per-invocation keys (receipt path, nonce, cancel / ack files) recorded by name only; there is no probe process at the
  after-load checkpoint. In P426 mode a ChainOps seam the checks need that is missing is systemic (never a skip); identities use
  `ChainOps.create_time(pid)`. The worker argv equals the expected argv exactly (no tolerated leading tokens).

### 16.8 Names pinned after delivery 3c (the s8 review) [d3]
- **Sequencer ops** (in addition to §16.6): `ops.operator_emails() -> list[str]` (the main checkout's `git config user.email`, read by
  the box ops only; tests fake it); `ops.worktree_state(path)` (as §16.4); `ops.identity(path) -> dict` (the worktree's
  `--print-identity`); `ops.harvest_path(attempt) -> Path` (`<main-root>/benchmark/results/p426/wave2/<attempt>/`). **Freeze ops**:
  `ops.identity(path)`, `ops.historical_walls() -> {w_python_s, w_go_s, max_request_elapsed_s}` (the M63 / P456 / P499 rows; the box ops
  read the operator's `--historical-walls` JSON), `ops.build_inputs()` (§16.7). Every other precondition, the restore diff included, goes
  through `checks(kind, **inputs)`; a missing seam is a refusal (`REFUSED:`, rc 2), never a traceback.
- **Settle bound (§4.2), derived, never typed**: v8 `settle_bound_s = max(900, 2 × max(R1's largest single-request elapsed,
  historical_walls.max_request_elapsed_s))`; the amendment `= max(v8's, 2 × the largest single-request elapsed over both pilots)`.
  Elapsed = the item records' request `elapsed_s`.
- **Production tree (§10.1)**: v8 checks both the `p426_plan.EXPECTED_BUILDS` gitlinks / production ref AND that the fork tree at the
  gitlink equals the production ref's tree under `mlx_vlm/` excluding `mlx_vlm/tests/` (`git diff --quiet <ref> <gitlink> -- mlx_vlm
  ':!mlx_vlm/tests'` in the worktree's `src/mlx-vlm`).
- **Planned slots**: the sequencer reads each leg's plan from its `chain.json` frozen schedule, never a constant.
- **Exit codes** of `p426_wave2`: 0 done, 1 stopped (leg / gate / pair / drift), 2 refused, 3 overrun pause, 4 harvest failure; none of
  1 / 3 / 4 loses or deletes a leg.
- **OVERRUN**: a leg that runs past `T` and then ends by itself is classified normally (§5.1) and its leg record carries `overrun: true`;
  the state `OVERRUN` is a leg that did not end by itself (the operator stopped it during `OVERRUN_PAUSED`) — never paired.
- **Occurrences (§5.5)**: `occurrence` = the 0-based position of the item in its (session, language) order in that leg's frozen schedule
  (`chain.json`); canonical order = s1 then s2, languages in the session's original order, then `occurrence`; records are de-duplicated
  per (session, language, item, seed) with `arm_of_dnf` merged into a sorted list (a slot DNF'd in both arms runs once per make-up leg).
- **Make-up out-roots** are flat like every attempt (§1): `<out-base>/tg1-p426-{off,on}-makeup.a<n>`; only the occurrences files live
  under `<out-base>/makeup/` (§16.7).
- **Injections (rehearsal only)**: `--inject reconcile-mismatch` makes the chain perturb the first item's reconciliation so that it
  invalidates with the exact reason `reconciliation mismatch (injected)` (v8 matches it exactly); `--inject stall-kill` makes the chain
  pass `--inject-stall-item <lang>/<item> --inject-stall-s 30` to the probe invocation holding the first Python item of the rehearsal
  schedule, and the probe applies that stall limit to that item only. Both flags refuse without `--rehearsal`.
- **Rehearsal inputs**: `p426_wave2 rehearsal` requires `--frozen-prompt-date`; the rehearsal manifest records it and
  `ops.identity(off_worktree)`.
- **Topology test (§13)**: in-process — the real `Sequencer` whose `launch` runs the real `run_tg1_chain.main(argv, ops=FakeOps)` on a
  thread with the fake probe: real argv, locks, records, `chain.json`, `LAST_LEG_END` and watcher contract; no router, worker or model.
- (after delivery 3e) **`not_run` (§5.5)**: an occurrence with no scored ledger row — never launched, or invalidated at its barrier — is
  `not_run`; the sensitivity line names every such occurrence.
- (after the s9 delivery) **Portable `chain.json`**: the chain writes `argv` and `probe` (and every other path it records in `chain.json`)
  in the portable form (`$STACK_WORKDIR/…`, `<WT>/…`, `<OUT>/…`), so the §11.2 scrub-identity rule holds for real legs.
- **The sequencer's launch log** is `<out-base>/logs/<attempt>.stdout` (never inside the attempt's out-root, which the chain creates
  fresh); the harvest inventories it as part of the attempt and routes it to `evidence`.
- **Other email addresses (§11.3)** are written to a local review file `$STACK_WORKDIR/p426/review/<attempt>.emails.json`
  (`{address, sources}`; never published); `HARVEST.json` carries only `review.emails_count` and that file's portable path. Absent
  credential sources stay listed by label in `HARVEST.json` (no values).
