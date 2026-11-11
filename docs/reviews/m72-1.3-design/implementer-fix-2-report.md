I applied the one change, and all the tests the brief names now pass.

## Failure before (verbatim)
```
E           bench.provenance.ServedConfigError: C1 resume refused: the journal's manifest is not compatible with this run (sampling / KV / draft / serving controls / code differ).

bench/run_reasoning.py:147: ServedConfigError
FAILED bench/tests/test_reasoning_persistence.py::test_cli_writes_partial_per_rung_and_resumes
FAILED bench/tests/test_reasoning_deep_design.py::test_cli_shallow_rows_resume_across_a_deep_redesign
2 failed in 3.42s
```

## Change
`benchmark/bench/tests/test_run_reasoning.py:37-38`: I added `"tq4_attention": "off"` to the runtime block in `stub_manifest_lite`, written the same way as the other three controls. I also changed the comment at the end of that line from `# v8 carries all 3` to `# v9 carries all 4` so it still matches the block. The diff is 2 insertions and 1 deletion, and no other file changed.

## Runs after
- **The two tests that failed:** 2 passed in 5.39s.
- **The wider set:** 312 passed, 0 failed, in 42.13s. It covered:
  - the three files that use `stub_manifest_lite` (`test_run_reasoning.py`, `test_reasoning_persistence.py`, `test_reasoning_deep_design.py`);
  - the four files candidate 2 updated (`test_mtp_verify_scan_provenance.py`, `test_provenance_fingerprint.py`, `test_orphaned_manifest.py`, `test_m72_13_impl_provenance.py`);
  - the two frozen files (`test_m72_13_provenance.py`, `test_m72_13_harness.py`).
- **A command error:** my first combined command also printed `(eval):1: == not found` and exited 1. That came from the `echo ===` separator, which zsh treats as a special `=` expansion, not from any test. The 2 passed result above came from that command. I reran the wider set on its own, and that run gave the 312 count.

## Not done / questions
- I did not run the full stack test suite, since the brief only names these files.
- The brief contradicts itself: it says the test directory is read-only, but it also puts this one test file in scope. I followed the specific scoping and edited only this file.
- I committed nothing.