Fix a flaky test in this repo. You may edit files; do NOT commit, do NOT push, do NOT touch anything outside benchmark/bench/.

SYMPTOM: `benchmark/bench/tests/test_work_queue.py::test_PAUSE_logs_entering_and_leaving_the_paused_state` failed once in four
full-suite runs and passes every time when its file is run alone (50 passed). The test monkeypatches `workqueue.time.sleep`
(i.e. the global `time.sleep`, since `workqueue.time` is the `time` module) and asserts on a list of logged messages
(`assert any("PAUSE" in m and "wait" in m.lower() for m in logged), logged`). Suspicion, unverified: an order- or thread-dependent
interaction — e.g. a background/daemon thread leaked by an earlier test (monitors, watchers, samplers) calling the patched
`time.sleep`, or shared module state in `bench/workqueue.py`.

HOW TO RUN (from the `benchmark/` directory; the interpreter is fixed, do not install anything):
  TMPDIR=<the extra writable dir you were given> ../.venv-bench/bin/python -m pytest bench/tests/test_work_queue.py -q -p no:cacheprovider
  full suite (about 2.5 minutes; 1 known unrelated failure: test_m50_entrypoints::test_run_opencode_probe_refuses_before_the_manifest):
  TMPDIR=<dir> ../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider

TASK
1. Find the ROOT CAUSE. Read the test, `bench/workqueue.py`, and whatever can interact with it. Reproduce the failure
   deterministically if you can (e.g. run the test repeatedly, after specific other test files, or with an artificial competing
   thread) — a fix without a reproduced or clearly demonstrated mechanism is not acceptable; if you cannot reproduce it, say so
   and explain the mechanism you can prove from the code.
2. Fix it at the right level: if the test is wrong (patches a global, depends on timing or ordering), make the test hermetic
   WITHOUT weakening what it asserts; if `workqueue.py` has a real race or shared-state bug, fix the code and keep the test strict.
   Do not add retries, sleeps, `flaky` markers or skips.
3. Prove it: the single test repeated at least 50 times in one pytest process (e.g. a loop or `--count` if available — do not
   install plugins), its file, and the full suite twice. Report exact commands and results.
macOS notes: there is no `timeout` command; use /usr/bin/grep; `rm`/`cp` may be interactive aliases (use `rm -f`, `/bin/cp -f`).

FINAL MESSAGE (under 300 words): root cause with file:line; how you reproduced or demonstrated it; the diff summary
(`git diff --stat`); commands run and their results; anything you could not verify.
