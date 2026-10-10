Continue the M61 implementer job, round 5. WORK ONLY IN THIS WORKTREE: $STACK_WORKDIR/m61/wt-r5 (branch `m61-r5`;
the main checkout is in use by a live benchmark — never touch $STACK_REPO). `.venv-bench` here is a symlink to the
main checkout's venv (untracked; leave it). Rules as in $STACK_WORKDIR/m61/build.prompt.md (tests first, local
mocks only, no :8000, no internet, no commit, no home paths in committed files, full model names, never edit docs/handoff.md).

Implement spec section P202 of `docs/specs/m61-web-audit-and-prompt-ab.md` (re-read the whole spec; P201 and the round-4 fixes are
already in the code). Pieces:
1. Auditor labels: add `partial`; update `benchmark/web_audit_prompt.md` with crisp definitions of `partial` vs `solution`
   (solution = complete or near-complete implementation of THIS exercise's required API; partial = exercise-specific hint,
   algorithm description or fragment that is not a working answer). The prompt sha changes (so old audits do not satisfy
   idempotence). Strict parsing accepts the new label.
2. `--extra-deny-file <json>` on the probe AND on `scripts/session_pinning_gate.py` (so receipts match), composed as deny rules
   appended after the carrier's permissions for webfetch and shell; recorded `extra_deny`, `extra_deny_sha256`; scaffold label
   unchanged (`opencode-v2-web`, operator ruling); identity/resume cover it; M50 env check accepts exactly carrier + recorded
   overlay, refuses anything else. Only valid with `--scaffold opencode-v2-web`.
3. A helper `bench/answer_key.py: deny_patterns_for(urls)` producing the P202 prefix patterns (GitHub/GitLab repo + raw
   mirror; otherwise URL without query + parent path `*`), with tests including uppercase variants where the host is
   case-insensitive (emit the lowercased owner/repo AND the as-fetched casing).
4. Re-run plumbing in the probe: `--rerun-of <session_id> --rerun-index N` recorded on the row; rows appended to the same leg
   file; resume logic treats an item as complete when its latest row is a non-cheat or `rerun_index == 2`.
5. Scoring in `report_rows`: per item, latest non-cheat attempt wins; cheat = `solution` label, `unclear` label, or
   `answer_key_contact`; after 2 re-runs still cheating → FAIL with `cheat_unresolved: true`; per-model counts of cheat attempts,
   re-runs, unresolved, partial lookups. `web_audit_incomplete` / `audit_error` rows: treated as cheat (re-run) too.
6. A driver-facing function (importable, e.g. `benchmark/web_audit.py: cheats_to_rerun(rows_path) -> [{item, session_id,
   seed, urls, rerun_index}]`) the runner will call after each leg, returning what to re-run next and the deny file content.
7. Tests per the spec's P202 test list, including a real-binary mock run where the re-run with the denied URL never reaches the
   mock target.

Run both suites and `configgen check` from the worktree (`cd benchmark && env -u STACK_WORKDIR ../.venv-bench/bin/python -m pytest
bench/tests -q -p no:cacheprovider`; `env -u STACK_WORKDIR .venv-bench/bin/python -m pytest configgen/tests -q -p no:cacheprovider`;
`.venv-bench/bin/python -m configgen check`). Report (terse, Q-numbered): files changed; the `cheats_to_rerun` contract; suite
summary lines; open questions.
