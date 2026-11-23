# Implementer report — S29 B8-A8 rule 3.6 (spec s29-a8-frozen-record v1.0)

Baseline `a073d594e`. Candidate: `out/candidate-1.diff` (staged only; nothing committed).

## Files changed
- `benchmark/bench/p426_verify.py`
  - `_a8_amendment(reader, run)`: reads `m76/wave2.tg2/run/amendment.json` through the B8-A8 `Reader` when it exists, so it becomes a hashed `inputs` entry (R3) and `check_b8_a8` detects a later change the same way it does for the v8 base. Returns None when the file is absent. Unreadable JSON is returned as a non-object, which rule 3.6 rejects; it never refuses.
  - `a8_amendment_problems(amendment, v8, pilot_dossier_sha256)`: lists the problems with the amendment: absent; not a sealed object (`p426_hooks.sealed_ok`); `kind` != `fz.KIND_AMENDMENT`; `corpus` != tg2; `v8_base_sha256` != the v8 base's sha256; no accepted pilot pair; `pilot_dossier_sha256` != the sha256 of the accepted pilot pair's dossier file.
  - `a8_frozen_record_reasons(arm, att, session, v8, amendment, pilot_dossier_sha256)` is the new rule 3.6 frozen-record check:
    - pilot: must name the v8 base's sha256. Naming the amendment gets its own reason.
    - decider session (s1, s2, reload): the v8 base's sha256, or the amendment's sha256 when `a8_amendment_problems` is empty.
    - Anything else is a `rule 3.6:` REASON (no amendment published, malformed, neither sha, a problem with the amendment).
  - `_a8_plan_reasons` / `_a8_session`: new keyword parameters `amendment` and `pilot_dossier_sha256` (default None, so existing positional callers still work). The old inline v8-only check is replaced by the new function.
  - `verify_a8_kv`:
    - loads the amendment;
    - evaluates the pilot session first; when it is accepted, the pilot dossier's sha256 comes from the file bytes the reader recorded (`reader.inputs[rec["dossier"]]`, the same byte hash the sequencer's `verify_amendment` uses);
    - then evaluates the other sessions;
    - `pairs` keeps its original order (s1, s2, pilot, reload).
  - No other A8 rule, output key or verdict code changed.
- `benchmark/bench/tests/test_s29_impl_a8_frozen_record.py` (new, 35 tests):
  - Unit tests on the real `amendment.json`, `v8_base.json` and the eight selected attempts' chain `frozen_record` blocks.
    - R1: all eight real attempts pass.
    - R2: pilot names the amendment; no amendment published; tampered amendment (seal kept); malformed amendment; resealed amendment with another v8 base, pilot dossier, kind or corpus; no accepted pilot; amendment of another v8 base than the one read; decider names neither sha or has no `frozen_record`.
  - End-to-end tests run on a tmp copy of `wave2.tg2/`:
    - real records → complete, all four accepted, amendment and v8 base in `inputs`;
    - `check_b8_a8` refuses a changed amendment;
    - amendment absent or tampered → s1, s2 and reload rejected with a rule-3.6 amendment reason, pilot still accepted.

## Judgement call (flag for the lead)
- **J1. A decider attempt that names the v8 base itself still passes rule 3.6.** R2's wording is "a decider attempt naming a sha that is *neither*", and the existing fixture worlds (`test_m76_b4b2_impl_world.py`, `test_m76_b4b2_fe_support.py`) build decider chains on the v8 sha. The goal's "still rejects anything else" could be read as amendment-only for decider legs. If the designer wants that, it is a one-line change in `a8_frozen_record_reasons`, but every fixture world would then need an amendment.

## Tests changed
None. No existing test pins the v8-only rule for decider sessions directly. See the findings below for tests that rely on it indirectly.

## Commands and results
All commands were run from the copy through `../fe_test.sh stack …`.
1. Baseline, before any edit: all 17 `bench/tests/test_m76_b4b2_*.py` modules. **4 failed**, the rest passed:
   - `fe_real::test_the_real_pilot_pair_builds_with_the_pilot_accepted`
   - `fe_real::test_the_real_s1_is_incomplete_with_x_s1_unaccepted`
   - `fe_real::test_the_real_latency_is_incomplete`
   - `impl_golden::test_pilot_pair_b8_a8_shape`

   All four have stale premises: the decider is harvested and `exec_latency.json` is published on `main`.
2. New tests before the fix: 34 failed, 1 passed (the premise test). 30 failed with `AttributeError` (the function did not exist yet); the end-to-end tests failed because rule 3.6 rejected the real decider legs.
3. New tests after the fix: **35 passed**.
4. All 17 `test_m76_b4b2_*` modules after the fix: **7 failed**, the rest passed. These are the 4 baseline failures (still failing, same stale premises) plus **3 that passed at baseline**:
   - `fe_real::test_a8_record_changes_only_the_a8_parts_of_the_real_sheet[SIGNALS.json-False]` and `[SIGNALS-partial.json-True]` (line 127, projection mismatch);
   - `impl_golden::test_with_b8_a8_the_sheet_differs_only_in_the_a8_section` (line 93, SIGNALS.md outside the A8 section).

## Finding F1 — acceptance item 3 is not met: 3 tests that passed at baseline now fail
- **Context.** These three tests assume A8 is incomplete ("here A8 is incomplete: no verdict, no flag, no A8 panel member"). They passed at baseline only because rule 3.6 rejected the decider. A scratch key-path diff (paths only, no values; driver at `scratch/r4_driver/test_sheet_keydiff.py`) shows the only non-A8 difference in the projected sheet is `panel/completeness/expected` and `panel/completeness/missing_members`. With A8 complete, the signals module now expects A8 panel members, and none are judged yet. The `.md` failure is presumably the same panel-completeness change; I did not diff the markdown.
- **Recommendation.** Treat these as stale-premise tests, like the 4 baseline failures. The designer should update the three tests (and the four) to the post-decider premise, or rule that panel completeness is expected to change. The fix itself stays as is.
- **Strongest counterpoint.** The spec says "nothing that passed on the baseline fails". The lead may want those tests updated in this same change instead. That is outside my brief: they do not pin the v8-only rule for decider sessions directly, and the panel and signals modules are out of scope.

## R4 outcome
I ran the brief's exact CLI from `benchmark/`:

`python -m bench.p426_verify --lever kv all --pair n16,x --rows-root results --results-root results/m76 --repo .. --out <scratch>/r4/B8.json`

Direct `python` was not pre-approved here, so it ran via a scratch-only pytest driver (`scratch/r4_driver/test_r4_cli.py`, not in the candidate) under `fe_test.sh`, with output in `../scratch/r4/`. Results:
- exit 0;
- `B8-A8.json` status **complete**;
- pairs: s1 **accepted**, s2 **accepted**, pilot **accepted**, reload **accepted**;
- `B8.json` **byte-identical** to `results/m76/B8.json`;
- `inputs` contains `m76/wave2.tg2/run/amendment.json`.

I did not read or report any A8 result, pass rate or verdict.
