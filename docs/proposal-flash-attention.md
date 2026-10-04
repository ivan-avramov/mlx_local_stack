# Proposal: qualify fused attention dispatch in the MLX stack

Recorded: 2026-10-03. Status: proposal; no runtime trace, kernel experiment or activation has been performed in this session. `docs/PLAN.md` remains the only execution queue. Saving this document authorizes no implementation or GPU work.

## Outcome

Determine whether MLX's fused attention kernels improve practical memory, prefill latency and decode behavior on the shipped models. Start with `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` at its deployed native16 KV configuration. Preserve quality, full active preallocation and existing sampling/predictor settings.

`OLLAMA_FLASH_ATTENTION` controls Ollama and has no effect on this MLX stack. No runtime migration is proposed.

## What FlashAttention changes

Ordinary scaled dot-product attention computes `softmax(Q K^T * scale + mask) V`. An unfused implementation can write the query/key score matrix and normalized probabilities to device memory before multiplying by values.

FlashAttention-style kernels tile queries and keys/values, fuse the operations, and maintain a running softmax maximum, normalization sum and output accumulator. This computes the same mathematical attention without storing the complete score/probability matrix. It reduces temporary memory and memory traffic; it does not reduce model-weight storage, persistent KV capacity or the number of token pairs considered in full attention. Full prefill attention still has quadratic arithmetic complexity. Floating-point rounding can change outputs despite mathematical equivalence.

Chunked prefill bounds the query dimension already: its score scratch scales with query-chunk length times accumulated key length, rather than a single full-context square. Fused attention can still reduce that scratch and its memory traffic. Decode uses few query tokens and a different kernel regime; prefill improvements do not imply the same decode speedup.

This is an implementation of softmax attention, not a new model architecture. It can apply to causal language attention, bidirectional attention, cross-attention, GQA/MQA and image-transformer attention when the backend supports the precise operation. Linear attention and recurrent state-space updates use different mathematics and are not replaced by softmax FlashAttention. Hybrid models benefit only on applicable layers.

## Source findings, not runtime evidence

The local environment metadata reports MLX 0.32.2. The assessed model has head dimension 256, 64 layers with full attention every fourth layer, native16 KV and `prefill_step_size: 512` in `main_models.yaml`.

The stack's `src/mlx-vlm/mlx_vlm/models/base.py::scaled_dot_product_attention` sends ordinary native KV to `mx.fast.scaled_dot_product_attention` without `force_fused`. Quantized caches have separate dispatch paths; forcing the native primitive does not automatically replace them.

MLX 0.32.2's Metal `ScaledDotProductAttention::use_fallback` normally selects unfused attention for multi-query head dimensions 192/256. One exception uses NAX for eligible causal 256-dimensional shapes with at least 1024 query tokens and no array mask. The configured 512-token chunks do not meet that exception. Therefore the ordinary prefill path is predicted to be unfused; confirm actual inputs, runtime version and kernels before drawing a performance conclusion. Decode and MTP verification need their own inspection.

Do not treat existing documentation's blanket descriptions of native16 as fused SDPA as kernel-trace evidence. A dated correction belongs with completed qualification, not an unmeasured claim of improvement.

MLX supports `force_fused=True`, which bypasses selection heuristics when a fused kernel exists and raises when no supported kernel exists. Shape, dtype, device, masking, layout and optional features determine eligibility. The documented trade-off can be lower temporary memory with slower execution.

MFLUX's `Qwen/Qwen-Image-2.1` attention implementation calls MLX's fast primitive with 128-dimensional heads. Its eligibility differs from the chat model's 256-dimensional case. Image-kernel qualification is separate and does not block recording the deferred image proposal.

## Proposed configuration contract

Use a per-model worker-startup attention policy. Candidate names are illustrative, not implemented configuration:

- `auto`: preserve MLX dispatch heuristics.
- `force_fused`: request fused execution for the explicitly qualified native softmax-attention paths; unsupported operations fail clearly in the experimental arm.

Record the scope of the policy: prefill, decode and verification paths must not be silently conflated. A narrower production policy may be chosen after results, but it is a distinct recipe requiring qualification.

Flow: registry -> mlx-serve worker arguments -> mlx-vlm model/attention configuration -> MLX primitive. Resolve the policy once when loading the worker; do not add a chat request parameter or per-session override. A changed policy requires a new worker and provenance identity. All sessions using that worker inherit it.

Static policy does not imply one kernel for every operation: <!-- allow-shorthand --> `auto` dispatches dynamically by shape; a qualified fused policy can still use different fused prefill/decode kernels. Transparent API behavior is compatible with observable server-side policy and kernel diagnostics.

Implement in the parent `mlx-vlm` fork, with parent `mlx-serve` configuration/argument plumbing if adopted. Avoid mutable module-global state that would leak across model instances. Provenance must record policy, scope, MLX version, serving revisions and registry hash. This is a structural serving control, not a sampling knob. No callers or client sampling carriers need to send it.

## Qualification sequence

1. Re-check source/dependency pins and inspect actual shape, dtype, mask and cache paths for prefill, cached continuation, decode and MTP verification. Validate any trace instrument against a known fused and a known fallback case.
2. Add inexpensive tests for default preservation, startup-policy propagation, unsupported fused shapes, instance isolation and unchanged quantized-cache dispatch. Follow failing-test-first discipline.
3. Prepare experimental overlays/worker policies for default and forced-fused arms. Keep prefill size 512, cap/preallocation 262144, native16 KV, deployed sampling, thinking headroom and shipped predictor state identical.
4. Start with a seeded five-item pilot. Do not alter the production worker during a live campaign. Coordinate exclusive GPU access before launching qualification.
5. Compare short and intermediate contexts and a matched near-256K capacity prompt, including cached multi-turn continuation. Report prefill and decode separately. Full-context peak is required for capacity conclusions.
6. Compare quality on relevant code/reasoning/retrieval items and tool/vision continuation smokes. Changes to output hashes trigger inspection, not an automatic quality-failure verdict. Use independent loaded instances and matched seed schedules; do not presume reload determinism.
7. Review results before changing defaults. If warranted, land the policy and dated documentation corrections with the measured scope and limits.

Do not increase chunk size to enter the NAX exception in this experiment. Do not quantize KV, change allocator limits, alter sessions, reduce preallocation, change MTP or tune sampling concurrently. Those would be separate variables.

The worker's allocator pool limit is currently derived partly from expected attention scratch. Keep that policy fixed in the first comparison; distinguish active MLX peak from retained allocator memory and system pressure. Any later allocator-policy optimization is separate.

## Measures and acceptance

Record actual kernel/path evidence, peak MLX memory, active/cached allocation observations, system pressure/swap, prefill time/TTFT, decode rate, end-to-end time, output hashes, convergence and failures. Log mechanism and power conditions. Use the current monitoring/provenance rules and `metrics.md`; timeouts must cover legitimate generations and transport failures must abort.

For task results, report accuracy, strict accuracy at the matched resolved budget, convergence and nonconvergence kinds. Use paired intervals and axis MDE; keep sessions separate under C109. Pre-register sufficient quality coverage before broad adoption. This is a serving optimization, not evidence for a B/C pick change.

Adoption requires correct masking/cache behavior, stable full-context execution and quality within the standing tolerance. Recommend from the observed quality/memory/latency trade-off; do not assume fused is always faster or that a lower peak guarantees useful system headroom. Preserve `auto` if forcing fusion has no practical benefit.

## Open decisions on resumption

- Exact policy field/CLI spelling and model-instance propagation mechanism.
- Trace method and operation scope for the first experimental arm.
- Pre-registered quality corpus, repeats, power and resource budget.
- Whether the measured trade-off supports a model-specific deployment policy.

These are design questions within this proposal, not additional execution queues. Implementation and live experiments need separate approval.

## Sources

- [FlashAttention paper](https://arxiv.org/abs/2205.14135)
- [MLX fast-attention API](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.fast.scaled_dot_product_attention.html)
- [MLX 0.32.2 Metal dispatch](https://github.com/ml-explore/mlx/blob/v0.32.2/mlx/backend/metal/scaled_dot_product_attention.cpp#L715)
- [Model architecture](https://huggingface.co/caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/blob/main/config.json)
- [MFLUX image attention](https://github.com/mflux-community/mflux/blob/main/src/mflux/models/qwen21/model/qwen21_transformer/qwen21_attention.py)
- Local: `main_models.yaml`, `src/mlx-vlm/mlx_vlm/models/base.py`, `src/mlx-vlm/mlx_vlm/server/cli.py`, `docs/metrics.md`, `docs/serving-path.md`.

## Review 2026-10-04 (Claude Fable 5.1; the proposal above was produced by GPT-Astra) <!-- allow-shorthand -->

**Verdict: pick it up.** The mechanism is right, the structural contract (registry → worker argument → fork attention policy, resolved
once per worker, recorded in provenance) is right, and one microbenchmark on this box turns the "expected trade-off" into a measured
one. Corrections and additions:

1. **The trade-off claim is backwards for our shape.** Measured 2026-10-04 on the M5 Max (MLX 0.32.2, `mx.fast.scaled_dot_product_attention`,
   fp16, 1 batch, 24 query / 4 KV heads, head dim 256, 512-query chunk against 131072 keys — the first pick's real prefill shape):

   | mask | default dispatch | `force_fused=True` |
   |---|---:|---:|
   | `"causal"` | 144 ms | **46 ms** (3.1×) |
   | boolean array | 127 ms | **53 ms** (2.4×) |
   | `"causal"`, 1024-query chunk (NAX exception) | 84 ms | — |
   | head dim 128, 512-query chunk (fused by default) | 16 ms | — |

   The forced-fused kernel exists for this shape (no exception raised), runs ~3× faster, and neither path showed a material transient
   allocation with the allocator cache cleared (≤ 0.07 GiB) — so the benefit is **prefill speed**, not memory. The proposal's "lower
   temporary memory with slower execution" should not be carried forward as the expectation.
2. **Scale of the win.** Only 16 of the first pick's 64 layers are full attention (`full_attention_interval: 4`; the other 48 are linear
   attention with 128-dim linear K/V, O(N), untouched by this flag), but those 16 are the quadratic term. Integrating the per-chunk saving
   (~98 ms per layer at 128K keys, linear in keys) over a 256K prefill gives on the order of 10–15 minutes of TTFT per full-context prompt,
   or ~3 s per 64K prompt. Decode is unaffected (single-query vector kernel). MTP verification runs with a few query tokens and sits in
   the same regime as decode; measure, do not assume.
3. **Which arms it touches.** In the parent fork `../mlx-vlm/mlx_vlm/models/base.py::scaled_dot_product_attention` there are three paths:
   TurboQuant caches (own fused TQ kernels or dequantize-then-SDPA), bit-quantized caches (`quantized_scaled_dot_product_attention`), and
   native (`mx.fast.scaled_dot_product_attention`). `force_fused` reaches only the native path, plus the two chunked-prefill call sites
   further down the file. So the first pick (native16, C81) is the beneficiary; the TQ4 picks need their own qualification of the
   TurboQuant prefill kernel and are out of scope here. The cited path `src/mlx-vlm/...` does not exist in this clone (the submodule is
   not checked out); per AGENTS.md the edit goes in the parent fork, then the submodule bump.
4. **The cheaper competing knob.** `prefill_step_size: 1024` enters MLX's NAX exception and gets the fused kernel without a flag (84 ms per
   1024 ≈ 42 ms per 512). The proposal is right to exclude it from the first arm (it changes chunk scratch, the reason 512 was chosen), but
   it belongs in the design as a second arm once fused attention has removed the score scratch that made 512 necessary.
5. **Risks to pre-register.** (a) Output hashes will change (summation order); the gate is the standing ±5 pp quality tolerance on a paired
   axis, not hash equality. (b) `force_fused` raises on unsupported combinations — sinks, some mask/dtype combinations; the experimental
   worker must fail loudly, and the qualification needs both mask kinds the fork emits (`"causal"` and array masks from
   `create_attention_mask` / `cache.make_mask`). (c) Interaction with the M5 Neural Accelerators and with the allocator pool limit (derived
   from attention scratch) is unmeasured; keep the pool limit fixed in arm 1 as the proposal says. (d) Reload nondeterminism (C109) means
   the A/B needs k=2 sessions per arm.
6. **Suggested shape as a PLAN row (M57):** build ~1 day (flag plumbing in `mlx-vlm` + `mlx-serve`, tests for default preservation,
   propagation, loud failure, per-instance isolation); qualification ~1 box-day on the first pick: TTFT and decode at 8K / 64K / 128K /
   256K prompts with the full-context peak, plus one paired quality axis (humanevalplus/mbppplus n=100 at the deployed profile) and the
   AgentBench 5-item pilot, auto vs force_fused, two sessions each. Decision rule: adopt if quality is within ±5 pp and TTFT improves at
   ≥ 64K; keep `auto` otherwise. This is Phase 2 (serving optimization), not B/C evidence.
