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

## Side-agent note, 2026-10-04 (recorded verbatim at the operator's request; to be discussed in a dedicated session)

> Heads up · The flash-attention microbench the main agent just ran suggests a ~3× attention speedup on long prompts for your first pick.
>
> **Fused attention looks like a real prefill win**
> * The GPT-Astra proposal predicted that MLX's default kernel choice is the *slow, unfused* one for your first pick, because its attention heads are 256 wide and prompts are fed in 512-token chunks.
> * The main agent tested exactly that shape on your box: the default path took **144 ms** per attention layer against 128K tokens of context, versus **46 ms** with MLX's `force_fused=True` flag. Same result shape, no errors.
> * That is only a microbench of one operation, not an end-to-end prompt. But if it transfers, prefill of very long prompts (the 256K case you care about) could get noticeably faster, and the quadratic scratch memory per chunk goes away.
> * Caveats the proposal gets right: it applies only to the 16 full-attention layers (the rest are linear attention), the TQ4-cached models route through a different path, and outputs can change by rounding, so quality must be re-checked.
> * **This is the strongest argument yet for picking up the flash-attention proposal**; expect the main agent to say so, but the number above is the part worth remembering.

Annotation (Claude Fable 5.1, same day) <!-- allow-shorthand -->: everything above matches the measurement except one clause — "the quadratic
scratch memory per chunk goes away" was NOT observed. With the MLX allocator cache cleared, the transient peak was ≤ 0.07 GiB on the default
path and ~0 on the forced path at the measured shape, i.e. MLX's unfused fallback does not materialise the full 512 × 131072 score matrix
either. The measured benefit is prefill time; any memory benefit must be shown on the real serving path (full-context peak) before it is
claimed. Open for the dedicated session: whether to queue it as M57 per the review above.

## Design session 2026-10-04 (Claude Fable 5.1) — M57 design AS PRESENTED; NOT approved, nothing built or run <!-- allow-shorthand -->

Record of the design the operator was shown (ids P25–P44). Superseded where the reviews below say so.

**Corrections to the 2026-10-04 review**

- P25 — One call site. The prefill path of `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` reaches attention only through
  `Qwen3_5Attention` (`mlx_vlm/models/qwen3_5/language.py`) into the native branch of `base.py::scaled_dot_product_attention`.
  `chunked_attention` and `ensure_fused_sdpa` are vision-tower helpers, not chunked-prefill sites; chunking is the generation loop
  reading `PREFILL_STEP_SIZE`.
- P26 — Predicted TTFT from a linear + quadratic fit of the C82 ladder rows (325 s at 131K, 1063 s at 261K; quadratic share 64 % /
  78 %) with the microbench 3.1× applied to the quadratic part: 8K ≈ unchanged, 64K 111 → 76 s, 128K 325 → 185 s, 256K 1063 → 500 s.
  The review's "~3 s per 64K prompt" was ~10× too small; the microbench over-predicts the in-situ quadratic time ~1.4×.
- P27 — Claimed that MTP verification is multi-query and unfused under `auto` (REFUTED in the review below).
- P28 — The microbench was fp16; the served dtype was not instrumented.
- P29 — humanevalplus/mbppplus prompts never exercise the long-key regime; add a long-context gate.
- P30 — Two zero-build probes before funding a build: a no-model microbench matrix (dtype × query length × mask × key count: raises,
  time, max-abs-diff) and an overlay-only 128K probe at `prefill_step_size: 1024` under `auto`.

**Proposed M57 row** (P31–P33): registry `attention_policy: auto | force_fused` → mlx-serve `--attention-policy` → resolved once at
worker model load → attribute on the instance's `Qwen3_5Attention` modules → keyword into the native branch only. Acceptance AC1–AC10:
default preservation (byte-identical cmdline, no keyword reaches MLX), propagation (+ a forced-call counter in timings), loud failure
(config-load errors, worker exits nonzero before READY, startup self-test at the real shape/dtype, runtime raise → 500 never graded),
per-instance isolation, unchanged quantized-cache dispatch, scope (single-query, batch, linear-attention, vision untouched), numeric
parity at up to 262K keys, fingerprint v7 (`attention_policy`, absent = `auto`, registry/worker mismatch refuses, `compare.py` refuses
across policy, one parametrised A/B tool), live gate, pilot twice.

**Qualification** (P34–P36): `auto` vs `force_fused` at step 512, shipped state (native16, MTP ON, deployed profile), k=2 order-balanced
sessions with paired seed schedules + a same-seed reload control on `auto`. Per arm-session: latency ladder 8K/64K/128K/256K (TTFT,
decode, `mx.get_peak_memory`, retrieval check, MTP counters, one cached continuation at 128K); humanevalplus/mbppplus n=100 paired
`acc_strict@81920`; AgentBench 5-item pilot (smoke); a seeded 5 + 5 long-context retrieval / chain-reasoning subset near 128K. Adopt
iff in both sessions: Q1 strict delta ≥ −5 pp and convergence no worse by > 5 pp; Q2 TTFT −15 % at 64K, −25 % at 128K, −30 % at 256K;
Q3 decode ≥ −5 %; Q4 256K completes, peak ≤ auto + 0.5 GB, retrieval 1.0, long-context subset ≤ 1 loss of 10; Q5 no raise.
`prefill_step_size: 1024` is a separate second arm against the arm-1 winner (derived pool limit 9 → 15 GB is a confound to pin).

**Risks** (P37): hash changes; raises (sinks, masks, dtype, odd lengths); prealloc slices forcing a contiguous copy; Neural Accelerator /
pool interaction and MLX-version dependence of `auto`; MTP verification; serving-path hash change; stacking a second provisional numerics
change on native16 (C81).

**Cost** (P38–P39): build 1.5–2 days CPU; qualification 12–18 box-hours (lower bound, re-sized from the seeded pilot).

**Video / HySparse2 follow-up** (P40–P44; arXiv 2609.26368, DeepSeek V4.1-Flash): trained-in architectures (few full-attention layers,
sparse layers reusing the preceding full layer's KV and top-k, prefill exiting at a mid-network handoff). P40/P44 — CPU-only pre-step:
distribution of new tokens, tool-output tokens and context size per turn in the M54/M55 transcripts, to weight the benefit. P41 —
watch-list entry for an open ~30B checkpoint of that family. P42 — MRCR-v2 / RULER-v2 / NoLiMa as a possible long-context axis (not M57).
P43 — no inference-time sparse retrofit (position re-examined in the reviews below).

## Review 2, 2026-10-04 (Claude Fable 5.1) — performance-maximizing lens <!-- allow-shorthand -->

Operator's lens: maximise the performance potential (prefill, decode, memory) without sacrificing output quality beyond a negligible
amount; implementation time is not a constraint. Evidence: MLX 0.32.2 / 0.32.3 / main dispatch source
(`mlx/backend/metal/scaled_dot_product_attention.cpp`), the fork, the checkpoint config, existing ladder rows. NO new measurements; every
number below is either cited or an estimate with its arithmetic. Written before reading the Codex review.

**Source-verified corrections to the design record**

- P45 — P27 is REFUTED. The drafter's `block_size` is 3, so verification queries are a handful of tokens. For query length ≤ 8 MLX uses
  the fused *vector* kernel whenever `query_len × gqa ≤ 32` (gqa = 24 / 4 = 6 → ≤ 5 tokens), and `auto` falls back there only for head
  dim 192. Single-token decode and MTP verification are ALREADY fused under `auto`; the flag changes only query lengths > 8.
- P46 — Blanket `force_fused` would 500 in normal traffic. Query lengths 6–8 have no fused kernel at gqa 6 (vector kernel needs
  `query_len × gqa ≤ 32`; the full kernel needs query length > 8), and `force_fused` raises when no kernel exists. The prefill loop's
  tail is `(N − 1) mod step`, snapshot-landing shrinks chunks, and short continuation turns exist — 6–8 is routine. The other raise
  conditions in 0.32.2: non-GPU stream, logsumexp (training), unsupported head dim, causal with query longer than keys. Sinks, array
  masks and boolean masks do NOT raise (P37's list was wrong). The full kernel copies inputs only when the last-dim stride ≠ 1, so
  preallocated-buffer slices are not copied (that risk is retired).
- P47 — The checkpoint is `bfloat16`; the Neural-Accelerator kernel is selected for any non-fp32 dtype. The fp16 microbench has to be
  repeated at bf16.
- P48 — Upstream's rule for head dim 256 with 8 < query length < 1024 is literally "unfused path is faster", unchanged in v0.32.3
  (2026-09-29) and on main. Our 512 × 131072 microbench says the opposite, so the heuristic is blind to KEY length. Upstream is reworking
  these kernels (0.32.3: head-dim 512 and head-dim padding paths; main: blocked kernels).

**New finding from existing rows — the 256K peak is unfused score scratch**

- P49 — Native16 ladder peaks 42.52 / 44.84 / 47.14 GB at 130783 / 196115 / 261449 prompt tokens: slope 35.3–35.4 KB per token,
  intercept 37.90 GB (independently measured short-prompt peaks: 37.70–37.85 GB). KV is preallocated at the cap, so it contributes no
  slope. One 512-row score tensor (24 heads × 512 × 2 B = 24.6 KB/token) plus the whole-prompt input embeddings (5120 × 2 B =
  10.2 KB/token) = 34.8 KB/token — 98.5 % of the observed slope. At 261449 tokens that is 6.43 GB of score scratch + 2.68 GB of
  embeddings. PREDICTION: fused attention removes the 6.4 GB (peak 47.1 → ≈ 40.7 GB); embedding per chunk instead of up front removes
  up to 2.7 GB more, bit-identically. This contradicts the microbench annotation ("no memory benefit"): that instrument never showed the
  known positive (a 3.2 GB score tensor on the default path at 131072 keys), so its zero is void. Inference from three rows — to be
  confirmed on the serving path. Consequences: (a) the pool-limit derivation (`_derive_cache_limit_gb`: heads × step × cap × 2 B +
  2 GB = 9 GB) must become policy-aware, or a 2048 step derives 28 GB; (b) chunk size stops being memory-bound; (c) 6–9 GB of headroom
  at 256K is a capacity result in its own right (C108 memory-pressure 500s; room for a higher-precision weight quant — a quality lever
  outside this track).

**Is `auto | force_fused` the maximal design? No.** Ranked by expected gain × confidence:

- P50 — DO; replaces the flag. **Shape-aware policy in the fork**: force fused iff query length > 8 AND the key length is past a
  measured crossover for that query length; otherwise MLX `auto`. Upstream claims unfused wins at these shapes, most turns live at short
  keys, and a blanket force could slow them. The crossover comes from a bf16 no-model microbench (query length 9 … 4096 × key length
  512 … 262144; raises, ms, max-abs-diff, peak with a validated instrument). Expected: TTFT ≈ 2.1× at 256K, 1.75× at 128K, 1.45× at
  64K (P26) and peak −6.4 GB at 256K (P49). Confidence: high (time), medium-high (memory).
- P51 — DO, same campaign. **Chunk size as a joint sweep under the fused policy** {512, 1024, 2048, 4096}. After fusion the
  non-attention work is ≈ 47 % of a 256K prefill and > 85 % below 32K, i.e. it is what most turns pay. Larger chunks fill the
  accelerator kernel (84 ms per 1024 vs 46 ms per 512 in the microbench), give larger weight GEMMs and 2–8× fewer chunk round-trips
  (each ends in `mx.eval` + `mx.clear_cache()`). Estimate +5–20 % at every context size, weak confidence, ~1 box-hour latency-only
  screen. Qualify quality ONCE on the winning (policy, step) pair against the `auto`@512 baseline, keeping fused@512 as a latency-only
  attribution arm; fall back to OFAT only if quality fails. Supersedes P36's sequential second arm.
- P52 — DO, small. Lazy per-chunk embedding (−2.7 GB at 256K, exact); care needed for prompts with merged image features.
- P53 — PROBE, then build if it holds: **long-context decode kernel.** Decode drops 44 → 20 → 16 → 13 tok/s from short context to
  131K / 196K / 261K, so ≈ 55 of 77 ms per token at 261K is context-proportional. Per verification round that is ≈ 8 ms per
  full-attention layer to read ≈ 1.07 GB of keys + values, ≈ 130 GB/s effective (estimate; assumes ≈ 2.4 tokens per round) — well under
  what unified memory should deliver (not measured). The path is MLX's generic two-pass vector kernel: its specialised GQA variant
  exists only for gqa 8 with head dim 64/128, and its block count tops out at 1024 with an env override (`MLX_SDPA_BLOCKS`).
  (i) No-model microbench at query length 1/3/4/5, 131K/262K keys, bf16, sweeping `MLX_SDPA_BLOCKS`, against a pure-read floor
  (`mx.sum` over the same arrays) — minutes. (ii) If ≥ 1.5× headroom remains, a GQA-6 / head-dim-256 few-query kernel in the fork
  (precedent: `_qwen3_5_ragged_sdpa_*` and the gated-delta kernels already use `mx.fast.metal_kernel`). Potential 13 → ≈ 25–30 tok/s at
  256K and 20 → ≈ 30 at 128K — speculative until (i). Exact up to summation order. This is where a new kernel is most likely to pay.
- P54 — DON'T (unless P50's microbench contradicts): custom exact PREFILL kernel. The fused kernel does ≈ 1.65e12 FLOP per layer-chunk
  in 46 ms ≈ 36 TFLOP/s; the weight GEMMs imply the GPU sustains ≳ 59 TFLOP/s (1100 tok/s × 54 GFLOP/token, rough). Headroom ≲ 1.6× on
  what will be about half of prefill → ≲ 20 % TTFT, against a vendor kernel upstream is still tuning.
- P55 — PROBE ONLY; I expect it to fail. Sparse / approximate retrofit. Prefill: after P50/P51 the quadratic term is ≈ 265 s of ≈ 500 s
  at 256K, so even a perfect scheme caps at another ≈ 2×. Training-free selection needs scores cheaper than QKᵀ; safe bound-based block
  pruning prunes little; the only candidate with a mechanism is the HySparse shortcut (alternate full layers attend to the previous
  full layer's top-k ∪ a recent window), which upstream TRAINED in. Errors land in the cache, compound over 16 layers and persist for
  every later turn. Decisive experiment: an offline attention-mass recall probe on real 64K–128K prompts (share of layer j's softmax
  mass captured by layer j−1's top-k ∪ last 128, k ∈ {1024, 4096, 16384}); fund a build only at ≥ 99.9 % mass with k ≤ 4096 for ≥ 99 %
  of queries in every layer. My estimate of a retrofit passing quality with ≥ 1.5× extra speedup: 15–25 %, for weeks of work. Decode
  sparsity rides the same probe but sits behind P53's exact kernel.
- P56 — DO, cheap. Upstream: report the key-length blindness with the crossover table; read the 0.32.3 / main kernel changes before
  writing any kernel. An MLX upgrade is its own numerics-changing arm — not folded into M57.
- P57 — MEASURE, CPU-only. Avoided re-prefill: extend P40/P44 to count turns with zero cached tokens at large context (prefix drift,
  compaction, eviction). One full re-prefill at 128K costs 185–325 s, more than dozens of ordinary turns; if frequent, retention beats
  every kernel.
- P58 — LATER, gated on P53(i). Cache-precision redesign: int8 keys/values with a purpose-built fused kernel would halve decode
  bandwidth and save ≈ 8 GiB; uniform8 lost in C82 because its path is unfused, not because of its precision.

**Changes to acceptance and qualification (P59)**: the startup self-test and scope tests sweep query lengths 1–9 and odd tails; add a
criterion that the pool-limit derivation is policy-aware; parity at bf16; Q4 becomes a prediction test (256K peak ≤ auto − 5 GB, else
the P49 mechanism is wrong — investigate; report peak and pool separately); add Q6 (8K and 32K TTFT no worse than −3 %); decode is
expected UNCHANGED (its kernels are untouched), so a decode shift beyond noise is a red flag, not a bonus. The overlay-only step-1024
probe stays as the zero-build mechanism check and now also tests P49 (128K peak should fall ≈ 3.2 GB) — valid only if the prompt's
tail `(N − 1) mod 1024` is short, because an unfused tail re-creates the scratch.

**Roadmap**: (1) zero-build probes, ≈ 1 box-hour + CPU: bf16 crossover/raise/parity matrix, vector-kernel decode microbench with the
read floor, step-1024 overlay probe with peak, transcript analysis (P40/P44/P57). (2) Build M57 as shape-aware policy + policy-aware
pool limit + lazy embeddings + provenance, 2–3 days. (3) Latency/peak screen of policy × step, 1–2 box-hours. (4) Qualify the winner,
12–18 box-hours. (5) Decode kernel as a separate milestone if (1) shows ≥ 1.5× headroom. (6) Sparse probe and int8 cache only behind
their gates.

## Review 3, 2026-10-04 (Codex CLI, model `gpt-6-astra`, cold, read-only) — condensed <!-- allow-shorthand -->

Brief: the design record above plus the operator's performance-maximizing lens; no conclusions from review 2 were given to it. Raw text:
`$STACK_WORKDIR/m57/codex_review_1.md` (not committed — it carries absolute paths). Verdict: **revise M57 before implementation;
`auto | force_fused` is a useful experimental control, not a performance-maximal design.** It fetched the MLX 0.32.2 and main sources.

- X2 — Ordinary prefill path confirmed (P25). MTP verification does NOT go through `Qwen3_5Attention.__call__`: a separate verifier
  (`mlx_vlm/models/qwen3_5/speculative_verifier.py`) attends a length-2 block jointly with an array mask and longer unpadded blocks as
  individual single-query calls. An attribute threaded only through the ordinary call misses these sites.
- X3 — Dispatch table for head dim 256, GQA 6 (source prediction): 512-token chunk and 9–511 tails fall back under `auto`, fused when
  forced; 6–8 fall back under `auto` and RAISE when forced; 1–5 and single-token decode are already the fused vector family; ≥ 1024
  with a causal string is fused under `auto`, with an array mask it falls back. An unrestricted multi-query policy can pass the
  headline benchmark and fail legitimate continuations. Preallocation does not force a contiguous copy.
- X4 — bf16 is the expectation, still needing live observation. The fallback explicitly builds QKᵀ, masks, softmaxes and multiplies V;
  the recorded ≤ 0.07 GiB transient does not establish absence of score materialisation (one logical score tensor is 3 GiB at 131072
  keys) — the instrument needs validating.
- X5 — P26 arithmetic approximately confirmed (fit `T(N) ≈ 0.0008986 N + 1.21209e-8 N²` s; 64K 111 → 76 s, 128K 325 → 184 s,
  256K 1063 → 502 s); the fit is not a component profile, and the 12–18 box-hour figure is not supportable before a pilot.
- X6 — P29 confirmed; a random-tensor matrix cannot establish served dtype or layout; the pool limit is applied in GiB; P40/P44
  should count actually reprocessed tokens, cache misses and retirement work; P43's blanket exclusion of sparse retrofits is rejected.
- Ranked options: X7 versioned shape/dtype/mask dispatch policy + chunk-size co-design (512/1024/2048, boundary-aware; ≈ 9 % further
  attention time at 1024). X8 eliminate remaining avoidable re-prefill (M48 already took 64K continuation 130 → 1.2 s; do not count it
  twice; decide by transcript/cache-event accounting). X9 exact long-context decode / verification kernels — the verifier's per-query
  decomposition means up to 3× more logical KV scans than a joint pass. X10 exact prefill kernels / upstream (another 2× on attention
  would be ≈ 1.36× beyond the forced result; main keeps the 512-query fallback heuristic; pin a commit). X11 GatedDeltaNet and MLP share:
  the Metal recurrent kernel loops through time while a chunk-parallel formulation exists only on the non-Metal route; profile first.
  X12 fused low-precision cache (8 GiB at 8 bits; uniform8 lost on its unfused path; the TurboQuant fused MSE prefill kernel is a
  `NotImplementedError` stub). X13 sparse / approximate attention: decode first, prefill behind a stronger gate, both behind a replay of
  captured queries measuring missed attention mass.
- X14 — AC1–AC10 are not executable yet: add an eligibility table (tails, both verifier branches, snapshot cuts, cache
  retirement/refloor, near-cap appends); independent numerical references with relative/RMS error, NaN and causal-leakage checks;
  actual kernel evidence (a forced-call counter only proves an argument was passed); worker readback of the resolved policy; historical
  absence must not be recorded as observed `auto`; a narrowly scoped A/B exception; a startup self-test bounded under the 300 s
  readiness timeout.
- X15 — Q1/Q4 can accept material damage (one loss in 5 + 5 is 10–20 pp) and reject a harmless stochastic miss (retrieval 1.0);
  n=100 is not automatically powered for ±5 pp; stratify retrieval / reasoning / agentic code with distractors and sustained
  continuations.
- X16 — Q2/Q3/Q5 can reject good designs: mandatory wins at every cold rung exclude memory or decode gains; one cached continuation is
  not the workload; use pre-registered workload weights, repeated timing blocks and tail latency. The 261449-token rung leaves 695
  tokens (≤ 556 thinking tokens), so capacity completion is not reasoning qualification.
- X17 — Roadmap: correct the record → validate instruments and capture component costs → qualify dispatch × chunking → fund exact
  prefill / decode / recurrent work from measured bottlenecks → fused cache precision and sparse decode → pinned recipe after
  multi-turn quality and full-context stability.

## Reconciliation, 2026-10-04 (Claude Fable 5.1) — where the two reviews stand <!-- allow-shorthand -->

Codex's code claims were re-checked against the fork before recording (verifier branches, GatedDeltaNet routes, TurboQuant stub, GiB
units: all confirmed).

**Both reviews, independently**: no blanket `force_fused` (query lengths 6–8 raise); the policy must be shape-aware and versioned;
chunk size is co-designed with the policy, not a later arm; bf16; the microbench's memory zero is void; measure avoidable re-prefill
before funding kernels; sparse retrofits are probe-gated with decode ahead of prefill; upstream main keeps the 512-query heuristic.

**Codex found, review 2 missed**

- P60 — The verifier is a second attention site (X2). The policy has to cover or explicitly exclude it, and it REVISES P53: with block
  3 a verification round makes up to three full scans of each layer's keys and values, so review 2's "≈ 130 GB/s effective" is ≈ 390
  GB/s per scan — the vector kernel is probably already near the memory-bandwidth limit. The decode lever is therefore a JOINT
  verification scan (the existing fused vector kernel accepts up to 5 queries at GQA 6), not a faster single-query kernel. Estimate if
  the context-proportional decode term is all attention and scans drop 3 → 1: 77 → ≈ 40 ms per token at 261K (13 → ≈ 25 tok/s),
  50 → ≈ 31 ms at 131K (20 → ≈ 32 tok/s). Cost: the per-query decomposition is deliberate (the fork's "exact" verifier keeps
  verification numerics identical to plain decode); a joint scan gives that up and requalifies MTP-ON. After that, bandwidth is the
  wall and only a narrower cache (P58 / X12) moves it.
- P61 — GatedDeltaNet on Metal is a per-token kernel while a chunk-parallel form exists in the same file (X11). Review 2 assumed the
  non-attention share was weight-GEMM-bound; a component profile has to settle it before any chunk-size conclusion.
- P62 — Qualification defects accepted (X14–X16): replace "≤ 1 loss of 10" with stratified, discordance-sized long-context sets; the
  256K rung is a capacity/retrieval rung only (≤ 556 thinking tokens of headroom); adoption by pre-registered workload weights rather
  than a win at every cold rung; kernel evidence beyond a call counter; pre-v7 manifests record `auto` with source `default`, never
  `observed`; self-test bounded under the readiness timeout.

**Review 2 found, Codex did not have**: P49 (ladder-slope evidence that ≈ 6.4 GB of the 256K peak is score scratch and ≈ 2.7 GB is
whole-prompt embeddings), P52 (lazy embeddings), the `MLX_SDPA_BLOCKS` override, and the bound on a custom prefill kernel (P54).

**Remaining disagreement**: none on direction. On the custom exact prefill kernel, Codex ranks it fourth with ≈ 1.36× if attention
doubles again; review 2 bounds it at ≲ 20 %. The same captured-tensor benchmark decides it.

**P63 — Consolidated recommendation** (supersedes the roadmap in review 2):

1. Evidence before any build. CPU: transcript and cache-event accounting (new / tool-output / reprocessed tokens, context size, cold
   replays). GPU, no model, ≈ 1 box-hour: bf16 matrix (crossover by query × key length, raises, parity against an independent fp32
   reference, a memory instrument validated on the known positive), vector-kernel scan time against a read floor with
   `MLX_SDPA_BLOCKS`. One overlay probe at 128K with `prefill_step_size: 1024` under `auto` (TTFT and peak).
2. A component profiler in the fork (env-gated, off by default): attention / GatedDeltaNet / MLP / verifier time per chunk and per
   round on the served path. This is the instrument every later funding decision needs.
3. M57 = versioned shape-aware dispatch policy over ALL native call sites (attention module, verifier, tails, snapshot cuts) + chunk
   size chosen jointly + policy-aware pool limit + lazy embeddings + provenance; qualified once on the winning recipe with the
   corrected, stratified quality design.
4. Next milestone candidate: long-context decode — joint verification scan, MTP-ON requalified.
5. Then, each behind its measurement: GatedDeltaNet / MLP prefill work, upstream report and pinned-commit kernel comparison, fused
   low-precision cache, sparse decode, sparse prefill last.

## Step-1 evidence, 2026-10-04 (C111 approved; M5 Max, MLX 0.32.2, stack down, 140 W, battery 96–97 %, no swap)

No model loaded for E1–E8: synthetic bf16 arrays at the first pick's attention shape (24 query / 4 KV heads, head dim 256), keys sliced
from a 262144-token buffer as the preallocated cache does. Scripts and raw JSON: `$STACK_WORKDIR/m57/` (`sdpa_microbench.py`,
`sdpa_serving_like.py`, `transcript_accounting.py`). Times are the minimum of 3–5 warm repetitions. PROBES, not gradable results.

- **E1 — Raise boundary (runtime-confirmed).** `force_fused=True` raises `ValueError` at query lengths 6, 7 and 8; 1–5 and ≥ 9 run.
- **E2 — Crossover, isolated warm kernel, ms per layer (`auto` / forced).**

  | query length | 16384 keys | 131072 keys | 262144 keys | forced vs `auto` |
  |---:|---:|---:|---:|---|
  | 16 | 0.77 / 1.88 | 5.39 / 14.0 | 10.9 / 27.9 | forced 2.4–2.6× SLOWER |
  | 64 | 1.22 / 1.89 | 11.9 / 14.0 | 24.0 / 28.0 | forced 1.2–1.5× slower |
  | 128 | 2.05 / 1.95 | 17.5 / 14.7 | 37.4 / 30.6 | forced 1.05–1.22× faster |
  | 256 | 3.72 / 3.74 | 30.4 / 28.9 | 65.5 / 58.4 | forced 1.00–1.12× faster |
  | 512 | 6.94 / 5.70 | 61.8 / 45.3 | 245 / 91.7 | forced 1.22× / 1.36× / 2.67× faster (the last includes pool misses) |
  | 1024 | 9.57 / 9.55 | 80.4 / 79.6 | 165 / 167 | identical — `auto` is already fused |
  | 2048 | 18.5 / 18.6 | 172 / 169 | 375 / 356 | identical |
  | 4096 | 33.7 / 33.4 | 334 / 346 | 712 / 726 | identical |

  The forced kernel has a floor of ≈ 14 ms at 131072 keys for any query length ≤ 128. Per 512-query equivalent at 131072 keys:
  forced-512 45.3 ms, 1024 → 40.2, 2048 → 43.1, 4096 → 41.8.
- **E3 — fp16 tie-back.** 512 × 131072: `auto` 62.8 ms, forced 46.8 ms. The first review's 144 ms default is not reproduced warm — it
  was a cold-buffer measurement. The "3.1×" was never a kernel ratio.
- **E4 — Serving-like chunk** (pool cleared, 16 dependent layers in one eval, pool limit 9 GiB), ms per layer `auto` / forced:
  65536 keys 33.0 / 22.3 (1.48×); 131072 keys 68.0 / 45.1 (1.51×); 262144 keys 150 / 93.1 (1.61×). 1024-query chunks under `auto`:
  92.3 ms at 131072 keys (46.2 per 512-equivalent — no gain over forced-512 in this setting). Transient peak: `auto` 6.6 / 9.9 /
  19.8 GB (about three score-sized buffers); forced 0.15 GB; 1024-query `auto` 0.30 GB.
- **E5 — Memory instrument.** Run 1 read 0.0 GB for a known 3.22 GB tensor (the base still counted the previous, not-yet-released
  buffer); the serving-like script reads it correctly (3.221 GB). The first review's "no memory benefit" was this artifact. The
  unfused path DOES materialise score-sized buffers; the fused path does not (P49's mechanism holds at kernel level).
- **E6 — Masks.** None / causal string / boolean array / additive array all run forced at 512 queries (48.5 / 47.0 / 54.3 / 52.1 ms
  at 131072 keys).
- **E7 — Accuracy against an independent fp32 CPU reference (relative RMS error).** Unfused bf16: 0.0044 with flat logits, 0.023 with
  peaky logits (max abs 0.096). Fused: 0.0017 in both. Decode's vector kernel: 0.0018–0.0024. The fused path is 2.6–14× CLOSER to
  exact arithmetic than what is served today, and brings prefill to the accuracy decode already has.
- **E8 — Vector kernel (decode / verification), ms per layer at 65536 / 131072 / 262144 keys.** 1 query: 0.71 / 1.25 / 2.36 (≈ 455 GB/s
  over keys + values — at memory bandwidth, no single-scan headroom). 3 queries jointly: 1.34 / 2.44 / 4.75. 3 separate single-query
  calls (the verifier's pattern): 1.79 / 3.45 / 6.58. Joint and per-query outputs are BIT-IDENTICAL (max abs 0.0, at 3 and 5
  queries). `MLX_SDPA_BLOCKS`: the default is already optimal (256 is 1.3–1.7× slower, 2048 equal, 8192 slower).
- **E9 — Workload accounting (CPU).** opencode M55 (60 surviving transcripts, 561 turns; per-turn cache counts read from the
  transcripts): context p50 14.0K, max 27.8K; prefilled tokens per turn p50 543, p90 8647; 47.6 % of turns prefill 9–511 tokens,
  19.1 % 512–1023, 33.3 % ≥ 1024; no turn prefills 1–8; turn 1 (≈ 8650 tokens, always cold) is 49 % of all prefilled tokens; one cold
  replay in 561 turns. AgentBench OS M54 (426 sessions, 1423 turns): context max 3.8K; cached-token counts not recorded (prefill
  estimated from prompt deltas). Worker log 2026-09-21…29 (656 requests, daily driver and probes mixed): prompt p50 589, p90 32K, max
  79K; 71 % of prefilled tokens at 16–64K context, 5 % above 64K, none above 128K. **Neither benchmark harness ever reaches the
  long-key regime; the M57 time benefit lands on long daily-driver sessions and on capacity, not on the current agentic axes.**

**What the evidence changes**

- P65 — The kernel-level time gain of fused over unfused at 512-query chunks is ≈ 1.5–1.6× in serving-like conditions, not 3.1×.
  The ladder fit puts the in-situ unfused quadratic cost at ≈ 102 ms per layer-chunk at 131072 keys; the serving-like microbench
  explains 68 ms of it. About a third of the quadratic cost is NOT the attention kernel and is not yet attributed (the component
  profiler's job). Revised TTFT predictions if only the kernel changes: 64K 111 → 82–99 s, 128K 325 → 209–278 s, 256K 1063 →
  600–873 s (P26's 76 / 185 / 500 s are withdrawn).
- P66 — Memory is confirmed at kernel level and becomes the lead benefit: GBs of score scratch per chunk under `auto`, ≈ 0.15 GB fused.
- P67 — Accuracy is a benefit, not a risk (E7).
- P68 — The dispatch policy needs a QUERY-length threshold, not a key-length crossover: fused wins from ≈ 128 queries up at every key
  length, loses below it (floor ≈ 14 ms at 131072 keys), and is identical to `auto` from 1024. Short tails cost little in absolute
  terms either way (≤ 17 ms per layer at 262144 keys) but an unfused 100-query tail still materialises GBs at long context, so the
  threshold is a memory/time trade to set in the spec.
- P69 — Decode (revises P60): a single scan is already at memory bandwidth; a joint verification scan is bit-identical to the
  per-query pattern and saves 28 % of verification attention (≈ 29 ms of a ≈ 221 ms round at 261K → ≈ +15 % tok/s, estimate), not the
  ≈ 2× claimed in P60. A single-pass kernel that reads keys and values once for all queries would save about twice that. About 58 ms
  per round of context-proportional decode time is not attention scans and is unattributed.

**E10 — Served-path overlay probe at 128K (one session per arm, fresh lean router, shipped state, same 130783-token prompt;
rows `capacity_ladder.m57probe-step{512,1024}-20261004`).** Worker command lines recorded; `APC_ENABLED` absent;
`MLX_VLM_CACHE_SESSION_MAX=1`; pool limit pinned at 9 GiB in the 1024 arm.

| arm | prefill s | MLX peak GB | decode tok/s | retrieval | MTP acceptance |
|---|---:|---:|---:|---:|---:|
| step 512, `auto` (127 unfused chunks of 512 + tail) | 308.5 | 42.52 | 21.6 | 1.0 | 0.806 |
| step 1024, `auto` (127 FUSED chunks + a 734-token UNFUSED tail) | 269.0 | 44.23 | 21.2 | 1.0 | 0.800 |

- Time: −12.8 % TTFT at 128K with fused chunks — at the pessimistic end of P65's range. The fused kernel removes about a fifth of the
  quadratic term; extrapolated ≈ −9 % at 64K and ≈ −16 % at 256K (estimate). Fused attention ALONE is a modest time win.
- Memory: the peak ROSE 1.71 GB, as the scratch mechanism predicts when the largest unfused chunk grows from 512 to 734 queries:
  (734 − 512) × 24 heads × 130783 keys × 2 B = 1.39 GB per score tensor, × 1.23 = 1.71 GB. So the served peak tracks ≈ 1.23 score
  tensors of the LARGEST UNFUSED chunk — the mechanism is confirmed on the serving path, and a policy that also fuses tails should
  take ≈ 3.9 GB off the 128K peak and ≈ 7.9 GB off the 256K peak (prediction). `prefill_step_size: 1024` under `auto` WITHOUT a tail
  policy is a memory regression at any prompt whose tail exceeds 512 tokens.
- One session per arm: a probe, not a result (no interval; the two arms ran back to back).

**E11 — MTP round profile at 128K (existing `MLX_VLM_MTP_PROFILE=1`, same prompt, one session; profiled rows kept in the workdir
only).** 79 rounds, 131.5 ms per round, 2.61 tokens emitted per round: verify 120.0 ms (91 %), draft 3.4, walk 3.8, accept 3.6,
rollback 0.7. Decode at long context IS the target verification forward. E8 puts its key/value scans at 16 × 3.45 = 55 ms in the
verifier's per-query pattern; a joint scan would be 39 ms (−16 ms, ≈ +14 % tok/s at 128K), a single-pass kernel ≈ 20 ms (−35 ms,
≈ +36 %). Estimates from kernel timings, not measured on the served path.
