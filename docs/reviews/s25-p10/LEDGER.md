# S25-P10 cold read — ledger (round 1 of 3)

Member: Sol (`gpt-5.6-sol-high`, cursor-agent `--mode ask`, read-only, `checkout` context = a scratch clone with the diff applied;
user instructions unconfirmed; no session id reported), exit 0, raw output `cold-read-sol-r1-report.md`. Brief `brief.md`, material
`fix.diff` (as reviewed; the adopted changes below came after).

| id | Sol | disposition | reason |
|----|-----|-------------|--------|
| P1 | blocker: the stack pytest step inherits `PYTEST_ADDOPTS` / `PYTEST_PLUGINS` (a `-k` can deselect the closure test, PASS) | ADAPTED (minor, pre-existing) | Real for the whole suite, not introduced here; neither variable is set on this box. The stack step now removes both (`PYTEST_ENV_DROP`, as the mlx-vlm run). `-o addopts=` not added: it would also drop configured addopts, a suite behaviour change. |
| P2 | blocker: `git diff --name-only` lists only a rename's destination; renaming a protected file away passes | ADOPTED | Confirmed. `carrier_edits` uses `--no-renames`; regression test. |
| P3 | blocker: `run` trusts a possibly stale local `origin/main` | DEFERRED → S27-P2 (operator) | Real only when `main` moves on GitHub from somewhere other than this box's own push (all pushes come from this box, C350). A fix belongs at the pre-push check, which already fetches; that changes push policy, so it is its own proposal. |
| P4 | blocker: `check` / `release` accept a receipt regardless of its `pushed_base` | DEFERRED → S27-P2 (operator) | A sha binding was built, then taken out (side-agent note, adopted: a code push would need a fresh multi-hour gate whenever GitHub `main` moved after gating — a push-policy change beyond S25-P10). The receipt records `pushed_base`; nothing enforces it yet. |
| P5 | major: nothing refuses base == HEAD | DECLINED | base == HEAD means nothing is unpushed: "this build" is empty and the empty diff is the true answer. Refusing would make gating any already-pushed commit impossible (a release on a new box). At push time the remote's main cannot contain the commit being pushed (S27-P2 would bind it). |

Tests: `bench/tests/test_s25_p10_pushed_base.py` (red first: ImportError on the old code; then the P1 / P2 regressions);
two M80 step-list pins updated for the added env keys (they failed on the change, 3 failed / 44 passed, as predicted).
