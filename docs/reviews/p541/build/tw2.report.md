I've amended `benchmark/bench/tests/test_p541_push_level.py` to spec v1.1. It now has 94 tests: 88 fail for the intended reasons and 6 pass on purpose. The existing gate tests still pass.

## Results (verbatim summary lines)
- New file: `88 failed, 6 passed in 28.19s`
- Existing gate tests (`test_local_gate.py` + `test_t3_local_gate.py`): `59 passed in 13.71s`

**Why the 88 fail.** I checked the reason for every failure:
- **69 fail because the new functions don't exist yet** (`AttributeError`): 43 on `push_level`, 16 on `is_docs_path`, 10 on `is_data_path`.
- **19 fail on the current behaviour**:
  - `check_lines` returns `[]` where the spec expects the exact `REFUSED: …` problem. This covers code branches, new code branches, fork `evidence` and fork code tags.
  - `main` exits 0 where the spec expects 1.
  - `main` prints no `[pre-push] level: …` lines.

**The 6 that pass on purpose** cover behaviour that already exists and must not break:
- An `evidence` push that shares history with `main` stays refused.
- A stack tag keeps its release-receipt rule.
- On each fork, a code tag with a receipt for the tagged commit passes. Before P541 it passes because tags were scan-only.
- On each fork, a docs-only tag passes. It also passes before P541, so the failing check for it is the printed level line in `test_main_prints_the_level_of_a_fork_docs_only_tag`.

**State of the tree.** `git status` shows only my test file as new. `docs/specs/p541-push-levels.md` also shows as modified; that is the designer's v1.1 section, and I didn't touch it. Nothing was committed or pushed.

## What changed, by v1.1 ruling
| v1.1 ruling | Change |
|---|---|
| Problem text starts with `REFUSED: `; `main` prefixes `[pre-push] ` | `_refusal()` now includes `REFUSED: `. Problem lists are compared exactly, e.g. `== ("full", "", [_refusal(...)])`. The `main` line is `[pre-push] {_refusal}`. |
| `detail` is the receipt file name for full, `""` otherwise | Every `push_level` check compares the whole `(level, detail, problems)` result; for full with a receipt, `detail` is the file name. |
| Scan problems come only from `check_lines` | The PII and message-scan tests now also require `push_level`'s problems to be `[]`. |
| Passing refs still print their level line when another ref refuses | New `test_main_prints_the_passing_refs_level_lines_when_another_ref_refuses`, run with the refused ref first and last. It expects exit 1, the docs-only line, the REFUSED line, and no level line for the refused ref. |
| Fork tags need a level | Replaced my old fork-tag guard with: a code tag without a receipt refuses; a code tag with a receipt for the tagged commit passes; a docs-only tag passes; `main` prints the docs-only tag's level line. |
| Docs + empty commit is docs-only; empty P is full | New `test_a_docs_commit_plus_an_empty_commit_is_docs_only` (3 repos × empty commit first/last). The empty-P test is now `test_an_empty_P_is_full` (3 repos × one or two empty commits). |
| Paths are case-sensitive and need their prefix | Docs: `docs`, `Docs/x.md`, `DOCS/x.md`, `README.MD`, `README.Md` are all not docs. Data: `benchmark/results`, `Benchmark/results/…`, `benchmark/Results/…` are all not data. |
| Merges; evidence sharing history | Unchanged: these tests already matched the rulings. |

## Still ambiguous after v1.1 (left open)
- **P10 Which sha a tag push names.** v1.1 doesn't say whether the refusal text and the level line for a tag use the tag object's sha or the tagged commit's. The tag tests only check the prefix and the message, not the sha.
- **P11 Which receipt a tag push needs.** "A receipt for exactly `local_sha`" doesn't fit tags, because `local_sha` is the tag object and receipts only exist for commits. My positive test assumes the receipt for the tagged commit counts; otherwise a fork code tag could never pass. Please confirm.
- **P12 The existing test that will break.** v1.1 says the implementer replaces `test_local_gate.py::test_a_branch_push_needs_no_receipt_only_the_scans`. For now it still passes; it is one of the 59.
