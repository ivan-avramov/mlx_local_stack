I made the P627 change in `benchmark/bench/local_gate.py`, the only file I touched. The existing gate tests pass. The new acceptance file `bench/tests/test_local_gate_absent_skips.py` doesn't exist in this copy yet, so none of the new rule's cases have been tested.

**The change**
- **New helper `entry_test_file(entry, roots)`** (just above `run`). It takes an entry like `a.b.c::name` or `a.b.c.Class::name` and returns the longest dotted prefix that is a `.py` file under any of the given roots (for example `a/b/c.py`), relative to the repo top. It returns `None` when the entry has no `::`, when a dotted part is empty, `.`, `..` or contains a slash, or when no prefix is a file.
- **Skip check in `run`, after C277's `unexplained` list:**
  - For each entry still unexplained, I find its file across both the scratch tree and the live tree.
  - The entry is moved to `receipt["baseline_skips_absent"]` (sorted) only if the file is missing from scratch and present in live. Only entries still unexplained after that cause the "baseline skip neither skipped nor passed" failure.
  - `baseline_skips_absent` starts as `[]` next to `baseline_skips_ran`.
  - Nothing else changed: the multiset, duplicate and junit-missing rules, `check`, and the digest are as before.

**Test command summary line (verbatim):** `225 passed in 92.65s (0:01:32)`

I didn't run the real gate (as the brief says). Two other checks were blocked by the permission prompt and not run: a direct run of the helper against the real tree and a `git diff --stat`.

**Ambiguities**
- **P1 — which tree the path is found in.** The spec says "the longest dotted prefix that is a `.py` file" but not in which tree. I check both scratch and live. So a file that is in neither tree, or an entry with no `::`, can't be found and keeps today's failure.
- **P2 — "always present".** I set `baseline_skips_absent` in the same place as `baseline_skips_ran`, which is only reached when all steps complete. A receipt that fails at an earlier step lacks both keys. If "always present" means every receipt, it should be set when the receipt is first built, and `baseline_skips_ran` should get the same treatment.
- **P3 — no "repo top" for the forks.** For mlx-vlm and mlx-serve, the fork's scratch clone root is treated as the repo top, the same way their baseline entries are written (`mlx_vlm.tests…`, `tests.test_config…`).
- **P4 — no gated-tree side check.** Rejecting `.`, `..` and slashes inside dotted parts is a guard I added that the spec doesn't mention.
