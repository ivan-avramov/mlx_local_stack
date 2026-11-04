**Verdict: fix then merge.** All three fixes work as specified, but fix 1 as written would refuse every `auto`-attention entry on a real worker (P1 below). The suites don't show this because they mock the worker.

## 1. What delivery 3 changed (all in my copy; the files equal `frozen-d3`)
**Amended tests**
- `control()` in `test_p475a_qualify_driver.py` now takes `arm`, and the 7 third-entry and unknown-entry tests call `control(rig, kv.FIXTURE, "TQ4")`. Class: test-defect fix; the tests stay new-behaviour.
- The AST test is replaced by `test_quantized_kv_start_is_not_an_arm_key` (invariant). The behaviour stays covered by the existing non-zero-start refusal tests.
- `test_predictor_on_serves_the_committed_mtp_on_arm_registry_without_an_overlay` was narrowed to the empty-delta params `fable-N16` and `uniform-TQ4` (new-behaviour). The non-empty params the designer flagged were already gone, so nothing needed amending in this delivery.

**New in `test_p475a_fixround.py` (82 tests)**
- `test_fix1_a_missing_none_negative_or_nonfinite_counter_is_a_problem` (reproduces-failure for zero-required cells, `inf` and string; invariant for fable-N16 with missing/None/negative/NaN).
- `test_fix1_the_right_counter_still_passes` and `test_fix1_the_wrong_but_valid_counter_is_still_a_problem` (invariant).
- `test_fix1_driver_a_record_without_the_counter_fails_the_entry` (reproduces-failure).
- `test_fix2_a_missing_manifest_yields_only_the_manifest_problem` (reproduces-failure for `auto` with forced > 0; invariant for the rest).
- `test_fix2_an_unreadable_counter_is_not_judged_without_a_manifest` (reproduces-failure for `inf` and string).
- `test_fix2_driver_a_no_manifest_record_fails_with_only_the_manifest_problem` (reproduces-failure for `auto`).
- `test_fix3_predictor_on_with_a_nonempty_delta_refuses_as_uncertified` (reproduces-failure) and `test_fix3_the_refusal_is_the_uncertified_arm_not_the_argv_binding` (reproduces-failure).
- `test_fix3_predictor_on_with_an_empty_delta_behaves_as_today`, `test_fix3_an_empty_delta_still_needs_the_certified_argv` and `test_fix3_the_unflagged_binding_refusal_is_the_same_for_the_same_certified_argv` (invariant).
- `test_f3_kv_arm_without_a_predictor_refuses` and `test_f3_kv_arm_predictor_on_without_a_summary_refuses` (invariant).

## 2. Runs on the fixed candidate (verbatim)
```
476 passed, 2 warnings in 66.71s (0:01:06)      # kv_arm + qualify_driver + fixround
698 passed, 2 skipped, 2 warnings in 55.99s     # the nine neighbours
```
No test fails, so there is no test-or-candidate call to make. The designer's 10 failures came from the d1 frozen tests. The 7 known ones were my `control()` defect, and the 3 non-empty-delta params were already removed in delivery 3.

## 3. Fixes 1–3
Fix 1 is resolved against spec v4.1, but the spec itself has a problem (P1 below). Fixes 2 and 3 are resolved.

- **Fix 1.** `qualify.py:652-663`: with the expected manifest known, the counter must be `type is int` and ≥ 0, so missing, None, negative, NaN, `inf`, strings, floats and bools all give a problem. Then the rule is as before.
- **Fix 2.** The whole attention check runs only when `native_attention is not None`, under any policy.
- **Fix 3.** `kv_arm_gate` (`qualify.py:1086`) refuses `--predictor on` with a non-empty delta, with "an MTP-ON KV arm is uncertified; preflight it with --predictor off". The empty-delta path is untouched. The MTP-OFF refusal comes first.

## 4. Findings
**P1. Fix 1 breaks `auto` entries on a real worker. This is blocking.**
- `server/schemas.py:549` omits `sdpa_forced` from the response under `auto` (the comment reads "omitted (not null) under `auto`").
- `worker.py:1587` sets `sdpa_forced=_find_key(response, "sdpa_forced")`, and `_find_key` returns `None` when the key is absent.
- So a live record for the uniform pick (default attention) carries `sdpa_forced: None`. The new rule reports `sdpa_forced None is not an integer >= 0` whenever the manifest is known. That would fail every `auto` entry, including the first P475 pick and today's no-flag runs of `auto` entries.   <!-- allow-shorthand: verbatim helper output -->
- The mocked tests can't see it, because they always put an integer in the record.
- I could not run a live worker, so this comes from code reading only. I recommend a live check on the uniform pick before merge.   <!-- allow-shorthand: verbatim helper output -->
- Suggested change for the designer: under non-fused policies, treat a missing or None counter as 0, or have the worker normalise it. Under `fused_v1` the strict check can stay, but confirm that a 0 count is emitted as `0` and not omitted.
- If the designer relaxes this for `auto`, four of my fix-round tests assert the strict reading for the uniform pick and would have to change: the missing/None cases in `test_fix1_a_missing_none_negative_or_nonfinite_counter_is_a_problem[…uniform-TQ4…]`, the uniform-TQ4 driver test `test_fix1_driver_a_record_without_the_counter_fails_the_entry[…-TQ4]`, and the `missing`/`none` variants of `test_fix2_an_unreadable_counter_is_not_judged_without_a_manifest`.   <!-- allow-shorthand: verbatim helper output -->

**P2. Minor.** `type(forced) is not int` rejects a float such as `640.0`. JSON counters are integers, so I think that's fine.

**P3. Open items.**
- Black and isort have not been run on the candidate or on my tests.
- The earlier delivery-2 notes still apply: the by-hand argv spelling is unverified against the real mlx-serve, and the `auto`-policy and `fused_v1` zero-count behaviour is unverified live.
