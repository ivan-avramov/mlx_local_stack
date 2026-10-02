# M54 AgentBench OS -- cross-arm comparison

`python -m bench.agentbench_compare --rows Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=$STACK_WORKDIR/m54/arms_df3b65c/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/agentbench_os.v1.jsonl --rows Qwen3.8-27B-mlx-uniform-4bit=$STACK_WORKDIR/m54/arms_df3b65c/Qwen3.8-27B-mlx-uniform-4bit/agentbench_os.v1.jsonl --rows Ornith-1.0-35B-mlx-uniform-4bit=$STACK_WORKDIR/m54/arms_df3b65c/Ornith-1.0-35B-mlx-uniform-4bit/agentbench_os.v1.jsonl --rows Qwen3.6-27B-Opus-Distill-OptiQ-4bit=$STACK_WORKDIR/m54/arms_df3b65c/Qwen3.6-27B-Opus-Distill-OptiQ-4bit/agentbench_os.v1.jsonl --rows NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=$STACK_WORKDIR/m54/arms_df3b65c/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit/agentbench_os.v1.jsonl --out $STACK_WORKDIR/m54/arms_df3b65c/compare_chain3.md`

Bootstrap: iters=10000 seed=0 TOST margin=0.05 (+-5pp); MDE alpha=0.05 power=0.8 p_d=0.2

## The four numbers (per arm)

capability ceiling = acc (raw `passed`, NOT gated by convergence); edit/agent competence = acc_strict (passed AND converged -- the ranking metric, at the named thinking budget); latency per task = wall_total_s; runaway tax = turn_cap + exec_timeout share of n and their share of total wall-clock. NEVER RANK ON TOKENS OR WALL-CLOCK -- reported as plain distributions, never a composite.

| model | n | graded_n | capability ceiling (acc) | acc_strict@budget | wall_total_s mean/p90/max | runaway tax n (share) / wall share |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 142 | 142 | 0.592 | 0.592@81920 | 30.3/58.8/159.1 | 3 (0.021) / 0.065 |
| Qwen3.8-27B-mlx-uniform-4bit | 142 | 142 | 0.592 | 0.592@81920 | 45.6/92.3/364.1 | 12 (0.085) / 0.217 |
| Ornith-1.0-35B-mlx-uniform-4bit | 142 | 142 | 0.542 | 0.535@81920 | 31.0/33.7/2071.9 | 5 (0.035) / 0.025 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 142 | 142 | 0.620 | 0.620@81920 | 101.8/70.4/5026.1 | 16 (0.113) / 0.427 |
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | 142 | 142 | 0.423 | 0.423@81920 | 12.5/23.1/97.2 | 17 (0.120) / 0.208 |

## Per-arm detail

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed

- n=142 graded_n=142
- acc (capability ceiling) = 0.592
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.592
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 84, 'failed_tests': 55, 'turn_cap': 3, 'exec_timeout': 0, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=385.8 median=235.5 p90=811.7 max=2510
- wall_total_s per task: mean=30.3 p90=58.8 max=159.1
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.714, 2: 1.0, 3: 1.0, 4: 0.944, 5: 0.6, 6: 0.667, 7: 0.448}
- runaway tax (turn_cap + exec_timeout): n=3 share=0.021 wall_share=0.065

### Qwen3.8-27B-mlx-uniform-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.592
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.592
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 84, 'failed_tests': 46, 'turn_cap': 12, 'exec_timeout': 0, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=720.1 median=398.0 p90=1597.4 max=6494
- wall_total_s per task: mean=45.6 p90=92.3 max=364.1
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.857, 2: 0.8, 3: 1.0, 4: 0.833, 5: 0.7, 6: 0.778, 7: 0.448}
- runaway tax (turn_cap + exec_timeout): n=12 share=0.085 wall_share=0.217

### Ornith-1.0-35B-mlx-uniform-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.542
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.535
- conv_rate = 0.993; nonconv_kinds = {'budget_hit': 1}
- outcome counts: {'solved': 77, 'failed_tests': 60, 'turn_cap': 5, 'exec_timeout': 0, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=1180.4 median=486.5 p90=1364.6 max=82351
- wall_total_s per task: mean=31.0 p90=33.7 max=2071.9
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.571, 2: 0.4, 3: 1.0, 4: 0.778, 5: 0.3, 6: 0.667, 7: 0.483}
- runaway tax (turn_cap + exec_timeout): n=5 share=0.035 wall_share=0.025

### Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.620
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.620
- conv_rate = 0.986; nonconv_kinds = {'budget_hit': 2}
- outcome counts: {'solved': 88, 'failed_tests': 38, 'turn_cap': 16, 'exec_timeout': 0, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=1892.4 median=502.5 p90=1508.7 max=88773
- wall_total_s per task: mean=101.8 p90=70.4 max=5026.1
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 1.0, 2: 1.0, 3: 1.0, 4: 0.944, 5: 0.7, 6: 0.778, 7: 0.448}
- runaway tax (turn_cap + exec_timeout): n=16 share=0.113 wall_share=0.427

### NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.423
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.423
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 60, 'failed_tests': 68, 'turn_cap': 14, 'exec_timeout': 3, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=1370.4 median=891.0 p90=2402.3 max=12946
- wall_total_s per task: mean=12.5 p90=23.1 max=97.2
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.571, 2: 0.4, 3: 0.833, 4: 0.611, 5: 0.5, 6: 0.333, 7: 0.345}
- runaway tax (turn_cap + exec_timeout): n=17 share=0.120 wall_share=0.208

## Pairwise comparisons (acc_strict, on the intersection of graded ids)

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs Qwen3.8-27B-mlx-uniform-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 Qwen3.8-27B-mlx-uniform-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.592 Qwen3.8-27B-mlx-uniform-4bit=0.592
- paired delta = 0.000 95% CI [-0.056, 0.056] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=8 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=8 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) p=1.0000 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 8 (['std-002-1', 'std-004-0', 'std-004-17', 'std-006-5', 'std-007-20', 'std-007-34', 'std-007-37', 'std-007-76']); Qwen3.8-27B-mlx-uniform-4bit only solves 8 (['std-001-5', 'std-005-0', 'std-006-3', 'std-006-7', 'std-007-11', 'std-007-32', 'std-007-36', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs Ornith-1.0-35B-mlx-uniform-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 Ornith-1.0-35B-mlx-uniform-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.592 Ornith-1.0-35B-mlx-uniform-4bit=0.535
- paired delta = 0.056 95% CI [-0.014, 0.134] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=18 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=10 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) p=0.1849 (Holm-adjusted: 0.8432)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 18 (['std-001-3', 'std-001-4', 'std-002-1', 'std-002-3', 'std-002-4', 'std-004-0', 'std-004-1', 'std-004-16', 'std-005-2', 'std-005-7']); Ornith-1.0-35B-mlx-uniform-4bit only solves 10 (['std-001-5', 'std-006-7', 'std-007-11', 'std-007-2', 'std-007-22', 'std-007-32', 'std-007-33', 'std-007-36', 'std-007-67', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.592 Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.620
- paired delta = -0.028 95% CI [-0.092, 0.028] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=7 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=11 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) p=0.4807 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 7 (['std-004-0', 'std-006-6', 'std-007-28', 'std-007-38', 'std-007-48', 'std-007-68', 'std-007-87']); Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 11 (['std-001-5', 'std-001-6', 'std-004-3', 'std-005-1', 'std-006-1', 'std-006-3', 'std-007-22', 'std-007-32', 'std-007-41', 'std-007-67'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.592 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.423
- paired delta = 0.169 95% CI [0.092, 0.246] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=30 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=6 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0001 (Holm-adjusted: 0.0006)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 30 (['std-001-3', 'std-001-4', 'std-002-2', 'std-002-3', 'std-002-4', 'std-003-5', 'std-004-0', 'std-004-1', 'std-004-12', 'std-004-16']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 6 (['std-001-6', 'std-007-11', 'std-007-22', 'std-007-25', 'std-007-67', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-mlx-uniform-4bit vs Ornith-1.0-35B-mlx-uniform-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-mlx-uniform-4bit-only, 0 Ornith-1.0-35B-mlx-uniform-4bit-only)
- acc_strict: Qwen3.8-27B-mlx-uniform-4bit=0.592 Ornith-1.0-35B-mlx-uniform-4bit=0.535
- paired delta = 0.056 95% CI [-0.014, 0.127] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=17 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) c=9 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) p=0.1686 (Holm-adjusted: 0.8432)
- exclusive-solve sets: Qwen3.8-27B-mlx-uniform-4bit only solves 17 (['std-001-3', 'std-001-4', 'std-002-3', 'std-002-4', 'std-004-1', 'std-004-16', 'std-005-0', 'std-005-2', 'std-005-7', 'std-005-8']); Ornith-1.0-35B-mlx-uniform-4bit only solves 9 (['std-004-17', 'std-006-5', 'std-007-2', 'std-007-20', 'std-007-22', 'std-007-33', 'std-007-34', 'std-007-67', 'std-007-76'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-mlx-uniform-4bit vs Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-mlx-uniform-4bit-only, 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only)
- acc_strict: Qwen3.8-27B-mlx-uniform-4bit=0.592 Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.620
- paired delta = -0.028 95% CI [-0.099, 0.042] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=11 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) c=15 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) p=0.5572 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-mlx-uniform-4bit only solves 11 (['std-005-0', 'std-006-6', 'std-006-7', 'std-007-11', 'std-007-28', 'std-007-36', 'std-007-38', 'std-007-48', 'std-007-68', 'std-007-73']); Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 15 (['std-001-6', 'std-002-1', 'std-004-17', 'std-004-3', 'std-005-1', 'std-006-1', 'std-006-5', 'std-007-20', 'std-007-22', 'std-007-34'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-mlx-uniform-4bit vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-mlx-uniform-4bit-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Qwen3.8-27B-mlx-uniform-4bit=0.592 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.423
- paired delta = 0.169 95% CI [0.077, 0.261] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=35 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) c=11 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0005 (Holm-adjusted: 0.0043)
- exclusive-solve sets: Qwen3.8-27B-mlx-uniform-4bit only solves 35 (['std-001-3', 'std-001-4', 'std-001-5', 'std-002-2', 'std-002-3', 'std-002-4', 'std-003-5', 'std-004-1', 'std-004-12', 'std-004-16']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 11 (['std-001-6', 'std-002-1', 'std-004-17', 'std-006-5', 'std-007-20', 'std-007-22', 'std-007-25', 'std-007-34', 'std-007-37', 'std-007-67'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Ornith-1.0-35B-mlx-uniform-4bit vs Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- intersection n = 142 (dropped 0 Ornith-1.0-35B-mlx-uniform-4bit-only, 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only)
- acc_strict: Ornith-1.0-35B-mlx-uniform-4bit=0.535 Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.620
- paired delta = -0.085 95% CI [-0.162, -0.007] -- TOST verdict (+-5pp): **b_better**
- exact McNemar: b=10 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) c=22 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) p=0.0501 (Holm-adjusted: 0.3006)
- exclusive-solve sets: Ornith-1.0-35B-mlx-uniform-4bit only solves 10 (['std-006-6', 'std-006-7', 'std-007-11', 'std-007-2', 'std-007-28', 'std-007-33', 'std-007-36', 'std-007-38', 'std-007-68', 'std-007-73']); Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 22 (['std-001-3', 'std-001-4', 'std-001-6', 'std-002-1', 'std-002-3', 'std-002-4', 'std-004-1', 'std-004-16', 'std-004-3', 'std-005-1'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Ornith-1.0-35B-mlx-uniform-4bit vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Ornith-1.0-35B-mlx-uniform-4bit-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Ornith-1.0-35B-mlx-uniform-4bit=0.535 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.423
- paired delta = 0.113 95% CI [0.035, 0.190] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=23 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) c=7 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0052 (Holm-adjusted: 0.0366)
- exclusive-solve sets: Ornith-1.0-35B-mlx-uniform-4bit only solves 23 (['std-001-5', 'std-002-2', 'std-003-5', 'std-004-12', 'std-004-18', 'std-004-7', 'std-006-6', 'std-006-7', 'std-006-8', 'std-007-10']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 7 (['std-001-6', 'std-002-1', 'std-005-2', 'std-005-8', 'std-007-25', 'std-007-37', 'std-007-48'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.6-27B-Opus-Distill-OptiQ-4bit vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.620 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.423
- paired delta = 0.197 95% CI [0.120, 0.275] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=32 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) c=4 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0000 (Holm-adjusted: 0.0000)
- exclusive-solve sets: Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 32 (['std-001-3', 'std-001-4', 'std-001-5', 'std-002-2', 'std-002-3', 'std-002-4', 'std-003-5', 'std-004-1', 'std-004-12', 'std-004-16']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 4 (['std-007-11', 'std-007-25', 'std-007-48', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

