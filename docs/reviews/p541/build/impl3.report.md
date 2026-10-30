A path that isn't valid UTF-8 no longer raises out of `_touched`; it is classified by its bytes. All four test files pass; I did not commit or push.

**Summary line:** `184 passed in 63.69s (0:01:03)`, from `../bin/run_stack_tests.sh bench/tests/test_p541_push_level.py bench/tests/test_local_gate.py bench/tests/test_t3_local_gate.py bench/tests/test_p541_impl.py`.

**Files changed**
- `benchmark/bench/local_gate.py`:
  - `_git_raw` now captures bytes.
  - `_touched` splits on `b"\0"` and decodes each path as UTF-8 with `errors="surrogateescape"`.
  - A git error message from `_git_raw` is decoded with `replace`.
- `benchmark/bench/tests/test_p541_impl.py`: added `test_a_non_utf8_path_is_classified_as_code_without_raising`.

**New test.** It commits a top-level `bad\xff.py` with a real 0xff byte, built through `git hash-object -w` and `git update-index --cacheinfo` with a bytes argument. It asserts that `_touched` returns the surrogate-escaped name. It also asserts that `push_level` for `mlx-serve` returns level `full` with one "no PASS gate receipt" problem.

**Judgement call.**
- **First run of the new test:** it failed because my first draft used `docs/bad…`. That path is docs-only by its bytes, so `docs-only` was the correct result and the test was wrong.
- **First fix attempt:** passing a str with `ÿ` was encoded as valid UTF-8, so it never produced a real 0xff byte.
- **Final test:** it uses a top-level `.py` name and passes the path as bytes.
- **Not covered:** I did not test a non-UTF-8 name under `docs/`.
