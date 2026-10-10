You are a cold, adversarial reviewer. Read-only: do not edit repository files or commit; scratch only under $TMPDIR. You may run tests from `benchmark/` with `../.venv-bench/bin/python -m pytest ...`; no model servers, no inference, no Docker runs.

A prior review (`$STACK_WORKDIR/m62/codex_impl_review.md`, findings P1–P11, verdict "not ready") was addressed in commit `HEAD` (`git show HEAD --stat`). Its adversarial fixtures: `$STACK_WORKDIR/m62/tmp/v5a-review-5t0icpqa/test_v5a_adversarial.py`.

Scope — verify the fixes only, focused on live-run safety:
1. For each of P1–P7, P9–P11: FIXED / PARTIAL / NOT FIXED with evidence (file:line, test, or a fixture you run). Re-run the original adversarial fixtures against HEAD.
2. P1 kill safety above all: enumerate every code path in `benchmark/bench/proc_guard.py` and `benchmark/bench/tg1_runner.py` that sends a signal or kill. For each, state what guarantees the target is a process this item created (pid + create_time tracked from a registered root, created after guard start, not router/worker/probe/ancestors/other sessions). Construct any scenario where an operator process, the router, the worker, Docker Desktop or an unrelated user process could be signalled.
3. Any regression introduced by the fixes in the gate/accounting paths (run the M62 tests and `STACK_WORKDIR=~/ws/mlx_local_stack_workdir ../.venv-bench/bin/python m62/replay.py`).

Output: table for item 1; numbered new findings with severity and evidence; verdict: ready for V3 / not ready (list).
