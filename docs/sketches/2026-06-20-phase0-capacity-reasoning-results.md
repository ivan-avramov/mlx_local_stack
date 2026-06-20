# Phase 0a + 0b results — capacity, retrieval, reasoning-depth (quick tier)

**Date:** 2026-06-20 (measured autonomously, M5 Max + M2 Max, both 64–68GB).
**Status:** Quick-tier complete for the shortlist. Inputs to model selection + Phase 0c (agentic coding) and the heavy reasoning tier.
**Harness:** `benchmark/bench/` (commits up to `e32e55b`). Result JSONs: `benchmark/results/<model>/{capacity_retrieval,reasoning}.json` on each box.

## The metric (settled the hard way)

Capacity gate = the model's **MLX peak memory** (`mx.get_peak_memory` = the prefill **spike**, which is what triggers OOM), with **steady-state RSS reported alongside**. Two earlier metrics were wrong and discarded:
- **system-used − idle-baseline**: contamination-prone — a concurrent HF download inflated it +4.7GB.
- **psutil process RSS**: *under-counts* MLX/Metal memory on Apple Silicon — it's the resident/steady-state cost and misses the spike. Proof from one run (Qwen-6bit @256K): **RSS 26GB vs MLX-peak 53GB vs system 63.8GB**.

A hard OOM (request 500s before returning) is caught → recorded as `fits=False` → stops the ladder (no crash).

## Phase 0a — capacity (≤46GB MLX-peak gate) + retrieval

| Model | Arch | Fits @46GB | @56GB (browser-closed) | MLX-peak @256K | RSS (steady) | Decode | Retrieval |
|---|---|---|---|---|---|---|---|
| **Qwen3.6-27B-UD-6bit** | dense + GatedDeltaNet hybrid | **≤192K** | **256K** | 53GB | 26GB | 4–6 tok/s | **1.0 → 256K** |
| **gemma-26b-a4b-QAT-4bit** | MoE (~4B active) + sliding-window | **256K** ✓ | 256K | **40.5GB** | 16.7GB | **12–26 tok/s** | thinking-contaminated* |
| gemma-26b-a4b-8bit | MoE + sliding-window | ≤192K | 256K | 53GB | 21GB | (fast) | thinking-contaminated* |
| gemma-4-31b-UD-4bit | dense + sliding-window | **none** (OOM @160K) | — | OOM | — | — | — |
| Qwen3.6-27B-OptiQ-4bit | dense + GDN | **load-crash** | — | — | — | — | — |

\* The capacity probe's retrieval used a 256-token answer budget; for thinking models the think-trace ate it (gemma read 0.0–0.4). Not a real failure — the reasoning probe below, with a proper thinking budget, shows gemma scoring fine. Qwen's 1.0 is solid (it answered within budget).

**Headline:** **gemma-QAT-4bit is the only model that fits 256K within the 46GB budget** (40.5GB peak), and it decodes 3–4× faster — the MoE + sliding-window architecture keeps both the KV and the prefill spike small. **Qwen-6bit fits 192K @46GB / 256K only on the browser-closed 56GB profile**, and is slower, but has the cleanest retrieval (1.0 to 256K). gemma-31b dense is out (its prefill spike OOMs a 64GB box at 160K). OptiQ is blocked — see below.

## Phase 0b — reasoning depth (multi-hop variable-tracking, threshold 0.8, 5 samples/rung)

| Model | 8K | 16K | 24K | 32K | 48K | 64K | Effective |
|---|---|---|---|---|---|---|---|
| Qwen3.6-27B-UD-6bit | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | **≥64K** |
| gemma-26b-a4b-QAT-4bit | 0.8 | 1.0 | 0.8 | 0.8 | 1.0 | 1.0 | **≥64K** |

**Both pass to the grid ceiling (64K); neither cliffs in range; Qwen is cleaner (perfect vs noisy).**

**Critical caveat:** this is RULER-style **variable-tracking** — multi-hop but with *explicit* "X = Y" links (lexically traceable). It is **easier than NoLiMa-style latent reasoning** (where the literature reports cliffs at 2–8K even for frontier models). So "reasons to ≥64K" is real but *task-specific*; it does **not** establish latent-reasoning depth. The honest reasoning ceiling needs the heavy tier (RULER-aggregation + NoLiMa), which is where the two architectures may finally diverge.

## Emerging picture — the trilemma, plus a surprise

- **Qwen3.6-27B-6bit = the quality leader.** Retrieval 1.0 to 256K; VT-reasoning perfect to 64K. But slow decode (4–6 tok/s) and capacity-capped at 192K @46GB (256K needs the browser closed).
- **gemma-26b-a4b-QAT-4bit = the capacity + speed leader, and the surprise.** The *only* 256K-fitter at 46GB, 3–4× faster decode, and VT-reasoning passes to 64K (noisier). The sliding-window MoE was predicted to be reasoning-weak; VT doesn't expose that — but latent reasoning (heavy tier) might.
- gemma-31b-4bit: eliminated (OOM). gemma-26b-a4b-8bit: redundant with the QAT-4bit (same arch, less headroom).

The daily-driver choice now hinges on the two axes still unmeasured: **heavy-tier latent reasoning** and **agentic coding (Phase 0c)** — that's where dense-hybrid Qwen and the MoE are most likely to separate. Quick-tier verdict so far: **Qwen = max quality, gemma-QAT = max usable context + speed**, both viable to 64K on tractable reasoning.

## OptiQ-4bit — blocked, but it unblocks MTP

`Qwen3.6-27B-OptiQ-4bit` crashes on load: the checkpoint **retains the MTP (multi-token-prediction) head** (29 `mtp.*` weights) and the deployed `src/mlx-vlm` loader rejects the extra params (strict load). Phase-1 research flagged MTP self-speculation (~1.5–2.5× *novel* decode — the one decode lever for the dense Qwen) as **blocked for lack of an MTP-retaining checkpoint.** OptiQ-4bit *is* that checkpoint. So a loader fix (strip-to-load, or wire MTP) both unblocks OptiQ's capacity number *and* enables the MTP lever — a Phase-2 item.

## Open / next

1. **Phase 0c — agentic coding** (tool-calling, Aider polyglot, SWE-verified subset, IFEval): the #3 axis, decides daily-driver fitness. Build needed.
2. **Heavy reasoning tier** — RULER-aggregation + NoLiMa (latent), the honest reasoning ceiling. Build needed; likely where Qwen vs MoE diverges.
3. **Extend the reasoning grid >64K** (both models didn't cliff on VT) to find the actual VT ceiling.
4. **Prefill-spike tuning** (smaller prefill chunks) to pull Qwen-6bit's 256K under 46GB — Phase-2 lever.
5. **OptiQ / MTP** loader fix → MTP self-spec — Phase-2.
6. Judge-panel code-quality rubric (Phase 0c) for the subjective coding axes.
