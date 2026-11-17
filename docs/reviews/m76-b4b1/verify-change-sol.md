P1 — Location: `benchmark/bench/corpus_tg2.py:239-246,273-278`  
Severity: minor  
Evidence: confirmed (source trace)  
Status: L2 not fully resolved.  
Problem: `prepare()` verifies both checkout SHA and item inputs, but the prompt path re-verifies only item inputs.  
Failure scenario: After preparation, the checkout moves to another commit while the selected exercise remains byte-identical; `prompt()` accepts it despite the required `source_sha() == polyglot_sha` check. Existing tests combine wrong SHA with modified instructions, so the input check masks this gap.  
Proposed change: Have `spec_text()` call `verify_source()` and add a wrong-SHA/unchanged-item prompt test.

P2 — Location: `benchmark/bench/p426_wave2.py:1087-1099,1129-1158`  
Severity: major  
Evidence: confirmed (source trace)  
Status: L3’s missing-counterpart disposition is resolved, but normal resume remains incorrectly bound.  
Problem: Attempt/selection fields are checked only when recovering a sealed file lacking a sequence record. When both record and file exist, resume checks only their SHA and accepts a re-check for obsolete selected attempts.  
Failure scenario: Re-check 1 passes for s1 attempt 1; the operator reruns one s1 leg, selecting attempt 2 whose rows would be outside the grid. Resume accepts the attempt-1 re-check, so no rc 5 or acknowledgement occurs.  
Proposed change: Validate the sealed document’s gate, axis, sessions, arms, and attempts against current selections whenever it exists; stop with rc 1 on mismatch, never recompute. Add a rerun/resume regression test.
