Findings on the M76 B4b tg2 runner spec, round 1: 15 findings and one scope request. I traced the call chains against the source and did not run anything. File:line references are in `benchmark/bench/` unless a path is given.

## F1 — The tg2 chain configuration is undefined, and the existing `tg2_tier` path is the M63/M64 chain, not the P426 chain
- **Location:** spec "Chain"; `chain_core.py:1349-1351`, `:372`; `chain_ops.py:303-314`; `run_config.py:293-298`.
- **Severity:** blocker. **Evidence:** confirmed.
- **Problem:**
  - `ChainConfig.__post_init__` allows `transport_policy="p426_continue"` only for `config_id == "tg1-p426"`. That config requires builder `"tg1"` and exactly one model. The spec lists `run_config.py` as changed but names no tg2 config id, builder or transport policy.
  - `chain_core.py:1349` runs `ops.ensure_overlay()` for every builder except `"tg1"`.
  - Under the tg1 entry the "overlay" is the committed registry itself (`run_tg1_chain.make_ops` passes `served` as the overlay).
  - With `--predictor mtp`, `ensure_overlay` compares the file to `overlay_header + raw`. They differ, so it raises `ChainAbort("M63 overlay stale")`. It also calls `require_mtp(…, (PICK1, PICK2))`.
  - `needs_docker` defaults to `lang == "go"` in the chain (`chain_core.py:328`), so the P290 docker gate is skipped for tg2. The spec puts `needs_docker` on the corpus only.
  - `self.pred` is the M64 table `PRED_S` for any non-tg1 builder.
- **Scenario:** an implementer who selects `tg2_tier` gets a leg that aborts at start under `--p426 --lever kv --predictor mtp`. If they instead reuse builder `"tg1"`, the schedule has no tg2 shape.
- **Change:**
  - Define the tg2 P426 `ChainConfig`: config id, builder, one model, `p426_continue`.
  - State that the overlay and `PRED_S` branches become P426-aware: `ensure_overlay` is skipped when the transport policy is `p426_continue`.
  - Pass `needs_docker = True` for every tg2 language into `Chain`.
  - Add acceptance tests for a tg2 leg start under mtp with the committed registry, and for the docker gate.

## F2 — The schedule shape and `leg = session` conflict with every downstream consumer
- **Location:** spec "Chain" and "B8 / signals"; `schedules.py:315-359`; `p426_freeze.py:705-720`; `p426_verify.py:165-189`, `:320`; `chain_core.py:1181,1200`.
- **Severity:** blocker. **Evidence:** confirmed.
- **Problem:**
  - `schedules.tg2_tier` emits `sessions[].cells[]`. `fz.planned_slots` (used by `classify_leg` and the pilot gate), `p426_verify.planned_slots` and `schedule_plan_sha` all read `blocks[].legs[].invocations[]`. `p426_not_run` reads `blocks[]` too.
  - `tg2_tier` builds every session of the tier. `check_tg2_membership` rejects any schedule that is not equal to the whole tier. A P426 leg is one session, so a one-session schedule fails (`:349-351`).
  - `tg2_tier(sessions=…)` only accepts exactly `TG2_SESSIONS[tier]`.
  - No smoke shape exists. The leg-level membership check also rejects a one-item-per-language cell.
- **Scenario:** `classify_leg` returns INVALID ("no blocks / legs / invocations") for every tg2 leg. B8's `check_planned` refuses every tg2 attempt.
- **Change:** pick one schedule document shape for tg2 legs. Either emit the `blocks/legs/invocations` shape with the draw check, or give `planned_slots`, `schedule_plan_sha` and `not_run` a second reader. State how a one-session or smoke leg is frozen and verified. Add acceptance on `classify_leg`, the pilot gate and B8 `check_planned` over a real tg2 leg schedule.

## F3 — Session labels, language order and the smoke/screen/reload definitions contradict the code and M65
- **Location:** spec "Chain"; `schedules.py:321,328-333`; `run_tg1_chain.py:284,365-369`; `p426_verify.py:2004-2015`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - **Language order.** `tg2_tier` orders languages alphabetically (cpp, java, javascript, rust). The spec wants rust, javascript, java, cpp for s1 and the reverse for s2. `tg2_tier` cannot produce this and the spec does not say it changes.
  - **Reload.** `tg2_tier` makes reload 5 items for every language (M65: "5 items per language"). The spec says 5 items of s1's first language only.
  - **Screen label.** The screen tier's session is `"s1"` (`TG2_SESSIONS`). The spec's leg names, pair names and B8 sessions are `screen`. B8 reads rows from `<attempt>/<session>/`. `p426_receipt.PAIRS` and the chain's session choices do not know `screen` or `smoke`. L17 and the B4 ledger flagged the session label as unfixed and v1 still does not fix it.
  - **Frozen record.** The record carries "tier" (L11: one tier per record). The flow runs smoke, screen and decider under one v8 record and one amendment. That is one tier per record or three, and the spec does not say which.
  - **Item order.** Within-language order is unspecified: draw order, or a seeded shuffle as tg1 does. Screen and decider s1 also share seed 1001 and the first 40 items, so the screen re-runs at the same seed.
- **Scenario:** the implementer and test-writer each pick a label and an order. B8 looks for `<attempt>/screen/` and finds `<attempt>/s1/`.
- **Change:** state, per leg kind (smoke, screen, s1, s2, reload), the session directory name, seed, language order, item list and order, and the tier the record carries. Say how reload and language order depart from `tg2_tier` and M65. Add golden-schedule acceptance.

## F4 — tg1's scaffold label is hard-coded outside the scope list
- **Location:** spec "Scope" and "Interfaces"; `chain_ops.py:20,904,1164-1197`; `chain_core.py:1597-1598,2033`; `scripts/session_pinning_gate.py:99-101,257`; `arm_specs.py:54-71`; `configgen/targets.py:34`; `modelnames.py:72-85`.
- **Severity:** blocker. **Evidence:** confirmed.
- **Problem:**
  - **Leg validation.** The flat (tg1/tg2) chain calls `co.validate_leg(…, spec=None)`. That compares each invocation manifest's `runtime.scaffold` to the constant `SCAFFOLD = "opencode-v2-web-tg1"`.
  - **A4 gate.** `a4_gate` is called without a scaffold in the flat layout. `session_pinning_gate.py` knows only the tg1, v2 and web carriers, and its `--scaffold` choices exclude tg2. The A4 pin check would run on the wrong carrier or be refused.
  - **Carrier.** The tg1 carrier is a configgen target (`emit_opencode_bench_v2_web_tg1`) listed in `GENERATED_PATHS`. A hand-written `opencode_bench_v2_web_tg2.json` drifts from the generator. A repo model-name hook may also flag it.
  - **Out of scope.** None of `chain_ops.py`, `session_pinning_gate.py`, `arm_specs.py`, `configgen/*` or `modelnames.py` is in the scope list.
- **Scenario:** every tg2 invocation fails completion with `runtime_scaffold: opencode-v2-web-tg2`. If that is bypassed, A4 checks the tg1 carrier, never the tg2 one.
- **Change:** add these files to scope. Make the label a parameter of `validate_leg` and `a4_gate` (from the `ArmBinding`). Add a configgen target for the tg2 carrier (or state why it is hand-written) and update `GENERATED_PATHS`. Test with a real tg2 manifest through `validate_leg`.

## F5 — Harvest and B8 constants contradict the spec's own names
- **Location:** spec "Harvest" and "B8 / signals"; `p426_harvest.py:204-213`; `p426_verify.py:42,331-345,1377,1974-1983,2130`; `p426_freeze.py:100,735`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - `NAMESPACE_RE = wave2(?:\.[a-z0-9][a-z0-9.-]*)?`, so `wave2-tg2` is refused by `namespace_root`.
  - B8 hard-codes `WAVE = "wave2"` for `run/`, attempt directories, `harvest_manifests` and dossiers.
  - `_kv_check_member` applies `KV_DENY_PATTERNS`, which includes `smoke`. The spec's attempt names include `smoke`, and AC3 wants "B8 (smoke as coverage)".
  - `verify_all_kv` detects A7 only via `m76/wave2/run`.
  - `kv_pilot_leg` is `tg1-m76-<arm>-pilot` and the pilot gate checks that name.
- **Scenario:** the first tg2 harvest fails with `HarvestError`. B8 rejects every smoke attempt name, or reads the wrong directory.
- **Change:** use a namespace the regex accepts (for example `wave2.tg2`) or change the regex. Parameterise `WAVE` and the verifier's deny list per corpus. Define `verify_all_kv` dispatch for A8 and a leg-name function per corpus.

## F6 — Freeze, amendment and sequencer values are python/go-specific, and the walls have no source
- **Location:** spec "Freeze / sequencer"; `p426_freeze.py:36,82-87,678,698,723-750,826-835`; `p426_wave2.py:209-227`; `p426_record.py`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - `cmd_v8` requires `w_python_s` and `w_go_s` and computes `pilot_deadline_s` from `{"python": 5}`. For tg2 the smoke deadline is needed in the v8 record before the smoke exists. The spec derives walls from the smoke's sizing report, which is circular.
  - "M55 heavy-tail allowance" has no value or source.
  - `ITEM_COUNT`, `PILOT_N` and `planned == PILOT_N` are tg1 values.
  - `pilot_walls` returns one undifferentiated list of walls with no per-language split.
  - `leg_deadline_s[kind]` keys for screen, s1, s2 and reload are not stated, and the reload deadline is `{python: 5}`.
  - `cmd_v8` requires the rehearsal manifest and R1–R3 (tg1 legs; R2 injects at the first Go item, R3 at the first Python item). The settle bound is derived from R1's walls. The spec does not say whether tg2 reuses the tg1 rehearsals or needs its own.
  - The "positives gate" in the sequence has no seam, record or content. The B4 candidate had an `ops.tg2_positives` seam for the grader positives. Whether the 12 injected stall/loop/alloc runs enter the gate is open.
- **Scenario:** `p426_freeze v8 --corpus tg2` cannot run, or runs on tg1 numbers. The amendment step raises `KeyError` or `ValueError` on tg2 languages.
- **Change:** state each wall's origin and number for the v8 base, and state the amendment's `leg_deadline_s` keys and n per language. State the rehearsal policy for tg2. Define the positives gate: seam, record, what it checks, and who produces it.

## F7 — The grader mapping contradicts `Tg2Grade.failing` and omits per-item data
- **Location:** spec "Probe" (`grade_outcome`); `tg2_grade.py:942-949`; `tg2_universe.py:194-200`; `arm_runner.py:412,464-470`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - The spec says `failing` = "leaves of the universe entry not passing". `Tg2Grade.failing(universe)` also counts every collected failing leaf outside the universe (initialisation, teardown, suite-level events). `baseline_failing` and the gate's baseline are computed with that function.
  - A literal implementation drops those failures, so a tree with a failing setup hook and all universe leaves green scores PASS.
  - The universe entry's `timeout_s` (`max(180, 3 × ref)`) and `prepared_cargo_toml` are not mentioned. All current values are 180, so omitting `timeout=entry["timeout_s"]` is benign today but wrong by design.
- **Scenario:** a Java or JavaScript item with a failing `@BeforeAll` or a jest suite-level failure is scored PASS and breaks the "strict" comparison.
- **Change:** `failing = result.failing(set(entry["leaves"]))` with `result.optional` set from the entry. Pass `timeout=entry["timeout_s"]`, `prepared_cargo_toml` and `solutions` from the entry. Add a mapping test for an out-of-universe failure.

## F8 — The grade-join timeout and the default universe are tg1-specific
- **Location:** spec "Probe" (`identity`); `arm_runner.py:166-169,253-257,945-953,1076,1105`; `chain_ops.py:27,998`; `tg2_grade.py:1068,1224,1361-1395`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - **Join timeout.** The core's join timeout is `2 × max(grader_timeout_s) + 60`. For tg1 that is 420 s because a tg1 grade is one timed run. A tg2 grade is several steps (compile, execute and others), each with its own timeout. A model-written infinite loop gives a compile of up to about 100 s plus an execute timeout of 180 s. Two grades (active plus queued) then exceed 420 s.
  - **Failure mode.** The join raises `TransportAbort` ("grading worker did not finish…"). That is systemic, so the leg is INVALID and an 8 h leg is lost.
  - **Spec silence.** The spec says nothing on what `Tg2Corpus.identity()["grader_timeout_s"]` holds.
  - **Cooperation bound.** `t_coop` uses `GRADER_TIMEOUT_S.get(lang, 300)`.
  - **Default universe.** `arm_runner.DEFAULT_UNIVERSE` is `m62/universe.json`. `a.universe or DEFAULT_UNIVERSE` is evaluated before the corpus sees it, and `leg_argv` never passes `--universe`. A tg2 probe would load the tg1 universe.
- **Change:** define `grader_timeout_s` per language as a whole-grade bound: the sum of step timeouts plus overhead. Make the default universe a corpus property. Add acceptance tests for the join bound against a worst-case grade, and for a probe started with no `--universe`.

## F9 — The A8 HOLD is computed but not surfaced; the A8 section is underspecified
- **Location:** spec "B8 / signals"; `p426_signals.py:1341-1349,1479-1503,1721-1764,1814-1903`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - `kv_flags` iterates only A1, A5 and A7. The `render_kv` markdown has no A8 section. `kv_axis_verdict` does not pass `languages`.
  - The HOLD (blocking, C339) would sit in the record but never reach `flags`, the markdown or the recommendation.
  - Cert §8 (S22-P9) wants an A8 decider noise floor (N16 s1 vs s2 discordance) beside X vs N16. `kv_a7` computes this for A7. The spec's A8 section omits it.
- **Scenario:** X shows −22.5 pp on Rust. The A8 record says `hold: true`, the signals sheet lists no blocking flag, and the operator-facing text omits it.
- **Change:** state `kv_flags` (loss, undecided, interaction, HOLD, size warnings for A8), the `render_kv` section, `kv_axis_verdict(languages=…)`, and the noise floor. Test that a −22.5 pp language produces a blocking flag in `flags` and in the rendered markdown.

## F10 — The C331 (3) re-check has no way to apply "the stricter α"
- **Location:** spec "Settled constraints" and "Freeze / sequencer"; `m76_sim.py:689-766`; `m76_rule.py:620-650`; `p426_signals.py:1703-1705`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - `m76_sim.recheck(axis, n16_rows, x_rows, …)` needs both arms' screen rows. It estimates the pass rate m̂, the discordance D̂ and, with k ≥ 2 only, the concentration κ̂. The spec says "pass-rate spread" and "nuisance only".
  - With the k=1 screen, κ̂ is unidentified and is not treated as "outside".
  - `recheck` writes `recheck-A8.json` into the committed B7 report directory by default.
  - `axis_verdict` takes α only from the committed plan. It has no α argument; only a `report=` file that would need a hand-built `alpha_star_fixed`.
  - Signals refuse any input not covered by B8, and the recheck record is not a B8 input.
- **Scenario:** the sequencer runs the re-check and finds it outside the grid. The verdict still uses 0.001, so "the stricter α applies" is silently not implemented.
- **Change:** state the module, call, row source (strict, DNF = 0), output location and the stop-or-continue rule when `operator_review`. State how the applied α reaches the verdict, with B8 or the signals carrying the record. Add `m76_sim` and `m76_rule` to scope if that needs a parameter.

## F11 — Q1 (make-up legs) is open, and the "as tg1" recommendation has no consumer
- **Location:** spec "Open questions" Q1; `p426_verify.py:39,2004`; `p426_signals.py:1767-1798`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - Every interface in the spec (attempt regex, leg names, pair names, B8 sessions) excludes make-up, while Q1's recommendation includes it.
  - The lever-kv B8 reads only s1, s2, … plus pilot and reload. `compute_kv` and `_kv_a7_section` never read make-up rows.
  - C343 (3) already scores a remaining DNF as 0. A make-up leg adds hours (a tg2 item can run 61 min) and cannot change the A8 verdict.
- **Change:** resolve Q1 in the spec. My recommendation is no make-up legs for tg2. Keep `MAX_DNF` as a systemic cap, and consider scaling it for 80-slot legs. Record the cost reasoning.

## F12 — Interface names left to the implementer cannot be tested blind
- **Location:** spec "Chain" ("the implementer states which"), "Probe", "Settled constraints".
- **Severity:** major (ambiguity). **Evidence:** confirmed.
- **Problem:**
  - The chain entry is `run_tg1_chain.py --corpus tg2` or `run_tg2_chain.py`. `leg_argv`, `CHAIN_ENTRY`, `HELP_ENTRIES`, `ENTRY_POINTS` and `CORE_SPECS` embed the entry name, and a separate test-writer cannot write the argv golden.
  - The argv head for smoke and screen is undefined, because `mode` allows pilot, chain and makeup only.
  - The draw seam is unnamed. L20 asked to "name the draw seam or drop it"; `chain_core.py:1223` still reads an unparsed `a.tg2_draw`.
  - L6 (an independent pin of the draw and universe sha) is adopted in the ledger. The spec still says "sidecar sha256", the trust root that L6 called insufficient.
  - L8 (the corpus root from the corpus seam) is adopted. The spec has no `source_root` / `polyglot` seam for `tg2_materialize`.
  - `--tg1-inject` and the `$STACK_WORKDIR/m62/inject/` out-path are unaddressed for the tg2 positives.
- **Change:** name the entry, the argv per leg kind, the draw seam and where the independent sha pin lives. Name the corpus root seam and the inject out-path.

## F13 — Harvest rules are partly redundant and partly missing
- **Location:** spec "Harvest"; `p426_harvest.py:309-321`.
- **Severity:** minor. **Evidence:** confirmed.
- **Problem:**
  - Already classified: `phases.json`, `index.json`, `report.json`, `report.xml` and `junit-*.xml` under the evidence suffixes; `.tg2-registry/*.json` (main) and `.tg2-list/*.out|.err` (evidence) under `grading-private`.
  - Actually unmatched: `<step>.stdout`, `.stderr`, `.inspect`, `.inspect.err`, and `<tag>.out|.err` under `<item>.grades/seq-N/`.
- **Change:** list exactly those unmatched names. Decide whether `.tg2-registry/*.json` (docker bookkeeping) should be main. Test with a fixture from one real grade per language.

## F14 — "tg1 byte-identical" cannot hold literally for rows
- **Location:** spec acceptance criterion 1; `identity_closure.py:116-126`; `tg1_runner.py`.
- **Severity:** minor. **Evidence:** confirmed.
- **Problem:** `probe_code_sha256` is a sha over the probe's import closure, which includes `arm_runner`, `provenance`, `arm_opencode` and `run_config`, all of which the spec changes. M65 T14 / C178 accepted that a core change rotates the tg1 identities. Rows and `chain.json` carry these shas.
- **Scenario:** the test-writer's golden of tg1 rows from the baseline fails after the first core edit.
- **Change:** define "byte-identical" as plan, argv, B8, signals and rows excluding the closure-derived identity fields. State that tg1 identity shas rotate, and what that means for A7 legs already run.

## F15 — Acceptance criteria miss the seams above
- **Location:** spec "Acceptance criteria".
- **Severity:** minor. **Evidence:** hypothesis (what the tests should cover).
- **Problem:** criterion 1 lists mapping, dossier, pilot gate, walls, harvest, B8 and the A8 section. It does not cover:
  - **Chain start and validation:** a tg2 leg start under mtp against the committed registry; `validate_leg` on a tg2 manifest; the A4 gate carrier; the docker gate.
  - **Schedule and verification:** planned-slot readers on the tg2 schedule shape; the tg2 language order and reload shape; B8 on a smoke attempt and on the chosen namespace.
  - **Timeouts and mapping:** the grade-join bound; an out-of-universe failing leaf.
  - **Verdict path:** the HOLD flag in `flags` and in the render; the α path from the re-check.
- **Change:** add these as red-first cases.

## Scope request — A8 panel packet and the "pending subjective review" label
Cert §7 (B4) lists "the A8 panel packet (task, final tree diff, transcript summary) as tg1's". M65 v5 says every tg2 report is labelled "pending subjective review" until the panel has run. B4b's spec says nothing on either, in or out. State it either way. If deferred, require the signals' A8 section to carry the pending label.

## Could drop
- **Make-up legs** (F11).
- **The screen's re-run of its 40 items.** The screen shares seed 1001 and the nested items with decider s1 (about 3–4 h GPU per arm). The screen is settled by C338, so this is an observation only.