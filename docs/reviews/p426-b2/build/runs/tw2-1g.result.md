Delivery 1g is done. The tests now take only the §16.7 forms, and the R1 subset check and the module-level `publish_*` functions have their own tests.

- **Baseline:** both support checks pass (52 passed). The frozen and `add_` set gives 329 failed, 10 passed, and all 10 passes are `[INV]` tests. No failure ends inside a support module.
- **Changed tests:** all 30 tests changed or added in 1g fail on the baseline only because the module or function they test doesn't exist yet (an `ImportError`, or `AttributeError` for `p426_harvest.publish_dossier` / `publish_run_files`).
- **Candidate:** not run, as you asked.

## Tests changed in this delivery

**Tightened to the pinned form**
| file::test | change (§16.7) |
|---|---|
| s5 `pair_problems` callers (6 tests) | `pair_problems(off, on)`: no `allowed` / `volatile` arguments; the local `VOLATILE` list is removed |
| s5 `test_new_volatile_keys_never_count_as_a_difference` | parametrized over all 7 closed-list keys (it now relies on the module constant) |
| s5 `test_new_an_off_and_an_on_receipt_of_one_build_pass_the_pair_gate` | no longer reads `volatile_env_keys` from v8 |
| s5 `test_new_the_pair_dossier_is_self_hashed_and_keyed_by_arm` | `write_dossier(path, *, pair, off={attempt, receipt, harvest}, on=…, differences, verdict)`; checks that `differences` round-trips and that `at` is set |
| s5 `test_new_the_pair_dossier_is_immutable` | the same call form, with real attempt names |
| s5 `test_new_credential_keys_are_recorded_per_process_never_their_values_or_hashes` | credential keys are **absent** from `env` (it used to check only that the value differed) |
| s7 `test_new_the_receipt_is_written_after_load_and_never_holds_a_credential_value` | adds: `HF_TOKEN` is absent from every `env` map |
| add_pair `test_new_a_rehearsal_leg_records_credential_keys_per_process_and_no_value` | the same addition |
| s4 `test_new_the_hooks_context_defaults_to_none` → `test_new_p426_hooks_called_without_a_context_raise_hook_infrastructure_error[before, after]` | raises `HookInfrastructureError` and writes no item record |
| s8 `_v8_argv` (used by the wrong-kind and gitlink tests) | `--r1-off` / `--r1-on`, each R1 root holding a `receipt.json` |
| add_sequencer `…dossier_is_per_pair_attempt_keyed_by_arm_published_and_selected` | exact name `pilot__off-a1__on-a1.json`; `pair == "pilot"`; attempts `tg1-p426-{off,on}-pilot.a1`; `differences` entries are `{process, field, off, on}` |
| add_sequencer `…run_files_are_published_with_the_record_dir_and_sequence_json` | files only: `v8_base.json` and `sequence.json` are in the list, the directory is not |
| add_sequencer `…each_sequence_json_version_records_the_sha256_of_the_previous_one` | captures every version at its `os.replace` / `os.rename`; the first has `previous_sha256 = null`, each later one equals the sha256 of the version before it |
| add_sequencer full run | dossier names are exactly the 4 pairs pilot / s1 / s2 / reload |
| add_sequencer makeup | `--occurrences` is `<out-base>/makeup/occurrences.<arm>.jsonl`, each holding the whole union; dossier `makeup__off-a1__on-a1.json` |
| add_sequencer occurrences canonicalization | adds the canonical order: s1 python, s1 go, s2 go, s2 python |
| add_sequencer rehearsal | dossier `r1__off-a1__on-a1.json`, with ON attempt `tg1-p426-rehearsal-on.a1` |
| add_sequencer resume | the prewritten `sequence.json` carries `previous_sha256: null` |
| add_support_check SeqOps | `publish_run_files` gets file paths, and the recorded call is checked exactly |

**New tests**
- **R1 subset check (s8):**
  - `test_new_v8_refuses_an_r1_difference_outside_the_closed_list_naming_its_field`
  - `test_new_v8_refuses_an_r1_credential_key_in_one_leg_only_naming_the_key_never_a_value`
  - `test_new_an_r1_difference_inside_the_closed_list_is_not_refused_as_an_r1_finding`
- **Module-level publish (s9):**
  - `test_new_publish_dossier_publishes_the_dossier_byte_identical_to_main_pairs_and_is_idempotent`
  - `test_new_publish_dossier_refuses_a_dossier_the_scrub_would_change_and_publishes_nothing`
  - `test_new_publish_run_files_publishes_each_file_to_main_wave2_run`
  - `test_new_publish_run_files_refuses_a_run_file_the_scrub_would_change_and_publishes_nothing`
- **s5:** `test_new_a_problem_names_the_differing_process_and_field`
- **s0 (fixture check):** `test_the_receipt_fixture_pair_differs_only_on_the_closed_list_and_keeps_credentials_out_of_env`. It confirms the OFF / ON receipt fixtures differ only in the §6.3 worker argv items and the drafter snapshot.

## Commands and summary lines (verbatim)
```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py bench/tests/test_b2_frozen_add_support_check.py
52 passed in 21.15s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s1_cli.py … bench/tests/test_b2_frozen_add_record.py --tb=line -rp   (all 17 files)
329 failed, 10 passed in 11.60s

../bin/run_stack_tests.sh <s8 s9 s5 s4 add_sequencer> -k "r1 or publish or dossier or volatile or problem_names or without_a_context or previous or occurrences or makeup or rehearsal_runs or credential_keys_are" --tb=line
30 failed, 163 deselected in 1.11s
```
The 10 baseline passes are the same `[INV]` tests as in 1f: 4 in s2, 2 in s3, 1 in s6, 2 in s9 and 1 in add_scrub.

## Problems still in the spec
- **P11 v8's worktree fields aren't portable.** `v8_base` records `off_worktree` / `on_worktree` as absolute paths (§16.1, and so does the fixture), but `publish_run_files` sends the frozen records to `main`, and §11.2 refuses any `main` record the scrub would change. My publish test overrides both fields with `$STACK_WORKDIR/stack-p426-{off,on}`. The spec should say v8 writes the portable form, and whether the chain compares it after expansion. The same applies to the rehearsal manifest (`off_worktree`, `out_root`).
- **P12 is R1's success output buildable?** My R1 contrast test is deliberately weak. v8 needs inputs this fixture doesn't build (build, production ref, grader image), so the test only says v8 is not refused *for R1*, and it checks the `r1_env_difference` shape only if v8 actually writes. A positive v8 test needs the spec to name where those inputs come from (`ops` or `checks`).
- **P13 `write_dossier`'s `off.receipt` / `off.harvest`:** the spec doesn't say whether these are paths or loaded documents, or whether `receipt_sha256` is the file's sha256 or the record's self-hash. My tests pass paths and expect the file sha256.
- **P14 the `differences` field names** (`argv`, `snapshots.drafter`, …) aren't pinned. The tests check only the entry keys and the `process` vocabulary.
- **P15 `publish_dossier` / `publish_run_files` return value:** it's only "dict". The tests check effects (the destination's bytes, idempotence, `HarvestError` and nothing published) and don't check the returned shape.

The set is ready for you to freeze. Nothing is committed: test writers don't commit.
