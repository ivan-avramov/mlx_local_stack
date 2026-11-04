The 8 amended tests and the new `test_p613s2_fixround.py` are written, and nothing outside `benchmark/bench/tests/p613s2/` changed. The unfixed candidate is still applied. On it, 40 of the 47 new tests fail, each for its stated reason, and 7 pass; those 7 are explained below.

## Run summary (unfixed candidate)

```
$ ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/p613s2 -rs --tb=no
280 failed, 108 passed, 1 skipped in 238.32s (0:03:58)
```

- **Count:** 389 tests, which is the 342 frozen ones plus 47 new.
- **Skip:** `test_golden_committed_outputs_are_the_all_outputs`, as before.
- **Why 280 fail:** the fixture's smoke legs have no `SCRUB_MANIFEST.json`, so the candidate refuses before it reaches any other check. That is fix 1. As in delivery 2, the frozen tests cannot tell their own rule from that refusal until fix 1 lands.
- **Check with manifests added:** with the same diagnostic plugin as in delivery 2, which adds smoke manifests (scratch only, no test edited), the run gives `62 failed, 326 passed, 1 skipped`.
  - **Not in the new file:** all 22 failures are tied to a fix:
    - Fix 15 (`render_md`): `test_cli_equals_in_process`.
    - Fix 6 (per-arm accuracy for both blocks): `test_golden_a1_accuracy`, `test_a1_per_arm_accuracy_strict_and_conv`.
    - Fix 1 (smoke files in `inputs`): `test_golden_b8_inputs_include_every_scrub_file`, `test_excluded_members_are_present_and_ignored`, `test_inputs_cover_the_files_read`.
    - Fix 9 (sorted keys): `test_a1_speed_geomean_and_dropped_keys`.
    - Fix 11 (flag items): `test_flag_nonconv_kind_on_only`.
    - Fix 13 (values in reasons): `test_rule2a_pins_differ_across_the_pair`, `test_rule2a_pins_differ_from_the_frozen_record`, and the 12 `test_rule2d_manifest_sampling_and_kv`.
  - **In `fixround`:** the other 40 are the fix-round tests below.
  - **Amended tests:** none of the 8 amended tests fails in that run.

## Amended frozen tests

| Test | Change | Why the contract still supports it |
|---|---|---|
| `test_rule2d_on_rows_draft_counters[patch2-…-reasoning]` | `draft_n_accepted` 101 → 201 | 201 exceeds `draft_n` for every kind (A4 draws have 200), so "0 ≤ accepted ≤ draft_n" is still what is tested. |
| `test_rule1_scrub_mismatch_rejects_the_pair[math500-rows\|vision-rows]` and the other `rows` cases | For `what == "rows"` the edit is now ` "key": ` → ` "key" : ` on the first key, which keeps every row parseable. The other files still get a trailing space. | A SCRUB sha mismatch on a parseable file rejects the pair (rule 1). A torn file is a refusal, as you declined in Sol P6. |
| `test_flag_a1_decode_ratio_below_1_3`, `test_acceptance_flags_not_raised_above_070` | The "not raised" checks use a new `carries_direct`, which matches the fraction form only and never reads `150 / 300` as 1.5. The "raised" checks are unchanged. | The contract says a flag carries its number; "not raised" means that number is absent. |
| `test_rejected_pair_never_enters_the_sheet` | n = 9 per block; sentinels ON b1 = 4/9 and delta 4/9 − 1, absent. The accepted b2's OFF 8/9 is present. | A rejected pair adds no number. The old 3/8 coincided with the accepted b2 CI end. |
| `test_a3_self_pass_counts_and_label` | Removed the `"panel"` requirement. | The contract asks for the label "self-check, lenient, descriptive", not the word "panel". |
| `test_identity_counts_are_printed` | Accepts a top-level `identity` section: it must exist and hold the 6 and 8 counts, and name A1 to A4, or the axis subtree says "identical". | Spec: "per axis and block the count … printed". |
| `test_verify_all_members_equal_their_verifiers` | A7 input keys must be present as-is or re-keyed under `p426/`. The Wave 1 inputs must be present as-is. | The contract says "inputs: union", and the candidate documents re-keying the A7 inputs under `p426/`. |

## New tests (`test_p613s2_fixround.py`, class reproduces-failure, outcome on the unfixed candidate)

The tests that need smoke manifests get them from a module-scoped patch (the fixture otherwise omits them); the two fix 1 tests restore the default world. Flag records are read through their `member` and `flag` keys.

| Fix | Test(s) | Outcome and first error line |
|---|---|---|
| 1 | `test_fix01_smoke_leg_without_manifest…` and `…bad_smoke_manifests_are_recorded…` | Fail: `RefusalError: smoke cjudge-p426s2-off-smoke SCRUB_MANIFEST.json: required file … missing`. The second hits `unreadable JSON`. |
| 2 | `fix02` swap and 81920, each with cjudge and math500 (4) | Fail: `AssertionError: []`. The pair is accepted, with no rejected pair. |
| 3 | `fix03` swapped worktree, ON and OFF, math500 and vision (4) | Fail: `AssertionError: []`. |
| 4 | `fix04` missing content and sha (2), missing description (A3) and content (A4) (2) | Fail: `DID NOT RAISE RefusalError`. |
| 4 | `fix04` missing sha alone (2) | **Pass.** The candidate already refuses it. Kept as a regression test. |
| 5 | `fix05` symlink out of `rows_root`: stdout, ids | Fail: `DID NOT RAISE RefusalError`. |
| 5 | `fix05` manifest symlink | **Pass.** The candidate already refuses that case. |
| 5 | `fix05` symlink inside `rows_root` is fine | **Pass.** It is a regression guard for the fix. |
| 6 | `fix06` | Fail: `AssertionError` on the `A1.both` pool (it has 1.0, 0.2 and so on, but not 0.9 and 0.7). |
| 7 | `fix07` | Fail: the family is `"label": "complete", "m": 3` with b2 rejected. |
| 8 | `fix08` | Fail: `assert (False)`. 0.64 and 0.72 are missing. |
| 9 | `fix09` | Fail: `assert (False)`. The plan-order CI is in the sheet, not the sorted one. |
| 10 | `fix10` | Fail: `AssertionError: 3000` (the rejected pair's wall is present). |
| 11 | acceptance, decode, M1 and nonconv flag tests (4) | Fail: for example `{"flag": "acceptance_below_0.70", "member": "a2-b1", … "value": 0.5}`, which has no keys or items. The M1 flag carries no legs. |
| 12 | `fix12` four argv or problem cases, plus the sheet test | Fail: the reason still holds the raw `/Users/zed`, `/home/zed` or `~/secret` path. | <!-- allow-pii-pattern -->
| 13 | `fix13` manifest (2), pins, M1 served | Fail: `('math500', ['rule 2d: manifest sampling differs between off and on'])`. The pair, and both values, are missing. |
| 14 | `fix14` S-build tune with valid rows, ON and OFF | Fail: `DID NOT RAISE RefusalError`. |
| 15 | `fix15` | Fail: `KeyError: 'sessions'` at `p426_signals.py:735`. |
| 16 | `fix16` for math500, cjudge and vision | Fail: `(['b1', 'test/algebra/1.json'], ['b1', 'test/algebra/2.json', 1592471921])`. The rejected key has 2 elements. |
| 16 | `fix16` reasoning | **Pass.** The A4 rejected key already has 3 elements. |
| G1 | `test_g1_rejected_a7_session_under_all` | **Pass.** The candidate degrades the family to incomplete. It pins the behaviour. |
| G2 | `test_g2_one_rejected_wave1_block_flags_the_other` | **Pass.** The candidate flags only A2-b2. It pins the behaviour. |

`fixround` on its own: 40 failed, 7 passed.
