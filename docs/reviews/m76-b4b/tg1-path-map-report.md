# tg1's real end-to-end path (P426 Wave 2, lever kv) — research map for M76 B4b (Explore agent, 2026-11-15)

Facts only; file:line at stack `1a96b854` (S23-P88 then touched only `bench/m76_ids.py`); paths relative to `benchmark/`.

Map of tg1's real end-to-end path, P426 Wave 2, lever kv (M76). Paths are relative to benchmark/. No tg2 runner, corpus or chain entry exists yet: there is no `bench/tg2_runner.py` and no `bench/corpus_tg2.py`.

## 1. Probe: generation and grading
- **Entry:** `run_tg1_probe.py`.
  - `_core.bind(globals())` at :21.
  - argparse at :54-94, notably `--scaffold choices=["opencode-v2-web-tg1"]` (:59) and `--lang choices=["python","go","rust","java","javascript"]` (:63). There is no `cpp`.
  - `--evidence p426` (:81) and `--attempt` / `--attempt-rerun-index` / `--invocation-nonce`.
  - `tg1_runner.main(sys.modules[__name__], a)` at :109.
- **`bench/tg1_runner.py`:**
  - `TG1_POLICY = rc.PolicyTemplate(config_id="tg1", langs=("python","go"))` (:41).
  - `TG1_P426_EVIDENCE` (namespace `opencode_transcripts`, `final_tree=True`, `item_barrier="on"`) at :45.
  - `_corpus()` builds `corpus_tg1.Tg1Corpus(universe or core.DEFAULT_UNIVERSE)` (:61).
  - `main` calls `core.main(p, ao.OpencodeArm(p, mode="tg1", p426=…), …, corpus=…)` (:75-78).
- **Generic core, `bench/arm_runner.py`:**
  - `DEFAULT_UNIVERSE = benchmark/m62/universe.json` (:50).
  - `main` refuses unless `a.lang in template.langs` (:1008).
  - Default rows path is `results/<model>/<label>.jsonl` (:1098).
  - Evidence dir is `$STACK_WORKDIR/<namespace>/<model>/<out.stem>.<run_id>` (:1101). Per-item evidence is `<evidence_dir>/<lang>__<name>` (:1203).
  - Item loop (:1189-1285): `corpus.prepare`, `corpus.prompt`, `run_item`, then `corpus.changed`, `passed = result.passed and changed` (:1244), then `corpus.final_tree(prepared, <item_evidence>.final_tree)` (:1248).
  - The row dict is built at :1251-1276. One full rewrite of the rows file per item (`pg.atomic_write`); the `.done` barrier comes from `_done_record` (:888).
- **Grading inside `_run_item`** (:401):
  - The grade dir is `<item_evidence>.grades` (:437).
  - Intermediate grades go through `GradeWorker` calling `grade(snap)`, which calls `corpus.grade(…, final=False)` (:464-470).
  - Final grade: `corpus.grade(…, final=True)` (:747). Its `failing` and `tampered` values go to `gate.terminal(...)`.
  - The result dict (:754-792) holds `gate`, `request_usage`, `nonconv_kind=gate.primary`, `converged=gate.primary is None`, `nonconv_flags`, `test_modified`, `passed`, `rc`, `wall_s`, `prompt_date*`, `session_id`, `termination`, `tmp_*`, `grade_reports=grade_reports(keep)`, `grader_mem_kill`, `grader_oom`, and optionally `receipts`, `task_tokens` and `compaction`.
  - `grade_reports` (:105) reads `seq-*/index.json` and returns `{boundary, seq, final, outcome, artifacts}`.
- **Row extra fields:** `bench`, `schema_version=3`, the carrier fields (`scaffold`, `carrier_source*`, `opencode_bench_config_sha256`, …), `id`, `model`, `sample=0`, `passed`, `acc`, `file_changed`, `worker_before`, `worker_after`, `stop_reason`, and the `row_fields` (`opencode_version`, `opencode_rc`, `events_path`, `datefreeze_path`, `transcript_path`, `stderr_path`, `evidence_sha256`; arm_opencode.py:347).
  - Also `generation_identity_sha256`, `arm_identity_sha256`, the metrics, `sampler_seed`, `seed_base`, `overlay_sha256`, `arm`, `config_id`, `epoch_id`, `snapshot_sha256`, `token_accounting`.
  - `final_tree={manifest, manifest_sha256, files, missing}`.
- **Corpus contract:** `bench/corpus.py` defines `PreparedItem`, `GradeOutcome(failing, leaves, tampered, outcome∈{model, infrastructure}, resources={grader_mem_kill, grader_oom}, phases, reports)` and `FinalTree`.
- **`bench/corpus_tg1.py`:**
  - `SCAFFOLD`, `EXCLUDED={"go/counter"}`, `languages=("python","go")`, `needs_docker = lang=="go"`.
  - `grade()` calls `sg.grade(...)` from structured_grade (:142-157); a tampered tree calls `sg.write_receipt(...,"tampered")`.
  - `final_tree` writes `objects/<sha>` plus `manifest.json` (:164).
  - `identity()` carries `grader_version=sg.VERSION` and `sg.TIMEOUTS`.
- **`bench/structured_grade.py`:**
  - `VERSION="m62-structured-v3"`, `TIMEOUTS={"python":300,"go":180}` (:19-20).
  - Raises if `lang not in ("python","go")` (:283).
  - Writes `<keep>/seq-%04d/` (:295). Files are `report.xml`, `stdout.txt`, `stderr.txt` (python) or `go.jsonl`, `go.stderr` (go), plus `index.json` (:300, `_write_index` :247).
- **Scaffold and data binding:** `bench/arm_opencode.py`.
  - `TG1_LABEL`, `CARRIER=benchmark/opencode_bench_v2_web_tg1.json`, `PLUGIN=toolbounds.js`, `DATEFREEZE_PLUGIN` (:44-47).
  - `GENERATION_DATA` (:51-56) = toolbounds.js, noretry.js, datefreeze.js, opencode_bench_v2_web_tg1.json.
  - `GENERATION_FIELDS` (:58).
  - `probe_code_sha256 = ic.closure_sha256(entry, REPO, data=GENERATION_DATA)` (:333).
  - The plugins are copied into the run dir (:409-414). `verify_env` / `discover` pass `scaffold=TG1_LABEL` to `provenance.opencode_v2_env_check` / `opencode_v2_destination` (:435, :458). provenance.py branches on that literal at :2017, :2026, :2038, :2095, :2113 and :2149.
  - Other copies of the label: `chain_ops.SCAFFOLD` (:20), `run_config.SCAFFOLD_TG1` (:19), `row_scores.py:43`.

## 2. Chain
- **`chains/c147/run_tg1_chain.py`:**
  - `LANGS=("python","go")` (:49). `SEEDS_M76 = schedules.TG1_SEEDS_M76`, which adds `s3=3003`.
  - `CORE_SPECS` (:61) holds the probe entry, `probe_data` (equal to `GENERATION_DATA`) and the chain entry. `campaign_core.closure_shas` (campaign_core.py:61) checks them against `--campaign-core`.
  - `tg1_config` (:82): `config_id = rc.P426_CONFIG_ID` ("tg1-p426"), `ArmBinding(arm="oc", label=SCAFFOLD)`, `schedule builder "tg1"` with `params` `seeds`, `legs`, `p426` and `m76_s3`, `transport_policy="p426_continue"`.
  - `Chain.p426_arm_name` returns the kv arm (:118). `p426_after_load` checks the KV argv and receipt, writes `receipt.json`, then runs the pair gate `pr.kv_pair_problems` (:122-161).
  - `load_universe` hard-codes `{"python":[], "go":[]}` from `m62/universe.json` (:165-172).
  - `ATTEMPT_NAME` regex `^.+\.a[1-9][0-9]*$` (:239). Flags `--lever kv`, `--kv-arm {n16,x,v}` (:327-329).
- **Probe argv:** `chain_core.build_cmd` (chain_core.py:277).
  - Passes `--model --items --lang --seed-base --out --scaffold --expect-items --a4-v2-receipt --sampling-profile deployed --cancel-file --manifest-ack`.
  - Optionally `--limit`, `--universe`, `--frozen-prompt-date`, `--invocation-nonce`, `--attempt`, `--attempt-rerun-index`, `--evidence p426`, `--inject-stall-*`.
- **Where rows land:**
  - `invocation_paths` (:1911) gives `<out-root>/<session>/` + `cr.rows_name(stem, li, phase, n)` = `<stem>.L<leg>.<phase>.a<n>.jsonl` (chain_rows.py:78), with a `.manifest.json` beside it.
  - `stem = <model>.<session>.opencode_<lang>` (schedules.py:53, :170). Make-up legs use `<model>.makeup.opencode_<session>_<lang>`.
  - Slot = `<config_id>|<arm>|<model>|<session>|<lang>|<item>` (plan_tg1, :1253). `slot_file` maps `|` to `__` and `/` to `--`.
- **Transport DNF:** `handle_p426_incomplete` (:2580-2660).
  - Uses `ci.classify_p426_dnf_cause`, `MAX_P426_DNF`, and the proper-prefix rule.
  - Writes the record `{slot, item, session, language, seed, arm, pick, load, attempt, invocation_file, abort{cause, error, evidence}, item_record="items/<slot_file>.dnf.json", …}`, sealed, into `self.p426_dnf` and `p426_ledger(kind="dnf")`.
  - Sidecar: `<out-root>/<session>/p426_dnf/<slot_file>.json`.
- **Make-up:** `schedules.tg1_makeup` (:262) / `makeup_canonical` (:241), with `MAKEUP_LANG_ORDER{s1:(python,go), s2:(go,python)}` and `_M76` (+s3) at :235-238. Dispatched from `chain_core.tg1_schedule` (:1162-1172).
- **P426 mode gating:** `p426` means `transport_policy=="p426_continue"` (:810). `freezes_schedule` is true for builder `blocks`/`tg2_tier` or `config_id==P426_CONFIG_ID` (:816).
- **Docker gate:** `needs_docker` defaults to `lang=="go"` (:328).

## 3. Sequencer and freeze
- **`bench/p426_wave2.py`:**
  - `kv_legs(ref,test)` (:118) names legs `tg1-m76-<arm>-<session>` (pilot, s1..sK from `kv_a7_sessions()`, reload, makeup, rehearsal).
  - `out_root_of` gives `<out_base>/<name>.a<n>` (:169).
  - `leg_argv` (:174) runs `run_tg1_chain.py <head> --p426 --models ENTRY --predictor mtp --out-root --probe-code-sha --policy-sha --frozen-prompt-date --campaign-core <arm>_commit --frozen-record [--lever kv --kv-arm] [--pair-receipt] [--occurrences]`.
  - `deadline_s` uses only `w_python_s` / `w_go_s` (:213). `LANG_ORDER` (:52).
  - `classify_leg` (:264) compares the ledger with `planned_slots` and allows at most `MAX_DNF=2`.
  - `ensure_amendment` (:803) calls `fz.write_amendment` (the pilot gate runs inside it). `ensure_kv_dossier` (:687) calls `pr.write_kv_dossier`.
- **`bench/p426_freeze.py`:**
  - `cmd_v8` (:649), CLI `bench.p426_freeze v8 --lever kv --pair ref,test --arm-worktree …`, writes `kind="p426_v8_base"`.
  - It contains `pilot_deadline_s = deadline_formula({"python":5}, walls)`, `settle_bound_s`, `<arm>_commit`, `lever`, `arms`, and `IDENTITY_KEYS` (probe_code / scaffold_policy / generation_identity sha256).
  - Its inputs are `ops.historical_walls()` (`--historical-walls` JSON: `w_python_s`, `w_go_s`, `max_request_elapsed_s`) and `ops.build_inputs()`.
  - `write_amendment` (:801) writes `kind="p426_timeout_amendment"`. `w_python_s = max(pilot row wall_s (pilot_walls :202 reads rows of COUNTED invocations), historical)` and `w_go_s = historical` only.
  - Deadlines: `deadline_formula(ITEM_COUNT={"python":22,"go":21}, w)` for s1, s2 and s3; reload uses `{"python":5}`.
  - `deadline_formula` refuses languages outside `("python","go")` (:84).
  - `pilot_gate_problems` (:723) expects leg name `kv_pilot_leg(arm)` = `tg1-m76-<arm>-pilot` and `PILOT_N=5`.
- **Pairs and dossiers:** `p426_receipt.PAIRS=("r1","pilot","s1","s2","reload","makeup")`, `KV_DOSSIER_PAIRS = PAIRS+("s3",)` (:323-324). `write_kv_dossier` (:480) writes `pairs/<pair>__<ref>-a<n>__<test>-a<m>.json`.

## 4. Harvest: `bench/p426_harvest.py`
- **Destination:** lever kv publishes under `benchmark/results/m76/<namespace>` (:208).
- **Run discovery:** `_manifest_runs` (:502) takes `run_id` from every `*.manifest.json` and globs `opencode-probe*/run-<id>` (run) and `opencode_transcripts/*/*.<id>` (evidence).
- **`classify` (:261), in order:**
  1. Anything under `*.final_tree/`: `manifest.json` is main, `objects/<x>` is evidence.
  2. Leg root, top level: `LEG_MAIN` (leg, chain, schedule, receipt, watch.jsonl, log_bounds) is main. `RUNLOG.md`, `STOP` and `RAW_SUFFIXES` (`.log .txt .stdout .stderr`) are evidence.
  3. Leg root, subdirectories:
     - `tmp/mlx-manager-logs/*.log` is evidence; `tmp/uv-*.lock` is excluded.
     - `quarantine/` and `archive/` are evidence.
     - `items/*.json` is main.
     - `a4/*.json` is main; other `a4/` files are evidence.
     - `<session>/`: barrier files (`.itemN.ready|go|done|continue|stop`) and ACK/CANCEL are evidence; `*.manifest.json`, `.json` and `.jsonl` are main; raw files are evidence.
     - `<session>/p426_dnf/*.json` is main.
  4. Run dir:
     - `home`, `data`, `state`, `cache` and `tmp` are excluded.
     - Under `grading-private/`, `.json/.diff/.patch` are main and `.log/.txt/.out/.err` are evidence.
     - `cfg/opencode/opencode.json` and `cfg/opencode/plugins/*.js` are evidence.
  5. Evidence dir: `go.stderr` only as `<x>.grades/seq-\d+/go.stderr` (P587). Otherwise a file is evidence only if its name ends in `EVIDENCE_SUFFIXES` (`.jsonl .json .txt .log .html`) or `.xml`.
  6. Any file with no matching rule fails the harvest.
- **Row reference checks:** `ROW_REFS` (:225) and `_check_row` (:633) check `events_path`, `stderr_path`, `transcript_path`, `datefreeze_path`, `toolwindows_path` against `evidence_sha256`, plus the `final_tree` manifest and its objects.

## 5. Verify (B8): `bench/p426_verify.py`
- **Attempt names:** `KV_ATTEMPT_RE = ^tg1-m76-(n16|x|v)-(pilot|s1|s2|s3|reload)\.a(\d+)$` (:1377), checked by `_kv_check_member` (:1974). The mtp lever uses `ATTEMPT_RE = ^tg1-p426-(off|on)-…` (:44).
- **`verify_a7_kv` (:1987):** reads `wave2/run/v8_base.json` (must have `lever=="kv"`) and `sequence.json` (`_sequence_pair`). It loops over `kv_sessions()` (`p426_plan.kv_a7_sessions`, from `m76_rule.axis_plan("A7")`) plus `SESSIONS_DIAGNOSTIC=("pilot","reload")`.
- **`_kv_load_attempt` (:2050):** reads `leg.json`, `chain.json`, `HARVEST.json` and `schedule.json`.
  - `session_rows` takes `<attempt>/<session>/*.jsonl` (not `*.dnf.*`) and requires a `<lang>/<item>` id and an int `sampler_seed`.
  - `load_dnf` takes the `chain.p426_dnf` records of the session that have no row.
  - `check_planned` requires rows + DNF to equal the schedule's slots exactly (`planned_slots` :165 sums `invocations[].names` / `expect`).
  - `load_items` needs one `items/*__<session>__<lang>__<item>.json` per row; a DNF slot needs none.
- **Pair checks:** `pair_keys` (:371) checks seed equality and identity via `harvest_manifests` (:331). The pattern there is `<prefix>wave2/<attempt>/evidence/<run>/<lang>__<item>.final_tree/manifest.json`, compared with `final_tree.manifest_sha256`. Provenance uses `kv_a7_provenance_reasons` (:1726).

## 6. Signals: `bench/p426_signals.py`
- `_strict(row)` (:105) is 1 only if the row exists, `passed is True` and `converged is True`. A missing row (DNF) is 0.
- `_arm_quality` (:121) counts `nonconv_kind`, using `"transport_dnf"` for DNF slots.
- `compute_kv` (:1606) requires a lever-kv B8 record and calls `_kv_a7_section(rows_root, b8["axes"]["A7"], ref, test)` (:1695).
- `_kv_a7_section` (:1767): every planned session must be B8-accepted, otherwise the result is "incomplete". It re-loads attempts with `V._kv_load_attempt` and takes strict per (item, session) over the accepted keys, so a DNF is a strict fail. Item sets must be equal across sessions. Result goes to `kv_a7(...)`, plus the `_speed` decode.

## 7. What exists for tg2
- **`bench/tg2_grade.py`:**
  - `VERSION="m65-tg2-v2"`, `IMAGE_TAG`, `LANGS=("rust","java","javascript","cpp")`, `TIMEOUT_FLOOR=180`.
  - `Tg2Grade` (:917) has `lang, outcome, leaves{id:bool}, all_failed, phases, artifacts, image_id, version, reason, reason_detail, stripped, cleanup_problems, tamper_reasons, optional`, plus `.passing` and `.failing(universe)`.
  - Outcomes: parsed, compile_failure, timeout, oom, mem_kill, crash, storage_cap, tampered. `TransportAbort` means infrastructure.
  - Entry points: `grade_item(lang, work, slug, private, *, prepared, solutions, prepared_cargo_toml, extra_crates, keep, seq, boundary, final)` (:961) and `grade(...)` (:980).
  - Files in `<keep>/seq-%04d/`:
    - `<step>.stdout` / `<step>.stderr` for each step: setup-image, setup-launch, preflight, compile, execute, collect.
    - `<step>.inspect` / `<step>.inspect.err`.
    - `<tag>.out` / `<tag>.err` for every docker bookkeeping call. Tags: plan-*, volume-*, own-*, holder, own-holder, `<step>-pre`, `-n`, `-rm`, `-v`, `-x`, cl-holder, cl-*, rm-*, ls-*.
    - `junit-NNN.xml` (java), `report.json` (js), `report.xml` (cpp).
    - `phases.json` and `index.json` (via `structured_grade._write_index`).
  - Under private: `.tg2-registry/*.json` and `.tg2-list/ls-ps|ls-vol.out|.err`.
- **`bench/tg2_materialize.py`:** `LANGS`, `Plan(lang, slug, solutions, tests, mapping, config)`, `prepare_tree`, `apply_reference`, `read_plan`, `SCAFFOLD` / `ITEM_SCAFFOLD` allow-lists.
- **`m65/tg2_draw.json`:**
  - Keys: `languages`, `needs_operator_acknowledgement` ({}), `seed` (6501), `tiers` ({screen:10, decider:20}), `universe_sha256` (ff7657…).
  - Each language has `N_actual` / `permutation` / `screen` / `decider`; `N_actual` is cpp 26, java 45, javascript 48, rust 30.
  - Sidecar `tg2_draw.json.sha256` = 8eb9d8ef…f2c3. Also present: `m65/tg2_universe.json` (+ .sha256).
- **`bench/schedules.py`:**
  - Constants `TG2_SEED`, `TG2_TIERS`, `TG2_SESSIONS{screen:(s1,), decider:(s1,s2,reload)}`, `TG2_RELOAD_ITEMS=5` (:47-50).
  - Functions `draw_sha256_of`, `_tg2_check_draw`, `_tg2_items`, `tg2_tier` (builder `tg2_tier`, seeds = `TG1_SEEDS`, no s3), `tg2_prefix_names`, `check_tg2_membership` (:292-360).
  - `chain_core` already handles builder `tg2_tier`: `build_schedule` / `tg2_draw_doc` (`a.tg2_draw`) / `verify_schedule` / `plan_tg2` (:1203-1312). There is no P426 / makeup / m76_s3 path for it.
- **Spec `docs/specs/m65-tg2-corpus.md` :126-134:**
  - Step 3: "`bench/tg2_runner.py` (`--lang` rust / java / javascript / cpp under `opencode-v2-web-tg2`) and chain runner tg2 LEGS as a configuration of the shared core (T14 amended, P371); final solution trees retained for the panel (T22)."
  - Step 4: "Injected positives (stall / loop / alloc) on one item per language; four-language `--smoke`; sizing report; then the operator's chain go."

## tg1-specific values hard-coded that a tg2 corpus must parameterize
1. Probe argparse: `--scaffold` choices (run_tg1_probe.py:59); `--lang` choices lack `cpp` (:63).
2. `TG1_POLICY.langs=("python","go")`, `config_id="tg1"` (tg1_runner.py:41); `arm_runner` refusal text (:1009).
3. `arm_runner.DEFAULT_UNIVERSE = m62/universe.json` (:50); `m62.universe_preflight` in corpus_tg1.
4. Label and carrier: `TG1_LABEL`, `CARRIER`, `GENERATION_DATA` (arm_opencode.py:44-56); `scaffold=TG1_LABEL` checks (:435, :458); provenance.py literal branches (:2017-2149); `chain_ops.SCAFFOLD`; `run_config.SCAFFOLD_TG1`; `row_scores.py:43`.
5. `CORE_SPECS.probe_entry` / `probe_data` and `NAMED_LIFECYCLE` (run_tg1_chain.py:56-64); `HELP_ENTRIES` (p426_freeze.py:47); `CHAIN_ENTRY` (p426_wave2.py:56, p426_freeze.py:35).
6. Chain `LANGS`, `load_universe` dict (run_tg1_chain.py:49, :165); `needs_docker` default `lang=="go"` (chain_core.py:328; corpus_tg1:81).
7. `P426_CONFIG_ID="tg1-p426"` gates `freezes_schedule` and the slot prefix (run_config.py:37; chain_core.py:816); P426 is tied to builder `"tg1"` (`tg1_schedule`, `tg1_makeup`).
8. Schedule language orders: `tg1_legs_table` s2 reversal; `MAKEUP_LANG_ORDER[_M76]` (schedules.py:235-238); wave2 `LANG_ORDER` (:52); rehearsal `stall-kill` picks the first `python` item (chain_core.py:1179).
9. Wall keys `w_python_s` / `w_go_s` / `max_request_elapsed_s` (p426_freeze.py:678, :826-832; wave2 :213); `deadline_formula` accepts only python/go (:84); `ITEM_COUNT={"python":22,"go":21}`; `pilot_deadline_s` and the reload deadline assume `{"python":5}`; `REHEARSAL_R1_ITEMS`; `r2_slot_problems` requires a Go slot (:308).
10. Leg and attempt names: `tg1-m76-<arm>-<session>` (wave2 `kv_legs` :129; `kv_pilot_leg` freeze :100); `tg1-p426-*` (RUN_LEGS, `pilot_gate` want_leg :740); verify `ATTEMPT_RE` (:44) and `KV_ATTEMPT_RE` (:1377).
11. Session sets: `TG1_SEEDS(_M76)`, `KV_SESSIONS`, `PAIRS` / `KV_DOSSIER_PAIRS`, `SESSIONS_DIAGNOSTIC`, `kv_a7_sessions` (A7 = tg1 axis in `m76_rule`); tg2 uses `TG2_SESSIONS` (no s3, no pilot).
12. Harvest rules: only `go.stderr` is special-cased in `.grades/seq-N/`, and the evidence suffixes exclude `.stdout`, `.stderr`, `.inspect`, `.err` and `.out`. Most tg2 per-grade files would therefore hit "no harvest rule matches". Run/evidence globs `opencode-probe*/run-*` and `opencode_transcripts/*/*.<run_id>` assume the opencode namespace.
13. Grader binding: `structured_grade.TIMEOUTS` / `VERSION` / language check, and `grade_join_timeout_s(sg.TIMEOUTS)` in the arm identity (arm_opencode.py:310-312). tg2 has `TIMEOUT_FLOOR` and `Tg2Grade.failing(universe)` / `.passing` with `optional` leaves, and needs `slug`, `solutions` and `prepared_cargo_toml`.
14. `EXCLUDED={"go/counter"}`, the tg1 prompt text and `INJECT_ADDENDA` (corpus_tg1.py); `--tg1-inject` flag name and the `m62/inject/` out dir (arm_runner.py:1038).
15. Stem `opencode_<lang>` (schedules `flat_stem`, `_tg1_leg`); `harvest_manifests` regex `<lang>__<item>.final_tree` (generic, but relies on the per-item evidence naming at arm_runner.py:1203).
16. Results roots: `M76 = benchmark/results/m76`, `KV_REPO_PREFIX`, `WAVE="wave2"`, `NAMESPACE_RE` (harvest :204, verify :1361-1364).
