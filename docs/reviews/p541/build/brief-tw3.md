Delivery 3 (same session): a cold review of the implementation found gaps in the tests and in the code; the designer amended the spec to v1.3 (`docs/specs/p541-push-levels.md`, section "v1.3" at the end — read it). The implementation (`benchmark/bench/local_gate.py`) now exists in this copy; do not edit it. Add or amend tests in `test_p541_push_level.py` (tag post-review r1):
1. a sole path ` docs/x.py` (leading space) is code → a push without a receipt refuses; ` benchmark/results/x.py` on the stack is not data; a first path with a trailing space or a newline inside the name is read exactly;
2. a non-evidence branch pushed at a commit that exists only on `<remote>/evidence` is classified by its paths (code → refuses without a receipt), never `none-new`;
3. `push_level` on the stack's `refs/heads/evidence` for a commit sharing history with `<remote>/main` returns the v1.3 problem (not `data-only`), and for an orphan returns `data-only`;
4. `digest_for` raising → the v1.3 problem, and another ref in the same push still gets its line;
5. a ref with a scan problem (PII) prints no `level:` line;
6. receipt files named for the right sha and digest but holding a wrong `policy_digest`, a wrong `sha`, or `verdict: FAIL` inside each refuse;
7. fork tags: the refusal and the level line name the tagged commit's sha8 exactly (compute it in the test).
Run the file and the existing gate tests; report the verbatim summary lines and which new tests fail against the current code and why (expected: items 1–5; items 6–7 may already pass). Test file only; no commit; no push.
