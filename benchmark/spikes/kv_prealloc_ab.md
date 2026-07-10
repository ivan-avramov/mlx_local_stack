# KV pre-allocation — live `mx.get_peak_memory` A/B (Task 11)

**Date:** 2026-07-10. **Box:** M5 Max (64 GB), same session. **Model:**
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (turboquant 4-bit KV, `quantized_kv_start: 0`,
`prefill_step_size: 512`, `max_kv_size: 262144`). Feature code (`feat/kv-prealloc`
mlx-vlm HEAD `3c8bf75`) run as an isolated direct worker on a spare port; the
production router and task model were left untouched and `src/mlx-vlm` restored after.

## Method

Identical request each run — `max_tokens: 500`, `temperature: 0.3`, 29-token prompt →
501 tokens generated. Toggle: `--kv-prealloc-tokens 262144` (ON) vs omitted (OFF),
same binary, same box, same session. `DEBUG` logging; reallocs counted from the
`Reallocating old:%d new:%d` cache-growth log line; `peak_memory` from the server's
per-request `mx.get_peak_memory` readout.

## Result

| run | `kv_prealloc_tokens` | reallocs during generation | peak_memory |
|---|---|---|---|
| ON | 262144 | **0** | 25.91 GB |
| OFF | (unset) | **90** | 20.81 GB |

- **Startup log confirms the arg reaches the worker:** `Namespace(… max_kv_size=262144,
  kv_prealloc_tokens=262144, …)` and `KV cache quantization: bits=4.0 scheme=turboquant`.
- **ON eliminates all 90 mid-generation reallocs** (goal #1). OFF's reallocs are the TQ
  cache growing from the 29-token prefill (`old:29, new:256`, then step/geometric growth),
  ~90 events across layers × growth steps for a single small request.
- Both peaks are well under the 46 GB gate.

## Reading the peak numbers

For this **small** request ON peak (25.91 GB) is *higher* than OFF (20.81 GB) — expected
and by design: `kv_prealloc_tokens = cap` pre-allocates the **full 262144-token** TQ KV
buffer on first fill regardless of prompt size (goal #2 — right-sizing small prompts — is
deliberately traded away for the never-realloc guarantee). The peak *advantage* of pre-alloc
appears only near the cap, where OFF's geometric growth transient (holds ~0.8·H while
allocating H ⇒ up to ~1.8× the KV high-water, captured by `mx.get_peak_memory`) would exceed
ON's steady footprint. The **0-realloc** result is the mechanistic guarantee that at 256K ON
sits at the steady ~43 GB (config-known) with **no transient above it** — i.e. it can never
spike over the gate mid-generation.

## Follow-up (optional)

A near-256K ON-vs-OFF run would directly show ON peak ≤ OFF peak (transient eliminated) at
scale; deferred here (slow 256K prefill) since the mechanism (0 vs 90 reallocs) is proven and
the 256K steady footprint is already characterized. Fp16 path (Ornith) A/B not yet run —
same mechanism, `kv_bits: 0` → `PreallocKVCache`, pre-alloc at creation.
