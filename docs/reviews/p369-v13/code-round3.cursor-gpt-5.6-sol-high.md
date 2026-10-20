# P369 v13 build — code review round 3 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p369-v13` `d36d33c5..a2808acf`

I’ll review the committed objects, not the workspace, and independently check the two commits’ red/green intent, lifecycle behavior, telemetry ownership across verifier and drafter paths, and the unchanged-production claim. I’ll treat C194 as authoritative for N1.The unchanged-production claim is verified: `git diff --exit-code 64afc7dd a2808acf -- mlx_vlm ':!mlx_vlm/tests'` is empty. The material risk is now concentrated in whether the boot-time bind changes what the harness certifies, and whether routed-frame ownership is stable under the exact served call graph.Production diff is empty as required. Static red/green causality is valid; no false-failing correct served verifier path found.

| ID | Status | Reason |
|---|---|---|
| M1 | CLOSED | `Campaign.prepare()` passes byte-decoded registry content directly to the classifier; the mutation to `read_text()` fails the new test. |
| M2 | CLOSED | Script fallback works, and blocks plus expert IDs are strictly validated for prefix, type, uniqueness, and range. |
| M3 | CLOSED | Fresh drafters are bound before identity inspection; callable identity includes owner and function. P412’s JSON tuple/list mismatch is fixed. See R1 for a new lifecycle side effect. |
| M4 | CLOSED | No regression in the split-artifact execution coverage. |
| M5 | CLOSED | Only the outermost successful helper records attribution. The width-512 test demonstrably enters the fused affine branch and checks the exact counter. |
| M6 | CLOSED | No regression in invocation-frame enforcement. |
| M7 | CLOSED | Prompt-end snapshot, probe, neutrality, full/partial cuts, and total emitted-token accounting are covered. |
| M8 | CLOSED | No regression in served-shape and singleton-equivalence coverage. |
| M9 | CLOSED | No regression in corpus-content and source-pick binding. |
| M10 | CLOSED | No regression in finite, non-negative timing validation. |
| N1 | CLOSED | C194 permits explicit `--wall-limit-s`; it is finite/positive, while the default remains unbounded. |
| N2 | CLOSED | Sabotage unwinds before telemetry restoration, preventing stale global wrappers. |
| N3 | CLOSED | The original cross-layer verifier-bank swap is now rejected by owner/module matching. Correct `_switch_glu` argument indexing does not false-fail. See R2 for an uncovered drafter path. |
| N4 | CLOSED | Both served fixtures reject dense eligible modules and require affine int4/g64 with bf16 scales and biases. |

R1 — HIGH — `dev/p369_phase2/worker.py:268-274`  
Problem: startup validation permanently calls `drafter.bind(model)` on the live served object. This changes its initial state and can mask a broken request-time `reset()` that omits binding.

Failure scenario: production serving from a fresh drafter would fail or remain unbound, but the harness’s boot-time bind supplies valid embedding/head references before the request, allowing the smoke to pass.

Fix: temporarily bind and restore all binding fields in `finally`, then inspect the live identity after the first real request-time reset without rebinding. Add a test proving startup validation leaves a fresh drafter unbound.

R2 — HIGH — `dev/p369_phase2/telemetry.py:293-334,710-720,744-778`  
Problem: ownership is enforced only for verify-scope frames. `draft_verdict()` reduces drafter bank calls to projection suffixes and ignores the recorded owner/module mismatch. Fused helpers also synthesize names as `owner.projection` instead of resolving each actual child module.

Failure scenario: a drafter gate bank references another layer’s or the target’s compatible bank. All expected draft parts and selected experts are recorded, so Ornith’s draft inventory passes despite executing foreign weights.

Fix: resolve projected helper banks through their actual module identities, enforce owner/module equality for draft frames, and add a drafter-bank swap negative covering direct and fused paths.

VERDICT: NOT CLEARED R1 R2

---

**Lead disposition (after the last round, for the operator):** R1 and R2 fixed test-first without a fourth round — `5f15d641` red, `3ae8770e` green (see `docs/open-questions.md` C196 request).
