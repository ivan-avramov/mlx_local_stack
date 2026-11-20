# Test-writer brief, delivery 5 (the last) — S27 bundle, fix round 3 (same session)

Your v4 set was frozen at 2026-11-20T17:27:23Z. Review round 3 (the last) produced ledger Z1–Z9 (`../scratch/change-ledger-r3.md`);
the operator ruled one last fix round (C377), with spec v1.5 §8.1: the watcher's sampled processes carry executable basename + argc,
never argument text. A fresh implementer fixed Z1–Z6, Z8, Z9 (`../scratch/implementer-fix3-report.md`). Your copy now holds
candidate 4 (`../scratch/candidate-4.patch`; the fix since candidate 3: `../scratch/fix-3.patch`) plus your frozen v4 tests. There
is no further panel round: your delivery and the designer's read are the verification before the gate.

Designer rulings on the implementer's choices: C1 (an absolute argv[0] that resolves to the process's own executable may name it),
C2 (non-psutil test fakes fall back to argv[0]) and C5 (a reused session's other members make the scan uncertain) are accepted.

1. Scenario tests for Z1–Z6 and Z8 that the implementer's `test_s27_impl_r3fix.py` does not already cover (read it), in a new file
   `test_s27_fe_r3.py`: in particular Z6 (a real `BoxSampler` tick over a real process whose arguments carry a marker string → the
   marker appears nowhere in the tick), Z5 (a real process with a title-style argv[0] → recorded as its executable), Z2 (a leader
   pid present in the snapshot but not the recorded probe → nothing claimed, nothing killed), Z3 (freeze and harvest: null-record
   sidecar accepted only when the record is absent), Z1 (a primary typed fault survives a failing cleanup).
2. Run your whole set on candidate 4 and on the baseline copy; run `test_s27_impl_*` on candidate 4; report failures verbatim.
3. Review fix 3 against Z1–Z9 and spec v1.5; verdict: merge, fix then merge (list), or reject.

Write the report to `../scratch/testwriter-5-report.md` and end with it as your final message. The constraint block of delivery 1
still applies.
