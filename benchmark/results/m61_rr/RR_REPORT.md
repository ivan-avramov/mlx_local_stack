# M61 C139(b) re-record report — opencode-v2-web, 48K first-write allowance, audited web

## Per leg (answer_key.report_rows; acc_strict@budget = pass AND converged)

| model | lang | session | acc_strict | 95% CI | nonconv kinds | cheat attempts | reruns | provisional | web fetches | mean wall s | window s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | 22/22 = 1.000 | [1.00, 1.00] | {'converged': 22} | 0 | 0 | False | 0 | 259 | 1984 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | 21/22 = 0.955 | [0.86, 1.00] | {'converged': 21, 'stalled': 1} | 0 | 0 | False | 0 | 253 | 1984 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | 21/22 = 0.955 | [0.86, 1.00] | {'converged': 22} | 0 | 0 | False | 0 | 306 | 1984 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | 22/22 = 1.000 | [1.00, 1.00] | {'converged': 22} | 0 | 0 | False | 0 | 318 | 1984 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | 22/22 = 1.000 | [1.00, 1.00] | {'converged': 22} | 0 | 0 | False | 0 | 366 | 1890 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | 22/22 = 1.000 | [1.00, 1.00] | {'converged': 22} | 0 | 0 | False | 0 | 303 | 1890 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | 21/22 = 0.955 | [0.86, 1.00] | {'converged': 21, 'stalled': 1} | 0 | 0 | False | 0 | 436 | 1890 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | 19/22 = 0.864 | [0.73, 1.00] | {'converged': 19, 'stalled': 3} | 0 | 0 | False | 0 | 598 | 1890 |

## Per-item consistency across sessions

- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python: discordant ['python/book-store']; missed in both []
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go: discordant ['go/counter']; missed in both []
- Qwen3.8-27B-mlx-uniform-4bit python: discordant []; missed in both []
- Qwen3.8-27B-mlx-uniform-4bit go: discordant ['go/book-store', 'go/kindergarten-garden']; missed in both ['go/alphametics']

## Head-to-head s1: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | +0.000 | [+0.00, +0.00] | equivalent | 0.27 | 1.000 | 1.000 |
| go | 22 | +0.000 | [-0.14, +0.14] | inconclusive | 0.27 | 1.000 | 1.000 |

## Head-to-head s2: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | -0.045 | [-0.14, +0.00] | inconclusive | 0.27 | 0.191 | 0.191 |
| go | 22 | +0.136 | [+0.00, +0.27] | inconclusive | 0.27 | 0.050 | 0.100 |

## Sensitivity: go/counter excluded (C145 proposal)

- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go s1: 21/21
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go s2: 21/21
- Qwen3.8-27B-mlx-uniform-4bit go s1: 20/21
- Qwen3.8-27B-mlx-uniform-4bit go s2: 18/21

## Sensitivity head-to-head s1 go, go/counter excluded: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| go | 21 | +0.048 | [+0.00, +0.14] | inconclusive | 0.27 | 0.191 | 0.191 |

## Sensitivity head-to-head s2 go, go/counter excluded: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| go | 21 | +0.143 | [+0.00, +0.29] | inconclusive | 0.27 | 0.050 | 0.050 |

## DESCRIPTIVE: M61 re-record s1 minus M59 s1 (same seeds; scaffold opencode-v2-web 48K vs opencode-v2 16K — never pooled)

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 22 | +0.045 | [+0.00, +0.14] | inconclusive | 0.27 | 0.191 | 0.383 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 22 | +0.045 | [+0.00, +0.14] | inconclusive | 0.27 | 0.191 | 0.383 |
| Qwen3.8-27B-mlx-uniform-4bit python | 22 | +0.091 | [+0.00, +0.23] | inconclusive | 0.27 | 0.117 | 0.351 |
| Qwen3.8-27B-mlx-uniform-4bit go | 22 | +0.136 | [+0.00, +0.27] | inconclusive | 0.27 | 0.050 | 0.200 |

## DESCRIPTIVE: M61 re-record s2 minus M59 s2 (same seeds; scaffold opencode-v2-web 48K vs opencode-v2 16K — never pooled)

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 22 | +0.045 | [-0.09, +0.18] | inconclusive | 0.27 | 0.514 | 1.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 22 | +0.091 | [+0.00, +0.23] | inconclusive | 0.27 | 0.117 | 0.468 |
| Qwen3.8-27B-mlx-uniform-4bit python | 22 | +0.091 | [+0.00, +0.23] | inconclusive | 0.27 | 0.117 | 0.468 |
| Qwen3.8-27B-mlx-uniform-4bit go | 22 | +0.045 | [-0.14, +0.23] | inconclusive | 0.27 | 0.624 | 1.000 |

## Misses (all legs)

| model | lang | session | item | kind | wall s | turns | output tokens | tool calls | error calls | repeated identical | max identical run | web | test_modified |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | python/book-store | stalled | 1988 | 3 | 186 | 3 | 0 | 0 | 1 | 0 | False |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | go/counter | fail | 485 | 9 | 10528 | 16 | 0 | 0 | 1 | 0 | True |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | go/alphametics | stalled | 1893 | 4 | 324 | 5 | 0 | 0 | 1 | 0 | False |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | go/alphametics | stalled | 1893 | 4 | 393 | 6 | 0 | 0 | 1 | 0 | False |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | go/book-store | stalled | 1893 | 13 | 37550 | 15 | 5 | 0 | 1 | 0 | False |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | go/kindergarten-garden | stalled | 1893 | 367 | 23592 | 368 | 0 | 358 | 359 | 0 | False |

## Runaway tax per session (descriptive, no interval)

| model | session | stalled | budget-hit | turn-cap | exec-timeout | dedup union / 44 | leg wall h |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s1 | 0 | 0 | 0 | 0 | 0 | 3.5 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | 1 | 0 | 0 | 0 | 1 | 3.5 |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | 1 | 0 | 0 | 0 | 1 | 4.9 |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | 3 | 0 | 0 | 0 | 3 | 5.5 |
