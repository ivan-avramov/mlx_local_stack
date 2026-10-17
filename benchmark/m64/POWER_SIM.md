# M64 power simulation (spec §12 step 2)

Observed run-to-run paired discordance (same model, same seeds; c144-base vs P223): 7/172 = 0.041. Margin ±0.05, alpha 0.05, bootstrap B = 2000, 400 simulated chains per scenario. Pair outcomes are drawn from a feasible joint table (P(D=+1) = (p_d+delta)/2, P(D=-1) = (p_d-delta)/2; E[delta] = true delta); each cell's reference accuracy is its observed c144-base strict rate, clamped to the feasible window (a 100 % reference becomes 1 - p_d/2 at delta = 0). Extra p_d rows: .182 (M55 same-model s1 vs s2, 24/132) and .303 (between picks, 40/132) from the P356 review.

| pick | p_d | true delta | spec claim (4-cell intersection) passes | pooled 86-item claim passes |
|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.041 | +0.00 | 0.000 | 0.507 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.041 | -0.05 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.041 | -0.10 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.050 | +0.00 | 0.000 | 0.345 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.050 | -0.05 | 0.000 | 0.180 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.050 | -0.10 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.100 | +0.00 | 0.000 | 0.065 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.100 | -0.05 | 0.000 | 0.050 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.100 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.182 | +0.00 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.182 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.182 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.303 | +0.00 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.303 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.303 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.041 | +0.00 | 0.000 | 0.490 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.041 | -0.05 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-mlx-uniform-4bit | 0.041 | -0.10 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-mlx-uniform-4bit | 0.050 | +0.00 | 0.000 | 0.398 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.050 | -0.05 | 0.000 | 0.160 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.050 | -0.10 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-mlx-uniform-4bit | 0.100 | +0.00 | 0.000 | 0.045 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.100 | -0.05 | 0.000 | 0.015 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.100 | -0.10 | 0.000 | 0.018 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.182 | +0.00 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.182 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.182 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.303 | +0.00 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.303 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.303 | -0.10 | 0.000 | 0.000 |

Rows at delta = 0 are POWER (want ≥ 0.80); rows at delta = −0.05 are the type-I error at the margin (want ≤ alpha); delta = −0.10 should almost never pass.

Per-cell inputs (pick, language, session, discordant, n, c144-base strict rate):
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python s1: 1/22, ref 0.955
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python s2: 2/22, ref 0.955
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go s1: 1/21, ref 1.000
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go s2: 0/21, ref 1.000
- Qwen3.8-27B-mlx-uniform-4bit python s1: 2/22, ref 1.000
- Qwen3.8-27B-mlx-uniform-4bit python s2: 1/22, ref 1.000
- Qwen3.8-27B-mlx-uniform-4bit go s1: 0/21, ref 1.000
- Qwen3.8-27B-mlx-uniform-4bit go s2: 0/21, ref 1.000
