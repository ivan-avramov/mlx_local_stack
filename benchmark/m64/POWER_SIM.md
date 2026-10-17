# M64 power simulation (spec §12 step 2)

Observed run-to-run paired discordance (same model, same seeds; c144-base vs P223): 7/172 = 0.041. Margin ±0.05, alpha 0.05, bootstrap B = 2000, 400 simulated chains per scenario. Per-cell paired differences are drawn directly: P(D=+1) = (p_d+delta)/2, P(D=-1) = (p_d-delta)/2, P(D=0) = 1-p_d (E[delta] = true delta; reference accuracy is irrelevant to the statistic); cell sizes are the observed ones. Extra p_d rows: .182 (M55 same-model s1 vs s2, 24/132) and .303 (between picks, 40/132) from the P356 review. Scenarios with |delta| > p_d are infeasible and not simulated.

| pick | p_d | true delta | spec claim (4-cell intersection) passes | pooled 86-item claim passes |
|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.041 | +0.00 | 0.000 | 0.480 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.041 | -0.05 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.041 | -0.10 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.050 | +0.00 | 0.000 | 0.365 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.050 | -0.05 | 0.000 | 0.142 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.050 | -0.10 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.100 | +0.00 | 0.000 | 0.055 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.100 | -0.05 | 0.000 | 0.030 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.100 | -0.10 | 0.000 | 0.003 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.182 | +0.00 | 0.000 | 0.003 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.182 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.182 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.303 | +0.00 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.303 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 0.303 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.041 | +0.00 | 0.000 | 0.463 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.041 | -0.05 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-mlx-uniform-4bit | 0.041 | -0.10 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-mlx-uniform-4bit | 0.050 | +0.00 | 0.000 | 0.345 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.050 | -0.05 | 0.000 | 0.198 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.050 | -0.10 | infeasible (delta beyond p_d) | infeasible |
| Qwen3.8-27B-mlx-uniform-4bit | 0.100 | +0.00 | 0.000 | 0.045 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.100 | -0.05 | 0.000 | 0.030 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.100 | -0.10 | 0.000 | 0.013 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.182 | +0.00 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.182 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.182 | -0.10 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.303 | +0.00 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.303 | -0.05 | 0.000 | 0.000 |
| Qwen3.8-27B-mlx-uniform-4bit | 0.303 | -0.10 | 0.000 | 0.000 |

Rows at delta = 0 are POWER (want ≥ 0.80); rows at delta = −0.05 are the false-pass rate at the margin (want ≤ alpha); delta = −0.10 should almost never pass. Monte Carlo uncertainty: each entry is a proportion of 400 chains (SE ≤ 0.025); an entry of 0.000 means 0/400, one-sided 95 % upper bound 0.0075.

**The pooled rule is INVALID** (P358): it fails calibration at the margin — at p_d = |delta| = .05 the false-pass rate is ≈ 0.178 = P(K ∈ {1, 2}) for K ~ Binomial(86, .05) (exact; the shift bootstrap passes when 1 or 2 of 86 pairs are discordant), far above alpha. Its power rows are therefore not evidence for a usable claim. The 4-cell rule's 0.000 is bounded by discreteness (cells of 21–22 cannot bound ±5 pp).

Owed (not built): a session-level random-effect / correlation sensitivity — cells here are generated independently, so shared loaded-instance effects are not simulated.

Per-cell inputs (pick, language, session, discordant, n, c144-base strict rate):
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python s1: 1/22, ref 0.955
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python s2: 2/22, ref 0.955
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go s1: 1/21, ref 1.000
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go s2: 0/21, ref 1.000
- Qwen3.8-27B-mlx-uniform-4bit python s1: 2/22, ref 1.000
- Qwen3.8-27B-mlx-uniform-4bit python s2: 1/22, ref 1.000
- Qwen3.8-27B-mlx-uniform-4bit go s1: 0/21, ref 1.000
- Qwen3.8-27B-mlx-uniform-4bit go s2: 0/21, ref 1.000
