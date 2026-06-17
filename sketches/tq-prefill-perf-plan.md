# Plan — TurboQuant Prefill Performance (Fused / LUT Attention Kernel)

**Status:** Not started. Gated on the uniform-vs-TQ 200K viability spike (see
`256k-prefill-kernels-plan.md` §5) — if uniform-4bit is good enough at 200K, this plan
becomes a quality-upgrade backlog item rather than a blocker.

**Goal:** make TQ prefill fast enough to be viable at 200K+ context. Today a single 200K TQ
prefill projects to ~1.5–4+ hours; the target is **minutes**, comparable to the uniform fused
path the owner has run before.

---

## §0 Context and relationship to the 256K plan

The TQ prefill **MEMORY** problem is already solved. Phase 1 (commit c72a82c) rewired the
dispatch so TQ prefill routes through `quantized_attention` instead of the full-KV
`dequantize()` spike — no OOM, verified to 80K. This plan is the **SPEED** follow-up. It is
"Fix B.2" from the sibling doc, promoted out of that doc's phase list into its own document
because the work is large enough to warrant it.

Locked decision, do not re-litigate: **TQ is the long-context QUALITY choice.** This plan is
purely about making it fast enough to use. It does not reopen the KV-scheme decision — that
was settled in `256k-prefill-kernels-plan.md` §0.

The sibling doc — `sketches/256k-prefill-kernels-plan.md` — owns the memory fix, the
uniform-vs-TQ spike, the broader phase plan, and the fork/submodule operating rules (its §4).
This doc references all of that rather than repeating it. Read the sibling first if you are
picking this up cold.

---

## §1 Diagnosis — why `quantized_attention` is slow

This is an **orchestration / fusion problem, not an algorithmic one.** The math is fine; the
way MLX is driven around it is the bottleneck. Three compounding causes:

1. **A forced `mx.eval(output, normalizer, max_score)` between every K-tile.** Each `mx.eval`
   is a hard GPU sync plus a Python round-trip. At 200K that is roughly **98 K-tiles × 32
   Q-blocks × N_full-attention-layers × ~390 prefill chunks** = millions of tiny serialized
   dispatches. This is latency-bound, and it is the dominant cost. The online-softmax running
   max and normalizer genuinely must be computed in sequence — but correctness does **not**
   require an `mx.eval` between tiles. MLX builds a lazy graph and the eval is there only to
   cap transient memory by forcing the graph to materialize. So eval frequency is a tunable
   throughput-vs-peak-memory tradeoff, not a correctness requirement. That distinction is the
   whole opening for Tier 0.

2. **Tiny tiles.** `prefill_query_block_size = 16` and `prefill_key_chunk_size = 2048`
   (constants in `TurboQuantKVCache`, `turboquant.py`). The GPU is never saturated — each
   dispatch processes too little work, so per-micro-op dispatch overhead dominates.

3. **No fused dequant.** The TQ rotation plus codebook reconstruction runs as separate MLX
   graph ops per tile, rather than fused inside one kernel. More graph nodes, more dispatches,
   more sync surface.

**Measured evidence** (from the Phase 1 probe, recorded in the sibling doc §5): prefill
throughput falls **73 → 30 tok/s over 8K → 80K**, with the per-token cost *rising*, not
holding flat. That makes total prefill cost roughly **O(T²)**, which projects to **~1.5–4+
hours** for a single 200K prefill. That is a batch job, not interactive load time.

---

## §2 The tiered fix (cheapest first)

### Tier 0 — Measure and tune (hours, no new kernel)

Before building anything, quantify how much of the loss is pure sync/dispatch overhead. Three
knobs, all in-fork:

- Raise `prefill_query_block_size` (16 → 64/128) and `prefill_key_chunk_size` (2048 → 8192+)
  so each dispatch carries more work and the GPU actually saturates.
- Call `mx.eval` periodically (every K tiles) instead of every tile, and sweep K to find the
  throughput-vs-peak-memory sweet spot. This is the direct lever on cause #1.
- Measure prefill tok/s at a fixed context (e.g. 32K and 64K) against the current baseline so
  the gain is attributable.

This is in-fork code in `turboquant.py` — propose the diff before commit (operating rules in
the sibling doc §4). It could claw back a large multiple on its own, and it tells us whether a
kernel is even needed. And the spike (sibling §5) may show uniform-4bit is good enough,
deferring all of this.

### Tier 1 — T-tiled fused `prefill_attention` in MLX (~1 day)

`prefill_attention` (the Prod-key fused path in `turboquant.py`) already computes scores as
larger fused MLX ops — a full `L×T` einsum, which is fast — **but** it materializes the entire
`[B*H*R, L, T]` scores matrix at once. That is a ~16.8 GB spike at 256K with L=512.
Restructure it to **tile over the T (context) dimension with online softmax.** The result has
the big-matrix throughput *and* bounded memory, with **no Metal shader required**. It is the
natural stepping stone between the slow K-tile loop and a hand-fused kernel.

Limitation: it is still MLX-graph-bound. It will beat `quantized_attention` but will not match
a true hand-fused kernel.

**Note:** enabling this path also requires the Prod codec (`mode="prod"`) — see B.1 in the
sibling doc. `_ensure_codecs` currently hardcodes `mode="mse"`, so the Prod-key fused path is
unreachable at runtime until `mode` is made configurable.

### Tier 2 — `mx.fast.metal_kernel` flash attention with in-kernel TQ dequant (the real fix)

Fused Metal **without** a separate build system. MLX exposes `mx.fast.metal_kernel(...)`: pass
a Metal shader source string plus input/output shapes and dtypes plus grid/threadgroup config,
and MLX JIT-compiles it and runs it directly on MLX arrays, sharing MLX's allocator and
streams. No Xcode project, no `.metallib`, no separate compilation step. This is how custom ops
ship in mlx-examples.

Two tricks move the hard math **out** of the kernel:

- **Rotate Q on the host, not K in the kernel.** TQ stores `quantize(R·K)` for an orthogonal
  rotation R. Since `Q·K = (R·Q)·(R·K)`, rotate Q once per chunk on the host — a cheap `[L,D]`
  transform — and the kernel works entirely in rotated space. It never runs the Hadamard / FWHT
  butterfly itself.
- **Express the score as a LUT-accumulate** (the T-MAC / LUT-GEMM idea). With a codebook,
  `K_d = codebook_d[code_d]`, so `score = Σ_d (RQ)_d · codebook_d[code_d]`. Precompute, per
  Q-block, a table `LUT[d][level] = (RQ)_d · codebook_d[level]` — e.g. 128 dims × 8 levels at
  3-bit = **1024 entries per query** — cache it in threadgroup memory, and the inner loop over
  context tokens becomes **gather-by-code-index + accumulate + online softmax.** The win is
  **bandwidth and fusion:** the kernel reads 3-bit codes directly (≈5× less K-read traffic than
  16-bit dequantized K), never materializes a scores matrix, and has no per-tile sync. FLOP
  count is similar to a plain dot product — the speedup comes from bandwidth and from removing
  the orchestration overhead, **not** from doing fewer multiplies.
- The **Prod codec** adds one rank-1 sign-correction term (`+ s·(b·RQ)`, where b is the 1-bit
  binary direction). That is also a lookup / cheap term in-kernel.

This is the right long-term answer for Apple Silicon: fused, memory-flat, GPU-saturating, and
inside MLX's Python/buffer model. The effort is real — kernel development plus numerics
validation — but it is the actual unlock.

### Bonus — architectural sidestep (Qwen3.6 hybrid arch)

Qwen3.6 (`qwen3_5`) is mostly **GatedDeltaNet** (linear attention, recurrent state — no KV
cache, cheap prefill) with only a **few** full-attention layers. The entire TQ prefill cost
lives in those few layers. So: keep just those layers' KV in fp16/uniform during prefill
(fused fast SDPA), and TQ-compress only for the decode-retained cache — `decode_attention` is
already a fused Metal kernel. This could sidestep TQ prefill compute almost entirely. Cost:
bounded extra fp16 KV during prefill for those few layers (~1 GB/layer × a handful of layers).
Possibly the cheapest "fix" of all if the full-attention layer count is low. **Measure that
count first.**

---

## §3 Recommended sequencing

1. **Run the spike first** (sibling doc §5). It may make uniform the interim answer and
   de-risks everything downstream.
2. **Tier 0** to quantify how much of the loss is pure sync/dispatch overhead.
3. **Tier 1** (T-tiled `prefill_attention`) as the buildable near-term win — it also removes
   the scores-matrix memory spike.
4. **Tier 2** (`mx.fast.metal_kernel` + LUT) as the real long-term kernel.
5. **Measure the hybrid-arch sidestep early.** If Qwen has few full-attention layers it may
   beat all of the above on effort-vs-payoff.

---

## §4 Verification / acceptance criteria

- **Numerics:** max-abs-diff of the new path vs the dequant/SDPA reference on a short prompt is
  small. Reuse the existing test pattern — e.g. `test_turboquant_prefill_*` in
  `mlx_vlm/tests/test_turboquant.py`.
- **Prefill speed:** prefill tok/s at 200K within striking distance of the uniform fused path —
  minutes, not hours.
- **Memory:** peak flat across context, with no scores-matrix spike.
- **End-to-end correctness:** needle-in-haystack at 200K still retrieves
  (`benchmark/needle_256k.py`).

---

## §5 Key files and references

- `../mlx-vlm/mlx_vlm/turboquant.py` — `TurboQuantKVCache`, with the tile-size constants
  `prefill_query_block_size`, `prefill_key_chunk_size`, and `decode_key_chunk_size`;
  `quantized_attention` (the slow Python K-tile loop — the Tier 0 target); `prefill_attention`
  (the fused Prod path — the Tier 1 target, needs T-tiling); `_ensure_codecs` (hardcodes
  `mode="mse"`); `decode_attention` (already a fused Metal kernel).
- `../mlx-vlm/mlx_vlm/models/base.py` — the `scaled_dot_product_attention` dispatch. Fix A
  landed here; the new kernel wires in here too.
- `mx.fast.metal_kernel` — the MLX custom-Metal-kernel API (Tier 2). Reference mlx-examples for
  usage patterns.
- `benchmark/needle_256k.py` — the 200K end-to-end check.
- Background on the LUT-matmul technique: **T-MAC / LUT-GEMM** (low-bit matmul as table
  lookup).
- Sibling: `sketches/256k-prefill-kernels-plan.md` — the memory fix, the spike, and the phase
  plan. The operating rules and fork workflow live there in its §4.
