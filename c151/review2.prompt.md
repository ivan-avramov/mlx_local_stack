You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

This is review round 2 of C151 (see docs/open-questions.md C151 and your round-1 review at
$STACK_WORKDIR/c151/cursor_review1.md — read it first). Round 1 reviewed commit 943376a3 (`git show 943376a3`).
The working tree now holds the fixes for your findings, uncommitted (`git diff`): benchmark/bench/proc_guard.py,
benchmark/bench/chain_ops.py, benchmark/bench/tests/test_c151_start_time.py.

Lead decisions on round 1:
- R1: partial — require_identity now names each drifted field with before/after values; no psutil-internals dump.
- R2: DEFERRED, recorded as a residual. Lead reasoning: a kernel start time compared with the guard's time.time()
  boundary misorders only if the wall clock steps BACKWARD by more than the gap between guard creation and a spawn
  (corrections observed on this box: +62.8 ms). Both outcomes fail closed: a just-spawned client read as pre-existing
  is "protected", register() raises TransportAbort and the item aborts; a pre-existing process read as new is only
  ever killed if it is tracked, and tracked identities are registered descendants of the guard's own client, which
  a pre-existing process cannot be. The boundary semantics predate C151 and ~10 test fixtures set `g.started`.
  Judge this reasoning: is there any FAIL-OPEN path (wrong kill, false "gone", false clearance) through
  `_protected` / `started` that the lead missed? Cite file:line.
- R3: fixed — chain_ops.default_parents walks ppid() with start_time(), mirroring psutil Process.parent() (stop at
  the lowest pid; a parent younger than its child is a reused pid). proc_guard's excluded_pids parents() use is
  pid-only and allowlisted.
- R4: fixed — boot_shift pins psutil's boot_time() to a controlled value equal to INIT_BOOT_TIME, shifts ±1 s.
- R5: fixed — platform-independent AST guard over all non-test benchmark/ and scripts/ modules for .create_time(),
  .parents(), .parent(); calls on `self` / `self.ops` are ChainOps effect hooks whose defaults are the checked
  functions.
- R6: fixed — real-child shift test asserts _identity_state == "alive" and verify_gone(...) is False.
- R7: fixed — on darwin a real psutil.Process without the raw path raises TransportAbort; the lock pins psutil 7.2.2
  (benchmark/requirements.txt stays loose: it is not the bench venv's source).

You may run: `cd benchmark && env -u STACK_WORKDIR TMPDIR=$STACK_WORKDIR/c151/tmp ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_c151_start_time.py bench/tests/test_proc_guard.py bench/tests/test_chain_ops.py`

For R1–R7 state answered / partial / not answered against the code with file:line. Then hunt for regressions from the
fixes (default_parents vs psutil semantics for pid 0/1, zombies, AccessDenied, races; the fail-closed raise reaching
paths that previously tolerated psutil errors, e.g. ProcessGuard.tick's transient handling (C148) and cleanup;
the AST guard's exemptions hiding a real psutil call). New findings as R8, R9, ... (severity, file:line, concrete
change). Final line: "cleared", "cleared after fixes" (ids), or "not cleared".
