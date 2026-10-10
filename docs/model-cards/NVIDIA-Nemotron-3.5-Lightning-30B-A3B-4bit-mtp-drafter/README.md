---
library_name: mlx
license: other
license_name: openmdw-1.1
license_link: https://openmdw.ai/license/1-1/
base_model: caslca/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit
tags:
- mlx
- speculative-decoding
- mtp
- nemotron-3.5  # allow-shorthand (Hugging Face topic tag)
---
# NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-mtp-drafter

Model-card date: 2026-10-10. **PROBE-ONLY — not certified, not recommended for serving.**

External MTP predictor for [NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit](https://huggingface.co/caslca/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit), not a standalone chat model. Published so the measured artifact stays available; the target is served predictor-OFF.

## Lineage and identity

The 270 native `mtp.*` tensors (one attention + one 128-expert MoE block, `eh_proj`, own `lm_head`) were split from shard 14 of [nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) with the mlx-vlm fork's `split_nemotron_h_mtp` (branch `nemotron-h-rollback` @ `d1d57955`) and quantized affine int4 / group 64 (`mtp.safetensors`, ~752 MB; `model_type: nemotron_h_mtp`, `block_size: 2`). The community 4-bit target drops this block; pair only with the matching target. Attribution and OpenMDW 1.1 terms follow the NVIDIA source. No training is claimed.

## Measured (M5 Max 64 GB, 2026-08-31)

| Probe | Verify path | Acceptance (1 draft/round) | Decode ON/OFF |
|---|---|---:|---:|
| M14 | per-position mamba2 state replay (`d1d57955`) | ≈ 0.90 | 0.76× (OFF ≈ 138 tok/s) |
| M29 | one-pass with-states kernel (`nemotron-h-with-states` @ `dd2a2dcb`) | ≈ 0.90 | 1.18× |

Both stopped at the pre-registered gate (1.3×); no quality OFAT, no predictor certification. The round is verify-bound on this already-fast target. Load with `--draft-kind mtp --draft-model <this repo>` on a fork build carrying the `nemotron_h_mtp` loader.
