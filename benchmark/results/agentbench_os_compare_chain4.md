# M54 AgentBench OS -- cross-arm comparison

`python -m bench.agentbench_compare --rows Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=$STACK_WORKDIR/m54/arms_aac939b_redo/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/agentbench_os.v1.jsonl --manifest Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=$STACK_WORKDIR/m54/arms_aac939b_redo/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/agentbench_os.v1.manifest.json --rows Qwen3.8-27B-mlx-uniform-4bit=$STACK_WORKDIR/m54/arms_aac939b_redo/Qwen3.8-27B-mlx-uniform-4bit/agentbench_os.v1.jsonl --manifest Qwen3.8-27B-mlx-uniform-4bit=$STACK_WORKDIR/m54/arms_aac939b_redo/Qwen3.8-27B-mlx-uniform-4bit/agentbench_os.v1.manifest.json --rows Ornith-1.0-35B-mlx-uniform-4bit=$STACK_WORKDIR/m54/arms_aac939b/Ornith-1.0-35B-mlx-uniform-4bit/agentbench_os.v1.jsonl --manifest Ornith-1.0-35B-mlx-uniform-4bit=$STACK_WORKDIR/m54/arms_aac939b/Ornith-1.0-35B-mlx-uniform-4bit/agentbench_os.v1.manifest.json --rows Qwen3.6-27B-Opus-Distill-OptiQ-4bit=$STACK_WORKDIR/m54/arms_aac939b/Qwen3.6-27B-Opus-Distill-OptiQ-4bit/agentbench_os.v1.jsonl --manifest Qwen3.6-27B-Opus-Distill-OptiQ-4bit=$STACK_WORKDIR/m54/arms_aac939b/Qwen3.6-27B-Opus-Distill-OptiQ-4bit/agentbench_os.v1.manifest.json --rows NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=$STACK_WORKDIR/m54/arms_aac939b/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit/agentbench_os.v1.jsonl --manifest NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=$STACK_WORKDIR/m54/arms_aac939b/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit/agentbench_os.v1.manifest.json --out $STACK_WORKDIR/m54/compare_chain4.md`

Bootstrap: iters=10000 seed=0 TOST margin=0.05 (+-5pp); MDE alpha=0.05 power=0.8 p_d=0.2

## The four numbers (per arm)

capability ceiling = acc (raw `passed`, NOT gated by convergence); edit/agent competence = acc_strict (passed AND converged -- the ranking metric, at the named thinking budget); latency per task = wall_total_s; runaway tax = turn_cap + exec_timeout share of n and their share of total wall-clock. NEVER RANK ON TOKENS OR WALL-CLOCK -- reported as plain distributions, never a composite.

| model | n | graded_n | capability ceiling (acc) | acc_strict@budget | wall_total_s mean/p90/max | runaway tax n (share) / wall share |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 142 | 142 | 0.620 | 0.620@81920 | 18.5/33.2/145.2 | 2 (0.014) / 0.033 |
| Qwen3.8-27B-mlx-uniform-4bit | 142 | 142 | 0.585 | 0.585@81920 | 29.6/63.6/246.2 | 8 (0.056) / 0.152 |
| Ornith-1.0-35B-mlx-uniform-4bit | 142 | 142 | 0.542 | 0.535@81920 | 14.2/13.3/976.7 | 9 (0.063) / 0.051 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 142 | 142 | 0.613 | 0.613@81920 | 35.5/75.7/290.2 | 16 (0.113) / 0.276 |
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | 142 | 142 | 0.394 | 0.394@81920 | 12.2/23.1/83.0 | 18 (0.127) / 0.224 |

## Per-arm detail

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed

- n=142 graded_n=142
- acc (capability ceiling) = 0.620
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.620
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 88, 'failed_tests': 52, 'turn_cap': 2, 'exec_timeout': 0, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=368.8 median=232.5 p90=694.9 max=3363
- wall_total_s per task: mean=18.5 p90=33.2 max=145.2
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.857, 2: 1.0, 3: 1.0, 4: 0.944, 5: 0.6, 6: 0.667, 7: 0.483}
- runaway tax (turn_cap + exec_timeout): n=2 share=0.014 wall_share=0.033

### Qwen3.8-27B-mlx-uniform-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.585
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.585
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 83, 'failed_tests': 51, 'turn_cap': 8, 'exec_timeout': 0, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=703.6 median=431.0 p90=1574.8 max=6289
- wall_total_s per task: mean=29.6 p90=63.6 max=246.2
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.714, 2: 0.8, 3: 1.0, 4: 0.833, 5: 0.7, 6: 0.778, 7: 0.448}
- runaway tax (turn_cap + exec_timeout): n=8 share=0.056 wall_share=0.152

### Ornith-1.0-35B-mlx-uniform-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.542
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.535
- conv_rate = 0.993; nonconv_kinds = {'budget_hit': 1}
- outcome counts: {'solved': 77, 'failed_tests': 56, 'turn_cap': 9, 'exec_timeout': 0, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=1175 median=532.5 p90=1122.5 max=82351
- wall_total_s per task: mean=14.2 p90=13.3 max=976.7
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.714, 2: 0.4, 3: 1.0, 4: 0.778, 5: 0.3, 6: 0.556, 7: 0.483}
- runaway tax (turn_cap + exec_timeout): n=9 share=0.063 wall_share=0.051

### Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.613
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.613
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 87, 'failed_tests': 39, 'turn_cap': 16, 'exec_timeout': 0, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=769.4 median=531.0 p90=1704.4 max=6770
- wall_total_s per task: mean=35.5 p90=75.7 max=290.2
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.857, 2: 1.0, 3: 1.0, 4: 0.944, 5: 0.7, 6: 0.667, 7: 0.46}
- runaway tax (turn_cap + exec_timeout): n=16 share=0.113 wall_share=0.276

### NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.394
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.394
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 56, 'failed_tests': 70, 'turn_cap': 16, 'exec_timeout': 2, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=1400.8 median=895.0 p90=2918.7 max=11637
- wall_total_s per task: mean=12.2 p90=23.1 max=83.0
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.571, 2: 0.4, 3: 0.833, 4: 0.611, 5: 0.5, 6: 0.111, 7: 0.322}
- runaway tax (turn_cap + exec_timeout): n=18 share=0.127 wall_share=0.224

## Pairwise comparisons (acc_strict, on the intersection of graded ids)

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs Qwen3.8-27B-mlx-uniform-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 Qwen3.8-27B-mlx-uniform-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.620 Qwen3.8-27B-mlx-uniform-4bit=0.585
- paired delta = 0.035 95% CI [-0.021, 0.092] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=11 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=6 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) p=0.3323 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 11 (['std-001-6', 'std-002-1', 'std-004-0', 'std-004-17', 'std-006-5', 'std-007-11', 'std-007-20', 'std-007-34', 'std-007-37', 'std-007-38']); Qwen3.8-27B-mlx-uniform-4bit only solves 6 (['std-005-0', 'std-006-3', 'std-006-7', 'std-007-32', 'std-007-72', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs Ornith-1.0-35B-mlx-uniform-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 Ornith-1.0-35B-mlx-uniform-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.620 Ornith-1.0-35B-mlx-uniform-4bit=0.535
- paired delta = 0.085 95% CI [0.014, 0.155] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=19 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=7 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) p=0.0290 (Holm-adjusted: 0.1738)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 19 (['std-001-4', 'std-001-6', 'std-002-1', 'std-002-3', 'std-002-4', 'std-004-0', 'std-004-1', 'std-004-16', 'std-005-2', 'std-005-7']); Ornith-1.0-35B-mlx-uniform-4bit only solves 7 (['std-001-5', 'std-007-2', 'std-007-22', 'std-007-32', 'std-007-33', 'std-007-67', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.620 Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.613
- paired delta = 0.007 95% CI [-0.063, 0.070] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=12 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=11 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) p=1.0000 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 12 (['std-001-6', 'std-004-0', 'std-006-0', 'std-006-6', 'std-007-11', 'std-007-27', 'std-007-28', 'std-007-3', 'std-007-36', 'std-007-48']); Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 11 (['std-001-5', 'std-004-3', 'std-005-1', 'std-006-1', 'std-006-3', 'std-007-22', 'std-007-25', 'std-007-32', 'std-007-41', 'std-007-67'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.620 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.394
- paired delta = 0.225 95% CI [0.148, 0.303] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=35 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=3 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0000 (Holm-adjusted: 0.0000)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 35 (['std-001-3', 'std-001-4', 'std-002-2', 'std-002-3', 'std-002-4', 'std-003-5', 'std-004-0', 'std-004-1', 'std-004-12', 'std-004-16']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 3 (['std-007-25', 'std-007-67', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-mlx-uniform-4bit vs Ornith-1.0-35B-mlx-uniform-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-mlx-uniform-4bit-only, 0 Ornith-1.0-35B-mlx-uniform-4bit-only)
- acc_strict: Qwen3.8-27B-mlx-uniform-4bit=0.585 Ornith-1.0-35B-mlx-uniform-4bit=0.535
- paired delta = 0.049 95% CI [-0.021, 0.120] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=18 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) c=11 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) p=0.2649 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-mlx-uniform-4bit only solves 18 (['std-001-4', 'std-002-3', 'std-002-4', 'std-004-1', 'std-004-16', 'std-005-0', 'std-005-2', 'std-005-7', 'std-005-8', 'std-006-0']); Ornith-1.0-35B-mlx-uniform-4bit only solves 11 (['std-001-5', 'std-004-17', 'std-006-5', 'std-007-2', 'std-007-20', 'std-007-22', 'std-007-33', 'std-007-34', 'std-007-38', 'std-007-67'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-mlx-uniform-4bit vs Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-mlx-uniform-4bit-only, 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only)
- acc_strict: Qwen3.8-27B-mlx-uniform-4bit=0.585 Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.613
- paired delta = -0.028 95% CI [-0.099, 0.042] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=12 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) c=16 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) p=0.5716 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-mlx-uniform-4bit only solves 12 (['std-005-0', 'std-006-0', 'std-006-6', 'std-006-7', 'std-007-27', 'std-007-28', 'std-007-3', 'std-007-36', 'std-007-48', 'std-007-68']); Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 16 (['std-001-5', 'std-002-1', 'std-004-17', 'std-004-3', 'std-005-1', 'std-006-1', 'std-006-5', 'std-007-20', 'std-007-22', 'std-007-25'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-mlx-uniform-4bit vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-mlx-uniform-4bit-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Qwen3.8-27B-mlx-uniform-4bit=0.585 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.394
- paired delta = 0.190 95% CI [0.106, 0.275] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=36 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) c=9 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0001 (Holm-adjusted: 0.0005)
- exclusive-solve sets: Qwen3.8-27B-mlx-uniform-4bit only solves 36 (['std-001-3', 'std-001-4', 'std-002-2', 'std-002-3', 'std-002-4', 'std-003-5', 'std-004-1', 'std-004-12', 'std-004-16', 'std-004-18']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 9 (['std-001-6', 'std-002-1', 'std-004-17', 'std-007-11', 'std-007-20', 'std-007-25', 'std-007-34', 'std-007-37', 'std-007-67'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Ornith-1.0-35B-mlx-uniform-4bit vs Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- intersection n = 142 (dropped 0 Ornith-1.0-35B-mlx-uniform-4bit-only, 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only)
- acc_strict: Ornith-1.0-35B-mlx-uniform-4bit=0.535 Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.613
- paired delta = -0.077 95% CI [-0.155, 0.000] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=10 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) c=21 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) p=0.0708 (Holm-adjusted: 0.3538)
- exclusive-solve sets: Ornith-1.0-35B-mlx-uniform-4bit only solves 10 (['std-006-6', 'std-007-2', 'std-007-27', 'std-007-28', 'std-007-3', 'std-007-33', 'std-007-36', 'std-007-68', 'std-007-73', 'std-007-87']); Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 21 (['std-001-4', 'std-002-1', 'std-002-3', 'std-002-4', 'std-004-1', 'std-004-16', 'std-004-3', 'std-005-1', 'std-005-2', 'std-005-7'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Ornith-1.0-35B-mlx-uniform-4bit vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Ornith-1.0-35B-mlx-uniform-4bit-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Ornith-1.0-35B-mlx-uniform-4bit=0.535 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.394
- paired delta = 0.141 95% CI [0.056, 0.225] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=29 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) c=9 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0017 (Holm-adjusted: 0.0116)
- exclusive-solve sets: Ornith-1.0-35B-mlx-uniform-4bit only solves 29 (['std-001-3', 'std-001-5', 'std-002-2', 'std-003-5', 'std-004-12', 'std-004-18', 'std-004-7', 'std-006-2', 'std-006-5', 'std-006-6']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 9 (['std-001-6', 'std-002-1', 'std-005-2', 'std-005-8', 'std-007-11', 'std-007-25', 'std-007-37', 'std-007-47', 'std-007-48'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.6-27B-Opus-Distill-OptiQ-4bit vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.613 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.394
- paired delta = 0.218 95% CI [0.141, 0.303] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=36 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) c=5 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0000 (Holm-adjusted: 0.0000)
- exclusive-solve sets: Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 36 (['std-001-3', 'std-001-4', 'std-001-5', 'std-002-2', 'std-002-3', 'std-002-4', 'std-003-5', 'std-004-1', 'std-004-12', 'std-004-16']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 5 (['std-001-6', 'std-007-11', 'std-007-27', 'std-007-48', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

