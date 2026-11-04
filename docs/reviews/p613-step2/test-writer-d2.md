**Verdict: fix then merge.** The candidate leaves 31 frozen tests failing, and I judge 14 of those 31 test failures to be the candidate's fault and 17 to be mine. One real gap blocks the merge: the A1 sheet has no per-arm accuracy for both blocks combined.

I applied the candidate with `git apply .p613-material/candidate.diff`, and the working tree now carries it. I fixed nothing and edited no frozen test. The only files I added are scratch under `.p613-material/scratch-d2/`: a diagnostic plugin, a runner, sheet dumps and `diag-out.txt`.

## Commands and summary lines

All commands ran from `benchmark/`.

| Run | Result |
|---|---|
| Frozen tests at baseline `5630d8f6` (delivery 1) | `327 failed, 14 passed, 1 skipped in 140.83s` |
| Frozen tests on the candidate: `../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/p613s2` | `240 failed, 101 passed, 1 skipped in 217.13s` |
| Same, plus a diagnostic plugin (see below) | `31 failed, 310 passed, 1 skipped in 223.29s` |
| Neighbours: `... pytest -q -p no:cacheprovider bench/tests/p613 bench/tests/test_p371_r7_consumers.py bench/tests/test_p426_wave1.py` | `274 passed in 96.06s` |

- **Same tests ran.** Both runs collect 342 tests. The 14 that passed at baseline still pass on the candidate: 10 `world_sanity`, 3 golden data-only tests and `test_a7_commands_are_unchanged`. The one skip is the same test, `test_golden_committed_outputs_are_the_all_outputs`, which is skipped until step 2 commits its outputs.
- **Why 240 fail.** The candidate reads each smoke leg's `SCRUB_MANIFEST.json` and raises `RefusalError` when it is absent, and my fixture's synthetic smoke legs have none (real ones do). The plugin gives the smoke legs a manifest; the 31 failures below are what remains with it.
- **Golden on the committed data.** With real smoke manifests present, the golden tests that depend on verification pass. These cover B8 10/10, keys, identical 166/166, rule 6, decode, acceptance, A2 to A4 counts, M1, the Wave 1 flags, and byte-identical `all` regeneration through the CLI on the committed data. Two fail (below).

## The 31 remaining failures

**Candidate wrong, test valid (14):**

| Test | First error line |
|---|---|
| `golden::test_golden_a1_accuracy` and `stats::test_a1_per_arm_accuracy_strict_and_conv[on,1]` | `AssertionError: 0.96` and `('on', 1, 0.6875)`: no per-arm both-block accuracy in the A1 section |
| `stats::test_a1_speed_geomean_and_dropped_keys` | the `lo` of the both-block geomean CI differs (1.1908 against 1.1854) |
| `flags::test_flag_nonconv_kind_on_only` | `'dom-04' in txt` is false: the A2 flag has no items |
| `rules::test_rule2a_pins_differ_across_the_pair` and `…_from_the_frozen_record` | the reasons give no values: `'rule 2a: receipt pins (without frozen_sha) differ between off and on'` |
| `rules::test_rule2d_manifest_sampling_and_kv` (12 parametrisations) | `'rule 2d: manifest sampling differs between off and on'`, with neither value named |

**Test wrong or over-specified, candidate acceptable (17):**

| Test | Reason |
|---|---|
| `rules::test_rule2d_on_rows_draft_counters[patch2-draft_n_accepted-reasoning]` | My bug: an A4 draw has `draft_n` 200, so `draft_n_accepted` 101 is valid and the pair is rightly accepted. |
| `rules::test_rule1_scrub_mismatch_rejects_the_pair[math500-rows]` and `[vision-rows]` | My mutation appends a space to a `.jsonl`, which makes a torn row file. The candidate refuses with `torn rows file` before it reaches the SCRUB comparison. The other 5 parametrisations pass. |
| `flags::test_flag_a1_decode_ratio_below_1_3`, `flags::test_acceptance_flags_not_raised_above_070` | False positives from my percent-form number match: `150 / 300` is read as 1.5 and a `80` as 0.8. The candidate flags only b1 and both for decode ratio, which is correct. |
| `stats::test_rejected_pair_never_enters_the_sheet` | The 0.375 I forbid also appears as the CI `hi` of the accepted b2 block. The candidate excludes the rejected pair correctly (`both.blocks == ["b2"]`). |
| `stats::test_a3_self_pass_counts_and_label` | I assert the word "panel" in the A3 section; the contract does not require it. |
| `stats::test_identity_counts_are_printed` | I look under the axis key; the candidate prints a top-level `identity` section with the right counts (A1 6/8, 6/8). |
| `all_cli::test_cli_equals_in_process` | I call the step-1 `render_md` on the new sheet. The contract does not pin that; the candidate renders it with `render_all`. The earlier assertions of that test pass. |
| `cross_wave::test_verify_all_members_equal_their_verifiers` | I read "inputs: union" literally. The candidate re-keys the A7 inputs under `p426/`, keeps `axes.A7.inputs` as in step 1, and says so. |
| `verify_rules::test_inputs_cover_the_files_read`, `keys_roots::test_excluded_members_are_present_and_ignored`, `golden::test_golden_b8_inputs_include_every_scrub_file` | I assert that no smoke file is an input. The contract's own "249 / 249" requires the 83 smoke SCRUB files to be re-verified. The candidate does this for coverage only; it never gates or scores them. |

## Findings

1. **Major: no per-arm accuracy for both blocks.** `p426_signals_wave1.py` writes `A1.both` with `paired_*`, `exclusive`, `permutation` and Holm, but no `quality` (the diagnostic sheet's keys are `blocks`, `exclusive`, `holm_p`, `n_pairs`, `paired_lenient`, `paired_strict`, `permutation`, `permutation_p`). The contract asks for per arm `acc`, `acc_strict@81920` and conv % "per block and both blocks". The committed-data both-block 0.96 (and 1.0) is nowhere in the A1 section, which is the ranking key the operator needs. Reproduce with the two failing tests above, or by listing the keys of `A1.both` in the generated `SIGNALS.json`.
2. **Major (robustness): a smoke leg without a manifest refuses everything.** `p426_verify.py:1021-1031`, `_w1_smoke_scrub`, reads `SCRUB_MANIFEST.json` of every `*-p426s2-*-smoke` directory through `read_json`. A missing manifest raises `RefusalError`, which makes all 10 pairs unverifiable. The contract treats smokes as excluded and coverage-only, so this is stricter than it says. A smoke mismatch is only recorded, so the leniency is already there for content. I would record a missing manifest as a coverage problem instead of refusing. This does not affect the committed data.
3. **Minor: reasons omit values for rules 2a and 2d.** The contract says each rejection names the pair, the rule and both values. Rules 1 and 2c reasons do name them; 2a pins and 2d manifest `sampling` / `kv` do not. Reproduce: edit one manifest `temperature` in an ON leg, then read `pair["reasons"]`.
4. **Minor: speed keys sorted by plan order, not by key.** The geomean CI uses the `ids.json` order within a block. The contract says "keys sorted (block, key)". The two orders differ only for ids such as `test/algebra/9.json` against `10.json`. The committed `ids.json` lists are already in sorted order, so the golden is unaffected.
5. **Minor: most flags carry no items.** In the F scenario only the A1 point and Holm flags list items. The decode, acceptance, M1 and `nonconv_kind` flags have an empty `items`. The contract says "each with its number and items", and step 1 lists them.
6. **Checked, no issue:**
   - Step 1: the `p613` suite (274 tests with the other two neighbour files) passes, and the `a7` commands are unchanged.
   - Hazards to consumers: none seen. `test_p426_wave1.py` passes, and the moved module `p426_signals_wave1.py` imports cleanly.
   - Refusal against rejection: where the contract says refuse (duplicate or count errors, unresolvable commits, root mismatch, tampered sha, regrade drift), the candidate refuses.
   - Outputs: no absolute paths, and byte-identical on rerun, including across two checkout locations.

## Deviations from the contract

- **Beyond the contract:** the candidate rejects a pair when an M1 `result.json` status is not `"ok"`, and when A3 turn-2 drafts are invalid. It also adds `scrub_coverage`, plus gitlink and entry-presence evidence in B8.
- **Resolved by the implementer, with a recorded reading:**
  - The A7 Holm p uses m = 3 under `all`, and `a7` keeps m = 2.
  - An id set differing at the right count is refused.
  - A3 and A4 non-convergence kinds are derived by the candidate's own rule, and the sheet prints the basis.
