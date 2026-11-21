# Test-writer report, delivery 1 — M76 B4b-2 (A8 consumers), spec v1.5

Working copy: the stack clone at the baseline (`HEAD` = `26287dce2`). Nothing was committed, pushed, reset or written outside the
copy and the scratch dir. (`../scratch/tw1_peek.py`, a 15-line read-only helper I wrote and never ran, is the only stray file there.)
Run command: `../fe_test.sh stack bench/tests/test_m76_b4b2_fe_*.py` (paths are relative to `benchmark/`).

## Result on the baseline (as it ran)

140 tests in 5 files: **34 passed, 95 failed, 11 errors** (the 11 errors are module-scoped fixtures that call `verify_a8_kv`).

* 34 passed = the invariants / goldens / world sanity checks (class b) that hold today. **All of them exercise baseline code**, so a
  green candidate must keep them green.
* Of the failures only **5 are behavioural reds** on existing code (A7 per-row final-tree rule, §3.3: no block, no match, two matches,
  row sha ≠ published, orphan). The other 90 fail because the named A8 symbol / argument does not exist yet
  (`p426_verify.verify_a8_kv`, `KV_AXES`, `kv_normalise`; `p426_signals.compute_kv(b8_a8=…)`; `p426_panel.kv_members(a8_sessions=…)`,
  `KV_INPUT_SOURCE["A8"]`, `kv_rubric("A8-…")`; the CLI's `B8-A8.json`). **I could not run any A8 test against a correct implementation**:
  their world is verified only against the baseline's own readers (below), so a red A8 test on the candidate may be a wrong assumption
  of mine — see "Assumptions" and send the failing name back rather than bending the code.

## Files

| file | what |
|---|---|
| `test_m76_b4b2_fe_support.py` | the shared synthetic world (`World`) + 8 checks of it |
| `test_m76_b4b2_fe_b8.py` | B8 / B8-A8 (`bench.p426_verify`): §3.1–3.6, §5, §4.2 input, §9.2–9.6 |
| `test_m76_b4b2_fe_signals.py` | the A8 section / flags of the sheet (`compute_kv`), §4, §9.5, §7.1 / §7.2 on a synthetic world |
| `test_m76_b4b2_fe_panel.py` | A8 members, rubric, input source, Holm family, leak rule (§6.1, §6.3, §6.4) |
| `test_m76_b4b2_fe_real.py` | committed records: §7.1 / §7.2 goldens, §7.3 on the real pilot pair, the CLI |
| `fixtures/m76_b4b2_fe/` | 8 real tg2 pilot invocation manifests (byte copies, `PINS.json` sha-pinned; no home path / user / host — checked by a test) |

`World` writes `<repo>/benchmark/results/m76/{wave2,wave2.tg2}/…` in the committed layout, with the tg2 schedules built by
`schedules.tg2_p426` from the pinned draw (so `check_tg2_p426` holds), real pilot manifests for provenance, `chain.json` with a
`progress` inventory that **`chain_rows.load_slots` accepts** (reruns, harness DNFs, accounting faults included — checked by
`test_the_world_is_valid_for_the_baseline_chain_reader`), sealed sidecars via `p426_hooks.seal`, sealed re-check documents in the
sequencer's own shape (`p426_wave2.ensure_recheck`), and a stand-in `B8.json`. The A7 variant (`corpus="tg1"`) is accepted by today's
`verify_a7_kv` (control tests pass).

## Tests (class · item · baseline)

Class: **a** reproduces a failure the spec fixes · **b** preserves an invariant · **c** new behaviour. Baseline: **PASS**; **RED-behaviour**
(runs, asserts the new rule, fails); **RED-symbol** (the named symbol / argument is absent).

### `test_m76_b4b2_fe_support.py` (all PASS — fixture sanity)
`test_pinned_manifest_fixtures_are_the_committed_pilot_manifests` (b), `test_the_pinned_draw_is_the_one_the_schedules_name` (b),
`test_fixtures_carry_no_home_path_user_or_host` (b), `test_tg2_world_sessions_are_the_pinned_draws[pilot-4|s1-80|s2-80|reload-20]` (b),
`test_the_world_is_valid_for_the_baseline_chain_reader` (b).

### `test_m76_b4b2_fe_b8.py`
Per-row final-tree rule, §3.3 / §7.4, **parametrized over both axes** (`[A7]` drives `verify_a7_kv`, `[A8]` `verify_a8_kv`):

| test | class | baseline `[A7]` / `[A8]` |
|---|---|---|
| `test_clean_session_is_accepted_with_both_manifest_shas` | b / c | PASS / RED-symbol |
| `test_row_without_final_tree_block_rejects_the_session` | a | **RED-behaviour** / RED-symbol |
| `test_row_whose_manifest_was_not_published_rejects_the_session` | a | **RED-behaviour** / RED-symbol |
| `test_two_published_manifests_for_one_row_reject_the_session` | a | **RED-behaviour** / RED-symbol |
| `test_row_sha_differing_from_the_published_manifest_rejects_the_session` | a | **RED-behaviour** / RED-symbol |
| `test_orphan_manifest_of_another_run_rejects_the_session` | a | **RED-behaviour** / RED-symbol |
| `test_manifest_of_a_discarded_rerun_attempt_is_not_an_orphan` (A8 only: the S27 rerun-keyed records exist only there) | c | RED-symbol |
| `test_all_dnf_attempt_passes_the_final_tree_rule` | b / c | PASS / RED-symbol |
| `test_a_dnf_slot_is_exempt` | b / c | PASS / RED-symbol |
| `test_committed_b8_has_no_null_manifest_sha` | b | PASS |

Axis table, names, guards (§3.1, §3.2): `test_axis_table_names_both_axes` (c; RED-symbol `KV_AXES`),
`test_a8_refuses_a_member_name_outside_its_axis[4 names]` (c; RED-symbol), `test_a7_refuses_a_tg2_attempt_name` (b; PASS),
`test_a8_normalises_the_arms_own_g2_worktree` / `test_a8_rejects_a_manifest_naming_the_other_arms_worktree` (c; RED-symbol — together they
separate the A8 `m76-g2` worktree prefix from A7's `m76-f45|m76-q`).

Provenance (§3.4): `test_real_tg2_manifests_pass_provenance` (c), `test_a_tg2_only_key_differing_between_arms_rejects_the_session[6 keys]`
(c: `runtime.policy.corpus_identity.draw_sha256`, `…policy.grader_version`, `…policy.gate.requests`, `runtime.scaffold`,
`sampling.thinking_budget`, `box`), `test_a_missing_manifest_rejects_the_a8_session` (c), `test_kv_normalise_is_corpus_neutral_and_the_a7_alias_is_kept`
(c) — all RED-symbol.

Record, partial decider, refusals (§3.2): `test_document_fields_and_inputs` (c), `test_partial_decider_is_incomplete_not_a_refusal` (c),
`test_a_session_without_its_pair_record_is_incomplete` (c), `test_a8_is_not_built_for_a_tg1_world` (c; accepts "refused" or "not built"),
`test_a_harvested_attempt_missing_schedule_or_chain_refuses[2]` (b), `test_an_unreadable_chain_refuses` (b) — RED-symbol.

Plan binding (§3.6): `test_schedule_not_the_pinned_draws_prefix_rejects_the_session`, `test_schedule_of_another_leg_rejects_the_session`,
`test_chain_tg2_leg_must_be_the_session`, `test_chain_frozen_record_must_be_the_v8_record`, `test_v8_arms_must_be_n16_x` (all c; RED-symbol;
each accepts "session rejected with a reason" or `RefusalError`, as the spec says "rejects" in §3.6).

Re-check binding (§5; module-fixture `clean_full`, **ERROR/RED-symbol** on the baseline): `test_complete_decider_is_accepted`,
`test_missing_recheck_s2_makes_only_the_label_incomplete`, `test_recheck_over_a_superseded_attempt_is_not_the_selected_ones`,
`test_outside_s1_recheck_without_ack_is_not_accepted`, `test_unsealed_recheck_is_not_accepted`, `test_recheck_sha_must_match_sequence_json` (all c).
The "not accepted" ones assert the record's `recheck` label differs from the clean decider's (or `RefusalError`), not a particular wording.

Latency (§4.2): `test_latency_absent_is_incomplete_and_present_is_an_input` (c; RED-symbol).

S27 additions (§9.2–9.6, §9.7; all c, RED-symbol): `test_harness_dnf_slot_is_accepted_and_counted[harness_fault_dnf|grade_fault]`,
`test_harness_dnf_sidecar_mismatch_refuses`, `test_harness_dnf_without_its_sidecar_refuses`, `test_rerun_slot_reads_the_accepted_attempt_and_is_listed`,
`test_slot_with_two_accepted_attempts_is_not_accepted` (accepts reason or refusal: §9.3 says "a REASON", §9.7 says "refuses"),
`test_rerun_without_a_recorded_reason_is_not_accepted`, `test_accounting_fault_row_is_accepted_and_listed`,
`test_accounting_sidecar_naming_another_row_is_not_accepted`, `test_accounting_fault_without_sidecar_is_not_accepted`,
`test_paused_leg_is_incomplete_never_a_result[n16|x]`, `test_speed_invalid_leg_keeps_the_session_accepted`.

### `test_m76_b4b2_fe_signals.py` (synthetic Wave 1 world from `test_m76_b3_impl_verify.World` + the tg2 `World`; sheet via `compute_kv`)
`test_a8_verdict_is_axis_verdict_over_the_strict_outcomes` (c; exact equality with `m76_rule.axis_verdict("A8", 1, …, languages=…)`),
`test_sheet_renders_the_a8_heading_after_a7` (c), `test_outcome_is_passed_and_converged_and_dnf_is_zero` (c: non-converged pass, transport DNF,
harness DNF, grade fault all score 0), `test_a_language_at_minus_25_pp_holds_and_blocks` (c), `test_minus_20_pp_exactly_does_not_hold` (c),
`test_a_clear_loss_is_flagged_for_a8` (c), `test_an_undecided_verdict_is_flagged_for_a8` (c), `test_per_language_loss_bounds_are_descriptive` (c),
`test_noise_floor_counts_the_discordant_items` (c), `test_reload_control_on_the_shared_items` (c), `test_reload_control_refuses_when_seeds_differ` (c;
the literal "refused: seeds differ"), `test_partial_decider_gives_an_incomplete_axis_without_a_verdict` (c), `test_a_paused_leg_makes_the_axis_incomplete` (c),
`test_unknown_language_prefix_refuses` (c), `test_sensitivity_removes_the_faulted_item_from_both_arms` (c), `test_every_fault_kind_in_either_arm_or_session_is_removed[3]` (c),
`test_sensitivity_without_faulted_items` (c; literal "no faulted items"), `test_the_verdict_keeps_faulted_items` (c),
`test_accounting_fault_keeps_its_outcome_and_leaves_the_decode_aggregate` (c), `test_speed_invalid_leg_leaves_quality_unaffected` (c),
`test_latency_summary` (c), `test_a8_record_changes_only_the_a8_parts_of_the_sheet` (b/c: the §7.2 projection), `test_a8_record_leaves_the_a1_to_a7_text_alone` (b/c),
`test_b8_a8_of_another_b8_refuses` (c), `test_a_changed_a8_input_refuses` (c), `test_explicit_none_equals_the_default` (c).
All RED-symbol, except **`test_no_b8_a8_means_no_a8_in_the_sheet` (b; PASS)**.

### `test_m76_b4b2_fe_panel.py`
`test_members_without_a8_are_unchanged` (b/c), `test_members_gain_one_a8_member_per_accepted_session` (c), `test_a8_rubric_and_input_source` (c),
`test_expected_members_follow_the_accepted_a8_sessions` (c), `test_a8_sessions_join_the_holm_family` (c: raw A1–A7 statistics unchanged, adjusted p
recomputed over the larger family, checked against `stats.holm`), `test_a8_member_with_under_five_judged_items_is_reported_not_tested` (c),
`test_an_a8_member_favouring_the_reference_is_flagged` (c), `test_an_a8_member_favouring_the_treatment_is_not_flagged` (c) — RED-symbol.
PASS (b, baseline functions the A8 export reuses): `test_family_without_a8_is_unchanged`,
`test_an_arm_revealing_text_refuses_the_export[6 patterns]` (refuses, writes nothing, never echoes the answer text),
`test_the_box_home_path_refuses`, `test_family_tokens_and_generic_paths_are_answer_content` (C362), `test_protected_manifest_holds_cargo_toml_and_the_tests`.

### `test_m76_b4b2_fe_real.py` (committed records)
PASS (b): `test_b8_regenerates_byte_identically` (CLI `all --lever kv --pair n16,x`), `test_committed_b8_has_no_a8`,
`test_signals_regenerate_byte_identically` (with `--panel`, no `--partial` — that is how the committed `SIGNALS.md/.json` were made),
`test_partial_signals_regenerate_byte_identically` (`--panel … --partial` → `SIGNALS-partial.*`), `test_the_frozen_panel_has_no_a8_member`,
`test_the_committed_pilot_schedule_is_the_pinned_draws_prefix[n16|x]`, `test_the_committed_pilot_rows_bind_their_published_manifests[n16|x]`,
`test_the_committed_v8_is_the_tg2_kv_pair`.
RED (c): `test_the_cli_writes_b8_a8_beside_b8` (RED-behaviour: no `B8-A8.json`), `test_a8_record_changes_only_the_a8_parts_of_the_real_sheet[SIGNALS.json|SIGNALS-partial.json]`
(§7.2), and the §7.3 group on the real pilot pair, all RED-symbol (fixture ERROR): `test_the_real_pilot_pair_builds_with_the_pilot_accepted`,
`test_the_real_pilot_identities_are_matched_and_provenance_passes`, `test_the_real_record_binds_b8_and_its_inputs`,
`test_no_regrade_machinery_in_the_real_record`, `test_the_real_latency_is_incomplete`.

## Not covered, and why

1. **The A8 packet (`_a8_packet`)**: the prompt-equality check against the evidence export's first user message; the protected-path
   assertion including a grader-accepted Rust `Cargo.toml` (new/changed protected path → refuse; changed `Cargo.toml` → diffed); the
   A8 export's leak refusal at export level. The spec names no signature for `_a8_packet` / `kv_a8_context(b8_a8)` (the A7 analogue takes
   `(results_root, b8)`), nor the shape of "the first user message of the HARVEST-bound evidence export" (the evidence files published
   for a row are `.events.jsonl`, `.web.jsonl`, `.datefreeze.jsonl`, `.stderr.txt`, the final tree and the grades; I found no `export`
   file), and the real `Tg2Corpus` pins the universe sha so a synthetic universe cannot pass it. Writing these against guesses would
   produce red tests I could not tell from a wrong guess. **Needs**: the packet signature + the export's shape (a later delivery, with the
   candidate, can add them). The leak rule itself is covered on the baseline functions (panel file).
2. **A8 member freeze / ingest bound to `B8-A8.json`'s sha** (`kv_export` / `kv_panel_members` for `A8-<s>`; A1–A7 staying bound to `B8.json`;
   the panel verifying `base_b8_sha256` and B8-A8's inputs): no signature for the A8 inputs of `kv_export` / `kv_panel_members`. Covered
   only through `kv_members`, `kv_rubric`, `KV_INPUT_SOURCE`, and the Holm family.
3. **§3.7 / §7.6 (the lock-file regrade)** are removed by §9.1: no test, except the one assertion that no "regrade" text is in the real record.
4. **§7.3 on the new-identity pilot pair**: not harvested; the committed pair is the old identity (no S27 sidecars / reruns). The tests describe
   what must hold on it and its successor.
5. The signals CLI flag that takes `B8-A8.json` is unnamed: the A8 sheet is driven in-process through the named `compute_kv(…, b8_a8=, b8_a8_sha256=)`.

## Assumptions (each is one place to fix if wrong)

* `verify_a8_kv(results_root)` (`results_root` = `<rows>/m76`) reads `B8.json` there (the world writes a stand-in; the real run has the real one), returns
  `{pairs:[{pair, accepted, status, reasons, role, keys[{key, identical, manifest_sha256{n16,x}}], keys_accepted, speed_valid, labels}], sessions:["s1","s2"],
  status:"complete"|"incomplete", corpus:"tg2", recheck, latency, base_b8_sha256, inputs}`; a session is *incomplete* ⇔ `status == "incomplete"` (with `accepted False` and reasons).
  `inputs` keys are relative to `results_root` **or** to `rows_root` (`m76/…`) — both accepted.
* "Rejects" = `accepted is False` with a reason; for §3.6 and the S27 faults the tests also accept a `RefusalError`, except where the spec says "refuses" without alternative
  (a harness-DNF sidecar mismatch / missing, a missing or unreadable `schedule.json` / `chain.json`, a foreign or non-axis attempt name).
* Signals: section `sig["axes"]["A8"]` = `axis_verdict` fields with `hold` (the `a8_hold` dict) and `status` for "incomplete"; decode `sig["decode"]["A8"][session]["primary"]["n"]`;
  flags use `flag` ∈ {`hold`, `loss`, `undecided`} with `member == "A8"`; the sensitivity / reload control / latency / per-language bounds are located by their labels
  ("sensitivity", "no faulted items", "refused: seeds differ", "latency … incomplete", "per-language … descriptive") and by values, not by key names.
* Panel: A8 members follow the A7 ones; `kv_panel_family` / `kv_expected_members` take the accepted A8 sessions as `a8_sessions` (passed only when the parameter exists).
* The baseline's own `kv_a7_normalise` / per-invocation keys are what B8-A8 must also tolerate; the spec names only `kv_normalise` for the neutral spelling.

## Spec points worth a decision (not blockers)

* §3.6 says plan mismatches "reject the session"; §9.7 says a double-accepted slot "refuses" while §9.3 says "a REASON". The tests accept either for those; say which you intend and I will tighten.
* §3.2 gives B8-A8 no `inputs` root; the signals' re-hash needs one.
* An all-DNF attempt writes no row: today's `session_rows` refuses an attempt with no row file at all. The tests give such an attempt an empty rows file + manifest per language leg;
  say if the harness never writes those.
