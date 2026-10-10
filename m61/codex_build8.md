- Shell URL splitting/ref stripping → extraction regressions pass.
- Original host/port and lowercase GitHub forms → matcher tests pass.
- Bounded page rules and shell boundaries → deny/allow regressions pass.

Failing tests first: 36 failed → all 44 new cases passed.
M61-only tests under `nice -n 19`: **278 passed, 1 existing xfailed**.

Commit: `7679bbc`