All 183 tests pass. The first run left two failures, which are explained below; nothing is committed or pushed.

**Files changed**
- `benchmark/bench/local_gate.py` is the only file I edited this delivery. `test_local_gate.py` and `test_p541_impl.py` are unchanged since delivery 1. The old `test_check_scans_a_new_branch_against_the_remote_refs` failure from delivery 1 is gone: the new `test_p541_push_level.py` has `test_check_lines_refuses_a_new_code_branch_without_a_receipt`, and everything now passes. I didn't track down which edit cleared it.

**Commands and summary lines**
- `../bin/run_stack_tests.sh bench/tests/test_p541_push_level.py bench/tests/test_local_gate.py bench/tests/test_t3_local_gate.py bench/tests/test_p541_impl.py`
  - First run: `2 failed, 181 passed in 67.48s (0:01:07)`. Both failures were the `<remote>/evidence` exclusion tests, because I had written the `--exclude` pattern wrongly. Git wants it relative to `refs/remotes/`.
  - Second run: `SyntaxError: '[' was never closed` and `4 errors in 0.27s`. I had put a comment inside a list literal.
  - Final run: `183 passed in 67.79s (0:01:07)`.

**What changed in `local_gate.py`**
- **Lossless paths:** a new `_git_raw` returns git output unstripped, and `_touched` splits it on NUL. A path like ` docs/x.py` is now code, not docs.
- **Evidence exclusion:** `introduced` takes `exclude_evidence` and adds `--exclude=<remote>/evidence` before `--remotes=<remote>`. It is on for every push whose `remote_ref` is not `refs/heads/evidence`, in both `push_level` and the per-commit scans.
- **`push_level`:** it resolves `^{commit}` itself and owns the evidence orphan rule, with the v1.3 problem text. A non-orphan returns `full` plus that problem. `check_lines` no longer has a duplicate check.
- **Raising `digest_for`:** any exception becomes `REFUSED: <repo> <sha8>: cannot compute the policy digest (<Type>: <message>)`, and the level is `full`.
- **`check_lines`:** it collects problems per ref and prints a `level:` line only for a ref with none. I removed `_level_of`.

**Judgement calls**
- **Stack tags:** `digest_for` raising inside the stack-tag release rule (`has_pass`) and in `gitlink_problems` still propagates. The spec's digest-failure rule is written for level problems, so I left those two paths alone.
- **Non-orphan evidence scan:** that push used to skip the PII scan and now gets it, because the scan runs for every ref. This is stricter only.
- **Evidence pushes from the forks:** a fork pushing `refs/heads/evidence` is treated as an evidence push for the exclusion. It does not get the orphan rule or the PII-only scan, which stay stack-only as before.
