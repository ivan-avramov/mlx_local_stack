---
library_name: mlx
license: other
license_name: openmdw-1.1
license_link: https://openmdw.ai/license/1-1/
pipeline_tag: text-generation
language:
- en
- es
- fr
- de
- it
- ja
tags:
- nvidia
- pytorch
- nemotron-3.5
- mlx
datasets:
- nvidia/nemotron-post-training-v3
- nvidia/nemotron-pre-training-datasets
track_downloads: true
base_model: nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16
---
# NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

Model-card update:2026-09-14.

## Status

Availability/insurance mirror retained as a fast text-only reasoning/math option. Research/design shortlist only, not a current C pick. The tested serving source is mlx-community; use this mirror as the corresponding availability copy after checking the pinned artifacts. Native expert routing and predictor OFF remain selected; temperature 0.5 was approved on 2026-09-10.

## Conversion and attribution

Availability mirror of [mlx-community/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit](https://huggingface.co/mlx-community/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit), itself an affine 4-bit/group 64 quantization of [nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16). Attribution and OpenMDW 1.1 terms follow those sources. It is a text-only `nemotron_h` Mamba-hybrid MoE, roughly 30B total/3B active parameters; the previous card reports 17.78 GB weights. The mirror was created 2026-08-23 for availability; no new training is claimed.

Packed low-bit tensor counts can understate true parameter counts in hub badges. Weight-file sizes, effective bits/weight and total MLX runtime peak are different measurements.

### Latest applicable historical tune and routing evidence

C48/C62,2026-09-10: temperature 0.5, native routing, predictor OFF. Math500100 tasks: ordinary/strict 97%, 100% convergence; paired against t1.0, delta+1 pp[0,+3] and token ratio recorded in the accompanying evidence. MBPPPlus 100 tasks: ordinary/strict 87%, 99% convergence (one nonconverged incorrect answer); delta+3 pp[−1,+8] versus t1.0, INCONCLUSIVE. Nominal axis MDE 12.5 pp. T0.5 was operator-approved; it is no longer an untuned t1.0 vendor default.

M34r routing transfer, 2026-09-10 at t1.0: expansion changed Math50096→98% strict (+2 pp[0,+5]) but MBPPPlus 84→82% (−2 pp[−8,+4]), with higher token/time cost. Native routing was retained. M14,2026-08-31: the transplanted MTP diagnostic ran 0.76× the OFF decode rate, so no quality OFAT or predictor activation followed. Neither observation is a benchmark of the other current picks.

This architecture is text-only. `type: vision` below selects the MLX-VLM backend; it does not grant image capability. No C84 runtime screen is claimed for this mirror.

## Predictor

Predictor OFF: no external MTP recommendation is configured or certified for this exact recipe. A bundled head or MTP tag alone is not evidence to enable speculation.

## Recommended current setting

Save this as `models.yaml` in an environment with the compatible fork revisions described below. The IDs name the target and, where configured, its exact companion; weight quantization and attention-KV precision are separate settings.

```yaml
manager_port: 8000
mlx_port: 8091
startup_timeout_seconds: 300
models:
- name: NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit
  type: vision
  hf_path: caslca/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit
  max_kv_cache_size: 262144
  kv_prealloc_tokens: 262144
  kv_bits: 0
  prefill_step_size: 512
  generation_defaults:
    temperature: 0.5
    top_p: 0.95
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

The model loads on demand. An OpenAI-compatible client sends requests to `http://localhost:8000/v1` with model ID `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`. Omitted sampling fields inherit `generation_defaults`; thinking is enabled. The output cap is 102400 and thinking budget 81920. Near the context limit the server resolves a smaller budget from remaining space; a configured 262144 cap does not imply 262144 input tokens plus another 102400 output tokens.

The full active KV floor equals the context cap; keep prefill 512. `kv_bits: 0` means unquantized native16 attention KV, not unquantized model weights or a newly measured IEEE-FP16 dtype. TurboQuant is inactive when bits are 0 even if its scheme name remains configured. Idle retirement is explicitly true only on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; omitted `cache_session_shrink` preserves the worker default OFF only when `MLX_VLM_SESSION_SHRINK_ON_RETIRE` is absent, as in the command above. Suffix decoding stays OFF. These structural settings target the 64 GB evaluation machine, not arbitrary hardware.

The published mirror ID is used above for availability; the historical evaluation used its mlx-community source. The mirror relationship and exact revision binding are distinct from the benchmark scores.

## Runtime and evidence scope

The final C84 environment uses [MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`](https://github.com/ivan-avramov/mlx-vlm/commit/522671c4bebc5ff492d465a1d0e6a14251f18260), [MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`](https://github.com/ivan-avramov/mlx-serve/commit/b632280709f771972bffbaf3231e996e8a89f4e8), and MLX/Metal 0.32.2. Those fork commits are published. Live validation of this exact final bundle covers the two current picks only; other cards retain historical model evidence and source-level compatible configuration, not a newly run model smoke. Older experiments used their recorded earlier runtime and cache mode.

Dates, original source revisions, per-axis observations and evidence-file hashes are recorded in [the accompanying evaluation evidence](evaluation/M44-evidence-2026-09-14.json) alongside this card. The tables here are self-contained: they do not rely on unpublished stack commits or links to future GitHub `main` content. Speculative decoding can change BF16 outputs; favorable task-specific intervals do not imply byte-lossless inference. Historical and current measurements are not pooled across cache modes, predictor states, budgets, corpora or runtimes.

## Artifact integrity audit, 2026-09-14

All 10 audited model and support files match the corresponding local artifact by full-byte cryptographic hashing, including weights and applicable configuration/tokenizer/vision files. README, license and repository-attribute files are tracked separately from inference artifacts. This publication changes the card and its dated evidence only; model artifacts remain unchanged. [Per-file hashes, audited revision and scope](evaluation/M44-evidence-2026-09-14.json).
