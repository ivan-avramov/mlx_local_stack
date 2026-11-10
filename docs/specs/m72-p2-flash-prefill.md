# Spec: M72 P2′ — TQ4 flash prefill on the Neural Accelerators, prototype (C311 / C312; S20-P14; four-eyes light)

Status: v1, 2026-11-10 (session 20). Designer: the session. Records: `docs/open-questions.md` C311, C312, S20-P14;
evidence `benchmark/results/m72/{REPORT.md, PROBE.md, probe/spike-f2-nax-matmul.log, probe/spike-f3-tq4-nax-scores.log}`.

## Goal (verbatim in every brief)

TurboQuant 4 (TQ4) prefill attention for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`'s shapes runs at 0.35× native16 at
260K, because the shipped TQ4 path never uses the M5 Max Neural Accelerators while native16's fused SDPA (`fused_v1`) does.
Build one prototype flash-attention kernel for a 512-token prefill chunk that runs QKᵀ and PV on the Neural Accelerators
(MLX's steel NAX fragment, `matmul2d`, inlined into the `mx.fast.metal_kernel` JIT as in spike F2) with two K / V loaders —
TQ4 (packed indices unpacked to codebook values in the codec's rotated space, once per threadgroup tile, shared by all the query
heads of a KV head) and native16 (bf16) — reading the full-cap preallocated buffers in place, accurate to the pre-registered
tolerance below, and measure it per layer and per chunk against `fused_v1`, today's TQ4 prefill and P1 (dequantize + fused SDPA)
so the operator can judge how far TQ4 prefill gets toward parity. Solving it means: the kernel and its measurement exist, the
accuracy criteria hold on both arms, the negative controls fail them, and the probe + generated report produce the timing and
projection tables. No speed bar.

## Scope

1. Fork `../mlx-vlm`: new `dev/m72_flash_prefill.py` (dev only, never imported by `mlx_vlm/`); GPU tests
   `dev/tests/test_m72_flash_prefill.py` (Metal required; skip with reason when unavailable).
2. Stack: `benchmark/spikes/m72_tq4_probe.py` gains `--mode p2`; new generator `benchmark/spikes/m72_p2_report.py` →
   `benchmark/results/m72/P2.md`; new launcher `benchmark/spikes/m72_run_p2.sh`; tests `benchmark/bench/tests/test_m72_p2_report.py`
   (no MLX, synthetic JSON) and `benchmark/bench/tests/test_m72_p2_probe_gpu.py` (`pytest.importorskip("mlx.core")`).
3. The NAX header inlining helper moves from `benchmark/spikes/spike_f2_nax_matmul.py` into the fork module (the fork owns the
   kernel); the spike keeps working.

## Settled constraints

- (operator, C311 / C312) Accuracy standard = an existing path's tolerance (as `joint_v1`), not bit-identity. Native16 arm included
  (C313). Neural Accelerators via the JIT, no MLX rebuild.
- (designer) Prototype only: no production dispatch, registry or server change. Batch 1; 24 q / 4 kv heads (R = 6), head dim 256,
  bf16 queries; TurboQuant MSE 4-bit keys and values, power-of-two RHT rotation (the probe's `TurboQuantKVCache(bits=4, ...)`).
- (designer) Full-cap buffers in place (per-head stride = capacity): TQ4 `cache.keys` / `cache.values` (`norms` (1, n_kv, cap) fp16,
  `indices` (1, n_kv, cap, 32) uint32, dim d at bits [4d, 4d + 4) of a token's words, LSB first); native16 (1, n_kv, cap, D) bf16. No
  dequantized K / V outside the kernel (that is P1, the reference arm only).
- (designer) Probe rules unchanged: power, idle-GPU and fragment-mapping gates before measured work; synthetic K / V; `timeit`;
  caches preallocated to 262,144; `CHECKPOINTS`; two passes with opposite arm order.

## Interfaces

```python
# dev/m72_flash_prefill.py
def nax_header() -> str                       # MLX steel defines + type_traits + integral_constant + gemm/nax.h, inlined
def flash_prefill_tq4(cache, queries, scale, q_offset, *, block_tokens=None, positions_per_tg=None, _kv_head_shift=0) -> mx.array
def flash_prefill_native16(keys, values, queries, scale, q_offset, *, block_tokens=None, positions_per_tg=None,
                           _kv_head_shift=0) -> mx.array
def fragment_mapping_ok() -> bool             # the NAX fragment's element -> (row, col) mapping, checked on this GPU
```

- `queries` (1, 24, L, 256) bf16, 1 ≤ L ≤ 512: the chunk at absolute positions [q_offset, q_offset + L). Keys / values hold the
  tokens [0, q_offset + L) (the cache already appended the chunk, as in production). Causal: query at position p attends to
  tokens t ≤ p. Preconditions (assert): q_offset ≥ 0; q_offset + L ≤ cache.offset (TQ4) or ≤ keys.shape[2] (native16).
- Returns (1, 24, L, 256) in `queries.dtype`, the attention output in the original (unrotated) space.
- TQ4 semantics: q' = `cache.key_codec.prepare_queries(queries * scale)`; score(p, t) = keys.norm[t] · ⟨q'_p, u_k(t)⟩;
  o' = Σ_t softmax_t · values.norm[t] · u_v(t); output = `cache.value_codec._rotate_inverse(o')`.
- Native16 semantics: score = ⟨q_p · scale, K[t]⟩; output = Σ softmax · V[t].
- `_kv_head_shift` (negative control): query heads of KV group g read KV head (g + shift) mod n_kv.

## Design (settled by the designer unless marked free)

- One threadgroup per (KV head g, block of P query positions): its rows are the R = 6 query heads of g × P positions (GQA rows
  packed, so each K / V tile is unpacked once per KV head, not once per query head); 16-row NAX fragments, one row-simdgroup per
  16 rows; P free (e.g. 16 → 96 rows, 6 row-simdgroups), optionally a head-dim split of P·V across WN ∈ {1, 2} simdgroups per row
  group (free; MLX's `attention_nax_dsplit` is the reference for the split and its S exchange).
- Per KV tile of BK tokens (free: 16 or 32; threadgroup memory ≤ 32 KB): TQ4 — the threadgroup copies the tile's packed words
  (coalesced) and unpacks them once into threadgroup memory as half codebook values, with the two norm vectors in fp32
  (threadgroup codebook lookup; spike F3's fastest form); native16 — copy or load bf16 directly (free). Row-simdgroups load their
  fragments from the tile. QKᵀ and PV with `BaseNAXFrag::mma` (fp32 accumulators); TQ4 key norm scales S's columns, value norm
  folds into P before PV.
- Online softmax per row in fp32 (as `attention_nax`: base-2 exponentials with the scale folded, row max / sum via the fragment's
  lane pairs); causal mask only in tiles that straddle a row's position; tiles entirely in the future are skipped per threadgroup;
  padded rows never written; no NaN for any row (every row sees ≥ 1 token: itself).
- No split over tokens: a threadgroup sweeps all tokens for its rows (prefill has 4 · 512 / P threadgroups per chunk — enough
  parallelism). The final normalization and the TQ4 inverse rotation follow (rotation outside the kernel, as in verify).

## Probe `--mode p2` (stack)

- Accuracy sweep (cache cap 40,960): chunk offsets {0, 511, 4096, 8190, 32256 (= a chunk ending at 32,768)} and L ∈ {512, 1, 37},
  both arms, vs the fp32 reference (below); planted-token cases and negative controls, each compared with the reference at the
  true offset: N1 `_kv_head_shift=1`; N2 leak — the kernel called with `q_offset + 1` (every row attends one token further) on a
  planted case where token p + 1 would dominate row p if visible; N3 drop — the kernel called with `q_offset − 1` on a planted
  case where each row's own token p dominates. Planted caches hold one token beyond the chunk so N2 stays in range.
- Per checkpoint (`CHECKPOINTS`, the chunk = the last 512 tokens ending at T), times of: `native16_fused_v1` (the shipped path),
  `tq4_production` (today's TQ4 prefill: `scaled_dot_product_attention(..., cache=tq, mask="causal")` on the state at T),
  `p1_rotated` (the probe's existing rotated-space dequantize + fused SDPA), `p2_tq4`, `p2_native16`; accuracy of both P2 arms on
  three query heads {0, 11, 23} (all rows) vs the fp32 reference (computed per head); `peak_GB`.
- fp32 reference: TQ4 — `codec.dequantize` of K / V; native16 — bf16 K / V cast to fp32; exact causal softmax per head.
  Rel error = max |out − ref| / max |ref| over the evaluated block.
- JSON: `meta.mode = "p2"`, `meta.fork`, `meta.arm_order`, `meta.p2_kernel` (BK, P, WN, mapping check), `meta.p2_accuracy`
  {rows: [{offset, L, arm, case, rel_err, prod_rel_err, allclose, finite, pass}], controls: [{name, arm, rel_err, pass}], n,
  n_pass}; `checkpoints[]`: {T, bytes, power, peak_GB, p2: {arm: TIMING ...}, p2_accuracy: {arm: ACC}} with TIMING / ACC as in
  `m72-mma-verify.md`.
- `m72_run_p2.sh <out_dir>`: as `m72_run_mma.sh` (refuse existing `p2-1.json` / `p2-2.json` with exit 10; pass 1
  `--arm-order forward`, pass 2 `reverse`; 600 s idle; exits 11 / 12; mode 755).
- `m72_p2_report.py <run_dir>` → stdout Markdown (GENERATED header; refuses passes with differing fork head / MLX / architecture /
  checkpoint lists): accuracy section (A3 holds only with exactly the six controls, each failing); per-chunk table (T, the five arms,
  p2_tq4 / native16_fused_v1, p2_tq4 / tq4_production, p2_native16 / native16_fused_v1); pass drift; projection of prefill time
  for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` at the `PICK_BASELINE["prefill_s"]` contexts with `m72_probe_report`'s
  method (t(N) = f·N + 16 · Σ_chunks attn(T_j) [+ TQ4 append]; f from the pick's measured time minus 16 · Σ native16 attention),
  for TQ4 today, P1 and P2 TQ4, as ratios to shipped native16.

## Acceptance criteria (pre-registered)

- A1 Accuracy, each arm, every sweep case and every checkpoint head: rel error ≤ 2 × max(production rel error, 2⁻¹²) and
  `allclose(atol = rtol = 3e-2)` vs the fp32 reference, all finite. Production: TQ4 — `tq4_production` on the same state; native16
  — MLX's `scaled_dot_product_attention` (fused, causal) on the same buffers (sliced to T).
- A2 Planted cases: A1 holds.
- A3 N1–N3 fail A1 on both arms (six controls).
- A4 Causality and edges: L = 1 and L = 37, q_offset = 0 (a row that sees only itself), chunks crossing tile boundaries, no NaN.
- A5 No layout copy or materialized K / V (peak memory above the live arrays < 0.4 × the K / V bytes read).
- A6 Tests pass; stack suite passes or fails only as on the baseline (the clean-clone gate).
- A7 `--mode p2 --max-t 32768` smoke completes with A1–A4 recorded.

## Non-goals

Production wiring, decode / verify (the matrix-unit verify kernel stays as measured; its NAX variant is for 1.3), batch > 1,
other shapes or codecs, bit-identity, tuning beyond a working default, a NAX-off control for the new kernel (its tensor ops have no
non-accelerator form; the comparison is against `fused_v1`, which is the shipped NAX path).

## Assumptions (designer)

- Spike F2: `BaseNAXFrag::mma` (16 × 32 × 16, half or bfloat operands, fp32 accumulate) runs in the JIT with the inlined headers;
  fragment loads from threadgroup memory work as from device memory (MLX's `load` takes any pointer).
- 32 KB of threadgroup memory per threadgroup; 96 + rows per threadgroup fit the register budget with WN = 2 if WN = 1 does not.
- The codebook-lookup floor (spike F3, ≈ 300 G lookups/s) makes the TQ4 unpack ≈ 2 % of a 260K chunk's math when shared by the
  six query heads of a KV head.

## Open questions

None for the operator; tiling is the implementer's within the criteria.
