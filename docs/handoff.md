# Handoff — 2026-10-04 (23:00 UTC): M57 approved (C111); evidence steps 1–2 COMPLETE; build NOT started — operator confirmation owed

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/proposal-flash-attention.md` (the whole M57
record: proposal → reviews → design P25–P44 → reviews 2/3 → reconciliation → evidence E1–E15 with P65–P75), `docs/PLAN.md` (M57 row),
`docs/specs/m57-attention-policy.md` (build spec, AC1–AC12) and `docs/specs/m57-prefill-profiler.md`.

## State of the world

- **Git (stack):** pushed through `bd2823d`; everything after is LOCAL ONLY (handoff, M57 docs, specs, probe rows, AGENTS.md rule).
  Push needs the operator's word.
- **Fork `../mlx-vlm`:** branch `m57-prefill-profile` @ `21d62fe6` (4 commits on `main` `1bd249d3`; env-gated prefill component
  profiler; 71 CPU tests; three cold-review rounds by a Claude reviewer and Codex `gpt-6-astra`; live gate passed). NOT pushed, NOT
  merged, submodule NOT bumped. The fork's working tree is left on that branch. `../mlx-serve` untouched.
- **Stack is DOWN by operator instruction: do NOT auto-start `runserver.sh`.** :8000 free, no router/worker. 140 W, battery 100 %.
- **Picks unchanged.** `main_models.yaml` untouched.
- Workdir `$STACK_WORKDIR/m57/`: microbench scripts + JSON, `probe/` (128K overlay probe, MTP round profile), `profile/` (component
  profiles, three runs), `overlays/step{512,1024}.yaml`, Codex prompts/reviews 1–4, `transcript_accounting.{py,json}`.
- `ts.md` at the repo root is the operator's untracked video transcript — not committed.

## What the evidence says (first pick `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, native16, MTP ON; all PROBES, one session per arm)

- Fused attention is NOT a 2× lever. At 128K, fused chunks give −16 % (warm vs warm) to −22 % (cool vs cool) TTFT. A 128K prefill is
  44 % attention, 34 % MLP, 17 % GatedDeltaNet; below 32K the weight projections (quantized matmuls) are nearly everything.
- Memory is the stronger benefit: the served peak tracks ≈ 1.23 score tensors of the LARGEST UNFUSED chunk (confirmed by a 1.71 GB
  rise when the tail grew from 512 to 734 queries). Predicted with a tail-fusing policy: −3.9 GB at 128K, −7.9 GB at 256K.
- Fused is 2.6–14× closer to an fp32 reference than the unfused bf16 path served today.
- `force_fused` raises at query lengths 6–8 and is slower below ≈ 128 queries → policy `fused_v1` in the build spec.
- Chunk size 1024 does not speed up MLP / GatedDeltaNet per token; without a tail policy it RAISES the peak.
- Decode at long context is the MTP verification forward (91 % of a round at 128K). A joint verification scan is bit-identical to
  the per-query pattern at kernel level; estimate +14 % tok/s at 128K. MLX's vector kernel is already at memory bandwidth.
- Neither agentic harness reaches long context (opencode max 27.8K, AgentBench OS max 3.8K): the time benefit lands on long
  daily-driver sessions and capacity.
- Warm-state drift (new AGENTS.md rule): ≈ 20 % slower prefill work when a run follows a five-minute GPU load; compare latency arms
  only in matched state with a ≥ 10 min cooldown.

## Pending (operator)

1. **Confirm the M57 build on the measured case** (approved when the expected gain was ≈ 2×). Recommendation: build — 256K memory
   headroom, better accuracy, −16…−22 % TTFT at 128K and ≈ −30 % predicted at 256K, and it unlocks larger chunks for the dense path.
   On go: M54 funnel from `docs/specs/m57-attention-policy.md` (Sonnet implementer per repo: fork, mlx-serve, stack provenance;
   cold reviews by a Claude reviewer and Codex; live gate; pilot twice; qualification design frozen before the first arm).
2. Queue or not: joint MTP verification scan as the next milestone; dense prefill path (dequantise-then-dense at chunks ≥ 2048) as a
   later candidate. Neither is in PLAN.
3. Push approvals: stack commits since `bd2823d`; fork branch `m57-prefill-profile` (merge to fork `main` or keep as a branch).
4. Carried: record P41 (watch-list for an open HySparse2-class checkpoint) and P42 (harder long-context benchmarks) in
   `docs/open-questions.md`? M56 stays PARKED (C110).

## Rules learned this session

- Read the kernel dispatch source and measure before designing around a flag: the "3.1×" was a cold-buffer artifact, and three
  claims in the first design were wrong.
- A memory instrument must show its known positive first (`get_active_memory` still counts a just-released buffer).
- A single back-to-back latency pair is order-biased on this laptop (E15) — matched state or no delta.
- `scripts/stack_stop.sh` kills ANY process whose command line matches the worker pattern, including a Codex review whose prompt
  was passed as an argument. Pass review prompts on stdin (`codex exec … - < prompt.md`); don't stop the stack while reviewers run.
- The worker's stderr log (`$TMPDIR/mlx-manager-logs/<model>.log`) is recreated at worker start — read the whole file per arm.
- Profiled or fork-branch runs write to the workdir only; nothing from them enters `benchmark/results/`.

Next decision id C112; discussion ids continue from P80.
