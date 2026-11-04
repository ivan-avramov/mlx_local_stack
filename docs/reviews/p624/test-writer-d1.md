I wrote 26 tests in `benchmark/bench/tests/test_local_gate_ran_skips.py` and ran them on the baseline: 17 fail, 9 pass. The 17 failures are all new-behaviour tests. I did not run the real gate, and I changed no other file.

The file imports `Runner` and `_repo` from `bench.tests.test_local_gate`. Its `JunitRunner` subclass extends the junit writer to emit passed, failed and errored testcases. The `env` fixture is copied, with no baseline file by default.

## Run summary

Command: `../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_local_gate_ran_skips.py bench/tests/test_local_gate.py`, run from `benchmark/`.
- Both files together: `17 failed, 61 passed in 34.00s`.
- New file alone: `17 failed, 9 passed`.
- Existing `test_local_gate.py`: all 52 pass, including `test_a_skip_list_unequal_to_the_baseline_fails`.

Failure kinds:
- **Helper missing:** 4 tests fail with an `AttributeError`, because `G.ran_and_passed_from_junit` does not exist.
- **`baseline_skips_ran` missing:** 3 tests fail with a `KeyError`, because the key is not in the receipt.
- **Wrong verdict or problem text:** 10 tests fail on an assertion. Cases where a baseline entry ran and passed get FAIL, but they should get PASS. Cases where an entry was absent, failed or errored get `skip list != baseline: ...` instead of `baseline skip neither skipped nor passed: [...]`.

## Tests

**reproduces-failure**
- `test_a_baseline_skip_that_ran_and_passed_no_longer_fails_the_gate`: this is the goal case (W−S ran and passed), which is FAIL today and should be PASS.

**new-behaviour**
- `test_helper_returns_none_for_an_absent_junit`
- `test_helper_lists_only_testcases_with_no_skipped_failure_or_error_sorted`
- `test_helper_on_a_junit_without_passed_testcases_is_an_empty_list`
- `test_helper_ids_are_classname_double_colon_name_like_the_skipped_helper`
- `test_equal_skip_list_and_baseline_passes_with_an_empty_baseline_skips_ran`: S == W gives PASS and `[]`.
- `test_empty_baseline_and_no_skips_passes_with_an_empty_baseline_skips_ran`
- `test_a_passed_test_outside_the_baseline_is_not_recorded`
- `test_a_baseline_skip_that_ran_and_passed_is_recorded_sorted`: it also checks that `skipped_tests` is unchanged.
- `test_a_partial_overlap_records_only_the_baseline_entries_that_ran`
- `test_baseline_blank_lines_are_ignored`
- `test_a_passed_test_with_the_same_name_in_another_class_does_not_count`
- `test_a_baseline_entry_absent_from_the_junit_fails_with_the_new_problem`
- `test_the_new_problem_lists_every_such_entry_sorted`
- `test_a_baseline_entry_that_failed_fails_the_gate_even_with_pytest_rc_0`
- `test_a_baseline_entry_that_errored_fails_the_gate_even_with_pytest_rc_0`
- `test_one_failed_entry_among_ran_and_passed_ones_fails_naming_only_it`

**invariant** (all 9 pass at the baseline)
- `test_skipped_helper_ignores_passed_failed_and_errored_testcases`
- `test_a_baseline_entry_missing_from_the_junit_fails`
- `test_an_unbaselined_skip_fails_with_todays_message`: it checks the exact `+[...] -[]` text.
- `test_an_unbaselined_skip_fails_even_if_a_baseline_entry_ran_and_passed`
- `test_an_unbaselined_skip_with_an_absent_baseline_entry_fails_with_the_skip_list_message`
- `test_no_baseline_file_keeps_todays_problem`
- `test_a_failing_pytest_step_fails_without_the_skip_rule`
- `test_a_pass_with_ran_skips_keeps_the_six_steps_and_the_scratch_is_removed`
- `test_the_policy_digest_does_not_depend_on_what_ran`

## Spec ambiguities and the reading I tested

1. **`baseline_skips_ran` on a FAIL receipt.** "Always present" could cover FAIL receipts too. I assert the key only on PASS receipts and leave its FAIL content untested.
2. **S−W non-empty and W−S entries both bad.** The spec does not say whether the new problem is also emitted. I assert only that the `skip list != baseline: +[...]` message appears. I do not assert on the absence of the new problem.
3. **The `-[W−S]` part of the old message when a W−S entry ran and passed.** I read "today's message, unchanged" as W−S still going into the `-[...]` part. I assert only the `+[...]` prefix in S−W cases, so either reading passes.
4. **New-problem format.** I assert the literal `baseline skip neither skipped nor passed: ['a', 'b']`, with Python list repr and sorted entries, taken from the spec's `[<sorted such w>]`. It is also the only test that pins that repr.
5. **A testcase with both `<skipped>` and a failure or error child.** The rule makes it not-passed (P) and also skipped (S). The spec does not address this and I did not test it.
6. **A failed entry among passed ones.** `test_one_failed_entry_among_ran_and_passed_ones_fails_naming_only_it` reads the rule as listing only the not-passed entries in the new problem.
