# Forward plan — OptiQ unblock + 4-model bake-off (agentic coding + heavy reasoning)

**Date:** 2026-06-20. **Purpose:** a clean-session starting point. Picks up after Phase 0a (capacity) + Phase 0b-light (VT reasoning) completed. Goal of the program unchanged: an evidence-based pick of local LLM(s) for **256K-context agentic coding on a 64GB Mac**, with B200-transferable technique/methodology.

## Where we are (recap)

**Metric (settled):** capacity gate = **MLX peak memory** (`mx.get_peak_memory` = prefill spike = OOM trigger), report steady-state RSS alongside. psutil-RSS under-counts MLX/Metal on Apple Silicon; system-delta is contamination-prone. OOM-graceful handling in the ladder.

**Phase 0a capacity (≤46GB MLX-peak gate) + Phase 0b-light (VT multi-hop reasoning):**

| Model | Arch | Fits @46GB | Decode | VT-reasoning | Role |
|---|---|---|---|---|---|
| Qwen3.6-27B-UD-6bit | dense + GatedDeltaNet | 192K (256K @56GB) | 4–6 tok/s | ≥64K, perfect | reasoning/quality leader |
| gemma-26b-a4b-QAT-4bit | MoE + sliding-window | **256K** | 12–26 tok/s | ≥64K, noisier | daily/capacity+speed leader |
| gemma-26b-a4b-8bit | MoE | 192K | — | — | OUT (redundant w/ QAT) |
| gemma-31b-4bit | dense + SW | none (OOM@160K) | — | — | OUT |
| Qwen3.6-27B-OptiQ-4bit | dense + GDN | not measured | — | — | **load-crash (MTP head)** |
| gemma-26b-a4b-OptiQ-4bit | MoE | not measured | — | — | untested |

Commits: MLX-peak gate `c0ffd5c`, reasoning probe `e32e55b`, results `4e64845`. Harness in `benchmark/bench/`; per-machine queue `benchmark/run_capacity_seq.sh`; re-gate helper `benchmark/rescore.py`. Result JSONs: `benchmark/results/<model>/{capacity_retrieval,reasoning}.json`.

**Key open finding:** VT (explicit-link multi-hop) was **too easy to discriminate** — both front-runners hit ≥64K. The honest reasoning ceiling needs the **heavy tier (RULER-aggregation + NoLiMa latent)**, which is also where dense-hybrid (Qwen) vs sliding-window MoE (gemma) are most likely to diverge.

## The 4-model bake-off roster

Two architectures × two quant tiers, framed by role:

- **Reasoning/quality pair (dense+GDN hybrid):** `Qwen3.6-27B-UD-6bit` (front-runner) vs `Qwen3.6-27B-OptiQ-4bit` (lighter tier: ~4-bit, expected lower quality esp. long-ctx, but better capacity + has the MTP head).
- **Daily/speed pair (MoE+SW):** `gemma-26b-a4b-QAT-4bit` (front-runner) vs `gemma-26b-a4b-OptiQ-4bit` (same 4-bit tier; expect QAT ≥ OptiQ).

**Calibrated expectation:** OptiQ variants are the lighter/cheaper tier — grading them **quantifies the quality cost of the lower-precision quant vs its capacity/speed gain**, not "are they equal." For pure quality, expect Qwen-6bit (reasoning) and QAT-4bit (MoE) to lead.

## Plan

### Step 0 — Unblock OptiQ (loader fix)  [fork change, bounded]
`Qwen3.6-27B-OptiQ-4bit` crashes on load: the checkpoint retains the MTP head (29 `mtp.*` weights) and the deployed `src/mlx-vlm` loader does a strict weight-load that rejects the extras (`Received 29 parameters not in model: mtp.*`).
- **Fix (minimal, to make it load):** strip/ignore `mtp.*` keys before the strict load (the loader was *supposed* to per Phase-1 notes — investigate why the strip isn't hit for the VL wrapper; the deployed `src/mlx-vlm` submodule may predate it). Edit the **parent fork** `../mlx-vlm`, test via PYTHONPATH override, then bump the submodule. ([[feedback-edit-parent-forks-not-submodules]])
- **Scope boundary:** this only makes the base model *load*. **Wiring the MTP head for self-speculative decode** (~1.5–2.5× novel decode) is a *separate, bigger* Phase-2 lever — do NOT conflate. (But it's the same checkpoint, so this is the on-ramp.)
- **Also test-load `gemma-26b-a4b-OptiQ-4bit`** — MTP is a Qwen3.6 feature, so gemma-OptiQ likely loads fine; confirm (it may have its own quirk).

### Step 1 — Capacity confirm on the two OptiQ variants  [existing harness, cheap]
Run the capacity+retrieval ladder (MLX-peak gate, `run_capacity_seq.sh`) on `Qwen3.6-27B-OptiQ-4bit` and `gemma-26b-a4b-OptiQ-4bit`. Expectation to verify: Qwen-OptiQ ~4-bit weights → ~47–50GB @256K (may cap ~224K @46GB); gemma-OptiQ ≈ QAT (~40GB, fits 256K). One model per machine, boxes quiet.

### Step 2 — Phase 0c: agentic coding  [BIG BUILD] → run on all 4
The #3 axis; decides daily-driver fitness. Build (spec → plan → TDD), reusing trusted benchmarks per the harness spec:
- **Tool-calling:** BFCL (quick) + τ-bench (agentic).
- **Coding (single-shot):** LiveCodeBench.
- **Coding (agentic, in-loop):** Aider polyglot (core) + a small SWE-bench-Verified subset (30–50 issues).
- **Instruction-following:** IFEval.
- **Execution-gated correctness** (sandbox) + **mixed-family judge panel** (Sonnet + Opus + GPT-5.5/codex; median; report per-judge) for the subjective code-quality rubric (the 10 axes). Judge ≠ correctness oracle — execution gates correctness.
- **Carry the thinking-budget fix** from the reasoning probe (generous `max_tokens` + `thinking_budget` cap) so coding answers aren't starved.
- Run all 4; produce a coding scorecard (objective pass/fail + subjective rubric).

### Step 3 — Heavy reasoning tier  [BUILD] → run on all 4, extend grid
Build the real reasoning discriminators (retire/keep-as-floor the light VT probe):
- **RULER-aggregation** (common/frequent words) + **NoLiMa** (latent 2-hop, minimal lexical overlap — the honest effective-context test).
- Thinking-controlled (same budget fix). Exact-match/MC scored.
- **Grid:** climb-to-cliff starting at the light grid, then **extend past 64K in 8K increments (72K, 80K, …) until accuracy drops below threshold** — find each model's true latent-reasoning ceiling.
- Run all 4. This is where Qwen-hybrid vs gemma-sliding-window likely separate (gemma's 1024 local window caps multi-hop spanning >1024 tokens).

### Step 4 — Synthesize → decision
One scorecard across the 4 on capacity × retrieval × reasoning(latent) × agentic-coding × speed. Output: the **daily-driver** pick (likely gemma-QAT for speed+256K *if* its latent reasoning holds; else Qwen) and the **reasoning-driver** pick (likely Qwen-6bit), with the quantified quality/capacity/speed tradeoffs per quant. Update `main_models.yaml` roles + write the decision guide.

## Deferred to Phase 2 (technique tuning on the winner[s])
- **MTP self-speculation** (wire the MTP head from the OptiQ checkpoint) — ~1.5–2.5× novel decode for the dense Qwen.
- **Prefill-spike tuning** (smaller prefill chunks) — pull Qwen-6bit's 256K under the 46GB gate (currently 53GB).
- **EpiCache** (token eviction) — the decode lever consistent with the compute-bound finding.
- Per-model: TQ-Prod KV, draft/suffix tuning.

## Execution notes for the clean session
- Two machines: `ssh $REMOTE_HOST` (M5 Max, ~7× faster, remote/clean — heavy runs) + local M2 Max (dev laptop). **One model per machine at a time**, unload between, **keep the box quiet during a run** (the MLX-peak gate is robust to other processes, but RAM headroom isn't).
- Start the lean router (no OWUI/docker): `MLX_SERVE_CONFIG=main_models.yaml uv run mlx-serve start`. On M5, prepend `PATH=/opt/homebrew/bin:$PATH` (uv not on the non-interactive PATH) and `set -a; . ./.env; set +a` for HF_TOKEN.
- Tests: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/`.
- Sync harness to M5 with rsync (not pushed to origin): `rsync -a benchmark/bench/ $REMOTE_HOST:~/Documents/ws/mlx_local_stack/benchmark/bench/` (+ `main_models.yaml` after the loader/submodule bump).
- Suggested order: Step 0 (loader) → Step 1 (OptiQ capacity, quick) → in parallel build Step 2 (coding) and Step 3 (heavy reasoning) harness, then run both across the 4 models.
