## Findings

**F1 — blocker — fork-tag level line names the tag object's sha8, not the tagged commit's (violates v1.2).**
Location: `local_gate.py` `_level_of` / `check_lines`, lines ~448–453 and ~477.
Evidence: confirmed. `check_lines` computes `sha = _git(repo_dir, "rev-parse", f"{local_sha}^{{commit}}")` and passes that `sha` to `_level_of` for the receipt lookup and refusal message (correct, matches v1.2), but `_level_of` also builds the level line as `f"level: {shown} {remote_ref} {sha[:8]}"` using the same resolved `sha`. That part is correct. The defect is in the **test**, not the code: `test_main_prints_the_level_of_a_fork_docs_only_tag` asserts only `l.startswith("[pre-push] level: docs-only refs/tags/v1.0.0 ")` and its comment says "sha8 of the tag object or of the tagged commit: not pinned by v1.1." v1.2 (in `spec.md` line 40) explicitly pins this to the tagged commit. The test therefore does not verify the v1.2 pinning it is supposed to enforce, and its comment is now wrong.
Problem: a future regression that re-introduces tag-object sha8 in the level line (or in the receipt lookup) would pass this test.
Scenario: change `_level_of` to use `local_sha` for the level line; the test still passes but v1.2 is violated.
Proposed change: assert the exact line `f"[pre-push] level: docs-only refs/tags/v1.0.0 {tagged_commit[:8]}"` (compute the tagged commit's sha in the test) and drop the "not pinned" comment.

**F2 — major — `test_a_fork_code_tag_without_a_receipt_refuses` does not pin the refusal's sha8 to the tagged commit (v1.2).**
Location: `test_p541_push_level.py` ~lines 480–486.
Evidence: confirmed. The assertion is `out[0].startswith(f"REFUSED: {repo} ")` plus `"no PASS gate receipt for a code push" in out[0]` — it never checks the sha8. v1.2 requires the refusal to name the tagged commit's sha8. A regression that names the tag object's sha8 (or the wrong commit) would pass.
Scenario: `check_lines` resolves `local_sha^{commit}` correctly today, but if someone removed the `^{commit}` resolution for tags, the refusal would name the tag object sha8 and this test would still pass.
Proposed change: assert `out[0] == _refusal(repo, tagged_commit_sha)` (compute the tagged commit's sha in the test).

**F3 — major — `test_a_fork_code_tag_with_a_receipt_for_the_tagged_commit_passes` does not reject a receipt for the tag object.**
Location: `test_p541_push_level.py` ~lines 488–494.
Evidence: confirmed. The test creates a receipt for the commit sha and confirms the tag push passes. It does not verify the negative case the spec implies: a receipt filed under the tag object's sha (if `^{commit}` resolution were skipped) must NOT be accepted. Combined with F2, the v1.2 "resolve to commit" guarantee is only half-tested (positive path only).
Problem: the test claims to "guard that receipts are looked up by the tagged commit" but only exercises the positive direction.
Scenario: if `check_lines` stopped resolving `^{commit}` and looked the receipt up under the tag-object sha, this test would still pass (it only files a receipt for the commit, which would no longer match — actually it would then fail). Re-examining: if resolution were removed, `pass_receipt(..., tag_object_sha, ...)` would not find the commit-sha receipt → refusal → test fails. So the positive test does catch that regression. Downgrade: this test is adequate for the positive path; F2/F1 are the real gaps. No separate finding — withdraw F3.

**F4 — minor — `_touched` on a merge ignores `--root` semantics only for non-merges; an octopus merge's first-parent diff may omit code brought in via parents 2..n that is not in the first-parent diff.**
Location: `local_gate.py` `_touched`, lines ~376–382.
Evidence: confirmed by reading; matches spec ("a merge contributes its diff against its first parent"). This is the spec's chosen semantics, so it is not a defect — but note: a merge that brings code in via parent 2 where that code is already in parent 1's tree (no net diff) is classified by the first-parent diff only. Consistent with spec; the test `test_a_merge_contributes_its_diff_against_its_first_parent` covers the bring-in case. No action — listing only because the brief asks about wrong-level classification; this is correct-by-spec. Withdraw as a finding.

**F5 — minor — `test_a_stack_evidence_push_sharing_history_with_main_still_refuses_as_not_orphan` uses `local_ref="refs/heads/main"` while pushing to `refs/heads/evidence`.**
Location: `test_p541_push_level.py` ~lines 422–426.
Evidence: confirmed. The line is `_line(sha, "refs/heads/evidence", local_ref="refs/heads/main")`, i.e. local ref `refs/heads/main` → remote `refs/heads/evidence`. The orphan check in `check_lines` is `merge-base --is-ancestor sha {remote}/main`. The commit is a normal child of base on main, so it IS an ancestor of `origin/main` after the fetch — refused as "not an orphan". The test passes, but the scenario it names ("evidence push sharing history with main") is exercised via a local-ref trick rather than a real evidence-branch commit that shares history. The assertion `any("not an orphan data commit" in o for o in out)` is correct. The test does test what it claims (a commit on main pushed to evidence is refused). No defect. Withdraw.

**F6 — major — `push_level` for the evidence branch short-circuits before the orphan check, so `push_level` returns `data-only` for an evidence commit that actually shares history with main.**
Location: `local_gate.py` `push_level`, lines ~386–388; `check_lines` evidence block, lines ~471–476.
Evidence: confirmed. `push_level` has `if repo == "stack" and remote_ref == EVIDENCE_REF: return "data-only", "", []` as its very first check — it does NOT verify the orphan property. The orphan check lives only in `check_lines`, which appends a problem and `continue`s before calling `_level_of`. So in production (`check_lines`) the refusal happens first and `_level_of` is never reached for a sharing-history evidence commit — correct. But `push_level` in isolation returns `("data-only", "", [])` for ANY evidence ref update, even one sharing history with main. The interface contract in `spec.md` says `push_level` is "pure apart from git reads" and returns `(level, detail, problems)`; the spec's Levels section defines data-only for evidence as "the P447 orphan rule stays exactly as today: shares no history with `<remote>/main`". So `push_level` returning data-only without checking orphan-ness is an incomplete implementation of the level's own definition.
Problem: any direct caller of `push_level` (the documented public interface) gets a wrong level for a non-orphan evidence commit. The independent tests call `push_level` directly in several places (e.g. `test_a_stack_evidence_orphan_is_data_only_and_pii_only`) but none test the non-orphan case through `push_level` — they only test it through `check_lines`. So the gap is untested.
Scenario: a future caller uses `push_level` to decide whether to accept an evidence push and trusts the `data-only` result without re-running the orphan check → a non-orphan (code-carrying) commit pushed to `evidence` is labelled data-only.
Proposed change: move the orphan check into `push_level` (return `("full", "", [<orphan refusal>])` or a dedicated problem when the evidence commit shares history with main), and have `check_lines` rely on `push_level`'s problems rather than duplicating the check. Alternatively, document in `push_level`'s docstring that the orphan check is the caller's responsibility and add a `push_level` test for the non-orphan evidence case asserting it is NOT `data-only`. The spec wording ("the orphan rule lives in `check_lines`" comment in the code) suggests the implementer chose the split deliberately, but the spec's Levels definition does not delegate it — flagging as a scope/contract mismatch.

**F7 — minor — `test_push_level_does_not_fetch` does not verify `introduced` was called against the right remote.**
Location: `test_p541_push_level.py` ~lines 408–412.
Evidence: confirmed. The test points origin at a missing URL and asserts `push_level` returns docs-only. Because the docs-only branch returns before `introduced` is called, no fetch happens. The test claims "the fetch stays in `check_lines`" — true for a docs-only push, but it does not exercise the `full`/`none-new` paths where `introduced` (which reads `--remotes=<remote>` but does not fetch) is called. `introduced` itself does not fetch (it's `git rev-list ... --not --remotes=<remote>`, reading remote-tracking refs), so the claim holds; the test is just narrow. Not a defect. Withdraw.

**F8 — minor — ambiguous output: when `local_sha^{commit}` fails to resolve, `check_lines` raises `GateError` and `main` prints `[local_gate] REFUSED: git rev-parse ...` rather than a per-ref refusal.**
Location: `local_gate.py` `check_lines` line ~470, `main` lines ~641–642.
Evidence: confirmed. `sha = _git(repo_dir, "rev-parse", f"{local_sha}^{{commit}}")` uses `_git` with `check=True`, so a bad sha raises `GateError`, which `main` catches and prints as `[local_gate] REFUSED: <exc>`, and no level lines are printed for any ref (the whole loop aborts). This is pre-existing behaviour (not introduced by P541 — the `^{commit}` resolution was already there per v1.2 "as `check_lines` already does"). Not a P541 regression. Withdraw.

**F9 — major — a stack `data-only` push to a non-evidence branch skips the naming scan but `push_level` returns no problem; the level is `data-only` even when the data commit's message violates naming.**
Location: `local_gate.py` `check_lines` lines ~477–479; `_scan` called with `naming=True` for non-evidence.
Evidence: confirmed by reading. For a non-evidence stack branch, `check_lines` runs `out += _scan(repo_dir, introduced(...), naming=True)` (naming ON) and THEN `_level_of`. So naming IS scanned for a `benchmark/results/**`-only stack branch push. The level is `data-only` and the naming scan still runs. This matches spec ("The existing per-commit scans (PII + naming; evidence: PII only) still run for every level"). Correct. Withdraw.

**F10 — major — `test_the_message_scan_still_runs_on_a_docs_only_push` uses a message that may not actually trigger the naming scan.**
Location: `test_p541_push_level.py` ~lines 468–472.
Evidence: hypothesis (not reproduced — would need `bench.modelnames`). The commit message is `"Ornith regressed"` with a comment `# allow-shorthand: the violation under test`. The test asserts `any("message" in o for o in _check(...))`. Whether `"Ornith regressed"` triggers `modelnames.message_violations` depends on the naming rules (the comment claims "Ornith" is a shorthand that violates). I cannot confirm without reading `modelnames`. If "Ornith" is NOT a known shorthand in `modelnames`, the test would fail (no "message" line) — but the test is in the submitted suite, so presumably it passes in the real environment. Flagging as hypothesis: the test relies on an external naming rule that the test file does not make explicit; if `modelnames`' shorthand list changes, the test breaks silently. Not a code defect. Minor / hypothesis.

**F11 — minor — `test_an_empty_P_is_full` and `test_a_docs_commit_plus_an_empty_commit_is_docs_only` create empty commits via `--allow-empty` but do not assert that `_touched` returns `[]` for them.**
Location: `test_p541_push_level.py` ~lines 358–378.
Evidence: confirmed. The tests assert the final level via `push_level` but never directly assert `G._touched(work, empty_sha) == []`. The behaviour (empty-diff commit → no paths → P empty → full, or docs-only when combined with a docs commit) is tested only end-to-end. Adequate but fragile. Not a defect. Withdraw.

**F12 — scope request — `push_level` does not validate that `local_sha` is a full 40-hex sha; the refusal message interpolates `local_sha[:8]` and `--sha {local_sha}` verbatim.**
Location: `local_gate.py` `push_level` lines ~398–399.
Evidence: confirmed. `check_lines` always passes a resolved `sha` (40-hex), so in production this is fine. A direct caller passing a short sha would produce a misleading `--sha` hint. Not exercised. Scope request: either document that `push_level` expects a full sha, or resolve `^{commit}` inside `push_level`.

---

### Substantive findings

- **F1** (blocker): test does not pin the fork-tag level line's sha8 to the tagged commit (v1.2 violation the test fails to catch) + stale comment.
- **F2** (major): test does not pin the fork-tag refusal's sha8 to the tagged commit (v1.2).
- **F6** (major): `push_level` returns `data-only` for evidence without checking the orphan rule; the level's own definition is only enforced in `check_lines`, so direct callers of the documented interface get a wrong level for a non-orphan evidence commit, and no test covers `push_level` on a non-orphan evidence update.

The rest were examined and withdrawn (correct-by-spec, pre-existing, or test-narrowness without material consequence).
