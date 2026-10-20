# P400 plan — Cursor gpt-5.6-sol-high PLAN review round 2 of 3 (v2, 2026-10-19)

Prompt: `plan-round2.prompt-head.md` + the round-1 output + v2; `--mode ask`, stream-json — the `result` text verbatim:

P401’s proposed guard is safe on the ordinary scalar-offset paths, but its exact placement matters: the current slicing branch is bypassed for per-row batched offsets and for block-local verifier positions. I’m checking the inherited Qwen4/Qwen3.5-MoE surface and whether the plan’s test matrix proves that distinction rather than only the original lazy-embedding repro.## Round-1 findings

- **T1 — RESOLVED.** §3 limits the exactness claim to unpadded B=1 and §4.6 characterizes B=2 left padding, preserving a strict xfail if the separate defect is confirmed.
- **T2 — RESOLVED.** §4.1–5 separates law, token, row/state, and direct-path tests; asserts cache/codec/bits/width; updates TurboQuant helpers; and uses independent caches.
- **T3 — RESOLVED.** §5.2 permits carryover only when every ON request reports `verify_blocks_per_query == 0`. Policy-served straddles are unaffected by A, so they need not be zero.
- **T4 — NOT RESOLVED.** See full finding below.
- **T5 — RESOLVED.** §2 now maps Qwen3.5, Qwen4 QSA, Gemma4, and Nemotron-H accurately; §4.8 adds the Qwen4 regression.
- **T6 — PARTIALLY RESOLVED.** See full finding below.
- **T7 — RESOLVED.** §4.9 adds pinned formatting and collection-count checks.

## P401 safety

The narrow intended guard—validate the result only when an explicit longer position tensor was actually sliced—is safe for:

- 3-D mRoPE: ellipsis slicing and checking `shape[-1]` are correct.
- Primed session reuse, APC, canonical prefill, and ordinary chunked prefill: each supplies full-prompt positions covering `cache_offset + chunk_length`.
- Batched offsets: that path currently bypasses scalar slicing, so the guard should not be applied using one scalar offset.
- Qwen3.5 speculative verification: it normally derives positions internally rather than supplying the full explicit tensor.
- Qwen4 verification: safe only if equal-length, already block-local positions remain unsliced.

EpiCache presents a separate logical-offset problem described in T9.

### T4 — BLOCKER — Prior GPU overlap remains accepted conditionally

**Problem:** §5 discloses that a Metal fixture overlapped smoke 8 but leaves whether the smoke “stands” to the operator. That does not satisfy T4’s requirement to treat any overlapped performance run as contaminated. Separate process state protects functional correctness, not timing, memory pressure, or GPU scheduling evidence.

**Concrete failure scenario:** The fixture inflates or suppresses smoke throughput or peak memory. Smoke 8 is subsequently cited as valid baseline evidence because the inflation was assumed conservative, although GPU interference is not directionally guaranteed.

**Change to plan:** Mark smoke 8 contaminated unconditionally. If the mandatory new-pin smoke supersedes it, no old-pin rerun is needed; otherwise rerun it on an idle GPU. Remove §7 decision (2).

### T6 — MEDIUM — Performance acceptance remains incomplete

**Problem:** §5.3 adds the requested width-2 benchmark and a ≤3% throughput bound, but gives no acceptance bound for peak memory and no repetition/noise protocol. The two regression smokes merely “compare” peak memory.

**Concrete failure scenario:** A passes the throughput threshold while materially increasing peak memory, or a single noisy timing measurement decides a 3% boundary.

**Change to plan:** Pre-register warmup/repetition and aggregation, plus an explicit peak-memory bound. Apply the throughput bound to the repeated width-2 probe, not a single smoke observation.

### T8 — HIGH — P401’s exact guard condition and positive matrix are underspecified

**Problem:** §3 and §4.7 do not explicitly distinguish a full-prompt position buffer from legitimate already block-local positions. An unconditional check that `cache_offset + chunk_length <= position_ids.shape[-1]` would be wrong.

**Concrete failure scenario:** Qwen4 `_speculative_verify` constructs absolute block-local positions of shape `[B, L]` and calls the inherited Qwen3.5 wrapper with a non-empty cache. Their length equals `L`, not `cache_offset + L`; an over-broad implementation would reject every verification block.

**Change to plan:** Specify the algorithm:

```python
if position_length < chunk_length:
    raise ValueError(...)
if position_length > chunk_length:
    position_ids = position_ids[..., cache_offset : cache_offset + chunk_length]
    if position_ids.shape[-1] != chunk_length:
        raise ValueError(...)
# Equal length is already block-local; do not slice.
```

Add positive tests for 3-D full-prompt slicing, equal-length warm block-local positions, Qwen4 speculative verify, and per-row batched offsets.

### T9 — HIGH — EpiCache requires logical, not physical, slice offsets

**Problem:** Qwen3.5 currently obtains the explicit-position slice start from `EpiCacheKVCache.offset`, which is the retained physical KV length. Its true sequence position is `rope_offset = evicted + offset`. A short-slice guard normally will not fire because the physical offset is smaller; it therefore silently permits incorrect positions.

**Concrete failure scenario:** After processing 5,120 tokens with a 4,096-token EpiCache budget, physical offset is 4,096 while `rope_offset` is 5,120. The next full-prompt position slice starts at 4,096 and repeats old RoPE positions, yet has the expected length and passes P401.

**Change to plan:** Either use `rope_offset` as the explicit-position slice start and add an EpiCache value-level test, or explicitly exclude EpiCache from P401 and file this as a separate local correctness defect. A shape-only test is insufficient.

VERDICT: DISAGREE T4 T8 T9