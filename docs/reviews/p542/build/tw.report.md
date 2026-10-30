I wrote `mlx_vlm/tests/test_p542_qualify_any.py`: 45 tests, and all 45 fail today, each for the reason it targets. The three existing qualify files still pass (106). Nothing else was changed and nothing was committed; `git status` shows only `P542_SPEC.md` and the new file as untracked.

## Runs (verbatim summary lines)
- `../bin/run_fork_tests.sh mlx_vlm/tests/test_p542_qualify_any.py` → `45 failed in 2.59s`
- `../bin/run_fork_tests.sh` on the three existing qualify test files (`test_p415_qualify.py`, `test_p426_qualify_predictor.py`, `test_p452_qualify_in_wrapper.py`) → `106 passed in 6.24s`

I checked every failure message. Each comes from the old behaviour or a missing interface, not from the test setup:
- `unknown entry '<name>'` from the fixed table;
- the old arm names (`mtp_on` instead of `served_on` / `served_off` / `mtp_on_restored`);
- the old guard `--predictor off: the committed registry serves X MTP-ON`;
- the classifier running for every arm (`not one of the 16 accepted byte states`, `classify_calls == [1, 1]`);
- the gate comparing against `7207179b` instead of `orchestrate.PRODUCTION`;
- Fable not being gated at all, so it completes with no summary; <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
- `TypeError: arm_for() got an unexpected keyword argument 'registry_entry'`;
- `load_references` refusing a name outside the table.

Two tests passed on the first run. I tightened both so they fail on the target: `test_c4_a_restore_classifies` now asserts the `mtp_on_restored` arm, and the extra-entry restore refusal now first checks that the same registry is accepted for a served arm. The tests where Fable is served MTP-ON get through to COMPLETED today, which shows the test setup itself works. <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->

**How the tests work:** the driver tests call the real `qualify.main` → `drive`. Registries are built from the pinned golden fixture with the real `registry_states` (`apply` to turn entries OFF, plus an appended candidate block). P369 summaries are real artifacts under `$STACK_WORKDIR/p369/phase2`. Only the host side is mocked: lock, preflight, job, git, power, console script, `full_command` and `request_problems`. `full_command` is mocked to build the argv from the served registry file and to record which file was served.

## Tests → spec items
| Test | Spec |
|---|---|
| P1 `test_c1_the_fixed_entries_table_is_removed` | 1: `ENTRIES` removed |
| P2 `test_c1_any_registry_name_is_accepted[nemotron, new-candidate]` | 1: any registry name | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P3 `test_c1_a_name_outside_the_registry_refuses_listing_the_registry_names` | 1: refusal lists the registry's names |
| P4 `test_c1_default_entries_are_the_picks_in_the_registry` | 1: `default_entries` = `PICKS` ∩ registry (4 entries) |
| P5 `test_c2_arm_for_derives_the_arm_from_the_committed_block` (8 ids) | 2: `arm_for` with the new signature |
| P6 `test_c2_arm_for_refuses_on_without_a_drafter_to_restore` (2) | 2: `no MTP drafter` refusal (unit) |
| P7 `test_c2_served_on_serves_the_committed_registry` | 2 `served_on`; 3 bare summary path |
| P8 `test_c2_predictor_on_for_an_entry_served_on_serves_it_as_committed` | 2: `on` + served ON |
| P9 `test_c2_an_entry_served_off_is_served_as_committed_without_a_gate` (2) | 2 `served_off` |
| P10 `test_c2_mtp_off_removes_only_the_mtp_keys_and_records_the_derived_sha` (4 MTP entries) | 2 `mtp_off`: only the 3 keys removed, file under `--out`, sha recorded, committed file untouched |
| P11 `test_c2_mtp_on_restored_serves_the_16_state_overlay` | 2 `mtp_on_restored` |
| P12 `test_c2_predictor_on_without_a_restorable_drafter_refuses` (2) | 2: `no MTP drafter` (driver) |
| P13 `test_c3_served_on_without_a_p369_summary_refuses` / `…mtp_on_restored_without…` | 3: missing summary |
| P14 `test_c3_a_summary_for_another_entry_refuses` | 3: wrong entry |
| P15 `test_c3_a_summary_on_the_old_production_constant_refuses` | 3: wrong production (binding and manifest) |
| P16 `test_c3_a_summary_on_the_default_production_passes` | 3: default `orchestrate.PRODUCTION` |
| P17 `test_c3_a_summary_must_match_the_runs_production_ref` | 3: matches `--production-ref`; mismatch refused |
| P18 `test_c3_per_entry_summaries_name_equals_path` | 3: `name=path`, repeatable; swapped paths refused |
| P19 `test_c3_mtp_on_needs_the_entry_in_picks_even_with_a_summary` | 3(a): not in `PICKS` → refused; its OFF arm runs |
| P20 `test_c4_served_and_off_arms_never_classify` / `test_c4_a_restore_classifies` | 4: classifier only for a restore |
| P21 `test_c4_…extra_entry_is_accepted_for_served_and_off_arms` (4) / `…refused_for_a_restore` | 4: extra entry accepted for served/off, refused for a restore |
| P22 `test_c5_load_references_takes_any_entry_name` | 5 |
| P23 `test_c5_an_entry_without_a_reference_reports_peak_and_guidance_only` | 5 |
| P24 `test_c6_the_final_state_carries_rates_and_arm_per_entry` | 6: `rates` and `arm` |
| P25 `test_c7_an_unknown_registry_key_on_a_new_entry_still_refuses` | 7: `expected_config` refusal kept |

## Existing tests the spec will break
This is from reading the tests; I haven't run them against an implementation.
- **`test_p415_qualify.py`:**
  - `test_t1_the_three_entries_and_their_arms`, `test_t1_a_synthetic_served_entry_takes_the_served_arm`, `test_t1_an_unknown_entry_or_an_ungated_qwen36_refuses`: `ENTRIES`, the old `arm_for` / `entry_problems`, and `7207179b` summaries.
  - `test_t6_the_reference_table_loads_and_refuses_bad_rows`: expects `"not-an-entry"` to raise.
  - `test_p476_the_real_reference_table_loads_against_the_real_entries`: `ENTRIES`.
  - `test_d8_the_default_run_is_all_three_and_needs_the_qwen36_evidence`: expects 3 defaults.
  - `test_d10_the_qwen36_gate_checks_the_summarys_provenance`: its "good" summary uses `7207179b`.
  - Every test that goes through `_drive`: it uses `_with_served` (`setitem(qualify.ENTRIES, …)`), a `models: []` registry that no name is in, and Fable served ON with no summary. That is `test_t7_every_entry_completed_exits_zero`, both `test_t11_*`, `test_d6_d13_*`, `test_e1_*`, `test_e2_*`, `test_d5_a_console_script_changed_*`, `test_d13_*` and `test_r3_d5_*`. <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
- **`test_p426_qualify_predictor.py`:**
  - `test_the_arm_follows_the_predictor` and `test_a_served_entry_has_no_on_arm`: old arm names and signature.
  - `test_the_off_arm_needs_no_p369_gate`: `entry_problems` without the registry.
  - `test_the_off_arm_serves_the_committed_registry`: now `served_off`, not `mtp_off`.
  - `test_the_off_arm_refuses_a_registry_serving_the_entry_mtp_on`: asserts the guard that rule 2 removes.
- **`test_p452_qualify_in_wrapper.py`:** none.

## Ambiguous spec points (not resolved)
- P26 What `registry_state` in `arm_for` means and what type it is: the classify result, the registry text, or something else. The unit tests pass `None` for the non-restore cases; the restore case is only tested through the driver.
- P27 How `arm_for` refuses. The tests assume it raises `ValueError` with `<name>: no MTP drafter to restore`.
- P28 The signature of `default_entries()`: it needs the registry, but the spec shows no argument. The order (registry order or `PICKS` order) is also open. It is tested only as a set, through the driver.
- P29 Where the MTP keys come from: `bench.p426_leg.MTP_KEYS` is in the stack, not the fork. The tests hard-code the three keys.
- P30 The derived `mtp_off` registry: removing the lines textually (keeping comments and bytes) or re-serializing it, and which report key holds its sha256. The tests check parsed equality and that the sha appears somewhere in the report.
- P31 Whether refusals happen before the run (`SystemExit`) or per entry (FAILED). The tests accept either: not COMPLETED and no job run.
- P32 Whether the summary's production is compared with the resolved full sha or with the `--production-ref` string as given. The test avoids this with a 40-character ref and an identity resolver.
- P33 What a bare `--p369-summary` does with several `--entry` values (refuse, or apply to all). Also, what `name=path` does when the name isn't an `--entry`, or the path contains `=`. Not tested.
- P34 Whether "today's checks" include `summary_artifact_problems` (the `STACK_WORKDIR` root, `manifest.json`, the v13-ancestor check) for every MTP-ON arm. The test summaries satisfy them, so either answer passes.
- P35 Whether `rates` is recorded only on COMPLETED or whenever a record exists. Only COMPLETED is tested.
- P36 What "restorable" means: the name is in `registry_states.ENTRY_OFF`, or the overlay succeeds. For an extra-entry registry, the refusal could be "no drafter" or a classifier refusal; the test only checks that it doesn't complete.
- P37 Strict-parse refusals for served arms (CR line endings, duplicate keys) aren't pinned. That behaviour already passes today, so a test for it couldn't fail today.

## Still open
- I didn't run black, isort or autoflake on the new file; they weren't in the allowed commands. A couple of lines are probably over 88 characters, so the fork gate's pre-commit step will likely reformat it.
- I didn't run the P369 harness tests or the fork gate.
