---
base_model: TeichAI/Qwen3.8-27B-Fable-Distill
tags:
- text-generation-inference
- transformers
- unsloth
- qwen3_5
- mlx
license: apache-2.0
language:
- en
datasets:
- armand0e/claude-fable-5-claude-code
- armand0e/Fable-5-Chat
library_name: mlx
pipeline_tag: image-text-to-text
---
# Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit

Model-card update:2026-09-14.

## Status

Historical published candidate, not a current B/C pick. Its recorded recipe and tests are retained below; it has not received the current two-pick C84 runtime screen or a new predictor certification.

## Conversion and attribution

MLX uniform 4-bit conversion of [TeichAI/Qwen3.8-27B-Fable-Distill](https://huggingface.co/TeichAI/Qwen3.8-27B-Fable-Distill). Historical metadata reports 27B VLM parameters, 498 four-bit quantized modules, 4.0 effective bits/weight and 16.05 GB weights. This is a separate conversion from `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; results and predictor compatibility must not be transferred merely because the fine-tuned parent is shared.

Packed low-bit tensor counts can understate true parameter counts in hub badges. Weight-file sizes, effective bits/weight and total MLX runtime peak are different measurements.

### Historical comparison, 2026-09-03 (M21b)

At this recipe's t0.6 versus `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` at t0.5, both predictor OFF with thinking enabled, 50 tasks×3 draws per dataset: HumanEvalPlus strict 90.0% here versus 89.3% mixed; MBPPPlus 79.3% here versus 81.3% mixed. The paired mixed/uniform token ratios were 0.66[0.39,0.98] and 0.64[0.40,0.97]. The historical pooled comparison supported carrying the mixed recipe; this is a comparison of complete recipe+tune pairs, not an isolated precision effect. Tail variability matters.

No external MTP predictor is certified for this exact fine-tuned uniform conversion. The current C84 results for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` or `Qwen3.8-27B-mlx-uniform-4bit` cannot be transferred here. Vision packaging does not itself establish image quality; no new vision gate or runtime smoke is claimed in this refresh.

## Predictor

Predictor OFF: no external MTP recommendation is configured or certified for this exact recipe. A bundled head or MTP tag alone is not evidence to enable speculation.

## Recorded historical-candidate configuration, not a new recommendation

Save this as `models.yaml` in an environment with the compatible fork revisions described below. The IDs name the target and, where configured, its exact companion; weight quantization and attention-KV precision are separate settings.

```yaml
manager_port: 8000
mlx_port: 8091
startup_timeout_seconds: 300
models:
- name: Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit
  type: vision
  hf_path: caslca/Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit
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

The model loads on demand. An OpenAI-compatible client sends requests to `http://localhost:8000/v1` with model ID `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`. Omitted sampling fields inherit `generation_defaults`; thinking is enabled. The output cap is 102400 and thinking budget 81920. Near the context limit the server resolves a smaller budget from remaining space; a configured 262144 cap does not imply 262144 input tokens plus another 102400 output tokens.

The full active KV floor equals the context cap; keep prefill 512. `kv_bits: 0` means unquantized native16 attention KV, not unquantized model weights or a newly measured IEEE-FP16 dtype. TurboQuant is inactive when bits are 0 even if its scheme name remains configured. Idle retirement is explicitly true only on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; omitted `cache_session_shrink` preserves the worker default OFF only when `MLX_VLM_SESSION_SHRINK_ON_RETIRE` is absent, as in the command above. Suffix decoding stays OFF. These structural settings target the 64 GB evaluation machine, not arbitrary hardware.

## Runtime and evidence scope

The final C84 environment uses [MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`](https://github.com/ivan-avramov/mlx-vlm/commit/522671c4bebc5ff492d465a1d0e6a14251f18260), [MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`](https://github.com/ivan-avramov/mlx-serve/commit/b632280709f771972bffbaf3231e996e8a89f4e8), and MLX/Metal 0.32.2. Those fork commits are published. Live validation of this exact final bundle covers the two current picks only; other cards retain historical model evidence and source-level compatible configuration, not a newly run model smoke. Older experiments used their recorded earlier runtime and cache mode.

Dates, original source revisions, per-axis observations and evidence-file hashes are recorded in [the accompanying evaluation evidence](evaluation/M44-evidence-2026-09-14.json) alongside this card. The tables here are self-contained: they do not rely on unpublished stack commits or links to future GitHub `main` content. Speculative decoding can change BF16 outputs; favorable task-specific intervals do not imply byte-lossless inference. Historical and current measurements are not pooled across cache modes, predictor states, budgets, corpora or runtimes.

## Artifact integrity audit, 2026-09-14

All 13 audited model and support files match the corresponding local artifact by full-byte cryptographic hashing, including weights and applicable configuration/tokenizer/vision files. README, license and repository-attribute files are tracked separately from inference artifacts. This publication changes the card and its dated evidence only; model artifacts remain unchanged. [Per-file hashes, audited revision and scope](evaluation/M44-evidence-2026-09-14.json).
