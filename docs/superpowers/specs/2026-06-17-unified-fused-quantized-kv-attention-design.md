# Unified Fused Quantized-KV Attention Kernel for Apple Silicon (TurboQuant)

**Date:** 2026-06-17
**Status:** Approved design, pre-implementation.

---

## 1. Goal and non-goals

### Goal

Replace TurboQuant's collection of quantized-KV attention kernels with one parameterized fused flash-attention Metal kernel (built through `mx.fast.metal_kernel`) that covers:

- both prefill (query length `L > 1`) and decode (`L = 1`), and
- both the MSE and Prod codecs.

The kernel is optimized against three axes, in the priority order the owner set:

1. Model output **quality**.
2. **Generality** across models — no per-model hardcoding; model-specific quirks plug in architecturally.
3. **Runtime speed** on Apple Silicon specifically.

Target workload: multi-turn chat with session prefix-KV-caching, context growing toward 200K. Per-turn cost is a small incremental prefill of the new tokens plus the decode of the reply, both running over a large cached KV. The expensive operation is reading and scoring against that large cache, not re-prefilling it.

### Non-goals

- Making a single-shot 200K prefill interactive. The MLP + GatedDeltaNet forward is a ~31-minute floor at 200K single-prefill. With prefix caching that cost amortizes across turns and never appears as a single wait, so it is out of scope here.
- Supporting the Polar codec. It is a documented extension point only.
- Changing the codec math or quality. This work wires up and fuses existing codecs; it does not alter how they quantize.

---

## 2. Background: current state

### Model

`Qwen3.6-27B-UD-MLX-6bit`:

| Property | Value |
|---|---|
| `head_dim` | 256 (power of 2) |
| `num_attention_heads` | 24 |
| `num_key_value_heads` | 4 (GQA ratio `R = 6`) |
| Layers | 64 |
| `full_attention_interval` | 4 |
| Full-attention layers | 16 — use `KVCache`, TQ-quantizable |
| GatedDeltaNet linear layers | 48 — use `ArraysCache`, not attention |

Live KV config: `kv_quant_scheme: turboquant`, `kv_bits: 3`.

### Codec wiring

`TurboQuantKVCache._ensure_codecs` and `BatchTurboQuantKVCache._ensure_codecs` both hardcode `mode="mse"` for the key and value codecs. (`BatchTurboQuantKVCache._ensure_codecs` reaches MSE by delegating to a temporary `TurboQuantKVCache`.) So `kv_bits=3` resolves to MSE key + MSE value.

The Prod codec, the Polar codec, and a large set of Prod / split / multi-query kernels exist in the fork but are dead code under the live wiring — none of them is reachable. A repo test asserts that for `kv_bits=3` (MSE), `prefill_attention` always returns `None`.

### Dispatch

`mlx_vlm/models/base.py`, function `scaled_dot_product_attention(queries, keys, values, cache, scale, mask)`, routes a `TurboQuantKVCache` as follows:

- query length `== 1` → `cache.decode_attention(...)`.
- otherwise → `cache.prefill_attention(...)`, which returns `None` for the MSE codec, then falls through to `cache.quantized_attention(...)`.

`qwen3_5` and `gemma4` both call this same wrapper, imported from `..base`. A `BatchTurboQuantKVCache` takes a different route entirely: `base.py` calls `cache.dequantize(...)` and hands the full-precision result to `mx.fast.scaled_dot_product_attention`.

### `decode_attention` (`L = 1`)

Already a fused flash kernel for MSE:

- single-pass `_fused_mse_decode_kernel` when total tokens ≤ 2048;
- otherwise a 2-pass flash kernel (`_fused_mse_decode_2pass_1_kernel` / `_fused_mse_decode_2pass_2_kernel`) that splits KV across blocks. The block count follows a ladder of 64 / 128 / 256 / 512, selected by the token-count thresholds 8192 / 32768 / 65536.

Both do in-kernel dequant, online softmax, and no score materialization.

### `quantized_attention` (the `L > 1` prefill fallback)

A Python K-tile loop. For each query block (`prefill_query_block_size = 256` after a prior fix) and each key chunk, it computes scores through codec ops, applies the mask, and merges with an online softmax, with an `mx.eval` GPU sync per (q-block × k-tile). It is not a fused kernel.

### `prefill_attention`

A partial fused attempt. It only supports the Prod-key codec (returns `None` for MSE) and materializes the full `[B, H, R, L, T]` score tensor to global memory before a separate value kernel. No T-tiling.

---

## 3. Problems

1. **Prefill (`L > 1`) under MSE has no fused kernel.** It runs the Python K-tile loop with per-tile `mx.eval` syncs.

2. **GQA bandwidth bug in decode.** The decode kernels launch one threadgroup per query-head and map `bh = bqh / RepeatCount`, so all `R` GQA query-heads of a kv-head re-read the same packed K/V from DRAM. That is `R = 6×` redundant reads for Qwen. Decode at long context is bandwidth-bound; at 200K the KV (~2.5 GB at 3-bit) does not fit in cache, so this is real DRAM traffic.

3. **No matrix intrinsics.** Every TQ kernel uses scalar FMA plus a `simd_sum` reduction (verified: zero `simdgroup_matrix` usage in the fork). Prefill at `L > 1` is a matrix-matrix problem — `Q[L×D]·Kᵀ`, then `W[L×T]·V` — which is a missed `simdgroup_matrix` (MMA) opportunity.

4. **Score materialization.** The Prod / Polar / multi-query-prod paths write the full `[B, H, R, (L,) T]` score tensor to global memory and finish softmax / merge / inverse-rotation in Python, across multiple dispatches.

5. **Prod codec is unwired and unfused.** It is the higher-fidelity codec (it recovers the MSE residual through a 1-bit QJL sign sketch projected through a fixed Gaussian), but it is both unreachable under the live wiring and not fused.

6. **Generality rigidity.** Hand-tuned token thresholds, per-`(bits, R, dim)` kernel recompilation, a `dim % 32 == 0` requirement (MSE), Polar restricted to pow2 + `bits == 4` + 4-levels-only, and an in-kernel O(D²) dense rotation in one Prod decode kernel.

### Precision is already good

All existing TQ kernels accumulate scores, online-softmax statistics, and AV in fp32 (`typedef float U`); only stored norms are fp16. The quality lever is therefore not internal accumulation precision. It is enabling the Prod codec and `kv_bits=4` affordably.

---

## 4. Architecture: one flash core plus pluggable codec dequant

A single parameterized flash-attention Metal kernel, with the codec dequant injected as a device-side function.

### Flash core

- **KV-tiled with fp32 online softmax (flash).** Single dispatch, with a 2-pass KV-block split for GPU occupancy at long `T`. The split is occupancy-driven, replacing the hand-tuned threshold ladder.
- **Handles `L ≥ 1` uniformly.** Decode (`L = 1`) and prefill (`L > 1`) run the same kernel. Prefill adds intra-block causal masking (query `i` attends to keys `≤ base + i`) and causal-tile skipping (skip K-tiles entirely in the query block's future).
- **GQA tile-reuse.** Load each kv-head's K/V tile once into threadgroup memory and serve all `R` query-heads from it. This removes the `R×` bandwidth bug and is the highest-value Apple-Silicon speed lever found.
- **Score in rotated space.** Pre-rotate the `L` queries once (RHT / Hadamard, or a matmul for non-pow2) to produce `q_rot` (and `q_proj` for Prod). Keys stay in rotated space (no per-key inverse rotation); only the `L × D` output is inverse-rotated. This keeps the O(D log D) rotation off the hot T-loop and matches the codec math exactly.

### Pluggable codec dequant

A device-side "reconstruct rotated coordinate" function is injected into the Metal source string. The kernels are already built from Python f-string templates, so source composition is the existing mechanism.

| Codec | Dequant |
|---|---|
| MSE | Scalar codebook gather — a shared ≤16-entry fp32 LUT indexed per dim, times a per-token fp16 norm. |
| Prod | MSE plus a QJL stage: unpack a 1-bit sign plane per dim → `±1`, dot against the pre-projected query `q_proj`, scale by the stored fp16 `residual_norm` and the constant `sqrt(pi/2)/dim`. |
| Polar | Out of scope (documented extension point). |

### Compute strategy (spike-selected, see §6)

The flash core is written to accept either inner-product op:

- (a) **MMA.** Dequantize the K/V tile to fp16 in threadgroup memory, then use `simdgroup_matrix` for `QKᵀ` and `AV` with fp32 accumulate.
- (b) **LUT scoring.** Precompute `q·codebook` per query block once (fp32, exact) and replace per-key multiplies with threadgroup-memory gathers and adds. Favored at 3-bit, and for `QKᵀ` only — `AV` stays dequant + MMA.

The spike picks the winner.

---

## 5. Three-axis mapping

| Design element | Quality | Generality | Speed on Apple Silicon |
|---|---|---|---|
| fp32 accumulation kept | ✓ | | |
| Prod + `kv_bits=4` made fast and first-class | ✓ | | |
| TDD bounds absolute error against a full-fp32 reference | ✓ | | |
| Templated `head_dim` (incl. `DimPadded` for non-pow2), GQA ratio, key/val bits, codec | | ✓ | |
| Single capability object gates eligibility | | ✓ | |
| Transparent fallback to the existing K-tile loop | | ✓ | |
| Enforced by a test matrix; no model-name branches | | ✓ | |
| GQA tile-reuse (≈`R×`) | | | ✓ |
| MMA / LUT inner product | | | ✓ |
| No score materialization | | | ✓ |
| Causal-tile skip | | | ✓ |
| Single dispatch, eliminating per-tile `mx.eval` syncs | | | ✓ |
| 3-bit KV reads (~5× less DRAM than fp16) | | | ✓ |

---

## 6. Phase 1 — Spikes

Validate the Apple-Silicon bets before building anything.

### Spike A — `simdgroup_matrix` MMA viability in `mx.fast.metal_kernel`

- **Hypothesis:** `simdgroup_matrix` compiles and runs inside `mx.fast.metal_kernel` and beats the scalar `simd_sum` reduction for `QKᵀ` and `AV` at Qwen dims.
- **Measure:** that it compiles and runs at all (unproven in this codebase), then `QKᵀ` / `AV` throughput against the current scalar reduction at `head_dim = 256`, `R = 6`.
- **Success:** MMA runs correctly and is faster than the scalar baseline at these dims.

### Spike B — LUT scoring at 3-bit

- **Hypothesis:** Precomputing `q·codebook` per query block and replacing per-key multiplies with gathers beats MMA at 3-bit.
- **Measure:** throughput and numerics of the `q·codebook` precompute + gather against Spike A.
- **Success:** LUT scoring matches MMA numerics and is at least competitive on throughput at 3-bit.

### Spike C — GQA tile-reuse decode prototype

- **Hypothesis:** Loading a kv tile once and serving `R` heads removes the `R×` re-read and wins big at long context. This may be the largest lever and is the cheapest to test.
- **Measure:** the bandwidth win against today's per-head re-read at long context.
- **Success:** measurable bandwidth reduction and decode speedup at long context.

### Spike D — bandwidth- vs compute-bound at large `T`

- **Hypothesis:** At large `T` the kernel is bandwidth-bound, so 3-bit reads set the ceiling.
- **Measure:** where the kernel sits on the roofline at large `T`.
- **Success:** a clear answer on whether a 3-bit fused kernel can beat fp16 fused SDPA, not just the Python loop.

### Spike E — decode-at-200K baseline

- **Hypothesis:** Decode at 200K may itself need tuning, independent of prefill.
- **Measure:** current decode tok/s with a 200K cached KV — the other half of per-turn responsiveness.
- **Success:** a baseline number that tells us whether a decode-tuning follow-up is needed.

---

## 7. Phases 2–4 — Build

### Phase 2 — Unified flash core + MSE dequant (prefill + decode)

TDD against the §8 reference. Replace the MSE single-pass / 2-pass decode kernels and the `L > 1` prefill path, both behind the capability gate and a YAML kill-switch. Validate on Qwen: needle retrieval, numerics, and prefill / decode tok/s against the current baseline.

### Phase 3 — Prod codec

Wire `mode="prod"` selection into `_ensure_codecs` (config-threaded, see §9) and add the Prod QJL dequant stage to the kernel's pluggable layer. Validate a measurable quality uplift over MSE at equal storage.

### Phase 4 — Generality and ship

Flip `gemma4` to `kv_quant_scheme: turboquant` and validate end-to-end. `gemma4` has never run TQ: only its global-attention layers quantize; the sliding-window layers stay on `RotatingKVCache`, unquantized and cheap. Run the full dim / GQA / bits test matrix. Document the config.

---

## 8. Numerics and TDD

Reference of record: full fp32 dequant of the KV, fed to `mx.fast.scaled_dot_product_attention` in fp32. This bounds the absolute codec + kernel error, not just parity with today's loop. Assert a tight max-abs-diff.

Reuse `test_turboquant.py` patterns: query-block-size invariance, prefill-matches-dequantized-attention, causal alignment.

Test matrix:

| Axis | Values |
|---|---|
| `head_dim` | 256, 128, and a non-pow2 such as 96 (exercises RHT padding) |
| GQA | 1 (MHA), 4, 6 |
| `kv_bits` | 3, 4 |
| `L` | 1, 64, 256, large |
| `T` | spanning the block-split thresholds and the causal diagonal |
| Codec | MSE and Prod |

---

## 9. Config threading (kill-switch)

Add `tq_fused_prefill` (boolean), per-model in `main_models.yaml`. Default behavior is auto-on for eligible TQ models; setting it to `false` disables the fused path for debug or fallback.

Thread it down the same path `kv_bits` uses:

```
main_models.yaml
  → mlx-serve config.py        (new field + default)
  → process_manager.py         (CLI flag, only emitted when set)
  → mlx-vlm cli.py             (parse → env var)
  → read at cache/dispatch construction, feeding the capability object
```

The primary gate is the eligibility predicate — TQ, MSE or Prod codec, wrapper-routed, supported dims. The flag is an override on top of it.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| MMA unproven in `mx.fast.metal_kernel` | Spike A de-risks it. Fallback is scalar / LUT, which still beats the Python loop. |
| Register pressure holding `L` queries × `D = 256` | Tile `L` into sub-blocks. |
| fp16 dequant precision for MMA | fp32 accumulate; 3-bit values represent exactly in fp16. |
| Causal off-by-one | TDD. |
| Prod needs dual pre-rotated query streams | Carry both `q_rot` and `q_proj`. |
| `BatchTurboQuantKVCache` (continuous-batching) is a parallel path | Give it the same treatment, or explicitly fall back. |
| Single-shot-200K non-attention floor is real | Amortized in the prefix-cache multi-turn regime; out of scope per §1. |

---

## 11. Operating constraints for the implementer

- All code edits go in the fork `../mlx-vlm`, never `src/mlx-vlm`.
- Test via `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ...` from the stack dir `$STACK_REPO`.
- The `:8000` stack serves one model at a time and never handles concurrent requests. First confirm no stray python eval / generate / needle processes are running.
- Propose fork changes for approval before commit or push.
- Restart the mlx-serve manager to load new code.
- Fork `main` is currently at the post-upstream-merge commit.

---

## 12. Driver prompt for a fresh session

```
Read this spec
(docs/superpowers/specs/2026-06-17-unified-fused-quantized-kv-attention-design.md)
and the memory entries project_tq_prefill_fix and project_200k_viability_spike.

Goal: implement the unified fused quantized-KV attention kernel per this spec.

Work spike-first. Run Phase 1 spikes A–E and confirm the Apple-Silicon bets
(MMA viability, LUT-vs-MMA at 3-bit, GQA tile-reuse, bandwidth ceiling, the
200K decode baseline) BEFORE building anything.

Operating constraints (§11): all edits in the fork
../mlx-vlm (never src/mlx-vlm); test with
PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ... from the stack
dir; serve one model at a time, no concurrent requests, and first confirm no
stray python eval/generate/needle processes; propose fork changes for approval
before committing or pushing; restart the mlx-serve manager to load new code.

Build with TDD against the §8 reference (full fp32 dequant →
mx.fast.scaled_dot_product_attention in fp32, tight max-abs-diff, full
dim/GQA/bits/L/T/codec matrix).

Order: Phase 2 (MSE, prefill + decode) → Phase 3 (Prod) → Phase 4 (generality +
gemma4). Propose before committing.

If brainstorming or writing-plans outputs are present, use them.
```

---

Reference this document by its path:
`$STACK_REPO/docs/superpowers/specs/2026-06-17-unified-fused-quantized-kv-attention-design.md`
