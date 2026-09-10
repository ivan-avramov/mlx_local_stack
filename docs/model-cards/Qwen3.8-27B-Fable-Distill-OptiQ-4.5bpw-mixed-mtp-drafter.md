---
license: apache-2.0
base_model: caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
tags:
- mlx
- speculative-decoding
- mtp
---
# Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed MTP drafter

A repaired MTP sidecar for [Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed](https://huggingface.co/caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed). This is a predictor, not a standalone language model.

## Status

CERTIFIED M36, 2026-09-10: validated in the speed and paired coding-quality experiment; operator approved the matching medium-effort production triple. Registry activation follows publication and anonymous download verification. Speculative decoding can change outputs; it is not guaranteed lossless.

## Repair and provenance

The original stripped-key sidecar retained seven HF normalization offsets. Its loader converts those offsets only when the keys retain the `mtp.` prefix. Adding 1.0 with BF16 round-to-nearest-even to the seven norm vectors repairs their convention. The 22 matrix/quant tensors are unchanged; all 29 resulting tensor payloads match the independently working base-model sidecar.

Original tensor-file SHA256: `26967a026f91d3bc1ce440584e931e41311e224c9467c376e5b06c45a402f968`.

Repaired tensor-file SHA256: `ff4d5cfc53e8de65afc6bf2b0734ede4b32c7a4b9e7ac5d5b047413630cc0353`.

The original head supplied with the checkpoint is the source; no new training or target-model weight change was performed. Attribution and licensing follow the source artifacts.

## Measured evidence

M5 Max 64GB; medium reasoning effort, target temperature 0.5, matching budgets and item seeds. Serving revisions: mlx-vlm `420c01e1`, mlx-serve `0ccc684`. Quality used native ARM64 EvalPlus evaluation with unchanged evaluator source and corpus.

Three-task speed screen: repaired sidecar 1.836x median decode speed versus OFF; draft acceptance 3843/4548 (84.5%); all six responses converged. The original sidecar accepted 0/12,516 and ran at 0.620x. A separate known-positive base control passed before interpreting the zero.

| Dataset | Tasks × samples per arm | Strict OFF | Strict repaired ON | ON minus OFF, paired 95% CI |
|---|---:|---:|---:|---|
| HumanEvalPlus | 50 × 3 | 92.0% | 90.67% | −1.33pp [−5.33,+2.0] |
| MBPPPlus | 50 × 3 | 84.67% | 85.33% | +0.67pp [−2.0,+4.67] |
| Combined, equal item weight | 100 × 3 | 88.33% | 88.0% | −0.33pp [−3.0,+2.33] |

All 600 responses converged. The combined quality interval lies within the predeclared ±5pp equivalence margin; HumanEvalPlus alone remains inconclusive. Nominal axis MDE is17.7pp per dataset and12.5pp pooled. These are descriptive paired bootstrap intervals before campaign-wide multiplicity adjustment.

Combined generation time was1.123h ON versus2.691h OFF; paired wall-time ratio0.417,95% CI[0.238,0.603]. Output-token ratio0.778,CI[0.463,1.082]. Wall-time improvement includes changed output lengths and long-tail behavior, not only faster decode. The OFF HumanEvalPlus arm included one48,353-token converged response.

Use only with the matching target and a compatible MTP implementation. This evidence does not establish long-context capacity or subjective code quality; it covers execution-tested coding tasks at the recorded configuration.
