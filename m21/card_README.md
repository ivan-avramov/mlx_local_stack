---
base_model: TeichAI/Qwen3.8-27B-Fable-Distill
tags:
- text-generation-inference
- transformers
- unsloth
- qwen3_5
- mlx
- optiq
license: apache-2.0
language:
- en
datasets:
- armand0e/claude-fable-5-claude-code
- armand0e/Fable-5-Chat
library_name: mlx
pipeline_tag: image-text-to-text
---
# Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed

**27B (VLM) parameters** — note: Hugging Face's size badge undercounts packed low-bit MLX
weights (it counts the packed uint32 tensors), so the number shown beside this repo is wrong;
the figure here is the true parameter count.

MLX **OptiQ sensitivity-mixed** quant of [TeichAI/Qwen3.8-27B-Fable-Distill](https://huggingface.co/TeichAI/Qwen3.8-27B-Fable-Distill):
KL-sensitivity-ranked layers get more bits, the rest stay at 4-bit. Sibling: the uniform 4-bit
[caslca/Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit](https://huggingface.co/caslca/Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit).

| measured | value |
|---|---|
| effective bits/weight | **4.67** (target 4.0 reference: uniform 4-bit; 150 layers raised, 346 at 4-bit) |
| weights footprint | 18.44 GB (text shards; `optiq/optiq_vision.safetensors` carries the bf16 vision tower sidecar) |
| quantized-layer bit histogram | 8-bit: 150, 4-bit: 346 |

## Why this quant exists (measured, not vibes)

Same checkpoint, two recipes, paired on the same items with 3 seeded draws each, thinking ON, no
speculative decoding, identical serving stack:

| bench (n=50 × 3 draws) | this quant @t0.5 | uniform 4-bit @t0.6 | tokens per task ratio |
|---|---|---|---|
| HumanEval+ strict pass@1 | 0.893 | 0.900 | 0.66 (95% CI 0.39–0.98) |
| MBPP+ strict pass@1 | 0.813 | 0.793 | 0.64 (95% CI 0.40–0.97) |
| pooled (100 items) | equivalent (TOST ±5pp) | — | **0.65 (95% CI 0.46–0.88)** |

Equal correctness, about a third fewer generated tokens per task. The saving is in the verbose /
bimodal reasoning tail, not in the items the model cannot solve (those fail on both recipes).

## Recommended sampling

| param | value |
|---|---|
| temperature | **0.5** (certified by a per-model temperature ladder 0.4–0.7, then the k=3 confirmation above) |
| top_p / top_k / min_p | 0.95 / 20 / 0.0 |
| presence_penalty | 0.0 |
| max_tokens / thinking_budget | 102400 / 81920 (thinking ON) |

These values were certified by an execution-gated benchmark campaign (temperature ladders with
convergence gates over HumanEval+/MBPP+, paired item-cluster bootstraps) — methodology and full
results: [https://github.com/<user>-avramov/mlx_local_stack](https://github.com/<user>-avramov/mlx_local_stack).

Serving: MLX (`mlx-vlm`). Quantized on-device with `mlx_optiq` (mixed-precision KL-sensitivity
recipe; `optiq/sensitivity.json` and `optiq/metadata.json` are the recipe's provenance).
`optiq/mtp.safetensors` is the checkpoint's MTP head carried through conversion — untested as a
drafter; serve draft-OFF.
