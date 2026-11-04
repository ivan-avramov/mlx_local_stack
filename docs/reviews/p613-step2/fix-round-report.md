All 16 fixes are in. The `all` outputs reproduce every golden number and are byte-identical on a second run, and the `a7` outputs are unchanged. The test command ends with 9 failures. All 9 are tests the test-writer already listed as defective, and none of them is supported by the specification.

## Per fix

| # | File · function | Change |
|---|---|---|
| 1 | `p426_verify.py` · `_w1_smoke_scrub(rows_root)`, `_w1_scrub_reasons(soft=)` | Each smoke leg gets its own reader. A missing, unreadable or mismatched smoke file goes into `problems` and never causes a refusal. Smoke files leave `inputs` and are listed with their sha256 under `scrub_coverage.smokes.<leg>.read`. |
| 2 | `p426_verify.py` · new `_w1_budget_reasons` (called from `_w1_equal_reasons`) | Every row manifest's `sampling.thinking_budget` and A4 `params.thinking_budget` must be 81920. A1/A2 row budgets are compared per key and must be 81920. Otherwise the pair is rejected and the reason gives both values. `_w1_rows` now also returns the A4 document. |
| 3 | `p426_verify.py` · `worker_argv(cmdline, arm)`, `job_argv(argv, arm)`, `_arm_path_re`, `_foreign_arm_items`, `_w1_argv_reasons` | Only the leg's own `stack-p426-s2-<arm>` path is normalised. An argv that names the other arm's worktree gets an explicit rule 2c rejection. `ARM_PATH_RE` is removed. |
| 4 | `p426_verify.py` · `_identity_sha` | The identity text (`content`, or `description` for A3) must be a string. For A1/A2, `content_sha256` must be 64-hex. Otherwise refusal. |
| 5 | `p426_verify.py` · `Reader(confine=)`, `check_confined`; `verify_wave1`, `verify_all`; `p426_signals_wave1.compute_wave1`; `p426_signals._check_all_b8` | Wave 1 readers refuse any input whose resolved path leaves the resolved `rows_root`. `verify_all` checks every union input, A7 included. The step-1 A7 reader keeps `confine=False`, so step 1 is unchanged. |
| 6 | `p426_signals_wave1.py` · new `_sum_quality`, `_a1`, `_a1_md` | `A1.both.quality` per arm over the accepted blocks: acc, acc_strict@budget, conv %, errors, nonconv_kinds. Rendered as a table (96/100 each arm). |
| 7 | `p426_signals.py` · `compute_all` | A1 joins the mechanical family only when both A1 blocks are B8-accepted. Otherwise the label is `INCOMPLETE …` and says why. |
| 8 | `p426_signals_wave1.py` · new `_acceptance_rows`, `_speed` | Acceptance is summed over every ON row of each accepted block (A3: turn 1). |
| 9 | `p426_signals_wave1.py` · `_speed` | Ratios are fed to the bootstrap with keys sorted by (block, key). |
| 10 | `p426_signals_wave1.py` · `_walls(…, blocks_status)`, `compute_wave1`, `coverage_md` | Walls and identity counts come from accepted pairs only. A rejected block is printed as "rejected by B8". |
| 11 | `p426_signals_wave1.py` · `flags` plus new `_a1_point_items`, `_decode_items`, `_acceptance_items`, `_nonconv_flag_items`, `flag_item_text`; `_nonconv_items` recorded per arm for A1–A4; `p426_signals._flag_item_text` dispatches | Every Wave 1 flag lists its keys or legs with both arms' values. The cross-wave flag keeps its `files` list. |
| 12 | `p426_verify.py` · new `mask_paths` / `PATH_TOKEN_RE`, `_pair_reason` | Every pair reason, rejected-key reason and smoke problem passes the mask. Absolute paths and paths under `~`, `$HOME` or `${HOME}` become `<path>`. |
| 13 | `p426_verify.py` · new `_diff_values`, `_w1_pins_reasons`, `_w1_equal_reasons`, `_pair_reason` | Rule 2a/2d reasons name each differing field with both values. Every reason now reads `rule N: pair <kind> <block>: …`. |
| 14 | `p426_verify.py` · `DENY_PATTERNS` | The S-build pattern is `(^|[/.])p426-(off|on)-`. |
| 15 | `p426_signals.py` · `render_md` | If `generator_version == "p613-step2"` it calls `render_all`; the A7 path is unchanged. |
| 16 | `p426_verify.py` · `_w1_keys` | A rejected key uses the same `[block, id, seed]` shape as an accepted one (seed = the OFF seed; the reason gives both seeds). |

## Commands and results (from `benchmark/`)

- **`all`:** the brief's two `all` commands, writing to `../.p613-material/out-fix/`, both returned 0. A second run into `scratch/fixrun2/` was byte-identical:

  | File | sha256 |
  |---|---|
  | `B8.json` | `111808d5…cb46` |
  | `SIGNALS.json` | `753653c4…e7df` |
  | `SIGNALS.md` | `ded460a7…0c40` |

- **`a7`:** `a7` verify and signals into `scratch/a7fix/` returned `b6ceddfb…`, `84d8d1a9…` and `50b27b18…`. These match the committed `benchmark/results/p426/{B8.json,SIGNALS.json,SIGNALS.md}` exactly.
- **No absolute paths:** zero matches for `/Users/`, `/home/`, `STACK_WORKDIR` or `$HOME` in any of the three `out-fix` files.
- **Golden numbers:** all reproduce. B8 is 10/10 pairs accepted, all `speed_valid`. Keys are 50+50 / 20+20 / 10+10 / 3+3 / 1+1, and identical outputs 166/166. SCRUB re-verifies 249/249 (166 full + 83 smoke) and `content_sha256` 280/280. Rule 6 gives `files == ["main_models.yaml"]`, flag, entry and globals equal, 34 closure files. A1 is 49/49/47/47 per block, delta 0, loss bound 5.82 / 2.95 pp, MDE 0.1772 / 0.1253, permutation p 1.0, Holm m 3 all 1.0, "complete". Decode ratios, acceptance values, M1 peaks and decode rates all match the contract. The Wave 1 flags are exactly A2 ×3, A3 ×3 and cross-wave.
- **Scratch checks:** `.p613-material/scratch/fixchecks.py` builds synthetic worlds for each fix using the frozen world builder (read-only). Result: 28 passed, 0 failed. Its temporary worlds were removed.

## Changed numbers vs `.p613-material/out/`

- `B8.json`: no numeric value changed. `inputs` went from 979 to 886 entries and `axes.wave1.inputs` from 285 to 192: the 93 removed are all smoke files (fix 1). They now sit under `scrub_coverage.smokes.*.read`.
- `SIGNALS.json`: one existing number changed, `header.n_inputs` 1004 → 911 (fix 1). The B8 sha and the inputs sha set change with it. New numbers were added for `A1.both.quality` (OFF and ON 96/100, 0.96, conv 100 %, errors 0, @81920), `acceptance_rows` and flag items. Acceptance totals are unchanged on the committed data, because no key is rejected there.
- `SIGNALS.md`: 3 lines replaced (B8 sha, inputs line, identity label) and 126 lines added (the A1 both-blocks table and the flag item lines).

## Tests

Summary line: `9 failed, 606 passed, 1 skipped in 329.64s (0:05:29)`

During the first run I had widened the mask to any `$VAR/…` token, which went past fix 12 and hid `stack-elsewhere-on` inside a scrubbed `$STACK_WORKDIR` placeholder. That made `test_rule2c_other_worktree_path_is_a_difference` fail. I narrowed the mask to exactly what fix 12 says, and the test now passes. As a result, a `$STACK_WORKDIR/…` placeholder inside a rejection reason is left as is (it was already scrubbed). The committed data has no reasons, so its outputs contain none.

All 9 remaining failures are in the test-writer's known-defect list, which goes to the test-writer per the dispositions. The specification supports none of them:

| Test | My reading |
|---|---|
| `cross_wave::test_verify_all_members_equal_their_verifiers` | Not supported. It expects the union inputs to contain each axis's inputs exactly as keyed there, but the A7 inputs are re-keyed under `p426/` in the union. |
| `flags::test_flag_a1_decode_ratio_below_1_3` | False positive: a flag number 150.0 matches "1.5" in percent form. Only A1 b1 and A1 both are flagged, which is correct. |
| `flags::test_acceptance_flags_not_raised_above_070` | False positive: 80.0 matches 0.8 in percent form. No cell at or above 0.70 is flagged. |
| `stats::test_a3_self_pass_counts_and_label` | The contract does not require the word "panel" in A3. |
| `stats::test_identity_counts_are_printed` | It looks for identity counts under the axis key. The contract only says "printed"; the counts are in the top-level `identity` section. |
| `stats::test_rejected_pair_never_enters_the_sheet` | 0.375 collides with the CI `hi` of the accepted block. |
| `verify_rules::test_rule1_scrub_mismatch_rejects_the_pair[math500-rows]` and `[vision-rows]` | The test's mutation tears the rows file, so a refusal is the contracted outcome. |
| `verify_rules::test_rule2d_on_rows_draft_counters[patch2-draft_n_accepted-reasoning]` | An A4 draw has `draft_n` 200, so `draft_n_accepted` 101 is valid and the pair is rightly accepted. |

Nothing was committed, and no frozen test or specification file was touched.
