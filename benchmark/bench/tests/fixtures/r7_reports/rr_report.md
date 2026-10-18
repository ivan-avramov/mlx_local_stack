# M61 C139(b) re-record report — opencode-v2-web, 48K first-write allowance, audited web

## Per leg (answer_key.report_rows; acc_strict@budget = pass AND converged)

go/counter excluded (C145); 'as recorded' includes it.

| model | lang | session | acc_strict | 95% CI | as recorded | nonconv kinds | cheat attempts | reruns | provisional | web fetches | mean wall s | window s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | 6/9 = 0.667 | [0.33, 1.00] | 6/9 | {'converged': 9} | 0 | 0 | False | 0 | 128 | 658 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | 6/9 = 0.667 | [0.33, 1.00] | 6/9 | {'converged': 9} | 0 | 0 | False | 0 | 128 | 658 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | 6/9 = 0.667 | [0.33, 1.00] | 6/9 | {'converged': 9} | 0 | 0 | False | 0 | 128 | 658 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | 6/9 = 0.667 | [0.33, 1.00] | 6/9 | {'converged': 9} | 0 | 0 | False | 0 | 128 | 658 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | 6/9 = 0.667 | [0.33, 1.00] | 6/9 | {'converged': 9} | 0 | 0 | False | 0 | 128 | 658 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | 6/9 = 0.667 | [0.33, 1.00] | 6/9 | {'converged': 9} | 0 | 0 | False | 0 | 128 | 658 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | 6/9 = 0.667 | [0.33, 1.00] | 6/9 | {'converged': 9} | 0 | 0 | False | 0 | 128 | 658 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | 6/9 = 0.667 | [0.33, 1.00] | 6/9 | {'converged': 9} | 0 | 0 | False | 0 | 128 | 658 |

## Per-item consistency across sessions

- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python: discordant []; missed in both ['python/item00', 'python/item03', 'python/item06']
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go: discordant []; missed in both ['go/item00', 'go/item03', 'go/item06']
- Qwen3.8-27B-mlx-uniform-4bit python: discordant []; missed in both ['python/item00', 'python/item03', 'python/item06']
- Qwen3.8-27B-mlx-uniform-4bit go: discordant []; missed in both ['go/item00', 'go/item03', 'go/item06']

## Head-to-head s1: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 9 | +0.000 | [+0.00, +0.00] | wash (MDE 42 pp; directional: tie) | 0.42 | 1.000 | 1.000 |
| go | 9 | +0.000 | [+0.00, +0.00] | wash (MDE 42 pp; directional: tie) | 0.42 | 1.000 | 1.000 |

## Head-to-head s2: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 9 | +0.000 | [+0.00, +0.00] | wash (MDE 42 pp; directional: tie) | 0.42 | 1.000 | 1.000 |
| go | 9 | +0.000 | [+0.00, +0.00] | wash (MDE 42 pp; directional: tie) | 0.42 | 1.000 | 1.000 |

## DESCRIPTIVE: M61 re-record s1 minus M59 s1 (same seeds; scaffold opencode-v2-web 48K vs opencode-v2 16K — never pooled)

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 7 | +0.000 | [+0.00, +0.00] | wash (MDE 47 pp; directional: tie) | 0.47 | 1.000 | 1.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 7 | +0.000 | [+0.00, +0.00] | wash (MDE 47 pp; directional: tie) | 0.47 | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit python | 7 | +0.000 | [+0.00, +0.00] | wash (MDE 47 pp; directional: tie) | 0.47 | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit go | 7 | +0.000 | [+0.00, +0.00] | wash (MDE 47 pp; directional: tie) | 0.47 | 1.000 | 1.000 |

## DESCRIPTIVE: M61 re-record s2 minus M59 s2 (same seeds; scaffold opencode-v2-web 48K vs opencode-v2 16K — never pooled)

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 7 | +0.000 | [+0.00, +0.00] | wash (MDE 47 pp; directional: tie) | 0.47 | 1.000 | 1.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 7 | +0.000 | [+0.00, +0.00] | wash (MDE 47 pp; directional: tie) | 0.47 | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit python | 7 | +0.000 | [+0.00, +0.00] | wash (MDE 47 pp; directional: tie) | 0.47 | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit go | 7 | +0.000 | [+0.00, +0.00] | wash (MDE 47 pp; directional: tie) | 0.47 | 1.000 | 1.000 |

## Misses (all legs)

| model | lang | session | item | kind | wall s | turns | output tokens | tool calls | error calls | repeated identical | max identical run | web | test_modified |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | python/item00 | fail | 100 | 4 | 900 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | python/item03 | fail | 121 | 4 | 903 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | python/item06 | fail | 142 | 4 | 906 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | python/item00 | fail | 100 | 4 | 900 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | python/item03 | fail | 121 | 4 | 903 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | python/item06 | fail | 142 | 4 | 906 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | go/item00 | fail | 100 | 4 | 900 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | go/item03 | fail | 121 | 4 | 903 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | go/item06 | fail | 142 | 4 | 906 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | go/item00 | fail | 100 | 4 | 900 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | go/item03 | fail | 121 | 4 | 903 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | go/item06 | fail | 142 | 4 | 906 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | python/item00 | fail | 100 | 4 | 900 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | python/item03 | fail | 121 | 4 | 903 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | python/item06 | fail | 142 | 4 | 906 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | python/item00 | fail | 100 | 4 | 900 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | python/item03 | fail | 121 | 4 | 903 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | python/item06 | fail | 142 | 4 | 906 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | go/item00 | fail | 100 | 4 | 900 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | go/item03 | fail | 121 | 4 | 903 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | go/item06 | fail | 142 | 4 | 906 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | go/item00 | fail | 100 | 4 | 900 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | go/item03 | fail | 121 | 4 | 903 | 3 | 0 | None | None | 0 | None |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | go/item06 | fail | 142 | 4 | 906 | 3 | 0 | None | None | 0 | None |

## Runaway tax per session (descriptive, no interval)

| model | session | stalled | budget-hit | turn-cap | exec-timeout | dedup union / 43 | leg wall h |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s1 | 0 | 0 | 0 | 0 | 0 | 0.6 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | 0 | 0 | 0 | 0 | 0 | 0.6 |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | 0 | 0 | 0 | 0 | 0 | 0.6 |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | 0 | 0 | 0 | 0 | 0 | 0.6 |
