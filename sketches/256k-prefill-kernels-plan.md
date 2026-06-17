# Plan: Long-Context Prefill Fix + Fused Quantized Attention Kernels

**Status:** Phase 1 complete (2026-06-16). Probe stopped at 80K context (10/32 steps); needle test pending. Other optimizations planned before resuming Phase 2+.

**Goal of the work:** make long-context (up to 256K) **prefill** work within ~50 GB on an
M2 Max (64 GB), for both TurboQuant (TQ) and uniform quantized KV caches, by replacing the
memory-spiking prefill attention paths with chunked + fused (flash-style) kernels.

---

## 0. Why this exists (the larger goal)

Selecting the best-quality **local coding + reasoning** model that runs at **full 256K
context** under ~50 GB on an M2 Max 64 GB, served via the local stack. Decisions already
locked (do not re-litigate):

- **KV scheme = TurboQuant** (chosen for long-context quality; research shows rotation +
  Lloyd-Max codebooks give ~FP16 quality at 3–3.5 bits, well above uniform-4bit on
  long-context retrieval). Uniform is *not* the daily driver, but we still want a proper
  fused uniform prefill kernel (Fix C) for completeness / fallback / possible upstreaming.
- **Qwen3.6-27B** = the 256K daily driver (linear-attention DeltaNet arch → sub-linear KV).
  Quant ladder to evaluate later: UD-4bit / OptiQ-4bit / UD-6bit / MLX-8bit, all on TQ KV.
- **`gemma-4-26b-a4b-it-8bit`** (MoE) = fast short-context vision generalist (sliding-window
  attention; not the 256K model).
- Dense Gemma-4-31B = **dropped** (slow + Qwen beats it; full-attention KV).
- **Vision is required** (documents/screenshots) → the daily driver must run through
  **mlx-vlm** (vision), not a text-only mlx-lm path. Vision quality = take official
  benchmarks; do not self-test vision.
- Preference under memory pressure: **lower `max_kv_cache_size` to preserve quality**, rather
  than drop to a worse quant.

Hardware/limits: M2 Max, 68.7 GB unified; mlx-serve sets `memory_limit_frac` default 0.85
(≈ 58 GB hard Metal limit). Target peak < 50 GB at 256K.

---

## 1. The problem (verified diagnosis)

A single 250K-token prefill **OOMs** both candidate models on the current stack:
- `Qwen3.6-27B-UD-MLX-6bit` → `[METAL] Command buffer execution failed: Insufficient Memory
  (kIOGPUCommandBufferCallbackErrorOutOfMemory)`.
- `gemma-4-26b-a4b-it-8bit` → the `Impacting Interactivity` variant of the same.

The KV cache *storage* is small (sub-linear attention: Qwen DeltaNet ~5 GB, Gemma
sliding-window ~3 GB at 256K, computed from configs at `kv_bits=4`). **The wall is the
prefill attention compute path, not KV storage.** Two distinct spike mechanisms:

### Uniform quantized KV (`kv_quant_scheme: uniform`)
Attention runs through mlx_lm's **`quantized_scaled_dot_product_attention`**
(`.venv/.../mlx_lm/models/base.py:64`, dispatched from `scaled_dot_product_attention` at
`base.py:108` when the cache has `.bits`). It reads quantized K/V directly via
`mx.quantized_matmul` (so **no full KV→fp16 dequant**) **but it is a manual, non-flash
attention**: it materializes the entire `scores = [B, heads, L, context]` matrix, runs
`mx.softmax`, then `mx.quantized_matmul` against V. At long prefill the **scores matrix is
the spike** (e.g. `[512 × 250K] × 24 heads × 4 B ≈ 12 GB/layer` transiently).

### TurboQuant KV (`kv_quant_scheme: turboquant`)

The dispatch lives in `mlx_vlm/models/base.py:scaled_dot_product_attention`. For L > 1
(prefill) with a `TurboQuantKVCache`, the call sequence was:

1. `cache.prefill_attention()` tried first. With `kv_bits=3`, `_ensure_codecs` hardcodes
   `mode="mse"` for both key and value → both are `_TurboQuantMSECodec`.
   `prefill_attention()` requires `_TurboQuantProdCodec` keys and returns `None` immediately
   when it doesn't find them. **This branch is permanently unreachable at runtime under the
   current codec configuration.**
2. The fallback was `cache.dequantize()` → full fp16 KV temporary of shape `[B, H, T, D]` →
   the spike (~20 GB at 256K on Gemma-4-31B-class; documented in
   `memtest_prefill_exercise/turboquant_debug_spike.md`).

`TurboQuantKVCache.quantized_attention()` (in `turboquant.py`) was already implemented with
a proper chunked approach — outer Q-block loop (16 queries at a time,
`prefill_query_block_size = 16`), inner K-tile loop (2048 tokens at a time,
`prefill_key_chunk_size = 2048`), online softmax (flash-style) with
`mx.eval(output, normalizer, max_score)` between K-tiles, and peak memory per tile around
16 MB instead of ~4 GB/layer. It was never called from any dispatch path. That was the bug.

The fix (commit c72a82c, 2026-06-16) routes the prefill fallback from `cache.dequantize()`
to `cache.quantized_attention()`. The chunked prefill loop in `ar.py` (lines 506–581, which
already called `mx.clear_cache()` between input chunks) was not part of this fix — it
pre-existed.

Reference doc with the original TQ diagnosis:
**`memtest_prefill_exercise/turboquant_debug_spike.md`** — this plan extends it.

---

## 2. The three fixes

| Fix | What | Scope | Effort | Critical path? |
|-----|------|-------|--------|----------------|
| **A** Dispatch rewire in `base.py` | Route TQ prefill fallback to `quantized_attention()` instead of `dequantize()` | TQ prefill | ~1 hour | Yes — **done** |
| **B** Codec choice + optional fused path | Make `mode` configurable; optional T-tiling fix in `prefill_attention` | TQ quality + speed | B.1 ~1 day; B.2 ~1 day Metal | B.1 yes (quality); B.2 optional (also a **performance** fix — restores fused Metal path) |
| **C** Fused uniform prefill kernel | Flash kernel reading mlx affine-quant KV directly | uniform-only | ~1–3 days (Metal) | No — completeness/fallback/upstream |

All edits land in the **fork at `../mlx-vlm`** (see §4 workflow), never directly in the
submodule `src/mlx-vlm`.

### Fix A — dispatch rewire in `base.py` (**done**, commit c72a82c)

**Where:** `../mlx-vlm/mlx_vlm/models/base.py:scaled_dot_product_attention`.

**Change:** for L > 1 with a `TurboQuantKVCache`, the fallback now calls
`cache.quantized_attention(q, mask)` instead of dequantizing the full KV to fp16.
`quantized_attention()` loops over 16-query blocks and 2048-token K-tiles with online
softmax, capping peak memory at ~16 MB per tile.

The chunked prefill loop in `ar.py` (lines 506–581) already existed and already called
`mx.clear_cache()` between input chunks. No changes were needed there.

**Status:** done. Tests: 36/36 pass including
`test_turboquant_prefill_no_dequantize_called`.

### Fix B — codec choice and optional fused path (next)

Two sub-steps, separable:

**B.1 — make `mode` a constructor parameter on `TurboQuantKVCache`** (no Metal work):

Currently `_ensure_codecs` hardcodes `mode="mse"` regardless of configuration. Making it
a parameter (constructor + YAML passthrough via `kv_quant_mode`) lets the stack switch to
`mode="prod"` (`_TurboQuantProdCodec` keys). The `quantized_attention()` K-tile path calls
`key_codec.score_prepared` on each tile, which Prod implements — so Prod keys work through
the same dispatch that MSE keys use now. This is a quality experiment, not a correctness
fix. Whether Prod wins on quality at 3 bits needs benchmark validation: Prod uses 2-bit MSE
coarse + 1-bit binary projection for residual direction, which structurally should be better
on long-context retrieval but is untested here.

**B.2 — fix the scores-matrix spike in `prefill_attention`** (optional, ~1 day Metal):

`prefill_attention` (the fused Prod-key path) materializes `[B*H*R, L, T]` scores all at
once. At 256K with L=512 query chunks that is ~16.8 GB per softmax call — a spike. Fixing
it requires tiling the T dimension in `prefill_attention`, which is Metal work. Once done,
Prod codec gets its dedicated fast fused path back and `quantized_attention` is no longer
needed for the Prod case.

Until B.2 lands, enabling Prod keys routes through `quantized_attention` (B.1), not
`prefill_attention`. That is correct and memory-safe; it just does not use the fused kernel.

### Fix C — fused uniform (affine-quant) prefill attention kernel (added scope)

**Where:** the dispatch in `scaled_dot_product_attention` (`base.py:108`) for uniform caches
(`seqlen_q > 1`). Today that path calls `quantized_scaled_dot_product_attention` (`base.py:64`)
which materializes the full scores matrix.

**Design:** a flash-attention prefill kernel reading mlx affine-quant KV
(`group_size`, `bits`, per-group `scales`/`biases`) directly, with online softmax over K-tiles
so the `[L × context]` scores matrix is never materialized. The per-tile dequant is mlx affine
(`x = q * scale + bias` per group) — simpler than TQ, no rotation needed.

Two implementation options:
1. **In-fork kernel** invoked from the model's attention (patch `base.py`'s dispatch). Fastest.
2. **Upstream-friendly**: implement as a drop-in `quantized_scaled_dot_product_attention`
   and consider contributing to mlx_lm/mlx. Before building, check whether `mx.fast` has
   gained a native quantized SDPA (`mx.core.fast` currently exposes only
   `scaled_dot_product_attention`); prefer upstream if it lands.

Numerics: validate against the existing `quantized_scaled_dot_product_attention` on short prompts.

C is not on the critical path to the TQ daily driver, but it removes the uniform scores spike
and is the cleaner long-term/upstream artifact.

---

## 3. Execution phases

> After every fork change: commit + push to `origin/main`, sync the submodule, restart the
> stack (see §4), then run the probe (§5).

- **Phase 1 — Fix A (done).** Dispatch rewire in `base.py` + YAML config
  (`kv_quant_scheme: turboquant, kv_bits: 3`). Probe to 256K must confirm peak < 50 GB,
  flat memory curve, and needle retrieval. Tests: 36/36 pass including
  `test_turboquant_prefill_no_dequantize_called`. Probe run 2026-06-16 (stopped at 80K —
  see §5 for data). No OOM. Memory curve flat-to-linear; peak grows ~0.7–0.9 GB per
  8K-step after the pool cap engages. Extrapolated 256K peak: 55–75 GB (see §5). Needle
  test (`benchmark/needle_256k.py`) written but not yet run; will run after other
  optimizations land.
- **Phase 2 — codec quality (next).** Benchmark MSE vs Prod codec on the `benchmark/`
  harness (short coding + retrieval run). Add `mode` as a constructor parameter on
  `TurboQuantKVCache`; expose via `kv_quant_mode` in YAML. If Prod wins on quality: switch.
  Validate that `quantized_attention` with Prod keys produces correct results
  (`key_codec.score_prepared` on K-tiles — the non-fused path needs a numerical check before
  production use).
- **Phase 3 — optional speed (Fix B.2).** Fix T-tiling in `prefill_attention` so it handles
  256K without the scores spike. Then Prod codec gets its dedicated fused kernel path.
  Validate numerics and memory.
- **Phase 4 — model/quant bake-off (unchanged).** With TQ KV working, evaluate Qwen weight
  quants (UD-4 / OptiQ-4 / UD-6 / MLX-8) for quality on the `benchmark/` harness (coding +
  reasoning) + the owner's real tasks; capture decode tok/s. Pick the best-quality quant that
  fits and runs.
- **Phase 5 — decision (unchanged).** Daily driver = chosen Qwen quant + TQ + 256K; MoE-8bit
  kept as the fast short-context companion. Update `main_models.yaml` + the eval plan doc.

---

## 4. Repo workflow, locations, and config

**Fork ↔ submodule sync (do all edits in the fork):**
```bash
# edit + test in the fork
cd ../mlx-vlm                       # git@github.com:ivan-avramov/mlx-vlm.git, branch main
#   ... make changes, run tests: cd mlx_vlm && pytest -s ./tests/test_generate.py ...
git commit -am "fix: <A|B|C> ..."   # end commit msgs per repo convention
git push origin main                # work SSH key can push this fork's main
# pull into the stack
cd ../mlx_local_stack
git submodule update --remote src/mlx-vlm   # runserver.sh also auto-syncs on start
# restart stack to load new code + config
./runserver.sh                      # or /mlx start
```

**Key files:**
- `../mlx-vlm/mlx_vlm/models/base.py` — prefill dispatch (`scaled_dot_product_attention`);
  Fix A landed here. Fix C wiring also goes here.
- `../mlx-vlm/mlx_vlm/turboquant.py` — TQ codecs + kernels; `quantized_attention` (now
  active for MSE prefill); `prefill_attention` (Prod path, needs T-tiling fix before use at
  256K).
- `../mlx-vlm/mlx_vlm/generate/ar.py` — chunked prefill loop (lines 506–581, pre-existing).
- `../mlx-vlm/mlx_vlm/models/{qwen3_5,gemma4}/language.py` — attention call sites (Fix C
  wiring reference).
- `.venv/.../mlx_lm/models/base.py:64,108` — uniform `quantized_scaled_dot_product_attention`
  + dispatch (Fix C reference).
- `.venv/.../mlx_lm/models/cache.py:232` — `QuantizedKVCache`.
- `memtest_prefill_exercise/turboquant_debug_spike.md` — diagnosis + A/B kernel sketches.
- `benchmark/validate_256k.py` — the 8K-step memory-curve probe (§5).
- `main_models.yaml` — per-model serving config.

**`main_models.yaml` config for TQ on Qwen (Phase 1, already active):**
```yaml
  - name: Qwen3.6-27B-UD-MLX-6bit
    type: vision
    on_demand: true
    hf_path: unsloth/Qwen3.6-27B-UD-MLX-6bit
    max_kv_cache_size: 262144
    kv_quant_scheme: turboquant
    kv_bits: 3                      # TQ native (3-bit packed); MSE codec
    prefill_step_size: 512
    quantized_kv_start: 0
    enable_thinking: true
    # cache_limit_gb: 48            # optional belt-and-suspenders pool bound
```
`process_manager.py` already forwards `--cache-limit-gb` / `--memory-limit-frac` /
`prefill_step_size` to the subprocess.

---

## 5. Verification (run after each fix)

**8K-step memory-curve probe** (already written, pure HTTP, sequential — nothing else may hit
the stack while it runs):
```bash
uv run python benchmark/validate_256k.py \
  --models Qwen3.6-27B-UD-MLX-6bit --step 8000 --max 256000
# records per-step: prompt_tokens, peak_mem_gb, sys_used_gb, prefill_tps, decode_tps
# -> eval_results/ctx_memory_curve.jsonl ; stops at the OOM ceiling
```
Expected post-fix curve (chunked/fused, sub-linear attention): roughly flat, peak < 50 GB
at 256K, no OOM. Pre-fix it OOMed around ~96–250K.

**Phase 1 probe results (2026-06-16, Qwen3.6-27B-UD-MLX-6bit, TQ kv_bits=3):**

| ctx   | prompt_tok | peak (MLX Metal) | Δ/8K  | prefill tok/s |
|-------|-----------|-----------------|-------|---------------|
| 8K    | 8,215     | 33.65 GB        | —     | 73            |
| 16K   | 15,428    | 33.96 GB        | +0.31 | 63            |
| 24K   | 22,509    | 34.35 GB        | +0.39 | 57            |
| 32K   | 29,775    | 34.83 GB        | +0.48 | 51            |
| 40K   | 37,105    | 35.41 GB        | +0.58 | 46            |
| 48K   | 44,525    | 36.11 GB        | +0.70 | 42            |
| 56K   | 52,049    | 36.97 GB        | +0.86 | 38            |
| 64K   | 60,056    | 37.69 GB        | +0.72 | 35            |
| 72K   | 67,050    | 38.59 GB        | +0.90 | 32            |
| 80K   | 74,471    | 39.44 GB        | +0.85 | 30            |

No OOM. Peak grows ~0.7–0.9 GB per 8K-step after the initial ramp; the per-step increment
oscillates around ~0.85 with slow upward drift (Metal buffer-pool retention, partially
capped by the auto-derived `cache_limit`). Linear extrapolation → ~58 GB at 256K. Pessimistic
quadratic → ~75 GB. Both are within the 85 GB Metal budget on this machine
(memory_limit_frac=0.85 × 100 GB).

**Performance note:** prefill tok/s drops from 73 at 8K to 30 at 80K (roughly O(T) scaling
expected for the K-tile loop). The owner reports prior 230K loads took minutes with uniform
KV + the fused `mx.fast.scaled_dot_product_attention` Metal kernel. `quantized_attention`'s
Python K-tile loop is substantially slower. Fix B.2 (T-tiling in `prefill_attention`) is
therefore also a **performance fix**, not just optional correctness hygiene.

Probe stopped at 80K to avoid the multi-hour tail. Single-shot needle test at 256K
(`benchmark/needle_256k.py`) will provide both the OOM proof and context-use check in one
request when resumed.

**Correctness (do not trust "didn't OOM" alone):**
- Numerics: compare `quantized_attention` output vs the dequant/SDPA path on a short prompt
  (max abs diff small). Already covered by the new test.
- Needle-in-haystack at 256K: insert a unique token at ~0.7 depth, confirm the model retrieves
  it (context is actually used, not just non-OOM). Script: `benchmark/needle_256k.py`
  (written 2026-06-16; not yet run).
- Multi-turn: verify prefix caching still works after chunked prefill.

**Perf:** record prefill tok/s and decode tok/s from the probe. Fix B.2 (if built) should
improve prefill vs the K-tile loop in `quantized_attention`. TQ decode speed vs uniform is
informational (TQ is chosen regardless).

---

## 6. Risks / open questions

- **`prefill_attention` not usable at 256K without T-tiling fix:** the existing
  `prefill_attention` (Prod key path) materializes `[B*H*R, L, T]` scores all at once. At
  256K with L=512 query chunks: ~16.8 GB per softmax call. Must fix T-tiling (Fix B.2) before
  enabling Prod codec with the fast fused path.
- **`quantized_attention` with Prod codec untested:** if `mode="prod"` is enabled (Fix B.1),
  the K-tile dispatch calls `key_codec.score_prepared` with Prod-state K-tiles. The non-fused
  `score_prepared` path (for L > 1) uses einsum against dequantized signs — needs a validation
  run to confirm correctness before switching production.
- **MSE vs Prod quality unknown:** Prod uses 2-bit MSE coarse + 1-bit binary projection for
  residual direction and structurally should be better at 3 bits, but has not been benchmarked
  on this stack. Phase 2 settles the question.
- **Prefix-cache breakage** from chunked prefill (verify multi-turn; the loop in `ar.py`
  pre-existed, so this may already be handled).
- **Upstream moving target:** mlx/mlx_lm may add a native quantized/flash SDPA — check before
  investing in Fix C; prefer upstream if it lands.
- **TQ bit width:** TQ's packed format unpacks `10 × 3-bit` indices per uint32 → `kv_bits: 3`.
  Confirm per served model.
- **head_dim assumptions** for the FWHT butterfly in `prefill_attention` (powers of two: Gemma
  512/256, Qwen 256) — re-check per model before enabling B.2.
- **memory_limit_frac (0.85 ≈ 58 GB):** keep target < 50 GB for headroom; raising the frac
  risks system OOM.
