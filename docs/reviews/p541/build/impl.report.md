The P541 change is in `local_gate.py`, but one existing test fails and I did not fix it. `test_local_gate.py::test_check_scans_a_new_branch_against_the_remote_refs` still asserts the old behavior (a code branch push with no receipt returns no problems). The latest run gave `1 failed, 154 passed in 48.42s`. The independent tests, `test_t3_local_gate.py` and my own tests all pass.

**Contradicting test.** At `bench/tests/test_local_gate.py:300` the test pushes a code commit (`b.txt`) to a new branch with no receipt and expects `[]`. The spec's Levels section says that push is level **full** and refused without a receipt. The v1.1 ruling replaces only `test_a_branch_push_needs_no_receipt_only_the_scans`, and I was told not to touch any other existing test. My reading is that this test is stale under P541. The designer needs to rule on it. A fix would be to give that test a receipt, or to change its commit to docs-only. The introduced-commits assertion on line 301 is unaffected.

**Files changed**
- `benchmark/bench/local_gate.py`:
  - Added `pass_receipt`, `is_docs_path`, `is_data_path`, `_touched`, `push_level` and `_level_of`.
  - `has_pass` now delegates to `pass_receipt`.
  - `check_lines` takes an optional `levels` list and calls `push_level` per ref.
  - `main` prints the level lines, then the problems.
- `benchmark/bench/tests/test_local_gate.py`: replaced `test_a_branch_push_needs_no_receipt_only_the_scans` with `test_a_code_branch_push_without_a_receipt_refuses`, as v1.1 directs.
- `benchmark/bench/tests/test_p541_impl.py` (new): two tests, one for `pass_receipt`/`has_pass` and one for a non-ASCII docs path.

**Commands**
- `../bin/run_stack_tests.sh bench/tests/test_p541_push_level.py bench/tests/test_local_gate.py bench/tests/test_t3_local_gate.py` (first run, before my own tests): `1 failed, 152 passed in 47.78s`
- The same command plus `bench/tests/test_p541_impl.py`: `1 failed, 154 passed in 48.42s`
- `git status --short`: shows only the files above plus the pre-existing `docs/specs/p541-push-levels.md` modification. Nothing was committed.

**Judgement calls**
- **Evidence orphan check:** it stays in `check_lines`. `push_level` returns `data-only` for the stack's `refs/heads/evidence` without checking orphan status. A non-orphan evidence push is refused before `push_level` runs, so it prints no level line.
- **Stack tags:** these skip `push_level` and keep the P448 release rule. Fork tags go through `push_level` with the tagged commit's sha (v1.2), so the receipt lookup and level line use the commit.
- **Data-only on forks:** it applies only when `repo == "stack"`, as the spec says ("any stack branch").
- **Merge diff:** a merge's paths come from `git diff-tree -r -z --name-only <parent1> <merge>`. A plain `diff-tree` prints nothing for a merge.
- **Path parsing:** I use `-z` so non-ASCII or quoted paths come through intact.
- **Receipt name:** when several PASS receipts match, I take the first in sorted order.
- **Passing the level lines out:** the spec didn't say how `check_lines` hands them to `main`, so I added an optional `levels=None` list parameter. The return value stays a problems list.
- **Output order:** `main` prints all level lines first, then all problems.
