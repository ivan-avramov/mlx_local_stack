Q1. Committed locally: `acb9364`. Issues 1–5 fixed; issue 6 partially fixed. No push or live-benchmark changes.

Q2. Fix → tests: URL/shell variants, planned-deny resume checks, provisional cheat accounting, invalid labels, punctuation/host/port normalization, and bounded repository forms all have regressions using the faithful opencode matcher.

Q3. Targeted tests under `nice -n 19`: **P202 30 passed; round6 40 passed; round7 39 passed, 1 expected failure**.

Q4. [Full report and every emitted pattern list for all three URLs]($STACK_WORKDIR/m61/wt-r5/docs/m61-round7-report.md).

Q5. **Open blocker C142:** opencode’s `?` is a wildcard, so `*github.com/Foo/Bar?*` also denies `Bar-docs`. Several requested bare-prefix `*` forms have the same conflict. Repository boundaries are preserved; root-query coverage remains incomplete.

I recommend a literal-URL matching change. Do you authorize that follow-up, or permit sibling over-denial?