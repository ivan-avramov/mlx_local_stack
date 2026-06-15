# TurboQuant Prefill Memory Spike: Diagnosis and Fix

## Summary

Memory grows beyond the pre-allocated TQ cache size during long-context prefill because
`mx.fast.scaled_dot_product_attention` only accepts fp16/bf16/fp32 tensors. When the
prefill attention pass runs, the entire accumulated compressed KV cache gets dequantized
to fp16 as a temporary allocation before being fed to SDPA. The cache storage itself is
not the problem — the compute path is.

**Confirmed symptom:** ~27 GB baseline (4-bit weights + pre-allocated TQ cache) growing
to ~50 GB at 96K tokens in context. Matches the projection: full fp16 KV at 96K on
Gemma 4 31B ≈ 20.78 GiB × (96K/256K) ≈ 7.8 GiB temporary fp16 KV, plus activation
overhead. The upstream mlx issue tracker explicitly names this: "31 GB activation spike
at 128K context on gemma-4-31B" for the dequantize path.

The decode path (L=1) is not affected because `_fused_integer_decode_single_tile_kernel`
reads compressed KV directly without creating a fp16 copy. The prefill path (L>1) has no
equivalent fused kernel.

---

## Diagnosis: Locating the Problem in the Fork

The bug lives in the prefill attention computation path, not the cache storage.

### Step 1 — Verify TQ storage is working

Before touching the compute path, confirm the cache is actually storing compressed data.
Add this instrumentation around the prefill call in `generate.py`:

```python
import mlx.core as mx

def log_cache_memory(cache, label=""):
    for i, c in enumerate(cache):
        if hasattr(c, 'keys') and c.keys is not None:
            k = c.keys
            v = c.values
            print(f"[{label}] layer {i}: "
                  f"keys dtype={k.dtype} shape={k.shape} "
                  f"nbytes={k.nbytes/1e9:.2f} GB, "
                  f"values nbytes={v.nbytes/1e9:.2f} GB")
            break  # just check first layer

# call before and after prefill
log_cache_memory(cache, "pre-prefill")
# ... run prefill ...
log_cache_memory(cache, "post-prefill")
```

If `k.dtype` is `uint32` (packed TQ), storage is correct. If it's `float16`, TQ is not
being applied to the cache at all and the spike has a different cause.

### Step 2 — Identify the dequantization callsite

In `turboquant.py` (or wherever `TurboQuantKVCache` is defined), look for the attention
path. There are two patterns to look for:

**Pattern A — explicit dequantize before SDPA:**
```python
# THIS IS THE PROBLEM
k_fp16 = self._dequantize(self.keys[:seq_len])   # allocates full fp16 copy
v_fp16 = self._dequantize(self.values[:seq_len])
output = mx.fast.scaled_dot_product_attention(q, k_fp16, v_fp16, ...)
```

**Pattern B — prefill bypass (TQ skipped entirely during prefill):**
```python
# Also a problem, just for a different reason
if q.shape[-2] > 1:  # prefill
    output = mx.fast.scaled_dot_product_attention(q, self.keys_fp16, ...)
else:  # decode
    output = self._fused_integer_decode_single_tile_kernel(q, ...)
```

Either way, the long-context temporary allocation follows the same path. Pattern A is
more common in naive TQ integrations; Pattern B was explicitly documented in at least
one community TQ-for-MLX port.

### Step 3 — Measure the spike

```python
mx.metal.clear_cache()
before = mx.metal.get_active_memory()
# run single prefill step over your 96K token prompt
output = model(input_ids_96k, cache=cache)
mx.eval(output)
after = mx.metal.get_active_memory()
print(f"peak delta: {(after - before) / 1e9:.1f} GB")
```

If delta is ~7–23 GB at 96K context, the dequantize path is confirmed.

---

## Fix Path A — Chunked Prefill (Quick Win, ~2 hours)

This is the right immediate fix. It does not eliminate the temporary allocation, but
caps it to `chunk_size × (per-token fp16 KV size)` rather than the full context size.

The temporary allocation is proportional to the number of tokens being attended to in
one SDPA call. Splitting the prompt into chunks means each chunk's temporary fp16 KV
copy is small and released before the next chunk runs.

### Implementation

In `generate.py`, inside `stream_generate()` or the equivalent prefill section, replace
the single full-context prefill with a chunked loop:

```python
PREFILL_CHUNK = 2048  # tune: larger = faster prefill, larger spike

def chunked_prefill(model, input_ids, cache, chunk_size=PREFILL_CHUNK):
    """
    Process prompt in chunks to cap peak memory from TQ dequantization.
    Each chunk's temporary fp16 KV allocation is released between chunks.
    """
    seq_len = input_ids.shape[1]
    
    for start in range(0, seq_len - 1, chunk_size):
        end = min(start + chunk_size, seq_len - 1)  # -1: last token handled in generate
        chunk = input_ids[:, start:end]
        
        # Forward pass for this chunk (populates KV cache)
        _ = model(chunk, cache=cache)
        mx.eval(cache)       # materialize cache writes
        mx.metal.clear_cache()   # release temporary fp16 dequant allocations
    
    # Return the last token for the generate loop
    return input_ids[:, -1:]
```

**Chunk size tuning:**

| Chunk size | Peak spike (Gemma 4 31B fp16 KV) | Prefill speed |
|------------|----------------------------------|---------------|
| 512        | ~0.04 GB                         | slowest       |
| 2048       | ~0.16 GB                         | good           |
| 8192       | ~0.63 GB                         | fast           |
| 16384      | ~1.27 GB                         | near-baseline  |

At chunk=2048 the spike is negligible and prefill throughput is acceptable. The
`mx.metal.clear_cache()` call is important — without it, MLX's Metal allocator holds
the released buffers for potential reuse and the OS-level RSS still grows.

### Caveat

Chunked prefill breaks prefix caching (PromptCacheState) if the cache reuse logic
expects a single contiguous prefill. Verify your cache-state key includes the full
context hash, not just per-chunk hashes.

---

## Fix Path B — Fused Prefill Attention Kernel (Correct Fix, ~1–3 days)

This is the proper solution: a Metal kernel that reads compressed K/V directly during
the prefill attention pass, with no intermediate fp16 tensors ever written to DRAM.

The existing `_fused_integer_decode_single_tile_kernel` already does this for L=1
(decode). The prefill case requires a tiled Flash Attention variant that decompresses
K/V on-the-fly in registers.

### Design

The kernel signature maps to the decode kernel, extended for seqlen_q > 1:

```
Input:
  q:         [batch, heads, seqlen_q, head_dim]  -- fp16/bf16
  k_packed:  [batch, kv_heads, seqlen_k, head_dim // pack_ratio]  -- uint32 TQ-packed
  v_packed:  [batch, kv_heads, seqlen_k, head_dim // pack_ratio]  -- uint32 TQ-packed
  codebook:  [8]  -- Lloyd-Max 3-bit quantization levels  -- fp16
  rotation:  [head_dim, head_dim]  -- Walsh-Hadamard rotation matrix (or seed)

Output:
  out:       [batch, heads, seqlen_q, head_dim]  -- fp16/bf16
```

### Metal kernel outline

```metal
// TQ prefill attention kernel — reads 3-bit packed KV, no fp16 allocation
// Tile: seqlen_q_tile × seqlen_k_tile

kernel void tq_prefill_attention(
    device const half*    q          [[buffer(0)]],   // [B, H, Sq, D]
    device const uint*    k_packed   [[buffer(1)]],   // [B, Hkv, Sk, D/10] (3bit packed)
    device const uint*    v_packed   [[buffer(2)]],   // [B, Hkv, Sk, D/10]
    device const half*    codebook   [[buffer(3)]],   // [8] Lloyd-Max levels
    device half*          out        [[buffer(4)]],   // [B, H, Sq, D]
    constant uint&        Sq         [[buffer(5)]],
    constant uint&        Sk         [[buffer(6)]],
    constant uint&        D          [[buffer(7)]],
    threadgroup half*     shmem      [[threadgroup(0)]],
    uint3                 tid        [[thread_position_in_threadgroup]],
    uint3                 gid        [[threadgroup_position_in_grid]])
{
    // Each threadgroup handles one (query_tile, batch, head) slice.
    // K tile: load packed uint32 from k_packed into registers
    // Unpack 10 × 3-bit indices per uint32 → codebook lookup → fp16 in registers
    // Compute Q×K^T tile, apply causal mask
    // Online softmax (flash-attention style across K tiles)
    // Accumulate weighted V (same unpack path for values)
    // Write output — no intermediate fp16 K or V ever hits DRAM

    const uint q_row  = gid.x * SQ_TILE + tid.x;
    const uint kv_col = gid.y * SK_TILE;          // outer K loop
    
    // --- unpack a K tile into registers ---
    half k_tile[SK_TILE][HEAD_DIM];  // lives in registers / threadgroup shmem
    for (uint k = 0; k < SK_TILE && (kv_col + k) < Sk; k++) {
        uint base = /* packed index for (batch, head, kv_col+k) */;
        for (uint d = 0; d < D / 10; d++) {
            uint packed = k_packed[base + d];
            // unpack 10 × 3-bit values
            for (uint j = 0; j < 10; j++) {
                uint idx = (packed >> (j * 3)) & 0x7;
                k_tile[k][d * 10 + j] = codebook[idx];  // in-register codebook lookup
            }
        }
        // apply inverse Walsh-Hadamard rotation (can be done as a butterfly in shmem)
        fast_had_decode(k_tile[k], D);
    }
    
    // ... standard flash attention tiling from here using k_tile and equivalent v_tile
}
```

### Rotation handling

TurboQuant applies a Walsh-Hadamard transform to K/V vectors before quantizing. The
inverse rotation during decode is a butterfly operation over `head_dim`. For head_dim
values that are powers of 2 (Gemma 4 31B: global layers head_dim=512, local=256) the
Fast Walsh-Hadamard Transform (FWHT) can be computed in `log2(D)` butterfly stages
entirely in threadgroup memory with no extra DRAM traffic.

If you used a seeded random rotation instead of FWHT (some TQ variants do this), store
the rotation matrix in constant buffer or precompute the butterfly factors.

### Integration with mlx-vlm

The fused kernel would be called from `TurboQuantKVCache.attention()` with a branch:

```python
def attention(self, q, mask=None):
    seqlen_q = q.shape[-2]
    if seqlen_q == 1:
        # existing decode kernel
        return self._fused_integer_decode_single_tile_kernel(q, mask)
    else:
        # new prefill kernel
        return self._fused_prefill_attention_kernel(q, mask)
```

The `mx.fast.metal_kernel()` dispatch interface is the right way to invoke this from
Python/MLX. Follow the same pattern as `_fused_integer_decode_single_tile_kernel`.

---

## Verification

After applying either fix, verify with this sequence:

```python
# 1. Baseline: measure peak memory at different context lengths
for ctx_len in [16_000, 32_000, 64_000, 96_000, 128_000, 256_000]:
    mx.metal.clear_cache()
    mx.metal.reset_peak_memory()
    
    tokens = make_test_prompt(ctx_len)   # e.g. repeat a code file
    output = run_prefill(model, tokens, cache)
    mx.eval(output)
    
    peak = mx.metal.get_peak_memory() / 1e9
    print(f"ctx={ctx_len//1000}K: peak={peak:.1f} GB")

# Expected after fix (chunked prefill, Gemma 4 31B 4-bit, pre-allocated 256K TQ cache):
# ctx=16K:  peak≈28 GB
# ctx=64K:  peak≈29 GB
# ctx=128K: peak≈30 GB
# ctx=256K: peak≈32 GB
#
# vs before fix:
# ctx=96K:  peak≈50 GB  (the spike you observed)
# ctx=256K: OOM or thrash

# 2. Quality check: verify TQ decode still works correctly after prefill
sample = generate_tokens(model, "print hello world in Python", cache, n=50)
assert "print" in decode(sample)   # basic sanity

# 3. Needle-in-haystack: confirm the long-context content is actually being used
# (not just that the model doesn't OOM)
needle = "SECRET_TOKEN_XK9F2"
haystack = build_256k_context_with_needle(needle, needle_position=0.7)
response = generate(model, haystack + "\nWhat is the secret token?", cache)
assert needle in response, "Model lost the needle — context not being used"
```

---

## Recommended Task for Opus

Hand Opus the following:

1. This document
2. `turboquant.py` from your fork
3. `generate.py` prefill section (the loop around `model(input_ids, cache=cache)`)
4. The existing `_fused_integer_decode_single_tile_kernel` Metal source

Ask Opus to:
- Confirm which of Pattern A or Pattern B applies to your fork
- Implement the chunked prefill workaround in `generate.py` first (quick win)
- Then scope the fused prefill kernel effort based on your existing Metal kernel's structure

The chunked prefill is a one-afternoon change. The fused kernel is the correct solution
but is 1–3 days of Metal work depending on how close your existing decode kernel is to a
form that can be extended for seqlen_q > 1.
