# Implementer report: M76 B4b-2, the A8 (tg2) consumers (spec v1.5, §1–§8 as amended by §9)

## Files

Changed:
- `benchmark/bench/p426_verify.py`: adds the `KV_AXES` table and threads the namespace and worktree prefix through the KV A7 helpers. Adds the fail-closed per-row final-tree rule (`final_tree_reasons`, applied to A7 kv and A8), `kv_normalise` / `kv_provenance_reasons` (the A7 names are kept as aliases), `verify_a8_kv` with its A8 loader, and `check_b8_a8`. The CLI (`--lever kv all --pair n16,x`) now also writes `B8-A8.json` beside `--out`.
- `benchmark/bench/p426_signals.py`: adds `compute_kv(..., b8_a8=None, b8_a8_sha256=None)`, `_kv_a8_section` with its descriptive helpers, and A8 plus `hold` in `kv_flags`. The `## A8 tg2` section is rendered after A7, the decode loop has an explicit A8 case, there is a B8-A8 header line, and the CLI takes `--b8-a8`.
- `benchmark/bench/p426_panel.py`: `kv_members(..., a8_sessions=None)`; A8 uses the `code` rubric; adds `KV_INPUT_SOURCE["A8"]`, `kv_a8_member_sessions`, `kv_a8_context`, `a8_corpus`, `a8_prompt`, `a8_prompt_check`, `_a8_packet` (with `_a8_start_tree`, `_a8_diff`, `_a8_response`) and `a8_leak_report`. Wires A8 into `kv_export`, `kv_panel_members` and `kv_expected_members`, and adds `kv-export --b8-a8`. `_a7_final_tree` now reads `ctx["namespace"]`.
- `benchmark/bench/tests/test_m76_b3_impl_a7.py` (an existing test, §3.3): the `KVWorld` fixture rows now carry `final_tree.manifest`, the run-directory path the real rows carry. Without it every fixture row is rejected under §3.3.
- `benchmark/bench/tests/test_s26_p15_rerun_pairs.py` (an existing test, §3.3): the `_rerun` helper's a2 copy now publishes HARVEST paths under a2, as the real rerun did. Before, it named a1's paths, and §3.3 now rejects that ("0 HARVEST main final-tree manifests").
- `benchmark/bench/tests/test_m76_b4b1_impl_golden_tg1.py` (an existing test, §3.3): one allowed difference was added, in the same way as the existing S27 allow-list. The `.b8.inputs.*.jsonl` shas of the KVWorld rows files move because the rows gained the manifest path. The baseline golden fixture was not re-recorded.

Added:
- `benchmark/bench/tests/test_m76_b4b2_impl_world.py`: the synthetic `wave2.tg2` world for (N16, X). It uses the real pinned draw and `schedules.tg2_p426` and includes the S27 slot records. One self-test.
- `benchmark/bench/tests/test_m76_b4b2_impl_verify.py`: B8-A8 (§3, §5, §7.4, §9).
- `benchmark/bench/tests/test_m76_b4b2_impl_signals.py`: the A8 section and its flags (§4, §7.4, §9.5–§9.7).
- `benchmark/bench/tests/test_m76_b4b2_impl_panel.py`: the A8 panel (§6, §7.4).
- `benchmark/bench/tests/test_m76_b4b2_impl_golden.py`: §7.1, §7.2 and §7.3 on `main`'s committed records.
- `benchmark/bench/tests/fixtures/m76_b4b2_impl/` was not created: the world is generated in code and no data fixture was needed.

The CLI that writes B8 is `bench.p426_verify` `main`; `B8-A8.json` is written there.

## Commands and results (via `../fe_test.sh stack …`)

1. `test_m76_b3_*` (all 25 files): **3 failed, 589 passed**. Failures, verbatim:
   - `FAILED bench/tests/test_m76_b3_impl_golden_mtp.py::test_mtp_golden_is_meaningful`
   - `FAILED bench/tests/test_m76_b3_impl_golden_mtp.py::test_mtp_golden_component[leg_checks]`
   - `FAILED bench/tests/test_m76_b3_impl_golden_mtp.py::test_mtp_golden_committed_b8_and_signals_regenerate`
   - Errors: `subprocess.CalledProcessError: Command '['git', …, 'show', 'f2b61127c55f0436b6c6c777bec5384ce004d62d:main_models.yaml']' returned non-zero exit status 128` and `REFUSED: frozen stack_head_on f2b61127c55f0436b6c6c777bec5384ce004d62d does not resolve: git rev-parse failed`.
   - `git cat-file -t f2b61127…` in this clone returns `fatal: git cat-file: could not get object info`: the commit is not in the clone.
   - The failing path is the P426 mtp Wave 1 verifier (`verify_wave1` / `verify_all`), which I did not change. I did not run these at the baseline, so "pre-existing" is inferred from the missing object, not demonstrated.
2. `bench/tests/p613 bench/tests/p613s2 bench/tests/p613s3 bench/tests/p613s4 bench/tests/test_p426_panel.py`: **883 passed, 22 skipped, 0 failed**.
3. The other existing tests that import the touched modules: `test_m76_b4b1_fe_chain`, `test_m76_b4b1_fe_golden_tg1`, `test_m76_b4b1_impl_golden_tg1`, `test_m76_b7_impl_sim`, the four `test_m76_b8_kinds_*` files, `test_s26_p15_rerun_pairs`, `test_s26_p17_panel_family_token`, `test_t3_frozen_panel`, `test_t3_frozen_support_check` and `test_t3_wave1`. Result: **1 failed, 425 passed, 1 skipped**.
   - `FAILED bench/tests/test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical` with `REFUSED: frozen stack_head_on f2b61127c55f0436b6c6c777bec5384ce004d62d does not resolve: git rev-parse failed`. It is the same missing commit.
   - Skip: `test_m76_b8_kinds_fe_wave1.py:522: commit f2b61127… is not in this checkout's object store (the mtp B8 needs it)`.
4. My family (the 5 `test_m76_b4b2_impl_*` files): **94 passed, 1 skipped**. Skip: `test_m76_b4b2_impl_golden.py:127: the tg2 pilot pair's evidence objects are not on origin/evidence in this clone`.
   - `test_b2_*`: no `test_b2_*` file imports `p426_verify`, `p426_signals` or `p426_panel`, so none ran.

## Acceptance items

- **§7.1** (no B8-A8 → `B8.json`, `SIGNALS.md` and `SIGNALS-partial.md` byte-identical): `test_m76_b4b2_impl_golden.py::test_b8_regenerates_byte_identical` and `::test_signals_without_b8_a8_are_byte_identical[False-SIGNALS]` / `[True-SIGNALS-partial]`. The `.md` and `.json` files are compared byte for byte. **PASS**.
- **§7.2** (with B8-A8: `B8.json` identical, and only the A8 section and header differ):
  - `::test_b8_regenerates_byte_identical` (the CLI wrote `B8-A8.json` beside it) and `::test_the_cli_writes_b8_a8_beside_b8_bound_to_it`.
  - `::test_with_b8_a8_the_sheet_differs_only_in_the_a8_section` (the projection on the real records).
  - Holm-only change: `test_m76_b4b2_impl_panel.py::test_the_holm_family_adds_a8_and_keeps_the_raw_statistics`.
  - **PASS**.
- **§7.3** (old-identity pilot pair, as a shape check): `::test_pilot_pair_b8_a8_shape`. The pilot is accepted, s1 / s2 / reload are incomplete, all four final-tree shas are matched (none null), latency and re-checks are incomplete, and the javascript row is listed as tampered with its receipt. **PASS**.
  - Provenance: `::test_provenance_passes_on_the_real_tg2_pilot_manifests`. It passes, and every differing key is in `KV_PROVENANCE_WHITELIST`. **PASS**.
  - Prompt check on the pilot export: `::test_pilot_export_prompt_check` **SKIPPED**, because `origin/evidence` has no `benchmark/results/m76/wave2.tg2/` in this clone. The prompt check itself is covered by fixtures (below).
- **§7.4**:
  - Per-row final-tree rule:
    - A8: `test_m76_b4b2_impl_verify.py::test_a8_missing_final_tree_block_is_a_reason`, `::test_a8_no_harvest_match_is_a_reason`, `::test_a8_two_harvest_matches_is_a_reason`, `::test_a8_orphan_manifest_is_a_reason`, `::test_a8_a_discarded_rerun_run_is_never_an_orphan` and `::test_a8_all_dnf_attempt_passes_the_final_tree_rule`.
    - A7: `::test_a7_missing_final_tree_block_is_a_reason`, `::test_a7_no_match_and_two_matches_are_reasons`, `::test_a7_orphan_is_a_reason` and `::test_a7_rows_need_a_run_id_and_an_all_dnf_attempt_passes`.
    - **PASS**.
  - A8 names / namespace / worktree guard: `::test_the_axis_table_names_both_wave2_axes`, `::test_a8_and_a7_member_names_never_cross[4 cases]`, `::test_the_worktree_guard_takes_the_axis_prefix`, `::test_a8_namespace_is_read` and `::test_b8_a8_is_built_only_for_the_tg2_kv_pair`. **PASS**.
  - A partial decider is incomplete, not a refusal: `::test_a_partial_decider_is_incomplete_not_a_refusal` and `::test_a_harvested_but_unpaired_session_is_incomplete`. **PASS**.
  - HOLD at −25 pp is blocking: `test_m76_b4b2_impl_signals.py::test_hold_fires_below_minus_twenty_pp_and_blocks`; exactly −20 pp does not fire: `::test_exactly_minus_twenty_pp_does_not_hold`. **PASS**.
  - DNF = 0: `::test_a_dnf_slot_scores_zero[transport]`. **PASS**.
  - Re-check binding (superseded attempt, missing ack): `test_m76_b4b2_impl_verify.py::test_a_recheck_naming_a_superseded_attempt_refuses`, `::test_an_outside_recheck_without_the_ack_refuses`, `::test_a_review_recheck_needs_the_ack_too`, `::test_the_recheck_binding[seq|report|seal]` and `::test_a_missing_recheck_s2_labels_only_that_recheck`. **PASS**.
  - Reload seed assert: `test_m76_b4b2_impl_signals.py::test_the_reload_control_asserts_equal_seeds`. **PASS**.
  - Prompt check: `test_m76_b4b2_impl_panel.py::test_the_prompt_check_passes_on_the_runners_prompt[quoted|unquoted]`, `::test_the_prompt_check_refuses_a_different_first_user_message` and `::test_the_prompt_check_refuses_an_export_harvest_does_not_bind`.
    - On the real polyglot checkout: `::test_the_real_prompt_and_start_tree_are_the_runners` (prompt = `corpus_tg2.prompt` with H; start tree = `prepare_tree` == `prepared`) and `::test_a_polyglot_checkout_at_another_sha_refuses`.
    - **PASS**.
  - Protected paths, including a grader-accepted `Cargo.toml`: `::test_a_grader_accepted_cargo_toml_is_diffed_as_content`, `::test_a_changed_protected_path_refuses[5 cases]`, `::test_a_cargo_toml_outside_rust_is_protected` and `::test_non_utf8_files_are_listed_by_path_and_size_and_unchanged_files_skipped`. **PASS**.
  - Leak refusal: `::test_the_leak_report_names_patterns_per_item` and `::test_a_leak_refuses_the_member_per_item`. **PASS**.
  - A7 / no-A8 goldens: §7.1 above. **PASS**.
- **§9.7**:
  - A harness DNF scores 0: `test_m76_b4b2_impl_signals.py::test_a_dnf_slot_scores_zero[harness]` and `test_m76_b4b2_impl_verify.py::test_a_harness_dnf_is_a_dnf_slot`. Its sidecar mismatch refuses: `::test_a_harness_dnf_sidecar_mismatch_refuses`. **PASS**.
  - A rerun slot reads its accepted attempt: `::test_a_rerun_slot_reads_its_accepted_attempt`. Two accepted attempts refuse: `::test_a_slot_with_two_accepted_attempts_refuses`. An earlier attempt with no reason is a reason: `::test_an_earlier_attempt_without_a_reason_is_a_reason`. **PASS**.
  - An accounting-fault row keeps its outcome and leaves the decode aggregate: `test_m76_b4b2_impl_signals.py::test_an_accounting_fault_leaves_the_decode_aggregate_and_keeps_its_outcome`, `test_m76_b4b2_impl_verify.py::test_an_accounting_fault_keeps_its_outcome_and_is_listed` and `::test_an_accounting_sidecar_that_does_not_stand_refuses`. **PASS**.
  - The sensitivity line with one faulted item and with none: `test_m76_b4b2_impl_signals.py::test_the_sensitivity_line`. **PASS**.
  - A PAUSED leg is incomplete: `test_m76_b4b2_impl_verify.py::test_a_paused_leg_is_incomplete` (sequence state) and `::test_a_paused_leg_record_is_incomplete` (leg.json). **PASS**.
  - Speed-invalid tiers: `test_m76_b4b2_impl_signals.py::test_a_speed_invalid_leg_labels_its_decode`. **PASS**.
- Also covered:
  - §3.6 plan binding: `::test_a_schedule_off_the_pinned_draw_rejects`, `::test_the_chain_binding_rejects[2]`, `::test_the_reload_key_set_is_the_first_five_of_s1`, `::test_a_harvested_attempt_missing_its_schedule_refuses` and `::test_a_v8_record_that_does_not_verify_rejects_every_session`.
  - §4.2 latency: `::test_the_latency_record` and `signals::test_the_latency_summary_per_leg_window`.
  - §4.4 / §6.1 the B8-A8 check: `::test_check_b8_a8_binds_the_base_b8_and_every_input`, `panel::test_the_export_refuses_a_b8_a8_of_another_b8` and `panel::test_the_a8_member_is_frozen_against_b8_a8_and_selects_on_passed`.
  - §4.1: `signals::test_the_verdict_is_axis_verdict_with_languages`, `::test_a_language_outside_tg2_refuses`, `::test_incomplete_b8_a8_gives_no_verdict_and_no_flag` and `::test_a_rejected_confirmatory_session_is_incomplete`.
  - §4.3: `::test_the_sheet_renders_the_a8_section_after_a7` and `::test_session_interaction_flags_a8`.
  - All **PASS**.

## Not satisfied, and why

- §7.3 "the prompt check passes on the pilot export" did not run. `origin/evidence` in this clone holds only `benchmark/results/m76/wave2/`; the tg2 pilot objects (export, events, final-tree objects) are absent. The test exists and skips with that reason.
- §7.3 also says to run "on the new-identity pilot pair once it is harvested". Per the brief, only the old-identity pair was available.
- §3.1 says "`_sequence_*` stay unchanged". `_sequence_pair_and_superseded` gained an optional `namespace` parameter (default `"wave2"`). It is used only in refusal message text, so A8 refusals name `wave2.tg2/run/sequence.json`. The logic is unchanged and A7's output is unchanged. This is flagged as a deviation from the letter of the clause.

## Choices where the spec leaves room

1. **Orphan exemption (§3.3).** A published manifest under another run id is not an orphan when that run id is in `progress.seen_run_ids` and the item has a non-accepted slot attempt or a DNF record.
2. **Scope of §3.3.** The per-row final-tree rule applies to the KV lever's A7 and A8, not to P426 mtp `verify_a7`, whose committed outputs I did not re-verify.
3. **Refuse vs REASON (§9.3 vs §9.7).** Two accepted attempts of a slot refuse, as §9.7 requires. Other slot anomalies are rule-9.3 REASONs: an earlier attempt that is not a `harness_fault` or has no reason, a rerun index above 1, a row with no accepted attempt, or a row from a file other than the accepted attempt's `invocation`.
4. **Refusals for corrupted or contradictory records.** These refuse:
   - an accounting sidecar that fails `p426_hooks.accounting_problems`;
   - a harness-DNF sidecar mismatch;
   - a re-check with a broken seal, a field mismatch against B8-A8's selection, a `sequence.json` sha mismatch, a simulation-report sha mismatch, or an s1 that is outside / under operator review with no ack;
   - an `exec_latency.json` that is present but unsealed or malformed.

   A missing re-check file, a gate whose sessions have no selected attempts, or a missing latency record gives `incomplete` only.
5. **Simulation report sha (§5).** It is compared with `m76_rule.load_report()`'s sha (the committed report the plan reads).
6. **B8-A8 output.**
   - `inputs` are rows-root-relative (`m76/…`, like `B8.json`).
   - The pinned draw, which is outside the rows root, goes in an extra `repo_inputs` key. `check_b8_a8` re-hashes it against `rows_root/../..`.
   - Extra top-level keys: `version`, `repo_inputs`.
   - Extra per-session keys: `status`, `legs` (started / ended / holds), `faults` (transport / harness DNFs, reruns, accounting faults), `tampered`.
7. **When B8-A8 applies (§3.2).**
   - An absent `wave2.tg2/run/v8_base.json` → not applicable.
   - An unreadable one refuses.
   - The CLI writes `B8-A8.json` only when `--pair` is `n16,x`.
   - Absent `run/` / pair record / attempt directory, or a PAUSED leg (latest `sequence.json` state or `leg.json` state) → that session is `incomplete`.
   - The `v8.arms` check is in place, but `a8_applies` already gates on the pair.
8. **Export equality (§6.2).** The first user message must equal the rebuilt prompt exactly, or the prompt wrapped in one pair of double quotes. That wrapping is what opencode 2.0.20 exports show for tg1 on the evidence ref.
9. **Tampered listing (§9.1).** Every language's final-tampered rows are listed per arm, not only javascript. The listing gives the final report's seq / boundary / final / outcome and its artifact names → sha256 (no paths).
10. **Reload seed assert (§4.2).** Seeds are compared only where both rows exist (a DNF slot has no seed). Any mismatch, in either arm, prints `refused: seeds differ` for the whole control.
11. **Sensitivity faulted set (§9.5).** Reruns, harness DNFs and accounting faults, in either arm, in any confirmatory session. Transport DNFs are not counted, since they are not harness faults. The sensitivity verdict is never a flag.
12. **Speed-invalid tiers (§9.6).**
    - A session is speed-invalid when `leg.speed_valid` is False (ALERT, watcher gaps and off-AC are folded into it by `classify_leg`) or `chain.p426_holds` is non-empty.
    - Accounting-fault items are excluded individually from decode and walls.
    - The labels are `descriptive-invalid (speed tier)`; `_speed`'s `inference` is set False.
13. **Descriptive A8 figures.**
    - Per-language: `m76_rule.loss_bound` at `PER_SESSION_ALPHA` over both confirmatory sessions, with its verdict dropped.
    - Walls: per session and language, the sum of row `wall_s` per arm over items with rows in both arms, plus the ratio X / N16.
    - Latency: rows whose `t` (an ISO `…Z` string or epoch seconds) falls within leg.json `started..ended`. The summary is the medians of fresh / repeat / true ms and the max `threatlocker_cpu`.
14. **Signals record.**
    - `sig["inputs"]` stays B8's.
    - With B8-A8 the record adds `inputs_a8`, the header keys `b8_a8_sha256` / `a8_inputs_sha256` / `n_a8_inputs`, and one header line.
    - Without B8-A8 nothing is added.
15. **Panel members (§6.1).**
    - A8 members are `A8-<s>` for each B8-A8-accepted confirmatory session, even when the other one is incomplete.
    - An A8 member directory is ignored when no B8-A8 is passed.
    - `len_*` of an A8 item counts the diff text plus the non-UTF-8 listing text.
16. **Leak report (§6.3).** A registry-name hit is reported as `registry-name`; the other hits keep their pattern name (e.g. `\bn16\b`, `box-home`, `template-tag`).
17. **A8 export inputs.** The export uses the pinned tg2 universe (`corpus_tg2` default) and the polyglot sha from the checkout by default (`a8_inputs["polyglot_sha"]` can override it). `--universe` stays A7's.
