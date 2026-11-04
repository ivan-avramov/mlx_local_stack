I've completed my review. Let me compile the findings.

## Verification summary

I traced every finding through the fixed candidate source, ran both `all` commands on the committed data, and confirmed byte-identical regeneration, golden numbers, step-1 `a7` preservation, and absence of absolute paths. I could not execute the frozen-test suite myself because the sandbox blocks `git init` in temp dirs (the world fixtures need it), so the test pass/fail count below relies on the fix-report plus my own source-level verification of each amended test.

## Per-finding dispositions

### Sol P1 (fix 1 — smoke legs) — RESOLVED
`_w1_smoke_scrub` (`p426_verify.py:1126-1152`) reads each smoke leg through its own `Reader(confine=True)` with `soft=True`; missing/unreadable/mismatched smoke files become `problems`, never a refusal. Smoke files are absent from `inputs` (confirmed: 192 wave1 inputs, zero containing `smoke`) and listed under `scrub_coverage.smokes.<leg>.read`. The frozen `test_fix01_*` tests pin both cases.

### Sol P2 (fix 2 — thinking budgets) — RESOLVED
`_w1_budget_reasons` (`p426_verify.py:1006-1041`) requires `sampling.thinking_budget == 81920` on every manifest, `params.thinking_budget == 81920` for A4, and per-key row `thinking_budget == 81920` for A1/A2. A compensated swap is rejected per-key. Confirmed: the sheet labels `@81920`.

### Sol P3 (fix 3 — arm worktree normalization) — RESOLVED
`_arm_path_re(arm)` (`p426_verify.py:583-585`) matches only the leg's own `stack-p426-s2-<arm>`; `_foreign_arm_items` (`p426_verify.py:887-889`) flags the other arm's component as a rule-2c rejection. The old `ARM_PATH_RE` is gone. I verified the masking regex preserves `stack-elsewhere-on` (a real difference) and does not mask it as a path.

### Sol P4 (fix 4 — identity fields) — RESOLVED
`_identity_sha` (`p426_verify.py:1051-1063`) requires `isinstance(text, str)` and, for A1/A2, a 64-hex `content_sha256`; otherwise `RefusalError`. `None == None` no longer passes.

### Sol P5 (fix 5 — symlink confinement) — RESOLVED
`Reader(confine=True)` + `check_confined` (`p426_verify.py:70-93`) resolve every input and refuse if it leaves `rows_root`. `verify_all` re-checks every union input (`p426_verify.py:1349-1350`). The step-1 A7 reader keeps `confine=False` (`verify_a7` uses `Reader(results_root)` with no confine), so step 1 is unchanged — confirmed by byte-identical `a7` outputs.

### Sol P6 (torn rows file) — DECLINED (deliberate, not a defect)
The dispositions decline this: a torn/unreadable required file is a refusal under the step-1 `chain_rows` torn-file rule. `read_rows` (`chain_rows.py:125-133`) raises `ChainRowsError` on a missing terminal newline, which `_w1_rows` converts to `RefusalError`. This is fail-closed, the stricter outcome. I agree with the disposition.

### Sol P7 (fix 6 — A1 both-blocks per-arm quality) — RESOLVED
`_sum_quality` (`p426_signals_wave1.py:220-238`) aggregates per arm over accepted blocks; `_a1` (`p426_signals_wave1.py:270`) sets `both.quality`. Confirmed in output: OFF 96/100 (0.96) @81920, ON 96/100 (0.96) @81920, conv 100%, errors 0.

### Sol P8 (fix 7 — family completeness) — RESOLVED
`compute_all` (`p426_signals.py:864-881`) gates A1 family membership on `a1_blocks_accepted and permutation_p is not None`; otherwise the label is `INCOMPLETE: missing [...]` with the reason. Confirmed: `family.label == "complete"`, `m == 3`, members `['A1','A7-s1','A7-s2']`.

### Sol P9 (fix 8 — acceptance denominator) — RESOLVED
`_acceptance_rows` (`p426_signals_wave1.py:142-156`) sums `draft_n_accepted`/`draft_n` over every ON row of the block (A3 turn 1 only), not just key-accepted rows. Confirmed: A1 106153/138464 = 0.7666, matching the contract.

### Sol P10 (fix 9 — bootstrap key order) — RESOLVED
`_speed` (`p426_signals_wave1.py:108`) iterates `sorted(keys, key=lambda k: k[1])` — sorted by (block, key). The `both` block concatenation follows the same sorted order.

### Sol P11 (fix 10 — walls/identity from accepted pairs only) — RESOLVED
`_walls` (`p426_signals_wave1.py:160-169`) skips `blocks_status[block]["status"] != "accepted"`. `compute_wave1` (`p426_signals_wave1.py:493-497`) builds `identity` only for accepted blocks. Rejected pairs appear in coverage only.

### Sol P12 (fix 11 — flags carry items) — RESOLVED
`_a1_point_items`, `_decode_items`, `_acceptance_items`, `_nonconv_flag_items` (`p426_signals_wave1.py:505-555`) attach per-key/per-leg crosswalks with both arms' values. Confirmed: A2-b1 acceptance flag has 20 items, each with `key`, `off`, `on`, `what`. The cross-wave flag keeps its `files` list.

### Sol P13 (fix 12 — path masking) — RESOLVED
`mask_paths` + `PATH_TOKEN_RE` (`p426_verify.py:51-58`) mask absolute (`/...`), home-relative (`~/...`), and `$HOME`/`${HOME}` tokens to `<path>`. I verified the regex preserves `stack-elsewhere-on`, `$STACK_WORKDIR`, and repo-relative paths like `Qwen.../math500...jsonl` (the `/` is preceded by a word char, so the negative lookbehind `(?<![\w.\-/~$])` blocks the match). No absolute paths in any output.

### Sol P14 (fix 13 — reasons name both values) — RESOLVED
`_diff_values` (`p426_verify.py:809-819`) emits `field: off X on Y` for each differing field. `_w1_pins_reasons`, `_w1_equal_reasons`, `_w1_budget_reasons` all name both values. `_pair_reason` (`p426_verify.py:1118-1123`) prefixes `rule N: pair <kind> <block>:` when not already present.

### Sol P15 (A3 turn-2 draft gate) — DECLINED (deliberate)
The dispositions keep the turn-2 draft check: recert §2 says every eligible ON request carries draft activity and every OFF request none; turn 2 is a request. This is a conservative addition, documented in the sheet. I agree it is not a defect.

### Sol P16 (fix 14 — S-build deny pattern) — RESOLVED
`DENY_PATTERNS` (`p426_verify.py:51`) uses `(^|[/.])p426-(off|on)-`, matching after `/` or `.`. So `math500.p426-on-b1.jsonl` (where `p426-on-` follows `.`) is deny-listed.

### Sol P17 (fix 15 — render_md dispatch) — RESOLVED
`render_md` (`p426_signals.py:722-728`) checks `signals["header"]["generator_version"] == ALL_VERSION` and calls `render_all`; otherwise renders the A7 record exactly as step 1. Confirmed: `render_md(compute_a7(...))` produces step-1 output with `p613-step1`, not `p613-step2`.

### GLM M1 (fix 16 — rejected-key shape) — RESOLVED
`_w1_keys` (`p426_verify.py:1095-1115`) uses `key = [block, x, ro["seed"]]` (3 elements) for both accepted and rejected keys. For reasoning request-seed mismatches, the key is still 3 elements with the OFF seed; the reason names both seeds.

### GLM M2 (stale A4 report claim) — NO CHANGE NEEDED
The implementer's report says the contract range is 1.584–1.656, but erratum D2 (`docs/specs/p613-step2-contract.md` line 150) corrects it to 1.528–1.656. The code produces 1.528–1.656 (confirmed: b2 draw seed 128000005 = 1.5278). The golden test `test_golden_decode_ratio_points` pins `min == 1.528`. The report is stale; the code is correct.

### GLM G1, G2 (test gaps) — RESOLVED
`test_g1_rejected_a7_session_under_all` and `test_g2_one_rejected_wave1_block_flags_the_other` are present in `test_p613s2_fixround.py` (lines 399-420).

### GLM S1, S3 (scope notes) — KEPT
M1 `result.json` status gate and extra evidence fields (`log`, `speed_problems`, `gitlinks`, `entry_present`) are conservative/evidence-only additions. No consumer hazard.

## Additional findings

**A1 — fix-report test-failure descriptions appear stale vs. the amended frozen tests**
- Location: `.p613-material/fix-report.md` (the 9-failure table).
- Severity: minor (report only; the code is correct).
- Evidence: confirmed by comparing the fix-report's descriptions against the amended tests in `frozen-tests/`. The fix-report says `test_rule2d_on_rows_draft_counters[patch2-draft_n_accepted-reasoning]` fails because "An A4 draw has `draft_n` 200, so `draft_n_accepted` 101 is valid." But the amended test (`test_p613s2_verify_rules.py:444-449`) uses `{"draft_n_accepted": 201}` (not 101), which is `> 200` and should be rejected — so the amended test should pass. Similarly, `test_flag_a1_decode_ratio_below_1_3` and `test_acceptance_flags_not_raised_above_070` now use `carries_direct` (fraction form only, no x100 reading), which should avoid the percent-form false positives the fix-report describes. And `test_rule1_scrub_mismatch_rejects_the_pair[math500-rows]` was amended to use `replace(b'": ', b'" : "', 1)` (valid JSON), not appending a byte (which tore the file).
- Problem: the fix-report's 9-failure list- Problem: the fix-report's 9-failure list appears to describe pre-amendment test versions. The delivery-3 amended tests in `frozen-tests/` address each of those defects (new `carries_direct`, `201` instead of `101`, value-preserving JSONL edit, n=9 to avoid the 0.375 collision, top-level `identity` section, `p426/` re-key handling, "self-check" label without "panel"). I could not run the suite to confirm the exact count because the sandbox blocks `git init` in temp dirs.
- Failure scenario: the operator reads the fix-report, believes 9 amended tests still fail, and either holds the candidate or asks for another fix round, when in fact the amended tests may pass.
- Proposed change: re-run the amended frozen tests in an unsandboxed environment and update `fix-report.md` with the actual amended-test results. If any amended test still fails, name it with the amended reason.

**A2 — `$STACK_WORKDIR` placeholder inside a rejection reason is not masked**
- Location: `benchmark/bench/p426_verify.py:51-58`, `PATH_TOKEN_RE`.
- Severity: minor (scope request, not a defect — the fix-report explicitly preserves this).
- Evidence: confirmed by regex trace. The mask matches `~...`, `$HOME`, `${HOME}`, and `/...` only. `$STACK_WORKDIR/path` is left as-is because `STACK_WORKDIR` ≠ `HOME` and the `/` is preceded by a word char.
- Problem: none, if the placeholder is already scrubbed before it reaches the reason. But if a raw `$STACK_WORKDIR/<real path>` ever appears in a rejection reason, it would not be masked.
- Failure scenario: a future SCRUB-covered file path written as `$STACK_WORKDIR/...` in a receipt leaks through. Not reachable on the committed data (no reasons are emitted).
- Proposed change: none needed for step 2; note for the operator that the mask is intentionally narrow.

## Conclusion

All 16 adopted fixes are correctly implemented and verified against the committed data (byte-identical `all` outputs, golden numbers reproduced, `a7` unchanged, no absolute paths). The two declined findings (P6, P15) are deliberate, documented decisions I agree with. GLM M2 is a stale report, not a code defect. The only substantive item is A1: the fix-report's 9-failure table appears to reference pre-amendment tests, and the delivery-3 amended tests in `frozen-tests/` likely address those failures — but this needs an unsandboxed test run to confirm.
