You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

This is review round 4 of C151. Read your round-3 review first ($STACK_WORKDIR/c151/cursor_review3.md; rounds 1-2
are beside it). Commit 943376a3 is the original change; the working tree holds every later fix uncommitted
(`git diff`): benchmark/bench/proc_guard.py, benchmark/bench/chain_ops.py, benchmark/bench/tests/test_c151_start_time.py.

Lead changes for round 3:
- R10: start_order maps ESRCH -> NoSuchProcess, EPERM/EACCES -> AccessDenied, any other errno -> TransportAbort.
  In ProcessGuard.cleanup, AccessDenied while deciding `_protected` for an eligible same-uid process sets
  `uncertain` with an orphan record `reason="start order unreadable"`; cleanup then raises its existing
  "cleanup uncertain" TransportAbort, which now names those processes. Test: your counterexample (untracked
  same-uid process with a denied order read) -> TransportAbort, status uncertain, process untouched; errno mapping
  parametrized (3, 1, 13, 22).
- R11: chain_ops.default_parents decides parent reuse on start_order (monotonic); wall clock only where an order
  is unreadable (AccessDenied: root-owned launchd/kernel_task). Tests: a parent that looks younger after a backward
  step is followed; a parent whose monotonic start is after the child's stops the walk.
- R9: exemptions pinned to exact qualnames (ChainOps.start_router / worker_ident / load / _alive; Chain.run_step).

You may run: `cd benchmark && env -u STACK_WORKDIR TMPDIR=$STACK_WORKDIR/c151/tmp ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_c151_start_time.py bench/tests/test_proc_guard.py bench/tests/test_chain_ops.py bench/tests/test_m62_safety.py bench/tests/test_m62_v5a.py`

For R9, R10, R11 state answered / partial / not answered with file:line. Then hunt for regressions from these fixes:
the new TransportAbort in start_order reaching the monitor thread (ProcessGuard.tick / _monitor: does an unexpected
errno now kill the monitor, and is that the right fail-closed outcome or a C148-class flake?); the R10 uncertainty
firing on ordinary same-uid processes during a long chain (false aborts); default_parents with the order fallback
mixing domains across one link; anything else. New findings as R12, R13, ... (severity, file:line, concrete
change). Final line: "cleared", "cleared after fixes" (ids), or "not cleared".

Also in the working tree (test-only, judge them too): benchmark/bench/tests/test_opencode_v2_probe.py
`test_real_gate_kill_interrupted_export_is_row` — its settle loop now retries a standalone export that fails with
"database is locked" within the existing 10 s deadline (root cause seen under full-suite load: opencode's
`serve --stdio` exits with SQLiteError "database is locked" while the SIGKILLed client's orphaned server is still
writing the interrupted message). benchmark/bench/tests/test_c147_inject.py — the alloc test's survivor check is a
direct pid lookup with pg.start_time instead of iterating process_iter() with create_time() (NoSuchProcess race,
and the adjusted start time). Is either change masking a product failure the test should catch? Full suite with
everything: 4405 passed, 2 skipped, 1 xfailed.
