## Findings — P627 candidate (cold review)

I traced the candidate (`benchmark/bench/local_gate.py:300-411`) against spec v1.2 and the frozen tests (`.p627-material/test_local_gate_absent_skips.py`); I could not execute the suite (sandbox blocks `git init` writes), so evidence is by static trace.   <!-- allow-shorthand: verbatim reviewer output -->

### Opinion-round findings — resolved/not

**Sol P1 / GLM F1 — class-named file vs module file ambiguity.** Resolved. `_absent_allowed` requires exactly one dotted prefix to be a tracked `.py` file in live (`len(tracked) != 1 → False`, `local_gate.py:321-322`); a class-named decoy alongside the real module file makes two and is refused. Frozen `test_two_live_prefix_files_make_the_entry_ambiguous_and_refused` pins it.

**Sol P2 / GLM F2 — failed/errored junit id reclassified as absent.** Resolved. `if entry in junit_ids: return False` (`local_gate.py:319`) gates the whole path; `_junit_ids` is the full testcase set. Frozen `test_an_id_that_failed_or_errored_in_the_junit_is_not_absent_allowed` (param failed/errored) pins it.

**Sol P3 / GLM F5 — symlinks / `Path.is_file()` follows links.** Resolved. The live check now reads `git ls-tree HEAD -- <rel>` and requires mode `100644`/`100755` (`local_gate.py:323-325`); on-disk state is not consulted. Frozen `test_a_live_symlink_does_not_allow_the_entry` pins it.

**Sol P4 — `baseline_skips_absent` not always present.** Resolved. The key is initialized in the receipt dict (`local_gate.py:352`), before any guard, so early-step failures still emit `[]`. Frozen `test_the_key_is_present_when_an_earlier_step_fails` and `test_the_key_is_an_empty_list_on_a_fail` pin it.

**Sol P5 / GLM F3 — "absent in gated, present in live" ≠ "added later" (untracked; staged-uncommitted; unrelated history; deleted-before-sha).** Resolved. `_absent_allowed` requires the file tracked at live HEAD, its adding commit via `git log --diff-filter=A -1 HEAD -- <rel>`, and `git merge-base --is-ancestor <sha> <added>` (`local_gate.py:326-330`). Frozen `test_an_untracked_live_file…`, `test_a_staged_but_uncommitted_live_file…`, `test_a_live_file_added_on_an_unrelated_history…`, `test_a_live_file_added_before_the_gated_sha_and_deleted_by_it…` each pin one.

**GLM F1 — longest-prefix decoy masks a gated module file (gated tree first).** Resolved. `any((Path(scratch)/p).is_file() for p in paths) → False` (`local_gate.py:320`) short-circuits before the live check. Frozen `test_a_live_only_class_named_file_does_not_allow_an_entry_whose_module_file_is_in_the_gated_tree` pins it.

**GLM F4 — `skip list != baseline: +{extra} -{missing}` still lists absent-allowed entries in `‑missing`.** Not resolved (declined by design). The spec v1.2 explicitly leaves C277's message unchanged ("Nothing else changes (C277's multiset / duplicate / junit-missing rules…)"), and `dispositions.md` records the decline. Cosmetic only; no gate outcome changes; not a candidate defect.

### Anything else the diff breaks or leaves failing

I traced every frozen test in `test_local_gate_absent_skips.py` (absent-in-gated/present-in-live PASS; absent-in-both FAIL; present-in-gated-not-collected FAIL; class/nested-class resolution; no-`::` and malformed entries; executable regular file; untracked/staged/unrelated-history/added-before-sha/symlink refusals; ambiguous two-prefix refusal; failed/errored id refusal; mixed baselines; C277 ran-and-passed disjoint from absent; extra-skip-not-excused; duplicate-rule-still-fires; missing-junit; no-baseline; six-steps-and-scratch-removed; policy-digest-independence) — each yields the asserted verdict and lists. The diff's only other edits are the `baseline_skips_absent=[]` initialization in the receipt dict and removal of the now-redundant `receipt["baseline_skips_ran"] = []` (relocated to the init dict, same effect), so C277's `baseline_skips_ran` path and the existing `test_local_gate_ran_skips.py` suite are unchanged. `_junit_ids` re-parses a junit already validated by `skipped_from_junit`/`ran_and_passed_from_junit`, so no new crash path. `_absent_allowed`'s `_git(..., check=False)` calls return `""` on absent paths and are filtered, so a path present in neither tree does not raise.

NOTHING OF SUBSTANCE
