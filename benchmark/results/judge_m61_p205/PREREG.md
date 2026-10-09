# P205 — blind pairwise quality panel over the P198 A/B (pre-registered 2026-10-09, before any verdict)

Question: do plain-v2 (arm A, more tokens) outputs beat brevity-prompt (arm B) outputs on quality beyond the tests?
Pairs: 20 = 2 models × 2 sessions × 5 items; both sides pass the tests (re-verified on rebuilt files; stubs fail).
Slots: per model, A/B slot swapped on exactly half the pairs (seeded 205); both presentation orders per judge.
Judges: claude-opus-5-5 subagent (blind-judge), claude-sonnet-5-5 subagent (blind-judge), codex gpt-6-astra medium.
Tasks: PRIMARY code (final solution only); SECONDARY final message to the user (each side's message + its own code as context; judge the message only).
Per (pair, judge): the two orders' choices agree, else tie. Panel verdict: majority of 3, else tie.
Measure: share preferring arm A = (A wins + 0.5 ties)/n over pairs; 95 % two-stage cluster bootstrap (items, then pairs within item), 20000 draws, seed 205. Per-model shares descriptive only.
Reading (code): lower bound > 0.5 → extra tokens buy quality (keep v2, no brevity file); CI includes 0.5 → no detectable difference (brevity free; P204 option a); upper bound < 0.5 → brevity better.
MDE ≈ ±25 pp at n=20. Reliability diagnostics (reported, not gating — no code anchors exist): per-judge order-flip rate, pairwise judge agreement. Unparseable verdict → re-issue once, then counts as disagreement (tie).
