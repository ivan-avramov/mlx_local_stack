You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

Confirmation round for P273 ONLY. In rounds 1-2 ($STACK_WORKDIR/c152/cursor_review1.md, cursor_review2b.md) you
reviewed a combined C152 + P273 tree. The operator then chose to WAIVE the C152 alloc positive; the C152 redesign is
parked off-main. The working tree on main (`git diff` + new file benchmark/bench/opencode_export.py) now holds ONLY:
- benchmark/bench/opencode_export.py: run_export(attempt, env, *, timeout=120, deadline 10 s, pause 0.5 s):
  attempt(env_copy_with_OPENCODE_PRINT_LOGS=1, timeout); retried only while the export failed AND its stderr
  contains "database is locked"; no pause that would cross the deadline; no retry started with < 1 s left (your T9);
  each retry's timeout capped to the time left (your T3); export_failure_tail() for the abort message.
- benchmark/run_opencode_probe_v2.py `_export_session` (M61 path) and benchmark/bench/tg1_runner.py terminal-path
  export (via guard.run_grader) both go through it; opencode_export.py is added to BOTH code-identity module lists.
- tests: bench/tests/test_opencode_v2_probe.py (retry-only-on-logged-lock, no retry on other failures, deadline,
  no sleep past the deadline, capped retry timeout, < 1 s left, stderr tail) and bench/tests/test_tg1_integration.py
  (tg1 export goes through the helper with an env copy); the earlier test-only retry in
  test_real_gate_kill_interrupted_export_is_row is removed (the probe's own retry now covers that race).
Also docs: open-questions C152 ruling A, spec §7 V3 waiver note, §9 B11.

You may run: `cd benchmark && env -u STACK_WORKDIR TMPDIR=$STACK_WORKDIR/c152/tmp ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_opencode_v2_probe.py bench/tests/test_tg1_integration.py -k "run_export or export"`

State T3 and T9 answered / partial / not answered with file:line, then only real defects in this P273 diff (masking a
non-lock failure, unbounded retry, stdout/parse change, env leakage into anything but the export, identity hashing
gaps). Findings P1, ... . Final line: "cleared", "cleared after fixes" (ids), or "not cleared".
