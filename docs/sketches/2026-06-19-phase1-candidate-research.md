# Phase 1 — Candidate research & pruning (256K agentic coding, 64GB Apple Silicon)

**Date:** 2026-06-19
**Status:** Research complete. Input to Phase 2 (technique characterization).
**Source:** workflow `wf_8dd78f6e-d1e` (17 agents, ~914K tokens): survey → draft roster → adversarial verification of load-bearing claims → synthesis. Program spec: `docs/superpowers/specs/2026-06-19-local-256k-eval-harness-design.md`.

## Headline finding

No roster model has a **proven** 256K story on either axis:

- **256K fit** — extrapolated from the 200K measurement (Qwen 40.4GB@200K on M5). Depends on the auto-derived `mx.set_cache_limit` buffer-pool cap (`cli.py:107`); the uncapped M2 curve projects ~50–55GB and would fail the 46GB budget. The only *directly measured* 256K pass in the roster is gemma-4-31b-UD-4bit at 44.6GB — a thin ~3% margin on a best-case synthetic run.
- **256K reasoning** — **refuted** for every candidate. Only single-needle *retrieval* is validated anywhere. Family RULER aggregation collapses (~92.6%@32K → ~80.8%@128K → ~59.6%@200K); NoLiMa-class 2-hop latent reasoning dies at 2–8K for *all* frontier models. Sliding-window Gemma has a hard 1024-token architectural ceiling on multi-hop.

This is the central justification for building the eval harness (Phase 0) before upgrading any "256K reasoning" claim from UNVERIFIED.

## Shortlist (4 entries, 5 checkpoints)

| # | Model | Role | 256K fit | Reasoning depth | Coding / agentic | Decode | First risk to test |
|---|-------|------|----------|-----------------|------------------|--------|---------------------|
| 1 | **Qwen3.6-27B-UD-MLX-6bit** (TQ kv4 + suffix) | Primary / quality | Unverified, thin (pool-cap-dependent) | Reliable ~32–64K; refuted past | **Best fit-in-64GB agentic coder** (SWE-Verified 77.2, LCB 83.9) | Weak: ~8–9.5 tok/s long-ctx (< 15 floor); dense-compute | Actual 256K needle + peak capture on M5/M2 |
| 2 | **Qwen3.6-27B-OptiQ-4bit** | Memory-headroom sibling | **Most likely to clear 46GB** (~28GB proj.) but never needle-run | ~32–64K + 4-bit-weight depth risk | Same family scores; better multi-turn tool-call robustness | Same dense profile | Does 4-bit regress multi-hop vs 6bit? + yaml `uniform→turboquant` fix |
| 3 | **gemma-4-26b-a4b** (QAT-4bit / 8bit) | Speed tier | **YES — high confidence** (MoE + iSWA → tiny KV) | **Weakest** (1024-window ceiling; predecessor NoLiMa <1K) | LCB 77.1, CF 1718 (below dense) | **Fastest** (MoE ~3.8B active; near-flat vs ctx) | 256K *prefill* completes w/o scores-matrix OOM? TTFT? |
| 4 | **gemma-4-31b-it-UD-MLX-4bit** | Dense quality cross-check | **Only directly-measured pass** (44.6GB, ~3% margin) | Refuted at depth (1024-window) | **Best dense coder** (LCB 80.0, CF 2150) | Slow (dense 31B) | Root-cause the 16K needle off-by-one FAIL before trusting retrieval |

## Pruned (with reasons)

- **Qwen3-Coder-Next 80B-A3B** (strongest *new* find) — **gate fails**: 4-bit weights ~42–45GB, ~52–54GB total @256K (only marginal in the 56GB browser-closed stretch). And "best agentic coder" is **false** — SWE 70.6 < roster Qwen's 77.2. Reconsider only behind a measured single-stream 256K-on-64GB run.
- **Qwen3-Coder-30B-A3B** — coding superseded (SWE 51.9); standard GQA grows KV on all ~48 layers → 256K tighter than the hybrid. Optional KV-path stress test only.
- **Qwen3.6-27B-MLX-8bit** — keep installed as the ~0.8%-lossless **bit-sweep quality anchor**, but heaviest weights leave least 256K headroom → out of the gate shortlist.
- **gemma-4-31B-it-qat-6bit** — gate fail (yaml caps it at 192K); keep as the **≤192K high-fidelity** (near-bf16 QAT) reference.
- **gemma-4-31b-it-6bit** — 256K gate fail (dense 6-bit weight wall); redundant with the 4-bit UD variant.
- **gemma-4-26B-A4B-it-OptiQ-4bit** — deduped in favor of the QAT-4bit variant (safer for this quant-fragile MoE).

## Framework verdict

**MLX (the mlx-vlm fork) primary; llama.cpp/GGUF cross-check.** Key correction: the 256K gate is won by *the fork*, not stock MLX — stock MLX SDPA caps ~52–73K (dequantizes quantized KV into an O(N²) score matrix); the fork's TurboQuant fused KV path + `chunked_prefill_policy` fix is what reaches 256K. **NA stays dead** (kernels present in mlx main, dispatch never selects them on M5; confirmed against source-built 0.32.0.dev). MLX's decode edge is real **only for MoE/low-active-param** models (the bandwidth lever), not the dense hybrid Qwen.

## Actionable repo fixes surfaced (proposing, not applied)

1. `Qwen3.6-27B-OptiQ-4bit` and `Qwen3.6-27B-MLX-8bit` yaml entries use `kv_quant_scheme: uniform` → should be `turboquant` to match the validated path before long-context reliance.
2. Highest-ROI deferred perf: re-convert Qwen3.6-27B **keeping the MTP head** (UD-MLX-6bit dropped it; loader strips `mtp.` keys) to unlock MTP self-spec (~1.5–2.5× novel decode) — the only novel-decode lever for the dense Qwen.

## Open questions → Phase 0/2 test targets

1. **GATE #1:** actual 256K needle on M5 (and M2) for Qwen-6bit with `mx.set_cache_limit` + `get_peak_memory` — < 46GB (browser-open) or only < 56GB (closed)? (M2 200K already OOMs → M2 256K may be impossible.)
2. **REASONING CURVES:** no model has any multi-hop/aggregation/NoLiMa number past ~64K. Build RULER-aggregation + NoLiMa-2-hop, run on the *actual quantized checkpoints*.
3. **QUANT × LONG-CTX:** does OptiQ-4bit (and gemma 4-bit) regress multi-hop vs 6/8-bit at length? (EMNLP-2025: 4-bit up-to-59% long-ctx loss; 8-bit ~0.8%.)
4. **PREFILL VIABILITY:** cold-256K TTFT per model — clears the ~90s floor, or is 256K "load-once, latency-tolerant" only?
5. **DECODE FLOOR:** dense Qwen ~8–9.5 tok/s < 15 floor. Does MTP self-spec deliver the 1.5–2.5× (where suffix gives ~0 on novel)?
6. **GEMMA-31B FIDELITY:** root-cause the 16K needle off-by-one (XKRYPTO9F1 vs F2) — tokenizer/quant artifact or real defect?
7. **M5 NA RE-TEST:** re-run `na_discriminator.py` on future mlx releases; if NA wires up, the prefill (matmul) story changes — decode (gather-bound) stays unchanged.
