Cold PLAN review — ROUND 3 OF 3 (the LAST round: open findings after it go to the operator as a table). Plan v3 of the P415
R7 qualification tool (inline below, `docs/specs/p415-r7-qualification.md`, STACK repo). Your round 2 (inline below) closed Q5
Q6 Q8 and left Q1 Q2 Q3 Q4 Q7 open + new Q9; v3 §2.2 applies all six, with ONE bounded exception argued there
(`cache_session_shrink` is attested but not behaviourally exercised: it acts only after a request retires and its session
idles, so it cannot move the measured single-request peaks). Code to check against: fork `p369-v13` `3ae8770e` in `../mlx-vlm`
(`git show 3ae8770e:<path>`, read-only) and the stack's mlx-serve argv builder (`src/mlx-serve/src/mlx_serve/process_manager.py`
`_build_command`, inline below).

First, per Q1–Q9: CLOSED or OPEN (with why) — judge the Q2 exception on its argument. Then new findings Q10 onward, each:
severity, plan section, problem, failure scenario, fix — only what would let the run pass for the wrong reason, fail open, or
be unbuildable. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids>`. OUTPUT RULE: your FINAL message must
contain EVERY finding in full, then the VERDICT line.
