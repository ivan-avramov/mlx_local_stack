# P371 — one shared arm-neutral item + chain core (PLAN v1, 2026-10-17)

Status: PLAN v1 → Cursor `gpt-5.6-sol-high` plan review → build. Ruling: C178 (operator: "go for the expanded p371").
Inputs: M64 step 4a Cursor round 1 NOT CLEARED A1–A14 (`benchmark/chains/m64/reviews/step4a-round1.cursor-gpt-5.6-sol-high.md`
on `m64-build` `406cc10e`); P370 lead calls; M64 spec §4–§8, §12; tg2 spec v5 (T14); P311 spec v4.
Branch / worktree: `m64-build` in `$STACK_WORKDIR/worktrees/m64` (main merged in first). No GPU work.

## 1. Problem

Two item loops and two chain runners do the same job:

| layer | tg1 | M64 | tg2 (step 3, not built) |
|---|---|---|---|
| item loop + probe main | `bench/tg1_runner.py` `run_item` / `_main` (~640 lines) | `bench/arm_runner.py` (757 lines, a copy driven through `ArmAdapter`) | would be a third copy (`tg2_runner.py`) |
| chain | `chains/c147/run_tg1_chain.py` `Chain` (1,025 lines) | `chains/m64/run_m64_chain.py` `ArmChain(base.Chain)` (881 lines, overrides most methods) | would be a third |

The copy existed to keep the tg1 generation identity unchanged. tg1 epoch `ae7fca94…` has no rows, so the identity can
move once now at no cost (C178). The M64 4a fixes (A1–A14) and P370 land in the one implementation instead of a copy.

## 2. Goal and non-goals

Goal: ONE item core and ONE chain core. tg1, tg2 and each M64 arm are CONFIGURATIONS (data + injected seams), each with
its own thin probe entry and thin chain entry. All A1–A14 + P370 fixes land in the core.

Non-goals (owned elsewhere, unchanged): the `../mlx-vlm` receipt endpoint (§6 P372), the D2 SearXNG service + MCP
server, Pi / dsh adapters, snapshot / adoption tooling, arm-neutral P201 audit lifecycle, the judge panel (M64 §12 steps
4–6); the tg2 corpus implementation and tg2 legs (tg2 step 3, on this core); any change to `structured_grade`,
`tg2_grade`, `opencode_v2_core` behaviour, the carriers, or the scoring path (`tg1_score`, `row_scores`).

## 3. Architecture

### 3.1 Modules

| module | role | status |
|---|---|---|
| `bench/run_config.py` | `RunConfig` frozen dataclass (pure data, §3.2); canonical JSON → part of `scaffold_policy_sha256` | new |
| `bench/corpus.py` | `Corpus` contract (pure): `load_universe`, `items`, `excluded`, `prepare(item, work)`, `prompt(entry, inject)`, `grade(...)`, `tampered(...)`, `changed(work, entry, initial)`, `final_tree(work, entry)`, `languages`, `needs_docker(lang)`, `identity()` (grader version, timeouts, image) | new |
| `bench/corpus_tg1.py` | tg1 corpus: today's universe preflight, `go/counter` exclusion, polyglot prepare + git init + mtime freeze + frozen-manifest check, tg1 prompt + inject addenda, `structured_grade` grade / tamper, the M59/M61 "untouched solution fails" rule, final-tree snapshot | new (moved code) |
| `bench/worker_receipts.py` | spec §7 runner side: `ReceiptSource` contract (`start(attempt)`, `fence(attempt)`), receipt schema, one-to-one join to classified client requests, `UnavailableReceiptSource`, `FakeReceiptSource` (tests) | new |
| `bench/arm_runner.py` | THE item core: `run_item` + probe `main` / `print_identity`; absorbs `tg1_runner`'s library parts (`GradeWorker`, `PhaseHeartbeat`, worker / router checks, `RunnerCancelled`, `_DiscoveryGuard`, `grade_reports`, `_link_mem_kills`) | rewritten |
| `bench/tg1_runner.py` | thin: tg1 constants (`SCAFFOLD`, carrier / plugin paths, `GENERATION_DATA`, `INJECT_*`), `TG1_CONFIG`, `main` / `print_identity` delegating to the core | thinned |
| `bench/arm_opencode.py` | opencode adapter, modes `tg1` / `m64`; owns every opencode specific the core used to name (A11); no `m64_search` import (search injected by the entry) | changed |
| `bench/arm_adapter.py` | contract gains `seed_overlay`, `overlay_sha`, `preflight(selection=…)`, `web_evidence(…, dest)` (raw + hash), `tool_windows` from live start receipts, `classify_terminal` incl. `compaction_failed`, `request_classes` (task / compaction / auxiliary) | changed |
| `bench/chain_core.py` | THE chain core: lifecycle freeze, per-arm policy derivation, frozen date, epoch + snapshots, schedule freeze, loads / legs / attempts, barrier, supervision (idle predicate, escalation, STOP, watch log), validation + pinning, transport policy (abort-restart or incident-retry), persisted progress + resume, A4 receipts | new (moved + merged code) |
| `bench/schedules.py` | pure, hashed builders: `tg1` (pilot / full / reload, today's LEGS order), `blocks` (M64 seeded order, blocks of 3, balanced arm permutations, reload control) over ANY corpus / language set, `tg2_tier` (screen / decider nested draw prefixes) | new (absorbs `m64_schedule.py`) |
| `bench/chain_rows.py` | one segment inventory + slot-deduplicating row loader (A9): base rows, `.w<n>` segments, `.dnf.jsonl`; used by the chain and every report entry point that reads chain rows | new |
| `chains/c147/run_tg1_chain.py`, `chains/m64/run_m64_chain.py` | thin entries: CLI, out-root rules (P340, ON/OFF separation), `ChainConfig`, `main` | thinned |
| `run_tg1_probe.py`, `run_oc_probe.py` | thin probe entries binding (config, adapter, corpus, host) | changed |
| `opencode_plugins/toolwindows.js` | M64 oc only: tool start / end receipts (`execute.before` / `execute.after`, callID, tool, ms) to a per-item file outside the config dir (A4) | new |

Dependency rule (identity hygiene): `arm_runner`, `chain_core`, `schedules`, `chain_rows`, `corpus`, `worker_receipts`,
`run_config`, `arm_adapter` import NO corpus, adapter or client module. Entries inject them. Consequences tested by the
P311 closure tests: the tg1 closure excludes `tg2_*`, `m64_search`, Pi / dsh modules and every scoring module; the M64 oc
closure excludes `tg2_*`; a future tg2 closure excludes `corpus_tg1`.

Host seam: the generic helpers the core calls on `p` today (`_scrub_pii`, `_portable`, `_sha_of`, `_stack_workdir`,
`_item_seed`, `_seed_row_fields`, `_polyglot_root`, `_polyglot_sha`, `_prompt_date`, scratch dirs, `_fresh_tmpdir`) become
an explicit `Host` protocol in `arm_runner` (documented list, checked at entry). `opencode_v2_core` keeps satisfying it;
moving them out of the opencode module is deferred to the Pi adapter (first non-opencode host).

### 3.2 Configurations

`RunConfig` fields (all in the policy hash): `config_id`, `label`, `arm`, `adapter_mode`, `corpus_id`, `langs`,
`inject_allowed`, `budgets` (thinking 81,920 / max 102,400 / context from the carrier — today hard-coded in
`validate_worker`), `watchdog` (off | on), `compaction` (off | on_accounted), `worker_receipts` (absent | required),
`transport_policy` (abort_restart | incident_retry), `snapshot_complete_required` (bool, non-smoke chains),
`evidence_root`, `web_evidence` (on — every config).

| config | entry | label | langs | watchdog | compaction | worker receipts | transport | snapshot complete |
|---|---|---|---|---|---|---|---|---|
| `tg1` | `run_tg1_probe.py` | `opencode-v2-web-tg1` | python, go | off | off | absent | abort_restart | no |
| `m64-oc` | `run_oc_probe.py` | `opencode-v2-web-tg1c` | corpus langs (tg1 or tg2) | on | on_accounted | required | incident_retry | yes (smoke: no) |
| `tg2` (step 3) | `run_tg2_probe.py` | `opencode-v2-web-tg2` | rust, java, javascript, cpp | off | off | absent | abort_restart | no |

`ChainConfig` (chain entry, frozen in `chain.json`): arms → (probe entry, label, arm spec), schedule builder + params,
out-root family, predictor, arm-switch ops required (search restart / cache reset / warm-up: M64 yes, tg1 / tg2 no),
resume policy (`restart_load` for abort_restart configs, `new_segment` for incident_retry).

### 3.3 Item core flow (one implementation; config decides the optional steps)

`main`: argument checks against the config (langs, inject, frozen date required, sampling profile) → adapter selection
(an arm needing a missing service refuses here) → toolchain → declared model + M50 router assertion → worker identity +
arm identity + budget check from `cfg.budgets` → `corpus.load_universe` + item checks → binary → `adapter.preflight`
(A4 receipt for THIS selection) → run dir → discovery (version + destination proof) → identity (+ `config`) → snapshot +
`epoch_id` (§4 A5) → resume checks (identity, serving path, worker, duplicate rows) → manifest → per item:
`corpus.prepare` → `adapter.seed_overlay` + `build_env` + `verify_env` → per-item discovery → `corpus.prompt` →
`receipts.start(attempt)` (when required) → `run_item` → `receipts.fence(attempt)` + join (when required) →
`corpus.changed` / pass rule → row (core fields + `adapter.row_fields` + `adapter.metrics` + `adapter.overlay_sha` seed
fields + `arm`, `config_id`, `epoch_id`, `snapshot_sha256`, `web_evidence`, `token_accounting`).

`run_item`: today's tg1 control flow verbatim (gate, guard, grade worker, heartbeat, ingestion, silence observer,
SIGTERM-first cancellation, terminal drain, transcript, reconcile, date-freeze receipts, tmp escapes, final grade), plus:
watchdog ticks (config on), compaction accounting (config on), web evidence on EVERY outcome (A12), final-tree snapshot.

## 4. Fix absorption (each: test first, red, then the fix)

| id | fix in the core | red test(s) |
|---|---|---|
| A1 | `schedules.blocks` takes the corpus's languages and per-language item lists (tg1 universe or a tg2 tier prefix), cell sizes from the data (10 = 3 blocks + 1 residual); `schedules.tg2_tier` (screen: k = 1 = s1 only, 10 / language; decider: s1 + s2 + same-seed reload 5 / language); a named `m64-tg2-screen` schedule = `blocks` over the tg2 screen, s1 only, both picks (C175 (3), C168 k = 1 exception; M64 spec amendment still follows the smoke, C175 D3); docker gate from `corpus.needs_docker(lang)`; `run_oc_probe.py --lang` from the corpus | 4-language fake corpus through `blocks` + `tg2_tier`: hashes stable, permutations balanced per cell, nested prefixes, realized order checked; a fake 4-language chain runs end to end |
| A2 / P370 | `compaction_failed` registered terminal shape (pinned 2.0.20 export / error shape, from a real-client fixture) → scored strict-fail row, `nonconv_kind: compaction_failed`, added to `tg.PRECEDENCE` after the client cuts; chain continues; compaction tokens counted: from receipts when present, else post hoc from the export (P370 (1), disclosed per row `compaction.accounting: post_hoc|receipts`) and INCLUDED in the task totals | adapter + core end to end: failed-compaction export → row scored, chain continues; tg1 config with a compaction message still aborts |
| A3 | `worker_receipts` (runner side of spec §7): start mark records the worker's admission sequence; end fence after client exit returns last sequence + receipts; attempt owns (start, end]; receipt after its fence → abort; requests classified from client events (task / compaction / auxiliary), joined ONE-TO-ONE by fence + admission order + timestamps (+ `X-Bench-Attempt` where supported), then checked per class (sampling, seed, budget, max_tokens, roles, `request_tools_present` / `request_tools_sha256` allowed set); task tokens = owned receipts incl. disconnected generations; `token_accounting: receipts` (complete) / `client` (absent). `worker_receipts: required` + `UnavailableReceiptSource` → refuses before any spawn. Fork endpoint: P372 | `FakeReceiptSource`: client cut with tokens after disconnect counted; auxiliary + compaction classes; missing, duplicate, late-after-fence, ambiguous join, tools mismatch per class → abort; legit tool-less compaction passes; tg1 config unaffected |
| A4 | `toolwindows.js` (M64 oc) writes start / end receipts at `execute.before` / `execute.after`; the adapter's `tool_windows` = live start receipts (open) merged with completed `tool_use` events by callID; the watchdog's `exec_timeout` (any kill OR any completed-window overrun) sets the gate flag; one final tick after client exit before reconcile; hook firing proven on the REAL pinned client | unit: open window from a start receipt only; completed-window overrun → flag; final tick; real-client contract: a hung `sleep` tool call killed at the accelerated limit, row flagged |
| A5 | `epoch_id` computed by the chain from every arm's snapshot (`--print-identity` now emits `snapshot_sha256`, `snapshot_complete`, `snapshot_fields`); `--epoch-id` becomes an assertion; `chain.json` freezes `arm → snapshot_sha256`; verified at entry, resume, every barrier (manifest `runtime.snapshot_sha256`), exit (re-run `--print-identity`); non-smoke chain of a `snapshot_complete_required` config refuses an incomplete snapshot | changed snapshot between legs / at resume / at exit → abort rc 2; CLI epoch mismatch → refuse; tg1 config runs with an incomplete snapshot |
| A6 | incident classification checks router (owner pid, config, port) and worker identity INDEPENDENTLY first (worker gone / changed → `worker_crash`; router gone / changed → `router_error`), then the adapter's cause; no cause → not transport | fake ops: worker crash with an unrecognized client error → incident `worker_crash`; router death → `router_error` |
| A7 | retry requires a COMPLETE cleanup receipt (dict; no survivors, no containers, `uncertain is False`); missing → chain abort with listing; partial-row validation = `validate_leg` + arm / config / epoch / snapshot row checks before the retry | missing receipt → abort; partial row with wrong `snapshot_sha256` → abort |
| A8 | `chain.json.progress`: per load {status, worker instances, current segment, validated legs with (segment, rows sha256)}; resume of a `new_segment` load: fresh worker, segment + 1, scored ids ONLY from chain-validated segments (sha-checked), realized order appended once per leg key; `restart_load`: archive the load with a sha256 manifest BEFORE moving, rerun from leg 0 (today's tg1 behaviour) | kill mid-load (fake) → resume: no refusal, no double-count, realized order == schedule; tampered validated segment → abort |
| A9 | `chain_rows.inventory(session_dir, stem)` → ordered segments + DNF sidecar; `load_slots` dedups by slot, refuses a slot scored twice, checks `chain.json["dnf"]` == sidecar; chain `scored_ids` and every report entry point that reads chain rows use it | base + w1 + dnf fixture → each slot once; duplicate slot → error; drifted DNF copy → error |
| A10 | A4 run after EVERY worker (re)load per arm; receipt copied to `<out_root>/a4/<load>.<worker_n>.<arm>.json` (immutable, exclusive create), sha in `chain.json`; probes get the immutable path | two arms + a recovery reload → 3 distinct receipts, none overwritten; probe given a pre-reload receipt → refused |
| A11 | opencode specifics move behind the adapter / arm spec: carrier field names in `preflight`, `OPENCODE_CONFIG_CONTENT` → `adapter.overlay_sha(env)`, seed overlay → `adapter.seed_overlay`, A4 gate command → `ArmSpec.a4_command` (`chain_ops.a4_gate` takes it), evidence dir name, label checks | a fake non-opencode adapter (different env var, no carrier fields) runs through core + chain with zero opencode names |
| A12 | `adapter.web_evidence(transcript, env, dest)` called on every outcome with a transcript (pass, fail, cut, incident, cancel), writing raw tool calls + their returned content (fetch body / search result / shell command + output as the model saw them) to `<evidence>.web.jsonl`, sha256 in the row / incident / cancel record; no transcript → `web_evidence: unavailable` + reason recorded (P201 treats it as unauditable, not as "no contact") | success, gate kill, incident and cancel paths each leave a hashed web evidence file; export failure records `unavailable` |
| A13 | contract suite runs on REAL core runs (fake client and the real pinned client against `opencode_v2_mock.py` with wire capture), checking every request incl. compaction requests (controls + tools per class); `benchmark/m64/contract_artifact.py --arm oc` writes a hashed artifact and FAILS (never skips) without the binary; checks that need unbuilt services (D2 search, infrastructure classification, P201 re-run) are listed `OWED` in the artifact; a non-smoke chain refuses an artifact with any `OWED` or failed check (P374) | artifact mode without binary → nonzero; suite case mutations (17 injected defects, re-based) each red; compaction request with wrong seed → red |
| A14 | differential tests: frozen copies of the pre-P371 tg1 path (`tests/legacy_tg1/` — `tg1_runner.py`, `run_tg1_probe.py`, `run_tg1_chain.py` at `0c9bd32a`; test-only, never imported by production, outside every closure) vs the core with `TG1_CONFIG`, same fake-client fixtures, on normal AND exceptional paths (tamper, `client_inactivity`, stall / loop / hard-ceiling kills, cooperative cancel, grader failure, export failure, transport abort, resume refusal, barrier mismatch, block restart); rows and manifests compared field by field modulo an EXPLICIT allow-list of added fields (`config_id`, `arm`, `epoch_id`, `snapshot_sha256`, `web_evidence`, `token_accounting`, `compaction`, the identity values); "byte-identical" wording dropped | each path: equal modulo the allow-list; an unlisted difference fails |

## 5. tg1 epoch and identities

- One new tg1 epoch at merge (C178): `probe_code_sha256` = closure of `run_tg1_probe.py` (now incl. the core, corpus,
  config, receipts contract, adapter); policy gains `config`. Recorded in the handoff with the merge commit; no rows exist
  in `ae7fca94…`.
- The pairing composite and arm identity recipes are unchanged (P311 spec 4); M64 arms keep `arm_generation_sha256`.
- Chain lifecycle freeze (P24) covers the chain entry, `chain_core`, `schedules`, `chain_rows`, `chain_ops`, the A4 gate
  and the launcher.
- P311 closure tests extended: per entry, the exclusion lists of §3.1; `sys.modules` after a fake item ⊆ closure; the
  reachability check covers the core's config-off branches (watchdog, receipts) as deliberate inputs.

## 6. Lead calls (operator may overrule)

- **P372 — A3 is absorbed on the runner side only.** The `../mlx-vlm` control endpoint (admission sequence, start / end
  fences, per-request receipts incl. disconnected generations) is built at the M64 fork step, branched from the fork after
  P369's fork push (one fork branch in flight at a time; the push needs the operator). Until then a `worker_receipts:
  required` config refuses at start — the M64 real chain already refuses (D2 stub), so no capability is lost.
- **P373 — transport and resume policy per config.** tg1 and tg2 keep today's tg1 semantics (transport abort → leg
  incomplete → load archived + restarted once → chain abort; no incident retry, no DNF rows; watchdog and compaction
  off). Incident retry + `transport_dnf` stays M64's (C165 2b). Moving tg2 to incident retry is a tg2 spec change for the
  operator.
- **P374 — `OWED` contract checks.** D2-, infrastructure- and P201-dependent contract checks are not faked: the artifact
  lists them `OWED` with their build step; smokes may run, a real chain refuses.
- **P375 — review loop bound.** Cursor code review rounds continue while findings are design-level; from round 4 on,
  findings that need an improbable collision or an unreachable state are fixed and cleared by lead verification + a green
  full suite without a further round (precedents P365 / C170).

## 7. Build phases (each: red tests → fix → green targeted tests → commit; push `m64-build` after each batch, privacy-scanned)

0. Merge `main` into `m64-build`; full suite from the worktree alone → baseline file.
1. Contracts: `run_config`, `corpus` + `corpus_tg1`, `worker_receipts` (+ fake / unavailable), `chain_rows`, `schedules`
   (absorbing `m64_schedule`), the `Host` protocol; legacy copies for A14.
2. Item core: `arm_runner` absorbs the tg1 loop; `tg1_runner` thinned; adapter contract changes (A11); A2, A3 (runner
   side), A4 (+ `toolwindows.js`), A12; A14 differential tests green.
3. Chain core: `chain_core` absorbs both chains; thin entries; A1, A5–A10; the tg1 chain tests and the M64 chain tests
   run against the core.
4. Contract suite re-based + artifact mode (A13); P311 closure tests per entry.
5. Docs: M64 spec §5 (contract additions, core + configs), §7 (runner side built, fork endpoint P372), §8 (schedule
   builder, `m64-tg2-screen`); tg2 spec T14 → "tg2 is a configuration of the shared core: own entry, corpus, label; the
   core is in every closure, so a core change moves every identity (accepted, C178)"; `benchmark/README.md` entry points;
   handoff.
6. Cursor code review on the build commit (one review at a time; output to the scratchpad); fixes per P375.
7. Full suite from the worktree alone (`> file`); lead verification of §8; merge to `main` when no chain from main runs.

## 8. Acceptance criteria (pre-registered)

1. Exactly one implementation of the item loop (`arm_runner.run_item`) and one chain class (`chain_core.Chain`): no other
   module spawns a client session or supervises a probe (grep test over `benchmark/` excluding `tests/legacy_tg1/`).
2. Every A1–A14 and P370 test of §4 exists, was red before its fix (commit order shows it), and is green.
3. A14 differential suite green on every listed path with the allow-list as written here (additions need a plan
   amendment).
4. P311 closure tests green for `run_tg1_probe.py` and `run_oc_probe.py` with the §3.1 exclusions.
5. A non-opencode fake adapter and a four-language fake corpus each run probe + chain end to end.
6. `contract_artifact.py --arm oc` on this box (real 2.0.20 binary, mock provider): every non-`OWED` check passes; the
   artifact is hashed; without the binary it exits nonzero.
7. Full suite from the worktree alone: 0 failed, 0 errors; skips only the documented environment skips (count reported
   against the phase-0 baseline).
8. Cursor code review cleared (or closed under P375 with the remaining findings listed and fixed).
9. The new tg1 `probe_code_sha256` and the M64 oc identity printed by `--print-identity` and recorded in the handoff.

## 9. Risks

- Test churn: 23 test modules import `tg1_runner`, 6 the M64 runners; seams move to `arm_runner` / `chain_core`.
  Mitigation: phase 2 and 3 each end with those modules green before the next phase.
- Hidden tg1 behaviour lost in the merge: A14's exceptional-path differential tests are the guard; any unlisted
  difference is a failure, not a judgement call.
- `toolwindows.js` hook names / callID availability in 2.0.20 are unverified: the real-client contract test is the first
  red test of A4; if the hooks cannot give a start time, A4 stops for an operator decision (watchdog without start
  instrumentation keeps the G2-style residual for hung tools).
- Size: ≈ 3–4 k lines moved or changed plus tests; estimate 2–3 working sessions of agent time, no GPU.
