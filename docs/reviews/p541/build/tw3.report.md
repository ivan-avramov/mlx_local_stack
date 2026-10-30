I added the tests for all seven review items to `test_p541_push_level.py`. 16 new or amended tests fail against the current implementation, all at items 1–5 and all for the reasons the review named. Items 6 and 7 already pass. The existing gate tests still pass.

## Results (verbatim summary lines)
- `bench/tests/test_p541_push_level.py`: `16 failed, 106 passed in 50.01s`
- `bench/tests/test_local_gate.py bench/tests/test_t3_local_gate.py`: `59 passed in 14.42s`

One error was my own: in the item-6 helper, a parameter name collided with the `sha` override (`TypeError: … multiple values for argument 'sha'`). I fixed it and reran. None of the 16 remaining failures comes from a fixture.

## Failures against the current code, by item
| Item | Failing tests | Why |
|---|---|---|
| 1 Lossless paths | `test_paths_are_read_losslessly[space-docs-stack, space-docs-vlm, space-docs-serve, space-results-stack, leading-newline-docs]` (5) | `_git` calls `.strip()` on the `-z` output (`local_gate.py:175`, used by `_touched` `:378-381`). That strips the first path's leading space or newline, so ` docs/x.py` is read as docs-only and ` benchmark/results/x.py` as data-only. The `trailing-space-md` and `inner-newline-docs` cases pass, because the trailing NUL protects trailing spaces and `-z` keeps inner newlines intact. |
| 2 Evidence-only commit | `test_a_branch_at_an_evidence_only_code_commit_is_classified_by_its_paths`, `…_data_commit_is_data_only_not_none_new` (2) | `introduced()` excludes everything under `--remotes=origin`, `origin/evidence` included, so both return `('none-new', '', [])`. |
| 3 Evidence rule in `push_level` | `test_push_level_refuses_a_stack_evidence_push_sharing_history_with_main` (1) | `push_level` returns `data-only` with `[]` for any stack `evidence` push (`:386`). |
| 3 | `test_a_stack_evidence_push_sharing_history_with_main_still_refuses_as_not_orphan` (1, amended) | `check_lines` still emits the old text `ceed585f pushed to …`, without the v1.3 `REFUSED: stack ` prefix. |
| 3 Tag resolved by `push_level` (v1.3 clause; I added this) | `test_push_level_resolves_a_tag_to_its_commit[mlx-vlm, mlx-serve]` (2) | Given a tag object sha, `push_level` names the tag object's sha8, because only `check_lines` resolves the tag to its commit. |
| 4 `digest_for` raising | `test_push_level_turns_a_failing_policy_digest_into_a_level_problem[GateError, OSError]` (2) | The exception propagates out of `push_level`. |
| 4 | `test_main_a_failing_policy_digest_…_other_ref_keeps_its_line[bad-last, bad-first]` (2) | `main` prints only `[local_gate] REFUSED: no UPSTREAM_SYNC_REF`, and the other ref's full-level line is lost. |
| 5 Scan problem | `test_main_a_ref_with_a_scan_problem_prints_no_level_line` (1) | `_level_of` (`:447-453`) prints the level line when only `push_level`'s own problems are empty, so a ref with a PII problem still prints `level: docs-only`. |

**Items 6 and 7 pass already:**
- **Item 6:** `test_a_receipt_file_named_right_but_wrong_inside_refuses[inner-digest, inner-sha, inner-FAIL]`.
- **Item 7:** the fork tag refusal through `check_lines`, the docs-only tag level line, and `test_main_prints_the_full_level_of_a_fork_code_tag_and_its_refusal_with_the_commit_sha`. Each now asserts the exact sha8 of the tagged commit, computed in the test.

**Tree state:** `git status` also shows `local_gate.py`, `test_local_gate.py` and a new `test_p541_impl.py`. Those are the implementer's changes; I only edited `test_p541_push_level.py`. I didn't run `test_p541_impl.py` or the full stack suite. Nothing was committed or pushed.

## Ambiguous points (left open)
- **P13 Which exceptions count as "`digest_for` raising".** I tested `GateError` and `OSError`. The `<reason>` format isn't pinned, so I only assert that the problem starts with the v1.3 prefix, contains `str(exc)` and ends in `)`.
- **P14 What level `push_level` returns alongside the not-orphan problem.** v1.3 gives only the problem text, so the tests don't check the level or `detail` in that case.
- **P15 Whether forks also drop `<remote>/evidence` from the `--not` set.** v1.3 says "a non-`evidence` push" without limiting it to the stack. I tested item 2 on the stack only.
