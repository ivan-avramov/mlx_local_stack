I wrote 112 tests in three new files. On the baseline, 79 fail and 33 pass, and none are errors. I did not run any of the new-behaviour tests against an implementation. All the "exercises new behaviour" tests and the launcher-fix tests (the "reproduces" class) fail at the flag-rejection point, so the later parts of their driver and worker harnesses are unproven until a candidate exists.

**Command and summary**
`<fork>/.venv/bin/python -m pytest -q -p no:cacheprovider mlx_vlm/tests/test_p658_*.py` gave `79 failed, 33 passed, 2 warnings in 26s`. I touched no file outside `mlx_vlm/tests/test_p658_*.py`, and `git status` shows only those three new files and the untracked `.p658-material/`.

**`test_p658_engagement_only.py`** (driver tests through the real `qualify.main`, reusing the P475a/P542 rig; the first body line of each test is the `# class:` comment)

| Test (parametrization) | Class | Baseline |
|---|---|---|
| `engagement_only_without_kv_arm_refuses_before_the_lock` (×3) | new behaviour | fail |
| `engagement_only_without_predictor_on_refuses_before_the_lock` (×2) | new behaviour | fail |
| `engagement_only_with_a_p369_summary_refuses_before_the_lock` (×2) | new behaviour | fail |
| `engagement_only_on_an_arm_registry_serving_the_entry_mtp_off_refuses` | new behaviour | fail |
| `engagement_only_refuses_a_non_empty_delta_arm_whose_entry_is_mtp_off` (×2) | new behaviour | fail |
| `engagement_only_keeps_the_one_entry_rule` | new behaviour | fail |
| `engagement_only_keeps_the_p475_pick_rule` (×3) | new behaviour | fail |
| `engagement_only_keeps_the_classify_kv_arm_rule` (×3) | new behaviour | fail |
| `each_arm_serves_mtp_on_exactly_as_committed_with_no_summary` (×10) | new behaviour | fail |
| `the_served_argv_carries_the_mtp_flags_and_the_arms_kv_flags` (×10) | new behaviour | fail |
| `a_tampered_served_argv_fails_the_entry_and_runs_no_job` | new behaviour | fail |
| `the_registry_changing_during_the_job_still_fails_the_entry` | new behaviour | fail |
| `the_target_manifest_is_still_judged_against_the_arms_expected_manifest` | new behaviour | fail |
| `the_engagement_job_is_todays_one_request_plus_the_drafter_flag` (×2) | new behaviour | fail |
| `a_k3_conforming_drafter_manifest_gives_no_problem_and_is_carried_in_the_state` | new behaviour | fail |
| `a_quantized_drafter_leaf…`, `a_turboquant_drafter_leaf…`, `a_continuous_batching_drafter_leaf…` | new behaviour | fail (×3) |
| `a_drafter_cache_that_does_not_match_its_template_fails_the_entry` (×2) | new behaviour | fail |
| `no_drafter_manifest_recorded_fails_the_entry`, `a_worker_that_ignores_the_job_field_fails_the_entry` | new behaviour | fail (×2) |
| `an_empty_absent_or_malformed_drafter_manifest_fails_without_raising` (×14) | new behaviour | fail |
| `the_report_declares_engagement_only_and_certifies_false` (×3) | new behaviour | fail |
| `a_failed_engagement_run_still_declares_itself_uncertified` | new behaviour | fail |
| `command_problems_still_refuses_a_tampered_mtp_on_argv` (×4) | invariant | pass |
| `command_problems_refuses_a_wrong_kv_width_for_the_arm` | invariant | pass |
| `the_no_flag_kv_arm_job_…` and `the_plain_committed_run_does_not_ask_for_the_drafter_manifest` | invariant | pass (×2) |
| `without_the_flag_the_drafter_manifest_is_not_judged` | invariant | pass |
| `request_problems_does_not_judge_the_drafter_manifest` (×4) | invariant | pass |
| `the_no_flag_kv_arm_report_is_unchanged`, `the_plain_report_is_unchanged` | invariant | pass (×2) |
| `without_the_flag_a_non_empty_delta_predictor_on_still_refuses_as_uncertified` (×3) | invariant | pass |
| `without_the_flag_predictor_on_still_needs_a_p369_summary` (×2) | invariant | pass |

**`test_p658_launcher.py`**
- Fail on baseline:
  - **reproduces a failure the spec fixes:** `a_p475_kv_ancestor_is_not_foreign`, `the_whole_launcher_chain_is_exempt_together`, `an_ancestor_p475_kv_exempts_only_itself_not_a_same_argv_sibling`, `unrelated_refused_processes_still_refuse_beside_a_p475_kv_ancestor`, `real_topology_a_p475_kv_parent_is_exempt_a_p475_kv_sibling_is_not`.
  - **new behaviour:** `the_launcher_modules_are_exactly_the_three_named`.
- Pass on baseline (preserves an invariant):
  - `a_p475_kv_non_ancestor_still_refuses`
  - `any_other_bench_ancestor_still_refuses` (×6)
  - `the_caller_itself_is_never_foreign_even_as_p475_kv`
  - `real_topology_another_bench_parent_still_refuses_beside_a_p475_kv_sibling`
  - `real_topology_the_p426_launcher_is_still_exempt`
- The real-topology tests ran, so `psutil` is present.

**`test_p658_worker_drafter_manifest.py`**
These drive the real `worker.run_job` and `qualify_request` with a faked server boundary.
- New behaviour, fail with `KeyError: 'drafter_manifest'`:
  - `the_record_gains_the_drafters_observed_and_template_manifests`
  - `the_drafter_cache_is_read_after_the_response_and_before_the_session_is_released`
  - `a_quantized_drafter_leaf_is_recorded_as_it_is`
  - `a_drafter_with_no_cache_after_the_request_records_an_empty_observed_list`
  - `the_target_part_of_the_record_is_the_same_with_and_without_the_field`
- Invariant, pass:
  - `without_the_job_field_the_record_has_exactly_todays_keys`
  - `a_falsy_job_field_records_nothing` (×3: `False`, `None`, `0`)

**Spec ambiguities and how I resolved them**
- **A1: where `drafter_manifest: true` lives.** The spec says "the job carries" it, so I put it at the top level of the job dict, not inside `requests[0]` or `expect`. If the implementer puts it elsewhere, the worker tests and `test_the_engagement_job_is_todays_one_request_plus_the_drafter_flag` will fail for that reason.
- **A2: no-flag jobs.** The spec says "set only under `--engagement-only`". I assert `not job.get("drafter_manifest")` for no-flag jobs, so an absent key and `False` both pass.
- **A3: refusal precedence.** The spec doesn't say which message wins when `--engagement-only` lacks `--kv-arm` and also carries a `--p369-summary`. My tests avoid combining them. The summary-refusal test uses `--kv-arm --predictor on`.
- **A4: where the drafter is judged.** The spec says `request_problems` is unchanged, so I test the drafter check only through the driver's entry problems. I assert `request_problems` ignores any `drafter_manifest`.
- **A5: problem wording.** The spec fixes only `"no drafter cache manifest"` exactly. For `drafter_problems` failures I match on substrings that come from the existing `kvmanifest.drafter_problems` text (`"drafter cache"`, `"continuous-batching"`).
- **A6: `reference` under the flag.** `reference` is `None` even when a reference peak exists. The tests make one exist, so a leftover comparison would be caught, and they assert `capacity_gb` is still recorded. That last assertion is my reading of "no capacity comparison is made", not spec text.
- **A7: failed entries.** For a failed entry the tests expect `status == "FAILED"` and exit code 1 (matching today's `exit_code`) and `drafter_manifest` carried in the state when it was recorded. They also expect `engagement_only` / `certifies` at the top level of the report even on failure, which the spec implies but doesn't state.
- **A8: all ten arm cells.** Acceptance 2 asks for five arms on the uniform pick and one non-empty delta on pick A. I parametrized all ten arm cells (five arms × two picks).
- **A9: PICKS drafter shape.** The success path depends on the real `orchestrate.PICKS[name]["drafter"]` shape, which the harness doesn't fake.
- **A10: test helpers.** I import one private helper (`_references`) from `test_p475a_qualify_driver`, and the rig fixtures. I pin no private function names beyond the spec's Interfaces section.
