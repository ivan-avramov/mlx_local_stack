# Test-writer report, delivery 5 — candidate 3 (stack)

Switch: `git apply -R ../candidate-2/mlx_local_stack.patch`, `git apply ../candidate-3/mlx_local_stack.patch`; both applied cleanly. The two fork
patches were not touched (stated byte-identical; I did not re-run the fork or mlx-serve suites). My frozen/amended test files are unchanged by the patch.

## The two reasoning-resume tests

| test | candidate 2 | candidate 3 |
|---|---|---|
| `bench/tests/test_reasoning_persistence.py::test_cli_writes_partial_per_rung_and_resumes` | FAILED | passed |
| `bench/tests/test_reasoning_deep_design.py::test_cli_shallow_rows_resume_across_a_deep_redesign` | FAILED | passed |

Verbatim: candidate 2 `2 failed in 3.49s`; candidate 3 `2 passed in 5.53s`.

## Candidate 3 stack run (my 2 files + the nine files of delivery 4 + `test_run_reasoning.py`; 10 files total, `-rs`)

`320 passed, 1 skipped in 46.43s`. The skip: `bench/tests/test_m72_13_impl_e2e_spike.py:100` — "the importable mlx_vlm is not this copy's fork (run: ./fe_py.sh -m pytest <this file>)" (same skip as before; that file was not run through `./fe_py.sh` here). No failures. (Delivery 4 on candidate 2 for the nine files: `2 failed, 307 passed, 1 skipped`.)

## Review of the change

`git diff` of the copy vs the baseline: 8 tracked stack files; the only difference from candidate 2 is one hunk in
`benchmark/bench/tests/test_run_reasoning.py` (`@@ -35,7 +35,8 @@ def stub_manifest_lite`): the stub runtime gains `"tq4_attention": "off"` and the comment becomes
"v9 carries all 4". I compared the two patches' hunk headers file by file: identical for `provenance.py`, the three pinned tests, the spike, both docs and the two
implementer test files; the only addition is the `test_run_reasoning.py` file diff.
- Correctness: `"off"` is the control's default (`_SERVING_CONTROLS["tq4_attention"] = (9, "off")`), so the stubbed manifest now reads the same value the real resolver returns for a mode-less registry; it does not mask anything (the stub is a hand-built manifest for models absent from the registry, the same role as the other three keys).
- Scope: it is the single change my delivery-4 experiment predicted (wrapping this stub made both tests pass); `pin_mtp_scan` / `conftest.py` stay unedited, as I advised.
- Side effects: every other test importing `stub_manifest_lite` (e.g. `test_run_reasoning.py`, both reasoning files) passes. No finding.

## Verdict: **merge**
The previously failing pair now passes, the ten stack files are green (one environment skip), and the change is one key in a test stub with the correct default. The earlier minor
observations of delivery 4 (stale `_TQ4_MANIFESTS` entry per port; exit snapshot only within the gathering process; unformatted mlx-serve test files) are unchanged and remain optional.
