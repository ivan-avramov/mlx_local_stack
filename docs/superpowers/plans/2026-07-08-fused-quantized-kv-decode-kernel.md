# Fused Quantized-KV DECODE Kernel (GQA tile-reuse) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make quantized-KV **decode** at least as fast as fp16 SDPA (ideally faster, since 3–4-bit KV moves ~4–5× less DRAM) by fixing the `R×` GQA-redundant read in the MSE decode kernels — turning turboquant KV from a memory-for-speed *trade* into a win on both axes.

**Architecture:** Decode (`L=1`) is matrix-*vector* and **bandwidth-bound**, so this is NOT a matrix-silicon problem — it's backend-agnostic (same kernel on M5 and M2–M4; no TensorOps/simdgroup split). The fix is GQA **tile-reuse**: load each kv-head's packed K/V tile once into threadgroup memory and serve all `R` query-heads from it, instead of re-reading it `R` times from DRAM. Productionize the spike-C prototype (occupancy-preserving token-block split, peak G≈2 heads/threadgroup) into the live `_fused_mse_decode_kernel` and the 2-pass pair, behind a capability gate + YAML kill-switch.

**Tech Stack:** `mx.fast.metal_kernel` Metal kernels in `../mlx-vlm/mlx_vlm/turboquant.py`; `pytest` (`test_turboquant.py`); mlx-serve registry threading. Parent design: `docs/superpowers/specs/2026-06-17-unified-fused-quantized-kv-attention-design.md` (§4 flash core, §6 spikes C–E, §8 numerics/TDD, §9 config). Scope = **decode only** (Phase 2's decode half). Prefill MMA (simdgroup/TensorOps), the Prod codec, and gemma4 generality are **follow-on plans** — deferred because APC already amortizes agentic prefill.

## Global Constraints

- **Fork edits only:** all code in `../mlx-vlm` (never `src/mlx-vlm`). Test from the stack dir: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ...`. Propose fork commits for approval before committing/pushing; bump the stack submodule + `git submodule update --force` on the boxes to deploy.
- **TDD reference of record (§8):** full fp32 dequant of KV → `mx.fast.scaled_dot_product_attention` in fp32; assert tight **max-abs-diff** (reuse `test_turboquant.py::test_turboquant_decode_attention_matches_dequantized_attention`). Existing accumulation is already fp32 — do NOT loosen it.
- **Test matrix (decode subset):** `head_dim ∈ {256, 128, 96(non-pow2)}`, `GQA ∈ {1, 4, 6}`, `kv_bits ∈ {3, 4}`, `L=1`, `T` spanning the block-split thresholds (2048 / 8192 / 32768 / 65536) and 256K, codec MSE.
- **Backend-agnostic:** decode uses NO MMA (matrix-vector). One kernel serves M5 + M2–M4. Validate on **M5 first** (deploy target), then **confirm on M2–M4**.
- **Quality gate:** needle retrieval ≥0.85 across the length ladder unchanged; numerics within the max-abs-diff bound. Decode is lossless-scheme (this changes the *kernel*, not the codec math).
- **Kill-switch:** behind the eligibility gate + a per-model YAML flag (default auto-on for eligible TQ models; `false` forces the old kernel). One model per box; restart the mlx-serve manager to load new code; confirm no stray eval/generate/needle procs first.
- **kv_bits × GPU gen:** M2–M4 fine at 3-bit (custom dequant). On M5, 3-bit decode is fine too (decode is custom-dequant, not TensorOps); TensorOps' 4-bit-native preference is a *prefill* concern, out of scope here. Test both 3 and 4.

---

### Task 1: TDD scaffold — fp32 reference + GQA/bits decode matrix (RED)

**Files:**
- Test: `../mlx-vlm/mlx_vlm/tests/test_turboquant.py` (extend).

**Interfaces:**
- Produces: `test_decode_gqa_matches_fp32_reference[dim,gqa,bits,T]` — the correctness net every later task must keep green.

- [ ] **Step 1: Write the parametrized failing test** modeled on `test_turboquant_decode_attention_matches_dequantized_attention` (line 238): build a `TurboQuantKVCache`, fill `T` tokens, run `scaled_dot_product_attention` (routes to `decode_attention`) vs `mx.fast.scaled_dot_product_attention` on the fp32-dequantized KV; assert `max(abs(q-ref)) < TOL`. Parametrize over `dim∈{256,128,96}`, `gqa∈{1,4,6}`, `bits∈{3,4}`, `T∈{512, 4096, 40000}`.

```python
@pytest.mark.parametrize("dim,gqa,bits,T", [(256,6,3,512),(256,6,3,40000),(256,4,4,4096),(128,1,3,512),(96,6,3,4096)])
def test_decode_gqa_matches_fp32_reference(dim, gqa, bits, T):
    q, cache, ref_kv = _build_decode_case(dim=dim, gqa=gqa, bits=bits, T=T)  # helper: see Step 2
    quantized = scaled_dot_product_attention(q, None, None, cache=cache, scale=dim**-0.5, mask=None)
    reference = mx.fast.scaled_dot_product_attention(q, ref_kv.k_fp32, ref_kv.v_fp32, scale=dim**-0.5, mask=None)
    assert quantized.shape == reference.shape
    assert mx.max(mx.abs(quantized - reference)).item() < 2e-2  # tighten after baseline measured
```

- [ ] **Step 2: Write `_build_decode_case` helper** (dequantized-KV reference kept alongside the TQ cache), reusing the existing fixture patterns in `test_turboquant.py`.
- [ ] **Step 3: Run — expect PASS on current kernel** (the current decode is correct, just slow): `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest mlx_vlm/tests/test_turboquant.py -k decode_gqa -q`. This is the *regression net*, green before and after the perf change. (If any matrix cell FAILs now, that's a pre-existing correctness bug — stop and report.)
- [ ] **Step 4: Commit the test scaffold** (propose): `test(turboquant): fp32-reference decode matrix (dim/gqa/bits/T) for GQA tile-reuse`.

---

### Task 2: GQA tile-reuse in the single-pass MSE decode kernel (≤2048 tokens)

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/turboquant.py` — `_fused_mse_decode_kernel` (single-pass) + its dispatch/grid in `decode_attention`.
- Reference impl: `benchmark/spikes/spike_c_gqa.py` (validated tile-reuse prototype).

**Interfaces:**
- Consumes: Task 1 test net.
- Produces: single-pass decode that loads each kv-head K/V tile once into threadgroup memory and serves all `R` heads (no `R×` re-read).

- [ ] **Step 1: Confirm the RED perf baseline** — micro-bench current single-pass decode tok/s at T≤2048 (record; the fix must not regress correctness and should improve or hold BW here — the big win is at long T in Task 3).
- [ ] **Step 2: Port the tile-reuse loop** from `spike_c_gqa.py`: change the grid from one-threadgroup-per-query-head (`bh = bqh / RepeatCount`, the `R×` re-read) to one-threadgroup-per-kv-head that loads the packed K/V tile into `threadgroup` memory once, then loops `r in 0..R` computing each query-head's scores from the shared tile. Keep in-kernel dequant + fp32 online softmax + no score materialization.
- [ ] **Step 3: Run the Task-1 matrix** (T=512 cells): `pytest -k "decode_gqa" -q` → PASS (numerics preserved).
- [ ] **Step 4: Micro-bench** single-pass tok/s vs Step 1 → record (expect ≥ parity; DRAM traffic drops `~R×` for the K/V reads).
- [ ] **Step 5: Commit** (propose): `perf(turboquant): GQA tile-reuse in single-pass MSE decode kernel`.

---

### Task 3: GQA tile-reuse + occupancy-preserving block-split in the 2-pass decode kernel (long T)

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/turboquant.py` — `_fused_mse_decode_2pass_1_kernel` / `_fused_mse_decode_2pass_2_kernel` + the block-count ladder (64/128/256/512) selection in `decode_attention`.
- Reference impl: `benchmark/spikes/spike_c2_blocksplit.py` (the occupancy-preserving split that won 1.6× at 200K, peak G≈2).

**Interfaces:**
- Consumes: Task 1 net.
- Produces: long-T decode that reuses the kv tile across `R` heads while keeping GPU occupancy via a token-block split (G≈2 heads/threadgroup).

- [ ] **Step 1: RED perf baseline** — micro-bench current 2-pass decode at T=40000 and (on M5) T=256K; record ms/token. Per spike E, current is ~2× slower than fp16 SDPA @200K.
- [ ] **Step 2: Port the block-split tile-reuse** from `spike_c2_blocksplit.py`: kv tile loaded once per (kv-head × token-block); serve G≈2 query-heads/threadgroup (not all R serially — that eats the saving + raises register pressure per spike C); keep the 2-pass online-softmax merge. Make G a template param (default 2).
- [ ] **Step 3: Run the Task-1 matrix** (T=40000 cell + add a 200K cell on M5) → PASS.
- [ ] **Step 4: Micro-bench** 2-pass tok/s at 40K/128K/(256K on M5) vs Step 1 and vs fp16 `mx.fast` SDPA decode → record. Target: ≥ fp16 SDPA at 3-bit (the "beat fp16" prize).
- [ ] **Step 5: Commit** (propose): `perf(turboquant): GQA tile-reuse + occupancy block-split in 2-pass MSE decode`.

---

### Task 4: Kill-switch + capability gate (config threading)

**Files:**
- Modify: `main_models.yaml` (per-model flag), `../mlx-serve/src/mlx_serve/config.py` (field+default), `process_manager.py` (CLI flag), `../mlx-vlm/mlx_vlm/generate/cli.py` (parse→env), dispatch/cache construction (read → capability object).
- Test: `test_turboquant.py` (gate on/off selects new vs old kernel).

- [ ] **Step 1: Failing test** — with the flag `false`, `decode_attention` uses the legacy kernel; `true`/default-eligible uses tile-reuse. Assert both produce equal output (within TOL) and the selection is observable (e.g., a `_last_decode_kernel` marker).
- [ ] **Step 2: Thread the flag** `tq_fused_decode` (bool; auto-on for eligible TQ+MSE+supported-dims; per §9 path). Emit the CLI flag only when set.
- [ ] **Step 3: Run** the gate test → PASS; run the full Task-1 matrix under both flag states → PASS.
- [ ] **Step 4: Commit** (propose, fork + stack): `feat(turboquant): tq_fused_decode kill-switch + eligibility gate`.

---

### Task 5: M5 validation (primary — deploy target)

**Files:** `benchmark/` (reuse `bench.run_capacity` for decode_tps + retrieval; add a decode micro-bench if needed).

- [ ] **Step 1: Deploy to M5** — bump stack submodule to the fork commit (or scp the changed `turboquant.py`), restart the router.
- [ ] **Step 2: Numerics + retrieval** — run the capacity+retrieval ladder for distill (kv_bits 4) and Ornith (kv_bits… Ornith is uniform-4bit weights + fp16 KV; for the TQ-decode test use a turboquant-KV variant, e.g. the `-kv3`/`-kv4` variants) at 64K/128K/192K/256K with `tq_fused_decode` ON: retrieval must stay ≥0.85 / unchanged; mx-peak unchanged.
- [ ] **Step 3: Speed** — decode tok/s ON vs OFF (kill-switch) AND vs fp16 SDPA where it fits (≤64K), at 64K/128K/256K, kv_bits 3 and 4. Record: does 4-bit decode now **beat** fp16? Does distill's 9.6 tok/s @256K improve?
- [ ] **Step 4: Record** in `docs/campaign-results.md` (Phase-2 #5 decode row): tok/s deltas + the fp16 comparison + the mechanism (BW traffic cut).

---

### Task 6: M2–M4 confirmation

- [ ] **Step 1: Deploy to M2**, restart router.
- [ ] **Step 2: Decode tok/s ON vs OFF** on M2 at ≤128K (M2 caps at ~192K co-resident), kv_bits 3. Confirm the tile-reuse win transfers (it should — bandwidth is generation-agnostic). Record.
- [ ] **Step 3: Numerics** — run the Task-1 matrix on M2 → PASS (same kernel, confirm no M2-specific compile/precision issue).

---

### Task 7: Decision & record

**Files:** `docs/campaign-results.md`, `docs/campaign-queue.md`.

- [ ] **Step 1: Synthesize** — decode tok/s ON vs OFF vs fp16 on M5 + M2; retrieval/numerics intact; the "does quantized KV now beat fp16 on decode?" verdict.
- [ ] **Step 2: Revisit the parked memory levers** — if 4-bit KV decode now ≥ fp16, **Ornith can take 4-bit KV for free** (reclaim ~5.7 GB) and **distill-kv3 revives** (the #2 finding flips). Note this explicitly.
- [ ] **Step 3: Propose the fork commit + submodule bump** for approval. Update `campaign-queue.md` #5-decode status → DONE; note the follow-on plans (prefill MMA, Prod codec, gemma4 generality).

---

## Self-Review

**Spec coverage:** design §4 decode (tile-reuse, no-MMA) → Tasks 2–3; §6 spike C/C2/E (the validated prototype + baseline) → Tasks 2–3 reference impls; §8 numerics/TDD (fp32 ref, matrix) → Task 1; §9 config kill-switch → Task 4; validation (retrieval, tok/s vs fp16) → Tasks 5–6. Prefill/Prod/gemma4 explicitly deferred (noted). Decode-first + M5-then-M2 ordering honored (Tasks 5→6).

**Placeholder scan:** implementation tasks reference the *validated spike files* (`spike_c_gqa.py`, `spike_c2_blocksplit.py`) as the source-of-truth Metal to port — concrete, not "TBD". The test code is shown; `_build_decode_case` is specified as "reuse existing fixtures." TOL starts at 2e-2, tightened after the baseline (Task 1 Step 3) — explicit.

**Type consistency:** kernel names match turboquant.py (`_fused_mse_decode_kernel`, `_fused_mse_decode_2pass_1/2_kernel`, `_mse_score_tiled_kernel`); flag `tq_fused_decode` used consistently (Task 4→5); test id `test_decode_gqa_matches_fp32_reference` consistent (Task 1→2→3→6).

**Note:** Task 1's test is expected to PASS on the current kernel (it's a regression net, not red-then-green) — this is correct for a perf change that must preserve numerics; the RED/GREEN cycle is on the *perf micro-benchmarks* (Tasks 2–3 Steps 1→4), not correctness.
