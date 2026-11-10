# Spec: M72 1.2 matrix-unit verify kernel prototype (C312 / C313; four-eyes light)

Status: v1.1, 2026-11-09 (session 20; v1.1 adds the JSON schema and report formulas before dispatch). Designer: the session. Records: `docs/open-questions.md` C312, C313, S20-P2, S20-P10.

## Goal (verbatim in every brief)

An MTP verify block of k drafted tokens (k = 1…5) on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`'s attention shapes costs
2.5–2.9× a single decode today, because every kernel we have (TurboQuant 4 per-query loop, the exact multi-query prototype
`dev/m72_mq_decode.py`, and native16's MLX joint SDPA call) pays the per-query, per-token work once per query. Build one prototype
attention kernel that computes the whole block with simdgroup matrix multiply-accumulate (8×8 MMA) over KV tiles loaded once into
threadgroup memory, with two tile loaders — TurboQuant 4 (unpack in the codec's rotated space) and native16 (bf16 copy) — reading
the full-cap preallocated buffers in place, accurate to the pre-registered tolerance below, and measure it per layer against the
existing baselines so the operator can judge (a) TQ4 + this kernel vs shipped native16 and (b) native16 + this kernel vs shipped
native16. Solving it means: the kernel and its measurement exist, the accuracy criteria hold on both arms, both negative controls
fail them, and the probe + generated report produce the timing and projection tables. No speed bar.

## Scope

1. Fork `../mlx-vlm`, new file `dev/m72_mma_verify.py` (dev only, never imported by `mlx_vlm/`).
2. Stack: `benchmark/spikes/m72_tq4_probe.py` gains `--mode mma`; new generator `benchmark/spikes/m72_mma_report.py`; new
   launcher `benchmark/spikes/m72_run_mma.sh`.
3. Tests: fork `dev/tests/test_m72_mma_verify.py` (GPU; Metal required, skip with reason when unavailable); stack
   `benchmark/bench/tests/test_m72_mma_report.py` (no MLX; synthetic JSON).

## Settled constraints

- (operator, C312) Accuracy standard = `joint_v1`'s, not bit-identity to the singleton. (operator, C313) Native16 arm included.
- (designer) Prototype only; no production dispatch, registry or server change. Batch 1. Shapes: n_q = 24, n_kv = 4, R = 6,
  D = 256, bf16 queries; TurboQuant MSE codec, 4-bit keys and values, power-of-two RHT rotation (the probe's
  `TurboQuantKVCache(bits=4, ...)`).
- (designer) Reads the full-cap buffers in place: TQ4 `cache.keys` / `cache.values` (`TurboQuantMSEState`: `norms` (1, n_kv,
  cap) fp16, `indices` (1, n_kv, cap, 32) uint32, 4-bit indices LSB-first, dim d at bits [4d, 4d+4) of the row's words);
  native16 full-cap arrays (1, n_kv, cap, D) bf16. Per-head stride = the buffer's capacity. No `mx.contiguous`, slice-copy or
  dequantized materialization of K/V outside the kernel.
- (designer) Probe rules unchanged: power gate and idle-GPU gate (`m72_gates`) before any measured work; synthetic K/V; medians
  via the existing `timeit`; caches preallocated to 262,144; checkpoints `CHECKPOINTS`.

## Interfaces

```python
# dev/m72_mma_verify.py
def mma_verify_tq4(cache, queries, scale, lengths, *, block_tokens=None, _kv_head_shift=0) -> mx.array
def mma_verify_native16(keys, values, queries, scale, lengths, *, block_tokens=None, _kv_head_shift=0) -> mx.array
def plan_blocks(max_length: int, block_tokens=None) -> tuple[int, int]   # (Blocks, tokens per block), recorded by the probe
```

- `queries` (1, 24, k, 256) bf16, k ∈ 1…5. `lengths`: k ascending ints, query j attends to tokens [0, lengths[j]).
  Preconditions (assert): `lengths[-1] <= cache.offset` (TQ4) or `<= keys.shape[2]` (native16); `lengths[0] >= 1`.
- Returns (1, 24, k, 256) in `queries.dtype`, the attention output in the original (unrotated) space.
- TQ4 semantics: q' = `cache.key_codec.prepare_queries(queries * scale)` grouped as the singleton does (`(B, n_kv, R, k, D)`);
  score(t) = keys.norm[t] · ⟨q', u_k(t)⟩ with u_k(t)[d] = key codebook[idx]; softmax over t < lengths[j]; o' = Σ p(t) · values.norm[t]
  · u_v(t); output = `cache.value_codec._rotate_inverse(o')`.
- Native16 semantics: score(t) = ⟨q · scale, K[t]⟩; output = Σ p(t) V[t].
- `_kv_head_shift` (negative control only): query heads of group h read KV head (h + shift) mod n_kv.

## Design (settled by the designer unless marked free)

- One threadgroup per (KV head, token block). Rows of a KV head = its R query heads × k queries, row r = i·k + j (i = head
  within the group, j = query); M = R·k ≤ 30, padded to a multiple of 8; one simdgroup per 8-row tile.
- Per tile of Tt tokens (free: Tt ∈ {16, 32}): all threads cooperatively load the tile into threadgroup memory — TQ4: unpack the
  4-bit indices to the codebook's unit values (half) plus the tile's two norm vectors (fp32); native16: copy bf16. Barrier.
- S = Q·Kᵀ and O += P·V with `simdgroup_multiply_accumulate`, fp32 accumulators (operand fragment type free: float, half or
  bfloat, subject to the accuracy criteria). Q held in threadgroup memory (free: half or float). TQ4 norms applied in fp32: key norm
  to S, value norm folded into P before P·V.
- Online softmax per row in fp32 (running max, sum, rescale of the row's O accumulators). Causal / length mask per row:
  t ≥ lengths[j] contributes nothing; padded rows contribute nothing and are never written. No NaN from fully masked tiles or rows.
- Split over token blocks (`plan_blocks`, free policy, ≥ 1 block, every block ≥ 1 tile): each block writes per-row partials
  (acc (rows·Blocks, D) fp32, sum, max), empty (row, block) pairs as max = −1e30, sum = 0, acc = 0 — the layout of
  `turboquant._fused_mse_decode_2pass_2_kernel`, which combines them unchanged (or an equivalent combine).
- MMA fragment element mapping: verify it with a unit test before relying on it (MLX steel's mapping is a reference, not a given).

## Probe `--mode mma` (stack)

- Before the checkpoint loop: an accuracy sweep (cache cap 40,960, `MQ_SWEEP_T`, k = 1…5) for both arms, plus the planted-token
  cases and negative controls below. Then per checkpoint and k: times of `native16` (k = 1 SDPA / k ≥ 2 `joint_attention`),
  `tq4_production` (singleton / `per_query_attention`), `mq_best` (`dev/m72_mq_decode.py`, min of G = 2 / 1), `mma_tq4`,
  `mma_n16`; per arm its error vs the fp32 reference (below) and the production path's error; `plan_blocks` output; `eff_GBps`.
- fp32 reference per query: TQ4 — `codec.dequantize` of K/V in fp32, exact softmax attention over t < lengths[j]; native16 — the
  bf16 K/V cast to fp32, same. Error metric: max |out − ref| / max |ref| over the block ("rel error").
- JSON: `meta.mode = "mma"`, `meta.fork`, `meta.mma_accuracy` (sweep rows, controls), `checkpoints[].mma[k]`. Existing modes
  unchanged.
- `m72_run_mma.sh <out_dir>`: two passes `mma-1`, `mma-2`, 600 s idle between, exit code = first failing pass (11 / 12), never
  masked.
- `m72_mma_report.py <run_dir>` → stdout Markdown (`benchmark/results/m72/MMA.md`, GENERATED header): accuracy table; per-layer
  times (T, k, the five arms, mma_tq4 / tq4_production, mma_tq4 / native16, mma_n16 / native16); pass-to-pass drift; projections
  for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` with `m72_mq_report`'s method and `PICK_BASELINE`: MTP ON k = 3 for TQ4 +
  mma vs shipped native16, native16 + mma vs shipped native16, TQ4 + mma vs native16 + mma; MTP OFF (k = 1: best of mq / mma for
  TQ4, best of SDPA / mma for native16).

### JSON schema (`--mode mma`)

```
meta: {..existing.., "mode": "mma", "fork": {...}, "mma_accuracy": {
  "rows": [{"T": int, "k": int, "arm": "mma_tq4"|"mma_n16", "case": "random"|"planted",
            "rel_err": float, "prod_rel_err": float, "allclose": bool, "finite": bool, "pass": bool}],
  "controls": [{"name": "N1"|"N2"|"N3", "arm": "mma_tq4"|"mma_n16", "rel_err": float, "pass": bool}],
  "n": int, "n_pass": int}}
checkpoints[]: {"T": int, "bytes": {"tq4_kv": int, "native16_kv": int}, "plan": {"blocks": int, "tokens_per_block": int},
  "power": {...}, "peak_GB": float, "mma": {"1".."5": {
    "lengths": [int], "native16": TIMING, "tq4_production": TIMING, "mq_best": TIMING + {"G": int},
    "mma_tq4": TIMING, "mma_n16": TIMING,
    "accuracy": {"mma_tq4": ACC, "mma_n16": ACC}}}}
TIMING = {"median_ms": float, "min_ms": float, "n": int}   (the existing timeit())
ACC = {"rel_err": float, "prod_rel_err": float, "allclose": bool, "finite": bool, "pass": bool}
```

`pass` = A1 (and `finite`). A control row's `pass` is A1 evaluated on the control; A3 requires it False.

### Report formulas

Passes = `mma-1.json`, `mma-2.json` in the run dir, whichever exist; times = mean over passes of `median_ms`. Projections use
`m72_probe_report.{LAYERS, PICK_BASELINE, VERIFY_K, interp}`, interpolating over sub-cap checkpoints only (T < 262,144), at the
`PICK_BASELINE` contexts; e = `PICK_BASELINE["emitted_per_round"]`:
- MTP ON (k = VERIFY_K): fixed = e / dd · 1e3 − LAYERS · native16(T, k); tok/s(arm) = e / (fixed + LAYERS · arm(T, k)) · 1e3, dd =
  `decode_on_tps[T]`. Rows: TQ4 today (`tq4_production`), TQ4 + mma (`mma_tq4`), native16 + mma (`mma_n16`); ratios vs dd and
  TQ4 + mma vs native16 + mma.
- MTP OFF (k = 1): fixed = 1e3 / dd − LAYERS · native16(T, 1); tok/s(arm) = 1e3 / (fixed + LAYERS · arm), dd = `decode_off_tps[T]`.
  Arms: TQ4 best = min(`mq_best`, `mma_tq4`), native16 best = min(`native16`, `mma_n16`).
- Accuracy section: per pass, sweep n_pass / n, checkpoint passes, each control with its `pass` (must be False).

## Acceptance criteria (pre-registered, S20-P10)

- A1 Accuracy, each arm, every sweep case and every checkpoint: rel error ≤ 2 × max(the production path's rel error, 2⁻⁸) and
  `mx.allclose(out_fp32, ref, atol=3e-2, rtol=3e-2)` (the `joint_v1` test tolerance). Production path: TQ4 singleton /
  `per_query_attention`; native16 `scaled_dot_product_attention` per query.
- A2 Planted-token masking: a case where one key per query dominates attention (aligned with that query, large norm) at position
  lengths[j] − 1 and a dominant key at position lengths[0] (visible only to j ≥ 1): A1 holds on both arms.
- A3 Negative controls fail A1 on both arms: N1 `_kv_head_shift=1`; N2 lengths + 1 (leak) and N3 lengths − 1 (drop), each on the
  planted case.
- A4 No NaN / Inf for any sweep case, including k = 1, lengths at tile and block boundaries (`MQ_SWEEP_T` straddles), and T not a
  multiple of Tt.
- A5 No layout copy: the kernel's K/V inputs are the full-cap buffers themselves (checked by identity / shape = cap in a test).
- A6 Tests: fork dev tests pass on this box's GPU; stack suite passes or fails only as on the baseline; `m72_mma_report.py` tested
  on synthetic JSON.
- A7 A `--mode mma --max-t 32768` smoke completes with A1–A4 recorded in its JSON.

## Non-goals

Production wiring, `mtp_verify_scan` value, registry, k > 5, batch > 1, other shapes / codecs (affine, PolarQuant, 4.5-bit),
Neural Accelerator tensor ops (P2′), prefill, bit-identity, tuning beyond a working default.

## Assumptions (designer)

- Metal `simdgroup_matrix` with fp32 accumulation compiles in `mx.fast.metal_kernel` (MLX 0.32.4) on `applegpu_g17s`.
- Threadgroup memory ≤ 32 KB per threadgroup suffices (e.g. Tt = 16: K 8 KB + V 8 KB half, Q ≤ 15 KB half).
- The production pass-2 kernel accepts any Blocks ≥ 1 (its loop strides blocks by 32 simdgroups).

## Open questions

None for the operator. Tiling (Tt, block policy, fragment types) is the implementer's within the accuracy criteria.
