# C77 — Proposed M43 quality diagnostic

Status2026-09-14: **REFRESHED PROPOSAL, NOT ARMED**. C84 certified the later integrated-runtime/cache-repair transition, not the original pre-merge upgrade. C88 shipped-config vision is complete; C89 shipped-config depth qualification is also complete. Phase2 is closed at its approved measured scope. This historical diagnostic remains deferred and is not a Phase 2 closure blocker. No external judge calls.

## Question and scope

Determine whether the integrated source's observed numerical differences affect sampled task outcomes, convergence, prose bodies or output cost. Preserve deployed weights, predictor, sampling, template inputs, context cap and full-cap allocation. Compare fresh original versus integrated runtime bundles (source plus MLX/Metal); historical rows supply selection and planning evidence only.

Models: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` and `Qwen3.8-27B-mlx-uniform-4bit`. Each receives five tasks on Math500, HumanEvalPlus, MBPPPlus and the existing prose corpus: **40 pairs /80 requests**, one explicit seeded draw per item/runtime. Both runtimes use MTP ON. Freeze TQ4 for BOTH models in BOTH source states, preserving the original C77 cache treatment. The first model now ships native16; this TQ4 control is deliberately historical and must not be called current-default certification. C88 tests current native16 versus TQ4 on the final runtime separately. Do not add candidates, change predictor state or change either ladder.

Frozen outcome-independent selection: [selection artifact](c77-proposed-selection.json), SHA-256 `5edcaf060e504c4eca1617a68a106a14e3f467d9510df75372dc25c64d7b94a6`. First-pick coding reuses the prior M36 random pilot; remaining axes sample sorted unique M40 IDs with `Random(4313)`. Preserve explicit sample-zero seeds. Verify corpus and request-builder hashes before launching. Historical rows omit prompt text; current corpus hashes do not prove historical prompt equality. The new causal comparison requires identical serialized prompts within each fresh pair.

## Runtime and supervision

- Original source: MLX-VLM `420c01e1`, MLX-Serve `0ccc684`, original MLX/Metal0.32.0 serving dependencies. Integrated source: final `522671c4` / `b632280`, MLX/Metal0.32.2 with the other preserved serving pins. Use the original frozen lock/environment and verify all installed versions before generation; no silently reconstructed dependency bundle. The declared treatment is the complete source/runtime upgrade, not an isolated kernel. Record full installed versions and actual executing source hashes.
- One resident model. Separate immutable tags and output directories; explicit overlay in every driver; APC absent, retained sessions 2, cap/preallocation 262144, prefill step 512. Preserve both models' deployed temperature and all other sampling defaults. Disable idle cache shrinking in both TQ4 control overlays (historical policy); full active allocation remains unchanged. Require zero cached prompt tokens on independent tasks and fresh matched state setup. Preserve current production YAML throughout.
- Derived per-request timeout, no retries. Daemon assessment every five minutes, known-positive selftest and runner-exit record. Abort on transport/provenance failure; never grade it as an incorrect answer. Do not replace a selected difficult item or lower its thinking budget.
- Generate at most the frozen 80 requests. The original frozen-task historical means imply **65.15 minutes of generation**, excluding loading, mechanical grading and supervision. This is a lower bound. Prior math maxima approach 8.2 and 13.4 minutes per item, and an earlier pilot underpredicted a full arm by 3.4×. Reserve several hours of box availability; re-estimate after each completed five-item block. No automatic expansion.

## Assessment and decision

Use canonical math and execution grading for code. Record per-item correctness, strict resolved-budget success, convergence/failure kind, complete output hashes, tokens, latency and predictor counters. Compare prose bodies and lengths mechanically; do not substitute a text hash or length measure for a quality judge.

The ordinary cross-model `compare.py` deliberately refuses changed serving hashes. Preserve that guard and all truthful manifests. Any dedicated diagnostic analysis must declare runtime as the treatment, enforce equality of other output-determining fields and exact item/seed pairing, and remain separate from cross-model ranking. Do not falsify provenance or strip refusal fields to obtain a comparison.

Five pairs per axis do not establish ±5pp equivalence. Report concrete discordant items and uncertainty, distinguish trace-only changes from final-answer failures, and recommend either a scoped expansion or a qualified historical-upgrade quality conclusion using all available evidence. New failed cases require diagnosis before expansion. Larger quality studies, depth/vision recertification and external judging require a new scoped proposal; this diagnostic does not authorize them.

The original selection/count was independently reviewed. The refreshed final-source and cache scope requires a new cold protocol/instrument review before launch. Preserve the selection artifact unchanged; its status is a frozen historical selection record, not a second queue.
