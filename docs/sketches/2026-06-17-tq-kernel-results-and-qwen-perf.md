# TurboQuant kernel investigation: results and Qwen decode perf

**Date:** 2026-06-17
**Status:** Closed. Results and decision record.

Plan sketch: `docs/sketches/fused-quantized-kv-attention-kernel.md`. Design spec: `docs/superpowers/specs/2026-06-17-unified-fused-quantized-kv-attention-design.md`.

## Verdict

The big fused-kernel rewrites, both prefill and decode, were measured and are not worth shipping. The existing TurboQuant kernels are already near-optimal for what they do; the rewrites tie them at best and cost memory. The wins that matter are config-level. Final config for Qwen3.6-27B: TurboQuant, `kv_bits=4` (MSE), suffix decoding. 200K is solved, it fits in 64GB and answers correctly. The goal order that drove these calls: quality first, generality second, Apple-Silicon speed third, M5 Neural Accelerators fourth.

## Environment

Two targets, both 64GB. An M2 Max for dev, and a remote M5 Max reached over `ssh $REMOTE_HOST` with the repos under `~/Documents/ws/`. The M5 is about 7x faster for real-model turnaround, which is why most end-to-end validation ran there: 16K prefill measured 579 tok/s on M5 versus 84 tok/s on M2, a 28s wall versus 212s.

## Phase-1 spikes (A–H)

All eight spikes were empirical, run on M2 unless a row names M5.

| Spike | Question | Result |
|---|---|---|
| A | `simdgroup_matrix` MMA in `mx.fast.metal_kernel` | Viable. fp16-in/fp32-acc is exact for QKᵀ. Beats scalar `simd_sum` 3.2–8.4x on M2, 1.3–5.3x on M5 (scalar is ~3x faster there to start). Hits ~2000 GFLOP/s against an `mx.matmul` ceiling of ~3900 on M2. |
| B | LUT vs MMA at 3-bit | MMA beats LUT 3–6x. LUT dropped. |
| C | GQA tile-reuse for decode | The 2-pass kernel already coalesces the R query-heads' reads, so there is no R-fold redundancy at long context. A naive single-pass tile-reuse regresses on occupancy. |
| D | Roofline | Practical peak DRAM BW is ~310 GB/s on M2, ~558 on M5. fp16 dense `mx.fast` SDPA decode at 200K hits 233 GB/s on M2, 75% of peak. 3-bit KV moves 5.3x less traffic. |
| E | Decode @200K baseline | Production TQ decode is 2x slower than fp16 SDPA at 200K, despite being 3-bit. |
| G | Decode: compute- vs latency-bound | Compute-bound. The readonly read-ceiling (M2 136 / M5 299 GB/s) sits well above the full kernel (M2 57 / M5 182 GB/s). The cost is the per-token dequant-plus-dot, not `exp` (~9%) and not tile-reuse. |
| H | Decode compute-opt prototype | Codebook-in-threadgroup, unrolled, grouped `simd_sum`: 0–1% on M2, 1.06x at 200K on M5. Failed the gate. |

Spike H pins the root cause. The per-token 3-bit codebook dequant is a gather, not a matmul, and it is irreducible. fp16 SDPA is faster only because it skips dequant entirely. A 3-bit decode cannot match fp16 on speed, and the Neural Accelerators cannot help because they accelerate matmuls, not gathers.

## M3/M5 research and M5 empirical findings

M5 Pro/Max add per-core Neural Accelerators, matrix hardware that is absent on M1 through M4. They are not reachable from hand-written `simdgroup_matrix`; that path needs Metal 4 TensorOps / MPP. On M5, `simdgroup_matrix` performs at M4 class.

`mx.fast.metal_kernel` can JIT-compile Metal 4 TensorOps headers on M5 (the gating spike, F). `matmul2d` natively supports `half × half → float` and `int4b`/`uint4b` operands. But 3-bit is unsupported, so using it would mean either repacking to 4-bit or writing a cooperative-tensor custom dequant.

Decode is bandwidth-bound on every generation, so the 3-bit traffic lever holds everywhere. And M3+ Dynamic Caching relaxes the register cap that forces sub-1024 threads on M2.

## What got built

### Phase 2 — fused prefill

Built a decomposed prefill: dequant to model-space units, then `mx.matmul` for QKᵀ and AV. TDD against an fp32 reference, 105 tests covering the full dim / GQA / bits / L / T matrix.

Real-model 16K result: it ties the qb-256 `quantized_attention` loop at ~84 vs ~83 tok/s, and it costs +4GB from score materialization plus a 200K OOM risk. Defaulted off, opt-in via `TQ_FUSED_PREFILL`. Prefill attention is a minority of prefill cost; GatedDeltaNet and MLP dominate, so there is nothing to win here.

### Phase 3 — Prod codec

Wired through `kv_quant_mode` (Prod key, MSE value), config-threaded from YAML through mlx-serve and the CLI to `TQ_KV_QUANT_MODE`. Quality was validated on the right metric, attention output rather than L2.

| Codec / bits | Attention-output error |
|---|---|
| MSE-4 | 0.00026 |
| Prod-3 | 0.00079 |
| MSE-3 | 0.00096 |

Prod-3 beats MSE-3 because QJL gives unbiased dot products. But MSE-4 beats Prod-3 outright. So Prod is the sub-4-bit quality option, and it is not needed at 200K where 4-bit fits. Confirmed working end-to-end on real Qwen, M5 needle PASS.

### Decode rewrite

Investigated through spikes G and H. The gate failed. Stopped.

## 200K validation (M5, real Qwen3.6-27B)

`kv_bits=4` at 200K:

| Metric | Value |
|---|---|
| `prompt_tokens` | 199,297 |
| Peak memory | 40.4GB |
| Needle | PASS |
| Prefill | ~159 tok/s |
| Decode | ~9.5 tok/s |
| Wall | ~21 min |
| OOM | none |

Peak landed at 40.4GB, not the ~51GB the earlier extrapolation predicted, so it fits 64GB comfortably and likely fits 256K too. `kv_bits=4` is the 200K quality answer with no real context tradeoff.

## Qwen decode-perf investigation

### Suffix decoding

Enabled. Decode throughput depends entirely on prompt type: 17.4 tok/s on a novel/UI prompt, 106 tok/s on a context-quoting prompt, a 6x swing. Suffix decoding is excellent for retrieval and quoting and useless for novel or UI generation.

### Neural Accelerators for prefill

Definitive negative result. The full toolchain is now in place: Xcode installed, the Metal Toolchain component downloaded (`xcodebuild -downloadComponent MetalToolchain`), and mlx built from git main (0.32.0.dev20260617) from source with the Metal-4 compiler. NA still does not activate on M5. Plain matmul fp16/fp32 measures 1.35–1.42x, not the ~3–4x NA would give. `quantized_matmul` holds at ~50–57 TFLOP/s, unchanged from the wheel, and fp16 SDPA at ~41 TFLOP/s shows no jump.

The NA kernels are present in mlx main: `steel/gemm/nax.h` and `steel/attn/nax.h` both call `mpp::tensor_ops::matmul2d`. The runtime dispatch just does not select them on M5, and there is no env flag to force it (checked the compiled lib). This is an upstream mlx dispatch/integration gap, kernels coded but not wired for general or quantized matmul on M5, not a build problem. The build was never the blocker. It is not fixable from our side without patching mlx's C++ dispatch. M5's fast prefill is steel-GEMM, not NA.

### Novel/UI decode lever

The lever is MTP self-speculation, not a draft model. A draft is blocked because no small Qwen3.6 exists: the smallest is 27B, and the vocab of 248,320 is family-only.

MTP is the only viable novel-decode speedup, worth roughly 1.5–2.5x. The config declares `mtp_num_hidden_layers=1` and the base has an MTP head, but the unsloth UD-MLX-6bit conversion dropped it: 1700 weight keys, zero `mtp` keys, and the loader strips `mtp.` keys anyway. Enabling it requires a checkpoint that keeps the head, un-stripping the loader, and wiring `draft_kind=mtp` for the vision-language model. Substantial work, deferred.

## Final config and what shipped

`main_models.yaml`, Qwen3.6-27B-UD-MLX-6bit:

```yaml
kv_quant_scheme: turboquant
kv_bits: 4
draft_kind: suffix
```

Fork commits, both pushed to `ivan-avramov/*` main:

- mlx-vlm `7009a3f`: fused prefill off by default, Prod codec, `kv_quant_mode` threading.
- mlx-serve `e9ec620`: `kv_quant_mode` read from YAML.

Per-context guidance:

| Context | KV scheme | Why |
|---|---|---|
| ≤64K | fp16 KV | Lossless and fastest |
| 100K–200K | TQ `kv_bits=4` | Best quality that fits |
| >256K | Prod-3 | Only under extreme memory pressure |

## Open and future work

- MTP self-speculation for novel/UI decode: re-convert keeping the MTP head, then wire `draft_kind=mtp`.
- NA via mlx: the source build is done and confirms NA does not activate (upstream dispatch gap). Re-test on a future mlx release that wires the dispatch; the kernels are already present, so it may turn on in a later version. The discriminator (`benchmark/spikes/na_discriminator.py`) and the source-built mlx (`~/Documents/ws/pyenv/.venv`) are available to re-run.
- The fused prefill decomposed path stays available behind `TQ_FUSED_PREFILL=1`. A fused-flash variant is unbuilt and not worth building, since prefill is GatedDeltaNet/MLP-bound.
