## Cold review — P613 step 3 fixed candidate

I traced all 12 fixes in `benchmark/bench/p426_panel.py` and `benchmark/bench/p426_signals.py` against the dispositions, the contract errata, and the frozen tests in `.p613-material/frozen-tests/`. I did not run the suites (the fix-report itself notes the frozen `bench/tests/p613s3/` suite was not run).

### Disposition of each opinion finding

| Finding | Status | Why |
|---|---|---|
| Sol P1 / FROZEN unsealed | resolved | `_seal` writes `frozen_sha256` (p426_panel.py:158); `_verdict_problem` (1059) refuses a verdict bound to a different FROZEN sha; `check_frozen` cross-checks FROZEN against `manifest.jsonl` via `_check_manifest` (857). |
| Sol P2 / trusted provenance | resolved | `a7_ingest` derives identity from FROZEN via `_expected_seal` (1049); `_verdict_problem` rejects mismatches; pre-sealed verdicts are re-checked, not skipped (1148-1160). |
| Sol P3 / re-call on resume | resolved | `run_cursor_judge` writes `<pkt>.attempt.json` before each call and skips any packet with attempt/verdict/failed marker (238-243). |
| Sol P4 / lengths from raw diff; silent redaction | resolved | `_a7_write_packets` puts the diff verbatim (770-799); `_a7_leaks` refuses on any hit (755); `len_* = len(diff)` (677). |
| Sol P5 / E1 `--panel` required | resolved | CLI passes `panel=args.panel` (default `None`); `compute_all(panel=None)` returns the step-2 record unchanged (p426_signals.py:853-856); no refusal gate. |
| Sol P6 / E3 A1 eligibility 100 vs 96 | resolved | `wave1_eligibility` (693) applies the both-correct rule for math500 via `_w1_eligible_fn` (678); FROZEN stores and the sheet recomputes/requires equality (p426_signals.py:999-1001). |
| Sol P7 / arbitrary `--b8`/`--universe` | resolved | `_committed_input` (1025) requires the committed path and byte-equality with `git show HEAD:<rel>`; low-level `a7_export` stays injectable. |
| Sol P8 / malformed verdict crashes sealing | resolved | `a7_seal` handles each file alone; malformed/invalid → `_fail_marker` (1118), counted `failed` (1151-1160). |
| Sol P9 / `a7_packet` signature | resolved | `a7_packet` has exactly 7 params (642); ctx moved to private `_a7_packet`. |
| GLM F4 / negative `missing_verdicts` | resolved | `valid_capped` + `duplicate_verdicts` (p426_signals.py:1036-1038); `missing_verdicts = planned - valid_capped`. |
| GLM H1 / freeze hashes every file | resolved | `_frozen_set` (813) lists exactly `README_JUDGE.md`, `manifest.jsonl`, manifest packets; strays ignored. |
| GLM F3 / stale frozen tests | partially resolved | The frozen tests were amended for E1 (`test_panel_option_is_optional`) and E3 (golden `162`/`96`), but four fix-round tests still over-read the contract (see F1 below). |
| TW d2 / A4 absent from §4.5 | resolved | `compute_subjective` builds `a4 = _wave1_member("A4", ...)` with `_a4_draws` (p426_signals.py:1023-1025). |

### New findings

**F1 — `a7_select` keeps `_ctx`, so fix 9 is inconsistent and `test_fix9` fails.**
Location: `benchmark/bench/p426_panel.py:397` (`def a7_select(results_root, b8, _ctx=None)`); `.p613-material/frozen-tests/test_p613s3_fixround.py:243`.
Severity: minor. Evidence: confirmed (traced in source).
Problem: Fix 9 moved `a7_packet`'s cached context into the private `_a7_packet` to restore the exact contract signature, but `a7_select` and `a7_partition` still carry `_ctx=None`. The contract lists `a7_select(results_root, b8)`. The frozen test asserts `list(inspect.signature(panel.a7_select).parameters) == ["results_root", "b8"]`, which fails with `["results_root", "b8", "_ctx"]`.
Failure scenario: a consumer introspecting the public signature sees a third parameter the contract doesn't define; the frozen signature test fails.
Proposed change: apply the same fix-9 pattern to `a7_select`/`a7_partition` (move `_ctx` into a private helper), or update the frozen test to `[:2]` as `test_p613s3_export.py::test_interface_signatures` already does. The dispositions classify this as a test defect for the test-writer (d5); I flag it because the code-side fix is the one already chosen for `a7_packet` and is more consistent.

**F2 — `test_fix4_pre_sealed_forged_verdict_is_not_trusted` asserts the verdict file is re-sealed; the code marks it failed.**
Location: `.p613-material/frozen-tests/test_p613s3_fixround.py:100-112`; `benchmark/bench/p426_panel.py:1155-1160`.
Severity: minor (test defect). Evidence: confirmed (traced).
Problem: `a7_seal` writes a `<pkt>.failed.txt` marker and leaves the forged verdict file untouched, so the test's `assert d["model"] == "claude-opus-5-5"` reads the still-forged content and fails.
Failure scenario: the frozen suite fails on a correct implementation.
Proposed change: the test should assert the `.failed.txt` marker exists and the forged model is absent from the sheet, not assert the verdict file was rewritten. (Dispositioned to d5; recorded because the fix-report did not run the frozen suite to confirm.)

**F3 — `test_fix12_a4_row_is_descriptive_and_untested` expects `| A4 |` in the table; A4 is rendered as a bullet.**
Location: `.p613-material/frozen-tests/test_p613s3_fixround.py:300`; `benchmark/bench/p426_signals.py:1163-1166`.
Severity: minor (test defect). Evidence: confirmed (traced).
Problem: `_subjective_md` emits A4 via `_wave1_line` (a `- A4 ...` bullet) after the family table, not as a table row, so `assert "| A4 |" in md.read_text()` fails.
Failure scenario: the frozen suite fails on a correct implementation.
Proposed change: either add A4 as a table row or relax the test to assert the A4 bullet line. (Dispositioned to d5.)

### Notes (not findings)

- The shared `seal_verdicts`/`ingest` (non-A7) still crash on malformed JSON and trust verdict-supplied provenance. The dispositions scope these out (step 3 uses its own `a7_seal`/`a7_ingest`); residual, as recorded.
- `a7-export` now regrades A1 through `bench.grade`, so it requires `rows_root == generate.results_root()` (enforced by `check_roots` inside `wave1_eligibility`) and the A1 score files to be present. This is by design (E3) and the test runner sets `MLX_BENCH_RESULTS`; production runs from the repo default. The fix-report's P1 ambiguity notes this.
- `test_fix10` takes the refusal path (duplicated manifest → `check_frozen` refuses via `counts.planned_verdicts != len(rows)`), so it passes via the early return but does not actually exercise the non-negative `missing_verdicts` path. Weak but not broken.

The 12 fixes are correctly applied in the source. The remaining failures are frozen-test defects already dispositioned to the test-writer (d5); the fix-report did not run that suite, so they are unverified rather than resolved.
