I wrote 69 tests in `benchmark/bench/tests/test_p541_push_level.py`. 65 fail for the intended reasons and 4 pass on purpose; the existing gate tests still pass. Before relying on them, note two things:

- **They were written from the in-repo spec, not `../spec.md`.** The read of `../spec.md` was blocked by permissions, so I used `docs/specs/p541-push-levels.md` ("spec v1"). If `../spec.md` is a different version, the tests may not match it.
- **One existing test contradicts the spec and will fail once P541 is implemented.** `test_local_gate.py::test_a_branch_push_needs_no_receipt_only_the_scans` asserts that a code branch push with no receipt returns `[]`. I didn't edit it, as instructed. Whoever implements this will have to change or delete it, and that needs your approval.

## Results
- New file: `65 failed, 4 passed in 21.75s`
  - 52 fail with `AttributeError: module 'bench.local_gate' has no attribute 'push_level' | 'is_docs_path' | 'is_data_path'`. I checked every failure message.
  - 13 fail on the old behaviour: `check_lines` raises no refusal, `main` returns 0 where 1 is expected, and stderr has no level lines. In the `main` tests stderr is `[]` and the exit code is 0, so the fixture runs cleanly.
  - 4 pass on purpose. They guard behaviour the spec says must not change: the evidence orphan rule, a tag on either fork, and a stack tag.
- Existing suites (`test_local_gate.py` + `test_t3_local_gate.py`): `59 passed in 14.47s`.
- Only the new file was added (`git status` shows nothing else). Nothing was committed.

The tests use temporary repos with a bare remote and inject `gate_dir` and `digest_for`. They point `GIT_CONFIG_GLOBAL` at `/dev/null`, set `core.hooksPath=/dev/null` in each repo, and set `STACK_WORKDIR` to a temp directory. The `main` tests give `origin` a canonical GitHub URL that is never fetched (push URL `no_push`); the only fetch goes to a remote called `local`, which is the bare repo.

## Tests → spec items
| Test | Spec item |
|---|---|
| `test_is_docs_path[11 cases]` | Interfaces: `is_docs_path`; Level 2: `docs/**` or a top-level `*.md` |
| `test_is_data_path[7 cases]` | Interfaces: `is_data_path`; Level 1: under `benchmark/results/` |
| `test_a_docs_only_push_is_docs_only_without_a_receipt[stack, mlx-vlm, mlx-serve]` | docs-only, for the stack and both forks |
| `test_a_stack_results_only_branch_push_is_data_only` | data-only (a stack branch) |
| `test_a_fork_results_path_is_not_data_only_and_needs_a_receipt[2 forks]` | data-only is stack-only, so a fork needs full |
| `test_a_code_push_without_a_receipt_refuses[3 repos]` | full: a code push without a receipt refuses, with the exact message |
| `test_a_code_push_with_a_PASS_receipt_for_the_sha_is_full[3 repos]` | full passes; `digest_for(repo, local_sha)` is called |
| `test_a_receipt_that_is_not_a_PASS_…[another-sha, FAIL, another-digest]` | wrong sha, FAIL verdict or other policy digest each refuse |
| `test_mixed_docs_and_code_is_full[one-commit, two-commits]` | mixed docs + code is full |
| `test_mixed_docs_and_data_is_full[one-commit, two-commits]` | mixed docs + data is full |
| `test_an_empty_diff_commit_is_full[3 repos]` | an empty-diff commit is full |
| `test_a_new_branch_name_for_a_pushed_commit_is_none_new[3 repos]` | none-new |
| `test_a_merge_contributes_its_diff_against_its_first_parent` | a merge counts its diff against its first parent (already-pushed code comes in, so full) |
| `test_a_merge_of_docs_only_commits_stays_docs_only` | the same rule, positive case |
| `test_push_level_does_not_fetch` | Interfaces: "pure apart from `git` reads" |
| `test_a_stack_evidence_orphan_is_data_only_and_pii_only` | evidence: data-only, no naming scan |
| `test_a_stack_evidence_push_sharing_history_…` (guard) | evidence orphan rule unchanged |
| `test_a_fork_evidence_branch_is_not_exempt[2 forks]` | evidence is stack-only, so a fork needs full |
| `test_check_lines_refuses_a_code_branch_push_without_a_receipt[3 repos]`, `…_new_code_branch_…` | `check_lines` returns the refusal |
| `test_the_pii_scan_still_runs_at_every_level[docs-only, data-only, full]`, `…_on_evidence` | scans still run and still refuse at every level |
| `test_the_message_scan_still_runs_on_a_docs_only_push` | the naming scan on the commit message still runs |
| `test_a_fork_tag_push_is_not_a_branch_push[2]`, `test_a_stack_tag_keeps_the_release_rule…` (guards) | tags unchanged |
| `test_main_prints_the_{docs_only, data_only, data_only…_for_evidence, none_new, full…_receipt_file_name}_level` | the exact printed level lines on stderr, exit 0 |
| `test_main_prints_the_refusal_and_exits_1` | the exact `[pre-push] REFUSED: …` line, exit 1 |
| `test_main_prints_one_level_line_per_ref` | one line per ref, in order |

## Ambiguous points (left open)
- **P1 Where "REFUSED:" goes.** `main` already adds `[pre-push] `, so either `check_lines`' problem text includes `REFUSED: ` or `main` adds it for this one case. I test for the substring in problems and for the exact full line from `main`.
- **P2 What `detail` holds.** The spec doesn't say. I assume it contains the receipt file name for full, and I don't check it for other levels.
- **P3 Who reports scan problems.** It could be `push_level`'s `problems` or `check_lines`. I only check that `check_lines` reports them.
- **P4 Level lines when a push is refused.** If one ref passes and another refuses, it's unclear whether the passing ref's line is printed. Not tested.
- **P5 Fork tags are a gap (I'm pushing back on this one).** "Tags unchanged" means a fork tag push still runs only the scans. A tag push uploads its commits, so unreceipted fork code can still reach the remote that way. My guard test locks in the current behaviour; you may want to decide otherwise.
- **P6 Merges.** Read literally, merging code that is already on the remote into a docs commit makes the push full. I test that reading; please confirm it's intended.
- **P7 Docs commit plus an empty commit.** P is non-empty and all docs, so the push would be docs-only, which conflicts with the spirit of "an empty-diff commit is full". Not tested.
- **P8 Evidence sharing history.** The level is unspecified; only the existing orphan message is tested.
- **P9 Path edge cases.** A path that is exactly `docs`, case such as `X.MD`, and `benchmark/results` without a trailing slash are unspecified and not tested.
