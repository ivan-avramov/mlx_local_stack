# Fix round 2, clarification (same session) — two small items, then the frozen v3 set

1. Y6 extended: cap the chain scan's `path_only` basename with the same `FOREIGN_ARGV0_CAP` (scrub first, then cap). Test.
2. Test-writer finding (delivery 3, minor, adopted): when an interim grade's infrastructure fault is returned by
   `GradeWorker.finish()` (X3), the faulted capture's boundary was added to `gate.pending` at capture time and is never discharged,
   so after the client exits an earlier faulted boundary above `last_progress_boundary` can keep the stall rule from firing at the
   terminal decision. Intent: a faulted interim grade must not change the item's nonconvergence flags — discharge (or drop) that
   boundary as ungraded so the terminal decision is what it would be had that capture never been graded. Red test first.
3. The frozen acceptance set is now v3 (`benchmark/bench/tests/test_s27_fe_*.py`, 12 files incl. `test_s27_fe_r1.py`, and
   `fixtures/s27_fe/`; READ-ONLY). Run it on your working tree: all must pass. If one fails because of a Y1–Y6 change, report
   whether the test or the fix is wrong under the specification and the ledger — do not edit the frozen files.

Append to `../scratch/implementer-fix2-report.md` (a "Clarification" section) and end with it as your final message. The constraint
block of your brief still applies.
