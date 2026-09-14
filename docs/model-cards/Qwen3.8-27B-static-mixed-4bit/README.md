---
base_model: unsloth/Qwen3.8-27B
license: apache-2.0
tags:
- unsloth
- mlx
library_name: mlx
pipeline_tag: image-text-to-text
---
# Qwen3.8-27B-static-mixed-4bit

Model-card update:2026-09-14.

## Status

Historical candidate, not a current B/C pick. The best-supported historical reproduction setting is temperature 0.4, with an incomplete pre-C28 screen described below. The current stack entry instead contains temperature 1.0; that discrepancy is not resolved by this refresh. Neither value is newly certified here.

## Conversion and attribution

MLX static mixed-precision conversion of [unsloth/Qwen3.8-27B](https://huggingface.co/unsloth/Qwen3.8-27B),27B parameters. The initial language-only conversion had a reported 13.33 GB footprint. The 2026-08-23 revision restored 333 BF16 vision tensors, adding about 0.92 GB. The opening of the previous card incorrectly continued to call that revised artifact text-only; it is corrected here. Keep the initial footprint separate from the restored package.

Packed low-bit tensor counts can understate true parameter counts in hub badges. Weight-file sizes, effective bits/weight and total MLX runtime peak are different measurements.

### Historical limits and configuration discrepancy

Canonical M2 artifacts from 2026-08-18 preserve the t0.4 recipe and exact source/configuration. There were 15 attempted HumanEvalPlus items:13 returned and converged, two transport timeouts (`HumanEval/94`, `HumanEval/71`), and 12/13 returned solutions passed official base/plus tests. The old score file reports strict 12/15=80%, but its `all_converged: true` covers only the 13 returned items; it is not a clean15/15 completion claim. `HumanEval/146` self-terminated after66171 tokens in2885.8 s and failed execution tests. The saved t0.6 screen has only one timed-out `HumanEval/146` request, so it does not establish model nonconvergence.

These pre-C28 transport-limited observations support t0.4 as a historical reproduction starting point, not clean all-item certification or proven superiority to t0.6/t1.0. The manifest pins MLX-VLM `0c1c8b1729c62c068cebf4ababf932306b38ab29` and MLX-Serve `83412c8e5482299389016062895cc4cb09d50a23`, predictor OFF, TQ4, deployed profile, cap/preallocation 262144 and prefill 512. Current registry t1.0 is not evidence of testing; no registry change is made.

The 2026-08-23 restored-vision revision had a one-image smoke, with historical unchanged-trunk byte/logit checks. There is no new 20-photo gate, C84 runtime screen, MTP certification or broad long-context quality result for this recipe. The configured 262144 cap is a setting, not demonstrated effective context.

## Predictor

Predictor OFF: no external MTP recommendation is configured or certified for this exact recipe. A bundled head or MTP tag alone is not evidence to enable speculation.

## Configuration status

For reproducing the historical text screen, use t0.4, top_p 0.95, top_k 20, min_p 0, presence_penalty 0, thinking ON, max_tokens 102400/thinking_budget 81920, TQ4, cap/preallocation 262144, prefill 512 and predictor OFF. This is the measured historical recipe, qualified by the two unrecovered transport failures above. The current stack entry says t1.0 instead; this difference remains unreconciled, and the present vision-restored artifact has not received a new current-runtime certification.

## Runtime and evidence scope

The final C84 environment uses [MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`](https://github.com/ivan-avramov/mlx-vlm/commit/522671c4bebc5ff492d465a1d0e6a14251f18260), [MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`](https://github.com/ivan-avramov/mlx-serve/commit/b632280709f771972bffbaf3231e996e8a89f4e8), and MLX/Metal 0.32.2. Those fork commits are published. Live validation of this exact final bundle covers the two current picks only; other cards retain historical model evidence and source-level compatible configuration, not a newly run model smoke. Older experiments used their recorded earlier runtime and cache mode.

Dates, original source revisions, per-axis observations and evidence-file hashes are recorded in [the accompanying evaluation evidence](evaluation/M44-evidence-2026-09-14.json) alongside this card. The tables here are self-contained: they do not rely on unpublished stack commits or links to future GitHub `main` content. Speculative decoding can change BF16 outputs; favorable task-specific intervals do not imply byte-lossless inference. Historical and current measurements are not pooled across cache modes, predictor states, budgets, corpora or runtimes.

## Artifact integrity audit, 2026-09-14

All 13 audited model and support files match the corresponding local artifact by full-byte cryptographic hashing, including weights and applicable configuration/tokenizer/vision files. README, license and repository-attribute files are tracked separately from inference artifacts. This publication changes the card and its dated evidence only; model artifacts remain unchanged. [Per-file hashes, audited revision and scope](evaluation/M44-evidence-2026-09-14.json).
