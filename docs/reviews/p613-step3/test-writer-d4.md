## Verdict: merge

All twelve fixes are resolved, and I found nothing the fixes broke. The four frozen test failures that remain are all errors in my tests, so I recommend merge, not a further fix round.

### Runs
- **Step 3 tests, as run:** `bench/tests/p613s3` gives `4 failed, 130 passed in 264.78s (0:04:24)`.
- **Runner amendment:** my first run gave `34 failed, 62 passed, 38 errors in 81.49s`. Every one of the 33 export failures was `REFUSED: rows_root does not resolve to bench.generate.results_root()`, which is the fix report's P1. I changed only `run_cli` in `s3world.py`: for `a7-export` it now sets `MLX_BENCH_RESULTS` to the parent of `--results-root`. No test body was touched.
- **Regression command** (including `test_p426_wave1.py`): `686 passed in 377.59s (0:06:17)`. That clears the 12 step-2 tests that failed on the earlier candidate.

### The 4 remaining failures (all test wrong)

| Test | Evidence |
|---|---|
| `test_fix4_pre_sealed_forged_verdict_is_not_trusted` | The test expects the forged verdict file to be normalised or removed. `a7_seal` instead writes a permanent `<pkt>.failed.txt` and leaves the file. `a7_ingest` checks the failed marker first, so the verdict is counted `failed` and never admitted. That meets the disposition ("rejected (counted)"). The test should check the marker or the sheet. |
| `test_fix9_a7_packet_signature_is_exact` | The `a7_packet` assertion passes; the failure is my extra assertion on `a7_select`, which still has an optional `_ctx`. Fix 9 names only `a7_packet`. |
| `test_fix12_a4_row_is_descriptive_and_untested` | All the JSON assertions pass (`subjective.descriptive.A4`, judged 0, 0.5, "descriptive", not tested, no p). The last line requires a `\| A4 \|` table row, but the candidate renders A4 as a bullet line. |
| `test_golden_export_84_verdicts_planned` | The 84 / 162 / 96 assertions pass. It then requires the text "not both correct" in `FROZEN.json`, which stores `not_both_correct` with a count of 4. The count is there; only my wording was too literal. |

The golden test stops at that assertion, so its leak scan did not run. I exported the real data separately to `.p613-material/scratch/d4-real-panel/`. It gave rc 0, 84 packets, no hits for paths, model names, `mtp`, session ids or message ids, and `wave1` 166 keys, 162 eligible, 4 not both correct (A1 96, A2 40, A3 20, A4 6).

### Fixes 1–12
- **Fix 1 (`--panel` optional):** resolved. The regression suite and `test_panel_option_is_optional` pass.
- **Fix 2 (A1 eligibility):** resolved. The real export shows 96 / 100 for A1 and 162 / 166 overall; the four excluded keys are listed.
- **Fix 3 (FROZEN binding):** resolved. Verdicts carry `frozen_sha256`. `check_frozen` cross-checks FROZEN against `manifest.jsonl` (items, slots, judges, prompt sha, counts). My three tamper tests pass.
- **Fix 4 (forged provenance):** resolved. Provenance comes from FROZEN and the batch directory. The sheet no longer reports forged fields. The one failing test checks the wrong artifact.
- **Fix 5 (retries across invocations):** resolved. An attempt marker is written before each call, and `test_fix5` passes.
- **Fix 6 (no rewriting, leaks refuse):** resolved. `_a7_write_packets` writes the diff verbatim and refuses on any leak. The exact-diff test and the model-name leak test pass.
- **Fix 7 (committed B8 and universe):** resolved. Both the copy-outside-the-repo and the edited-file cases are refused.
- **Fix 8 (bad Claude verdicts):** resolved. Each file gets its own failed marker and is counted missing, without aborting.
- **Fix 9 (`a7_packet` signature):** resolved; see the `a7_select` nit below.
- **Fix 10 (negative missing):** resolved. Duplicates are counted separately.
- **Fix 11 (stray files):** resolved. The frozen set is exactly the README, the manifest and the manifest's packets.
- **Fix 12 (A4 row):** resolved in the data and sheet; only my markup assertion fails.

### Blindness and freeze-before-verdict
- **Packet blindness:** nothing got worse. Packets are written verbatim, and any identity, path or family-token hit refuses the export before a file is written. They carry no arm names, paths, timestamps or ids, apart from the tool-count line the contract requires.
- **Freeze-before-verdict:** nothing broke. `freeze` still refuses when a verdict exists. Anything that changes the frozen files or the manifest is refused by `check_frozen`. A FROZEN edit after verdicts exist is refused through the bound `frozen_sha256`.
- **Gap, minor:** `len_on` / `len_off` are only checked to be positive. An edit made between export and the first verdict is not detected. Detecting it would mean recomputing the lengths from the packet text. The disposition required binding after verdicts, which holds.

### Nits that do not block merge
- **`a7_select` `_ctx` parameter:** the extra optional parameter differs from the contract signature; fix 9 only covered `a7_packet`.
- **Open item from the fix report (P5):** `provenance.json` is rewritten on every `a7-cursor` run, and `a7-seal` accepts a cursor-agent label.
- **Open item from the fix report (P3):** the malformed-JSON crash still exists in the shared `seal_verdicts`, which is used by other axes.
- **Fix 7:** only the "differs from HEAD" branch was verified through my tests, not its handling of an untracked or dirty index.

My four failing tests would need amending in a further delivery. I did not do that, as instructed.
