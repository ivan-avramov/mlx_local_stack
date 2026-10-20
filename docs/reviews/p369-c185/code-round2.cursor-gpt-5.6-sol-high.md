# P369 phase-2 C185 (same-instance E2) — Cursor gpt-5.6-sol-high CODE review round 2 of 3 (fork `p369-mtp` `f4c841be..a44a8070`, 2026-10-19)

Prompt: `code-round2.prompt-head.md` + the round-1 output + `git diff f4c841be..a44a8070`; `--mode ask`, stream-json — the `result` text verbatim:

I’ll re-evaluate E1–E4 against the committed `a44a8070` tree, then trace every E2 verdict input and failure path for false PASS or misclassification. I’ll keep production isolation and C185 interactions as explicit gates.Production isolation is clean. The four original fixes are materially present, but one decisive comparison still omits part of the typed evidence: ON and OFF can have identical token IDs with different finish reasons and currently PASS. I’m checking whether any cleanup or malformed-shape paths create additional false verdicts versus only explicit harness errors.P1 — Production isolation: RESOLVED  
`git diff --exit-code 4e6d0e03 a44a8070 -- mlx_vlm ':(exclude)mlx_vlm/tests'` is empty.

P2 / E1 — PARTIALLY RESOLVED — LOW — `dev/p369_phase2/orchestrate.py:504-521`  
Problem: The required fields are now exactly typed for all four turns, preventing the original false PASS. However, malformed containers do not consistently raise `MalformedEvidence`: a truthy non-dict `telemetry` raises `AttributeError`, while missing/empty `turns` can raise `KeyError`/`IndexError` at line 545.  
Scenario: ON contains `telemetry=["bad"]`; line 518 calls `.get()` on the list. The campaign correctly becomes `HARNESS_ERROR`, not an MTP finding, but violates the promised malformed-evidence contract.  
Fix: Validate entry, `turns`, `final`, and `telemetry` container shapes before indexing or calling `.get()`, routing all malformed shapes through `bad()`/`MalformedEvidence`.

P3 / E2 — RESOLVED  
`dev/p369_phase2/orchestrate.py:563-569` requires every trajectory digest to be lowercase 64-hex before equality. Invalid or missing digests produce an INCOMPLETE problem. Tests cover invalid and absent digests at `mlx_vlm/tests/test_p369_phase2_orchestrate.py:1751-1762`.

P4 / E3 — RESOLVED  
`instance_identity` retains strong references and `same_instance` rereads live state at `dev/p369_phase2/worker.py:838-846`. E2 checks after each replay at lines 881-884. P397 also replaces the vacuous E1c check at lines 1041 and 1081.

P5 / E4 — RESOLVED  
The coordinator is isolated at `dev/p369_phase2/worker.py:849-889`; `run_job` delegates at lines 1137-1149. Tests at `mlx_vlm/tests/test_p369_phase2_worker.py:621-703` cover ordering, detachment, releases, distinct chat IDs, restoration, policy replacement, and speculative replay rejection.

P6 / E5 — BLOCKER — `dev/p369_phase2/orchestrate.py:552-557`  
Problem: E2’s decisive ON/OFF identity compares only `token_ids`; it ignores the typed `finish_reason`. The descriptive cross-load comparison has the same omission. This contradicts “ON equals OFF1” and can produce PASS without generation-outcome identity.  
Scenario: ON and both OFF runs emit `[1, 2]`; ON finishes with `"length"` while OFF1/OFF2 finish with `"stop"`. C1 is true, engagement and digests pass, `identity[n]` is true, and E2 returns PASS.  
Fix: Define output identity as equality of both `token_ids` and `finish_reason`, and use it for C1, ON-vs-OFF1, and cross-load reporting. Add a regression test where only ON’s finish reason differs and require FAIL.

No worker/coordinator failure path reviewed here is converted into an MTP finding: uncaught worker failures become `HARNESS_ERROR` through `dev/p369_phase2/orchestrate.py:2106-2108`.

VERDICT: NOT CLEARED E5