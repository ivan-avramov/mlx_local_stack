# Phase 2 — Optimization Program (Ornith + Distill): perf + KV memory

**Status:** design (approved structure 2026-07-07). Program-level spec; the two
real builds (#4 prompt-lookahead, #5 TQ fused kernel) spin out their own
brainstorm→spec→plan when reached.

## Goal & scope

Take the two settled winners and improve **throughput** (prefill = input tok/s /
TTFT; decode = output tok/s) and **KV-cache memory footprint**, without regressing
quality. This is Phase 2 (Optimization) of the campaign: quality-neutral perf
levers on the winners, measured OFAT along a context-length curve.

Winners (full registry names, always):
- `Ornith-1.0-35B-mlx-uniform-4bit` — hybrid linear-attn MoE (256 experts / 8 active
  + shared expert; ~10/40 layers carry a *growing* KV, the rest are constant-state
  linear-attn). Shipped config: **fp16 KV** (`kv_bits: 0`), `prefill_step_size 512`,
  256K peak **32.4 GB** (13.6 GB headroom), decode ~72 tok/s short → 37 @256K.
- `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` — dense qwen3_5 + linear-attn, self-OptiQ
  3.97 bpw. Shipped config: **turboquant 4-bit KV**, `prefill_step_size 512`, 256K
  peak **43.3 GB** (only 2.7 GB headroom), decode **9.4 tok/s @256K**.

**The two winners have opposite bottlenecks.** Ornith is already fast + memory-light
(soft spot: prefill/TTFT at long ctx; memory has slack). Distill is slow *and*
memory-tight (both axes bite; decode is weight-bandwidth-bound at 27B dense). Levers
that help one barely touch the other — so each lever is scoped per model.

## Metrics & instrumentation

Report **prefill-TTFT and decode-tok/s SEPARATELY** (never the router's conflated
metric). `benchmark/bench/run_capacity.py` already emits, per rung: `prefill_tps`,
`decode_tps`, `system_peak_gb` (= `mx.get_peak_memory`, the prefill spike),
`retrieval_acc`, `fits`. That is the perf+memory+retrieval curve harness.

- **Memory** = `mx.get_peak_memory` (prefill spike), not RSS.
- **Length ladder** = `16384, 65536, 131072, 196608, 262144` (16K/64K/128K/192K/256K).
- **Quality gate metric** = execution-gated LCB pass@1 + convergence (coding), plus
  retrieval accuracy for the retrieval curve. Convergence rule:
  `converged = finish_reason=="stop" AND completion_tokens < thinking_budget`.

## Quality gate (hard constraint)

Every **lossy** lever must clear **≤5% quality drop, OFAT, measured at the deploy
length (256K)** — not just at 8K. Retrieval-depth and reasoning/coding curves stay
**separate**; retrieval effective-ctx threshold = accuracy ≥0.85. Quality is goal #1
and is never traded for speed/convergence. Lossless levers (APC, prompt-lookahead
under rejection sampling, the TQ kernel) skip the gate but still get a spot-check.

## Box strategy (apples-to-apples enforced)

- **M5 Max (remote, 256K-capable, quiet, deploy target) = the speed/memory track.**
  All box-sensitive numbers (prefill_tps, decode_tps, mx-peak) are single-box on M5,
  same-session, with a **freshly re-measured baseline alongside every test**. Each
  model's full length ladder runs on ONE box (M5) so the curve has no cross-box seam.
- **M2 Max (local laptop, ≤192K co-resident ~22 GB) = the quality-gate + build track.**
  Quality-gate benches (LCB pass@1, convergence, retrieval) are box-independent, so
  M2 runs them in parallel; this pipelines cleanly — **M2 decides whether a lossy
  lever clears ≤5% before M5 spends slow 256K hours quantifying its speed win.** M2
  also hosts TDD for the two builds (#4, #5).
- **One resident model per box, always** (RAM). Unload between models
  (`POST /v1/models/unload` + `pkill -f bench.run_*`). Never two big models per box.
- Cross-box speed/latency/memory comparisons are INVALID; only quality/retrieval
  transfer across boxes.

## The six levers

| # | Lever | Model(s) | Axis | Loss? | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | **APC prefix caching** (`APC_ENABLED=1`) | both | prefill/TTFT (agentic reuse) | **lossless (exact)** | flag-flip | plumbed end-to-end; needs multi-turn measurement harness |
| 2 | **Quantized-KV bit-width** (distill 4→3; Ornith fp16→4) | both | memory + decode@len | lossy → gate | config (registry variant) | uses `TurboQuantKVCache` |
| 3 | **KV eviction** (EpiCache / Pooling-SnapKV / Rotating-StreamingLLM) | both | memory + decode@len | lossy → gate | characterize existing | ⚠ hybrid arch caps savings; sinks+window risks retrieval |
| 4 | **Prompt/context-lookahead decoding** | distill | decode | lossless (rejection-corrected) | **build (spin-out)** | not in tree; the fresh angle for coding |
| 5 | **Unified TQ fused kernel** (MMA prefill 3–8× + T-tiling) | both | prefill/TTFT@len | lossless | **build (spin-out)** | spiked (`benchmark/spikes/`), not built |
| 6 | **MTP self-spec re-test** | distill only | decode | dist-preserving under sampling | config+measure | ⚠ **proven-negative prior** |

### Per-lever hypothesis / mechanism / kill-criterion

**#1 APC prefix caching** — *Hypothesis:* agentic coding re-sends the same
system+repo prefix every turn; caching prefill KV across requests turns a 256K
re-prefill (minutes of TTFT) into ~0 for the cached prefix. *Mechanism:* exact
block-level KV reuse (byte-identical; warm-to-warm deterministic). Plumbed:
`server/app.py:727` builds the manager from env; mlx-serve worker inherits env.
*Measurement:* NOT captured by single-request benches — need a repeated-prefix /
multi-turn harness measuring cold-vs-warm TTFT. *Kill:* n/a (lossless); ship if the
warm-TTFT win is material. Note the batch-non-invariance caveat (cold≠warm logits by
FP noise; not a correctness issue).

**#2 Quantized-KV bit-width** — *Hypothesis:* distill 4→3-bit turboquant KV frees
the scary 2.7 GB headroom AND streams fewer KV bytes per decode step (decode
speedup at length); Ornith fp16→4-bit trades free memory for the same decode win.
*Mechanism:* KV bytes are decode-bandwidth; fewer bits = fewer bytes read/token.
*Kill:* >5% LCB pass@1 drop or retrieval <0.85 at 256K.

**#3 KV eviction** — *Hypothesis:* dropping low-value KV shrinks footprint + decode
bandwidth. *Mechanism/caveat:* both models are **hybrid linear-attn** → only ~10/40
layers have a growing KV to evict, capping absolute savings; sinks+window
(StreamingLLM) drops the middle → **kills needle retrieval** (gated ≥0.85), so favor
pooling/SnapKV (attention-preserving) and EpiCache. *Kill:* retrieval <0.85 at
256K or >5% coding drop. (EpiCache ≤5% gate is the pre-existing live task.)

**#4 Prompt-lookahead decoding** — *Hypothesis:* for coding with a big repo in
context, generated tokens reuse identifiers/lines verbatim → high acceptance,
draft-model-free. *Mechanism:* copy candidate spans from prompt/context, verify in
one forward; rejection-corrected under sampling → distribution-preserving. Dodges
both MTP priors (no draft forward = no net slowdown; sampling-correct = lossless).
*Kill:* accepted-token rate too low to beat single-stream decode on distill.
**Own spec.**

**#5 Unified TQ fused kernel** — *Hypothesis:* MMA prefill path is 3–8× on long-ctx
prefill (spiked, exact). *Mechanism:* quantized-attention MMA (prefill) + T-tiling;
decode stays bandwidth-bound (TQ decode is currently ~2× slower than fp16 SDPA — NOT
a decode win). *Kill:* exactness regression or no prefill win on the target arch.
**Own spec** (design doc already exists: `docs/superpowers/specs/2026-06-17-unified-fused-quantized-kv-attention-design.md`).

**#6 MTP self-spec re-test (distill only)** — *Prior (must respect):* suffix/MTP/draft
is non-lossless on bf16 (verify-vs-decode kernel numerics flip greedy argmax) AND was
a **net slowdown** on this HW (campaign runs suffix-OFF). *Reframe:* the daily driver
samples (temp 0.3) → speculative *sampling* with rejection correction is
distribution-preserving by construction (a weaker criterion the lossless probe never
isolated). *MoE excluded* (batched verify activates the union of experts ≫8 → verify
disproportionately expensive). *Distill (dense)* is the plausible case. *Kill:* net
tok/s ≤ baseline at op-temp 0.3 (expected, given the prior — one honest shot).

## OFAT sequencing & dependencies

1. **Baseline (both models, M5):** the length-ladder perf+mem+retrieval curve at
   shipped config. *(running 2026-07-07)*
2. **#1 APC** — lossless, orthogonal, highest real-world ROI → measure early (needs
   the multi-turn harness). Its stored-KV precision inherits #2, so record #1 at
   baseline precision, then note the interaction.
3. **#2 quant-KV precision** — settle the KV precision per model BEFORE eviction
   (OFAT: vary one KV property at a time). M2 runs the quality gate; M5 the speed/mem.
4. **#3 eviction** — on the chosen KV precision, gated at 256K + retrieval curve.
5. **#4 vs #6 decode speculation** — alternatives for distill decode; compare on the
   same baseline, do NOT stack. #4 gets its build spec first.
6. **#5 kernel** — parallel track (Metal work, orthogonal to serving-config
   experiments); highest effort, its own spec.

## Deliverables & living-doc integration

- Per-lever rows appended to `docs/campaign-results.md` (never prune); worklist state
  in `docs/campaign-queue.md`; both kept current as work moves boxes.
- Each lossy lever logs: box + config + on/off + params + the bottleneck/mechanism
  (compute vs bandwidth, which memory pool) so verdicts are auditable and the
  *mechanism* transfers to future H200/B200 work.

## Findings so far (2026-07-07)

### Baselines (M5, shipped configs, `mx.get_peak_memory` = `server_peak_gb`)

`Ornith-1.0-35B-mlx-uniform-4bit` (fp16 KV) — VALIDATED (256K mx-peak 32.6 GB matches
the recorded 32.4 GB):

| ctx | mx-peak | prefill tok/s | decode tok/s | retrieval |
|---|---|---|---|---|
| 16K | 22.1 GB | 2478 | 71.7 | 1.0 |
| 64K | 24.2 GB | 1842 | 59.4 | 1.0 |
| 128K | 27.0 GB | 1360 | 52.1 | 0.2 ⚠ re-probe |
| 192K | 29.9 GB | 1006 | 44.4 | 1.0 |
| 256K | 32.6 GB | 794 | 37.9 | 1.0 |

Prefill degrades 3.1× over the range → the surface #5 (MMA kernel) targets. The
`retrieval=0.2 @128K` (neighbors 1.0) is a suspected flaky single-needle probe; a
128K-rung re-probe is queued.

`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (turboquant 4-bit KV) — recorded reference
(my-grid low-context run pending): 256K mx-peak **43.3 GB** (2.7 GB headroom),
decode **9.4 tok/s**, prefill ~124 tok/s @256K, retrieval 1.0. Memory-tight,
decode-slow (dense weight bandwidth).

### #1 APC — works, but agentic-only; measurement subtlety

- Built + plumbed + env-gated (`APC_ENABLED=1`), EXACT/lossless, optional SSD tier
  (`APC_DISK_PATH`). mlx-serve worker inherits the router env → flag-flip to enable.
- **Empirically active and fast: identical-request warm = 75× (45.9s → 0.61s) on
  distill.** So the hybrid-model path (recurrent-state snapshot restore + replay)
  works.
- **Reuse is prefix-boundary-gated.** A first A/B with *independent* divergent
  queries (`[sys+Q1]` vs `[sys+Q2]`) got 1.04× — the lone snapshot (end of
  `[sys+Q1]`) is not a usable prefix of `[sys+Q2]`, forcing full replay. That is NOT
  the agentic pattern. Real multi-turn shares a *growing* prefix ending at prior-turn
  snapshot boundaries → the reusable case (growing-conversation test in progress).
- Implication: #1's win is realized on **multi-turn agentic reuse**, not on
  single-shot benches — so its measurement harness must be a growing conversation,
  and its verdict depends on confirming per-turn TTFT collapse. Track the APC block
  pool's RAM cost (default 2048×16 = 32K tok, lazy KV alloc) against the 256K/co-res
  budget.

### Other confirmations

- **Speculative infra exists** (`mlx_vlm/speculative/drafters`, `split_qwen3_5_mtp`,
  `_get_draft_block_size_from_env`) — relevant to #4/#6.
- **KV-eviction menu already exists as cache classes** — `EpiCacheKVCache`,
  `BufferedRotatingKVCache`/`SlidingWindowCache` (StreamingLLM), `PoolingCache`
  (SnapKV-style), `TurboQuantKVCache` — so #3 is characterize-existing, not build.
- **Op note:** on-demand cold loads can exceed the router's 300s startup timeout when
  a shard is still downloading (hit on M2 distill; the caslca cache was partial). Warm
  caches load fine; pre-verify shard completeness before a timed run.
