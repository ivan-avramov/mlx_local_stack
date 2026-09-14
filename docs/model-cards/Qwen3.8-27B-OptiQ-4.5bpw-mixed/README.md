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
# Qwen3.8-27B-OptiQ-4.5bpw-mixed

Model-card update:2026-09-14.

## Status

Historical published candidate, not a current B/C pick. Its recorded recipe and tests are retained below; it has not received the current two-pick C84 runtime screen or a new predictor certification.

## Conversion and attribution

MLX OptiQ KL-sensitivity 4/8-bit conversion of [unsloth/Qwen3.8-27B](https://huggingface.co/unsloth/Qwen3.8-27B), with the vision tower retained. Historical serving metadata reports 27B VLM parameters, 4.98 effective bits/weight, 18.44 GB weights and 152 eight-bit/346 four-bit quantized modules. The 4.5bpw repository name is not the measured effective precision. The intermediate conversion print 5.485bpw/17.6 GB belongs to a different packaging stage and must not replace the final manifest accounting.

Packed low-bit tensor counts can understate true parameter counts in hub badges. Weight-file sizes, effective bits/weight and total MLX runtime peak are different measurements.

### Historical results and limits

The 2026-08-17/19 predictor-OFF t0.6 code screen recorded HumanEvalPlus 42/48 graded, 42/50 strict and MBPPPlus 40/50. Two HumanEvalPlus timeouts came before the repaired C28 transport/orphan-cascade handling; these are historical, compromised shallow-screen data, not evidence of precision preventing runaways. No post-fix shallow re-run of this exact recipe is claimed.

M25,2026-08-29, opencode 22-item sets at t0.6/template xhigh, predictor OFF:18/22 Python and 16/22 Go; comparison against `Qwen3.8-27B-mlx-uniform-4bit` at20/22 and16/22 was a historical WASH, not promotion.

The old capacity ladder recorded 33.72 GB MLX peak, 1977 s prefill and 10.53tok/s decode at nominal 256K, retrieval co-score 1.0. It used an old runtime/predictor-OFF protocol and historical 46 GB flag. Rough 48 GB is now guidance, not a strict rejection cutoff; old capacity/speed must not describe today's two-pick runtime. No general causal claim that architecture alone determines decode speed is retained.

T0.6 and omitted reasoning_effort retain the historical template default (xhigh in those runs); no medium-effort or MTP certification exists for this recipe. The bundled original MTP file is inert under normal target loading; do not enable it by copying a sibling's recommendation. Vision tower presence is recorded, without a new quality gate.

## Predictor

Predictor OFF: no external MTP recommendation is configured or certified for this exact recipe. A bundled head or MTP tag alone is not evidence to enable speculation.

## Recorded historical-candidate configuration, not a new recommendation

Save this as `models.yaml` in an environment with the compatible fork revisions described below. The IDs name the target and, where configured, its exact companion; weight quantization and attention-KV precision are separate settings.

```yaml
manager_port: 8000
mlx_port: 8091
startup_timeout_seconds: 300
models:
- name: Qwen3.8-27B-OptiQ-4.5bpw-mixed
  type: vision
  hf_path: caslca/Qwen3.8-27B-OptiQ-4.5bpw-mixed
  max_kv_cache_size: 262144
  kv_prealloc_tokens: 262144
  kv_quant_scheme: turboquant
  kv_bits: 4
  quantized_kv_start: 0
  prefill_step_size: 512
  generation_defaults:
    temperature: 0.6
    top_p: 0.95
    top_k: 20
    min_p: 0.0
    presence_penalty: 0.0
    max_tokens: 102400
    thinking_budget: 81920
    enable_thinking: true
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

The model loads on demand. An OpenAI-compatible client sends requests to `http://localhost:8000/v1` with model ID `Qwen3.8-27B-OptiQ-4.5bpw-mixed`. Omitted sampling fields inherit `generation_defaults`; thinking is enabled. The output cap is 102400 and thinking budget 81920. Near the context limit the server resolves a smaller budget from remaining space; a configured 262144 cap does not imply 262144 input tokens plus another 102400 output tokens.

The full active KV floor equals the context cap; keep prefill 512. `kv_bits: 0` means unquantized native16 attention KV, not unquantized model weights or a newly measured IEEE-FP16 dtype. TurboQuant is inactive when bits are 0 even if its scheme name remains configured. Idle retirement is explicitly true only on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; omitted `cache_session_shrink` preserves the worker default OFF only when `MLX_VLM_SESSION_SHRINK_ON_RETIRE` is absent, as in the command above. Suffix decoding stays OFF. These structural settings target the 64 GB evaluation machine, not arbitrary hardware.

## Runtime and evidence scope

The final C84 environment uses [MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`](https://github.com/ivan-avramov/mlx-vlm/commit/522671c4bebc5ff492d465a1d0e6a14251f18260), [MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`](https://github.com/ivan-avramov/mlx-serve/commit/b632280709f771972bffbaf3231e996e8a89f4e8), and MLX/Metal 0.32.2. Those fork commits are published. Live validation of this exact final bundle covers the two current picks only; other cards retain historical model evidence and source-level compatible configuration, not a newly run model smoke. Older experiments used their recorded earlier runtime and cache mode.

Dates, original source revisions, per-axis observations and evidence-file hashes are recorded in [the accompanying evaluation evidence](evaluation/M44-evidence-2026-09-14.json) alongside this card. The tables here are self-contained: they do not rely on unpublished stack commits or links to future GitHub `main` content. Speculative decoding can change BF16 outputs; favorable task-specific intervals do not imply byte-lossless inference. Historical and current measurements are not pooled across cache modes, predictor states, budgets, corpora or runtimes.

## Artifact integrity audit, 2026-09-14

All 14 audited model and support files match the corresponding local artifact by full-byte cryptographic hashing, including weights and applicable configuration/tokenizer/vision files. README, license and repository-attribute files are tracked separately from inference artifacts. This publication changes the card and its dated evidence only; model artifacts remain unchanged. [Per-file hashes, audited revision and scope](evaluation/M44-evidence-2026-09-14.json).
