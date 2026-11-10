# Spec: M72 P2′ stage 1 (b′) — fused TQ4 dequantize into a reused scratch + MLX fused SDPA (C314; four-eyes strict)

Status: v1, 2026-11-10 (session 20). Designer: the session. Records: `docs/open-questions.md` C314, S20-P14, C311;
`benchmark/results/m72/{REPORT.md, PROBE.md}`; design-review findings on the superseded in-kernel design:
`docs/reviews/m72-p2-flash-prefill/` (those that apply here are folded in below).

## Goal (verbatim in every brief)

TurboQuant 4 (TQ4) prefill attention for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`'s shapes runs at 0.35× native16 at 260K
because the shipped TQ4 path never reaches the M5 Max Neural Accelerators, while native16's fused SDPA (`fused_v1`) does. The
probe's P1 (dequantize the layer's K / V to bf16 in the codec's rotated space with generic MLX ops, then MLX's fused SDPA) already
puts TQ4 prefill on the accelerators at 0.83× (its generic-op dequantize costs 43–60 ms per 260K chunk). Build the fused form of
P1: one Metal kernel that dequantizes a layer's TQ4 K / V for tokens [0, T) into a bf16 scratch in the rotated space, reused across
layers (one layer at a time; C314 allows ≈ 1.07 GB at 256K, never the whole KV cache), followed by MLX's own fused SDPA; show it
is bit-identical to P1-rotated, accurate to the pre-registered tolerance, and measure it per 512-token chunk against `fused_v1`,
today's TQ4 prefill and P1, with the prefill-time projection, so the operator can see how close TQ4 prefill gets to native16
parity. Solving it means: the kernel and its measurement exist, the criteria below hold, and the probe + generated report
produce the tables. No speed bar.

## Scope

1. Fork `../mlx-vlm`: new `dev/m72_scratch_prefill.py` (dev only, never imported by `mlx_vlm/`); GPU tests
   `dev/tests/test_m72_scratch_prefill.py` (Metal required; skip with reason when unavailable).
2. Stack: `benchmark/spikes/m72_tq4_probe.py` gains `--mode p2s`; generator `benchmark/spikes/m72_p2s_report.py` →
   `benchmark/results/m72/P2S.md`; launcher `benchmark/spikes/m72_run_p2s.sh`; tests `benchmark/bench/tests/test_m72_p2s_report.py`
   (no MLX, synthetic JSON) and `benchmark/bench/tests/test_m72_p2s_probe_gpu.py` (`pytest.importorskip("mlx.core")`; run with the
   fork venv; added to `benchmark/gate/stack.skips.txt` as a module-level skip, as `test_m72_mma_probe_gpu`).

## Settled constraints

- (operator, C314) A per-layer bf16 scratch of one layer's K / V (≈ 1.07 GB at 256K) reused across layers is allowed; the whole KV
  cache must never be materialized. (operator, C311 / C312) Accuracy standard = an existing path's tolerance; no MLX rebuild.
- (designer) Prototype only: no production dispatch, registry or server change. Batch 1; 24 q / 4 kv heads (R = 6), head dim 256,
  bf16 queries; TurboQuant MSE 4-bit keys and values (the probe's `TurboQuantKVCache(bits=4, ...)`).
- (designer) The dequantize kernel reads the full-cap preallocated state in place (`norms` (1, n_kv, cap) fp16, `indices`
  (1, n_kv, cap, 32) uint32, dim d at bits [4d, 4d + 4) of a token's words, LSB first; per-head stride = capacity).
- (designer) Probe rules unchanged: power, idle-GPU gates before measured work; synthetic K / V; `timeit`; caches preallocated to
  262,144; `CHECKPOINTS`; two passes with opposite arm order.

## Interfaces

```python
# dev/m72_scratch_prefill.py
def dequant_rotated(cache, T, *, _kv_head_shift=0) -> tuple[mx.array, mx.array]
    # K_rot, V_rot, each (1, n_kv, T, D) bf16, contiguous: X[0, h, t, d] = bf16(float(codebook[idx(h', t, d)]) * float(norm(h', t)))
    # with h' = (h + _kv_head_shift) mod n_kv, codebook / norm / idx of the key (resp. value) codec and state, tokens [0, T).
def scratch_prefill_tq4(cache, queries, scale, *, _kv_head_shift=0) -> mx.array
    # queries (1, 24, L, 256) bf16 = the chunk at positions [T - L, T), T = cache.offset (the chunk already appended).
    # = value_codec._rotate_inverse(SDPA(key_codec.prepare_queries(queries).astype(bf16), K_rot, V_rot, scale, mask="causal",
    #   force_fused=True).astype(f32)).astype(queries.dtype), with (K_rot, V_rot) = dequant_rotated(cache, T).
```

- Preconditions (assert): 1 ≤ L ≤ T ≤ cache.offset; 4-bit MSE codec on both; batch 1.
- `dequant_rotated` computes exactly the probe's P1 `deq_rot()` expression (`(mx.take(codebook, idx) * norms[..., None]).astype(bf16)`),
  so its output must be bit-identical to it, and `scratch_prefill_tq4` bit-identical to the probe's `rot_fused()`.
- Reuse: no explicit buffer is kept; each call returns fresh arrays and MLX's buffer cache recycles the previous layer's freed
  scratch. A5 measures that the steady-state peak over a sequence of layers stays at about one scratch.

## Design (settled by the designer unless marked free)

- One fused Metal kernel (`mx.fast.metal_kernel`) writes both outputs in one launch; thread mapping free (e.g. one thread per
  (head, token, 8 dims) reading one packed word, or a simdgroup per token row with coalesced 128-bit loads); the codebook in
  threadgroup memory or registers (free; spike F3: lookup mechanism matters little). fp32 product, one rounding to bf16 (the
  bit-identity contract fixes this).
- Rotation stays outside the kernel: queries rotated once per chunk, the output inverse-rotated once (exact, P1's derivation).
- No change to MLX's SDPA call: the same arguments as P1's `rot_fused()`.

## Probe `--mode p2s` (stack)

- Exactness sweep (cache cap 40,960; T ∈ {1, 511, 512, 4096, 8193, 32768, 40000}): `dequant_rotated` bit-identical to `deq_rot()`
  on K and V; `scratch_prefill_tq4` bit-identical to `rot_fused()` for L ∈ {512, 37, 1} (L ≤ T); negative control N1
  `_kv_head_shift=1` on KV-head-distinct data (each KV head scaled differently) must not be bit-identical and must fail A1.
- Per checkpoint (`CHECKPOINTS`; the chunk = the last 512 tokens ending at T): **timed arms first, in the pass's arm order**:
  `native16_fused_v1` (the shipped path, as the probe's `full` mode), `tq4_production` (today's TQ4 prefill on the state at T),
  `p1_rotated` (the probe's `rot_fused()`), `p2s` (`scratch_prefill_tq4`, the whole public function), `p2s_dequant_only`
  (`dequant_rotated`). Then, untimed: bit-identity of `p2s` vs `p1_rotated` (all heads), and A1 for `p2s` on query heads
  {0, 11, 23} vs the fp32 reference, computed one head at a time from K / V sliced to [0, T) and released before the next
  checkpoint's timings.
- fp32 reference: `codec.dequantize` of the state sliced to T (unrotated), exact causal softmax (query at T − L + i sees tokens
  ≤ T − L + i). Production comparator for A1: `tq4_production` on the same state, i.e. on a real slice to T (the cache holds exactly T).
- A5 window: on a fresh cache state at T = 262,144 run 16 consecutive `scratch_prefill_tq4` calls (distinct queries, one graph per
  call, as layers would), with `mx.reset_peak_memory()` immediately before and the peak read immediately after; report
  `peak − active_before`.
- JSON: `meta.mode = "p2s"`, `meta.fork` (head + dirty), `meta.arm_order`, `meta.p2s_kernel` (thread mapping, codebook placement),
  `meta.p2s_exactness` {rows: [{T, L, what, bit_identical}], controls: [{name, bit_identical, rel_err, pass_a1}], n, n_ok};
  `checkpoints[]`: {T, bytes, power, peak_GB, p2s: {arm: TIMING}, p2s_vs_p1_bit_identical: bool, p2s_accuracy: {head: ACC}};
  `meta.p2s_memory` {T, layers: 16, peak_minus_active_GB, scratch_GB}. TIMING / ACC as in `docs/specs/m72-mma-verify.md`.
- `m72_run_p2s.sh <out_dir>`: as `m72_run_mma.sh` (exit 10 on existing `p2s-1.json` / `p2s-2.json`; pass 1 `--arm-order forward`,
  pass 2 `reverse`; 600 s idle; exits 11 / 12; mode 755).
- `m72_p2s_report.py <run_dir>` → stdout Markdown (GENERATED header; refuses passes whose `meta.fork.head`, `meta.mlx`,
  `meta.device.architecture`, `meta.p2s_kernel` or checkpoint lists differ): exactness and accuracy section; memory line; per-chunk
  table (T, the five arms, p2s / native16_fused_v1, p2s / tq4_production, p2s / p1_rotated, dequant share = p2s_dequant_only /
  p2s); pass drift; projection (below).
- Projection (per arm X, for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` at each `PICK_BASELINE["prefill_s"]` context N; the
  chunks end at T_j = 512·j, j = 1..N/512, times interpolated linearly in T over the sub-cap checkpoints, clamped at the ends):
  fixed = prefill_s(N) − 16 · Σ_j native16_fused_v1(T_j); t_X(N) = fixed + 16 · Σ_j X(T_j) + [X is a TQ4 arm] · 16 · (N/512) ·
  (append_tq4 − append_native16), the append terms the probe's measured `kv_append_chunk_ms` means at long context; report
  t_X(N) and native16 / t_X ratios for X ∈ {tq4_production, p1_rotated, p2s}. Check: t_native16 reproduces prefill_s(N).

## Acceptance criteria (pre-registered)

- A1 Exactness: every sweep row and every checkpoint: `dequant_rotated` bit-identical to `deq_rot()`, and `scratch_prefill_tq4`
  bit-identical to `rot_fused()`. Accuracy: on the checkpoint heads, rel error ≤ 2 × max(production rel error, 2⁻¹²) and
  `allclose(atol = rtol = 3e-2)` vs the fp32 reference, all finite (P1's accuracy, carried by bit-identity, re-checked).
- A2 Control: N1 is not bit-identical and fails the accuracy criterion; each named control present exactly once (extra named
  controls allowed).
- A3 Edges: T = 1, L = 1, L = 37, T not a multiple of any thread-mapping width: bit-identity holds, no NaN / Inf.
- A4 Memory: the 16-layer window's `peak − active_before` ≤ 1.25 × one scratch (2 · 4 · T · 256 · 2 B) + 0.25 GB.
- A5 In place: the kernel's inputs are the cache's full-cap state arrays themselves (no slice copy), checked in a test.
- A6 Tests pass; stack suite passes or fails only as on the baseline (the clean-clone gate).
- A7 `--mode p2s --max-t 32768` smoke completes with A1–A3 recorded.

## Non-goals

Production wiring, decode / verify, stages 2–3 (our own attention core; in-kernel unpack), batch > 1, other shapes or codecs,
tuning MLX's SDPA, a persistent explicitly-managed scratch buffer (the buffer cache provides reuse; A4 verifies it).

## Assumptions (designer)

- MLX's fused SDPA output depends only on its inputs (deterministic), so equal inputs give bit-identical outputs.
- The buffer cache recycles a freed bf16 scratch for the next call of the same size (A4 tests this rather than assuming it).

## Open questions

None for the operator.
