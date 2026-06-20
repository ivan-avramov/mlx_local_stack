# Forward plan — Phase 1 Selection (finish) + Phase 2 Optimization

**Date:** 2026-06-20 (rev 3). **Purpose:** clean-session starting point. Program goal: an evidence-based pick of local LLM(s) for **256K-context agentic coding on a 64GB Mac**, with B200-transferable technique/methodology.

## Phase scheme (clean labels)

- **Phase 1 — Selection** ("find the right model[s]"): build the eval harness and measure every candidate at **baseline config** across four axes — **capacity → retrieval → reasoning → agentic coding** — then decide the *daily-driver* and *reasoner* picks. The early landscape-research/pruning was the front of this phase.
- **Phase 2 — Optimization** ("make the chosen model[s] better"): apply perf levers to the *winner(s)* under the ≤5% quality-neutral bar.

> **rev 3:** renamed to this two-phase scheme (was "Phase 0a/0b/0c" + "Phase 2 levers"). Both OptiQ variants and the MTP-loader-fix step are dropped (MTP is a separate lossless drafter — see Phase 2).

## Where we are (Phase 1 progress)

**Metric (settled):** capacity gate = **MLX peak memory** (`mx.get_peak_memory` = prefill spike = OOM trigger), report steady-state RSS alongside. psutil-RSS under-counts MLX/Metal on Apple Silicon; system-delta is contamination-prone. OOM-graceful handling in the ladder.

**Phase 1 axes measured so far — capacity (≤46GB MLX-peak gate) + light reasoning (variable-tracking):**

| Model | Arch | Fits @46GB | Decode | VT reasoning | Disposition |
|---|---|---|---|---|---|
| **Qwen3.6-27B-UD-6bit** | dense + GatedDeltaNet | 192K (256K @56GB) | 4–6 tok/s | ≥64K, perfect | **KEEP — reasoner/quality** |
| **gemma-26b-a4b-QAT-4bit** | MoE + sliding-window | **256K** | 12–26 tok/s | ≥64K, noisier | **KEEP — daily/speed+capacity** |
| gemma-26b-a4b-8bit | MoE | 192K | — | — | OUT (redundant w/ QAT) |
| gemma-4-31b-4bit | dense + SW | none (OOM@160K) | — | — | OUT |
| Qwen3.6-27B-OptiQ-4bit | dense + GDN | — | — | — | DROPPED (tier below 6-bit; MTP via drafter instead) |
| gemma-26b-a4b-OptiQ-4bit | MoE | — | — | — | DROPPED (QAT ≥ OptiQ, same tier) |

Commits: MLX-peak gate `c0ffd5c`, reasoning probe `e32e55b`, results `4e64845`. Harness `benchmark/bench/`; per-machine queue `run_capacity_seq.sh`; re-gate helper `rescore.py`. Result JSONs: `benchmark/results/<model>/{capacity_retrieval,reasoning}.json`.

**Open finding:** light VT reasoning was **too easy to discriminate** (both KEEP models ≥64K). The honest ceiling needs the heavy tier (RULER-aggregation + NoLiMa latent) — likely where dense-hybrid (Qwen) and sliding-window MoE (gemma) diverge.

## Phase 1 — remaining: the 2-model bake-off

- **Reasoner (dense + GDN):** `Qwen3.6-27B-UD-6bit` — quality/reasoning/coding leader [E for coding], retrieval 1.0→256K [M], slow decode [M].
- **Daily driver (MoE + SW):** `gemma-26b-a4b-QAT-4bit` — only 256K-@46GB fitter [M], fast decode [M], coding/latent-reasoning open [E].

`[M]`=measured, `[E]`=expected/prior. Grade both on the two unmeasured axes:

### Step 1 — agentic coding  [BIG BUILD] → run on both
Build (spec → plan → TDD), reusing trusted benchmarks:
- **Tool-calling:** BFCL (quick) + τ-bench (agentic).
- **Coding (single-shot):** LiveCodeBench.
- **Coding (agentic, in-loop):** Aider polyglot (core) + SWE-bench-Verified subset (30–50 issues).
- **Instruction-following:** IFEval.
- **Execution-gated correctness** (sandbox) + **mixed-family judge panel** (Sonnet + Opus + GPT-5.5/codex; median; per-judge reported) for the subjective code-quality rubric (10 axes). Judge ≠ correctness oracle.
- Carry the **thinking-budget fix** (generous `max_tokens` + `thinking_budget`).

### Step 2 — heavy reasoning  [BUILD] → run on both, extend grid
- **RULER-aggregation** + **NoLiMa** (latent 2-hop, minimal lexical overlap — the honest effective-context test). Thinking-controlled, exact-match/MC.
- **Grid:** climb from the light grid, then extend past 64K in 8K steps until accuracy drops below threshold — each model's true latent-reasoning ceiling.

### Step 3 — decide
One scorecard across the 2 on capacity × retrieval × latent-reasoning × agentic-coding × speed → confirmed daily-driver + reasoner, with quantified tradeoffs. Update `main_models.yaml` roles + write the decision guide. **This closes Phase 1.**

## Phase 2 — Optimization (perf levers on the winner[s], quality-neutral)

Priority order:
1. **MTP self-speculation — the dense Qwen's decode lever, LOSSLESS ~1.4–2.2×.** Load `mlx-community/Qwen3.6-27B-MTP-5bit` (or `-4bit`) as the **draft** model alongside the `Qwen-UD-6bit` **target**, `draft_kind=mtp`. No re-convert, no quality trade (spec-decode verifies every token). **Decision-relevant** — sits at the Phase-1/2 boundary: if it makes Qwen fast, Qwen may take the daily-driver role too (leaving gemma-QAT only the 256K-@46GB-browser-open niche), so evaluate it right after Step 3. **Validate, don't assume:** the fork's `draft_kind` must handle `mtp` for the VL model with **GatedDeltaNet recurrent-state capture/rollback on rejection** (the `suffix` path needed a v1.1 fix for exactly this); confirm the drafter's footprint doesn't dent the 256K budget.
2. **Prefill-spike tuning** (smaller prefill chunks) — pull Qwen-6bit's 256K under the 46GB gate (currently 53GB).
3. **EpiCache** (token eviction) — long-context decode lever, consistent with the compute-bound finding (fewer tokens, not fewer bits).
4. **Per-core-NA** — prefill/TTFT only; **currently not reachable** via mlx's dispatch, and the workload front-loads prefill → lowest priority; "re-test on a future mlx release" item.
5. Per-model: TQ-Prod KV, draft/suffix tuning.

## Execution notes for the clean session
- Two machines: `ssh $REMOTE_HOST` (M5 Max, ~7× faster, remote/clean → heavy runs) + local M2 Max (dev laptop). **One model per machine at a time**, unload between, **keep the box quiet during a run** (MLX-peak gate is robust to other processes; RAM headroom isn't).
- Lean router (no OWUI/docker): `MLX_SERVE_CONFIG=main_models.yaml uv run mlx-serve start`. On M5 prepend `PATH=/opt/homebrew/bin:$PATH` (uv not on non-interactive PATH) and `set -a; . ./.env; set +a` for HF_TOKEN.
- Tests: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/`.
- Sync harness to M5 via rsync (nothing pushed to origin): `rsync -a benchmark/bench/ $REMOTE_HOST:~/Documents/ws/mlx_local_stack/benchmark/bench/`.
- Suggested order: build Step 1 (coding) + Step 2 (heavy reasoning) harness in parallel, then run both across the 2 models (Qwen on M5, gemma on M2), then Step 3. MTP (Phase 2) right after.
