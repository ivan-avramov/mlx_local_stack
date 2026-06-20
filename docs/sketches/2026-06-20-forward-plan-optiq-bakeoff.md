# Forward plan — 2-model bake-off (agentic coding + heavy reasoning) + MTP

**Date:** 2026-06-20 (rev 2). **Purpose:** a clean-session starting point. Picks up after Phase 0a (capacity) + Phase 0b-light (VT reasoning). Program goal unchanged: an evidence-based pick of local LLM(s) for **256K-context agentic coding on a 64GB Mac**, with B200-transferable technique/methodology.

> **rev 2 change:** both OptiQ variants and the MTP-loader-fix step are **dropped**. Reason below (MTP turns out to be a separate, lossless drafter — no OptiQ needed).

## Where we are (recap)

**Metric (settled):** capacity gate = **MLX peak memory** (`mx.get_peak_memory` = prefill spike = OOM trigger), report steady-state RSS alongside. psutil-RSS under-counts MLX/Metal on Apple Silicon; system-delta is contamination-prone. OOM-graceful handling in the ladder.

**Phase 0a capacity (≤46GB MLX-peak gate) + Phase 0b-light (VT multi-hop reasoning):**

| Model | Arch | Fits @46GB | Decode | VT-reasoning | Disposition |
|---|---|---|---|---|---|
| **Qwen3.6-27B-UD-6bit** | dense + GatedDeltaNet | 192K (256K @56GB) | 4–6 tok/s | ≥64K, perfect | **KEEP — reasoner/quality** |
| **gemma-26b-a4b-QAT-4bit** | MoE + sliding-window | **256K** | 12–26 tok/s | ≥64K, noisier | **KEEP — daily/speed+capacity** |
| gemma-26b-a4b-8bit | MoE | 192K | — | — | OUT (redundant w/ QAT) |
| gemma-4-31b-4bit | dense + SW | none (OOM@160K) | — | — | OUT |
| Qwen3.6-27B-OptiQ-4bit | dense + GDN | — | — | — | **DROPPED** (see below) |
| gemma-26b-a4b-OptiQ-4bit | MoE | — | — | — | **DROPPED** (QAT ≥ OptiQ, same tier) |

Commits: MLX-peak gate `c0ffd5c`, reasoning probe `e32e55b`, results `4e64845`. Harness in `benchmark/bench/`; per-machine queue `benchmark/run_capacity_seq.sh`; re-gate helper `benchmark/rescore.py`. Result JSONs: `benchmark/results/<model>/{capacity_retrieval,reasoning}.json`.

**Why OptiQ is dropped:**
- **gemma-OptiQ-4bit** is the same 4-bit MoE tier as QAT-4bit; QAT (quant-aware) ≥ OptiQ (post-training) for this fragile MoE → redundant.
- **Qwen-OptiQ-4bit** is a 4-bit tier *below* the UD-6bit → no quality gain. Its only draws were (a) marginal extra capacity and (b) it embedded MTP weights. Both are moot: capacity is covered (256K via gemma-QAT @46GB or Qwen-6bit @56GB), and **MTP is available the right way — see Phase 2.**

**Open finding:** the light VT probe was **too easy to discriminate** (both KEEP models ≥64K). The honest reasoning ceiling needs the **heavy tier (RULER-aggregation + NoLiMa latent)** — also the most likely place dense-hybrid (Qwen) and sliding-window MoE (gemma) diverge.

## The 2-model bake-off

- **Reasoner (dense + GDN hybrid):** `Qwen3.6-27B-UD-6bit` — quality/reasoning/coding leader [E for coding], retrieval 1.0→256K [M], slow decode [M].
- **Daily driver (MoE + sliding-window):** `gemma-26b-a4b-QAT-4bit` — only 256K-@46GB fitter [M], fast decode [M], coding/latent-reasoning are the open questions [E].

Grade both on the two unmeasured axes (agentic coding, latent reasoning) to confirm/refine the role split. `[M]`=measured, `[E]`=expected/prior.

## Plan

### Step 1 — Phase 0c: agentic coding  [BIG BUILD] → run on both
The #3 axis; decides daily-driver fitness. Build (spec → plan → TDD), reusing trusted benchmarks:
- **Tool-calling:** BFCL (quick) + τ-bench (agentic).
- **Coding (single-shot):** LiveCodeBench.
- **Coding (agentic, in-loop):** Aider polyglot (core) + SWE-bench-Verified subset (30–50 issues).
- **Instruction-following:** IFEval.
- **Execution-gated correctness** (sandbox) + **mixed-family judge panel** (Sonnet + Opus + GPT-5.5/codex; median; report per-judge) for the subjective code-quality rubric (the 10 axes). Judge ≠ correctness oracle.
- Carry the **thinking-budget fix** from the reasoning probe (generous `max_tokens` + `thinking_budget`).
- Produce a coding scorecard (objective pass/fail + subjective rubric) for both models.

### Step 2 — Heavy reasoning tier  [BUILD] → run on both, extend grid
Build the real discriminators (retire the light VT probe, or keep only as a floor):
- **RULER-aggregation** (common/frequent words) + **NoLiMa** (latent 2-hop, minimal lexical overlap — the honest effective-context test). Thinking-controlled, exact-match/MC.
- **Grid:** climb from the light grid, then **extend past 64K in 8K steps (72K, 80K, …) until accuracy drops below threshold** — each model's true latent-reasoning ceiling.
- This is where Qwen-hybrid vs gemma sliding-window (1024 local window caps multi-hop spanning >1024 tokens) most likely separate.

### Step 3 — Synthesize → decision
One scorecard across the 2 on capacity × retrieval × latent-reasoning × agentic-coding × speed. Output: confirmed **daily-driver** (gemma-QAT for speed+256K *if* its latent reasoning holds; else Qwen) and **reasoner** (likely Qwen-6bit), with the quantified tradeoffs. Update `main_models.yaml` roles + write the decision guide.

## Phase 2 levers (technique tuning on the winner[s])

- **MTP self-speculation — the dense Qwen's decode lever, LOSSLESS ~1.4–2.2×.** Path: load `mlx-community/Qwen3.6-27B-MTP-5bit` (or `-4bit`) as the **draft model** alongside the `Qwen-UD-6bit` **target**, `draft_kind=mtp`. **No re-convert, no quality trade** — spec-decode verifies every token, so it's the high-quality 6-bit *and* fast. Attacks Qwen's only real weakness (4–6 tok/s); could let Qwen double as a daily driver (narrowing gemma-QAT's edge to the 256K-@46GB-browser-open niche). **Validate, don't assume:** the fork's `draft_kind` must handle `mtp` for the VL model with **GatedDeltaNet recurrent-state capture/rollback on rejection** (the `suffix` path needed a v1.1 fix for exactly this); confirm the drafter's small footprint doesn't dent the 256K budget. → wire + validate GDN-rollback + measure.
- **Prefill-spike tuning** (smaller prefill chunks) — pull Qwen-6bit's 256K under the 46GB gate (currently 53GB).
- **EpiCache** (token eviction) — the decode lever consistent with the compute-bound finding (fewer tokens, not fewer bits).
- Per-model: TQ-Prod KV, draft/suffix tuning.

## Execution notes for the clean session
- Two machines: `ssh $REMOTE_HOST` (M5 Max, ~7× faster, remote/clean — heavy runs) + local M2 Max (dev laptop). **One model per machine at a time**, unload between, **keep the box quiet during a run** (MLX-peak gate is robust to other processes; RAM headroom isn't).
- Lean router (no OWUI/docker): `MLX_SERVE_CONFIG=main_models.yaml uv run mlx-serve start`. On M5, prepend `PATH=/opt/homebrew/bin:$PATH` (uv not on the non-interactive PATH) and `set -a; . ./.env; set +a` for HF_TOKEN.
- Tests: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/`.
- Sync harness to M5 with rsync (nothing pushed to origin): `rsync -a benchmark/bench/ $REMOTE_HOST:~/Documents/ws/mlx_local_stack/benchmark/bench/`.
- Suggested order: build Step 1 (coding) and Step 2 (heavy reasoning) harness in parallel, then run both across the 2 models (Qwen on M5, gemma on M2). MTP is Phase 2 (after the bake-off picks the candidate).
