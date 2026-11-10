I applied all eight findings. The A7 smoke ran to completion (exit 0) and recorded A1–A4. The only test failures are the two frozen tests the brief already marks as wrong.

## Findings
1. **Done.** `tq_production` now slices the TQ4 state for real with `tq_mod._slice_state(…, lengths[-1])` before building the proxy and calling the singleton or `per_query_attention`. Planted k = 1 production rel errors are now 2.604e-3 at T = 8193 and 1.704e-3 at T = 32770, down from 1.71. All planted TQ4 production errors fall between 1.70e-3 and 3.30e-3.
2. **Done.** `A1_FLOOR = 2.0 ** -12`; the probe docstring and the report heading now say 2⁻¹².
3. **Done.** The launcher refuses with exit 10, before `mkdir` and before running anything, when `<out_dir>` already holds `mma-1.json` or `mma-2.json`. Pass 1 runs `--arm-order forward`, pass 2 `--arm-order reverse`. Mode is 755 (`-rwxr-xr-x`) and `zsh -n` is clean. A scratch run with an existing `mma-2.json` gave rc 10 and left the directory untouched.
4. **Done.** New `ARM_ORDERS` constant and `--arm-order {forward,reverse}` flag (default forward). The five timed arms are now separate small functions run in that order for each checkpoint and k, and `meta.arm_order` is recorded. The accuracy work comes after the timing, as before. One side effect: the arms' key order in the JSON follows the run order.
5. **Done.** The probe calls `fragment_mapping_ok()` before `fork_sha` and the accuracy sweep. If it fails, the probe logs `REFUSED: fragment mapping …` and exits 6. Otherwise the result goes into `meta.mma_kernel.fragment_mapping_ok`.
6. **Done.** The report now has `provenance_mismatch`: it exits 1 with `REFUSED: passes not combinable (…)` when the fork head, MLX version, GPU architecture or checkpoint T list differ between passes. Each pass's `meta.arm_order` is printed, or "not recorded" if missing. A new `a3_verdict` says "A3 holds" only when exactly the six controls are present, none duplicated, and every `pass` is False; otherwise it says "A3 NOT shown (missing / unexpected / duplicated / did not fail A1: …)". I checked each of these branches on scratch synthetic data.
7. **Done.** Removed `last_kv_inputs`, which nothing read. The comment now says the fp32 codebook centroids are rounded to half (about 2⁻¹¹ relative), as are the rotated queries and P, so the result is not exact and accuracy is shown by A1. `./fe_test.sh fmt`: the first run reformatted the file with black, the second passed black, isort and autoflake.
8. **Done.** Removed the extra blank line before `main()`. No line over 120 characters remains in the three stack files; that included two older probe lines and one older report line, which I wrapped.

## Smoke (`./fe_test.sh smoke` → `../smoke/mma-smoke.json`; the old file is now `../smoke/mma-smoke-candidate1.json`)
- **Exit code:** 0. Arm order was forward and the fragment mapping check passed.
- **Accuracy sweep:** 120/120 pass A1, 0 non-finite. Worst rel error as a share of its bound: mma_tq4 0.59, mma_n16 0.50.
- **Planted k = 1 rows:**

| T | arm | production rel error | kernel rel error |
|---|---|---|---|
| 8193 | mma_tq4 | 2.604e-3 | 2.604e-3 |
| 8193 | mma_n16 | 1.014e-3 | 1.014e-3 |
| 32770 | mma_tq4 | 1.704e-3 | 1.704e-3 |
| 32770 | mma_n16 | 1.542e-3 | 1.542e-3 |

  All four pass.
- **Controls:** all six fail A1, as they must:

| control | mma_tq4 rel | mma_n16 rel |
|---|---|---|
| N1 | 1.22 | 1.18 |
| N2 | 1.11 | 1.07 |
| N3 | 1.37 | 1.36 |

- **Checkpoints:** T = 8192 and T = 32768 each pass A1 10/10.
- **k = 3 at T = 32768:**

| arm | median ms | min ms | n |
|---|---|---|---|
| native16 | 0.744 | 0.682 | 200 |
| tq4_production | 1.287 | 1.202 | 200 |
| mq_best (G = 1) | 0.855 | 0.790 | 200 |
| mma_tq4 | 0.607 | 0.548 | 200 |
| mma_n16 | 0.758 | 0.689 | 200 |

## Frozen tests
- **Fork** (`./fe_test.sh fork dev/tests/test_m72_mma_verify.py`): 425 passed, 1 failed. The failure is `test_a5_reads_nothing_beyond_the_last_length[tq4]` with `AttributeError: Module 'random' has no attribute 'bits'`, the known-wrong test.
- **Stack** (`./fe_test.sh stack` on `test_m72_mma_report.py` and `test_m72_run_mma.py`, run again after my last edit): 40 passed, 1 failed. The failure is `test_launcher_runs_two_passes_with_mode_mma_and_idles_600`, the known-wrong one: the monitor's `sleep 60` calls show up in the fake sleep log.
- **Tests the specification does not support:** only those two known ones. Separately, no frozen test yet covers findings 3–6 (exit 10, `--arm-order`, exit 6, report refusal and the A3 completeness check); my scratch checks are not frozen tests.
- **Not run:** the full stack suite, so the A6 "same as baseline" comparison is not done.

## Notes
- On every planted k = 1 row, and wherever the n16 worst share is 0.50, the kernel's rel error equals the production one to four digits. This looks like both outputs rounding to the same bf16 values at the element with the largest error. A1 still holds, but it means that metric can't separate the two paths there.
- Scratch files I wrote outside the four candidate files: `../smoke/adhoc_check.py`, `../smoke/summarize.py` and `../smoke/mma-smoke.log`. I did not commit, push or stage anything; `git status` matches the start of the session.
