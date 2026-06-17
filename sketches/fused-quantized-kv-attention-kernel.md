# Plan: Fused Quantized-KV Attention Kernel for Qwen3.6-27B TQ Prefill (or not)

**Status:** The two shipped prefill fixes already made TQ correct and competitive:

- `chunked_prefill_policy` on qwen3_5 (fork c3192a0) + gemma4 (7696f5a) — keeps chunked
  prefill ON under suffix decoding, killing the dense `[N, N]` causal-mask OOM at 200K.
- `prefill_query_block_size` 16→256 in `quantized_attention` — ~15x on the attention op
  (157→11 ms at L=512, T=8K).

A fused quantized-KV attention kernel is now **lower-ROI than expected**. The profiling below
says validate **fp16 KV first** — the kernel may be unnecessary. Do not write kernel code until
Phase 0 closes.

---

## 1. Findings to date (do not repeat this work)

- **Measured TQ needle prefill** (Qwen3.6-27B-UD-MLX-6bit, kv_bits=3, chunked, after both
  fixes): 93 tok/s @16K, 75 tok/s @64K. Needle PASS, peak ~37 GB. 200K projected ≈ 71 min.
- **Profile** (component micro-bench at real dims, anchored to the measured 16K/64K runs): at
  200K, prefill ≈ 71 min splits as attention 57% + non-attention 43%.
  - Attention 57% = the 16 full-attention layers' `quantized_attention`, O(T²).
  - Non-attention 43% = 64 MLP + 48 GatedDeltaNet linear layers + per-chunk TQ quantize, O(T),
    ≈ 4.8 s per 512-token chunk — the fundamental cost of forwarding a 27B model over 200K
    tokens.
  - Arch: 64 layers, `full_attention_interval=4` (16 full-attn + 48 GDN), hidden 5120,
    intermediate 17408, n_q 24 / n_kv 4 (GQA), head_dim 256.
- **Speed-gain ceiling — MEASURED.** Fused dense `mx.fast.scaled_dot_product_attention` is only
  ~1.8x faster than the qb-256-tuned `quantized_attention` at Qwen full-attn dims (depths
  8K–196K; e.g. 64K = 141 ms fused vs 258 ms TQ). The manual path is already close, so a fused
  quantized-KV kernel's **FLOOR gain is ~1.8x**.
- **Speed-gain upside — speculative, unmeasured.** A fused quantized kernel reads 3-bit KV
  (~5x less data than dense bf16). If attention is memory-bandwidth-bound at 200K, it could beat
  dense-fused (ceiling maybe ~3–5x). Must be measured before committing.
- **Hard constraint.** Even a perfect attention kernel cannot make 200K interactive. The
  non-attention 43% is a ~31-min floor at 200K. Kernel alone: 71 min → ~40–53 min. Not
  "minutes."
- **fp16-KV alternative — LIKELY the better lever.** Qwen3.6 full-attn KV is small: 16 layers ×
  GQA-4 × head_dim 256 × fp16 ≈ ~13 GB at 200K, which fits under the ~58 GB Metal cap on the
  confirmed 68.7 GB machine. fp16 KV → standard `KVCache` → fused dense flash attention (the
  ~1.8x path) + best quality + no scores spike + **no kernel to build** (a config change). This
  likely obviates the custom kernel. Must validate it fits + works end-to-end + quality is
  acceptable.
- **gemma comparison.** gemma-4-31b uniform-4bit (chunked) = 55 tok/s @64K — SLOWER than Qwen TQ
  (75). Uniform-quantized KV is NOT a fast path (also manual quantized SDPA). Uniform is not an
  escape hatch.

---

## 2. Phase 0 — profile & validate the fix location (required before any kernel code)

The kernel is the most expensive option on the table and the one the profiling argues against.
Phase 0 either kills it or earns it. No `.metal` source gets written until 0c passes.

### 0a. fp16-KV viability on Qwen3.6, end-to-end

Add a temporary twin to `main_models.yaml` — same weights (`unsloth/Qwen3.6-27B-UD-MLX-6bit`),
but `quantized_kv_start: 999999999` so KV stays fp16. **Verify it actually yields a plain fp16
`KVCache`, not TurboQuant**, by checking peak memory: `maybe_quantize_kv_cache` gates on
`offset < quantized_kv_start` and returns early when `kv_bits` is None, so the offset never
crosses the start and the cache never quantizes. Peak memory at 200K is the proof — ~13 GB of
fp16 KV looks nothing like a 3-bit packed cache.

Restart, then run `benchmark/needle_256k.py --ctx 64000` and, if it fits, `--ctx 200000`.
Record:

- peak memory — does ~13 GB fp16 KV at 200K fit under the ~58 GB cap?
- prefill tok/s vs TQ (75 @64K).
- needle retrieval.
- quality spot-check.

**If fp16 fits AND quality is acceptable → fp16 KV obviates the kernel.** It gives fused-dense
speed (the ~1.8x path), best quality, no scores spike, and is a config-only change. Recommend
fp16 for Qwen3.6 and STOP. Remove the twin.

### 0b. If fp16 is NOT viable (OOM at target context, or quality regression needing compression)

Re-profile per-layer at large T to confirm attention is the dominant *addressable* cost, and
determine whether attention is bandwidth- or compute-bound at 200K (compare 3-bit vs dense data
volume) to estimate the fused-quantized kernel ceiling. Reuse the existing scripts
`/tmp/tq_prefill_profile.py` and `/tmp/tq_vs_fused_attn.py` — move them into `benchmark/` and
clean up.

### 0c. Decision gate

Build the kernel ONLY IF all three hold:

1. fp16 is not viable; AND
2. the measured/estimated kernel ceiling > ~2–3x; AND
3. the ~31-min non-attention floor at 200K is acceptable or separately addressed.

---

## 3. Phase 1 — fused quantized-KV flash attention kernel (only if Phase 0 justifies)

A Metal kernel via `mx.fast.metal_kernel`, reusing the kernel infrastructure already in
`mlx_vlm/turboquant.py` (25+ `metal_kernel` defs). It does flash attention reading TQ-quantized
KV directly: per K-tile, in-kernel dequant (inverse FWHT rotation + codebook lookup), QK^T,
online softmax, AV — never materializing the `[L, T]` scores or an `[N, N]` mask.

It replaces the Python K-tile loop in `TurboQuantKVCache.quantized_attention` for the prefill
(L > 1) path.

**Numerics (TDD).** Validate against the current `quantized_attention` / dequantize-then-SDPA
reference: max abs diff small (~< 1e-3). Reuse the `test_turboquant.py` patterns —
`test_turboquant_prefill_attention_matches_dequantized_attention` and
`test_turboquant_quantized_attention_invariant_to_query_block_size`.

**Risks to call out:**

- FWHT requires head_dim power-of-2 (Qwen 256 ✓).
- GQA broadcast (n_q=24 / n_kv=4).
- Causal-mask alignment for prefill chunks — queries are the last L positions of the context.
- Currently MSE codec (kv_bits=3); the Prod codec is a separate path.
- The existing `prefill_attention` (Prod path) already attempts a fused approach but
  materializes `[B*H*R, L, T]` scores — it needs T-tiling too.

---

## 4. Phase 2 — the non-attention floor (note, not a kernel task)

The 43% non-attention cost (MLP + GatedDeltaNet forward) is largely the irreducible cost of a
27B model over 200K tokens. Interactive 200K is not reachable by attention work alone. The
realistic levers are capping usable context (prefill is a few minutes at ≤ ~32–64K) or a smaller
model. State this plainly so a future reader does not expect the kernel to deliver
interactivity.

---

## 5. Driver prompt for a new session

```
Read sketches/fused-quantized-kv-attention-kernel.md and memory project_200k_viability_spike.md for full context. Goal: decide whether to build a fused quantized-KV attention kernel for Qwen3.6-27B TQ long-context prefill — PROFILE/validate the fix location FIRST, before any kernel code.

Operating rules: the stack on :8000 serves ONE model at a time (never issue concurrent requests; first confirm there are no stray python eval/generate/needle processes). ALL mlx-vlm code edits go in the FORK at ../mlx-vlm, never the submodule src/mlx-vlm; test via PYTHONPATH=../mlx-vlm. Propose fork changes for approval before commit/push. Restart the main manager to load new code.

Phase 0 (do this before ANY kernel work):
1. fp16-KV viability on Qwen3.6 end-to-end. Add a TEMPORARY main_models.yaml twin (same hf_path unsloth/Qwen3.6-27B-UD-MLX-6bit, quantized_kv_start: 999999999 so KV stays fp16 — VERIFY it yields a plain fp16 KVCache not TurboQuant, via peak memory). Restart, run `uv run python benchmark/needle_256k.py --model <twin> --ctx 64000`, and if it fits `--ctx 200000`. Record peak memory (does ~13GB fp16 KV @200K fit under the ~58GB cap?), prefill tok/s (vs TQ 75 @64K), needle retrieval, and a quality spot-check. If fp16 fits AND quality is acceptable → fp16 KV obviates the kernel (fused-dense speed + best quality, config-only); recommend fp16 for Qwen3.6 and STOP. Remove the twin.
2. If fp16 is NOT viable: re-profile per-layer at large T (benchmark/tq_prefill_profile.py, benchmark/tq_vs_fused_attn.py — move them out of /tmp) to confirm attention is the dominant addressable cost and estimate the fused-quantized kernel ceiling (bandwidth- vs compute-bound; 3-bit KV reads ~5x less than dense).
3. Decision gate: build the kernel only if fp16 isn't viable AND the kernel ceiling is > ~2-3x AND you accept the ~31-min non-attn floor at 200K.

Phase 1 (only if justified): build the fused quantized-KV flash kernel per the sketch — a mx.fast.metal_kernel doing flash attention over TQ-quantized KV (in-kernel FWHT dequant + online softmax, no [L,T] scores or [N,N] mask materialized), replacing the Python K-tile loop in TurboQuantKVCache.quantized_attention for prefill. TDD numerics vs the current path in test_turboquant.py. Mind: FWHT head_dim power-of-2 (256 ✓), GQA 24/4, causal alignment, MSE codec (kv_bits=3).

Remember: even a perfect kernel can't make 200K interactive — non-attn (MLP+GDN) is a ~31-min floor at 200K; the kernel is at most ~25–46% off total prefill. Frame accordingly.
```
