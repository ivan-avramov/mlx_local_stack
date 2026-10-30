# Verify — P541 round 1 (post-repair)

## Disposition of the opinion's findings

**1. `_git` strips `-z` output (` docs/x.py` → docs-only).** Resolved. `_git_raw` (374:1-379) returns stdout unstripped; `_touched` (382:1-390) splits on `"\0"` and keeps every non-empty field. `is_docs_path` (368:1) requires the literal `docs/` prefix, so ` docs/x.py` is code. `test_is_docs_path` (133:1-138) and `test_paths_are_read_losslessly` (286:1-292) cover it.

**2. `introduced()` counted `<remote>/evidence` as already pushed (code branch at an evidence commit → none-new).** Resolved. `introduced` (422:1-425) takes `exclude_evidence` and emits `--exclude={remote}/evidence`; `push_level` (404) and `check_lines`' scan (483) pass `exclude_evidence=remote_ref != EVIDENCE_REF`. `test_a_branch_at_an_evidence_only_code_commit…` (312) and the data variant (317) assert full / data-only, not none-new.

**3. `push_level` returned data-only for any evidence push without the orphan check.** Resolved. `push_level` resolves `^{commit}` (397) and owns the orphan rule (399-403): non-orphan → `"full"` + the not-orphan problem; `check_lines` has no duplicate evidence check (the pre-repair block was deleted, repair.diff 100-110). `test_push_level_refuses_a_stack_evidence_push_sharing_history_with_main` (318) and `…accepts_a_stack_evidence_orphan_as_data_only` (324) cover both sides.

**4. A raising `digest_for` crashed the hook.** Resolved. `push_level` wraps the digest call in `try/except` (411-413) and returns a `REFUSED: … cannot compute the policy digest (type: msg)` level problem; `check_lines` is per-ref, so other refs keep their lines. `test_push_level_turns_a_failing_policy_digest_into_a_level_problem` (332) and `test_main_a_failing_policy_digest_refuses_its_ref_and_the_other_ref_keeps_its_line` (555) cover it.

**5. A ref with a scan problem still printed a `level:` line.** Resolved. `check_lines` accumulates scan + level problems into one `ref_out` and only appends a level line when `shown and not ref_out` (506-507). `test_main_a_ref_with_a_scan_problem_prints_no_level_line` (577) covers it.

**6. Receipt-content checks untested.** Resolved. `test_a_receipt_file_named_right_but_wrong_inside_refuses` (201) was added; `pass_receipt` (352-358) checks `verdict`, `sha` and `policy_digest` against the content, so a right-named/wrong-inside file refuses.

**7. Fork-tag tests did not pin the tagged commit's sha8.** Resolved. `test_a_fork_code_tag_without_a_receipt_refuses` (425) asserts `tag != sha` and `[_refusal(repo, sha)]`; `test_main_prints_the_level_of_a_fork_docs_only_tag` (532) and `…full_level_of_a_fork_code_tag…` (540) assert the exact commit sha8.

**8. Naming-scan test depends on `modelnames`.** Declined (no change). N/A.

**9. Scope: `push_level` should resolve a short/tag sha itself.** Resolved (folded into 3): `push_level` resolves `^{commit}` at 397.

**10. Implementer's calls.** (a) stack-tag release (493) and gitlink (449) `digest_for` calls are unwrapped, so a raise propagates to `main`'s `except GateError` (657) → whole-push `[local_gate] REFUSED`, exit 1. This is outside the level rules and pre-dates P541; accepted as the opinion held — not a defect introduced here. (b) The opinion's claim that a non-orphan evidence push "now also gets the PII + naming scan (stricter)" is **not borne out by the code**: the scan key is `naming=not evidence` with `evidence = repo == "stack" and remote_ref == EVIDENCE_REF` (482-484), so every evidence push — orphan or not — gets PII only, matching the spec. The material is correct; the opinion's (b) is inaccurate. No defect in the material.

## Anything else the diff breaks or leaves failing

I traced the level selection, the receipt lookup, the orphan rule, the `--exclude` path, the merge first-parent diff, the empty-P → full rule, mixed docs+data → full, the per-ref level-line gating, the stack-tag (P448) path, and the fork-tag path against the spec and the tests. I checked the tests against what each claims; each tests what it claims (notably `test_paths_are_read_losslessly`' `docs/a\nb.py` → docs-only correctly proves one NUL field, and `test_a_merge_contributes_its_diff_against_its_first_parent` correctly proves a merge brings in excluded topic code via the first-parent diff). I found no bypass, no wrong level, no refusal the spec allows, no weakening of the existing scans / orphan rule / tag rule, and no crash or ambiguous output beyond the accepted item 10(a).

NOTHING OF SUBSTANCE.
