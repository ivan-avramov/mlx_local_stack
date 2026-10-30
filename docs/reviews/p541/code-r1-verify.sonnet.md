Dispositions, checked against `repair.diff`, `spec.md` v1.3/v1.4 and the repaired module. I did not run anything; each is a source trace.

1. **Resolved.** `_git_raw` returns unstripped stdout, and `_touched` splits it on NUL. `is_docs_path` and `is_data_path` get the exact path. The tests cover the leading-space, trailing-space, leading-newline and inner-newline cases for all three repos.
2. **Resolved.** `introduced(..., exclude_evidence=True)` adds `--exclude=<remote>/evidence` before `--remotes=<remote>`. Git applies that pattern relative to `refs/remotes/`, so it matches only `refs/remotes/<remote>/evidence`. `push_level` and the scan in `check_lines` both pass `exclude_evidence=remote_ref != EVIDENCE_REF`, so scan and level use the same C. The new tests pin both the code case (`full`) and the data case (`data-only`, not `none-new`).
3. **Resolved.** `push_level` resolves `^{commit}` first and owns the orphan rule. `check_lines` no longer repeats the check, and the not-orphan problem appears once. A short or tag sha now works when `push_level` is called directly, and a test covers the tag case.
4. **Resolved.** The `digest_for` and `pass_receipt` call is wrapped in `except Exception` and becomes the v1.3 problem for that ref only. The test with two refs shows the other ref keeps its level line, in either order.
5. **Resolved.** `check_lines` collects each ref's problems in `ref_out`, covering scan, level and stack-tag problems. It appends a `level:` line only when `ref_out` is empty. The test shows a ref with a PII problem prints no level line and a clean ref still does.
6. **Resolved.** `_receipt_named` writes a correctly named file with a wrong inner digest, sha or verdict, and the parametrised test refuses all three.
7. **Resolved.** The tag tests assert the tagged commit's sha8 and check that it differs from the tag object's.
8. **Decline accepted.** The naming-scan test depends on the `modelnames` list, and that dependency is intended.
9. **Resolved**, within item 3.
10. **Accepted.**
    - The stack-tag release and gitlink `digest_for` calls are unchanged and sit outside the level rules. An exception there still refuses the push: `GateError` is caught in `main`, and anything else exits non-zero with a traceback.
    - A non-orphan evidence push now also gets the PII scan and the naming scan. That is stricter, never weaker.

I found no new defect in the repair. The stack-tag path keeps its order: scan, SemVer, release receipt, gitlinks. The evidence orphan rule is preserved, and non-orphan pushes are still refused.

NOTHING OF SUBSTANCE
