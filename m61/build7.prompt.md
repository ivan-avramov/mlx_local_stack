Continue the M61 implementer job, round 7 (cold re-verification of your d8f10ff found a BLOCKER). WORK ONLY IN
$STACK_WORKDIR/m61/wt-r5. Live benchmark on this box: no full suites, only targeted test files under `nice -n 19`,
never touch $STACK_REPO. Other rules as before. Verifier repro scripts (use them as failing tests first):
$STACK_WORKDIR/m61/verify6/ (deny.py ports opencode 2.0.20 wildcard.ts — keep a faithful port in the tests and
check every pattern against it; states.py; resume.py).

Fix:
1. BLOCKER: non-repo patterns must match the URL itself and its variants: emit `*<netloc>/<path>*` (no query/fragment), plus the
   variant without `www.` and without a trailing slash; shell rules must match the URL anywhere in the command — wrap as
   `*<pattern>*` (opencode's shell resource is the whole command node text, shell/parse.ts:195). Tests: exact URL, `#frag`,
   `?q`, no-www, trailing-slash, `curl <url> | python`, `curl <url> -o f` all DENIED.
2. MAJOR: `_rerun_resume` must require that the planned deny patterns for the source (`rerun_plan(latest_state)['extra_deny']`)
   are a subset of the run's `--extra-deny-file`; an unrelated deny file refuses.
3. MAJOR: `report_rows` must never silently drop a cheat: a latest-attempt cheat that is not re-run eligible (non-web scaffold,
   needs_operator) counts as `cheat_review` and makes the result provisional (or is scored FAIL — choose `cheat_review` +
   provisional, documented).
4. Labels outside LABELS ∪ {audit_error} (wrong case, null, unknown) → treated as missing (AuditMissing), never clean.
5. URL extraction: strip trailing `)]},;:.'"` before deriving patterns; lowercase the host and drop default ports in the
   derived patterns (keep the as-fetched path casing plus a lowercase-path variant).
6. Repo forms: for GitHub O/R emit `*github.com/O/R`, `*github.com/O/R/*`, `*github.com/O/R.git*`, `*github.com/O/R?*`,
   `*github.com/O/R#*`, `*raw.githubusercontent.com/O/R/*`, `*api.github.com/repos/O/R*`, `*cdn.jsdelivr.net/gh/O/R*`,
   `*github.com:O/R*` (ssh form), and for shell additionally `*gh repo clone O/R*` and `*gh api repos/O/R*`; shell variants of
   the URL forms wrapped so they match anywhere (`*github.com/O/R *`, end-of-command, `/`, `.git`, quotes). GitLab: the same
   shapes for gitlab.com with the full project path (subgroups included, no raw.githubusercontent pattern). Siblings like
   `O/R-docs` must NOT be denied (test).
Report (terse, Q-numbered): fix → test; targeted test summary (p202 + round6 + new file); every pattern list printed for the
three example URLs `https://github.com/Foo/Bar/blob/main/x.py`, `https://pastebin.com/raw/abc?x=1`,
`https://www.geeksforgeeks.org/solution-x/`; open questions.
