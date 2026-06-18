# TurboQuant Fused MSE Prefill (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Python K-tile `quantized_attention` loop for MSE prefill (`L > 1`) with a single fused flash-attention Metal kernel (dequant→fp16 + `simdgroup_matrix` MMA, in-kernel online softmax, no score materialization), behind a capability gate and a `tq_fused_prefill` kill-switch, validated by TDD against a full-fp32 reference.

**Architecture:** One `mx.fast.metal_kernel` flash core. Per (query-block, kv-head): dequantize the K-tile to fp16 in registers, `QKᵀ` via MMA (fp16-in/fp32-acc), apply per-token norm + causal mask, online-softmax-merge across K-tiles, fold norms into the weights, `AV` via MMA, accumulate. Output in rotated space → `value_codec._rotate_inverse` → reshape. This is the M2–M4 (`simdgroup_matrix`) backend; the M5 TensorOps backend and the decode rewrite are separate follow-on plans (see Roadmap).

**Tech Stack:** MLX `mx.fast.metal_kernel` (Metal Shading Language via runtime JIT), Metal `simdgroup_matrix<T,8,8>`, Python 3, pytest. Fork: `../mlx-vlm`.

## Global Constraints

- All code edits go in the fork `../mlx-vlm`, **never** `src/mlx-vlm`. (Verbatim from spec §11.)
- Test from the stack dir `$STACK_REPO` with: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest <path> -v`.
- The `:8000` stack serves **one model at a time**, **no concurrent requests**. Before any real-model run, confirm no stray python eval/generate/needle processes (`ps aux | grep -iE 'python|needle' | grep -v grep`).
- Restart the mlx-serve manager to load new fork code (the stack `.venv` imports `mlx_vlm` editably).
- **Propose fork changes for approval before commit or push.** Do not commit/push without explicit approval.
- Reference of record (spec §8): full fp32 dequant of KV → `mx.fast.scaled_dot_product_attention` in fp32. Assert a tight max-abs-diff, not just parity with the old loop.
- Numerics target (validated, spike A): fp16-input/fp32-accumulate is exact for QKᵀ; keep score/softmax/AV accumulation in fp32 (`typedef float U`); dequant the **unit** codebook value to fp16 and apply the per-token **norm in fp32** (never fold a large norm into fp16).
- Capability gate is the primary control (TQ + MSE codec + wrapper-routed + supported dims); `tq_fused_prefill` (bool, per-model YAML) is an override defaulting to auto-on.
- Quantized state layouts (verbatim from the fork): MSE key/value state is `norms: [B,H,T] fp16` + `indices: [B,H,T,PackedWidth] uint32`, packed little-endian with index `d` at bit `d*bits`; `PackedWidth = (D*bits + 31)//32`; codebook is `[2**bits]` fp32. Queries are pre-rotated via `self.key_codec.prepare_queries(grouped_queries)`; output is inverse-rotated via `self.value_codec._rotate_inverse(out_rotated)`.

---

## Reference facts (read once before Task 1)

Exact fork locations confirmed at plan time (`../mlx-vlm`, commit `d07f854`):

- Dispatch wrapper: `mlx_vlm/models/base.py:193` `scaled_dot_product_attention(...)`. For `TurboQuantKVCache`: `queries.shape[-2]==1` → `decode_attention`; else → `prefill_attention(...)`; if that returns `None` → `quantized_attention(...)`. **No change needed in base.py** — making `prefill_attention` return non-`None` for MSE is sufficient.
- `TurboQuantKVCache.prefill_attention`: `mlx_vlm/turboquant.py:5308`. Currently returns `None` unless key codec is `_TurboQuantProdCodec`. This is where the MSE fused path is added.
- `TurboQuantKVCache.quantized_attention`: `mlx_vlm/turboquant.py:5213` — the fallback loop (kept as the gated-off path).
- `decode_attention`: `mlx_vlm/turboquant.py:5879` — mirror its query prep (`q_rot = self.key_codec.prepare_queries(grouped_queries)`), kernel-input ordering, and post-kernel `self.value_codec._rotate_inverse(out_rotated)` + `reshape(B, n_q_heads, L, value_dim)`.
- Decode 2-pass kernel builder (structural template for the MMA flash core): `_fused_mse_decode_2pass_1_kernel` at `mlx_vlm/turboquant.py:2457`.
- Existing tests: `mlx_vlm/tests/test_turboquant.py`. There is an assertion that `prefill_attention` returns `None` for MSE (`kv_bits=3`) — it will be updated in Task 6.
- Validated spike kernels to lift from (stack repo, throwaway): `benchmark/spikes/spike_a_mma.py` (MMA `QKᵀ` + `AV`, fp16-in/fp32-acc), `benchmark/spikes/spike_b_lut.py` (3-bit→fp16 dequant kernel), `benchmark/spikes/spike_c2_blocksplit.py` (block-split flash online-softmax).

---

## Task 1: fp32 reference harness + sanity test

**Files:**
- Create: `../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py`

**Interfaces:**
- Produces: `build_cache(B, n_kv, T, D, bits, seed) -> (TurboQuantKVCache, keys_state, values_state)`; `reference_attention(q, cache, ks, vs, scale, causal) -> mx.array [B,n_q,L,D]` (full fp32 dequant → `mx.fast.scaled_dot_product_attention`); `mad(a,b) -> float` max-abs-diff.

- [ ] **Step 1: Write the harness + a sanity test that the reference matches a brute-force numpy attention for a tiny dequantized case**

```python
import math, numpy as np, mlx.core as mx, pytest
from mlx_vlm.turboquant import TurboQuantKVCache

def build_cache(B, n_kv, T, D, bits, seed=0):
    rng = np.random.default_rng(seed)
    k = mx.array(rng.standard_normal((B, n_kv, T, D)).astype(np.float32) * 0.1)
    v = mx.array(rng.standard_normal((B, n_kv, T, D)).astype(np.float32) * 0.1)
    cache = TurboQuantKVCache(bits=bits, seed=seed)
    ks, vs = cache.update_and_fetch(k, v)
    mx.eval(cache.keys, cache.values)
    return cache, ks, vs

def reference_attention(q, cache, ks, vs, scale, causal):
    kd, vd = cache.dequantize(ks, vs)            # fp32 [B,n_kv,T,D]
    B, n_q, L, D = q.shape
    n_kv = kd.shape[1]; r = n_q // n_kv
    kd = mx.repeat(kd, r, axis=1); vd = mx.repeat(vd, r, axis=1)
    mask = "causal" if causal else None
    return mx.fast.scaled_dot_product_attention(
        q.astype(mx.float32), kd, vd, scale=scale, mask=mask)

def mad(a, b):
    return mx.max(mx.abs(a.astype(mx.float32) - b.astype(mx.float32))).item()

def test_reference_matches_bruteforce_numpy():
    B, n_kv, T, D, r = 1, 1, 8, 16, 1
    cache, ks, vs = build_cache(B, n_kv, T, D, bits=3, seed=1)
    q = mx.array(np.random.default_rng(2).standard_normal((B, n_kv*r, 1, D)).astype(np.float32)*0.1)
    scale = 1.0/math.sqrt(D)
    out = reference_attention(q, cache, ks, vs, scale, causal=False)
    kd, vd = cache.dequantize(ks, vs)
    qn = np.array(q[0,0,0]); kn = np.array(kd[0,0]); vn = np.array(vd[0,0])
    s = (qn @ kn.T) * scale; s -= s.max(); w = np.exp(s); w /= w.sum()
    ref = w @ vn
    assert mad(out[0,0,0], mx.array(ref)) < 1e-4
```

- [ ] **Step 2: Run it; expect PASS (validates the reference path itself)**

Run: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py::test_reference_matches_bruteforce_numpy -v`
Expected: PASS.

- [ ] **Step 3: Commit (after approval)**

```bash
cd ../mlx-vlm && git add mlx_vlm/tests/test_turboquant_fused_prefill.py
git commit -m "test(turboquant): fp32 reference harness for fused prefill"
```

---

## Task 2: Capability gate + kill-switch read

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/turboquant.py` (add `_fused_prefill_eligible`; read env override in `TurboQuantKVCache.__init__`)
- Test: `../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py`

**Interfaces:**
- Produces: `TurboQuantKVCache._fused_prefill_eligible(self, queries, keys_state, values_state) -> bool` — True iff key & value codecs are `_TurboQuantMSECodec`, states are `TurboQuantMSEState`, `D` is a multiple of 8, `bits in (3,4)`, and `self._fused_prefill_enabled` is True. `self._fused_prefill_enabled` reads env `TQ_FUSED_PREFILL` (default True; "0"/"false" → False), settable via `__init__(..., fused_prefill: Optional[bool]=None)`.

- [ ] **Step 1: Write the failing test**

```python
import os
from mlx_vlm.turboquant import TurboQuantKVCache, _TurboQuantMSECodec

def test_gate_on_for_mse_supported_dims():
    cache, ks, vs = build_cache(1, 1, 64, 256, bits=3)
    q = mx.zeros((1, 1, 4, 256))
    assert cache._fused_prefill_eligible(q, ks._state if hasattr(ks,'_state') else ks,
                                          vs._state if hasattr(vs,'_state') else vs) is True

def test_gate_off_via_killswitch():
    cache = TurboQuantKVCache(bits=3, seed=0, fused_prefill=False)
    k = mx.zeros((1,1,64,256)); v = mx.zeros((1,1,64,256))
    ks, vs = cache.update_and_fetch(k, v)
    q = mx.zeros((1,1,4,256))
    assert cache._fused_prefill_eligible(q, cache._unwrap(ks), cache._unwrap(vs)) is False
```

- [ ] **Step 2: Run; expect FAIL (`_fused_prefill_eligible` not defined)**

Run: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py -k gate -v`
Expected: FAIL (AttributeError).

- [ ] **Step 3: Implement the gate**

In `TurboQuantKVCache.__init__` (turboquant.py:4988), after `self.seed = seed`, add:
```python
import os as _os
self._fused_prefill_enabled = (
    fused_prefill if fused_prefill is not None
    else _os.environ.get("TQ_FUSED_PREFILL", "1").lower() not in ("0", "false", "no")
)
```
Add `fused_prefill: Optional[bool] = None` to the `__init__` signature. Add the method (near `prefill_attention`):
```python
def _fused_prefill_eligible(self, queries, keys_state, values_state) -> bool:
    if not self._fused_prefill_enabled:
        return False
    D = queries.shape[-1]
    return (
        isinstance(self.key_codec, _TurboQuantMSECodec)
        and isinstance(self.value_codec, _TurboQuantMSECodec)
        and isinstance(keys_state, TurboQuantMSEState)
        and isinstance(values_state, TurboQuantMSEState)
        and D % 8 == 0
        and int(self.key_codec.bits) in (3, 4)
        and int(self.value_codec.bits) in (3, 4)
    )
```

- [ ] **Step 4: Run; expect PASS**

Run: same as Step 2. Expected: PASS (both gate tests).

- [ ] **Step 5: Commit (after approval)**

```bash
cd ../mlx-vlm && git add mlx_vlm/turboquant.py mlx_vlm/tests/test_turboquant_fused_prefill.py
git commit -m "feat(turboquant): fused-prefill capability gate + TQ_FUSED_PREFILL kill-switch"
```

---

## Task 3: Fused MSE prefill kernel — numerics against fp32 reference

This is the core task. The kernel is developed test-first against the §8 reference, lifting the validated MMA `QKᵀ`/`AV` from `benchmark/spikes/spike_a_mma.py`, the 3-bit→fp16 dequant from `spike_b_lut.py`, and the block-split online-softmax from `spike_c2_blocksplit.py`.

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/turboquant.py` (add `_fused_mse_prefill_kernel(key_bits, val_bits, dim)` builder + `fused_mse_prefill(self, queries, keys_state, values_state, scale, mask)`)
- Test: `../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py`

**Interfaces:**
- Consumes: state layouts and codecs from Task 2; `prepare_queries`/`_rotate_inverse` from the codecs.
- Produces: `TurboQuantKVCache.fused_mse_prefill(queries, keys_state, values_state, scale, mask) -> mx.array [B, n_q, L, D]`. Kernel inputs (mirror decode order): `q_rot_flat [B*n_kv*r, L, D]`, `keys_state.norms`, `keys_state.indices`, `key_codec.codebook`, `values_state.norms`, `values_state.indices`, `value_codec.codebook`. Template: `Dim`, `RepeatCount`, `KPackedWidth`, `VPackedWidth`, `L`, plus a `Causal` flag. Kernel output: rotated `[B*n_kv*r, L, D]` fp32.

- [ ] **Step 1: Write the failing numerics test (non-causal, small)**

```python
def test_fused_prefill_matches_reference_small_noncausal():
    B, n_kv, r, T, D = 1, 2, 6, 512, 256
    cache, ks, vs = build_cache(B, n_kv, T, D, bits=3, seed=3)
    q = mx.array(np.random.default_rng(4).standard_normal((B, n_kv*r, 64, D)).astype(np.float32)*0.1)
    scale = 1.0/math.sqrt(D)
    ref = reference_attention(q, cache, ks, vs, scale, causal=False)
    out = cache.fused_mse_prefill(q, cache._unwrap(ks), cache._unwrap(vs), scale=scale, mask=None)
    assert mad(out, ref) < 2e-2     # 3-bit codec + fp16 inputs; fp32 accumulate
```

- [ ] **Step 2: Run; expect FAIL (`fused_mse_prefill` not defined)**

Run: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py -k fused_prefill_matches -v`
Expected: FAIL.

- [ ] **Step 3: Implement the kernel builder + method**

Build the kernel from the validated spike pieces. Structure (one threadgroup per `(B*n_kv, query-block, k-block)` with a 2-pass merge, mirroring `spike_c2_blocksplit.py`; or single-pass over K-tiles with in-kernel online softmax mirroring `_fused_mse_decode_2pass_1_kernel` extended to `L>1`). Per K-tile: (a) cooperatively dequant the K-tile `[Tk, D]` 3-bit→fp16 into threadgroup memory (`spike_b` dequant, unit codebook, norm kept separate); (b) `simdgroup_matrix` `QKᵀ`: `q_rot_block[L×D] · Ktile_fp16ᵀ` → `score[L×Tk]` fp32 (`spike_a` MMA, transpose-load K); (c) multiply column `t` by `norm_t` (fp32) and `scale`; (d) if `Causal`, mask `score[i,t]` where `(past + qblock_base + i) < (k_base + t)` to `-inf`, and skip whole K-tiles strictly in the query block's future; (e) online-softmax merge into running `m,l` and rescale the accumulator; (f) dequant V-tile `[Tk,D]`→fp16 (unit); (g) fold norm into weights `w'[L×Tk] = exp(score-m) * norm_t`; (h) `simdgroup_matrix` `AV`: `w'[L×Tk] · Vtile_fp16[Tk×D]` accumulate into `acc[L×D]` fp32. After all K-tiles: divide `acc` by `l`. Write rotated `[L×D]`.

Python wrapper `fused_mse_prefill`:
```python
def fused_mse_prefill(self, queries, keys_state, values_state, scale, mask):
    B, n_q, L, D = queries.shape
    n_kv = keys_state.norms.shape[1]; r = n_q // n_kv
    grouped = queries.reshape(B, n_kv, r, L, D)
    q_rot = self.key_codec.prepare_queries(grouped)          # [B,n_kv,r,L,D] rotated
    q_rot_flat = q_rot.reshape(B * n_kv * r, L, D)
    causal = 1 if (isinstance(mask, str) and mask == "causal") else 0
    key_bits = int(self.key_codec.bits); val_bits = int(self.value_codec.bits)
    kern = _fused_mse_prefill_kernel(key_bits, val_bits, D)
    out = kern(
        inputs=[q_rot_flat, keys_state.norms, keys_state.indices, self.key_codec.codebook,
                values_state.norms, values_state.indices, self.value_codec.codebook],
        template=[("Dim", D), ("RepeatCount", r), ("L", L), ("Causal", causal),
                  ("KPackedWidth", keys_state.indices.shape[-1]),
                  ("VPackedWidth", values_state.indices.shape[-1])],
        grid=..., threadgroup=...,
        output_shapes=[(B * n_kv * r, L, D)], output_dtypes=[mx.float32])[0]
    out_rot = out.reshape(B, n_kv, r, L, D)
    return self.value_codec._rotate_inverse(out_rot).reshape(B, n_q, L, D).astype(queries.dtype)
```
The `scale` multiplies `q_rot` once before the kernel (or inside, step (c)). Implement the Metal `source` as an f-string mirroring `_fused_mse_decode_2pass_1_kernel` (turboquant.py:2457) with the `L` loop and MMA from `spike_a_mma.py`. Apply `#include <metal_simdgroup_matrix>` via the `header` arg. Tile `L` into sub-blocks of 8 to bound registers (spec §10 risk).

- [ ] **Step 4: Run; iterate to PASS**

Run: same as Step 2. Expected: PASS (`mad < 2e-2`). If it fails, debug numerics with the spike scripts as oracles (they already match their own fp32 references); check the causal-mask off-by-one and the norm-folding (norm in fp32, not fp16).

- [ ] **Step 5: Commit (after approval)**

```bash
cd ../mlx-vlm && git add mlx_vlm/turboquant.py mlx_vlm/tests/test_turboquant_fused_prefill.py
git commit -m "feat(turboquant): fused MSE prefill flash kernel (dequant+MMA, fp32 accumulate)"
```

---

## Task 4: Causal correctness + query-block-size invariance

**Files:**
- Test: `../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_fused_prefill_causal_matches_reference():
    B, n_kv, r, T, D = 1, 2, 6, 1024, 256
    cache, ks, vs = build_cache(B, n_kv, T, D, bits=3, seed=5)
    L = 256
    q = mx.array(np.random.default_rng(6).standard_normal((B, n_kv*r, L, D)).astype(np.float32)*0.1)
    scale = 1.0/math.sqrt(D)
    ref = reference_attention(q, cache, ks, vs, scale, causal=True)
    out = cache.fused_mse_prefill(q, cache._unwrap(ks), cache._unwrap(vs), scale=scale, mask="causal")
    assert mad(out, ref) < 2e-2

def test_fused_prefill_blocksize_invariant():
    # flash online-softmax is blocking-independent: result must not depend on internal tiling
    B, n_kv, r, T, D = 1, 1, 6, 600, 256
    cache, ks, vs = build_cache(B, n_kv, T, D, bits=3, seed=7)
    q = mx.array(np.random.default_rng(8).standard_normal((B, n_kv*r, 128, D)).astype(np.float32)*0.1)
    ref = reference_attention(q, cache, ks, vs, 1.0/math.sqrt(D), causal=True)
    out = cache.fused_mse_prefill(q, cache._unwrap(ks), cache._unwrap(vs), 1.0/math.sqrt(D), "causal")
    assert mad(out, ref) < 2e-2
```

- [ ] **Step 2: Run; expect PASS (fix causal off-by-one if FAIL)**

Run: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py -k "causal or blocksize" -v`
Expected: PASS.

- [ ] **Step 3: Commit (after approval)**

```bash
cd ../mlx-vlm && git add mlx_vlm/tests/test_turboquant_fused_prefill.py
git commit -m "test(turboquant): fused prefill causal + block-size invariance"
```

---

## Task 5: Wire into `prefill_attention` behind the gate + update dispatch test

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/turboquant.py:5308` (`prefill_attention`)
- Modify: `../mlx-vlm/mlx_vlm/tests/test_turboquant.py` (the stale "returns None for MSE" assertion)
- Test: `../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py`

- [ ] **Step 1: Write the failing dispatch test**

```python
def test_prefill_attention_uses_fused_for_mse_when_eligible():
    cache, ks, vs = build_cache(1, 1, 256, 256, bits=3, seed=9)
    q = mx.array(np.random.default_rng(10).standard_normal((1, 6, 32, 256)).astype(np.float32)*0.1)
    out = cache.prefill_attention(q, keys_state=ks, values_state=vs, scale=1.0/16, mask="causal")
    assert out is not None
    assert out.shape == (1, 6, 32, 256)

def test_prefill_attention_none_when_killswitch_off():
    cache = TurboQuantKVCache(bits=3, seed=0, fused_prefill=False)
    k = mx.zeros((1,1,256,256)); v = mx.zeros((1,1,256,256))
    ks, vs = cache.update_and_fetch(k, v)
    q = mx.zeros((1,6,32,256))
    assert cache.prefill_attention(q, keys_state=ks, values_state=vs, scale=1.0/16, mask="causal") is None
```

- [ ] **Step 2: Run; expect FAIL (prefill_attention returns None for MSE today)**

Run: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py -k prefill_attention -v`
Expected: FAIL (first asserts None).

- [ ] **Step 3: Add the MSE branch at the top of `prefill_attention`**

After unwrapping states at the top of `prefill_attention` (mirror how `decode_attention` unwraps via `self._unwrap`), insert before the existing Prod-only check:
```python
ks = self._unwrap(keys_state); vs = self._unwrap(values_state)
if self._fused_prefill_eligible(queries, ks, vs):
    return self.fused_mse_prefill(queries, ks, vs, scale=scale, mask=mask)
```

- [ ] **Step 4: Update the stale assertion in `test_turboquant.py`**

Find the test asserting `prefill_attention(...) is None` for `kv_bits=3` (MSE) and either delete it or assert it returns `None` only with `fused_prefill=False`. Run the full file to confirm no regressions:
Run: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant.py -v`
Expected: PASS (all).

- [ ] **Step 5: Run the new dispatch tests; expect PASS**

Run: same as Step 2. Expected: PASS.

- [ ] **Step 6: Commit (after approval)**

```bash
cd ../mlx-vlm && git add mlx_vlm/turboquant.py mlx_vlm/tests/test_turboquant.py mlx_vlm/tests/test_turboquant_fused_prefill.py
git commit -m "feat(turboquant): route MSE prefill through fused kernel behind gate"
```

---

## Task 6: Full dim / GQA / bits / L / T matrix (spec §8)

**Files:**
- Test: `../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py`

- [ ] **Step 1: Write the parametrized matrix test**

```python
@pytest.mark.parametrize("D", [256, 128, 96])          # 96 exercises RHT padding (non-pow2)
@pytest.mark.parametrize("n_kv,r", [(1,1),(2,4),(4,6)]) # MHA, GQA-4, GQA-6
@pytest.mark.parametrize("bits", [3, 4])
@pytest.mark.parametrize("L,T", [(1,512),(64,2048),(256,9000)])  # span block-split + diagonal
def test_fused_prefill_matrix(D, n_kv, r, bits, L, T):
    if D % 8 != 0: pytest.skip("kernel requires D%8==0")  # 96 is %8; documents the constraint
    cache, ks, vs = build_cache(1, n_kv, T, D, bits=bits, seed=D+n_kv+bits+L)
    q = mx.array(np.random.default_rng(99).standard_normal((1, n_kv*r, L, D)).astype(np.float32)*0.1)
    scale = 1.0/math.sqrt(D)
    ref = reference_attention(q, cache, ks, vs, scale, causal=True)
    out = cache.fused_mse_prefill(q, cache._unwrap(ks), cache._unwrap(vs), scale, "causal")
    assert mad(out, ref) < 3e-2
```

- [ ] **Step 2: Run; iterate to PASS (non-pow2 RHT padding is the likely failure point)**

Run: `PYTHONPATH=../mlx-vlm uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py -k matrix -v`
Expected: PASS across the matrix. For non-pow2 `D=96`, the dequant must zero-pad to the RHT padded dim then crop (mirror `_rht_forward`); if MMA padding is awkward, the gate already restricts to `D%8==0` and the kernel pads K-tile columns to a multiple of 8 with zeros (which contribute 0 to `QKᵀ`).

- [ ] **Step 3: Commit (after approval)**

```bash
cd ../mlx-vlm && git add mlx_vlm/tests/test_turboquant_fused_prefill.py
git commit -m "test(turboquant): full dim/GQA/bits/L/T matrix for fused MSE prefill"
```

---

## Task 7: `tq_fused_prefill` kill-switch config threading

**Files:**
- Modify: `mlx_local_stack/main_models.yaml` (add `tq_fused_prefill: true` under the Qwen entry, documented)
- Modify: `../mlx-serve/.../config.py` (new optional field + default), `../mlx-serve/.../process_manager.py` (emit `--tq-fused-prefill` only when set)
- Modify: `../mlx-vlm/mlx_vlm/cli.py` (parse flag → set `TQ_FUSED_PREFILL` env)

**Interfaces:**
- Produces: env var `TQ_FUSED_PREFILL` read by `TurboQuantKVCache.__init__` (Task 2). The capability gate is primary; this flag is the override.

- [ ] **Step 1: Trace the existing `kv_bits` threading and mirror it**

Read how `kv_bits` flows `main_models.yaml → mlx-serve config.py → process_manager.py → mlx-vlm cli.py`. Mirror that exact path for `tq_fused_prefill` (boolean; emit the CLI flag only when present, like `kv_bits`). No new mechanism.

- [ ] **Step 2: Add the field + default in mlx-serve config, emit the flag in process_manager**

Add `tq_fused_prefill: Optional[bool] = None` to the model config dataclass; in `process_manager.py`, append `--tq-fused-prefill {true|false}` to the worker argv only when the field is set.

- [ ] **Step 3: Parse in mlx-vlm cli.py → env**

```python
if args.tq_fused_prefill is not None:
    os.environ["TQ_FUSED_PREFILL"] = "1" if args.tq_fused_prefill else "0"
```

- [ ] **Step 4: Verify the env is honored (unit, no server)**

Run: `PYTHONPATH=../mlx-vlm TQ_FUSED_PREFILL=0 uv run --with pytest python -m pytest ../mlx-vlm/mlx_vlm/tests/test_turboquant_fused_prefill.py -k killswitch -v`
Expected: PASS (gate off via env).

- [ ] **Step 5: Commit (after approval)**

```bash
cd $STACK_REPO && git add main_models.yaml
cd ../mlx-serve && git add -A
cd ../mlx-vlm && git add mlx_vlm/cli.py
# commit each repo with: "feat: thread tq_fused_prefill kill-switch (YAML->serve->cli->env)"
```

---

## Task 8: Real-model validation on Qwen (needle + prefill tok/s)

**Files:** none (operational).

- [ ] **Step 1: Confirm no stray processes; restart the manager**

```bash
ps aux | grep -iE 'python|needle|eval_harness' | grep -v grep   # expect none
# bump the stack submodule to the fork commit, restart only the mlx-serve manager
```

- [ ] **Step 2: Run the 16K needle (fused on) and capture prefill tok/s + peak mem**

Run `benchmark/needle_256k.py --ctx 16000` against `Qwen3.6-27B-UD-MLX-6bit` (TQ kv_bits=3). Expected: needle PASS (retrieves the token), prefill tok/s **≥** the qb-256 baseline (memory: ~93 tok/s @16K), peak memory unchanged (~35 GB).

- [ ] **Step 3: A/B against the kill-switch (fused off → old loop) at 16K and 64K**

Set `tq_fused_prefill: false`, restart, rerun. Compare prefill tok/s and confirm identical needle result. Record both numbers. Expected: fused ≥ loop; needle identical.

- [ ] **Step 4: Document results**

Append a results block to this plan (tok/s fused vs loop at 16K/64K, peak mem, needle pass/fail). If fused is not faster end-to-end, note it (memory: TQ attention is ~28% of prefill at 16K; the op-level win is large but end-to-end gated by GDN+MLP) — this is expected and still a correctness/foundation win for the unified core.

---

## Self-Review

**Spec coverage:** §3 problem 1 (no fused MSE prefill) → Tasks 3–6. §4 flash core + pluggable dequant (MSE) → Task 3. §4.1 generation-keyed backend → this plan is the M2–M4 `simdgroup_matrix` backend; M5 TensorOps backend is a separate plan (Roadmap). §6 spikes → done (referenced as oracles). §8 numerics/TDD/test matrix → Tasks 1, 6. §9 config threading → Task 7. §10 register-pressure risk → Task 3 L-subtiling note; decomposed-vs-fused caution → measured in Task 8. Decode rewrite (§4 decode lever, Spike C/E), Prod codec (§7 Phase 3), gemma4 (§7 Phase 4) → separate plans.

**Placeholder scan:** kernel body in Task 3 references the three validated spike files as the concrete source-of-truth rather than re-pasting ~200 lines of MSL; this is intentional (the spikes are committed, runnable oracles), not a "TODO". All test code is complete and runnable. Config threading (Task 7) mirrors the existing `kv_bits` path by inspection (Step 1) because the exact mlx-serve line numbers are not pinned in this plan — that is the one reconnaissance step, scoped to a single task.

**Type consistency:** `fused_mse_prefill(queries, keys_state, values_state, scale, mask)` and `_fused_prefill_eligible(queries, keys_state, values_state)` use the same arg names and the unwrapped-state convention (`self._unwrap`) everywhere. Kernel input ordering matches `decode_attention`.

---

## Roadmap (separate follow-on plans, written when each predecessor lands)

1. **Phase 2b — decode rewrite (bandwidth lever).** GQA tile-reuse + block-split decode (Spike C/E), benchmarked head-to-head against fp16-SDPA (≤64K) and the bandwidth budget (200K). Behind the same gate. Higher-risk; measure before flipping the default.
2. **Phase 3 — Prod codec.** Wire `mode="prod"` into `_ensure_codecs` (config-threaded) + add the QJL dequant stage (1-bit sign plane · `q_proj` · `residual_norm` · `sqrt(pi/2)/dim`) to the kernel's pluggable layer. Validate quality uplift over MSE at equal storage.
3. **M5 TensorOps backend.** First task: get a running `matmul2d` via `mx.fast.metal_kernel` using the cooperative-tensor destination (Spike F proved the headers/types are reachable; `half×half→float` and `int4b/uint4b` operands exist). Then a `simdgroup_matrix`-vs-TensorOps backend switch by GPU family, and a `kv_bits=4` int4-operand path on M5. Validate on `ssh $REMOTE_HOST`.
4. **Phase 4 — generality + gemma4.** Flip `gemma4` to `kv_quant_scheme: turboquant`; global-attn layers quantize, sliding-window stays `RotatingKVCache`. Run the full matrix; document.
