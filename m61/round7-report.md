# M61 round-seven implementer report — 2026-10-08

Q1. **Status: partial; C142 remains open.** Issues 1–5 are fixed and tested. Issue 6 now covers bounded
GitHub page/raw/API/CDN/SSH/gh forms and GitLab subgroup forms without sibling denial, but the prescribed
root-query/bare-prefix wildcard spellings contradict sibling access under opencode 2.0.20. This is not
complete round-seven acceptance.

Q2. **Fix → test.**

| Fix | Targeted regression in `test_m61_round7.py` |
|---|---|
| Non-repo URL itself, query/fragment, www and slash variants; whole-shell-node suffix matching | `test_page_variants_and_entire_shell_node` |
| Planned source denies plus inherited denies required on resume; unrelated/inherited-only files refuse; supersets pass | `test_resume_requires_source_plan_subset` |
| Latest non-web/operator-review cheat remains visible and provisional, even alongside a missing audit | `test_ineligible_latest_cheat_is_visible_and_provisional`, `test_ineligible_cheat_with_missing_audit_still_counts_review` |
| Wrong-case/null/unknown/non-string labels become missing; driver raises AuditMissing | `test_invalid_labels_are_missing` |
| Strip trailing punctuation; normalize host/default ports; preserve original/lowercase paths | `test_url_punctuation_is_removed_from_extraction_and_patterns`, page-variant tests |
| Bounded GitHub aliases, SSH/gh forms, GitLab subgroups and sibling negative controls | `test_repo_boundaries_and_shell_positions` |
| Prove wildcard conflict and retain unmet root-query acceptance | `test_wildcard_contract_cannot_escape_question_or_bound_bare_star`, strict-xfail `test_root_query_and_sibling_contract` |

The POSIX `match` helper faithfully ports verify6/deny.py's opencode 2.0.20 wildcard matcher (regex escaping,
slash normalization, `*`, `?`, optional terminal space-star and dotAll). Tests evaluate every pattern, not
just patterns before the first match. Old fnmatch checks were replaced. Prior tests that asserted sibling
matching, GitLab-to-GitHub raw aliases or unnormalized hosts were corrected to the round-seven requirements.

Q3. **Targeted verification only, all at `nice -n 19`.**

| File | Passed | Expected failure |
|---|---:|---:|
| `test_m61_p202.py` | 30 | 0 |
| `test_m61_round6.py` | 40 | 0 |
| `test_m61_round7.py` | 39 | 1 |
| Total | 109 | 1 |

No unexpected failures or skips; 23.79 seconds. Includes the four existing real-opencode 2.0.20 loopback
integration cases. No model calls, live benchmark changes or full suites. Supplied repro scripts were
copied into worktree scratch with their temporary output destinations redirected there before execution.
Initial failures: exact/page-query/shell suffix denial, sibling over-denial, invalid-label clean scoring,
non-web cheat omission and unrelated-file resume. New regression baseline: 31 failed / 6 passed before
production edits; two additional missing-audit/cheat combinations also failed before their fix.
The worktree-local Python environment avoids the pre-existing `.venv-bench` link into the main checkout.
Detailed raw logs and the JUnit record remain in `.round7/` (untracked).

Q4. **Exact emitted pattern lists.** `webfetch` is the planned `extra_deny` list; `shell` is the final
carrier expansion. Lists below are generated from the implementation, with every entry printed.

URL: `https://github.com/Foo/Bar/blob/main/x.py`

webfetch / extra_deny (36):

```json
[
  "*github.com/Foo/Bar",
  "*github.com/Foo/Bar/*",
  "*github.com/Foo/Bar.git*",
  "*github.com/Foo/Bar#*",
  "*github.com:Foo/Bar",
  "*github.com:Foo/Bar/*",
  "*github.com:Foo/Bar.git*",
  "*github.com:Foo/Bar#*",
  "*raw.githubusercontent.com/Foo/Bar/*",
  "*api.github.com/repos/Foo/Bar",
  "*api.github.com/repos/Foo/Bar/*",
  "*api.github.com/repos/Foo/Bar.git*",
  "*api.github.com/repos/Foo/Bar#*",
  "*cdn.jsdelivr.net/gh/Foo/Bar",
  "*cdn.jsdelivr.net/gh/Foo/Bar/*",
  "*cdn.jsdelivr.net/gh/Foo/Bar.git*",
  "*cdn.jsdelivr.net/gh/Foo/Bar@*",
  "*cdn.jsdelivr.net/gh/Foo/Bar#*",
  "*github.com/foo/bar",
  "*github.com/foo/bar/*",
  "*github.com/foo/bar.git*",
  "*github.com/foo/bar#*",
  "*github.com:foo/bar",
  "*github.com:foo/bar/*",
  "*github.com:foo/bar.git*",
  "*github.com:foo/bar#*",
  "*raw.githubusercontent.com/foo/bar/*",
  "*api.github.com/repos/foo/bar",
  "*api.github.com/repos/foo/bar/*",
  "*api.github.com/repos/foo/bar.git*",
  "*api.github.com/repos/foo/bar#*",
  "*cdn.jsdelivr.net/gh/foo/bar",
  "*cdn.jsdelivr.net/gh/foo/bar/*",
  "*cdn.jsdelivr.net/gh/foo/bar.git*",
  "*cdn.jsdelivr.net/gh/foo/bar@*",
  "*cdn.jsdelivr.net/gh/foo/bar#*"
]
```

shell (128):

```json
[
  "*github.com/Foo/Bar",
  "*github.com/Foo/Bar *",
  "*github.com/Foo/Bar\"*",
  "*github.com/Foo/Bar'*",
  "*github.com/Foo/Bar;*",
  "*github.com/Foo/Bar|*",
  "*github.com/Foo/Bar&*",
  "*github.com/Foo/Bar)*",
  "*gh repo clone Foo/Bar",
  "*gh repo clone Foo/Bar *",
  "*gh repo clone Foo/Bar\"*",
  "*gh repo clone Foo/Bar'*",
  "*gh repo clone Foo/Bar;*",
  "*gh repo clone Foo/Bar|*",
  "*gh repo clone Foo/Bar&*",
  "*gh repo clone Foo/Bar)*",
  "*gh repo clone Foo/Bar/*",
  "*gh api repos/Foo/Bar",
  "*gh api repos/Foo/Bar *",
  "*gh api repos/Foo/Bar\"*",
  "*gh api repos/Foo/Bar'*",
  "*gh api repos/Foo/Bar;*",
  "*gh api repos/Foo/Bar|*",
  "*gh api repos/Foo/Bar&*",
  "*gh api repos/Foo/Bar)*",
  "*gh api repos/Foo/Bar/*",
  "*github.com/Foo/Bar/*",
  "*github.com/Foo/Bar.git*",
  "*github.com/Foo/Bar#*",
  "*github.com:Foo/Bar",
  "*github.com:Foo/Bar *",
  "*github.com:Foo/Bar\"*",
  "*github.com:Foo/Bar'*",
  "*github.com:Foo/Bar;*",
  "*github.com:Foo/Bar|*",
  "*github.com:Foo/Bar&*",
  "*github.com:Foo/Bar)*",
  "*github.com:Foo/Bar/*",
  "*github.com:Foo/Bar.git*",
  "*github.com:Foo/Bar#*",
  "*raw.githubusercontent.com/Foo/Bar/*",
  "*api.github.com/repos/Foo/Bar",
  "*api.github.com/repos/Foo/Bar *",
  "*api.github.com/repos/Foo/Bar\"*",
  "*api.github.com/repos/Foo/Bar'*",
  "*api.github.com/repos/Foo/Bar;*",
  "*api.github.com/repos/Foo/Bar|*",
  "*api.github.com/repos/Foo/Bar&*",
  "*api.github.com/repos/Foo/Bar)*",
  "*api.github.com/repos/Foo/Bar/*",
  "*api.github.com/repos/Foo/Bar.git*",
  "*api.github.com/repos/Foo/Bar#*",
  "*cdn.jsdelivr.net/gh/Foo/Bar",
  "*cdn.jsdelivr.net/gh/Foo/Bar *",
  "*cdn.jsdelivr.net/gh/Foo/Bar\"*",
  "*cdn.jsdelivr.net/gh/Foo/Bar'*",
  "*cdn.jsdelivr.net/gh/Foo/Bar;*",
  "*cdn.jsdelivr.net/gh/Foo/Bar|*",
  "*cdn.jsdelivr.net/gh/Foo/Bar&*",
  "*cdn.jsdelivr.net/gh/Foo/Bar)*",
  "*cdn.jsdelivr.net/gh/Foo/Bar/*",
  "*cdn.jsdelivr.net/gh/Foo/Bar.git*",
  "*cdn.jsdelivr.net/gh/Foo/Bar@*",
  "*cdn.jsdelivr.net/gh/Foo/Bar#*",
  "*github.com/foo/bar",
  "*github.com/foo/bar *",
  "*github.com/foo/bar\"*",
  "*github.com/foo/bar'*",
  "*github.com/foo/bar;*",
  "*github.com/foo/bar|*",
  "*github.com/foo/bar&*",
  "*github.com/foo/bar)*",
  "*gh repo clone foo/bar",
  "*gh repo clone foo/bar *",
  "*gh repo clone foo/bar\"*",
  "*gh repo clone foo/bar'*",
  "*gh repo clone foo/bar;*",
  "*gh repo clone foo/bar|*",
  "*gh repo clone foo/bar&*",
  "*gh repo clone foo/bar)*",
  "*gh repo clone foo/bar/*",
  "*gh api repos/foo/bar",
  "*gh api repos/foo/bar *",
  "*gh api repos/foo/bar\"*",
  "*gh api repos/foo/bar'*",
  "*gh api repos/foo/bar;*",
  "*gh api repos/foo/bar|*",
  "*gh api repos/foo/bar&*",
  "*gh api repos/foo/bar)*",
  "*gh api repos/foo/bar/*",
  "*github.com/foo/bar/*",
  "*github.com/foo/bar.git*",
  "*github.com/foo/bar#*",
  "*github.com:foo/bar",
  "*github.com:foo/bar *",
  "*github.com:foo/bar\"*",
  "*github.com:foo/bar'*",
  "*github.com:foo/bar;*",
  "*github.com:foo/bar|*",
  "*github.com:foo/bar&*",
  "*github.com:foo/bar)*",
  "*github.com:foo/bar/*",
  "*github.com:foo/bar.git*",
  "*github.com:foo/bar#*",
  "*raw.githubusercontent.com/foo/bar/*",
  "*api.github.com/repos/foo/bar",
  "*api.github.com/repos/foo/bar *",
  "*api.github.com/repos/foo/bar\"*",
  "*api.github.com/repos/foo/bar'*",
  "*api.github.com/repos/foo/bar;*",
  "*api.github.com/repos/foo/bar|*",
  "*api.github.com/repos/foo/bar&*",
  "*api.github.com/repos/foo/bar)*",
  "*api.github.com/repos/foo/bar/*",
  "*api.github.com/repos/foo/bar.git*",
  "*api.github.com/repos/foo/bar#*",
  "*cdn.jsdelivr.net/gh/foo/bar",
  "*cdn.jsdelivr.net/gh/foo/bar *",
  "*cdn.jsdelivr.net/gh/foo/bar\"*",
  "*cdn.jsdelivr.net/gh/foo/bar'*",
  "*cdn.jsdelivr.net/gh/foo/bar;*",
  "*cdn.jsdelivr.net/gh/foo/bar|*",
  "*cdn.jsdelivr.net/gh/foo/bar&*",
  "*cdn.jsdelivr.net/gh/foo/bar)*",
  "*cdn.jsdelivr.net/gh/foo/bar/*",
  "*cdn.jsdelivr.net/gh/foo/bar.git*",
  "*cdn.jsdelivr.net/gh/foo/bar@*",
  "*cdn.jsdelivr.net/gh/foo/bar#*"
]
```

URL: `https://pastebin.com/raw/abc?x=1`

webfetch / extra_deny (1):

```json
[
  "*pastebin.com/raw/abc*"
]
```

shell (1):

```json
[
  "*pastebin.com/raw/abc*"
]
```

URL: `https://www.geeksforgeeks.org/solution-x/`

webfetch / extra_deny (4):

```json
[
  "*www.geeksforgeeks.org/solution-x/*",
  "*www.geeksforgeeks.org/solution-x*",
  "*geeksforgeeks.org/solution-x/*",
  "*geeksforgeeks.org/solution-x*"
]
```

shell (4):

```json
[
  "*www.geeksforgeeks.org/solution-x/*",
  "*www.geeksforgeeks.org/solution-x*",
  "*geeksforgeeks.org/solution-x/*",
  "*geeksforgeeks.org/solution-x*"
]
```

Q5. **Open question — C142.** `*github.com/Foo/Bar?*` matches both the wanted `Bar?q=1` and the
unwanted `Bar-docs`. `*api.github.com/repos/Foo/Bar*`, `*cdn.jsdelivr.net/gh/Foo/Bar*`,
`*github.com:Foo/Bar*`, `*gh repo clone Foo/Bar*` and `*gh api repos/Foo/Bar*` also match sibling names.
Wrapping the exact repository-root pattern with a trailing `*` does likewise. There is no literal `?`
escape or negative boundary assertion in this wildcard language. The implementation therefore uses
bounded API/CDN/SSH/gh shapes and exact-root shell token boundaries; root-query coverage remains missing.

Recommendation: retain sibling access and authorize a separate literal-URL matcher/canonicalization
change. The alternative is explicit approval to over-deny sibling repositories. No such broader change
has been made. Re-run cold verification after the decision and its implementation; do not call this build
fully verified merely because the known gap is an expected failure.
