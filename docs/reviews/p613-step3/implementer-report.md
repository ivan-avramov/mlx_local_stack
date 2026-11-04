I did **not** meet done-means #3: the test command gives **674 passed, 12 failed**. All 12 failures have the same cause. The step-3 contract says `all` must refuse without `--panel`, and these 12 step-2 tests run `all` without `--panel` and expect it to succeed (rc 0) with the step-2 header and status. I checked one (`test_header`): stderr is `REFUSED: --panel <dir> is required …`. Done-means #1 and #2 are met.

## Files changed
- `benchmark/bench/p426_panel.py`: added the A7 functions (`a7_select`, `a7_partition`, `a7_packet`, `wave1_identity`, `freeze`, `check_frozen`, `a7_export`, `a7_ingest`, `a7_seal`, `a7_cursor`) and the CLI subcommands `a7-export`, `a7-cursor` and `a7-seal`. The existing functions are untouched.
- `benchmark/bench/p426_signals.py`: `compute_all(..., panel=None)` and `all --panel`. These add the `§4.5` computation (`compute_subjective`), its flag (`subjective_flags`), its rendering, the step-3 header and status, and a `render_md` dispatch for `p613-step3`.
- `p426_signals_wave1.py` is not modified. No other module was created, there are no tests, and nothing was committed.

## Commands and results (run from `benchmark/`)
- **Export:** `a7-export` into `.p613-material/out/panel/` wrote 21 items as 84 packet files (2 judges × 2 orders), plus `manifest.jsonl`, `README_JUDGE.md` and `FROZEN.json`. Rc 0, no verdict exists, and `leak_problems` (run inside `export`) is clean.
  - A grep of the panel directory for paths, the model family names, session/message ids and timestamps found 0 hits.
  - A second export into `panel-b/` is byte-identical (`diff -r`).
- **Fake verdicts:** built in `.p613-material/out/fake-verdicts/panel-m1/` and labelled FAKE (client version `FAKE-0`).
  - The Cursor judge's 42 verdicts went through the real `a7_cursor` with a stub runner, so no judge was called. One deliberate failure (`p0050`) leaves 41 verdicts.
  - The Claude judge's 42 bare verdicts were sealed by `a7_seal`.
- **Sheet with fake panel:** `p426_signals all --panel <fake>` gives rc 0 in about 15 s, and the `§4.5` section renders. A rerun is byte-identical (MD and JSON), and the outputs contain no absolute paths.
- **Refusals:** without `--panel`: rc 2, `REFUSED: --panel <dir> is required …`. With a directory that has no `FROZEN.json`: rc 2, `REFUSED: panel: FROZEN.json is missing or unreadable`. No files are written in either case.
- **Freeze guards:** `check_frozen` refuses a changed packet, and `freeze` refuses when a verdict file is present (both run on copies).
- **Changes against the committed `SIGNALS.md`:**
  - 3 lines changed: the title status, the generator version `p613-step2` → `p613-step3`, and the removal of the pending line `4.5 subjective: pending (step 3: panel run)`.
  - Added: one `Panel (header.panel)` header line and the `## Subjective panel (§4.5)` section, placed between the mechanical family and the flags.
  - Nothing else differs.
- **Test command:** 674 passed, 12 failed in 358 s. The failures are 9 in `test_p613s2_all_cli.py` (write three files, byte-identical ×2, no absolute path, header, section order, pending, no composite, CLI equals in-process) and 3 in `test_p613s2_golden.py` (CLI rc 0, byte-identical, committed outputs).

## Golden table (committed data)

| | contract | got |
|---|---|---|
| A7 items | s1 11, s2 10 | s1 11, s2 10 |
| excluded identical | 30 / 31 | 30 / 31 |
| one-arm-pass | s1 1 `go/bottle-song`; s2 2 `python/pov`, `python/book-store` | same |
| neither-pass | s1 1 `go/crypto-square`; s2 0 | same |
| planned verdicts | 84 | 84 |
| Wave 1 identical | 166 | 166 |
| tested members, m | {A7-s1, A7-s2}, 2 | {A7-s1, A7-s2}, 2 (fake set) |

## Ambiguities and my reading
- **P1 — `--panel` "required" conflicts with the step-2 CLI tests.** I followed the contract: the CLI refuses without `--panel`. In-process, `compute_all(...)` without `panel` still returns the step-2 record unchanged, so the step-2 in-process tests pass. The 12 CLI tests above need the test-writer to update them, for example by passing `--panel` and expecting `p613-step3`. The alternative is to amend the contract to make `--panel` optional; the designer has to choose.
- **P2 — events hash.** The events file on the evidence branch is scrubbed, so its bytes never hash to the row's `evidence_sha256.events` (the first export refused on exactly this). Instead I check that the attempt's HARVEST record has raw `sha256` equal to the row's value and `published_sha256` equal to the bytes on the evidence branch. If neither check passes it refuses. This departs from the contract's literal wording; the final-tree objects do hash to their names, as the contract says.
- **P3 — manifest paths.** `export_packets` writes absolute paths into `manifest.jsonl`. I rewrite them relative to the output directory, which keeps the export path-free and byte-identical. `a7_ingest` and `a7_seal` then run `ingest` / `seal_verdicts` inside that directory (`contextlib.chdir`). `a7_cursor` passes the resolved absolute directory.
- **P4 — identical A7 pairs in the test.** The contract doesn't say; spec §4.5 says identical pairs "score 0.5, stay in the test". So the permutation vector is judged items plus identical items at 0, sorted by id. The raw mean and `length_adjusted` use judged items only. The table shows both the judged mean and the mean including identical items. The flag fires when Holm p < .05 and the mean including identical items is < 0.5.
- **P5 — A1 count.** I report A1 as 100 identical keys, as the contract says. That includes the 4 keys where both arms are wrong, even though the spec's selection rule for A1 is "both correct".
- **P6 — packet layout.**
  - The grader line sits in the shared Task block, after the file names, because the shared prompt comes before both responses.
  - A/B slots are balanced within each session (`make_pairs` called per session).
  - Item ids are `s1/<id>` and `s2/<id>`, and the `make_pairs` key prefix is `entry`, so the manifest carries no model name.
  - `strip_model_names` (which `export` applies) strips trailing whitespace from diff lines. The length used for `length_adjusted` is the raw diff before that stripping.
- **P7 — fail-closed additions not in the contract:**
  - an empty diff refuses;
  - non-identical Wave 1 keys refuse (no packet type is defined for them);
  - the frozen item set must equal the set recomputed from B8;
  - the `FROZEN.json` B8 sha must equal the B8 file's sha when one is given.
  - `excluded[s]` has the shape `{identical: n, one-arm-pass: {n, ids}, neither-pass: {n, ids}, rejected key: n}`.
- **P8 — scratch output.** Everything is under `.p613-material/out/`: `panel/`, `panel-b/`, and `fake-verdicts/` with `panel/` (an earlier fake set with no missing verdict, left in place because I'm not allowed to `rm -rf`), `panel-m1/`, `sheet-a`/`sheet-b` and `guards/`. Helper scripts are in `scratch/`.
- **P9 — second pytest process.** One other pytest run with the same arguments was running during my run (not my process; I couldn't inspect it). I left it alone.
