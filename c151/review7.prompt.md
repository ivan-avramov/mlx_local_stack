You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

Review round 7 of C151. Read your round-6 review first: $STACK_WORKDIR/c151/cursor_review6.md. The working tree holds
all fixes on top of commit 943376a3, uncommitted (`git diff`).

Lead changes for round 6:
- R17: the "cleanup uncertain" exception lists each entry with its reason; the R16 test asserts "identity unreadable".
- R18: tg1_runner's grader kill on the exception path is wrapped so guard.cleanup() always runs; cleanup re-audits
  every tracked identity (survivors / unknown -> uncertain) and raises, so nothing is certified clean.
  Test: test_failing_grader_kill_still_runs_cleanup.

You may run: `cd benchmark && env -u STACK_WORKDIR TMPDIR=$STACK_WORKDIR/c151/tmp ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_c151_start_time.py bench/tests/test_proc_guard.py bench/tests/test_m62_safety.py bench/tests/test_m62_v5a.py bench/tests/test_m62_revision5.py`

For R17 and R18: answered / partial / not answered with file:line. Then a final whole-diff pass (`git diff 943376a3`
plus `git show 943376a3`): only real defects that could make a live tg1 chain kill a process it does not own,
certify a process gone that is not, publish a clean cleanup status that is not, hang, or abort spuriously on an
ordinary macOS process. Do not re-raise settled decisions (R2 superseded by R8; R13 interim pending P273). New
findings R19, ... . Final line: "cleared", "cleared after fixes" (ids), or "not cleared".

Also changed since round 6 (test-only): test_real_gate_kill_interrupted_export_is_row's interim retry now also matches
"Standalone server exited before reporting readiness" — without OPENCODE_PRINT_LOGS=1 opencode prints only that
symptom, not the SQLite "database is locked" cause (the earlier string match never fired; the test failed once more
in a full run). Still bounded by the test's 10 s settle deadline. For P273 the lead will propose a production retry
that runs the export with OPENCODE_PRINT_LOGS=1 and retries only on the logged lock cause. Judge the interim only.
