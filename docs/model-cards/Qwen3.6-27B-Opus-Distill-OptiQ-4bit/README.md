---
license: apache-2.0
base_model: TeichAI/Qwen3.6-27B-Claude-Opus-Reasoning-Distill-v2
library_name: mlx
tags:
- mlx
- qwen3_5
pipeline_tag: image-text-to-text
---
# Qwen3.6-27B-Opus-Distill-OptiQ-4bit

Model-card update:2026-09-14.

## Status

Fourth choice on the operator-approved coding menu (B4); not a current research/design pick. Temperature 0.3 with the certified native MTP companion remains configured. Ordinary correctness can conceal expensive nonconvergence on math/research tasks.

## Conversion and attribution

MLX OptiQ KL-sensitivity 4/8-bit conversion of [TeichAI/Qwen3.6-27B-Claude-Opus-Reasoning-Distill-v2](https://huggingface.co/TeichAI/Qwen3.6-27B-Claude-Opus-Reasoning-Distill-v2). Historical serving metadata reports 27B dense parameters, 4.97 effective bits/weight, 18.75 GB weights and 152 eight-bit/353 four-bit quantized modules. The 2026-08-23 vision restoration grafted 333 tensors from the parent:57 linear modules at 8-bit affine/group 64, with convolution/norm/bias/position tensors BF16. The recorded trunk-byte/logit checks and image smoke belong to that graft, not a claim about every future runtime.

Packed low-bit tensor counts can understate true parameter counts in hub badges. Weight-file sizes, effective bits/weight and total MLX runtime peak are different measurements.

### Historical predictor and quality limits

M6b, 2026-08-25, HumanEvalPlus 63 paired tasks, temperature 0.3/TQ4: ordinary 95.24% ON versus 93.65% OFF, delta+1.6 pp[0,+4.8], historical±5 pp equivalence; acceptance 0.923 and approximately 2× decode. This is the recorded predictor certification, not a claim that every later axis is equivalent.

C63 matched Math500,2026-09-11, predictor OFF: ordinary 99%, strict 93%, 94% convergence at 81920 budget, n 100; five repetition runaways plus one budget hit consumed 37% of 21.72 h. The strict score preserves the cost of nonconvergence despite correct final answers. This is why ordinary accuracy alone must not advertise this model as an unrestricted research default.

M39,2026-09-12, predictor OFF:18/20 on a 20-photo COCO description/self-check gate; one person-description mistake and one missed face-wiping detail. Three descriptions were manually inspected. Limited visual functionality is established, not comprehensive image understanding. No current C84 runtime screen for this model is claimed.

## MTP companion

Use [caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter](https://huggingface.co/caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter), captured revision `900b5993b4b590512d5ce9273f2fee599d0ce682`, with `draft_kind: mtp`. The predictor has separate artifact provenance; it is not inferred from a target’s MTP tags.

## Recommended current setting

Save this as `models.yaml` in an environment with the compatible fork revisions described below. The IDs name the target and, where configured, its exact companion; weight quantization and attention-KV precision are separate settings.

```yaml
manager_port: 8000
mlx_port: 8091
startup_timeout_seconds: 300
models:
- name: Qwen3.6-27B-Opus-Distill-OptiQ-4bit
  type: vision
  hf_path: caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit
  max_kv_cache_size: 262144
  kv_prealloc_tokens: 262144
  kv_quant_scheme: turboquant
  kv_bits: 4
  prefill_step_size: 512
  quantized_kv_start: 0
  generation_defaults:
    temperature: 0.3
    top_p: 0.95
    top_k: 20
    min_p: 0.0
    presence_penalty: 0.0
    max_tokens: 102400
    thinking_budget: 81920
    enable_thinking: true
  draft_kind: mtp
  draft_model: caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter
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

The model loads on demand. An OpenAI-compatible client sends requests to `http://localhost:8000/v1` with model ID `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. Omitted sampling fields inherit `generation_defaults`; thinking is enabled. The output cap is 102400 and thinking budget 81920. Near the context limit the server resolves a smaller budget from remaining space; a configured 262144 cap does not imply 262144 input tokens plus another 102400 output tokens.

The full active KV floor equals the context cap; keep prefill 512. `kv_bits: 0` means unquantized native16 attention KV, not unquantized model weights or a newly measured IEEE-FP16 dtype. TurboQuant is inactive when bits are 0 even if its scheme name remains configured. Idle retirement is explicitly true only on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; omitted `cache_session_shrink` preserves the worker default OFF only when `MLX_VLM_SESSION_SHRINK_ON_RETIRE` is absent, as in the command above. Suffix decoding stays OFF. These structural settings target the 64 GB evaluation machine, not arbitrary hardware.

## Runtime and evidence scope

The final C84 environment uses [MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`](https://github.com/ivan-avramov/mlx-vlm/commit/522671c4bebc5ff492d465a1d0e6a14251f18260), [MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`](https://github.com/ivan-avramov/mlx-serve/commit/b632280709f771972bffbaf3231e996e8a89f4e8), and MLX/Metal 0.32.2. Those fork commits are published. Live validation of this exact final bundle covers the two current picks only; other cards retain historical model evidence and source-level compatible configuration, not a newly run model smoke. Older experiments used their recorded earlier runtime and cache mode.

Dates, original source revisions, per-axis observations and evidence-file hashes are recorded in [the accompanying evaluation evidence](evaluation/M44-evidence-2026-09-14.json) alongside this card. The tables here are self-contained: they do not rely on unpublished stack commits or links to future GitHub `main` content. Speculative decoding can change BF16 outputs; favorable task-specific intervals do not imply byte-lossless inference. Historical and current measurements are not pooled across cache modes, predictor states, budgets, corpora or runtimes.

## Artifact integrity audit, 2026-09-14

All 16 audited model and support files match the corresponding local artifact by full-byte cryptographic hashing, including weights and applicable configuration/tokenizer/vision files. README, license and repository-attribute files are tracked separately from inference artifacts. This publication changes the card and its dated evidence only; model artifacts remain unchanged. [Per-file hashes, audited revision and scope](evaluation/M44-evidence-2026-09-14.json).
