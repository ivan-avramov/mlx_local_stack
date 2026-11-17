I wrote the behaviour tests for acceptance 1, and 25 of the 47 fail on the baseline, as intended. The other 22 pass on the baseline and are the guards that must stay green. I did not run the whole stack suite, so acceptance 3 is untested.

I ran `../fe_test.sh stack bench/tests/test_m76_b8_kinds_fe_wave1.py` from the `stack` directory, which only accepts paths relative to `benchmark/`. All 25 fail for the reason the spec gives:
- **`AttributeError` (6):** `p426_plan.kv_w1_kinds` and `kv_w1_dropped` do not exist yet.
- **`TypeError` (1):** `verify_all_kv` has no `build` keyword.
- **`KeyError: 'm1'` (17):** `verify_wave1_kv` indexes `ids['m1']` at `p426_verify.py:1921`, including the longctx missing-leg cases and every explicit-`m1` case.
- **Other (1):** `p426_wave1 --lever kv` still defaults `--axes` to every axis, so `m1` is included.

Files created, all under the paths the brief names:
- `benchmark/bench/tests/test_m76_b8_kinds_fe_wave1.py`
- `benchmark/bench/tests/fixtures/m76_b8_kinds_fe/mtp_b8_golden.json`

Each test has its class (a), (b) or (c) in a comment above it.

**What the tests build on.** The tree is synthetic, with the committed `m76/ids.json` copied byte for byte. It has every planned leg for both arms at tier 1 (math500, cjudge, vision, reasoning, longctx) and no M1 leg. A passing test proves the fixture is sound: with the planned kinds passed explicitly, all 10 planned pairs verify on the baseline. A second passing test proves the M1 fixture legs are sound, by injecting an empty `m1` entry into the ids index.

**Classes**
- **(a), the 25 failing:**
  - the two `p426_plan` interfaces;
  - default kinds verifying the five planned kinds;
  - `m1/b1` and `m1/b2` in `not_run` alongside the existing tier-2 entries, and `wave1.dropped == {"m1": reason}`;
  - the `build` keyword;
  - the public CLI emitting the record;
  - a missing planned leg refusing, for each kind, in both arms and blocks;
  - explicit `kinds=` including `m1` verifying present legs, and refusing when a leg is missing;
  - the kv sequencer's default `--axes`.
- **(b), the 22 passing:**
  - the mtp golden;
  - the mtp CLI refusals and axes constants;
  - the real-ids preconditions;
  - an unknown kind refusing;
  - the tier-2 `not_run` entries;
  - a rejected pair not being a refusal;
  - the frozen-record and deny-list checks;
  - an explicit `--axes` winning;
  - the missing-leg refusals for math500, cjudge, vision and reasoning (these pass on the baseline for the right reason).
- **(c):** `test_present_m1_legs_stay_not_run_under_the_default` is a reading of the spec I'd like a reviewer to check. It says that m1 legs which are present are still recorded as `not_run` under the default kinds, not verified. I took that from "verifies exactly the kinds the stage planned, records every unplanned kind as not_run".

**Two readings of the spec to confirm**
- I assume `verify_wave1_kv` itself puts `m1/b1` and `m1/b2` in `not_run` when called with its default kinds, not only `verify_all_kv`. If you intend `verify_all_kv` alone to add them, `test_wave1_record_lists_m1_not_run` needs adjusting.
- For an unknown build, I accept `ValueError` or `RefusalError`, since the spec only says "refuses".

**mtp golden.** It is the sha256 of `p426_verify.dumps(verify_all(...))` on the committed p426 data, plus pair counts and top-level keys, computed on the baseline. It ran rather than skipped (10 of 10 Wave 1 pairs accepted). Regenerating it needs a `WRITE_GOLDEN` sentinel file beside it, which the test consumes. That file is gone now.

**Left over from earlier runs.** The pytest temp directories are under `tw/scratch/pytest-of-<user>/`. I never printed or logged environment variables or credentials.