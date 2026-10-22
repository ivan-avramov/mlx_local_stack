Cold PLAN review — ROUND 2 OF 3 (at most 3 rounds, then the operator decides open findings). The plan is
`docs/specs/p434-local-gate.md` (v2) in this STACK repo at the commit named in the instruction line; round 1's findings and
verdict are in `docs/reviews/p434/plan-round1.cursor-gpt-5.6-sol-high.md` (G1–G11). Same read-only context as round 1
(`docs/reviews/p434/plan-round1.prompt-head.md`). For EACH of G1–G11 state CLOSED or OPEN with one line of reason against v2;
then review v2 adversarially for NEW problems (ids H1 onward) introduced by the v2 changes, each: severity, plan section,
problem, failure scenario, fix. Prefer the simplest fix that closes the hole; flag over-building. End with exactly one line:
`VERDICT: AGREE` or `VERDICT: DISAGREE <ids>`. OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the
VERDICT line.
