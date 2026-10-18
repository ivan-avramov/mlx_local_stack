# P371 — one shared arm-neutral item + chain core (PLAN v4, 2026-10-17)

Status: PLAN v4 → Cursor plan review round 4 (confirmation) → build. v4 applies round 3 (AGREE WITH CHANGES R24–R28 +
partials R10 R11 R13 R23; `docs/reviews/p371/plan-round3.cursor-gpt-5.6-sol-high.md`); v3 = `ec5d7166` applied round 2 (DISAGREE R18–R23 + partials R6 R9 R10 R11
R13, all accepted; `docs/reviews/p371/plan-round2.cursor-gpt-5.6-sol-high.md`); v2 = `7fadf532` applied round 1 (DISAGREE
R1–R17; `docs/reviews/p371/plan-round1.cursor-gpt-5.6-sol-high.md`); v1 = `6243acdc`. Ruling: C178 (operator: "go for the expanded
p371"). Inputs: M64 step 4a Cursor round 1 NOT CLEARED A1–A14 (`benchmark/chains/m64/reviews/step4a-round1.cursor-gpt-5.6-sol-high.md`
on `m64-build` `406cc10e`); P370 lead calls; M64 spec §4–§9, §12; tg2 spec v5 (T14); P311 spec v4.
Branch / worktree: `m64-build` in `$STACK_WORKDIR/worktrees/m64` (main merged: `5fb51c1a`). No GPU work.

## 1. Problem

Two item loops and two chain runners do the same job:

| layer | tg1 | M64 | tg2 (step 3, not built) |
|---|---|---|---|
| item loop + probe main | `bench/tg1_runner.py` `run_item` / `_main` (~640 lines) | `bench/arm_runner.py` (757 lines, a copy driven through `ArmAdapter`) | would be a third copy |
| chain | `chains/c147/run_tg1_chain.py` `Chain` (1,025 lines) | `chains/m64/run_m64_chain.py` `ArmChain(base.Chain)` (881 lines, overrides most methods) | would be a third |

The copy existed to keep the tg1 generation identity unchanged. tg1 epoch `ae7fca94…` has no rows, so the identity can
move once now at no cost (C178). The M64 4a fixes (A1–A14) and P370 land in the one implementation.

## 2. Goal and non-goals

Goal: ONE item core and ONE chain core. tg1, tg2 and each M64 (arm × corpus) are CONFIGURATIONS bound immutably to a thin
probe entry and a thin chain entry. All A1–A14 + P370 fixes land in the core, plus the seams the next steps need (D2
health checks, P201 same-slot re-runs, fork receipts, tg2 multi-file items) so they do not force a second refactor (R13).

Non-goals (owned elsewhere): the `../mlx-vlm` receipt endpoint (P372; its protocol is fixed here, §4 A3), the D2 SearXNG
service + MCP server, Pi / dsh adapters, snapshot / adoption tooling, the arm-neutral P201 auditor, the judge panel (M64
§12 steps 4–6); the tg2 corpus implementation, its entries and legs (tg2 step 3, on this core); any behaviour change in
`structured_grade`, `tg2_grade`, the carriers, or the scoring path (`tg1_score`, `row_scores`).

## 3. Architecture

### 3.1 Modules

| module | role | status |
|---|---|---|
| `bench/run_config.py` | `GenerationPolicy`, `EvidencePolicy` (pure data, §3.2); only `GenerationPolicy` enters `scaffold_policy_sha256` (R11) | new |
| `bench/corpus.py` | `Corpus` contract + typed records (R12): `PreparedItem` (work dir, entry, editable paths, editable-tree baseline manifest, protected manifest, test paths), `GradeOutcome` (failing count, leaf set, `tampered`, `outcome` ∈ model / infrastructure, resource flags, phase records, report artifacts), `FinalTree` (content-addressed bytes of the graded editable tree + manifest). Methods: `load_universe`, `items`, `excluded`, `source_root`, `prepare(item, dest) -> PreparedItem`, `prompt(prepared, inject)`, `tampered(snap, prepared)`, `grade(snap, prepared, private, guard, keep, seq, boundary, final) -> GradeOutcome`, `changed(prepared) -> bool`, `final_tree(prepared, dest) -> FinalTree`, `languages`, `needs_docker(lang)`, `identity()` (corpus sha, grader version, timeouts, image) | new |
| `bench/corpus_tg1.py` | tg1 corpus: universe preflight, `go/counter` exclusion, polyglot root / sha / prepare + git init + mtime freeze + frozen-manifest check (moved out of the host), tg1 prompt + inject addenda, `structured_grade` grade / tamper → `GradeOutcome`, the M59/M61 "untouched solution fails" rule as `changed`, final tree | new (moved code) |
| `bench/worker_receipts.py` | spec §7 runner side: `AttemptContext` (attempt id, slot, correlation header), `ReceiptSource` contract (`start(ctx)`, `fence(ctx)`), receipt schema, the HTTP protocol client for the fork endpoint (§4 A3, pinned by a protocol fixture), one-to-one join to classified requests, per-class checks; `UnavailableReceiptSource`, `FakeReceiptSource` (tests) | new |
| `bench/item_barrier.py` | generation-neutral per-item file barrier in the probe (R23): before each item attempt the probe writes `<run>.item<k>.ready` and waits for `.go` or `.stop`; after it, writes `<run>.item<k>.done` (row key, evidence paths + sha256) and waits for `.continue` or `.stop`; timeouts / cancel as the manifest ack (`ACK_TIMEOUT_S`); off unless the runner policy enables it (no wait, no files) | new |
| `bench/chain_hooks.py` | chain-owned `ChainHooks` (R13, R23), OUTSIDE every probe closure: `before_attempt(slot)` (D2 health / canary later; infrastructure failure → transport class) and `after_attempt(slot, done) -> Disposition` ∈ `accept` / `rerun_same_slot(reason)` (P201 cheat later: the chain stops the probe after this item, then cache reset + warm-up + a new invocation for the slot with re-run index + 1, same seed, fresh receipt marks; the cheat attempt's row stays as an attempt record with its tokens) / `block(reason)` (P201 `unclear`: chain stops for the operator); default no-op `accept`; every disposition persisted in `chain.json.progress` before the barrier file is written, so crash-resume keeps cheat tokens and dispositions | new |
| `bench/arm_runner.py` | THE item core: `run_item` + probe `main` / `print_identity`; absorbs `tg1_runner`'s library parts (`GradeWorker`, `PhaseHeartbeat`, worker / router checks, `RunnerCancelled`, `_DiscoveryGuard`, `grade_reports`, `_link_mem_kills`) and the generic seed-row derivation (`rowschema.sample_seed` + `adapter.overlay_sha`) | rewritten |
| `bench/tg1_runner.py` | thin: tg1 constants (`SCAFFOLD`, carrier / plugin paths, `GENERATION_DATA`, `INJECT_*`), `TG1_POLICY`, delegation | thinned |
| `bench/arm_opencode.py` | opencode adapter, modes `tg1` / `m64`; owns every opencode specific (A11); search service injected by the entry (no `m64_search` import) | changed |
| `bench/arm_adapter.py` | contract additions: `seed_overlay`, `overlay_sha`, `preflight(selection=…)`, `build_env(…, attempt=AttemptContext)` (correlation header into the generated provider config, R3), `request_classes(stream, transcript)` (task / compaction / auxiliary from the FINALIZED transcript's pinned boundaries, R2), `web_evidence(…, dest)` (raw + hash), `tool_windows` from live start receipts, terminal shapes incl. `compaction_failed` | changed |
| `bench/chain_core.py` | THE chain core (runs `ChainHooks` at the item barrier): lifecycle closure freeze, per-arm policy derivation, frozen date, epoch + snapshots, contract artifacts, schedule freeze, loads / legs / attempts, barrier, supervision (idle predicate, escalation, STOP, watch log), validation + pinning, transport policy, persisted progress + resume, immutable A4 receipts | new (moved + merged code) |
| `bench/schedules.py` | pure, hashed builders: `tg1` (pilot / full / reload, today's LEGS order), `blocks` (M64: seeded order, blocks of 3, balanced arm permutations, reload control) over any language set, `tg2_tier` (consumes the frozen seed-6501 draw artifact's prefixes; never redraws, R14) | new (absorbs `m64_schedule.py`) |
| `bench/chain_rows.py` | THE chain-row loader (R7): leg-attempt file inventory, validated-sha check, DNF sidecar, slot-deduplicating `load_slots`; legacy read-only layout mode for stored chains (P223, M63, c144-base, M65 pilot) | new |
| `chains/c147/run_tg1_chain.py`, `chains/m64/run_m64_chain.py` | thin entries: CLI, out-root rules (P340, ON/OFF separation), `ChainConfig` | thinned |
| `run_tg1_probe.py`, `run_oc_probe.py` | thin probe entries binding (generation policy, evidence policy, adapter, corpus, host, hooks) | changed |
| `opencode_plugins/toolwindows.js` | M64 oc only: tool start / end receipts (§4 A4) | new |

**Closure rule (R11, R26):** everything a probe entry imports is in its `probe_code_sha256` by construction (P311): the
core, `worker_receipts`, `item_barrier`, the corpus and the adapter. So a code change there moves the generation identity
(accepted, C178); an `EvidencePolicy` VALUE change does not. To keep evidence code out of the probe closure where
possible, web-evidence extraction runs CHAIN-side (`bench/web_evidence.py`, imported by `chain_core` only) over the
hashed transcript the probe already stores; `chain_hooks` and `web_evidence` are never imported by a probe entry (closure
test). In-probe evidence steps are limited to what must happen before the scratch tree or the worker moves on: the
transcript, the receipt fence, tool-window receipts, the final-tree snapshot.

**Dependency rule:** `arm_runner`, `chain_core`, `schedules`, `chain_rows`, `corpus`, `worker_receipts`,
`run_config`, `item_barrier`, `arm_adapter` import NO corpus, adapter or client module; entries inject them. The P311 closure tests
assert per entry: the tg1 closure excludes `tg2_*`, `m64_search`, Pi / dsh modules and every scoring module; the
`m64-oc-tg1` closure excludes `tg2_*`; a future tg2 closure excludes `corpus_tg1`.

**Host seam:** only client-neutral process helpers remain on the host (`_scrub_pii`, `_portable`, `_sha_of`,
`_stack_workdir`, `_prompt_date`, scratch dirs, `_fresh_tmpdir`), as an explicit `Host` protocol checked at entry.
Corpus paths move into `Corpus`; seed derivation into the core (R12). `opencode_v2_core` keeps satisfying `Host`.

### 3.2 Configurations (R1, R11)

A configuration is bound to exactly one probe entry, one corpus and one label; there is no runtime corpus switch.

| config | probe entry | label | corpus / langs | built in |
|---|---|---|---|---|
| `tg1` | `run_tg1_probe.py` | `opencode-v2-web-tg1` | tg1 (python, go) | P371 |
| `m64-oc-tg1` | `run_oc_probe.py` | `opencode-v2-web-tg1c` | tg1 (python, go) | P371 |
| `tg2` | `run_tg2_probe.py` | `opencode-v2-web-tg2` | tg2 (rust, java, javascript, cpp) | tg2 step 3 |
| `m64-oc-tg2` | `run_oc_tg2_probe.py` | provisional `opencode-v2-web-tg2c` (fixed in the C175 D3 M64 amendment) | tg2 | after the tg2 smoke |

Three policy objects, each frozen where it belongs:

- **`GenerationPolicy`** (= the dict hashed into `scaffold_policy_sha256`, the generation identity; P311 §3–4, R22): a
  strict SUPERSET of today's tg1 policy recipe — `gate`, `hygiene`, `toolbounds_sha256`, `noretry_sha256`,
  `datefreeze_sha256`, `carrier_sha256`, `universe_sha256`, `grader_version`, `grader_timeout_s`,
  `grade_join_timeout_s`, `plugin_proof`, `env`, `scaffold`, `toolchain` (lock sha, interpreter, grader image id), `inject`
  — plus `config_id`, `corpus_id` + corpus identity, `langs`, `inject_allowed`, `budgets` (thinking 81,920 / max
  102,400 / context from the carrier; today hard-coded in `validate_worker`), `watchdog` (off | on + limit / grace +
  `toolwindows_sha256`), `compaction` (off | on_accounted), and for M64 the existing `arm` block. tg1: watchdog off,
  compaction off; m64-oc-tg1: watchdog on, compaction on_accounted. Test: every key of the pre-P371 recipe is present
  with its pre-P371 derivation, and a drift of each (incl. lock, interpreter, grader image) changes the sha.
- **`EvidencePolicy`** (manifest `runtime.evidence_policy`, verified by the chain; NOT in the generation identity):
  logical relative evidence namespace (`opencode_transcripts` | `transcripts/<arm>`), web evidence on (every config),
  final-tree retention, `worker_receipts` (absent | required), `item_barrier` (off | on). tg1: absent / off; m64-oc:
  required / on. Runner protocol, not generation: a change is verified by the chain, never a pairing break.
- **`ChainConfig`** (chain entry; serialized canonically into `chain.json` and the lifecycle closure, R15): arms →
  (probe entry, label, arm spec), schedule builder + params (+ draw artifact sha and tier for tg2, R14), out-root
  family, predictor, arm-switch ops (search restart / cache reset / warm-up: M64 yes, tg1 no), `transport_policy`
  (abort_restart | incident_retry), `resume_policy` (restart_load | new_segment), `snapshot_complete_required`, contract
  artifacts per arm (path + sha, R8). tg1: abort_restart / restart_load / no / none; M64: incident_retry / new_segment /
  yes (smoke: no) / required (smoke: allowed `OWED`).

### 3.3 Per-item evidence artifacts (R28)

Each kind has its own file, env field and adapter parameter; none shares a schema or a path:

| artifact | writer | env / parameter | configs |
|---|---|---|---|
| `<evidence>.events.jsonl`, `.stderr.txt`, `.json` (transcript) | client / adapter | spawn stdout / stderr; `adapter.transcript` | all |
| `<evidence>.datefreeze.jsonl` | `datefreeze.js` (P364) | `BENCH_DATEFREEZE_RECEIPTS`; `build_env(datefreeze_receipts=)` | all opencode |
| `<evidence>.toolwindows.jsonl` | `toolwindows.js` (A4) | `BENCH_TOOLWINDOW_RECEIPTS`; `build_env(toolwindow_receipts=)` | watchdog on |
| `<evidence>.receipts.json` | core, from the fence (A3) | none (runner-written); `ReceiptSource.fence` | worker receipts required |
| `<evidence>.final_tree/` + manifest | core via `corpus.final_tree` | none | all |
| `<evidence>.web.jsonl` | chain (`web_evidence`, A12) | none | all |

`adapter.evidence_suffixes()` declares the client-written kinds; the core reserves every path before spawn; the env
check refuses a spawn env whose receipt fields name anything but this item's paths.

### 3.4 Item core flow

`main`: argument checks against `GenerationPolicy` (langs, inject, frozen date required, sampling profile) → adapter
selection (an arm needing a missing service refuses here) → toolchain → declared model + M50 router assertion → worker
identity + arm identity + budget check → `corpus.load_universe` + item checks → binary → receipt source check (`required`
+ unavailable → refuse before any spawn) → `adapter.preflight(selection)` (A4 receipt for THIS selection, immutable path
from the chain) → run dir → discovery → identity (+ generation policy) → snapshot + `epoch_id` → resume checks → manifest
(+ evidence policy) → per item attempt:

1. `corpus.prepare` → `PreparedItem`;
2. `AttemptContext` (attempt id = slot + attempt n + re-run index; correlation header) created (R3);
3. `adapter.seed_overlay` + `build_env(…, attempt=ctx)` + `verify_env`; per-item discovery; `corpus.prompt`;
4. item barrier `ready` → wait for `go` (chain runs `before_attempt`), when enabled;
5. `receipts.start(ctx)` immediately before spawn (R3);
6. `run_item` (spawn … terminal drain, transcript);
7. `receipts.fence(ctx)` after client exit; `adapter.request_classes` from the finalized transcript; one-to-one join +
   per-class checks (A3, R2);
8. reconcile, final grade, `corpus.changed`, `corpus.final_tree`;
9. row written (every attempt is a row; the chain's disposition decides whether it is the scored one); item barrier
   `done` → wait for `continue` / `stop` (chain runs `after_attempt`), when enabled;
10. row = core fields + `adapter.row_fields` + `adapter.metrics` + seed fields + `config_id`, `arm`, `epoch_id`,
    `snapshot_sha256`, `final_tree`, `token_accounting`, `receipts` (path + sha256 when present) (+ `compaction` only when the generation policy
    has compaction on; tg1 rows never carry it, R10).

`run_item` keeps today's tg1 control flow (gate, guard, grade worker, heartbeat, ingestion, silence observer,
SIGTERM-first cancellation, terminal drain, transcript, reconcile, date-freeze receipts, tmp escapes, final grade), plus
watchdog ticks and compaction accounting when the generation policy enables them.

## 4. Fix absorption (each: test first, red, then the fix)

| id | fix in the core | red test(s) |
|---|---|---|
| A1 | `schedules.blocks` takes per-language item lists from the bound corpus (cell sizes from the data: 10 = 3 blocks + 1 residual); `schedules.tg2_tier` consumes the frozen draw artifact (sha + tier recorded in `schedule.json` and `ChainConfig`; membership + sha verified at every leg); screen = s1 only, 10 / language (C168 k = 1); decider = s1 + s2 + same-seed reload 5 / language; the `m64-oc-tg2` chain schedule = `blocks` over the screen prefix, s1, both picks (built with that config); docker gate from `corpus.needs_docker(lang)` | 4-language fake corpus through `blocks` + `tg2_tier`: hashes stable, permutations balanced per cell, nested prefixes, a changed draw sha refuses, realized order checked; a fake 4-language chain end to end |
| A2 / P370 | `compaction_failed`: registered terminal shape from a pinned real-client fixture → scored strict-fail row, `nonconv_kind: compaction_failed`, in `tg.PRECEDENCE` after the client cuts; the chain continues. Compaction requests classified from the finalized export's compaction boundaries (2.0.20 emits no live event, R2) BEFORE the receipt join; tokens from receipts when present, else post hoc from the export (P370 (1), `compaction.accounting: receipts|post_hoc`), always in the task totals | end to end through core + fake receipts: successful compaction (tool-less request passes), failed compaction → scored row + chain continues; tg1 config with a compaction message still aborts |
| A3 | runner side of spec §7 (fork endpoint: P372). Protocol pinned now by a fixture both sides test against: `POST /bench/attempt/start {attempt_id}` → `{worker:{pid,create_time}, seq}`; `POST /bench/attempt/fence {attempt_id}` → returns after every request admitted before it finalized: `{worker:{pid,create_time}, last_seq, receipts:[{seq, worker:{pid,create_time}, attempt_header, received_mono, finished_mono, sampling{temperature,top_p,top_k,min_p,presence_penalty}, seed, thinking_budget, max_tokens, roles, request_tools_present, request_tools_sha256, prompt_tokens, cache_tokens, completion_tokens, reasoning_tokens, disconnected, terminal}]}`. Attempt owns (start.seq, fence.last_seq]; the start, fence and EVERY receipt must name the attempt's worker (a replacement between marks → transport class `worker_crash`, R21); the raw fenced receipt set is written to `<evidence>.receipts.json`, sha256 in the row; receipt finalized after its fence → abort; join ONE-TO-ONE to the adapter's classified requests by order + timestamps + header; per-class checks (controls; allowed tools set per class); task tokens = owned receipts incl. disconnected generations; `token_accounting: receipts` / `client`. `required` + unavailable → refuse before any spawn | `FakeReceiptSource` + an HTTP fake serving the fixture: client cut with tokens after disconnect counted; auxiliary + compaction classes; missing, duplicate, late-after-fence, ambiguous join, tools mismatch per class, header mismatch → abort; a receipt naming another worker → `worker_crash`; the persisted receipt file's sha matches the row; legit tool-less compaction passes; protocol fixture round-trips; tg1 config unaffected. Fork step acceptance (pre-registered): the fork endpoint passes the same fixture tests against a live tiny-model worker |
| A4 | `toolwindows.js` (M64 oc): at `execute.before` / `execute.after` appends `{attempt_id, session_id, call_id, tool, phase, seq, ms}` to the per-item receipt file named by env (outside the config dir); a write failure THROWS (the tool call fails, never silently unwatched, R4); the adapter merges live start receipts (open windows) with completed `tool_use` events by call id; validated every watchdog tick: malformed record, sequence gap, wrong attempt / session, a `tool_use` whose call id has no start receipt → abort (transport class not; contract violation → chain abort); `exec_timeout` (any kill OR completed-window overrun) sets the gate flag; final tick after client exit before reconcile; hook firing proven on the real pinned client | unit: open window from a start receipt only; overrun → flag; final tick; corrupt / missing / out-of-order receipt → abort; plugin disabled (env check refuses) and plugin write failure (tool fails) tests; real-client contract: a hung `sleep` tool killed at the accelerated limit, row flagged |
| A5 | the chain computes `epoch_id` from every arm's snapshot (`--print-identity` emits `snapshot_sha256`, `snapshot_complete`, `snapshot_fields`); `--epoch-id` is an assertion; `chain.json` freezes `arm → snapshot_sha256`; verified at entry, resume, every barrier (manifest `runtime.snapshot_sha256`), exit (re-run `--print-identity`); `snapshot_complete_required` refuses an incomplete snapshot | changed snapshot between legs / at resume / at exit → rc 2; CLI epoch mismatch → refuse; tg1 runs with an incomplete snapshot |
| A6 | incident classification checks router (owner pid, config hash, port owner) and worker identity INDEPENDENTLY first (worker gone / changed → `worker_crash`; router gone / changed → `router_error`), then the adapter's cause; no cause → not transport | worker crash with an unrecognized client error → `worker_crash`; router death → `router_error`; both healthy + no cause → not an incident |
| A7 | retry requires the EXACT cleanup schema (R5): dict with exactly {survivors, containers_remaining, uncertain, orphans_unattributed, unknown, completed}; `completed is True`, `uncertain is False`, every list empty; anything else (missing, extra, malformed) → chain abort with listing; partial rows validated with `validate_leg` + config / arm / epoch / snapshot checks before the retry | `completed:false`, nonempty `unknown`, nonempty `orphans_unattributed`, extra key, missing receipt → each abort; partial row with a wrong `snapshot_sha256` → abort |
| A8 / A9 (R6, R18, R19) | one IMMUTABLE rows file per leg INVOCATION: `<stem>.L<leg>.<phase>.a<n>.jsonl` (+ manifest), `phase` ∈ `pilot` / `full` / `block` / `rerun` / `retry`; each invocation's item list and `--expect-items` are exactly its own slots (tg1 `full` = the cell's items minus the pilot's validated slots — never a re-run of pilot rows; probe-level resume within a file is removed). `chain.json.progress` (fsync before any next action): per load `{status ∈ pending|running|done|archived, workers:[{n, pid, create_time, a4_receipt_sha256}], cursor:{leg_index, phase}}`; per invocation `{leg_key, phase, attempt, worker_n, file, manifest, status ∈ running|validated|partial_incident|quarantined, expected_slots, accepted_slots, sha256}`; `partial_incident` = an incident attempt whose rows before the failing slot validated (accepted, counted, sha-checked). Every record carries `load_gen` (incremented by each `restart_load`); archiving marks the load generation's records `archived` (paths rewritten to the archive, shas kept) and they are excluded from the active inventory and from `scored_ids` (R24). A never-validated invocation file → `quarantine/` with a sha256 manifest before any retry or resume. **Hook stop (R25):** with the item barrier on, a `rerun_same_slot` or `block` disposition writes `.stop` at the slot's `done` barrier; the probe exits cleanly after that row with manifest `hook_stop: {after_slot, disposition}` and `--expect-items` satisfied by the prefix through `after_slot`; the record's status is `hook_stopped`, `accepted_slots` = that prefix; per slot attempt `{rerun_index, disposition ∈ accepted|cheat|unclear|exhausted}` is persisted BEFORE `.stop` is written; a `cheat` attempt's row is an attempt record (its tokens count to the task) and never in `scored_ids`; the rerun is a one-slot `rerun` invocation (same seed, `rerun_index` + 1, at most 2 re-runs, P202), then the leg's remaining slots continue in a new invocation; the scored attempt per slot = the latest non-cheat attempt; exhausted cheating scores that slot's latest attempt as a strict FAIL (P201). `scored_ids` = accepted slots of `validated` / `partial_incident` records (sha re-checked) + DNF rows; a cell is complete when its accepted slots == the schedule's slots; realized order appended once per leg key. `new_segment` resume: fresh worker, cursor's leg / phase, only unaccepted slots; `restart_load`: the load's files archived (sha manifest first), rerun from leg 0 (today's tg1). `chain_rows` is the only loader (inventory = progress records; an unregistered rows file → error) | pilot/full: interrupt in pilot, after pilot validated, inside full after ≥ 1 row; each resumed (and resumed again): no duplicate slot, no premature completion, full's expect set excludes pilot slots; M64: interrupt during the second leg after ≥ 1 row, resume twice: no refusal, no double count, realized == schedule, quarantine holds the partials; incident with a validated prefix → `partial_incident` accepted; tg1 `restart_load` after a validated pilot: the archived pilot is not scored and its moved file is not sha-rechecked, the rerun pilot is (R24); hook stop at slot 2 of 3 with `cheat` → rerun of slot 2 (index 1) then slot 3, scored = the rerun; crash between the persisted disposition and the rerun → resume reruns slot 2 once, cheat tokens kept; two further cheats → exhausted, strict FAIL; tampered validated file → abort; base + recovery + DNF fixture → each slot once; duplicate slot → error; drifted DNF copy → error |
| R7 | consumers enumerated in phase 1 (every module under `benchmark/` that reads chain out-root rows) and migrated to `chain_rows`; a repository test rejects direct chain-row reads outside `chain_rows` (pattern scan with an explicit allow-list for non-chain probes) | the scan finds no unregistered reader; a planted direct reader fails it |
| A10 | A4 run after EVERY worker (re)load per arm; receipt copied to `<out_root>/a4/<load>.<worker_n>.<arm>.json` (exclusive create), sha in `chain.json`; probes get the immutable path; the probe verifies the receipt's worker identity equals the current worker | two arms + a recovery reload → 3 distinct receipts, none overwritten; a pre-reload receipt → refused |
| A11 | opencode specifics behind the adapter / arm spec: carrier field names (`preflight(selection)`), `OPENCODE_CONFIG_CONTENT` → `adapter.overlay_sha(env)`, seed overlay → `adapter.seed_overlay`, A4 gate command → `ArmSpec.a4_command`, evidence namespace, label checks | a fake non-opencode adapter (other env var, no carrier fields) runs core + chain with zero opencode names (grep on its rows / manifests) |
| A12 | chain-side `web_evidence.extract(adapter_spec, transcript_path, transcript_sha256, dest)` runs after EVERY invocation for every attempt with a stored transcript (pass, fail, cut, incident, cancel, rerun, hook stop), writing raw tool calls + returned content as the model saw it (fetch body, search result, shell command + output) to `<evidence>.web.jsonl` (sha256 in `chain.json.progress` per slot attempt and in the incident / cancel record); the transcript sha is re-verified first; no transcript → `web_evidence: unavailable` + reason (P201: unauditable, never "no contact"); the per-arm extraction rules live in the arm spec (data), not the probe | success, gate kill, incident, cancel and hook-stop paths each leave a hashed file; export failure → `unavailable`; a transcript whose sha differs → abort; closure test: `web_evidence` absent from every probe closure |
| A13 | the contract suite runs REAL core runs (fake client; real pinned client against `opencode_v2_mock.py` with wire capture) and checks every request incl. compaction requests (controls + tools per class); `benchmark/m64/contract_artifact.py --arm oc` writes a hashed artifact, exits nonzero without the binary; checks needing unbuilt services are `OWED` with their build step; `ChainConfig` names each arm's artifact path + sha; frozen in `chain.json`, verified at entry, resume, barriers, exit (R8); non-smoke refuses `OWED` / failed / missing / drifted; smoke allows `OWED` only | artifact without binary → nonzero; the 17 injected defects (re-based on real runs) each red; compaction request with a wrong seed → red; chain refusal for `OWED`, failed, missing, hash drift (incl. mid-chain replacement); smoke exception |
| A14 (R9, R10, R20) | baseline = the pre-P371 tree executed IN ISOLATION. **Bundle:** `git archive 0c9bd32a` of every tracked path except `benchmark/results/` and `docs/`, extracted to a temp dir (root runtime inputs — `main_models.yaml`, carriers, plugins, `benchmark/m62/universe.json`, `scripts/` — included), sha256 manifest recorded. **Harness:** a driver copied into the bundle runs as a subprocess with `sys.path` = the bundle only (an import-hook asserts no module loads from the current tree) and uses the BUNDLE's own fakes — `bench/tests/test_tg1_integration.tg_fixture` (fake opencode binary, patched worker / router seams), `chains/c147/fake_probe.py`, the archived chain tests' fake `ChainOps` + `Timers`; one scenario file (JSON: client event script, grader outcomes, ops script, injected clock / UUID seed) drives both sides; the new side runs the same scenario with the current tree's equivalent fakes. Normalizer: injected clock, UUIDs, temp paths. **Item differential** (phase 2): normal, tamper, `client_inactivity`, stall / loop / hard-ceiling kills, cooperative cancel, grader failure, export failure, transport abort, resume refusal. **Chain differential** (phase 3): pilot → full, barrier mismatch, block restart, STOP, idle cancel + escalation. Compared by exact JSON pointer: allowed row additions `/config_id`, `/arm`, `/epoch_id`, `/snapshot_sha256`, `/final_tree/*`, `/token_accounting`; manifest additions `/runtime/{config_id,arm,epoch_id,snapshot_sha256,snapshot_complete,snapshot_fields,evidence_policy}`; allowed value changes `/probe_code_sha256`, `/scaffold_policy_sha256`, `/generation_identity_sha256`, `/runtime/policy/*` (each re-derived independently by the test from its recipe; every pre-P371 policy key must keep its value except `scaffold`-independent additions); `/compaction` and `/receipts` FORBIDDEN in tg1 rows. **File-layout table (R10, R27)**, one row per tg1 phase shape (`steps_for`): (a) pilot only (`pilot` mode; `reload`; smoke when pilot == full): old `<stem>.jsonl` == new `<stem>.L<leg>.pilot.a<n>.jsonl`, old manifest ↔ the pilot manifest; (b) pilot + full (first leg of a block, pilot ≠ full): old rows == pilot rows then full rows (validated attempts only), each slot once; old manifest (last writer = full) ↔ the full manifest, the pilot manifest ↔ the old pilot-step manifest the harness captures before the full step overwrites it; (c) full only (later legs of a block): old rows == `<stem>.L<leg>.full.a<n>.jsonl`, manifests 1 : 1; (d) smoke (1-item pilot + 2-item leg): as (b) with the smoke counts; each shape has its own differential test; old `<stem>.attempt<n>.{log,json}` ↔ new `<stem>.L<leg>.<phase>.a<n>.{log,json}`; `chain.json` compared on every pre-P371 key, new keys (`progress`, `lifecycle` members, `chain_config`, `snapshots`, `epoch_id`, `artifacts`) listed. Anything else = failure | each path equal modulo the table; a planted unlisted difference fails; a planted current-tree import in the bundle run fails; missing git history (shallow clone) → the test FAILS in the worktree, skips only with `P371_NO_GIT_HISTORY=1` and an explanation |

## 5. tg1 epoch, identities, lifecycle

- One new tg1 epoch at merge (C178): `probe_code_sha256` = closure of `run_tg1_probe.py` (now incl. the core, corpus,
  policies, receipt contract, hooks, adapter); `scaffold_policy_sha256` gains the generation policy. Recorded in the
  handoff with the merge commit; no rows exist in `ae7fca94…`.
- Pairing composite and arm identity recipes unchanged (P311 spec 4); M64 arms keep `arm_generation_sha256`.
- **Chain lifecycle closure (R15):** per chain entry, the static import closure of the entry (`identity_closure`, as the
  probe identity) + the serialized `ChainConfig` + the A4 gate + the launcher; frozen in `chain.json` at creation,
  verified before every launch, barrier, validation, resume and at exit (P24). Arm specs / arm ops / schedules / rows
  loader are in it by import. A drift test edits a temp copy of each member.
- P311 closure tests extended per probe entry (§3.1 exclusions; `sys.modules` after a fake item ⊆ closure;
  reachability covers config-off branches as deliberate inputs).
- **Isolation (R17):** one test process runs `tg1`, `m64-oc-tg1` and the fake non-opencode × four-language config in
  both orders; rows, identities, closures and disabled features (watchdog, compaction, receipts) are asserted per config.

## 6. Lead calls (operator may overrule; `docs/open-questions.md`)

- **P376 — tg1 pilot / full become disjoint invocations** (R18): the pilot invocation runs the 5 seeded items, the full
  invocation the cell's remaining items (today the full step re-launches all items and the probe skips the pilot's rows
  by resume). Generation per item is unchanged (fresh session per item, same seed, same order of the remaining items);
  the on-disk layout changes and is mapped by the A14 table.
- **P372 — A3 runner side only.** The `../mlx-vlm` endpoint (the §4 A3 protocol) is built at the M64 fork step, branched
  from the fork after P369's fork push; it must pass the same protocol fixture tests. Until then `worker_receipts:
  required` refuses at start (the M64 real chain already refuses on the D2 stub).
- **P373 — transport and resume policy per `ChainConfig`.** tg1 and tg2 keep tg1 semantics (abort_restart /
  restart_load; watchdog and compaction off). Incident retry + `transport_dnf` stays M64's (C165 2b). tg2 → incident
  retry would be a tg2 spec change for the operator.
- **P374 — `OWED` contract checks.** D2-, infrastructure- and P201-dependent checks are listed `OWED`, never faked;
  smokes may run with `OWED`; a non-smoke chain refuses.
- **P375 (revised, R16) — review loop bound.** Another cold Cursor review is required after any semantic / control-flow
  fix. Lead-only closure (lead verification + green full suite) is allowed only for mechanical fixes (naming, messages,
  typing, a missing assertion) that come with a proving regression test and no behaviour change on any other path.

## 7. Build phases (each: red tests → fix → green targeted tests → commit; push `m64-build` after each batch, privacy-scanned)

0. DONE: main merged into `m64-build` (`5fb51c1a`); baseline full suite from the worktree alone → scratchpad file.
1. Contracts: `run_config`, `corpus` + `corpus_tg1` (+ typed records), `worker_receipts` (+ protocol fixture, fake,
   unavailable), `item_barrier`, `chain_hooks`, `web_evidence`, `chain_rows` (+ consumer enumeration, R7), `schedules` (absorbing `m64_schedule`),
   `Host`; the isolated-baseline harness for A14.
2. Item core: `arm_runner` absorbs the tg1 loop; `tg1_runner` thinned; adapter contract changes (A11); A2, A3 (runner
   side), A4 (+ `toolwindows.js`), A12; item differential tests (A14) green; the 23 `tg1_runner`-coupled test modules
   green against the core.
3. Chain core: `chain_core` absorbs both chains; thin entries; A1, A5–A10, R7 scan, lifecycle closure (R15); chain
   differential tests; the tg1 and M64 chain test modules green.
4. Contract suite re-based + artifact mode + chain refusal (A13); P311 closure tests per entry; isolation (R17).
5. Docs: M64 spec §5 (contract additions, core + configs, hooks), §7 (protocol fixed; fork endpoint P372), §8 (schedule
   builders, leg-attempt files); tg2 spec T14 → "tg2 is a configuration of the shared core: own entry, corpus, label;
   the core is in every closure, so a core change moves every identity (accepted, C178)"; `benchmark/README.md` entry
   points; handoff.
6. Cursor code review on the build commit (one review at a time; output to the scratchpad); fixes per P375.
7. Full suite from the worktree alone (`> file`); lead verification of §8; merge to `main` when no chain from main runs.

## 8. Acceptance criteria (pre-registered)

1. One item loop (`arm_runner.run_item`) and one chain class (`chain_core.Chain`): no other production module spawns a
   client session or supervises a probe (scan over `benchmark/` excluding tests).
2. Every §4 test exists, was red before its fix (commit order shows it), and is green.
3. A14 item and chain differential suites green with the JSON-pointer table as written (a change needs a plan amendment).
4. P311 closure tests green for `run_tg1_probe.py` and `run_oc_probe.py` with the §3.1 exclusions.
5. The fake non-opencode adapter × four-language corpus runs probe + chain end to end; the isolation test (R17) green.
6. `contract_artifact.py --arm oc` on this box (real 2.0.20 binary, mock provider): every non-`OWED` check passes; the
   artifact is hashed; without the binary it exits nonzero; the chain-refusal tests (A13) green.
7. Full suite from the worktree alone: 0 failed, 0 errors; skips only documented environment skips, count reported
   against the phase-0 baseline.
8. Cursor code review cleared, or closed under P375 (revised) with every remaining finding listed and fixed.
9. The new tg1 `probe_code_sha256` and the `m64-oc-tg1` identity from `--print-identity`, recorded in the handoff.

## 9. Risks

- Test churn: 23 test modules import `tg1_runner`, 6 the M64 runners; seams move to `arm_runner` / `chain_core`; phase 2
  and 3 each end with those modules green.
- Hidden tg1 behaviour lost: the isolated-baseline differential suites are the guard; any unlisted difference fails.
- `toolwindows.js` hook names / call-id availability in 2.0.20 are unverified: the real-client contract test is A4's
  first red test; if the hooks cannot give start times, A4 stops for an operator decision.
- Leg-attempt files change the on-disk layout of new tg1 chains; stored chains are read through `chain_rows`' legacy
  mode, with byte-identical report outputs on P223 / M63 / c144-base / M65 pilot as a test.
- Size: ≈ 4–5 k lines moved or changed plus tests; estimate 2–3 working sessions of agent time, no GPU.
