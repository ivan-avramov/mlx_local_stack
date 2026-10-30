# Delivery 2d (same session): the s1–s5 fix pass — amend two test defects, re-run, add failing-case tests

A fresh implementer fixed the adopted findings of s1–s5 (C239): the fix is `.b2-fix-s1-s5.diff` (on top of s5), its report `.b2-fix-report.md`. A clean copy (baseline + s1–s5 fixed + `frozen5`) runs with `../bin/run_candidate_fix_tests.sh <paths>`.

Designer rulings on the implementer's three open points:
1. `test_b2_frozen_s5_receipt.py::test_new_a_receipt_whose_seal_does_not_verify_is_a_problem` is a test defect (your tamper sets `PWD` to the value it already has): amend it so the seal really breaks.
2. `test_b2_frozen_add_pair.py::…second_leg_of_a_pair_passes_the_gate_and_runs` and `…same_credential_keys_with_other_values_pass_the_gate`: the P32 ruling stands (the probe environment is the chain's launch environment, `ops.env_base()`); the defect is the fixture's — its `env_base` carries arm-specific fake keys (`B2_DRAFT`, `FAKE_REGISTRY_SHA`) a real launch environment does not have after canonicalization. Amend the fixture.
3. The flat-layout DNF refusal (`validate_partial` applies the per-arm `arm_row_problems` to flat tg1 rows) is a real defect, queued for the final fix round; leave `test_b2_frozen_add_ledger.py::…dnf_is_ledgered_in_its_place…` as it is (it should stay red until then).

Do:
1. Amend 1 and 2 (list every test touched); run on the baseline (support checks must pass).
2. For each finding the report says fixed, write a test that reproduces its failing case (class: reproduces a failure the specification fixes) in a NEW file `test_b2_frozen_fix_cases.py` (fixtures in `b2_frozen_fix_support.py` if needed) — e.g. a kill-key row that is not a kill (P16), a real s2 abort manifest DNF (P17), a router replaced with the same config (R4), a missing seam (P29), an argv with an extra leading token (P33). Run them on the baseline (expected to fail) — the designer installs them in the candidate copy after freezing; then report which of the fixed findings you could NOT reproduce as a test and why.
3. Run the whole frozen set (your current files) on the fixed candidate copy, which still holds `frozen5`: report the result and classify every failure as before.
4. Review the fix diff for correctness and for anything it does beyond the findings: findings with file and line.

Report facts only; list every test touched.
