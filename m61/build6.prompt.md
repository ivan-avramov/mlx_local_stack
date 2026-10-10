Continue the M61 implementer job, round 6 (fixes from a cold verification of your P202 commit 79d34ad). WORK ONLY IN
$STACK_WORKDIR/m61/wt-r5 (branch m61-r5). A live benchmark runs on this box from the main checkout:
never touch $STACK_REPO; DO NOT run the full suites; run only the M61 test files and any file you change,
always under `nice -n 19` (`cd benchmark && env -u STACK_WORKDIR nice -n 19 ../.venv-bench/bin/python -m pytest <files> -q -p no:cacheprovider`).
Other rules as in $STACK_WORKDIR/m61/build.prompt.md. Verifier repro scripts: $STACK_WORKDIR/m61/verify5/.

Fix, each with a failing test first:
1. Fail closed on missing/stale audits: `audit_states` marks web entries with no matching audit record (missing sidecar,
   prompt sha / auditor version mismatch) as `missing`, distinct from `unclear`. `cheats_to_rerun` raises
   `AuditMissing("audit first: missing/stale audit for <item>")` when any latest row has a missing entry; the probe's re-run
   resume says the same instead of "cheated item requires explicit --rerun-of". `report_rows` refuses (or marks provisional
   with a count) when entries are missing.
2. Deny patterns in the carrier's style: scheme-less with a leading wildcard, e.g. `*github.com/<owner>/<repo>*`,
   `*raw.githubusercontent.com/<owner>/<repo>*`, GitLab likewise (accept the over-match on `<repo>-foo`), as-fetched AND
   lowercase casings; the same patterns for shell. Must match: repo root, `.git`, `git clone https://github.com/O/R`,
   `http://` and `www.` variants, raw mirror paths. Test with the real binary: a webfetch of the repo root and a shell
   `git clone` of the repo both rejected without reaching a local target (use a local mock host mapping or the
   resource-matching path that does not need the internet — show how you made it hermetic).
3. Never over-deny: refuse `*` and `?` in URL-derived input (sanitize: drop the URL from patterns and record it); never emit a
   host-root or bare-owner prefix (`github.com/<owner>` alone, `example.com/*`); for non-repo URLs use the exact URL without
   query (scheme-less, leading `*`) plus its parent path only when the parent has at least two path segments; when the source
   of a contact is unknown (incomplete audit / contact with no URL), do NOT deny every URL in the row — emit no patterns and
   flag the job `needs_operator: true` (see 6).
4. `report_rows`: per-model `pending_reruns`; results with pending > 0 are labelled provisional.
5. Same-instance check for re-runs also compares the worker load identity (worker pid + model path from the router/worker
   provenance already recorded), not only the router pid.
6. Empty deny list or `needs_operator` → `cheats_to_rerun` returns the job with `needs_operator: true` and no re-run is
   launched for it; the item is reported as `cheat_review` (excluded from strict, counted) until the operator rules.
7. Cross-scaffold rows (non-web rows with answer_key_contact) are never returned as re-run jobs; they are reported as flagged.
8. Auditor prompt: state explicitly that a complete implementation of this exercise in ANOTHER language, or one whose API
   differs but whose algorithm/structure transfers directly, is `solution`; a description of the approach without code is
   `partial`; "near-complete" = would pass most tests after trivial edits.
Report (terse, Q-numbered): fix → test, one line each; targeted test summary; how 2 was made hermetic; open questions.
