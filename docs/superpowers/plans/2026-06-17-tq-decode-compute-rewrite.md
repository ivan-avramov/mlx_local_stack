# TurboQuant Decode Compute Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long-context TQ decode (the per-token cost in multi-turn-at-200K) reach fp16-SDPA-*class* latency at 3-bit memory, by optimizing the compute-bound per-token work in the 2-pass decode kernel — *not* tile-reuse (already done) or exp (minor).

**Architecture:** Spike G proved decode is compute-bound: the read-only ceiling (M2 136 / M5 299 GB/s) is ~1.6–2.4× the full kernel (M2 57 / M5 182 GB/s), and the readonly ceiling ≈ fp16-SDPA latency. The cost is the per-token dot-product: per-dim **codebook gathers from device memory** + per-token **simd_sum** reductions, ×G heads ×T tokens. Optimize those (stage codebook/q in fast memory, cut per-token reduction overhead), gated behind a flag, validated by TDD against the fp32 reference and benchmarked on **both M2 and M5**.

**Tech Stack:** MLX `mx.fast.metal_kernel` (MSL), Metal `simd_sum`/threadgroup memory, Python 3, pytest. Fork: `../mlx-vlm`. Remote M5: `ssh $REMOTE_HOST`, repos at `~/Documents/ws/`.

## Global Constraints

- All code edits in the fork `../mlx-vlm`, never `src/mlx-vlm`. Test from the stack dir with `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest <path> -v`.
- Reference of record: full fp32 dequant → `mx.fast.scaled_dot_product_attention` in fp32; tight max-abs-diff. Decode is L=1; reuse the harness in `mlx_vlm/tests/test_turboquant_fused_prefill.py` (`build_cache`, `reference_attention`, `mad`).
- Accumulation stays fp32 (`typedef float U`); dequant the unit codebook value, apply per-token norm in fp32.
- **Success bar (reframed):** the win is **200K viability at reduced memory** — a 3-bit decode at fp16-SDPA-*class* latency (parity is enough; fp16-KV OOMs at 200K so it can't compete there). Keep the optimization if it meaningfully closes full→readonly on **both** boxes without regressing; **stop if the Task-1 prototype shows no meaningful gain** (the current kernel already meets the bar at reduced memory).
- New behavior behind `TQ_DECODE_IMPL` env (`"current"` default | `"opt"`); the existing 2-pass kernel stays the default until the opt path provably wins on both boxes.
- M5: test every perf claim on `ssh $REMOTE_HOST` too (different compute/bandwidth balance; M5 headroom is smaller, ~1.6×).
- Dynamic Caching (M3+/M5) relaxes the register cap — the opt kernel may use larger threadgroups on M5 than M2; measure, don't assume.
- Propose fork changes for approval before commit/push (own no-PR repo; commit locally as we go, push only to deploy for real-model validation).

---

## Reference facts (read once before Task 1)

- Current decode kernels: `_fused_mse_decode_kernel` (single-pass ≤2048) and `_fused_mse_decode_2pass_1_kernel` (`turboquant.py:2458`) + pass-2 merge. `decode_attention` (`turboquant.py:~5960`) selects them and applies `value_codec._rotate_inverse` + reshape.
- The 2-pass pass-1 inner loop (the compute hot spot): per token `t`, byte-extract the lane's `qk_per_thread` (=D/32=8) key indices, gather `key_codebook[idx]` (**device-memory indexed load**), FMA with the registered query, `simd_sum` the 8-lane... 32-lane partial → score; then exp online-softmax; then the same for values. `key_codebook`/`val_codebook` are passed as **device** inputs → every `cb[idx]` is a device load.
- Spike harness with the working block-split decode + GQA tile-reuse: `benchmark/spikes/spike_g_decode_compute.py` (`full`/`noexp`/`readonly` variants, `make_kv`, GB/s bench). This is the prototyping base.
- Spike G numbers (T=200K): M2 readonly 136 / full 57 GB/s; M5 readonly 299 / full 182. readonly→noexp is the big drop (dequant+score+simd_sum); noexp→full (exp) is ~9%.
- fp16-SDPA decode @200K: M2 3.52 ms, M5 1.87 ms (the parity target).

---

## Task 1: Prototype the compute optimization + benchmark gate (BOTH boxes)

**Files:**
- Create: `benchmark/spikes/spike_h_decode_opt.py` (throwaway prototype; extends spike_g)

**Interfaces:**
- Produces: a benchmark comparing `full` (current-style) vs `opt` (optimized) vs `readonly` at T∈{65536,131072,200000} on M2 and M5, reporting GB/s and the fraction of the full→readonly gap closed. No production code yet.

- [ ] **Step 1: Copy spike_g as the base and add an `opt` kernel variant**

Start from `benchmark/spikes/spike_g_decode_compute.py`. Add an `"opt"` entry to `KERNELS` that applies these three changes to the per-token loop (the measured bottlenecks), keeping the math identical to `full`:
1. **Stage the codebook in threadgroup memory once** at kernel start (`threadgroup float cbsh[16]; if (lane < (1<<BITS)) cbsh[lane]=cb[lane]; threadgroup_barrier(...)`) and gather `cbsh[v]` instead of the device `cb[v]` — removes per-dim device-memory indexed loads.
2. **Hoist the query into threadgroup memory** for the G heads (already in registers `qreg`; keep, but ensure no re-read) and unroll the dim loop with `#pragma unroll`.
3. **Cut per-token reduction cost:** accumulate each head's partial dot across the lane's dims, then `simd_sum` — but compute the G heads' partial dots first and issue the G `simd_sum`s back-to-back (lets the scheduler overlap), and move the `exp`/online-softmax update off the critical path where possible.

```python
# opt kernel body: _HEAD + per-token loop with cbsh[] gather + unrolled dims + grouped simd_sum
# (full source written here following the spike_g _HEAD / _DEQ_K / _DEQ_V structure)
```

- [ ] **Step 2: Verify `opt` is numerically identical to `full` (same math)**

Add a correctness check in the script: run `opt` and `full` for a small T, merge partials (the spike's mx merge), assert `mx.max(mx.abs(opt_out - full_out)) < 1e-4`.
Run: `PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_h_decode_opt.py --check`
Expected: PASS (opt == full numerically).

- [ ] **Step 3: Benchmark on M2 Max**

Run: `PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_h_decode_opt.py`
Record GB/s for full/opt/readonly at each T. Compute `gap_closed = (opt - full) / (readonly - full)`.

- [ ] **Step 4: Benchmark on M5 Max**

```bash
scp -q benchmark/spikes/spike_h_decode_opt.py $REMOTE_HOST:~/Documents/ws/mlx_local_stack/benchmark/spikes/
ssh $REMOTE_HOST 'cd ~/Documents/ws/mlx_local_stack && .venv/bin/python benchmark/spikes/spike_h_decode_opt.py'
```
Record the same.

- [ ] **Step 5: GATE decision**

If `opt` beats `full` meaningfully on **both** boxes (e.g., closes ≥30% of the full→readonly gap, or ≥1.15× throughput) → proceed to Task 2. **If `opt` ≈ `full` on either box → STOP**: document the result, keep the current kernel (it already meets the 200K-at-reduced-memory bar), and report. No commit of throwaway spike needed.

---

## Task 2: Productionize the optimized pass-1 kernel (TDD vs fp32)

*(Only if Task 1 gate passes.)*

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/turboquant.py` (add `_fused_mse_decode_2pass_1_kernel_opt` or extend the builder with an `opt` flag; codebook-in-tgmem + the validated Task-1 changes)
- Test: `../mlx-vlm/mlx_vlm/tests/test_turboquant_decode_opt.py`

**Interfaces:**
- Consumes: the validated `opt` kernel body from Task 1.
- Produces: a kernel builder returning a callable with the **same inputs/outputs/template** as `_fused_mse_decode_2pass_1_kernel` (drop-in), selected by `TQ_DECODE_IMPL`.

- [ ] **Step 1: Write the failing numerics test (decode L=1 vs fp32 reference)**

```python
import math, numpy as np, mlx.core as mx
from mlx_vlm.tests.test_turboquant_fused_prefill import build_cache, reference_attention, mad

def test_decode_opt_matches_reference():
    import os; os.environ["TQ_DECODE_IMPL"] = "opt"
    B, n_kv, r, T, D = 1, 4, 6, 9000, 256   # >2048 -> 2-pass path
    cache, ks, vs = build_cache(B, n_kv, T, D, bits=3, seed=11)
    q = mx.array(np.random.default_rng(12).standard_normal((B, n_kv*r, 1, D)).astype(np.float32)*0.1)
    scale = 1.0/math.sqrt(D)
    ref = reference_attention(q, cache, ks, vs, scale, causal=True)
    out = cache.decode_attention(q, cache._unwrap(ks), cache._unwrap(vs), scale=scale, mask="causal")
    assert mad(out, ref) < 3e-2
```

- [ ] **Step 2: Run; expect FAIL (opt kernel not built / env not wired)**

Run: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant_decode_opt.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the opt kernel builder + `TQ_DECODE_IMPL` selection in `decode_attention`**

Add `_fused_mse_decode_2pass_1_kernel_opt(key_bits, val_bits, dim)` (the Task-1 body, codebook staged in tgmem, unrolled, grouped reductions). In `decode_attention`, read `os.environ.get("TQ_DECODE_IMPL","current")`; when `"opt"`, build the opt pass-1 kernel instead of the current one (pass-2 merge unchanged). Same `inputs`/`template`/`grid`/`threadgroup`/`output_shapes`.

- [ ] **Step 4: Run; expect PASS**

Run: same as Step 2. Expected: PASS (mad < 3e-2).

- [ ] **Step 5: Block-size / token-count invariance + single-pass parity**

```python
def test_decode_opt_matches_current_kernel():
    # opt and current must produce ~identical output (same math, different compute)
    B, n_kv, r, T, D = 1, 4, 6, 9000, 256
    cache, ks, vs = build_cache(B, n_kv, T, D, bits=3, seed=13)
    q = mx.array(np.random.default_rng(14).standard_normal((B, n_kv*r,1,D)).astype(np.float32)*0.1)
    import os
    os.environ["TQ_DECODE_IMPL"]="current"; cur = cache.decode_attention(q, cache._unwrap(ks), cache._unwrap(vs), scale=1/16, mask="causal")
    os.environ["TQ_DECODE_IMPL"]="opt";     opt = cache.decode_attention(q, cache._unwrap(ks), cache._unwrap(vs), scale=1/16, mask="causal")
    assert mad(cur, opt) < 5e-3
```
Run: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant_decode_opt.py -v`
Expected: PASS.

- [ ] **Step 6: Commit (local)**

```bash
cd ../mlx-vlm && git add mlx_vlm/turboquant.py mlx_vlm/tests/test_turboquant_decode_opt.py
git commit -m "perf(turboquant): compute-optimized decode pass-1 kernel behind TQ_DECODE_IMPL"
```

---

## Task 3: Dual-box op-level perf + numerics confirmation

**Files:**
- Modify: `benchmark/spikes/spike_g_decode_compute.py` (add an `--impl current|opt` switch that drives the real `decode_attention`, or a small new bench script driving `decode_attention` at 200K both ways)

- [ ] **Step 1: Bench real `decode_attention` (current vs opt) at 200K on M2**

Drive `cache.decode_attention` (real path, not the spike kernel) at T=200000 with `TQ_DECODE_IMPL=current` then `=opt`; record ms + needle-free output equality (mad < 5e-3).
Run: `PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/bench_decode_attention.py`
Expected: opt faster than current; outputs match.

- [ ] **Step 2: Same on M5 Max**

```bash
scp -q benchmark/spikes/bench_decode_attention.py $REMOTE_HOST:~/Documents/ws/mlx_local_stack/benchmark/spikes/
ssh $REMOTE_HOST 'cd ~/Documents/ws/mlx_local_stack && .venv/bin/python benchmark/spikes/bench_decode_attention.py'
```
Expected: opt ≥ current (M5 headroom smaller; even parity acceptable per the bar).

- [ ] **Step 3: Decision — keep opt as default?**

If opt is clearly faster on both (or faster on M2 + parity on M5) and within tolerance → in a follow-up, consider flipping `TQ_DECODE_IMPL` default to `"opt"`. Record the numbers in this plan.

---

## Task 4: Real-model validation (deploy + decode tok/s at long context)

**Files:** none (operational). Requires push + submodule bump + manager restart (per the prefill deploy chain).

- [ ] **Step 1: Confirm clean env; deploy**

`ps aux | grep -iE 'mlx-serve|needle' | grep -v grep` → none. Commit + push fork; bump `src/mlx-vlm`; restart only the mlx-serve main server (light launch, `:8000` only).

- [ ] **Step 2: Decode tok/s at long context, opt vs current, on M2**

Launch with `TQ_DECODE_IMPL=opt` then `=current`; run the needle (or a decode-only generation) at a large cached context and record decode tok/s + peak mem. Compare to the fp16-SDPA-class target.

- [ ] **Step 3: Same on M5 Max**

Bring up the light server on `ssh $REMOTE_HOST` with each `TQ_DECODE_IMPL`; record decode tok/s at long context.

- [ ] **Step 4: Lock-in decision + document**

If opt meets the reframed bar (fp16-SDPA-class decode at 3-bit memory on both boxes, output correct), propose flipping the default + a memory update. Otherwise keep `current` default and document opt as available via the flag.

---

## Self-Review

**Spec/goal coverage:** compute-bound decode optimization (Spike G) → Tasks 1–2. Both-box validation → Tasks 1,3,4. fp32 TDD + block-size invariance → Task 2. Reframed success bar (parity-at-reduced-memory) + stop-if-no-gain gate → Task 1 Step 5, Global Constraints. The lever is per-token compute (codebook-in-tgmem + reduced reduction overhead), explicitly *not* tile-reuse/exp (Spike G).

**Placeholder scan:** Task 1 Step 1's `opt` kernel body is described by its three concrete changes against the existing spike_g structure rather than re-pasting ~60 lines of MSL; the spike_g source is the committed, runnable base. All test code is complete. The `bench_decode_attention.py` script (Task 3) is named + its behavior specified (drive `decode_attention` both ways at 200K, compare ms + mad) — it's a thin harness over the existing API.

**Type consistency:** `TQ_DECODE_IMPL` env ("current"/"opt") used consistently; the opt kernel builder keeps the exact inputs/template/grid/threadgroup/output_shapes of `_fused_mse_decode_2pass_1_kernel` (drop-in); tests use the shared `build_cache`/`reference_attention`/`mad` harness.

**Note:** This plan deliberately gates at Task 1 — if the prototype doesn't realize the Spike-G headroom on both boxes, we stop and keep the current kernel, since 3-bit already delivers the 200K-at-reduced-memory win.
