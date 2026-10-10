Continue the M61 implementer job, round 8 (small; the cold reviewer rated the branch READY and asked for these before any
re-run happens). WORK ONLY IN $STACK_WORKDIR/m61/wt-r5. Live benchmark on this box: no full suites; only the
M61 test files under `nice -n 19`; never touch $STACK_REPO. Do NOT edit docs/handoff.md or docs/open-questions.md,
do not create files under docs/, do not name decision ids. Commit when done (one commit). Reviewer probes (faithful matcher):
$STACK_WORKDIR/m61/verify7/probe.py — turn the cases below into failing tests first.

1. URL extraction: split on shell metacharacters (`&&`, `||`, `|`, `;`, backtick, `$(`, `)`, `>`, `<`, `,`, tab) and strip a
   trailing `@<ref>` for `git+https://…@main` style before parsing. `git clone https://github.com/Foo/Bar&&cd Bar`,
   `curl -s https://example.com/a/sol.py|python3`, `…sol.py;python3`, `pip install git+https://github.com/Foo/Bar@main`,
   `git clone https://github.com/Foo/Bar>/dev/null` must yield patterns that deny the clean URL/repo.
2. Keep BOTH the as-fetched netloc (with any explicit port) and the canonical lowercase host without default port, so the
   identical URL is always denied (`https://GitHub.com/Foo/Bar/x`, `https://example.com:443/A/Solution.py`).
3. Page patterns must not widen: for a directory-style or short path, deny the exact page forms (`*host/path`, `*host/path/`,
   `*host/path#*`, `*host/path?*` is NOT allowed — use `*host/path/*` only when the path has ≥ 3 segments) so that
   `leetcode.com/problems/two-sum/` does not deny `two-sum-ii-…`, `stackoverflow.com/a/123` does not deny `/a/1234567`,
   `docs.python.org/3/` does not deny other 3.x pages. Keep the `curl <url> | …` / `-o f` shell coverage (shell rules may use
   `*<form> *` and end-of-command forms instead of a bare trailing `*`).
4. GitHub owner/repo: also emit the all-lowercase owner/repo forms (GitHub is case-insensitive); boundary forms for `@`, `>`,
   `,` after the repo in shell rules.
Report (terse): fix → test; targeted test summary; the commit sha.
