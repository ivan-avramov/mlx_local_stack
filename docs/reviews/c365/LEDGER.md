# C365 cold read — ledger (round 1 of 3)

Member: Sol (`gpt-5.6-sol-high`, cursor-agent `--mode ask`, read-only, `checkout` = a scratch clone at `9abef6a69`; user instructions
unconfirmed; no session id reported), exit 0, raw output `cold-read-sol-r1-report.md`. Brief `brief.md`, material `fix.diff`.

| id | Sol | disposition | reason |
|----|-----|-------------|--------|
| P1 | major: `graded.set()` in `finally` fires the stop even when the snapshot grade raises, masking a grader defect | ADOPTED (minor) | The event is set only after a grade returns. Minor: other tests cover the grader; this one tests the SIGTERM cleanup. |
| P2 | major: the firing thread is never stopped; after an early failure it SIGTERMs a later test | ADOPTED (minor) | A stop event + lock: the thread signals only while the test is live; `finally` sets it and joins. Pre-existing in the shared `when` helper (unchanged; its other users fire on markers the test itself waits for). |

Not re-gated alone: the running gate of `9abef6a69` (the tg2 arms' commit) stays valid — both findings matter only once the test
already fails or the grader is broken; this commit rides into the next gate. `test_c147_cancel.py` 30 / 30, three runs.
