Cold PLAN review — ROUND 3 OF 3 (the LAST round) (at most 3 rounds, then the operator decides open findings; prioritise what must change
before the harness is built). P369 phase-2 run plan v12 (inline: the v12 diff, then the full plan, then your rounds 1–2). First verify each
round-2 finding V8–V13 (and the round-1 V5 / V6 / V1 residuals) is resolved by v12 (say so per id). V9 is partly contested:
Fable gets a regression smoke on `7207179b` under the operator-approved C188 carry-over rule, not a full run — judge that
argument on its merits. Then review v12 afresh; only BLOCKER / HIGH findings that must change the plan before the harness
build should block. Context: the operator
(C191) widened MTP qualification to every MTP-certified registry entry — `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (qwen3_5
dense hybrid, TurboQuant 4-bit KV once P405 lands, per-query verification) and `Ornith-1.0-35B-mlx-uniform-4bit`
(qwen3_5_moe, native KV, transplanted MTP head) — so all ship MTP-ON only after passing this phase on the P400 + P401 + P405
fork. Code: fork branch `p405-kv-scheme` HEAD `6911b17f` (read with `git show 6911b17f:<path>`, read-only; harness in
`dev/p369_phase2/`, model code `mlx_vlm/models/qwen3_5*/`, drafters `mlx_vlm/speculative/drafters/`). Stack registry
(`main_models.yaml`) is not in this workspace; the relevant facts are in the plan text.

Review adversarially: (1) is the borrowed-item design (no C84 bundles for either entry) sound for E2 / E7 — what does it
lose, can a reconstruction silently differ, is the replacement check (templated-prompt sha256 + count) enough; (2) does the
plan prove the harness actually observes the MoE model (Ornith): verifier / recorder hooks, emission cut, probe, kernel
inventory, the drafter split via `qwen3_next`, the MoE batched-vs-singleton expert dispatch (a P400 analogue) — what must
be tested on a tiny `qwen3_5_moe` fixture first; (3) is the overlay / registry-state handling (P406 marked lines, the §5
third accepted state) exact and fail-closed; (4) is the restore rule right and is anything missing for "qualify and enable
MTP across the picks" (e.g. Ornith's or Qwen3.6's predictor parameters, verify policies, the router re-certification after
this worker-level phase); (5) estimate realism.

Findings ids V14 onward, each: severity (BLOCKER / HIGH / MEDIUM / LOW), the problem, a concrete failure scenario, the change to
the plan. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
