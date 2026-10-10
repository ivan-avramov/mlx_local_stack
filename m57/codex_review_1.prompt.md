You are a cold, adversarial DESIGN reviewer. Nothing has been built. Review the proposed "M57" attention work for this repo.

REVIEW LENS (the operator's instruction, binding): review from a QUALITY-MAXIMIZING perspective. Do NOT optimize for the fastest or
cheapest implementation. Because the topic is performance optimization, "quality" means: the option that maximizes the idea's potential
for improving performance (long-context prefill/TTFT, long-context decode, memory) WITHOUT sacrificing model output quality (a
reasonable, negligible amount is acceptable). If the better outcome needs new Metal kernels, a retrofit of sparse/approximate
attention, a cache-precision redesign, chunking redesign, upstream MLX changes, or a different scope than a flag — say so and justify
it. Implementation time is not a constraint; unsupported optimism is.

TARGET: the first pick `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` served with native16 KV (kv_bits 0), MTP predictor ON,
prefill_step_size 512, cap/prealloc 262144, on one M5 Max 64GB laptop, MLX 0.32.2. Workload: agentic coding (short actions, long tool
observations, growing context up to 256K).

READ (read-only):
- AGENTS.md (rules), docs/proposal-flash-attention.md (ALL of it; the section "Design session 2026-10-04" is the design under review),
  docs/PLAN.md (Phase 2), docs/serving-path.md, docs/metrics.md, main_models.yaml (first-pick entry),
  docs/campaign-results.md (grep "native16", "Prefill s", "261449" for the measured ladders).
- Fork (sibling dir): ../mlx-vlm/mlx_vlm/models/base.py (scaled_dot_product_attention and neighbours),
  ../mlx-vlm/mlx_vlm/models/qwen3_5/language.py (Qwen3_5Attention, masks, the custom Metal kernels, GatedDeltaNet linear layers,
  speculative verify), ../mlx-vlm/mlx_vlm/models/cache.py, ../mlx-vlm/mlx_vlm/turboquant.py (existing fused kernels),
  ../mlx-vlm/mlx_vlm/speculative/mtp.py, ../mlx-vlm/mlx_vlm/server/cli.py and server/generation.py (prefill loop, pool-limit derivation).
- Router: ../mlx-serve/src/mlx_serve/config.py, process_manager.py.
- MLX dispatch source for the installed version, if you have network:
  https://raw.githubusercontent.com/ml-explore/mlx/v0.32.2/mlx/backend/metal/scaled_dot_product_attention.cpp
  (and the same path on `main`). If you cannot fetch it, say so and mark every claim about MLX internals UNVERIFIED.

HARD CONSTRAINTS: read-only. Do NOT load any model, run any GPU/Metal workload, start servers, or write files. Reading, grepping and
trivial CPU-only arithmetic are fine. Never state a measurement you did not find in the repo; label estimates as estimates and show
the arithmetic.

DELIVER (markdown, ids X1, X2, ... one per finding; cite file:line for every code claim):
1. FACT CHECK of the design record's claims (P25–P44): confirmed / refuted / unverifiable, with evidence. Hunt specifically for wrong
   assumptions about which MLX kernel each path takes (prefill chunk, tail chunk, cached continuation, MTP verification, single-token
   decode), about when force_fused raises, and about dtype.
2. IS `auto | force_fused` THE PERFORMANCE-MAXIMAL DESIGN? What performance is left on the table. Give a ranked option list covering at
   least: dispatch policy design, prefill chunk size, custom exact kernels (prefill and decode/verify), the linear-attention
   (GatedDeltaNet) and MLP share of prefill, long-context decode, cache precision/layout, avoiding re-prefill, sparse/approximate
   attention retrofits (prefill vs decode), upgrading or upstreaming MLX. For each: mechanism, estimated gain with arithmetic,
   confidence, output-quality risk, and the CHEAPEST DECISIVE EXPERIMENT that would fund or kill it.
3. Defects and gaps in the acceptance criteria (AC1–AC10) and the qualification design / decision rule (Q1–Q5) — things that would let
   a wrong or sub-maximal result pass, or a good one fail.
4. Your recommended roadmap in order, with explicit go/no-go gates. State plainly where you disagree with the design record.
Be concrete and terse; no praise, no restating the brief. Aim for 1200–2200 words.
