Verdict: **fix then merge**. The candidate meets the spec, and the only required fix is a one-line amendment to the implementer's test, which the designer makes.

## Test outcomes on the candidate

I ran my file, the implementer's `test_m76_b8_kinds_impl_planned.py` and `test_m76_b3_impl_wave1.py` together: 72 passed, 2 failed, matching the designer's run. After amending one of my tests (below), my file passes 47 of 47. I did not re-run the other two files after that edit, and I did not run the full stack suite.

| File | Baseline | Candidate |
|---|---|---|
| `test_m76_b8_kinds_fe_wave1.py` (47 tests) | 25 fail (all class a), 22 pass | 47 pass after the amendment |
| `test_m76_b8_kinds_impl_planned.py` (14 tests) | 8 fail (implementer's report) | 14 pass |
| `test_m76_b3_impl_wave1.py` (12 tests) | 12 pass | 11 pass, `test_main_kv_refuses_v_before_anything_runs` fails (rc 1, expected 2) |

- **Class (b) tests:** all 22 pass on both sides, the mtp golden included (it ran, not skipped). The golden is unchanged, and `dropped` does not leak into the mtp record.
- **Class (c) reading:** the candidate does what I assumed. Present m1 legs stay `not_run` under the default, and `test_present_m1_legs_stay_not_run_under_the_default` passes.
- **Amended test not re-run on the baseline:** I did not re-run the amended sequencer test on the baseline, since the candidate is now applied. It cannot pass there, because `kv_w1_kinds` doesn't exist, so it stays class (a).

## Amended test

`test_kv_sequencer_default_axes_are_the_planned_kinds` was my seam guess, not a candidate defect. I stubbed `main_kv` and read `args.axes`. The spec says the default is `kv_w1_kinds(build)`, and the build is only validated inside `main_kv` (`p426_wave1.py:302-303`), so the default is correctly resolved there. I now stub `schedule_kv` and observe the axes it receives, with the same assertion as before: `("math500","cjudge","vision","reasoning","longctx")`. The explicit `--axes m1,cjudge` test is unchanged and still passes.

## The implementer's point 1

`test_main_kv_refuses_v_before_anything_runs` fails because of the spec, not because of a defect. Its second half passes `n16,x` with no `--axes` and expects the "stage-2 record" refusal. That refusal comes from X's `m1` leg, which the old default included and the spec's new default drops. Preflight now passes, and the sequencer stops at the missing frozen record (rc 1, and `claim_out` has already created `out`).

The test's intent is the M1 certified-by refusal, so the designer should add `--axes m1` (or `--axes m1,cjudge`) to that call. I did not edit it. The first half (the `x,v` refusal) still passes.

## Review findings

- **R1, point 2 (`dropped` only under `kinds=None`): acceptable, with a spec gap.**
  - **Behaviour:** with explicit kinds the record carries `dropped: {}` and no dropped-kind `not_run` entries (`p426_verify.py:1910-1914`, `1965-1967`). That is consistent with the spec's "`kinds=None` → `kv_w1_kinds(build)`" and keeps the existing `kinds=()` test (`not_run == []`) passing.
  - **Residual gap:** a caller who spells out the planned tuple explicitly gets no `m1/*` in `not_run`. My tests only compare pair keys for that case, so they don't catch it.
  - **Recommendation:** keep as is, and add a line to the spec stating it.
- **R2, point 3 (`not_run` order): fine.** Tier-2 entries come first, then dropped kinds (`m1/b1`, `m1/b2`). My tests compare sets only, so they don't depend on the order.
- **R3, point 4 (import placement): works, but the layering is inverted.** `p426_plan.kv_w1_kinds` imports `KV_W1_KINDS` from `p426_verify` (`p426_plan.py:497`), and `p426_verify` already imports `p426_plan` lazily. There is no cycle, but the plan now depends on the verifier. Cleaner would be to define the kinds tuple in `p426_plan` and have `p426_verify` import it. Non-blocking.
- **R4, the ids guard is by constant, not by ids.json contents.** The guard is `kind in KV_ITEM_KINDS` (`p426_verify.py:1930`), not "has items in `ids.json`" as the spec words it. It is equivalent today, because `load_kv_ids` only loads `KV_ITEM_KINDS`, and it can never raise `KeyError` for `m1`. This is a wording deviation only.
- **R5, a side effect of validating kinds first.** The unknown-kind check now runs in its own loop before any leg (`p426_verify.py:1923-1926`), so an unknown kind refuses before any other kind's missing-leg refusal. This is harmless and arguably better. My `test_unknown_explicit_kind_refuses` passes.
- **R6, the bad-build refusal is covered.** `verify_wave1_kv(..., kinds=None, build="zz")` turns `ValueError` into `RefusalError` (`p426_verify.py:1906-1910`). The implementer's `test_unknown_build_refuses` passes. The `kv_w1_*` functions raise `ValueError`, which my tests accept.
- **R7, `main_kv` is correct.** It applies the default after `check_kv_build` inside the `try`, so a bad build returns rc 2, and an explicit `--axes` is untouched (`p426_wave1.py:302-303`). The mtp default is unchanged (`p426_wave1.py:419-420`).

## Deviations from the spec

- The `dropped` and dropped-kind `not_run` behaviour applies only under the default kinds (R1). The spec is silent on explicit kinds.
- The ids guard uses a constant (R4).
- No other deviations. All of acceptance 1 passes, including the missing planned leg, an explicit `kinds=` with m1 legs, and the mtp golden.

## Before merge

1. The designer amends `test_main_kv_refuses_v_before_anything_runs` to pass `--axes m1` on the second call.
2. Acceptance 3 is still open: nobody has a complete full-suite result, and the implementer's broad run was cut off at about 74%. The two `test_local_gate.py` failures the implementer found on both baseline and fixed code are environmental, with no `.venv-bench` in the copy.
3. Optional: R3 and a spec sentence for R1.