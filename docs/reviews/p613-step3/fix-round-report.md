All twelve fixes are in, and the brief's test command passes: **686 passed, 0 failed** (368 s, rc 0). That includes the 12 step-2 tests that failed before. One caveat: the run started before my last edit, which only renames "admitted-eligible verdict rows" to "bound verdict rows" in the §4.5 Markdown. None of those suites renders §4.5, and I regenerated the FAKE sheets after the edit. I did not run the frozen `bench/tests/p613s3/` suite. Nothing was committed, no judge was called, and all outputs are under `.p613-material/out-fix/`.

## Fixes (both files: `benchmark/bench/p426_panel.py`, `benchmark/bench/p426_signals.py`)

| Fix | What changed |
|---|---|
| 1 | `all --panel` is optional again. Without it the step-2 record is unchanged; with a missing or unreadable FROZEN.json it refuses (rc 2, nothing written). |
| 2 | New `wave1_eligibility(rows_root, b8)`. A1 counts only keys correct in both arms (strict score, re-graded; strict and lenient both give 96 here). A2 and A3 count every key; A4 counts keys where both arms score 1.0. The others are "not both correct", excluded and counted. FROZEN stores the result; the sheet recomputes it and refuses if it differs. This replaces the earlier `wave1_identity`. |
| 3 | Every verdict records `frozen_sha256` (the sha256 of FROZEN.json). Ingest and the sheet refuse a verdict bound to a different FROZEN.json. `check_frozen` now also checks FROZEN against `manifest.jsonl`: items, A/B slots, keys, judges, judge × order coverage, prompt sha, rubric and counts. |
| 4 | `a7_ingest` takes judge, family, model, client and prompt sha from FROZEN and the batch directory, never from the verdict. A verdict whose fields disagree is counted as `rejected`; an unsealed one as `unsealed`. Already-sealed verdicts are re-checked by `a7_seal`, not skipped. |
| 5 | `run_cursor_judge` writes `<pkt>.attempt.json` before each call and never calls a packet again that has an attempt, verdict or failed marker. It gained an optional `frozen_sha` argument and a `skipped` count. |
| 6 | New `_a7_write_packets` keeps `export_packets`' layout but puts each diff in verbatim (no `strip_model_names`). Any leak hit (model names, `LEAK_PATTERNS`, family tokens, template tags) refuses the export before anything is written. Judged length = characters of the diff. |
| 7 | The `a7-export` CLI requires `--b8` = `benchmark/results/p426/B8.json` and `--universe` = `benchmark/m62/universe.json` under the repo top, with bytes equal to `git show HEAD:<path>`. The low-level `a7_export` stays injectable. |
| 8 | `a7_seal` handles each file on its own. Malformed JSON, a non-object, an invalid choice, or a pre-sealed verdict that disagrees with FROZEN gets a permanent `<pkt>.failed.txt` holding the reason and the raw bytes. Ingest counts these as `failed`. |
| 9 | `a7_packet` has exactly the contract's seven-argument signature; cached context moved to the private `_a7_packet`. |
| 10 | `missing_verdicts` = planned − Σ min(valid, planned per item); new `duplicate_verdicts` counts the excess separately. |
| 11 | The frozen set is exactly `README_JUDGE.md`, `manifest.jsonl` and the manifest's packets. A packet outside the manifest refuses; other files are ignored. |
| 12 | §4.5 has an A4 record (`subjective.descriptive.A4`): 6 / 6 eligible keys identical, scored 0.5, not judged, never tested, with the per-block draw distribution. |

## Runs
- **`a7-export` (committed data, evidence ref `b6ec7819`)**:
  - `frozen: 21 items {'s1': 11, 's2': 10}, 84 packet files, 84 planned verdicts; Wave 1 eligible 162 / 166 keys, identical 162, not both correct 4`.
  - Leak check clean with no rewriting; a scan of all 84 packets for paths, session ids and timestamps found 0 hits.
  - A second export into `panel-b` is byte-identical (`diff -r`).
- **FAKE verdicts** (client version `FAKE-0`, stub runner, in `fake/panel-FAKE`):
  - Cursor run 1: 41 written, 1 failed (`p0050`), 42 calls. Run 2: 0 new calls, 42 skipped.
  - Claude seal 1: 41 sealed, 1 failed (`p0003`, the malformed one). Seal 2 with a different version: 41 already sealed, files unchanged.
  - Ingest: 82 rows; failed 2; missing, unsealed, unbound, rejected and unparseable all 0.
- **Guards** (on copies):
  - Editing `len_on` in FROZEN → refused (verdicts are bound to the old FROZEN sha).
  - Flipping an A/B slot in FROZEN → refused (FROZEN and the manifest disagree).
  - Forged verdict family or model → 2 counted as rejected.
  - A bare verdict → counted as unsealed.
  - A stray `.DS_Store` → ignored.
  - An edited `README_JUDGE.md` → refused.
  - Fix 7: a non-repository `--b8` or `--universe` → rc 2, nothing written. I did not exercise the "differs from HEAD" branch, because that would mean changing committed files.
- **`all --panel` on the FAKE set**: rc 0, about 16 s; byte-identical when run twice; no absolute paths.
  - Against the committed sheet only these differ: the title status, the generator version, one `header.panel` line, the new §4.5 section, and the removed "4.5 subjective: pending" line.
  - FAKE result: A7-s1 judged 9 (2 items incomplete), A7-s2 judged 10; tested members {A7-s1, A7-s2}, m = 2.
- **`all` without `--panel`**: `SIGNALS.md` and `SIGNALS.json` are byte-identical to the committed `benchmark/results/p426/`.

## Golden table

| | Contract (with E3) | Got |
|---|---|---|
| A7 items | s1 11, s2 10 | s1 11, s2 10 |
| Excluded identical | 30 / 31 | 30 / 31 |
| One-arm-pass | s1 `go/bottle-song`; s2 `python/pov`, `python/book-store` | same |
| Neither-pass | s1 `go/crypto-square`; s2 0 | s1 1; s2 0 |
| Planned verdicts | 84 | 84 |
| Wave 1 identical (eligible) | 162 (A1 96, A2 40, A3 20, A4 6) | 162 (96, 40, 20, 6) |
| A1 not both correct | 4 | 4 (both arms wrong; 0 with one arm correct) |
| Tested members, m | {A7-s1, A7-s2}, 2 | {A7-s1, A7-s2}, 2 (FAKE set) |

## Ambiguities and my reading
- **P1. Export now re-grades A1.** Fix 2 needs per-item A1 correctness, which the committed `score.json` files don't hold. So `a7-export` now regrades through `bench.grade` and requires `generate.results_root()` to match the results root. The hermetic CLI tests will need `MLX_BENCH_RESULTS` set for `a7-export`, as the signals tests already do (a note for the test-writer). It also reuses private helpers from `p426_signals_wave1` (`_a1_arm`, `_accepted_keys`, `_row_map`, `_check_b8_pairs`); that module is not edited.
- **P2. Judged length.** It is the length of the diff only (the contract's wording). The disposition says "rendered solution text", which could also mean the whole Solution section. That section adds only the heading, fence and tool line, and the diff now sits in the packet verbatim. Say if you want the whole section counted.
- **P3. Shared functions left alone.** `seal_verdicts` and `ingest` are unchanged for the other axes; the A7 path has its own seal and ingest logic. The malformed-JSON crash in `seal_verdicts` still exists there; it needs its own proposal if wanted.
- **P4. A sealed verdict with no `frozen_sha256` is counted as rejected, not refused.** Refusal applies only to a verdict bound to a different FROZEN.
- **P5. Small leftovers.** `provenance.json` is rewritten on every `a7-cursor` run. `a7-seal` does not refuse a cursor-agent judge label. Neither was in the fix list.

The scratch scripts and logs are in `.p613-material/out-fix/scratch/` and `.p613-material/out-fix/logs/`.
