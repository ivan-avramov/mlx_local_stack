---
license: apache-2.0
base_model: unsloth/Qwen3.8-27B  # allow-shorthand
library_name: mlx
tags:
- mlx
- unsloth
- qwen3_5
pipeline_tag: image-text-to-text
---
# Qwen3.8-27B-mlx-uniform-4bit

Model-card update:2026-09-14.

## Status

Second operator-approved choice for agentic coding and research/design assistance (B2/C2), at temperature 0.6, medium reasoning effort and native MTP ON. The current runtime retains TurboQuant 4 KV. The M40 MBPPPlus predictor comparison remains INCONCLUSIVE; deployment approval does not erase that limit.

## Conversion and attribution

MLX uniform affine 4-bit/group 64 conversion of [unsloth/Qwen3.8-27B](https://huggingface.co/unsloth/Qwen3.8-27B). Historical packaging records describe 27B parameters, 498 four-bit modules and 15.13 GB weights. The 2026-08-23 restoration added 333 BF16 vision tensors. A historical tensor comparison with [mlx-community/Qwen3.8-27B-4bit](https://huggingface.co/mlx-community/Qwen3.8-27B-4bit) found 2179/2180 tensors identical, with the vision patch projection differing. That comparison identifies those historical revisions, not arbitrary future revisions of either repository.

Packed low-bit tensor counts can understate true parameter counts in hub badges. Weight-file sizes, effective bits/weight and total MLX runtime peak are different measurements.

### Earlier predictor certification, 2026-08-30 (M6d)

At xhigh reasoning effort/TQ4,164 paired HumanEvalPlus tasks: ordinary 94.5% both states, delta 0 pp[−3,+3]; strict 93.9% ON versus 92.7% OFF. Mean acceptance 0.674 and paired mean decode 1.60×. The later medium-speed screen was an instrument check; it is now followed by the separate M40 medium-quality evidence below, rather than an enduring “not measured” claim.

### M40 predictor-ON certification, 2026-09-13 — historical TQ4 configuration

These ON/OFF comparisons used the same deployed tune, matched seeds, cap 262144 and resolved thinking budget 81920. Both predictor states remain recorded; new optimization work runs in the shipped ON state. This supersedes earlier blanket statements that every benchmark always runs predictor-OFF.

| Axis and sample size | OFF | ON | Paired interpretation |
|---|---:|---:|---|
|Math500,100|99%|99%|0 pp[0,0]; zero observed discordance|
|HumanEvalPlus, 100|93%|94%|+1 pp[0,+3]|
|MBPPPlus, 100|83%|82%|−1 pp[−6,+3], INCONCLUSIVE; ON-only 2/OFF-only 3|
|Research prose, 40 pairs|—|—|OFF preference 0.56[0.45,0.68], Holm p=.28; underpowered|
|128K chain-4,3 draws|3/3|3/3|No budget hits|
|20-photo vision gate|19/20|19/20|Same missed photo detail|

Operator-approved state is MTP ON. Per-axis limits remain: a zero-discordance empirical interval is not proof of universal equivalence; n 100 nominal MDE is 12.5 pp and n 40 is 20 pp. Vision and depth drivers verified the worker flag but did not expose per-request draft counters. Those small gates do not certify arbitrary images, OCR, complex diagrams, or full-context reasoning. The photo gate uses description followed by a ground-truth-caption self-check; it is a lenient capability screen, not a ranked vision benchmark.
C74 explicitly preserves the MBPPPlus INCONCLUSIVE label; pooled coding diagnostics do not replace it.

### C84 actual-runtime regression screen, 2026-09-14

M5 Max 64 GB, MLX/Metal 0.32.2. BEFORE was the initially merged runtime `e3bffd9a`/`f8f1df4`. AFTER combines later upstream changes, cache lifetime/logical-trim/eager-retirement repairs, and the per-model retirement option; retirement is enabled only for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. This is not an isolated retirement/kernel effect or the original pre-merge/upstream comparison.

Five frozen seeded tasks per axis, 20 requests in each state for this model. All 20 pairs have identical visible answers, reasoning and completion-token counts; all 40 responses converge. Ordinary accuracy equals strict accuracy. No exclusive solves or new nonconvergence were observed.

| Axis | AFTER score | Task-time AFTER/BEFORE[95% interval] | Mean per-request decode ratio[95% interval] |
|---|---:|---:|---:|
|math500|5/5|1.008[1.002,1.016]|0.995[0.987,1.004]|
|humanevalplus|5/5|1.006[0.995,1.012]|1.002[0.993,1.016]|
|mbppplus|5/5|1.001[0.982,1.012]|1.003[0.994,1.020]|
|cjudge|5 reviewed ties|1.000[0.990,1.008]|1.002[0.992,1.014]|

Intervals use 10000 paired two-stage task-bootstrap resamples, seed 84; they are nominal exploratory intervals, not multiplicity-adjusted or repeated-session uncertainty. Five items per axis have nominal MDE 56 pp; empirical quality intervals[0,0] with zero discordance do not establish±5 pp equivalence. The prose review was nonblinded, one reviewer, and found shared factual/methodological weaknesses; matching answers are not proof of correctness. This bounded screen does not rerank models or replace broad native16 depth/vision certification.

Final runtime smoke covers arithmetic, Python, JSON, native tool continuation and one fixed image, five cases/six requests. It passed for both current picks. Only `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` received the additional fresh tool-pair and three-turn prefix-reuse checks.

Total short-task time 821.4→822.9 s; per-axis changes are below 1%, not a claim of zero speed cost. An earlier integrated-runtime TQ4 capacity ladder on 2026-09-13 measured 37.7970 GB peak, 1598.33 s prefill and 6.15tok/s decode at 261449 prompt tokens (MTP ON, source`c5a6f97b`). That closes the historical capacity gap but is not a fresh final-C84 full-context comparison.

## MTP companion

Use [caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter](https://huggingface.co/caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter), captured revision `6262b9a3baed755085010776d9321218fbc3cc9d`, with `draft_kind: mtp`. The predictor has separate artifact provenance; it is not inferred from a target’s MTP tags.

## Recommended current setting

Save this as `models.yaml` in an environment with the compatible fork revisions described below. The IDs name the target and, where configured, its exact companion; weight quantization and attention-KV precision are separate settings.

```yaml
manager_port: 8000
mlx_port: 8091
startup_timeout_seconds: 300
models:
- name: Qwen3.8-27B-mlx-uniform-4bit
  type: vision
  hf_path: caslca/Qwen3.8-27B-mlx-uniform-4bit
  max_kv_cache_size: 262144
  kv_prealloc_tokens: 262144
  kv_quant_scheme: turboquant
  kv_bits: 4
  quantized_kv_start: 0
  prefill_step_size: 512
  draft_kind: mtp
  draft_model: caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter
  generation_defaults:
    temperature: 0.6
    top_p: 0.95
    top_k: 20
    min_p: 0.0
    presence_penalty: 0.0
    max_tokens: 102400
    thinking_budget: 81920
    enable_thinking: true
    reasoning_effort: medium
  on_demand: true
```

Start from the compatible installed fork environment without additional worker overrides. This command clears cache/predictor environment overrides, disables APC and selects two retained sessions with one resident model:

```sh
env -u APC_ENABLED -u KV_BITS -u KV_QUANT_SCHEME -u KV_GROUP_SIZE \
  -u KV_KEY_BITS -u KV_VALUE_BITS -u KV_KEY_SCHEME -u KV_VALUE_SCHEME \
  -u QUANTIZED_KV_START -u MLX_VLM_SESSION_SHRINK_ON_RETIRE \
  -u MLX_VLM_DRAFT_KIND -u MLX_VLM_DRAFT_MODEL -u MLX_VLM_DRAFT_BLOCK_SIZE \
  MLX_VLM_CACHE_SESSION_MAX=2 MLX_SERVE_CONFIG=models.yaml mlx-serve start
```

The model loads on demand. An OpenAI-compatible client sends requests to `http://localhost:8000/v1` with model ID `Qwen3.8-27B-mlx-uniform-4bit`. Omitted sampling fields inherit `generation_defaults`; thinking is enabled. The output cap is 102400 and thinking budget 81920. Near the context limit the server resolves a smaller budget from remaining space; a configured 262144 cap does not imply 262144 input tokens plus another 102400 output tokens.

The full active KV floor equals the context cap; keep prefill 512. `kv_bits: 0` means unquantized native16 attention KV, not unquantized model weights or a newly measured IEEE-FP16 dtype. TurboQuant is inactive when bits are 0 even if its scheme name remains configured. Idle retirement is explicitly true only on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; omitted `cache_session_shrink` preserves the worker default OFF only when `MLX_VLM_SESSION_SHRINK_ON_RETIRE` is absent, as in the command above. Suffix decoding stays OFF. These structural settings target the 64 GB evaluation machine, not arbitrary hardware.

## Runtime and evidence scope

The final C84 environment uses [MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`](https://github.com/ivan-avramov/mlx-vlm/commit/522671c4bebc5ff492d465a1d0e6a14251f18260), [MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`](https://github.com/ivan-avramov/mlx-serve/commit/b632280709f771972bffbaf3231e996e8a89f4e8), and MLX/Metal 0.32.2. Those fork commits are published. Live validation of this exact final bundle covers the two current picks only; other cards retain historical model evidence and source-level compatible configuration, not a newly run model smoke. Older experiments used their recorded earlier runtime and cache mode.

Dates, original source revisions, per-axis observations and evidence-file hashes are recorded in [the accompanying evaluation evidence](evaluation/M44-evidence-2026-09-14.json) alongside this card. The tables here are self-contained: they do not rely on unpublished stack commits or links to future GitHub `main` content. Speculative decoding can change BF16 outputs; favorable task-specific intervals do not imply byte-lossless inference. Historical and current measurements are not pooled across cache modes, predictor states, budgets, corpora or runtimes.

## Artifact integrity audit, 2026-09-14

All 13 audited model and support files match the corresponding local artifact by full-byte cryptographic hashing, including weights and applicable configuration/tokenizer/vision files. README, license and repository-attribute files are tracked separately from inference artifacts. This publication changes the card and its dated evidence only; model artifacts remain unchanged. [Per-file hashes, audited revision and scope](evaluation/M44-evidence-2026-09-14.json).
