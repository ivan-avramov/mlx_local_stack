# Delivery 3h: set amended to the strict-verify fix round; only the two baseline-only s0 checks fail on the final copy

Nothing was committed or pushed. No candidate file or spec file was edited.

## Runs

- **Support checks on the baseline** (`run_stack_tests.sh`, `test_b2_frozen_s0_support.py` + `test_b2_frozen_add_support_check.py`): `55 passed in 19.84s`
- **Whole set on the final copy**, re-synced with `sync_to_final.sh` and run with `run_candidate_final_tests.sh` over the 20 files: `2 failed, 501 passed in 139.69s (0:02:19)`
  - Before the amendments the set gave 32 failed / 437 passed there.

## The two remaining failures

Both are support checks that only hold on the baseline commit, so they fail on any candidate by design (none of classes (a)–(d)). Both pass on the baseline.

| Test | Evidence |
|---|---|
| s0 `test_the_legacy_chain_goldens_hold_on_the_base_commit` | `s0_support.py:128: TypeError: tg1() missing 1 required keyword-only argument: 'picks'`: the base-commit call against the candidate's changed `schedules.tg1` signature. |
| s0 `test_the_item_barrier_fake_probe_completes_under_the_baseline_chain_…` | `run_tg1_chain.py:220: SystemExit: 2`: the baseline chain argv on the candidate's CLI. |

## The 30 failures the amendments cleared

All were spec changes after my freeze, fixed in my fixtures and expectations:
- **Unsealed `leg.json`** (s9 ×17, add_scrub ×1, s0 harvest copy ×1): my fixture `not_started_leg_root` wrote the leg record without its self-hash.
- **`ready_sha256` as the file hash** (s4 ×1, fix_cases ×1): it is now the ready record's self-hash.
- **Unbound rehearsal legs** (s8 ×7): the R1/R2/R3 fixtures did not record `frozen_record` / `inject`, so v8 refused.
- **No pilot dossier** (s8 ×2): `amend` now runs the full pilot gate, which needs the pilots' PASS dossier.

## My own test defects found in this round (class (c), both fixed)

- My new dossier-resume test looked for the STOP line in stderr only. The sequencer logs it to stdout. The test now reads both streams; which stream the sequencer uses is the candidate's choice.
- My new shell-parsing test looked up values by variable name. `credential_values`' keys are the candidate's labels, so the test now compares the value set.

## Tests touched or added (all tagged post-reveal 3h)

**Fixtures**
- `b2_frozen_support.py` `not_started_leg_root`: `leg.json` is sealed.
- `b2_frozen_add_support.py` `write_leg`:
  - `ready_sha256` is the ready self-hash;
  - the `p426_dnf` entries are sealed and carry `load`;
  - new `dnf_engaged` knob.

**Amended tests**
- s4 `test_new_the_done_hook_reconciles_writes_the_item_record_and_accepts`: `ready_sha256` is the self-hash.
- fix_cases `test_fix_p21_p22_an_invalidated_done_writes_its_item_record_with_the_ready_files_sha256`: same change. The name is kept for its finding id; the docstring is updated.
- s9 `test_new_a_main_record_with_an_absolute_path_fails_the_harvest`: re-seals after editing, so only the path is wrong.
- s7 `test_new_the_p426_dnf_record_carries_the_section_16_1_fields`: adds `load` is an int, and the `chain.json` entry equals its sidecar.
- s7 `test_new_the_rehearsal_runs_the_smoke_shape_of_s1s_p426_python_order`: `frozen_record` equals `{$STACK_WORKDIR/records/rehearsal.json, its sha256}`, and `inject` is None.
- fix_cases R2 and R3 injection cases: `chain.json` `inject` equals `reconcile-mismatch` / `stall-kill`.
- s8 `leg_root_with`, `_v8_argv` and the manifest locations:
  - every rehearsal leg is bound to its manifest;
  - manifests move under `<tmp>/wd` so the recorded path is portable.
- s8 `test_new_the_amendment_raises_the_settle_bound_over_both_pilots`: writes the pilot dossier through the pinned `p426_receipt.write_dossier` and asserts `pilot_dossier_sha256`.

**New tests**

| File | Test | Rule covered |
|---|---|---|
| s4 | `an_on_item_with_no_judgeable_request_is_unengaged_never_accepted` | Unengaged ON item |
| s4 | `a_kill_with_a_trailing_failed_line_but_no_in_flight_marker_is_off_table` | In-flight marker (kill) |
| s4 | `a_dnf_with_a_trailing_failed_line_but_no_in_flight_marker_is_systemic` | In-flight marker (DNF) |
| s5 | `a_kv_or_tq_name_off_the_exact_allowlist_is_a_credential` (×5) | Exact `KV_*` / `TQ_*` allowlist |
| s5 | `a_stack_defined_kv_name_is_on_the_exact_allowlist` (`KV_KEY_BITS`, which the fork's server defines) | Exact allowlist |
| s5 | `config_assignments_are_parsed_shell_style` | Shell-style config parsing |
| s5 | `an_unparseable_credential_keyed_config_line_refuses_naming_the_key_never_the_value` | Shell-style config parsing |
| s5 | `the_bearer_format_matches_the_quoted_and_json_header_forms` (×2) | Bearer header forms |
| s8 | `amend_refuses_without_a_pass_pilot_dossier` (none / FAIL) | Amendment owns the pilot gate |
| s8 | `v8_refuses_a_rehearsal_leg_not_bound_to_its_manifest` (R2 no inject, R3 wrong inject, R1 other manifest) | Rehearsal binding |
| s8 | `v8_does_not_compare_the_rehearsal_manifests_commits_with_its_arms` | Rehearsal binding |
| s9 | `an_immutable_record_without_its_sha256_fails_the_harvest` | Missing hash fails |
| s9 | `a_manifest_run_id_resolving_to_one_run_directory_harvests` (positive control) | Run id resolves to one directory |
| s9 | `a_manifest_run_id_resolving_to_no_or_two_directories_fails_the_harvest` | Run id resolves to one directory |
| s9 | `a_chain_json_dnf_entry_must_equal_its_sidecar` (equal / differs) | `p426_dnf` entry equals sidecar |
| s9 | `a_non_utf8_evidence_file_is_scrubbed_scanned_and_marked_lossy` | Lossy decode |
| s9 | `a_credential_in_a_non_utf8_evidence_file_still_quarantines` | Lossy decode |
| add_sequencer | `a_pair_dossier_found_on_resume_is_reverified_never_trusted` (receipt hash / verdict / seal) | Dossier re-verified on resume |
| add_sequencer | `an_existing_amendment_is_reverified_before_use` | Amendment re-verified |
| add_sequencer | `a_dnf_item_record_is_engagement_checked` (engaged → VALID_WITH_DNF; unengaged → INVALID) | DNF engagement |
| add_sequencer | `a_failure_to_publish_the_run_files_is_exit_4` | Run-file publish exit 4 |

## Where these tests depend on names the spec leaves open

- **Amendment re-verify exit code:** the test accepts rc 1 or 2, because the spec doesn't pin it.
- **Run-id format:** the s9 run-id tests use the candidate's format (`YYYYMMDDTHHMMSS-<12 hex>`).
- **`lossy_decode` value:** the test checks only that the mark is present, not its value.
