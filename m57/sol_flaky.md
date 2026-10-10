**P1 — Root cause.** [The PAUSE test]($STACK_REPO/benchmark/bench/tests/test_work_queue.py:366) patched `workqueue.time.sleep`, which also changed global `time.sleep`. A competing thread could remove `PAUSE` before [the queue checked it]($STACK_REPO/benchmark/bench/workqueue.py:353), leaving no waiting log. I forced that interleaving: the original assertion was false. I could not identify which thread caused the one-in-four suite failure.

**P2 — Fix.** The four PAUSE tests now replace only `workqueue.time`; their assertions remain strict. With the same competing thread, the waiting and resumed logs appeared. `git diff --stat`: `benchmark/bench/tests/test_work_queue.py | 18 +++++++++++-------` (one file). No commit or push.

**P3 — Verification.** From `benchmark/`, with `TMPDIR=$STACK_WORKDIR/m57/soltmp`:

- One pytest process using `pytest.main(['bench/tests/test_work_queue.py'] * 50 + ['--keep-duplicates', '-k', 'test_PAUSE_logs_entering_and_leaving_the_paused_state', '-q', '-p', 'no:cacheprovider'])`: **50 passed**.
- `../.venv-bench/bin/python -m pytest bench/tests/test_work_queue.py -q -p no:cacheprovider`: **50 passed**.
- `../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider`, run twice: **both aborted with exit 134** during an MLX import in `test_provenance.py`, before reaching the queue tests. A full-suite pass remains unverified.