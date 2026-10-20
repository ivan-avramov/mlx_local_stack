# P369 phase-2 C185 + smoke fixes — Cursor gpt-5.6-sol-high CODE review round 3 of 3 (fork `p369-mtp` `a44a8070..fa89d19b`, 2026-10-19)

Prompt: `code-round3.prompt-head.md` + the round-2 output + plan v9 §2.2 + `git diff a44a8070..fa89d19b`; `--mode ask`, stream-json — the `result` text verbatim:

Production isolation is verified: `4e6d0e03..fa89d19b` is empty under `mlx_vlm` excluding tests. I’m now reducing the review to two risk surfaces: whether inferred forced positions can falsely excuse a sampled position, and whether retry accounting preserves verdict precedence without converting invalid evidence into a production finding.Production isolation is clean: `git diff --exit-code 4e6d0e03 fa89d19b -- mlx_vlm ':(exclude)mlx_vlm/tests'` returned empty.

Round-2 findings

E1 — PARTIALLY RESOLVED — LOW — `dev/p369_phase2/orchestrate.py:579-581`  
Problem: The reported round-2 cases are fixed, but not every malformed E2 container becomes `MalformedEvidence`. `cross` itself is never type-checked before membership and indexing.  
Scenario: With `pair={"a": ...}` and malformed `cross="a"`, `n in cross` succeeds, then `cross[n]` raises `TypeError`. The outcome is still `HARNESS_ERROR`, but violates the promised evidence contract.  
Fix: Validate `cross` as a non-empty dict before iteration and route malformed top-level containers through `bad()`.

E5 — RESOLVED — `dev/p369_phase2/orchestrate.py:568-592`  
`outcome()` now includes both token IDs and finish reason for C1-E2, ON/OFF1 identity, and cross-load reporting. The regression test covers both decisive and descriptive comparisons.

New findings

E6 — HIGH — `dev/p369_phase2/compare.py:86-102`  
Problem: `forced_positions()` permits one unmatched forced pop at any length finish, without proving that it occurred beyond the emitted output. This weakens the “exactly the forced emissions are row-less” proof.  
Scenario: Suppose `[newline, close]` are both emitted, with `close` at the final length-budget position, but a stale verifier row incorrectly remains at `close`. Only `newline` is missing, so `extra == 1` and `finish_reason == "length"` pass by misclassifying the emitted `close` as the allowed unemitted pop. If the stale row matches OFF, the run can PASS without the row-less claim; if it differs, the harness reports a false MTP difference.  
Fix: Record each forced pop with its intended emission position. Require every position below `len(tokens)` to be row-less and token-equal; permit only a forced position exactly at `len(tokens)` as unemitted.

E7 — HIGH — `dev/p369_phase2/orchestrate.py:1871-1875`  
Problem: P399 accounting is bypassed when every seed is invalid. The unconditional `RuntimeError` occurs before `pick_outcome()` can apply rejected-attempt C1/neutrality precedence.  
Scenario: All five T65536 attempts are too short or do not straddle, but one exposes the TurboQuant width-2 difference with `neutral=False` and stable C1. Instead of E1c `FAIL`, the campaign records `HARNESS_ERROR`, masking the production finding. A rejected C1 failure is similarly lost instead of producing `ABORT`.  
Fix: Reduce all recorded attempts before the all-invalid exit: any C1 failure → `ABORT`; otherwise any neutrality failure → `FAIL`; otherwise all-invalid evidence → `INCOMPLETE`.

No additional defect found in routed-model handling or the dry-run change. `run_job()` binds the model from the worker argv, and both request paths apply it; `prompt_ids()` fails closed on absent tokenization, success status, and divergent repeated tokenization. The block cut itself follows the current singleton walk/emission sequence correctly; E6 is the remaining forced-position proof gap.

VERDICT: NOT CLEARED E6 E7
---

Lead (2026-10-19): E6, E7 and the E1 residual fixed test-first after this round (fork red `7f227d70`, fix `0d06bb0c`); no fourth round without the operator (C186) — escalated.
