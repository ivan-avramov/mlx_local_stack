---
base_model:
- caslca/Ornith-1.0-35B-mlx-uniform-4bit
- Qwen/Qwen3.5-35B-A3B
license: apache-2.0
tags:
- mlx
- speculative-decoding
- mtp
library_name: mlx
---
# Ornith-1.0-35B-mlx-uniform-4bit-mtp-drafter

Model-card update:2026-09-14.

This repository is an external MTP predictor for [Ornith-1.0-35B-mlx-uniform-4bit](https://huggingface.co/caslca/Ornith-1.0-35B-mlx-uniform-4bit), not a standalone chat model. Third choice on the operator-approved coding menu (B3); research/design shortlist only, not a C pick. Retain native expert routing, temperature 0.4 and the certified transplanted MTP head. Later MBPPPlus tail costs qualify the original predictor result.

## Predictor lineage and identity

The fine-tuned trunk omitted its base predictor. This is the transplanted native head from [Qwen/Qwen3.5-35B-A3B](https://huggingface.co/Qwen/Qwen3.5-35B-A3B),785 `mtp.*` tensors from shards 13–14, stacked into 9 `switch_mlp` quantization triplets. One layer, 256 routed experts plus one shared expert, int4/group 64, roughly 450 MB plus tokenizer. Head weights are Apache 2.0; the trunk is MIT. Historical cards used the additional attribution spelling `ornith-ai/Ornith-1.0-35B`; the trunk’s preserved base_model link is deepreinforce-ai. Historical splitting used `--model-type qwen3_next`; serving model_type is `qwen3_5_mtp`. Measured serving used two drafted tokens per round; config block_size 3 is splitter metadata, not a claim that three tokens were proposed.

### Historical predictor and routing evidence

M27,2026-08-31, HumanEvalPlus 164 paired seeded tasks, native16 KV, temperature 0.4, thinking 81920: MTP ON/OFF ordinary 92.07/92.68%, delta−0.61 pp[−4.3,+3.0] (historical±5 pp equivalence); strict 85.98/86.59%, delta−0.61 pp[−6.7,+5.5] INCONCLUSIVE. Nonconverged 13/164 versus 12/164. Nominal MDE 9.8 pp; acceptance 0.778, paired mean decode 1.56×, corpus 3.28 h ON versus 4.65 h OFF. These are workload/session-specific measurements.

M34r, 2026-09-10, native routing MBPPPlus 100 paired tasks: ordinary 83% both; strict 78% ON versus 81% OFF, delta−3 pp[−8,+2], INCONCLUSIVE (MDE 12.5 pp). Nonconverged 6 versus 2; output-token ratio 1.939[0.970,4.149], generation 1.47 h versus 1.06 h. Expanded routing did not earn promotion. Native routing/MTP remain configured on the combined historical evidence, with this adverse coding-tail trend explicit; do not pool the different corpora into blanket equivalence.

M39,2026-09-12:20/20 in a 20-photo COCO description/self-check gate, predictor OFF. Three descriptions were manually checked against captions. This establishes limited visual functionality, not OCR/document/chart quality or a vision ranking. No C84 runtime screen for this model is claimed.

## Recommended current setting

Save this as `models.yaml` in an environment with the compatible fork revisions described below. The IDs name the target and, where configured, its exact companion; weight quantization and attention-KV precision are separate settings.

```yaml
manager_port: 8000
mlx_port: 8091
startup_timeout_seconds: 300
models:
- name: Ornith-1.0-35B-mlx-uniform-4bit
  type: vision
  hf_path: caslca/Ornith-1.0-35B-mlx-uniform-4bit
  max_kv_cache_size: 262144
  kv_prealloc_tokens: 262144
  kv_bits: 0
  prefill_step_size: 512
  draft_kind: mtp
  draft_model: caslca/Ornith-1.0-35B-mlx-uniform-4bit-mtp-drafter
  generation_defaults:
    temperature: 0.4
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

The model loads on demand. An OpenAI-compatible client sends requests to `http://localhost:8000/v1` with model ID `Ornith-1.0-35B-mlx-uniform-4bit`. Omitted sampling fields inherit `generation_defaults`; thinking is enabled. The output cap is 102400 and thinking budget 81920. Near the context limit the server resolves a smaller budget from remaining space; a configured 262144 cap does not imply 262144 input tokens plus another 102400 output tokens.

The full active KV floor equals the context cap; keep prefill 512. `kv_bits: 0` means unquantized native16 attention KV, not unquantized model weights or a newly measured IEEE-FP16 dtype. TurboQuant is inactive when bits are 0 even if its scheme name remains configured. Idle retirement is explicitly true only on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; omitted `cache_session_shrink` preserves the worker default OFF only when `MLX_VLM_SESSION_SHRINK_ON_RETIRE` is absent, as in the command above. Suffix decoding stays OFF. These structural settings target the 64 GB evaluation machine, not arbitrary hardware.

## Runtime and evidence scope

The final C84 environment uses [MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`](https://github.com/ivan-avramov/mlx-vlm/commit/522671c4bebc5ff492d465a1d0e6a14251f18260), [MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`](https://github.com/ivan-avramov/mlx-serve/commit/b632280709f771972bffbaf3231e996e8a89f4e8), and MLX/Metal 0.32.2. Those fork commits are published. Live validation of this exact final bundle covers the two current picks only; other cards retain historical model evidence and source-level compatible configuration, not a newly run model smoke. Older experiments used their recorded earlier runtime and cache mode.

Dates, original source revisions, per-axis observations and evidence-file hashes are recorded in [the accompanying evaluation evidence](evaluation/M44-evidence-2026-09-14.json) alongside this card. The tables here are self-contained: they do not rely on unpublished stack commits or links to future GitHub `main` content. Speculative decoding can change BF16 outputs; favorable task-specific intervals do not imply byte-lossless inference. Historical and current measurements are not pooled across cache modes, predictor states, budgets, corpora or runtimes.

## Artifact integrity audit, 2026-09-14

All 5 audited model and support files match the corresponding local artifact by full-byte cryptographic hashing, including weights and applicable configuration/tokenizer/vision files. README, license and repository-attribute files are tracked separately from inference artifacts. This publication changes the card and its dated evidence only; model artifacts remain unchanged. [Per-file hashes, audited revision and scope](evaluation/M44-evidence-2026-09-14.json).
