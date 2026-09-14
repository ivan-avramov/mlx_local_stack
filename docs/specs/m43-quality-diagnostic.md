# C77 — Proposed M43 quality diagnostic

Status: **PROPOSED, NOT ARMED**. This is outside C75's bounded compatibility/capacity authorization. No external judge calls are proposed.

## Question and scope

Determine whether the integrated source's observed numerical differences affect sampled task outcomes, convergence, prose bodies or output cost. Preserve deployed weights, predictor, sampling, template inputs, context cap and full-cap allocation. Compare fresh original versus integrated runtime bundles (source plus MLX/Metal); historical rows supply selection and planning evidence only.

Models: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` and `Qwen3.8-27B-mlx-uniform-4bit`. Each receives five tasks on Math500, HumanEvalPlus, MBPPPlus and the existing prose corpus: **40 pairs /80 requests**, one explicit seeded draw per item/runtime. Both runtimes use the shipped MTP-ON state. Do not add candidates, change predictor state or change either ladder.

Frozen outcome-independent selection: [selection artifact](c77-proposed-selection.json), SHA-256 `5edcaf060e504c4eca1617a68a106a14e3f467d9510df75372dc25c64d7b94a6`. First-pick coding reuses the prior M36 random pilot; remaining axes sample sorted unique M40 IDs with `Random(4313)`. Preserve explicit sample-zero seeds. Verify corpus and request-builder hashes before launching. Historical rows omit prompt text; current corpus hashes do not prove historical prompt equality. The new causal comparison requires identical serialized prompts within each fresh pair.

## Runtime and supervision

- Original source: MLX-VLM `420c01e1`, MLX-Serve `0ccc684`, original serving dependencies. Integrated source: `c5a6f97b` / `f8f1df4`, MLX/Metal 0.32.2 with the preserved serving pins. Record full installed versions and actual executing source hashes.
- One resident model. Separate immutable tags and output directories; explicit overlay in every driver; APC absent, retained sessions 2, cap/preallocation 262144, prefill step 512. Preserve both models' deployed temperature and all other defaults.
- Derived per-request timeout, no retries. Daemon assessment every five minutes, known-positive selftest and runner-exit record. Abort on transport/provenance failure; never grade it as an incorrect answer. Do not replace a selected difficult item or lower its thinking budget.
- Generate at most the frozen 80 requests. Historical full-source means imply **65.15 minutes of generation**, excluding loading, mechanical grading and supervision. This is a lower bound. Prior math maxima approach 8.2 and 13.4 minutes per item, and an earlier pilot underpredicted a full arm by 3.4×. Reserve several hours of box availability; re-estimate after each completed five-item block. No automatic expansion.

## Assessment and decision

Use canonical math and execution grading for code. Record per-item correctness, strict resolved-budget success, convergence/failure kind, complete output hashes, tokens, latency and predictor counters. Compare prose bodies and lengths mechanically; do not substitute a text hash or length measure for a quality judge.

The ordinary cross-model `compare.py` deliberately refuses changed serving hashes. Preserve that guard and all truthful manifests. Any dedicated diagnostic analysis must declare runtime as the treatment, enforce equality of other output-determining fields and exact item/seed pairing, and remain separate from cross-model ranking. Do not falsify provenance or strip refusal fields to obtain a comparison.

Five pairs per axis do not establish ±5pp equivalence. Report concrete discordant items and uncertainty, distinguish trace-only changes from final-answer failures, and recommend either a scoped expansion or an explicitly qualified activation decision using all available evidence. New failed cases require diagnosis before expansion. Larger quality studies, depth/vision recertification and external judging require a new scoped proposal; this diagnostic does not authorize them.

Independent cold review verified the selection, source hashes, count and timing arithmetic, provenance separation and scope limits before any diagnostic launch.
