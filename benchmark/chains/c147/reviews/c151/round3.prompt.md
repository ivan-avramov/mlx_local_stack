You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

This is review round 3 of C151. Read your round-1 and round-2 reviews first: $STACK_WORKDIR/c151/cursor_review1.md
and cursor_review2.md (round 2 verdict "not cleared": R8 HIGH false cleanup clearance after a backward wall-clock
step; R9 AST guard exemptions too broad). Round 1 reviewed commit 943376a3; the working tree holds all later fixes
uncommitted (`git diff`): benchmark/bench/proc_guard.py, benchmark/bench/chain_ops.py,
benchmark/bench/tests/test_c151_start_time.py.

Lead changes for round 2:
- R8: identity and ordering are now separate. Identity stays start_time() (unadjusted wall-clock kernel start, the
  value recorded in manifests). Every ORDERING decision uses start_order(): macOS proc_pid_rusage
  ri_proc_start_abstime compared with clock_order() = mach_absolute_time() taken at guard creation
  (ProcessGuard.started_order): `_older_than_guard` (used by `_protected`), the tick ancestry "parent younger than
  child = pid reuse" check, and the cleanup orphan sweep. Test fakes may supply start_order(); objects without one,
  or non-darwin, fall back to the old wall-clock comparisons. ESRCH -> NoSuchProcess, other errors -> AccessDenied
  (the existing transient/uncertain handling). Tests: your counterexample (client wall 110 / child wall 99,
  started 100) with orders, a forward-step pre-existing process staying protected, and a real client -> grandchild
  with `g.started += 1000` (simulated backward step) tracked and killed by cleanup.
- R9: exemptions are (file, enclosing qualname, receiver text, method) tuples; parse failures fail. A mutation
  (an added `p.create_time()` in tg1_runner.py) was caught.

You may run: `cd benchmark && env -u STACK_WORKDIR TMPDIR=$STACK_WORKDIR/c151/tmp ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_c151_start_time.py bench/tests/test_proc_guard.py bench/tests/test_chain_ops.py bench/tests/test_m62_safety.py bench/tests/test_m62_v5a.py`

For R8 and R9 state answered / partial / not answered with file:line. Re-check R2's fail-open question against the
new code. Then hunt: is proc_start_abstime on the same clock as mach_absolute_time on Apple silicon, including across
sleep (Caffeine keeps this box awake, but say what happens); ctypes struct layout of rusage_info_v0 (field order and
sizes) against <libproc.h>/<sys/resource.h>; errno mapping (EPERM for other users, races with exit); thread safety of
the lazy ctypes init (the guard runs a monitor thread); any ordering site still on wall clock; any path where a
mixed comparison (one side order, other side wall) can occur; the chain_ops router/worker ownership checks
(default_parents walk uses start_time comparisons for parent reuse — is that also exposed to a backward step, and
does it fail open or closed?). New findings as R10, R11, ... (severity, file:line, concrete change). Final line:
"cleared", "cleared after fixes" (ids), or "not cleared".
