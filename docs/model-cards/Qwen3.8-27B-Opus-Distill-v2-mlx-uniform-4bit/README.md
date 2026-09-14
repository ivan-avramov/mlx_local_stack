---
license: apache-2.0
base_model: barozp/Qwen3.8-27B-Opus-Distill-v2
base_model_relation: finetune
library_name: mlx
pipeline_tag: image-text-to-text
tags:
- qwen
- lora
- reasoning
- opus-distill
- vision
- mtp
- causal-lm
- v2
- mlx
---
# Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit

Model-card update:2026-09-14.

## Status

Historical published candidate, not a current B/C pick. Its recorded recipe and tests are retained below; it has not received the current two-pick C84 runtime screen or a new predictor certification.

## Conversion and attribution

MLX uniform 4-bit conversion of [barozp/Qwen3.8-27B-Opus-Distill-v2](https://huggingface.co/barozp/Qwen3.8-27B-Opus-Distill-v2). Historical metadata reports 27B VLM parameters, 498 four-bit quantized modules, 4.0 effective bits/weight and 16.05 GB weights. Parent fine-tuning attribution and Apache 2.0 metadata are preserved in the card frontmatter.

Packed low-bit tensor counts can understate true parameter counts in hub badges. Weight-file sizes, effective bits/weight and total MLX runtime peak are different measurements.

### Historical tune, 2026-09-03 restatement (C46)

The t0.55 recipe's recorded HumanEvalPlus/MBPPPlus strict scores were 86%/74%, versus 86%/70% at t0.6, with zero versus two budget-hit draws across 100 items. Earlier larger claims relied on pre-C28 timeout artifacts and are not retained as clean evidence. These point estimates do not establish a new paired equivalence claim. The existing t0.55 setting remains a historical candidate recipe, not a current pick.

No MTP predictor or current C84 runtime certification is claimed for this exact conversion. Vision-tagged packaging is not a substitute for a documented vision benchmark; no new image-quality result is added.

## Predictor

Predictor OFF: no external MTP recommendation is configured or certified for this exact recipe. A bundled head or MTP tag alone is not evidence to enable speculation.

## Recorded historical-candidate configuration, not a new recommendation

Save this as `models.yaml` in an environment with the compatible fork revisions described below. The IDs name the target and, where configured, its exact companion; weight quantization and attention-KV precision are separate settings.

```yaml
manager_port: 8000
mlx_port: 8091
startup_timeout_seconds: 300
models:
- name: Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit
  type: vision
  hf_path: caslca/Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit
  max_kv_cache_size: 262144
  kv_prealloc_tokens: 262144
  kv_quant_scheme: turboquant
  kv_bits: 4
  quantized_kv_start: 0
  prefill_step_size: 512
  generation_defaults:
    temperature: 0.55
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

The model loads on demand. An OpenAI-compatible client sends requests to `http://localhost:8000/v1` with model ID `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`. Omitted sampling fields inherit `generation_defaults`; thinking is enabled. The output cap is 102400 and thinking budget 81920. Near the context limit the server resolves a smaller budget from remaining space; a configured 262144 cap does not imply 262144 input tokens plus another 102400 output tokens.

The full active KV floor equals the context cap; keep prefill 512. `kv_bits: 0` means unquantized native16 attention KV, not unquantized model weights or a newly measured IEEE-FP16 dtype. TurboQuant is inactive when bits are 0 even if its scheme name remains configured. Idle retirement is explicitly true only on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; omitted `cache_session_shrink` preserves the worker default OFF only when `MLX_VLM_SESSION_SHRINK_ON_RETIRE` is absent, as in the command above. Suffix decoding stays OFF. These structural settings target the 64 GB evaluation machine, not arbitrary hardware.

## Runtime and evidence scope

The final C84 environment uses [MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`](https://github.com/ivan-avramov/mlx-vlm/commit/522671c4bebc5ff492d465a1d0e6a14251f18260), [MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`](https://github.com/ivan-avramov/mlx-serve/commit/b632280709f771972bffbaf3231e996e8a89f4e8), and MLX/Metal 0.32.2. Those fork commits are published. Live validation of this exact final bundle covers the two current picks only; other cards retain historical model evidence and source-level compatible configuration, not a newly run model smoke. Older experiments used their recorded earlier runtime and cache mode.

Dates, original source revisions, per-axis observations and evidence-file hashes are recorded in [the accompanying evaluation evidence](evaluation/M44-evidence-2026-09-14.json) alongside this card. The tables here are self-contained: they do not rely on unpublished stack commits or links to future GitHub `main` content. Speculative decoding can change BF16 outputs; favorable task-specific intervals do not imply byte-lossless inference. Historical and current measurements are not pooled across cache modes, predictor states, budgets, corpora or runtimes.

## Artifact integrity audit, 2026-09-14

All 12 audited model and support files match the corresponding local artifact by full-byte cryptographic hashing, including weights and applicable configuration/tokenizer/vision files. README, license and repository-attribute files are tracked separately from inference artifacts. This publication changes the card and its dated evidence only; model artifacts remain unchanged. [Per-file hashes, audited revision and scope](evaluation/M44-evidence-2026-09-14.json).
