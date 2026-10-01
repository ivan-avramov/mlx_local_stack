# M54 AgentBench OS -- cross-arm comparison

`python -m bench.agentbench_compare --rows Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=$HOME/ws/mlx_local_stack_workdir/m54/arms_b43c8e5/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/agentbench_os.v1.jsonl --rows Qwen3.8-27B-mlx-uniform-4bit=$HOME/ws/mlx_local_stack_workdir/m54/arms_b43c8e5/Qwen3.8-27B-mlx-uniform-4bit/agentbench_os.v1.jsonl --rows Ornith-1.0-35B-mlx-uniform-4bit=$HOME/ws/mlx_local_stack_workdir/m54/arms_b43c8e5/Ornith-1.0-35B-mlx-uniform-4bit/agentbench_os.v1.jsonl --rows Qwen3.6-27B-Opus-Distill-OptiQ-4bit=$HOME/ws/mlx_local_stack_workdir/m54/arms_b43c8e5/Qwen3.6-27B-Opus-Distill-OptiQ-4bit/agentbench_os.v1.jsonl --rows NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=$HOME/ws/mlx_local_stack_workdir/m54/arms_b43c8e5/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit/agentbench_os.v1.jsonl --out $HOME/ws/mlx_local_stack_workdir/m54/arms_b43c8e5/compare_chain1.md`

Bootstrap: iters=10000 seed=0 TOST margin=0.05 (+-5pp); MDE alpha=0.05 power=0.8 p_d=0.2

## The four numbers (per arm)

capability ceiling = acc (raw `passed`, NOT gated by convergence); edit/agent competence = acc_strict (passed AND converged -- the ranking metric, at the named thinking budget); latency per task = wall_total_s; runaway tax = turn_cap + exec_timeout share of n and their share of total wall-clock. NEVER RANK ON TOKENS OR WALL-CLOCK -- reported as plain distributions, never a composite.

| model | n | graded_n | capability ceiling (acc) | acc_strict@budget | wall_total_s mean/p90/max | runaway tax n (share) / wall share |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 142 | 142 | 0.613 | 0.613@81920 | 18.7/36.8/103.8 | 4 (0.028) / 0.094 |
| Qwen3.8-27B-mlx-uniform-4bit | 142 | 142 | 0.620 | 0.620@81920 | 28.3/56.7/310.9 | 8 (0.056) / 0.200 |
| Ornith-1.0-35B-mlx-uniform-4bit | 142 | 142 | 0.556 | 0.549@81920 | 22.0/15.3/1015.0 | 6 (0.042) / 0.018 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 142 | 142 | 0.613 | 0.613@81920 | 35.5/63.9/316.6 | 12 (0.085) / 0.181 |
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | 142 | 142 | 0.415 | 0.415@81920 | 16.6/28.8/141.7 | 19 (0.134) / 0.252 |

## Per-arm detail

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed

- n=142 graded_n=142
- acc (capability ceiling) = 0.613
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.613
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 87, 'failed_tests': 52, 'turn_cap': 3, 'exec_timeout': 1, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=371.5 median=242.0 p90=689.4 max=2450
- wall_total_s per task: mean=18.7 p90=36.8 max=103.8
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.714, 2: 1.0, 3: 1.0, 4: 0.944, 5: 0.6, 6: 0.667, 7: 0.483}
- runaway tax (turn_cap + exec_timeout): n=4 share=0.028 wall_share=0.094

### Qwen3.8-27B-mlx-uniform-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.620
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.620
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 88, 'failed_tests': 46, 'turn_cap': 8, 'exec_timeout': 0, 'shell_died': 0, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=690.9 median=421.5 p90=1478.3 max=8395
- wall_total_s per task: mean=28.3 p90=56.7 max=310.9
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 1.0, 2: 0.8, 3: 1.0, 4: 0.889, 5: 0.7, 6: 0.778, 7: 0.471}
- runaway tax (turn_cap + exec_timeout): n=8 share=0.056 wall_share=0.200

### Ornith-1.0-35B-mlx-uniform-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.556
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.549
- conv_rate = 0.986; nonconv_kinds = {'budget_hit': 2}
- outcome counts: {'solved': 79, 'failed_tests': 57, 'turn_cap': 6, 'exec_timeout': 0, 'shell_died': 2, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=1868.5 median=495.5 p90=1342.4 max=83500
- wall_total_s per task: mean=22.0 p90=15.3 max=1015.0
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.714, 2: 0.4, 3: 1.0, 4: 0.778, 5: 0.3, 6: 0.556, 7: 0.506}
- runaway tax (turn_cap + exec_timeout): n=6 share=0.042 wall_share=0.018

### Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.613
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.613
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 87, 'failed_tests': 43, 'turn_cap': 12, 'exec_timeout': 0, 'shell_died': 2, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=738.4 median=514.5 p90=1374.8 max=7185
- wall_total_s per task: mean=35.5 p90=63.9 max=316.6
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 1.0, 2: 1.0, 3: 1.0, 4: 0.944, 5: 0.7, 6: 0.778, 7: 0.437}
- runaway tax (turn_cap + exec_timeout): n=12 share=0.085 wall_share=0.181

### NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- n=142 graded_n=142
- acc (capability ceiling) = 0.415
- acc_strict@81920 (edit/agent competence, ranking metric) = 0.415
- conv_rate = 1.000; nonconv_kinds = {}
- outcome counts: {'solved': 59, 'failed_tests': 66, 'turn_cap': 17, 'exec_timeout': 2, 'shell_died': 1, 'setup_error': 0, 'harness_error': 0}
- tokens per task: mean=1454.8 median=992.0 p90=2927.1 max=14789
- wall_total_s per task: mean=16.6 p90=28.8 max=141.7
- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): {1: 0.571, 2: 0.4, 3: 0.833, 4: 0.611, 5: 0.5, 6: 0.444, 7: 0.322}
- runaway tax (turn_cap + exec_timeout): n=19 share=0.134 wall_share=0.252

## Pairwise comparisons (acc_strict, on the intersection of graded ids)

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs Qwen3.8-27B-mlx-uniform-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 Qwen3.8-27B-mlx-uniform-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.613 Qwen3.8-27B-mlx-uniform-4bit=0.620
- paired delta = -0.007 95% CI [-0.063, 0.049] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=8 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=9 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) p=1.0000 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 8 (['std-002-1', 'std-004-0', 'std-004-17', 'std-006-5', 'std-007-2', 'std-007-20', 'std-007-37', 'std-007-41']); Qwen3.8-27B-mlx-uniform-4bit only solves 9 (['std-001-5', 'std-001-6', 'std-004-3', 'std-005-0', 'std-006-3', 'std-006-7', 'std-007-32', 'std-007-50', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs Ornith-1.0-35B-mlx-uniform-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 Ornith-1.0-35B-mlx-uniform-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.613 Ornith-1.0-35B-mlx-uniform-4bit=0.549
- paired delta = 0.063 95% CI [-0.007, 0.134] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=19 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=10 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) p=0.1360 (Holm-adjusted: 0.6802)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 19 (['std-001-2', 'std-002-1', 'std-002-3', 'std-002-4', 'std-004-0', 'std-004-1', 'std-004-16', 'std-005-2', 'std-005-7', 'std-005-8']); Ornith-1.0-35B-mlx-uniform-4bit only solves 10 (['std-001-5', 'std-007-22', 'std-007-25', 'std-007-3', 'std-007-32', 'std-007-33', 'std-007-67', 'std-007-69', 'std-007-72', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.613 Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.613
- paired delta = 0.000 95% CI [-0.063, 0.063] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=11 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=11 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) p=1.0000 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 11 (['std-004-0', 'std-006-6', 'std-007-2', 'std-007-20', 'std-007-36', 'std-007-38', 'std-007-41', 'std-007-48', 'std-007-68', 'std-007-85']); Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 11 (['std-001-5', 'std-001-6', 'std-004-3', 'std-005-1', 'std-006-1', 'std-006-3', 'std-007-32', 'std-007-50', 'std-007-67', 'std-007-72'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed=0.613 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.415
- paired delta = 0.197 95% CI [0.120, 0.275] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=32 (exclusive to Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed) c=4 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0000 (Holm-adjusted: 0.0000)
- exclusive-solve sets: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only solves 32 (['std-001-2', 'std-001-4', 'std-002-2', 'std-002-3', 'std-002-4', 'std-003-5', 'std-004-0', 'std-004-1', 'std-004-12', 'std-004-16']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 4 (['std-001-6', 'std-007-22', 'std-007-67', 'std-007-73'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-mlx-uniform-4bit vs Ornith-1.0-35B-mlx-uniform-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-mlx-uniform-4bit-only, 0 Ornith-1.0-35B-mlx-uniform-4bit-only)
- acc_strict: Qwen3.8-27B-mlx-uniform-4bit=0.620 Ornith-1.0-35B-mlx-uniform-4bit=0.549
- paired delta = 0.070 95% CI [0.000, 0.148] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=20 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) c=10 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) p=0.0987 (Holm-adjusted: 0.5924)
- exclusive-solve sets: Qwen3.8-27B-mlx-uniform-4bit only solves 20 (['std-001-2', 'std-001-6', 'std-002-3', 'std-002-4', 'std-004-1', 'std-004-16', 'std-004-3', 'std-005-0', 'std-005-2', 'std-005-7']); Ornith-1.0-35B-mlx-uniform-4bit only solves 10 (['std-004-17', 'std-006-5', 'std-007-2', 'std-007-22', 'std-007-25', 'std-007-3', 'std-007-33', 'std-007-67', 'std-007-69', 'std-007-72'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-mlx-uniform-4bit vs Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-mlx-uniform-4bit-only, 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only)
- acc_strict: Qwen3.8-27B-mlx-uniform-4bit=0.620 Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.613
- paired delta = 0.007 95% CI [-0.049, 0.063] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=9 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) c=8 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) p=1.0000 (Holm-adjusted: 1.0000)
- exclusive-solve sets: Qwen3.8-27B-mlx-uniform-4bit only solves 9 (['std-005-0', 'std-006-6', 'std-006-7', 'std-007-36', 'std-007-38', 'std-007-48', 'std-007-68', 'std-007-85', 'std-007-87']); Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 8 (['std-002-1', 'std-004-17', 'std-005-1', 'std-006-1', 'std-006-5', 'std-007-37', 'std-007-67', 'std-007-72'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.8-27B-mlx-uniform-4bit vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Qwen3.8-27B-mlx-uniform-4bit-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Qwen3.8-27B-mlx-uniform-4bit=0.620 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.415
- paired delta = 0.204 95% CI [0.120, 0.289] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=35 (exclusive to Qwen3.8-27B-mlx-uniform-4bit) c=6 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0000 (Holm-adjusted: 0.0000)
- exclusive-solve sets: Qwen3.8-27B-mlx-uniform-4bit only solves 35 (['std-001-2', 'std-001-4', 'std-001-5', 'std-002-2', 'std-002-3', 'std-002-4', 'std-003-5', 'std-004-1', 'std-004-12', 'std-004-16']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 6 (['std-002-1', 'std-004-17', 'std-006-5', 'std-007-22', 'std-007-37', 'std-007-67'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Ornith-1.0-35B-mlx-uniform-4bit vs Qwen3.6-27B-Opus-Distill-OptiQ-4bit

- intersection n = 142 (dropped 0 Ornith-1.0-35B-mlx-uniform-4bit-only, 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only)
- acc_strict: Ornith-1.0-35B-mlx-uniform-4bit=0.549 Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.613
- paired delta = -0.063 95% CI [-0.141, 0.014] -- TOST verdict (+-5pp): **inconclusive**
- exact McNemar: b=12 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) c=21 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) p=0.1628 (Holm-adjusted: 0.6802)
- exclusive-solve sets: Ornith-1.0-35B-mlx-uniform-4bit only solves 12 (['std-006-6', 'std-007-2', 'std-007-22', 'std-007-25', 'std-007-3', 'std-007-33', 'std-007-36', 'std-007-38', 'std-007-68', 'std-007-69']); Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 21 (['std-001-2', 'std-001-6', 'std-002-1', 'std-002-3', 'std-002-4', 'std-004-1', 'std-004-16', 'std-004-3', 'std-005-1', 'std-005-2'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Ornith-1.0-35B-mlx-uniform-4bit vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Ornith-1.0-35B-mlx-uniform-4bit-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Ornith-1.0-35B-mlx-uniform-4bit=0.549 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.415
- paired delta = 0.134 95% CI [0.049, 0.218] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=28 (exclusive to Ornith-1.0-35B-mlx-uniform-4bit) c=9 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0026 (Holm-adjusted: 0.0179)
- exclusive-solve sets: Ornith-1.0-35B-mlx-uniform-4bit only solves 28 (['std-001-4', 'std-001-5', 'std-002-2', 'std-003-5', 'std-004-12', 'std-004-18', 'std-004-7', 'std-005-9', 'std-006-2', 'std-007-10']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 9 (['std-001-6', 'std-002-1', 'std-005-2', 'std-005-7', 'std-005-8', 'std-007-11', 'std-007-37', 'std-007-45', 'std-007-48'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

### Qwen3.6-27B-Opus-Distill-OptiQ-4bit vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit

- intersection n = 142 (dropped 0 Qwen3.6-27B-Opus-Distill-OptiQ-4bit-only, 0 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only)
- acc_strict: Qwen3.6-27B-Opus-Distill-OptiQ-4bit=0.613 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit=0.415
- paired delta = 0.197 95% CI [0.120, 0.275] -- TOST verdict (+-5pp): **a_better**
- exact McNemar: b=32 (exclusive to Qwen3.6-27B-Opus-Distill-OptiQ-4bit) c=4 (exclusive to NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit) p=0.0000 (Holm-adjusted: 0.0000)
- exclusive-solve sets: Qwen3.6-27B-Opus-Distill-OptiQ-4bit only solves 32 (['std-001-2', 'std-001-4', 'std-001-5', 'std-002-2', 'std-002-3', 'std-002-4', 'std-003-5', 'std-004-1', 'std-004-12', 'std-004-16']); NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit only solves 4 (['std-006-6', 'std-007-22', 'std-007-48', 'std-007-85'])
- nominal MDE at n=142 (p_d=0.2) = 0.105

