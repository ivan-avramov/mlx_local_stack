Final status: the candidate applies cleanly, the frozen tests are unchanged, and 202 of 212 pass. I found no blocker. The 10 failures are not caused by candidate defects: 9 are defects in my tests (lookups or fixtures) or ambiguity in the spec, and 1 (the seed-mismatch test) is for the operator to decide.

## 1. Apply and integrity
- `git apply` of the candidate succeeded.
- All 11 files in `bench/tests/p613` match the frozen sha list (every line `OK`, checked from `benchmark/bench/tests`).
- I could not read `impl-report.md`: it sits outside the directories I can read. The review below comes from the diff and the code.

## 2. Frozen tests (golden included)
| Run | Result |
|---|---|
| Baseline, delivery 1 | 18 failed, 25 passed, 169 errors (212 tests) |
| Candidate | **10 failed, 202 passed in 94.36s** (212 tests) |

By class, the 31 invariant tests all pass on the candidate. All 10 failures are new-behaviour tests. All 23 golden tests (`p613_golden`) pass: B8 accepts s1, s2, pilot and reload with 43 keys each, strict 42 / 41 / 41 / 42 and lenient 42 / 41 / 41 / 43 per session and arm, and byte-identical regeneration.

## 3. Related suites
Command: `bench/tests/test_stats.py bench/tests/test_compare_predictor.py bench/tests/test_p426_*.py`. The summary line, verbatim:

`2 failed, 339 passed in 10.82s`

Both failures are `FileNotFoundError` for `<worktree>/.venv-bench/bin/python`, because the copy has no `.venv-bench`. They are unrelated to the candidate:
- `test_p426_plan.py::test_k3_round3_the_frozen_builds_qualify_accepts_the_planned_argv`
- `test_p426_watcher.py::test_the_real_watcher_imports_bench_ticks_and_stops`

A rerun of those two files gave `2 failed, 24 passed in 3.68s`. The full suite was not run in this delivery, because a gate is using the box; it runs in the gate before any push.

## 4. The 10 failing frozen tests
Each entry gives the verdict, then the first failing assertion line.

| # | Test | Verdict and evidence | First failing line |
|---|---|---|---|
| 1 | `test_holm_flag_not_raised_when_not_significant` | **Test defect.** My number extractor parses digits out of flag text such as "A7-s1" and the "-5 pp" threshold. The candidate's flag list holds the single point flag, −12.5 pp. | `AssertionError: [-5.0, 7.0, 1.0, -12.5, 7.0, 1.0, ...]` (flags.py:84) |
| 2 | `test_md_has_no_composite_or_hours_metric` | **Test defect.** The md carries the disclaimer "No composite, no successes_per_hour, …", which my substring check trips on. | `assert ('successes_per_hour' not in '# p426 sign…` (output.py:89) |
| 3 | `test_wall_per_leg` | **Test defect (lookup).** `walls` is keyed by attempt name, so `scope(sig, "s1")` cannot see it. The values are present: 5415.0 on a direct run. | `assert (7200 in [1.0, 1.0, 426.0, …]` (tax_speed_noise.py:200) |
| 4 | `test_power_invalid_pair_keeps_quality_and_drops_speed` | **Spec ambiguity.** The candidate keeps the numbers, marks `inference: false`, writes "power-invalid: speed descriptive only", and raises no decode flag. That fits "leaves speed inference / descriptive". My test demanded absence, which the spec does not say. | `AssertionError: no speed ratio for a power-invalid pair` (:213) |
| 5 | `test_cross_epoch_noise_floor` | **Test defect.** The spec lists `on-s1.a2` among the qualifying attempts, so the candidate is right to compare it with current `on-s1.a1` by leg name. My fixture excluded it, and I expected a per-arm total of 13. The candidate's three matches are OFF s1 1/8, ON s1.a2 6/8 and OFF pilot 0/5. | `AssertionError: OFF: 1 flip over 8 + 5 common items` (:256) |
| 6 | `test_superseded_namespace_does_not_leak_into_sessions` | **Test defect (lookup).** `scope()` also collects noise-floor records tagged `session: s1`. I checked directly: `sessions.s1` and `sessions.s2` are identical with and without the old namespace. | `assert '[{"b8_accept…` (:274) |
| 7 | `test_coverage_lists_invalid_leg` | **Fixture defect, plus minor finding F8.** My `sequence.json` keeps every leg VALID while `leg.json` says INVALID, and the candidate builds coverage from `sequence.json`. | `assert ('tg1-p426-on-s1' in …` (:284) |
| 8 | `test_coverage_counts_valid_legs` | **Test over-strict.** Coverage lists the legs (8 entries) but has no count leaf. | `assert (8 in [1.0, 426.0, …] or 4 in …)` (:291) |
| 9 | `test_rule3_seed_mismatch_rejects_the_key_only` | **Spec ambiguity.** The candidate rejects the whole pair when any key is rejected (`p426_verify.py:436-437`). The contract does not say. Operator call, see F1. | `assert False is True` (verify_b8.py:210) |
| 10 | `test_rule3_missing_slot_rejects_both_unshared_keys` | **Fixture defect.** My ON rows name `go/g2x`, which is not in ON's own `schedule.json`, so the candidate refuses ("rows outside the planned slots"). The "missing slot" path stays reachable when the two attempts' schedules differ. | `RefusalError: … rows outside the planned slots: ['go/g2x']` |

## 5. Review: statistics and rules
Checked against the contract and spec:
- **`permutation_p`** matches the contract formula: ±1 draw matrix, `|mean| ≥ |T| − 1e-12`, `(1+k)/(iters+1)`, n = 0 → 1.0.
- **`geomean_ratio_ci`** uses `default_rng(426)`, item-index bootstrap and percentile 2.5 / 97.5.
- **Paired quality block.** `paired_delta` is read only for the five fields. The label, loss bound, MDE (default row when p_d = 0) and Holm over the members present all match the contract. Holm's family label is `PROVISIONAL: family incomplete (A1 pending)`.
- **Strict scoring** covers the planned denominator, DNF slots and budget hits.
- **Tax categories** are counted from flags or kind, with a deduplicated union. C269 drops pairs where either arm ended `client_inactivity`.
- **Speed.** The primary and sensitivity rates are as defined. Dropped items are listed, acceptance is Σ/Σ, and wall time is correct.
- **Noise floor.** Same-epoch is correct. Cross-epoch matches by leg name with the same schedule sha and VALID in both. The only caveat is F4.
- **Determinism and failure paths.** The refusal and `_covered` input checks work. Two locations give byte-identical outputs with no absolute paths. CLI rc 2 prints one REFUSED line and writes nothing.
- **Extra checks the candidate adds.** These are the `leg.json` self-hash / leg name / attempt, the `sequence.json` leg state, the `v8_base` self-hash, dossier `pair == session`, dossier hashes against file bytes, the HARVEST self-hash / leg name, and the stray-row refusal. All hold on the committed data (golden passes). I found no path where they wrongly accept an invalid pair. They could wrongly reject a valid one only if real records lack those fields, and the real records have them.

## 6. Findings (none is a blocker)
- **F1 (minor, needs an operator decision).** `p426_verify.py:436-437`: any rejected pair key rejects the whole pair. This is fail-closed and defensible, but the contract does not say, and `keys_accepted` is still reported next to a rejected pair. My first-delivery assumption A5 was the opposite.
- **F2 (minor).** `p426_signals.py:411`: no tolerance at exactly −5.0 pp. I ran n = 20 with one loss: the delta is −0.050000000000000044, and `strict_point_below_-5pp` is raised, though the spec says "< −5 pp". Real n = 43 cannot hit this.
- **F3 (minor).** `p426_signals.py:494`: `b8_sha256` is the sha of the canonically re-dumped B8 dict, not of the file bytes. The two match only if the file is already canonical, as the CLI writes it.
- **F4 (minor).** `p426_signals.py:348-349`: the cross-epoch headline `flips` / `common` pools both arms (7/21 in my run). Spec §4.9 says per arm, and the per-attempt matches are correct. The old-namespace files read for the noise floor are recorded in the header but are not in B8's inputs, so staleness there is not detected. A defect in superseded rows raises a refusal for the whole sheet.
- **F5 (minor).** `p426_signals.py:428-432`: the tax flag covers only the six categories. Spec §4.11 says "a nonconv kind or tax category". The pooled acceptance flag is per session, which follows the contract. The contract wins in step 1; both are noted as deviations.
- **F6 (minor, latent).** `p426_verify.py:197` and `:238-251`: the `*.jsonl` glob would also read `<stem>.dnf.jsonl` synthetic rows, and `items/*.dnf.json` DNF records are read as ordinary item records, so a DNF slot could get a partial speed rate. No committed attempt has a DNF, so this is unverified against real data. The DNF tests passed on fixtures only.
- **F7 (minor).** `p426_verify.py:256-260`: rule 7's identity key (the row's `manifest_sha256`) is not tied to the HARVEST main file shas. `expect` and `names` lengths in `schedule.json` are not compared.
- **F8 (minor).** `p426_signals.py:448`: coverage reads leg states from `sequence.json` only, so a leg that `leg.json` or B8 marks invalid can show as "done".
- **F9 (minor).** Both CLIs raise a traceback with rc 1, not rc 2, if the `--out` directory is missing. The signals CLI writes JSON and md as two separate replaces.

## 7. Deviations from the spec
- Rule 6 (the cross-wave check) is deferred to step 2, as the contract says.
- The candidate emits power-invalid speed numbers as descriptive; I read that as spec-compatible.
- Strict 42/43 for s2 ON is used, per your note on the designer's error.

## 8. Verdict
**Fix-then-merge**, all small:
1. F2: add a tolerance to the −5 pp comparison.
2. F3: hash the B8 file bytes for the header sha.
3. F8: take coverage from `leg.json` and B8 state.

The operator should also decide F1 (does one bad key reject the pair?) and confirm F4–F6 for step 2. No candidate defect needs a code change to make the frozen tests pass. If you want the frozen tests to go green, I would repair the 10 listed lookups and fixtures in a separate round.