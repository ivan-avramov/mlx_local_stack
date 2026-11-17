**Verdict: fix then merge.** All 214 tests in the named files pass on candidate 2, and the fixes F1–F5 behave as specified in my tests. One spec deviation is worth tightening before merge (R1 below), and the red-on-candidate-1 check could not be run.

## What ran

Full output is in `../scratch/fe_fix1_run1.txt` and `../scratch/fe_fix1_run2.txt`. Run 2 covered the seven named files and had 0 failures and 0 skips.

| File | Tests | Result |
|---|---|---|
| `test_m76_b8_kinds_fe_wave1.py` (mine, delivery 1; includes the mtp golden) | 47 | pass |
| `test_m76_b8_kinds_fe_fix1.py` (mine, new) | 28 | pass |
| `test_m76_b8_kinds_impl_planned.py` | 14 | pass |
| `test_m76_b8_kinds_impl_fixround1.py` | 21 | pass |
| `test_m76_b3_impl_wave1.py` (K1 amended) | 12 | pass |
| `test_m76_b3_impl_counter.py` (F3 amended) | 51 | pass |
| `test_m76_b3_fe_fix_v15.py` (F3 amended) | 41 | pass |

The real-tokenizer tests ran rather than skipped (their warnings are in the output). The one failure in my first run of the new file was my own over-strict assertion: the ids tables include two smoke items. I fixed the test, not the code.

## Amendments, listed separately

- **K1** (`test_m76_b3_impl_wave1.py`): the `n16,x` half of `test_main_kv_refuses_v_before_anything_runs` now passes `--axes m1`. The intent is unchanged: it checks the m1 certified-by refusal.
- **F3 stand-ins** (`test_m76_b3_impl_counter.py:31`, `test_m76_b3_fe_fix_v15.py:294`): `apply_chat_template` now accepts `**template_kwargs`. That covers the 10 tests that use these two stand-in classes.
- **F3 real tokenizer** (`test_m76_b3_fe_fix_v15.py`, 510 vs 552): the reference text now renders with `M.deployed_template_kwargs(G.ENTRY)`. It also asserts that the counter's `meta["template_kwargs"]` equals those kwargs.

## New tests (`test_m76_b8_kinds_fe_fix1.py`)

- **F1:**
  - Arm-local worktree paths (`m76-f45-<arm>` and `m76-q-<arm>`) are accepted.
  - A path naming the other arm is rejected, and the reason names the offending arm.
  - A differing content hash beside the path still rejects.
  - Per-arm result stamps are accepted even though the two arms' bytes, and so stamps, differ.
  - Altered result bytes on either arm, for reasoning and for longctx, reject naming that arm, and the other block stays accepted.
  - A missing stamp on one arm, and a `result_file` naming another file, both reject.
- **F2:**
  - A complete record raises no `wave1_incomplete`, and M1 is `not_run` with its ruling.
  - A rejected planned pair gives one blocking flag, and an absent pair gives one too.
  - Several rejected pairs give one flag each.
  - A subset record, including an empty one, flags every absent planned pair and records `dropped`.
  - A record with no parsable build refuses.
- **F3:** every `apply_chat_template` call, calibration included, carries the deployed kwargs, and unset kwargs are omitted. The committed `ids.json` records the kwargs and loads. For all 144 committed A5 result files (both arms, tier 1), `prompt_tokens` equals the committed ids count.
- **F4:** `kinds` defaults to `None` on both entry points. The CLI passes no kinds, emits the five planned kinds with `dropped.m1`, and `compute_kv` raises no flag on that record.
- **F5:** `V.KV_W1_KINDS is P.KV_W1_KINDS`, and the plan code no longer references the verifier.

## Class and the red check

In the new file, each test's class (a) or (b) is stated in the comment above it, and class (c) applies to the build-refusal test. Candidate 1 is no longer applied in this copy, so I did not run any test red on it. The (a)/(b) split is by construction: (a) means candidate 1 lacked that behaviour, and the implementer's report records candidate 1 red for the same behaviours. (b) is `test_f1_a_differing_content_hash_beside_the_path_still_rejects`, `test_f1_unstamped_kinds_still_verify` and `test_f1_other_provenance_differences_still_reject`.

## Findings

- **R1: F1.2 "absent" is narrower than the spec.** `_kv_result_reasons` only checks stamps when either arm's manifest carries one (`p426_verify.py` in the diff, around line 280). A reasoning or longctx pair whose manifests both lack `result_file` and `result_sha256` is accepted. The spec says absent means a rule-2d reason. The implementer's reason (D1) is sound: the Math500, cjudge and vision runners write no stamps.
  - **Recommendation:** require the stamps for `reasoning` and `longctx`, the kinds whose runners write them, and leave the other kinds unstamped.
  - **Counterpoint:** this is untested against real data, so the designer should confirm all 144 harvested A5 manifests and the A4 ones carry both stamps.
  - **Why it matters:** otherwise stripping both arms' stamps silences the integrity check.
- **R2: F2 refuses a record with no parsable build.** `_kv_build_of` takes the build from `frozen.path`. This is stricter than the spec and sensible, and a test covers it. Keep it.
- **R3: `dropped` under a subset is recorded from the build.** That is erratum v1.1a and my test confirms it. `not_run` for `m1/*` is still only added under the default kinds. This is acceptable, because the consumer's `wave1_incomplete` closes the K2 hazard.
- **R4: F3 follows the spec's two kwargs.** The server also sends `reasoning_strength`, `thinking_budget` and the start/end tokens. The committed counts equal the served counts for all 144 harvested items, so this is currently correct. Only the designer's real-data check covers it if the template ever starts reading the other kwargs.

I found no other deviation from the spec.

Nothing was committed or pushed. Only the files named in the brief were edited.