# Plan: Long-Context Prefill Fix + Fused Quantized Attention Kernels

**Status:** Two distinct prefill walls, now separated by the 200K viability spike (§5,
2026-06-16):
- LOAD/MEMORY wall — **FIXED** (Fix A′, fork c3192a0 / stack e296c4f). The 200K OOM was a
  dense `[N, N]` causal mask (~40 GB), caused by suffix decoding silently disabling chunked
  prefill on qwen3_5 — KV-scheme-independent, which is why both uniform and TQ OOM'd
  identically. Re-enabling chunked prefill via a model policy fixed it; 200K now bounded
  ~47–48 GB, 16K needle PASS. This was NOT the KV scheme and NOT the §1 scores-matrix story.
- SPEED wall — **OPEN** (Fix B.2). `quantized_attention`'s Python K-tile loop is ≈ O(T²);
  16K prefill ≈ 228 s (~70 tok/s), so 200K projects to hours. 200K now fits but isn't
  interactive on TQ. The fast long-context path is uniform KV until B.2 lands.

SuffixDecoding v1.1 (commits 888f3b1 → 1c9f7a5) accelerates DECODE only; it is also what
triggered the LOAD wall regression (it passes a non-None draft_model).

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

## 1a. Update (2026-06-16): prefill SPEED is the blocker; suffix decoding is orthogonal

Two things happened since §1 was written, and together they move the bottleneck from memory
to prefill speed.

The Phase 1 memory fix works for its target (the TQ `dequantize()` spike is gone). The probe
ran clean to 80K; peak Metal memory rose from 33.65 GB at 8K to 39.44 GB at 80K. That curve
was first read as buffer-pool retention; the later 200K spike (§5 RESULTS) showed it is
actually the dense `[N, N]` causal mask growing as N² — a *separate* memory wall the Phase-1
fix never touched. See §5 for the correction.

What the probe exposed instead is a prefill-speed wall. Prefill throughput falls from 73
tok/s at 8K to 30 tok/s at 80K, and the per-token cost is *rising*, not holding flat. That
makes total prefill cost roughly O(T²): each new chunk of prompt attends to everything before
it through `quantized_attention`'s Python K-tile loop, so the loop does more work per query as
the context grows. Extrapolating the decline, a single 200K prefill projects to roughly
1.5–4+ hours. That is not interactive load time — it is a batch job.

SuffixDecoding v1.1 landed in the fork (commits 888f3b1 → 1c9f7a5) and is now enabled across
all models in `main_models.yaml` (`draft_kind: suffix`, `draft_block_size: 16`,
`suffix_min_match: 2`, `draft_cooldown: 2`). It is drafter-free speculative decoding: instead
of a separate draft model, it proposes candidate continuations from n-gram / prompt-lookup
matches against text already seen, then verifies them in one forward pass. On qwen3_5 it is
GatedDeltaNet-aware — the verify forward captures the GDN recurrent state (via
`capture_layer_ids=[]`) so that rejected drafts roll the recurrent state back correctly rather
than corrupting it. See `sketches/suffix-decoding-plan.md` and
`sketches/suffix-decoding-v1.1-plan.md` for that workstream.

So SuffixDecoding accelerates DECODE, the answer-generation phase that runs *after* the prompt
is loaded. It does nothing for PREFILL, the prompt-loading phase. The two phases are
independent, and the slow thing right now is prefill.

| Phase           | Wall                                                   | The fix                                     |
|-----------------|--------------------------------------------------------|---------------------------------------------|
| Prefill (LOAD)  | dense `[N, N]` causal mask (~40 GB @200K) when chunked prefill is off | qwen3_5 `chunked_prefill_policy` — **done** (§5 FIX) |
| Prefill (SPEED) | `quantized_attention` Python K-tile loop, ≈ O(T²)      | Fix B.2 (fused / T-tiled prefill kernel) — open |
| Decode          | autoregressive token-by-token generation               | SuffixDecoding v1.1 (already landed)        |

Note (post-200K-spike): the LOAD wall above is the dense-mask regression, not the
`quantized_attention` loop. It was discovered after §1a was first written; the
`quantized_attention` K-tile loop is the SPEED wall only. See §5 RESULTS / root cause.

None of this re-opens the §0 quality decision. TQ stays the locked KV scheme — the issue is
that its *current implementation* (the `quantized_attention` Python loop) is too slow for
interactive 200K+ contexts, not that the quant choice is wrong. The consequence is a priority
shift: Fix B.2 (fused / T-tiled `prefill_attention`) is promoted from an optional speed
upgrade to the critical-path unblocker for TQ at long context. Until B.2 lands, the only fast
long-context path is uniform KV through mlx_lm's fused
`quantized_scaled_dot_product_attention` — and that carries a long-context-quality cost at
4-bit, which is exactly why TQ was chosen in the first place. The owner's prior "230K loaded
in minutes" experience was on that uniform path, not on TQ.

---

## 2. The three fixes

| Fix | What | Scope | Effort | Critical path? |
|-----|------|-------|--------|----------------|
| **A** Dispatch rewire in `base.py` | Route TQ prefill fallback to `quantized_attention()` instead of `dequantize()` | TQ prefill | ~1 hour | Yes — **done** |
| **A′** qwen3_5 `chunked_prefill_policy` | Re-enable chunked prefill under suffix decoding → kill the dense `[N, N]` causal mask (the long-context LOAD/MEMORY wall) | all qwen3_5 long-context, KV-scheme-independent | ~37 LOC | Yes — **done** (fork c3192a0, stack e296c4f). Was the actual 200K OOM (§5), not the KV scheme |
| **B** Codec choice + fused prefill path | Make `mode` configurable; T-tiling fix in `prefill_attention` | TQ quality + speed | B.1 ~1 day; B.2 ~1 day Metal | B.1 yes (quality); B.2 **critical-path for TQ long-context PERFORMANCE** — confirmed by §5: 200K now FITS (Fix A′) but is hours-slow through the O(T²) `quantized_attention` loop, so TQ is not interactive at 200K until this lands |
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
  (`kv_quant_scheme: turboquant, kv_bits: 3`). Tests: 36/36 pass including
  `test_turboquant_prefill_no_dequantize_called`. Probe run 2026-06-16 (stopped at 80K —
  see §5 for data). No OOM to 80K. The 55–75 GB "256K peak" extrapolation here is
  **retracted**: that curve was the dense `[N, N]` causal mask growing as N², not the KV
  path, and the box is 68.7 GB not ~100 GB (§5, §6). Fix A removed the TQ `dequantize()`
  spike but not the mask wall — that took Fix A′.
- **Phase 1′ — Fix A′ (done).** qwen3_5 `chunked_prefill_policy` re-enables chunked prefill
  under suffix decoding, killing the dense `[N, N]` causal mask that was the actual 200K OOM
  (§5 RESULTS / root cause). Fork c3192a0, stack e296c4f. Validated: 200K prefill bounded
  ~47–48 GB (no OOM), 16K end-to-end needle PASS. This closes the long-context LOAD/MEMORY
  wall. The SPEED wall (Fix B.2) remains.
- **200K viability spike (§5) — DONE.** Result: both uniform-4bit and TQ OOM-crashed at 200K
  (~58–60 GB, jetsam) — and the cause was neither KV scheme but the dense causal mask above.
  The spike's three-case decision logic never applied. It did, however, settle Fix B.2's
  priority: with the mask wall fixed, 200K fits but is hours-slow through TQ
  `quantized_attention`, so B.2 is the interactive-TQ unblocker (Phase 3).
- **Phase 2 — codec quality (next).** Benchmark MSE vs Prod codec on the `benchmark/`
  harness (short coding + retrieval run). Add `mode` as a constructor parameter on
  `TurboQuantKVCache`; expose via `kv_quant_mode` in YAML. If Prod wins on quality: switch.
  Validate that `quantized_attention` with Prod keys produces correct results
  (`key_codec.score_prepared` on K-tiles — the non-fused path needs a numerical check before
  production use).
- **Phase 3 — Fix B.2 (priority confirmed by the §5 spike).** Fix T-tiling in
  `prefill_attention` so it handles 256K without the scores spike. Then Prod codec gets its
  dedicated fused kernel path. Validate numerics and memory. The §5 spike settled this: with
  the mask wall closed by Fix A′, 200K now fits but TQ prefill is hours-slow through the
  O(T²) `quantized_attention` K-tile loop (16K took ~228 s ≈ 70 tok/s). B.2 is the unblocker
  for an interactive TQ long-context daily driver; until it lands the fast long-context path
  is uniform KV.
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
- `benchmark/needle_256k.py` — single-shot needle test, and (to add) prefill-tps reporting for
  the §5 viability spike; written 2026-06-16.
- `benchmark/suffix_qwen_ab.py` — suffix A/B test: echo-vs-novel decode-rate contrast on the
  real 27B (does SuffixDecoding actually accelerate decode?).
- `eval_harness.py` — repo-root preload / probe / status helpers driving mlx-serve over HTTP.
- `sketches/suffix-decoding-plan.md`, `sketches/suffix-decoding-v1.1-plan.md` — the
  SuffixDecoding workstream (decode acceleration; orthogonal to prefill — see §1a).
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

No OOM. Peak grows ~0.7–0.9 GB per 8K-step. **This was originally read as Metal buffer-pool
retention — that was wrong.** The 200K spike (RESULTS below) confirms the growth is the dense
`[N, N]` causal mask: 39.44 GB peak − ~33 GB base = 6.4 GB = exactly 80K² bytes, an N²
curve, not the flat-to-linear pool curve assumed here. The "extrapolation fits if the box is
~100 GB / 0.85 × 100 GB" reasoning is also retracted — the machine is 68.7 GB (see §6), and
the mask, not the KV path, is what blows up. The probe ran clean only because it stopped at
80K, where the mask is still ~6 GB.

**Performance note:** prefill tok/s drops from 73 at 8K to 30 at 80K (roughly O(T) scaling
expected for the K-tile loop). The owner reports prior 230K loads took minutes with uniform
KV + the fused `mx.fast.scaled_dot_product_attention` Metal kernel. `quantized_attention`'s
Python K-tile loop is substantially slower. Fix B.2 (T-tiling in `prefill_attention`) is
therefore also a **performance fix**, not just optional correctness hygiene.

Probe stopped at 80K to avoid the multi-hour tail. The 200K viability spike (RESULTS below)
resumed it and turned up the dense-mask OOM, which this 80K probe was already showing as the
N² memory growth — it just hadn't grown large enough at 80K to crash.

### Uniform vs TQ 200K viability spike (next action)

The one experiment that decides everything else. It tells us whether TQ-via-`quantized_attention`
is usable at 200K as-is, or whether Fix B.2 is a hard prerequisite — and whether uniform-4bit
is the pragmatic interim daily driver.

**Goal.** For the *same* Qwen weights under two KV schemes, measure three things at 200K:
- prefill tok/s (the headline — does TQ confirm the ~10–15 tok/s / multi-hour projection?);
- peak memory (does uniform OOM at 200K even after the buffer-pool cap from commit bf7b05f?);
- needle retrieval (does 4-bit uniform actually retain the needle at 200K, or does TQ's
  long-context quality edge show up here?).

Holding the weights fixed isolates the KV-scheme variable, which is the whole point.

**Setup.** Add a TEMPORARY twin entry to `main_models.yaml`:

```yaml
  - name: Qwen3.6-27B-UD-MLX-6bit-uni4
    type: vision
    on_demand: true
    hf_path: unsloth/Qwen3.6-27B-UD-MLX-6bit   # same weights as the TQ entry
    max_kv_cache_size: 262144
    kv_quant_scheme: uniform                    # the only difference vs the TQ entry
    kv_bits: 4
    prefill_step_size: 512
    quantized_kv_start: 0
    enable_thinking: true
    # same suffix params as every other entry (draft_kind: suffix, etc.)
```

One restart then serves BOTH the TQ entry and this uniform twin serially — the manager swaps
on demand, one model at a time, so there is no double-load. Note the existing
`Qwen3.6-27B-MLX-8bit` and `Qwen3.6-27B-OptiQ-4bit` entries are already uniform, but they are
DIFFERENT weights, so they confound the weight variable with the KV-scheme variable and cannot
answer this question. Alternative if you prefer not to add an entry: flip the existing TQ entry
to uniform, restart, test, then flip it back and restart again.

**Pre-flight (operating rules).** Confirm there are NO stray Python eval/generate/validate
processes still running; serve exactly ONE model at a time; and make sure nothing else hits
`:8000` during the run. Concurrent load contaminates both the memory and the timing numbers.

**Run order.** Uniform FIRST. It is the fast positive control — it de-risks the harness (proves
the needle script, timing, and memory readout all work) before committing to the slow TQ run.
Then TQ.

**Command:**
```bash
uv run python benchmark/needle_256k.py --model <name> --ctx 200000
```
The script needs a small addition: report prefill tok/s as `prompt_tokens / (wall_s −
predicted_ms/1000)`, mirroring how `validate_256k.py` derives it (subtract the decode time from
wall time to isolate prefill). Keep `max_tokens` small so decode and SuffixDecoding don't skew
the prefill timing.

**TQ early-abort.** The per-chunk rate is visible within ~1 minute of the TQ run. If it confirms
the ~10–15 tok/s projection (i.e. hours to complete), record the rate and kill the run — there
is no need to sit through a full 200K prefill to make the decision.

**Decision logic.**
1. Uniform is fast + fits + retrieves the needle → uniform-4bit is the pragmatic 200K daily
   driver TODAY; TQ becomes a quality upgrade gated on Fix B.2.
2. TQ prefill is ~hours → confirms TQ-via-`quantized_attention` is not viable interactively;
   Fix B.2 is promoted to the critical-path unblocker.
3. Uniform OOMs at 200K but TQ fits → memory (and quality) favor TQ; Fix B.2 is critical for
   speed, or lower `max_kv_cache_size` to trade context for headroom.

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

### RESULTS (2026-06-16): both KV schemes OOM at 200K — neither the spike's premise

Ran `benchmark/needle_256k.py --ctx 200000` on Qwen3.6-27B-UD-MLX-6bit, same weights, two KV
schemes (temporary `-uni4` twin entry, since removed; surgical manager restart to pick up the
YAML).

| KV scheme        | result      | live peak | time to crash | needle | prefill tok/s |
|------------------|-------------|-----------|---------------|--------|---------------|
| uniform, kv_bits=4 | OOM crash | ~58.6 GB  | ~35 s         | none   | none          |
| TQ, kv_bits=3      | OOM crash | ~60.1 GB  | ~20–30 s      | none   | none          |

Both worker subprocesses were OS-killed (jetsam, `<defunct>`) — true *system-RAM* exhaustion,
not a graceful Metal-budget abort. Neither retrieved the needle; neither produced a
prefill-tps number (both crashed mid-prefill, before decode). **The §5 three-case decision
logic did not apply — none of its cases predicted "both schemes OOM."** Holding the weights
fixed did isolate the KV variable, and the answer was that the KV variable was not the cause.

### CONFIRMED ROOT CAUSE: suffix decoding disabled chunked prefill → dense [N, N] causal mask

The 200K OOM was **not** the KV scheme, and **not** the §1 "uniform scores-matrix spike"
story. It is a regression from enabling drafter-free suffix decoding on Qwen3.6 (commit
1cb9da8), and it is KV-scheme-independent — which is exactly why both schemes OOM identically
at the same ~58–60 GB.

Chain:
1. Drafter-free suffix decoding passes a **non-None `draft_model`** (a `SuffixDecodingProposer`).
2. `_chunked_prefill_enabled` (`ar.py`) falls back to `return draft_model is None` unless the
   model exposes a `chunked_prefill_policy`. **qwen3_5 had no policy** → returns False →
   chunked prefill DISABLED.
3. → the **full prompt** runs in one forward pass.
4. → qwen3_5 builds its own mask over the full sequence: `create_causal_mask(N, offset)` →
   a dense bool `[N, N+offset]` causal mask. At N=200K that is ~40 GB → system OOM.

**Quantitative clincher:** the Phase-1 80K peak of 39.44 GB minus the ~33 GB base = 6.4 GB =
exactly 80K² bytes, i.e. a full `[80K, 80K]` mask. The earlier conclusion that this curve was
buffer-pool retention (§1a, §5 Phase-1 note) was wrong — it was the mask growing as N². The
gemma data point fits the same model: `gemma-4-31b` ran 100K at ~40 GB RSS = a 10 GB
`[100K, 100K]` mask plus a lighter weights base, so it fit by luck of being smaller — gemma
would also OOM at 200K. Pre-suffix, `draft_model` was None → chunking ON → a tiny per-chunk
mask `[512, offset]`, consistent with the owner's prior "230K loaded in minutes."

This means there are **two distinct walls**, and they were being conflated:

- **(a) the long-context LOAD/MEMORY wall** — the dense `[N, N]` causal mask, fatal above
  ~150K. Caused by chunked prefill being switched off, not by the KV quant or the attention
  kernel. FIXED below by re-enabling chunked prefill.
- **(b) the long-context SPEED wall** — the O(N²) `quantized_attention` Python K-tile loop
  (Fix B.2 / T-tiled `prefill_attention`). STILL OPEN.

### FIX (shipped + validated): re-enable chunked prefill on qwen3_5 — no new kernel

The fix is a `chunked_prefill_policy` added to the qwen3_5 `LanguageModel` (mirroring gemma4's)
that keeps chunked prefill **ON** for `draft_kind == "suffix"`. This is safe because suffix
captures the GatedDeltaNet recurrent state at verify/decode time on the *post-prefill* cache:
chunked prefill produces the identical end-of-prompt state as one full-prompt forward, so the
capture is unaffected. **No new mask kernel was needed** — the per-chunk mask is already tiny
(`[512, offset]`, ~0.1 GB). `max_kv_cache_size` does not help here: it caps KV storage, not the
prompt-length mask.

Shipped: fork `ivan-avramov/mlx-vlm` @ **c3192a0**; stack submodule bumped (stack commit
**e296c4f**). Validated on the real 27B (Qwen3.6-27B-UD-MLX-6bit, TQ kv_bits=3):

- **200K prefill no longer OOMs** — memory bounded ~47–48 GB for >2 min (vs the pre-fix
  60 GB crash at ~25 s).
- **16K end-to-end needle PASS** (retrieved `XKRYPTO9F2`), prefill ~70 tok/s, peak 35 GB,
  suffix decode intact (~9 tok/s).

TDD: a dispatch test (chunked prefill now enabled for suffix on qwen3_5) plus an equivalence
test (chunked 3-tok-step prefill matches one full-prompt forward on the GDN recurrent state +
next-token logits, atol 1e-4). No regressions across the suffix / mtp / dispatch suites.

The MEMORY wall (a) is now closed at 200K. The SPEED wall (b) is what's left: 200K now FITS
but is slow. 16K prefill took ~228 s (≈ 70 tok/s), so 200K projects to hours through the
`quantized_attention` K-tile loop. The fast long-context path remains uniform KV. Fix B.2
(T-tiled `prefill_attention`) is therefore the unblocker for an *interactive* TQ long-context
daily driver.

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
- **Machine RAM contradiction (RESOLVED):** the box is 68.7 GB unified (confirmed via
  `/v1/status` `total_gb`), the ~64 GB-class M2 Max — NOT the ~100 GB the §5
  extrapolation assumed. The "0.85 × 100 GB" note in §5 was simply wrong. The Metal/RAM
  ceiling at `memory_limit_frac` 0.85 is ~58 GB. 200K prefill did not fit either KV scheme as
  originally configured (both OOM-crashed at ~58–60 GB; see §5 RESULTS). The real cause turned
  out not to be the §5 extrapolation tail at all — it was a dense upfront causal mask (§5 root
  cause), KV-scheme-independent.
- **Suffix-vs-prefill (don't misread the perf story):** SuffixDecoding v1.1 accelerates
  DECODE only — it cannot cut long-context LOAD (prefill) time. But it is not inert on
  prefill either: enabling it passed a non-None `draft_model`, which silently disabled
  chunked prefill on qwen3_5 and created the dense `[N, N]` causal mask that was the 200K
  LOAD wall (§5 root cause). That wall is now fixed by re-enabling chunked prefill (Fix A′),
  not by speculative decoding. The remaining prefill SPEED wall is Fix B.2.
