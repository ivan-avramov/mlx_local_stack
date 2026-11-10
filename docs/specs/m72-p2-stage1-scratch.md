# Spec: M72 P2′ stage 1 (b′) — fused TQ4 dequantize into a reused scratch + MLX fused SDPA (C314; four-eyes strict)

Status: v1.1, 2026-11-10 (session 20; v1.1 = the cold design review's adopted findings, applied once, not re-reviewed: fp16 scratch after a preflight, cap-sized scratch, per-layer evaluation, the memory criterion moved to the separate instrumented spike, projection units and terms, references and controls — ledger `docs/reviews/m72-p2-stage1/dispositions-report.md`). Designer: the session. Records: `docs/open-questions.md` C314, S20-P14, C311;
`benchmark/results/m72/{REPORT.md, PROBE.md}`; design-review findings on the superseded in-kernel design:
`docs/reviews/m72-p2-flash-prefill/` (those that apply here are folded in below).

## Goal (verbatim in every brief)

TurboQuant 4 (TQ4) prefill attention for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`'s shapes runs at 0.35× native16 at 260K
because the shipped TQ4 path never reaches the M5 Max Neural Accelerators, while native16's fused SDPA (`fused_v1`) does. The
probe's P1 (dequantize the layer's K / V to bf16 in the codec's rotated space with generic MLX ops, then MLX's fused SDPA) already
puts TQ4 prefill on the accelerators at 0.83× (its generic-op dequantize costs 43–60 ms per 260K chunk). Build the fused form of
P1: one Metal kernel that dequantizes a layer's TQ4 K / V for tokens [0, T) into an fp16 scratch in the rotated space, reused across
layers (one layer at a time; C314 allows ≈ 1.07 GB at 256K, never the whole KV cache), followed by MLX's own fused SDPA, evaluated once per layer; show its
dequantize is bit-identical to P1's (in fp16), accurate to the pre-registered tolerance, that its memory stays within the scratch
(separate instrumented spike), and measure it per 512-token chunk against `fused_v1`,
today's TQ4 prefill and P1, with the prefill-time projection, so the operator can see how close TQ4 prefill gets to native16
parity. Solving it means: the kernel and its measurement exist, the criteria below hold, and the probe + generated report
produce the tables. No speed bar.

## Scope

1. Fork `../mlx-vlm`: new `dev/m72_scratch_prefill.py` (dev only, never imported by `mlx_vlm/`); GPU tests
   `dev/tests/test_m72_scratch_prefill.py` (Metal required; skip with reason when unavailable).
2. Stack: `benchmark/spikes/m72_tq4_probe.py` gains `--mode p2s`; `benchmark/spikes/m72_p2s_memory.py` gains `--impl p2s`
   wiring to the new module and the A4 scenarios (SDPA-only baseline, growing T) — the designer owns this spike's instrument code; generator `benchmark/spikes/m72_p2s_report.py` →
   `benchmark/results/m72/P2S.md`; launcher `benchmark/spikes/m72_run_p2s.sh`; tests `benchmark/bench/tests/test_m72_p2s_report.py`
   (no MLX, synthetic JSON) and `benchmark/bench/tests/test_m72_p2s_probe_gpu.py` (`pytest.importorskip("mlx.core")`; run with the
   fork venv; added to `benchmark/gate/stack.skips.txt` as a module-level skip, as `test_m72_mma_probe_gpu`).

## Settled constraints

- (operator, C314) A per-layer scratch of one layer's K / V (≈ 1.07 GB at 256K) reused across layers is allowed; the whole KV
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
def dequant_rotated(cache, T, *, dtype=mx.float16) -> tuple[mx.array, mx.array]
    # K_rot, V_rot, each (1, n_kv, cap, D) `dtype` (cap = the state's capacity, so the buffer cache reuses one size for every
    # chunk; only tokens [0, T) are written and read): X[0, h, t, d] = dtype(float(codebook[idx(h, t, d)]) * float(norm(h, t)))
    # with the fp32 codebook and fp16 norm of the key (resp. value) codec and state; the product in fp32, one rounding.
def scratch_prefill_tq4(cache, queries, scale, *, dtype=mx.float16, _kv_head_shift=0) -> mx.array
    # queries (1, 24, L, 256) bf16 = the chunk at positions [T - L, T), T = cache.offset (the chunk already appended).
    # = value_codec._rotate_inverse(SDPA(key_codec.prepare_queries(queries).astype(dtype), K_rot[:, perm, :T], V_rot[:, perm, :T],
    #   scale, mask="causal", force_fused=True).astype(f32)).astype(queries.dtype), (K_rot, V_rot) = dequant_rotated(cache, T),
    #   perm = the KV heads rolled by `_kv_head_shift` (negative control only; 0 = identity).
def reference_dequant_rotated(state, T, codec, dtype) -> mx.array      # the generic-op form (P1's `deq_rot()`, explicit T)
def reference_prefill(cache, queries, scale, T, dtype) -> mx.array     # P1's `rot_fused()` with explicit T and dtype
```

- Preconditions (assert): 1 ≤ L ≤ T ≤ cache.offset; 4-bit MSE codec on both; batch 1.
- `dtype` = fp16 by default (preflight, `docs/reviews/m72-p2-stage1/`: P1 with a bf16 scratch has rel error up to 7.0e-3 vs the fp32
  reference at 8K, 2.1× TQ4 production's 3.5e-3, outside A1; with fp16 4.0e-3, 0.61 of the bound); bf16 kept as an option.
- MLX's `mask="causal"` with L queries over T keys aligns the queries to the last L positions (query i sees key j iff
  j ≤ i + T − L); the tests check it against an explicit mask.
- Reuse: each call returns fresh cap-sized arrays; MLX's buffer cache recycles the previous layer's / chunk's freed scratch of the
  same size. The caller must evaluate once per full-attention layer during TQ4 prefill (memory spike: one lazy 16-layer graph
  holds ≈ 6.4 scratches). The probe and the memory spike do so; production wiring (1.3) must too.

## Design (settled by the designer unless marked free)

- One fused Metal kernel (`mx.fast.metal_kernel`) writes both outputs in one launch; thread mapping free (e.g. one thread per
  (head, token, 8 dims) reading one packed word, or a simdgroup per token row with coalesced 128-bit loads); the codebook read
  as fp32 at the multiply (threadgroup memory or registers, never downcast before the product); fp32 product, one rounding to
  `dtype` (the bit-identity contract with the reference fixes this). Tokens ≥ T in the cap-sized outputs are left unwritten.
- Rotation stays outside the kernel: queries rotated once per chunk, the output inverse-rotated once (exact, P1's derivation).
- No change to MLX's SDPA call: the same arguments as P1's `rot_fused()`.

## Probe `--mode p2s` (stack)

- Exactness sweep (cache cap 40,960, each cache filled to offset = T; T ∈ {1, 511, 512, 4096, 8193, 32768, 40000}, those ≤
  `--max-t`): `dequant_rotated` bit-identical on [0, T) to `reference_dequant_rotated` for K and V in fp16 (and bf16);
  `scratch_prefill_tq4` vs `reference_prefill` (fp16) bit-identity recorded as a diagnostic for L ∈ {512, 37, 1} (L ≤ T).
  Negative control N1 `_kv_head_shift=1` on planted data where each KV head's values are a distinct constant (e.g. 1, 4, 16, 64
  times the head's norm scale) at T = 8193, L = 37: must fail A1.
- Per checkpoint (`CHECKPOINTS`; the chunk = the last 512 tokens ending at T): **timed arms first, in the pass's arm order**:
  `native16_fused_v1` (as the probe's `full` mode), `tq4_production` (today's TQ4 prefill on the state at T), `p1_rotated_bf16`
  (the probe's `rot_fused()`), `p2s` (`scratch_prefill_tq4`, the whole public function, fp16), `p2s_dequant_only`
  (`dequant_rotated`, a diagnostic). Then `chain16` timings at the 262,144 checkpoint only: 16 chained `scratch_prefill_tq4` calls
  over 16 distinct caches at T (each layer's queries depend on the previous output) as one lazy graph vs evaluated per layer — the
  cost of the per-layer evaluation. Then, untimed: A1 for `p2s` on query heads {0, 6, 12, 18} (one per KV head) vs the fp32
  reference, computed one head at a time from K / V sliced to [0, T) and freed (`del`, `mx.clear_cache()`) before the next
  checkpoint's timings; `p2s` vs `reference_prefill` bit-identity (diagnostic).
- fp32 reference: `codec.dequantize` of the state sliced to T (unrotated), exact causal softmax (query at T − L + i sees tokens
  ≤ T − L + i), per head. Production comparator for A1: `tq4_production` on the same state (the cache holds exactly T).
- JSON: `meta.mode = "p2s"`, `meta.fork` (head + dirty), `meta.arm_order`, `meta.p2s_kernel` (thread mapping, codebook placement,
  dtype), `meta.p2s_exactness` {rows: [{T, L, what, dtype, bit_identical}], controls: [{name, rel_err, pass_a1}], n, n_ok};
  `checkpoints[]`: {T, bytes, power, p2s: {arm: TIMING}, chain16 (262,144 only): {lazy: TIMING, per_layer_eval: TIMING},
  p2s_vs_reference_bit_identical: bool, p2s_accuracy: {head: ACC}}. TIMING / ACC as in `docs/specs/m72-mma-verify.md`.
- `m72_run_p2s.sh <out_dir>`: as `m72_run_mma.sh` (exit 10 on existing `p2s-1.json` / `p2s-2.json`; pass 1 `--arm-order forward`,
  pass 2 `reverse`; 600 s idle; exits 11 / 12; mode 755).
- `m72_p2s_report.py <run_dir>` → stdout Markdown (GENERATED header; refuses passes whose `meta.fork.head`, `meta.mlx`,
  `meta.device.architecture`, `meta.p2s_kernel` or checkpoint lists differ, or whose arm orders are not one forward + one
  reverse): exactness / accuracy section; per-chunk table (T, the five arms, p2s / native16_fused_v1, p2s / tq4_production,
  p2s / p1_rotated_bf16); the chain16 line (lazy, per-layer, ratio); pass drift; the projection:
- Projection, per arm X ∈ {tq4_production, p1_rotated_bf16, p2s}, for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` at each
  `PICK_BASELINE["prefill_s"]` context N (seconds): with `m72_probe_report`'s `interp` over the sub-cap checkpoints (its linear
  extrapolation below the first), attn_X(N) = Σ_{j=1..N/512} interp(X, 512·j) / 1000 seconds (as `prefill_attn_total_s`), and
  append_X = the two-pass mean of `kv_append_chunk_ms` (`tq4_mean_last64` for TQ4 arms, `native16_mean_last64` for native16) at the
  260,096 checkpoint / 1000: fixed = prefill_s(N) − 16 · attn_native16(N) − 16 · (N/512) · append_native16;
  t_X(N) = fixed + 16 · attn_X(N) + 16 · (N/512) · append_X; report t_X(N) and prefill_s(N) / t_X(N). The probe records
  `kv_append_chunk_ms` in `--mode p2s` as `full` mode does. The report test checks the formula on hand-computed synthetic data.
- Memory: not measured in the perf run (operator, 2026-11-10). The separate spike `benchmark/spikes/m72_p2s_memory.py` (two
  per-process instruments, fresh process per scenario, known positives) runs on the accepted kernel (`--impl p2s`), A4 below.

## Acceptance criteria (pre-registered)

- A1 Accuracy: on every checkpoint head (and the sweep's L = 512 rows), `p2s` rel error ≤ 2 × max(production rel error, 2⁻¹²)
  and `allclose(atol = rtol = 3e-2)` vs the fp32 reference, all finite. Fidelity: `dequant_rotated` bit-identical to
  `reference_dequant_rotated` on [0, T) in every sweep row (fp16 and bf16).
- A2 Control: N1 fails A1; each named control present exactly once (extra named controls allowed).
- A3 Edges: T = 1, L = 1, L = 37, T ∈ {511, 8193, 40000} (not multiples of any power-of-two mapping width ≤ 32): fidelity holds,
  no NaN / Inf; the causal alignment test passes.
- A4 Memory (separate spike, `--impl p2s`, T = 262,144, 16 layers): (i) the chained 16-layer forward evaluated per layer peaks
  ≤ 1.25 × one scratch above the SDPA-only baseline scenario (the same forward with the scratch replaced by a resident
  pre-dequantized copy, so SDPA's own transients cancel) on both instruments; (ii) a growing-T scenario (chunks of 512 appended
  from 0 to 262,144 over 16 layers, per-layer evaluation) ends with peak ≤ 1.25 scratches above the caches (OS ledger, which
  includes MLX's buffer cache); (iii) the known positives read 1.00 ± 0.05 and 16.00 ± 0.5 scratches.
- A5 In place: the kernel's inputs are the cache's full-cap state arrays themselves (passed unsliced; the test asserts the arrays
  passed are the state's arrays and that a sentinel written past T in the state does not change the [0, T) output).
- A6 Tests pass; stack suite passes or fails only as on the baseline (the clean-clone gate).
- A7 `--mode p2s --max-t 32768` smoke completes with A1–A3 recorded (sweep rows above `--max-t` skipped and listed as skipped).

## Non-goals

Production wiring, decode / verify, stages 2–3 (our own attention core; in-kernel unpack), batch > 1, other shapes or codecs,
tuning MLX's SDPA, a persistent explicitly-managed scratch buffer (the buffer cache provides reuse; A4 verifies it), memory
measurement inside the perf run.

## Assumptions (designer)

- MLX's fused SDPA output depends only on its inputs (deterministic), so equal inputs give bit-identical outputs.
- The buffer cache recycles a freed scratch for the next call of the same size (A4 tests this rather than assuming it).
- For D = 256, `prepare_queries` / `_rotate_inverse` are single Hadamard-transform dispatches (RHT); the projection assumes it.

## Open questions

None for the operator.
