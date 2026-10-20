# P369 phase-2 C185 (same-instance E2) — Cursor gpt-5.6-sol-high CODE + PLAN review round 1 of 3 (fork `p369-mtp` `508bab78..f4c841be`, 2026-10-19)

Prompt: `code-round1.prompt-head.md` + plan v8 §3 E2 + `git diff 508bab78..f4c841be`; workspace `../mlx-vlm` at `24551869`; `--mode ask`, stream-json — the `result` text verbatim:

I’ll verify the committed tree at `f4c841be`, the production-pinned diff, and the reused E1c detachment/session machinery. I’ll treat malformed/missing evidence separately from genuine MTP divergence and focus only on C185.The production isolation check is clean: `git diff 4e6d0e03 f4c841be -- mlx_vlm ':!mlx_vlm/tests'` is empty. The core ordering and failure classification also match C185 so far; I’m now stress-testing coverage completeness, artifact joining, and the timeout/session edge paths where a false PASS could hide.Production isolation is verified: the requested diff is empty.

E1 — HIGH — `dev/p369_phase2/orchestrate.py:504-525`  
Problem: E2 compares evidence without validating token, finish-reason, or engagement-count types. Malformed evidence can PASS or become an MTP FAIL/ABORT instead of a harness error.  
Scenario: all trajectories contain `token_ids=None`, while argmax and round counts are `True`; equality and `> 0` all succeed, allowing PASS.  
Fix: validate turn structure, `list[int]` token IDs, finish reasons, and exact integer counts before verdict computation; raise `MalformedEvidence`. Add malformed-field tests.

E2 — HIGH — `dev/p369_phase2/orchestrate.py:527-531`  
Problem: four missing straddle digests become `[None, None, None, None]` and are considered equal. Straddles are absent from reconstruction digests, so nothing else catches this.  
Scenario: every trajectory for `T1024` lacks `prompt.sha256`; E2 can PASS with unbound prompt evidence.  
Fix: require every trajectory digest to be a valid SHA-256 string. Missing or malformed digests must produce an INCOMPLETE digest problem. Add an all-four-missing test.

E3 — MEDIUM — `dev/p369_phase2/worker.py:1087,1112`  
Problem: the verify-policy identity assertion is vacuous: both snapshots use `id(policy)` on the same local variable rather than rereading `rg.mtp_verify_policy`.  
Scenario: the response generator’s policy is replaced during the triple, but the assertion still passes.  
Fix: snapshot and later reread `getattr(rg, "mtp_verify_policy", None)`; test a policy replacement.

E4 — MEDIUM — `dev/p369_phase2/worker.py:1083-1119`  
Problem: no test executes the new `e2_pair` coordination branch. Existing tests cover helpers and mocked job layout only.  
Scenario: release ordering, detachment scope, fresh chat IDs, restoration, or artifact assembly regresses while all current tests remain green.  
Fix: add a mocked branch-level test, or extract the triple coordinator and test ordering, restoration, releases, unique IDs, evidence shape, and exception paths.

VERDICT: NOT CLEARED E1 E2 E3