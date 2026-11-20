# Test-writer brief, delivery 4 — S27 bundle, fix round 2 (same session)

Your v3 set was frozen at 2026-11-20T16:58:08Z. Round 2 of the change review adopted Y1–Y6 (`../scratch/change-ledger-r2.md`); a
fresh implementer fixed them (`../scratch/implementer-fix2-report.md`, with a Clarification section). Your copy now holds
candidate 3 (`../scratch/candidate-3.patch`; the fix since candidate 2: `../scratch/fix-2.patch`) plus your frozen v3 tests.

1. One v3 test conflicts with adopted Y3 and is amended by you:
   `test_s27_fe_r1.py::test_x10_a_session_member_started_after_the_probe_is_ours_and_is_killed` spawns a live session LEADER
   whose start is not the recorded probe start and expects it killed — Y3 rules that is a reused session (no session claim,
   recorded). Re-stage it to what X10(b) means: a NON-leader member inside the probe's own session (the probe = the recorded
   leader, or the leader already exited), started after the probe's recorded start → ours, killed, verified; keep a separate test
   that the reused-leader case is not claimed and is recorded (`session_reused`) and nothing is killed.
2. Add scenario tests for Y1–Y6 not already covered by the implementer's `test_s27_impl_r2fix.py` (read it): in particular Y3 (a
   reused session never kills), Y4 (freeze AND harvest refuse a sidecar that does not bind slot / attempt / row / record, accept
   the bound ones), Y1 (an absent / malformed sample never enters the anchored case).
3. Run your whole set on candidate 3 and on the baseline copy; run `test_s27_impl_*` on candidate 3. Report failures verbatim.
4. Review fix 2 against Y1–Y6 and the specification; verdict: merge, fix then merge (list), or reject.

Write the report to `../scratch/testwriter-4-report.md` and end with it as your final message. The constraint block of delivery 1
still applies.
