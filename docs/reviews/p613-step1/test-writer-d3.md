Both candidates behave as expected, and I'm recommending merge: the fixed candidate passes all 241 p613 tests, and every adopted finding 1–16 has a test that fails on the first candidate and passes on the fixed one.

## Tests amended (class: new-behaviour unless stated)
- **#1** `test_holm_flag_not_raised_when_not_significant` now asserts `sig["flags"]` is exactly `["strict_point_below_-5pp"]` with value −12.5, instead of scraping digits from flag text.
- **#2** `test_md_has_no_composite_or_hours_metric` ignores the sheet's own "- No composite…" disclaimer line and asserts the forbidden strings are absent everywhere else.
- **#3** `test_wall_per_leg` reads `sig["walls"]["<attempt>"]["wall_s"]`: 7200.0 and 5415.0.
- **#4** `test_power_invalid_pair_keeps_quality_and_drops_speed` is renamed `…_marks_speed_descriptive`.
  - It asserts the quality delta is kept and `speed.inference` is False.
  - It asserts the order note says "descriptive", the ratio 0.5 is still present, and there is no decode flag.
- **#5** `test_cross_epoch_noise_floor` now expects the matches (OFF s1.a1 1/8, OFF pilot 0/5, ON s1.a2 6/8) and checks the INVALID and different-schedule attempts are excluded.
- **#6** `test_superseded_namespace_does_not_leak_into_sessions` compares `sig["sessions"]["s1"]` and `["s2"]` directly.
- **#8** `test_coverage_counts_valid_legs` is renamed `test_coverage_lists_valid_legs`: eight legs listed, all VALID, no invalid / pending / mismatch entries.
- **#10** `test_rule3_missing_slot_rejects_both_unshared_keys` is renamed `test_rule3_row_outside_the_planned_slots_refuses`.
- **#7 and #9** are unchanged.

## Tests added
New file `test_p613_fix_round.py` has 29 tests, class reproduces-failure except one invariant test (`test_fix2_arm_fields_are_not_a_plan_difference`). Names:
- **fix 1:** `test_fix1_missing_item_record_refuses`, `…mis_slotted_item_record_refuses`, `…dnf_slot_gets_no_speed_rate`
- **fix 2:** `test_fix2_schedule_difference_rejects_the_pair`, `…arm_fields_are_not_a_plan_difference` (invariant), `…one_sided_keys_listed_with_schedule_reason`, `…seed_mismatch_rejects_only_the_key`
- **fix 3–9, one test each:** `test_fix3_makeup_record_refuses`, `test_fix4_rejected_diagnostic_pair_blocks_the_same_epoch_floor`, `test_fix5_dnf_slot_is_a_flip_over_planned_slots`, `test_fix6_other_decode_rate_source_is_dropped_with_reason`, `test_fix7_row_sha_not_in_harvest_is_never_identical`, `test_fix8_cross_epoch_is_per_arm`, `test_fix9_exactly_minus_5pp_is_not_flagged`
- **fix 10:** `test_fix10_header_sha_is_the_file_bytes`, `test_fix10_compute_takes_the_sha_argument`
- **fix 11:** `test_fix11_coverage_follows_leg_json`
- **fix 12:** `test_fix12_verify_missing_out_dir`, `test_fix12_signals_missing_out_dir_writes_nothing`
- **fix 13:** `test_fix13_other_nonconv_kind_on_only_is_flagged`, `test_fix13_tax_category_is_not_flagged_twice`
- **fix 14:** `test_fix14_dnf_row_sidecar_is_not_read_as_rows`, `test_fix14_dnf_item_record_is_not_an_item_record`
- **fix 15:** `test_fix15_expect_longer_than_names_refuses`, `test_fix15_expect_count_mismatch_refuses`
- **fix 16:** `test_fix16_strict_point_flag_items_and_md`, `…acceptance_flag_items_are_the_low_items`, `…decode_flag_items_are_the_slow_items`, `…tax_flag_items`

These read the sheet by its now-known layout (for example `sig["sessions"]["s1"]["speed"]["primary"]`).

Every finding has a reproducible failing case, so none is checked by inspection only. A one-sided key without a schedule difference cannot occur: with identical schedules, every planned slot is a row or a DNF in both arms. So fix 2's one-sided case is tested with schedules that plan different slots, which also rejects the pair.

## Runs (241 tests each)
Run order was baseline, first candidate, fixed candidate.

| Run | Summary line (verbatim) |
|---|---|
| Baseline (no candidate) | `21 failed, 25 passed, 195 errors in 10.78s` |
| First candidate | `30 failed, 211 passed in 65.05s (0:01:05)` |
| Fixed candidate (left applied) | `241 passed in 66.34s (0:01:06)` |

First-candidate failures: the 27 fix-round tests that fail there, plus `test_coverage_lists_invalid_leg` (#7), `test_coverage_lists_valid_legs` (#8, rewritten for the fixed layout) and `test_rule3_seed_mismatch_rejects_the_key_only` (#9). The two fix-round tests that pass on the first candidate are `test_fix2_arm_fields_are_not_a_plan_difference` and `test_fix13_tax_category_is_not_flagged_twice`; both are regression guards.

Related suites on the fixed candidate (`bench/tests/test_stats.py`, `test_compare_predictor.py`, `test_p426_*.py`), verbatim:

`2 failed, 339 passed in 11.71s`

The 2 failures are the same ones as in the previous delivery: `test_p426_plan.py::test_k3_round3_the_frozen_builds_qualify_accepts_the_planned_argv` and `test_p426_watcher.py::test_the_real_watcher_imports_bench_ticks_and_stops`. Both fail because the copy has no `.venv-bench`. The full suite was not run, per the brief.

## Per-finding verdict on the fixed candidate
| # | Verdict | Note |
|---|---|---|
| 1 | Fixed | |
| 2 | Fixed, with a limit | The plan hash drops `predictor` and `draft_kind`, and their values are not checked, so a wrong value would pass. Designer accepted this. |
| 3 | Fixed | |
| 4 | Fixed | |
| 5 | Fixed | |
| 6 | Fixed | |
| 7 | Fixed | |
| 8 | Fixed | |
| 9 | Fixed | |
| 10 | Fixed | |
| 11 | Fixed | |
| 12 | Fixed, with a limit | Both files are written to temporaries and then renamed one after the other, so a rename failure on the second could leave the first in place. |
| 13 | Fixed | |
| 14 | Fixed | |
| 15 | Fixed | |
| 16 | Fixed | |

Nothing from the earlier rounds regressed. The golden numbers (strict 42 / 41 / 41 / 42 and the same-epoch noise floor) and byte-identical regeneration still pass.

Two things the fix round changed are worth knowing:
- `compute_a7` now refuses when `sequence.json` records any make-up leg. Make-up substitution is not implemented in step 1.
- Coverage gains a `rejected` category (a valid leg whose pair B8 rejected) and a `state_mismatch` list.

## Verdict
**Merge.** No fixes are required. Two minor points for the designer: the unchecked `predictor` / `draft_kind` values (fix 2) and the non-atomic rename pair (fix 12).