Cold CODE review — ROUND 3 OF 3, THE LAST (C186: any finding still open after this round goes to the operator as a table;
prioritise what must be fixed before the full GPU run) — C185 (P369 phase-2 E2, same-instance design) plus the GPU-smoke-driven
harness fixes (fork `mlx-vlm`, branch `p369-mtp`).

Workspace: the `mlx-vlm` fork checkout at the base `24551869`; the branch commits are in this repository's object store — read
any file with `git show <HEAD>:<path>` (read-only; modify nothing). Production pinned at `4e6d0e03` (diff must stay empty —
verify). Round 2 reviewed `f4c841be..a44a8070`; this round's diff is `a44a8070..<HEAD>` (inline below; red tests first).
SCOPE: the round-2 fixes and every smoke-driven fix below; the rest of the harness is closed (operator, C186) — cite it only
where these changes interact. If this round's head is CLEARED it becomes the `--reviewed-head` of the full run.

Changes (all test-first):
- C185 round 2: E5 — E2 output identity = token ids AND finish reason (C1-E2, ON vs OFF1, cross-load report); E1 residual —
  every malformed E2 container raises `MalformedEvidence`.
- Smoke 1: request bodies carry the worker's `--model` (`routed()`), as mlx-serve's router rewrites `body["model"] = hf_path`.
- Smoke 2: the dry-run prompt measurement raises a plain `Exception` (a `BaseException` unwound through the app's `http`
  middleware as a `BaseExceptionGroup` and stopped the TestClient portal); ids recorded on the side; refuses when tokenization
  never ran, when the request returned 200, or when two tokenizations disagree.
- Smoke 3 / P398: the ON recorder cuts each verifier block's rows at its emission decision (`_mtp_acceptance_walk` base +
  `_mtp_plain_emission` n_emit) and records forced pops (`_mtp_pop_forced`); `forced_positions` proves the row-less ON
  positions are exactly the forced emissions; they are excluded from the ON/OFF1 row comparison and the smoke positives (plan
  v9 §2.2). Live: Fable T = 1,024 / 65,536 compared 158 rows bit-identical, forced [129, 130] excluded.
- Smoke 4 / P399: an E1c attempt retried for validity (no straddle / too short) still counts — its C1 failure ABORTs and its
  neutrality failure FAILs the pick.
Context (not in scope, for your judgement of the harness): smoke 4 found a PRODUCTION defect — on the uniform pick's TurboQuant
4-bit KV a width-2 MTP verify block is not exact (reproduced on the tiny fixture; widths 3 / 4 and the default KV are exact);
it goes to the operator separately. Is anything in the harness changes above masking or misattributing such a defect?

Review adversarially: (1) for each round-2 finding (E1, E5): RESOLVED / PARTIALLY RESOLVED / NOT RESOLVED, citing code; (2) NEW
defects in the smoke fixes (the recorder cut and forced-position proof: can it drop a SAMPLED row, mis-pair a block, or hide a
real difference? the routed model; the dry run; P399's attempt accounting); (3) anything that could let a run PASS without the
claim, or report a harness failure as an MTP finding.

Findings ids E6 onward (re-cite older ids when not resolved), each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line, the
problem, a concrete failure scenario, the fix. End with exactly one line: `VERDICT: CLEARED` or
`VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
