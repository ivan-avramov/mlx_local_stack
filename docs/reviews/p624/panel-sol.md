P1 — `benchmark/bench/local_gate.py:350-360`; severity: major; evidence: confirmed (source trace).  
Problem: converting `want` and `skipped` to sets suppresses duplicate-count differences, although the request requires every non-exempt difference to fail exactly as before.  
Failure scenario: baseline contains `A` once and JUnit contains two skipped `A` testcases—or baseline contains `A` twice and JUnit skips it once. Previously `skipped != want` failed; the candidate sees no set difference and emits PASS.  
Proposed change: preserve multiplicity when comparing baseline and skipped lists. Exempt only a single, genuinely absent baseline entry proven passed; route every remaining count mismatch through the existing `skip list != baseline` failure. Add frozen tests for duplicate baseline and duplicate skipped entries.

P2 — `benchmark/bench/local_gate.py:113-118,351-360`; severity: major; evidence: confirmed (source trace).  
Problem: pass status is existential after IDs are collapsed into a set. If duplicate testcases share an ID, one clean testcase masks another carrying `<failure>` or `<error>`, defeating the explicit rc-0 protection.  
Failure scenario: baseline contains `A`; JUnit contains `<testcase ...A/>` and a second `<testcase ...A><failure/></testcase>`, with pytest rc 0. `A` enters `passed`, `missing == ["A"]`, and the receipt passes.  
Proposed change: aggregate outcomes by testcase ID and regard an ID as passed only when every occurrence is free of `skipped`, `failure`, and `error`. Add duplicate-ID pass+failure and pass+error tests; the frozen tests currently use distinct IDs only.
