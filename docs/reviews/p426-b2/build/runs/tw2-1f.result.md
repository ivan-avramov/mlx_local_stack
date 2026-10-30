All of delivery 1f is done on the baseline. The candidate run happened, but it ran the old frozen tests, not the amended ones.

**Status**
- Both support checks pass on the baseline (51 passed).
- On the baseline, 314 frozen and `add_` tests fail and 10 pass. All 10 passes are `[INV]` tests, and no failure comes from inside a support module.
- The candidate copy (`../eval-s3/mlx_local_stack`) still has the 1e frozen files. Collection there finds none of the 1f tests, and its s1 failures are `unrecognized arguments: --hmac-fd`, an argument only the old test fixtures pass. I couldn't install the new files: the candidate must not be edited, and reading or writing there was denied. Its result below is therefore 1e tests against the candidate, not the frozen 1f s1–s3.

## Amended tests (reason)

**Fixtures**
- **`b2_frozen_support.py`:**
  - `p426_argv`: no `--hmac-fd`, returns `(argv, None)` (C238).
  - `v8_base`: `r1_env_difference` replaces `allowed_env_differences` ([d2] closed list).
  - `arm_receipt_doc`: `credential_keys: {router, worker, probe}`, keys only (C238).
  - New `client_error_events` / `set_client_error`: they fix my s2 fixture defect, which was the leading `not json` line.
- **`b2_frozen_add_support.py`:**
  - `pair_argv` replaces `keyed_argv`.
  - `SeqOps` has no keys. `harvest` returns `{rc, harvest_json, harvest_sha256}` and writes a self-hashed `HARVEST.json`. New `publish_dossier` and `publish_run_files` recorders.
  - The fake `p426_dnf` record carries `pick`, `attempt`, `invocation` and `load_gen` (§16.1).

**s0 and support check**
- `test_b2_frozen_s0_support.py`:
  - The client-abort fixture test is parametrized over drop and refuse. It now asserts the "error event" abort and the `classify_error` cause. This fixes the check that missed the malformed fixture.
  - The abort-manifest test uses `set_client_error`.
  - The world test asserts `rfd is None`, no `--hmac-fd`, the `credential_keys` shape and `r1_env_difference`.
- `test_b2_frozen_add_support_check.py`:
  - `test_pair_argv_adds_the_pair_receipt_and_never_a_key` replaces the keyed-argv test.
  - The SeqOps test drops `--hmac-fd` and the keys, and checks the dict harvest and the publish calls.

**Frozen slice files**
- **s1:** `p426_argv` returns no key.
- **s2:**
  - `test_new_a_p426_client_abort_manifest_carries_cause_gate_usage_session_and_termination` uses the real event shape. It asserts session `s1`, usage `["m1"]` and in-flight `m2`.
  - `test_inv_a_tg1_client_abort_manifest_keeps_its_shape` uses the same fixture.
  - Together these fix the `drop` / `refuse` defect.
- **s3:**
  - `test_new_p426_continue_is_a_third_transport_policy_and_the_others_stay` parses a real `--p426` argv. This fixes my test that built an invalid `tg1-p426` config.
  - `test_new_invalidate_has_no_slot_disposition` was a **false pass on the baseline**: `invalidate()` itself raised `ValueError` inside `pytest.raises`. The disposition is now built outside the block.
- **s5:**
  - The credential-keys parameter was added.
  - The allowed-list test became `test_fix_an_env_difference_outside_the_closed_list_refuses`.
  - The no-hmac-echo test became `test_new_a_credential_key_missing_from_one_process_of_one_leg_refuses_naming_the_key`.
  - The dossier test became `test_new_the_pair_dossier_is_self_hashed_and_keyed_by_arm` (arms shape, `pairs/pilot__off-a1__on-a2.json`). The immutable-dossier path was renamed to match.
  - `receipt()` calls `arm_receipt` without a key. The canonicalize test expects `credential_keys`.
  - The hmac test became `test_new_credential_keys_are_recorded_per_process_never_their_values_or_hashes`.
  - The other-pair-key test was removed (C238).
- **s7:** the receipt test asserts no `credentials` and `HF_TOKEN` in each process's `credential_keys`.
- **s9:** `entry_for` matches `leg:<rel>`, to fit the typed sources.

**`add_` files**
- **`add_pair`:** the key tests became:
  - `test_new_a_credential_key_in_one_process_of_one_leg_only_refuses_before_item_one`;
  - `test_new_the_same_credential_keys_with_other_values_pass_the_gate`;
  - `test_new_a_rehearsal_leg_records_credential_keys_per_process_and_no_value`.

  The different-pair-key test was removed.
- **`add_sequencer`:**
  - The pilot-pair test became `test_new_the_pilot_pair_runs_each_legs_argv_with_the_first_receipt` (asserts no `--hmac-fd`).
  - The dossier test became `test_new_the_pair_dossier_is_per_pair_attempt_keyed_by_arm_published_and_selected` (name, arms, receipt and harvest sha256s, `publish_dossier` called, named in `sequence.json`).
  - The full run checks 4 dossiers `*__off-a1__on-a1.json` and no keys.
  - The voiding test became `test_new_a_restart_between_the_legs_of_a_pair_resumes_it_with_the_first_legs_persisted_receipt`: only on-pilot a1 runs, with the off a1 receipt, and nothing is voided.
  - The makeup test compares the occurrences as a set and drops the keys.
  - The rehearsal test became `test_new_the_rehearsal_runs_r1_as_a_pair_then_r2_and_r3`: R1's second leg gets `--pair-receipt`, and no leg gets `--hmac-fd`.
- **`add_scrub`:** the source is `leg:RUNLOG.md`.

## New tests
- s1 `test_new_p426_requires_an_attempt_out_root_named_leg_dot_a_n` (4 cases).
- s3 `test_new_invalidate_has_no_slot_disposition`.
- s4 `test_new_the_hooks_context_defaults_to_none`.
- s5: the closed-list and missing-key tests above.
- s7:
  - `test_new_log_bounds_is_a_two_phase_record_created_before_the_router_and_finalized_once`;
  - `test_new_records_destined_for_main_carry_no_absolute_paths`;
  - `test_new_the_p426_dnf_record_carries_the_section_16_1_fields`.
- s9:
  - `test_new_every_harvest_source_is_typed`;
  - `test_new_a_retry_discards_only_this_attempts_incomplete_destination_and_commits`;
  - `test_new_a_main_record_with_an_absolute_path_fails_the_harvest`.
- add_sequencer:
  - `test_new_the_run_files_are_published_with_the_record_dir_and_sequence_json`;
  - `test_new_each_sequence_json_version_records_the_sha256_of_the_previous_one`;
  - `test_new_the_occurrences_file_is_an_unordered_set_the_sequencer_canonicalizes`.

## Commands and summary lines (verbatim)
```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py bench/tests/test_b2_frozen_add_support_check.py
51 passed in 25.20s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s{1..9}_*.py bench/tests/test_b2_frozen_add_{sequencer,pair,census,ledger,a4,argv,scrub,record}.py --tb=no -rp
314 failed, 10 passed in 14.72s

../bin/run_candidate_tests.sh bench/tests/test_b2_frozen_s1_cli.py bench/tests/test_b2_frozen_s2_probe.py bench/tests/test_b2_frozen_s3_core.py --tb=no
42 failed, 26 passed in 51.57s        # the candidate copy's own (1e) test files, not the 1f set
```
The second command listed all 17 files by full name; I've shortened it to brace form here. The 10 baseline passes are the 4 s2 `test_inv_*`, 2 s3, 1 s6 and 2 s9 `test_inv_*` tests, and `add_scrub`'s `test_inv_the_wave1_scrub_constructor_still_works_without_emails`.

## Problems still in the spec
- **P1 R1 subset check:** this can't be tested blind. `--r1` takes one path, but R1 is a pair, and the dossier's `differences` entry format isn't named.
- **P2 `pair_problems(first, second, *, allowed, volatile)`:** it still takes `allowed`, though [d2] closes the list. Either drop the parameter or say it must equal the closed list.
- **P3 dossier names and types:** the `<pair>` label (`pilot`? `s1`? `r1`?) and the type of `arms.*.attempt` (int or `<leg>.a<n>`) aren't named. My tests accept either type and derive the name from `doc["pair"]`.
- **P4 `write_dossier(path, *, pair, attempts, receipts, harvests, verdict)`:** this is still positional-pair input. Nothing says whether OFF comes first or how it maps to `arms`.
- **P5 `sequence.json` journal:** the field holding the previous version's sha256 isn't named. My test only requires that the hex digest appears in the next version.
- **P6 occurrences:** where the sequencer writes its canonicalized copy isn't named. My test compares what each chain's `--occurrences` file contains, not the path.
- **P7 `publish_run_files(paths)`:** it's unclear whether the frozen-record directory is passed as one directory path or as its files. My test accepts either.
- **P8 `P426Hooks` with `context=None`:** the behaviour isn't named. My test asserts only that the call is legal and returns a `Disposition`.
- **P9 `p426_harvest.publish_dossier` / `publish_run_files`:** module-level signatures aren't named beyond the `ops` ones, so they're tested only through the sequencer's ops.
- **P10 credential keys in `env`:** nothing says whether they may still appear in the receipt's `env` with placeholder values, or must be absent there. My tests only require that no value or hash of a value appears.

Recommendation: install the 1f frozen set into the candidate copy and rerun the s1–s3 command before anyone uses its result. Today's 42/26 judges the candidate against superseded tests.
