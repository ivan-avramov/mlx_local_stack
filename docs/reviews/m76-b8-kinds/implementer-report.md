The fix is in and acceptance 1 passes, but acceptance 3 isn't met: one existing test that passes on the baseline now fails, because the spec's new kv default `--axes` breaks it. I didn't edit it, since the test directory is read-only for me. Nothing is committed.

## Files changed
- `benchmark/bench/p426_plan.py`: adds `KV_W1_DROPPED`, `kv_w1_dropped(build)` and `kv_w1_kinds(build)`. For `s3` the kinds are math500, cjudge, vision, reasoning, longctx, and the dropped entry is `{"m1": "C352: …"}`. A non-kv build raises `ValueError`.
- `benchmark/bench/p426_verify.py`:
  - New constant `KV_ITEM_KINDS`, which `load_kv_ids` now uses.
  - `verify_wave1_kv` and `verify_all_kv` now default to `kinds=None`, meaning the build's planned kinds; a bad build is refused.
  - `ids[kind]` is indexed only for kinds that have items, so `m1` is checked from its leg evidence only.
  - Dropped kinds show up in `not_run` as `m1/b1` and `m1/b2`, and the record gets a new `dropped` field.
  - `verify_all_kv` gains a `build=` argument.
- `benchmark/bench/p426_wave1.py`: with `--lever kv`, the default `--axes` is now `kv_w1_kinds(build)`, set in `main_kv` once the build has been checked. The mtp default is unchanged.
- New test file `benchmark/bench/tests/test_m76_b8_kinds_impl_planned.py` (14 tests). It runs on the real committed `m76/ids.json`, which has no `m1`, with synthetic s3 legs for all five planned kinds and both blocks. It covers:
  - the default record and the CLI `all --lever kv` path;
  - a missing planned leg still being refused, once for each of the five kinds;
  - explicit `kinds=` including `m1`: verified when its legs exist, refused (not a `KeyError`) when they don't;
  - an unknown build being refused;
  - the sequencer's default axes.

## Commands and counts
- **Red first:** `../fe_test.sh stack bench/tests/test_m76_b8_kinds_impl_planned.py` gave 8 failed, 6 passed. The failures were `KeyError: 'm1'` at `p426_verify.py:1921`, the missing `kv_w1_kinds`, and the sequencer default containing `m1`. A fixture check (explicit planned kinds) passes on the baseline, so the red comes from the `m1` handling, not the fixture.
- **After the fix:** the same file gives 14 passed.
- **Full suite:** `../fe_test.sh stack` was stopped by the 60-minute background limit at about 74%, with failures scattered through it. I have no complete full-suite result and no full baseline run.
- **What I ran instead:** the 35 test files and directories that import `p426_plan`, `p426_verify` or `p426_wave1` (the mtp golden and `test_m76_b3_impl_verify` included), on the fixed code and on the baseline code (HEAD versions written in temporarily, fixed files restored afterwards; diff confirmed).

| Test | Baseline | Fixed |
|---|---|---|
| `test_local_gate.py` (2 tests) | fail | fail |
| `test_m76_b8_kinds_impl_planned.py` | 8 fail | 14 pass |
| `test_m76_b3_impl_wave1.py::test_main_kv_refuses_v_before_anything_runs` | pass | **fail** |
| Everything else in the set, mtp golden included | pass | pass |

The two `test_local_gate.py` failures are environmental: the copy has no `.venv-bench/bin/python`.

## Deviations and questions
1. **The new failure.** The second half of `test_main_kv_refuses_v_before_anything_runs` runs pair `n16,x` with the default axes. It expects the refusal *"stage-2 record"*, which only happened because the old default included `m1` (X's `m1` leg needs `--certified-by`). With the spec's default, preflight now passes. The sequencer then stops at the frozen-record check with rc 1 instead of 2, and it creates `out` along the way, because `claim_out` writes `.build`. My recommendation is that the designer adds `--axes m1` to that call, since its intent is to test the `m1` certified-by refusal. The alternative is to keep `m1` in the default, which contradicts the spec.
2. **`dropped` with explicit `kinds=`.** I only apply `dropped` and the dropped-kind `not_run` entries when `kinds=None`. With explicit kinds the record carries `dropped: {}` and nothing extra in `not_run`. This keeps the existing `kinds=()` test, which expects `not_run == []`, passing. The spec doesn't say what should happen here.
3. **Order of `not_run`.** Dropped-kind entries go after the tier-2 entries, so existing `not_run` prefixes don't change.
4. **Where `kv_w1_kinds` gets its list.** It imports `KV_W1_KINDS` from `p426_verify` inside the function, so the list isn't defined twice and there's no import cycle at module level.