Cold review — OPERATOR-AUTHORIZED EXTRA ROUND (round 4; C186's three rounds are used, the operator ordered this one round:
"did you run this by cursor? run one round if you havent"). After this round the operator decides. Prioritise what must be
settled before the Fable full GPU run. Fork `mlx-vlm`, branch `p369-mtp`, HEAD `0d06bb0c`.

Workspace: the `mlx-vlm` fork checkout at `24551869`; the branch commits are in this repository's object store — read any file
with `git show 0d06bb0c:<path>` (read-only; modify nothing). Production pinned at `4e6d0e03` (diff must stay empty — verify).

Four questions, in priority order:

Q1 — P398 judgement (the claim-integrity question). GPU smoke 3 (before the fix) reported ONE ON vs same-instance OFF1 row
mismatch out of 160 (evidence inline below). The lead judged it an INSTRUMENT ARTEFACT: the thinking budget (128 = 0.8 x
max_tokens 160) forces `\n</think>` at positions 129-130; forced tokens are emitted with no sampler call; ON's recorded row at
130 was a stale verifier row from the block whose emission the forcing cut (conditioned on a replaced draft), and "the last
record wins" kept it. Evidence for "artefact": ON emitted `</think>` with ZERO probability in its own recorded row; states +
probes equal at every commit; emitted tokens identical; C1 identical; after the fix 158 / 158 sampled rows bit-identical raw in
both Fable cells (smokes 4 and 6). Is that judgement sound, or can you construct a real MTP non-neutrality that would produce
exactly this signature and that the P398 fix now HIDES? Read `dev/p369_phase2/observe.py` (Recorder: `_cut_block`, the
`_mtp_acceptance_walk` / `_mtp_plain_emission` / `_mtp_pop_forced` / `ThinkingBudgetCriteria.__call__` wrappers),
`dev/p369_phase2/compare.py` (`forced_positions`, `compare_streams(exclude=)`), `dev/p369_phase2/worker.py` (`e1c_pair`) and
`mlx_vlm/speculative/mtp.py` (the inline round loop: forced branch, `_mtp_plain_emission`, `_mtp_pop_forced`).

Q2 — the narrowed claim. E1c's row claim now covers every SAMPLED emitted position; forced positions are covered by the
forced-pop proof (E6), full state hashes + probes at every commit, and E2 greedy token identity. Is that claim wording correct
and sufficient, or does excluding forced positions lose something that matters for "MTP-ON is neutral"?

Q3 — proposal (B), not yet built. Residual the lead found: if MTP forced at a different position than plain decoding would,
the OFF1 forced replay would not reproduce ON's tokens (plain's own criteria overrides) → C1 fails → pick ABORT — fail-closed,
but misattributed to the instrument instead of an MTP FAIL. Proposal: the OFF recorder also records plain decoding's forced
pops (position + token) the same way, and E1c requires ON's and OFF1's forced lists to be identical (mismatch = neutrality
FAIL, not ABORT). Is the residual real, is (B) correct and sufficient, and is there a simpler or stronger design?

Q4 — verify the round-3 fixes, diff `fa89d19b..0d06bb0c` (inline below): E6 (forced pops carry intended positions; emitted
ones exactly the row-less positions, token-equal; an unemitted one only exactly at len(tokens) under a length finish), E7
(cells invalid on every seed become verdicts from their attempts: C1 failure ABORT, neutrality failure FAIL, else INCOMPLETE),
E1 residual (cross-load container validated). RESOLVED / PARTIALLY / NOT, citing code; new defects.

Findings ids E8 onward, each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line, the problem, a concrete failure scenario, the
fix. Answer Q1-Q3 explicitly (AGREE / DISAGREE + reasoning). End with exactly one line: `VERDICT: CLEARED` or
`VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding and the Q1-Q3 answers in full, then the VERDICT line.
