# M64 power simulation (spec §12 step 2)

Observed run-to-run paired discordance (same model, same seeds; c144-base vs P223): 7/172 = 0.041. Margin ±0.05, alpha 0.05, bootstrap B = 2000, 400 simulated chains per scenario. References = the c144-base strict outcomes of each pick.

| pick | p_d | true delta | spec claim (4-cell intersection) passes | pooled 86-item claim passes |
|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.041 | +0.00 | 0.000 | 0.340 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.041 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.041 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.050 | +0.00 | 0.000 | 0.198 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.050 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.050 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.100 | +0.00 | 0.000 | 0.005 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.100 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.100 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.041 | +0.00 | 0.000 | 0.300 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.041 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.041 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.050 | +0.00 | 0.000 | 0.220 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.050 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.050 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.100 | +0.00 | 0.000 | 0.007 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.100 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.100 | -0.10 | 0.000 | 0.000 |

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
