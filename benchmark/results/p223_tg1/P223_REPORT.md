# P223 tg1 re-record report — opencode-v2-web-tg1 (token/turn gate), predictor OFF, k=2 + reload control

Scaffold `opencode-v2-web-tg1`, opencode 2.0.20, probe sha `8d1b4c84…`, box `m5max-128`, chain 2026-10-12T18:16Z → 2026-10-13T12:40Z, rc 0, every leg validated. acc_strict@budget = pass AND converged (any nonconv kind fails strict). `client_inactivity` = opencode 2.0.20's 60-min single-request interrupt (C154).

## Per leg (answer_key.report_rows, inline web audit)

| model | lang | session | acc_strict | 95% CI | lenient | nonconv kinds | web fetches | answer-key contact | audit incomplete | provisional | mean wall s | leg wall h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | 22/22 = 1.000 | [1.00, 1.00] | 22/22 | {'converged': 22} | 1 | 0 | 0 | False | 167 | 1.0 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | 21/22 = 0.955 | [0.86, 1.00] | 21/22 | {'converged': 21, 'client_inactivity': 1} | 0 | 0 | 0 | False | 310 | 1.9 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | 20/21 = 0.952 | [0.86, 1.00] | 20/21 | {'client_inactivity': 1, 'converged': 20} | 0 | 0 | 0 | False | 468 | 2.7 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | 21/21 = 1.000 | [1.00, 1.00] | 21/21 | {'converged': 21} | 0 | 0 | 0 | False | 231 | 1.3 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | 20/22 = 0.909 | [0.77, 1.00] | 20/22 | {'converged': 20, 'client_inactivity': 2} | 2 | 0 | 0 | False | 551 | 3.4 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | 21/22 = 0.955 | [0.86, 1.00] | 22/22 | {'converged': 21, 'looping': 1} | 0 | 0 | 0 | False | 357 | 2.2 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | 21/21 = 1.000 | [1.00, 1.00] | 21/21 | {'converged': 21} | 0 | 0 | 0 | False | 411 | 2.4 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | 21/21 = 1.000 | [1.00, 1.00] | 21/21 | {'converged': 21} | 0 | 0 | 0 | False | 418 | 2.4 |

## Per-item consistency across sessions

- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python: discordant ['python/book-store']; missed in both []
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go: discordant ['go/alphametics']; missed in both []
- Qwen3.8-27B-mlx-uniform-4bit python: discordant ['python/beer-song', 'python/book-store', 'python/paasio']; missed in both []
- Qwen3.8-27B-mlx-uniform-4bit go: discordant []; missed in both []

## Head-to-head s1: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | +0.091 | [+0.00, +0.23] | wash (MDE 27 pp; directional: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed (not a shown difference)) | 0.27 | 0.117 | 0.234 |
| go | 21 | -0.048 | [-0.14, +0.00] | wash (MDE 27 pp; directional: Qwen3.8-27B-mlx-uniform-4bit (not a shown difference)) | 0.27 | 0.191 | 0.234 |

## Head-to-head s2: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | +0.000 | [-0.14, +0.14] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

## C154 sensitivity s1: head-to-head excluding items where either pick ended client_inactivity (dropped ['python/book-store', 'python/paasio', 'go/alphametics'])

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 20 | +0.000 | [+0.00, +0.00] | wash (MDE 28 pp; directional: tie) | 0.28 | 1.000 | 1.000 |
| go | 20 | +0.000 | [+0.00, +0.00] | wash (MDE 28 pp; directional: tie) | 0.28 | 1.000 | 1.000 |

## C154 sensitivity s2: head-to-head excluding items where either pick ended client_inactivity (dropped ['python/book-store'])

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 21 | +0.048 | [+0.00, +0.14] | wash (MDE 27 pp; directional: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed (not a shown difference)) | 0.27 | 0.191 | 0.383 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

## Reload control (pick 1, fresh instance, s1 seed, the s1 pilot items)

- 5 items ['python/beer-song', 'python/book-store', 'python/dominoes', 'python/grep', 'python/pig-latin']; reload strict 5/5, s1 strict on the same items 5/5; agreement 5/5

## DESCRIPTIVE: P223 tg1 s1 minus M61 s1 (same seeds; scaffold opencode-v2-web-tg1 vs opencode-v2-web — never pooled)

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 22 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 21 | -0.048 | [-0.14, +0.00] | wash (MDE 27 pp; directional: M61 (not a shown difference)) | 0.27 | 0.191 | 0.574 |
| Qwen3.8-27B-mlx-uniform-4bit python | 22 | -0.091 | [-0.23, +0.00] | wash (MDE 27 pp; directional: M61 (not a shown difference)) | 0.27 | 0.117 | 0.468 |
| Qwen3.8-27B-mlx-uniform-4bit go | 21 | +0.048 | [+0.00, +0.14] | wash (MDE 27 pp; directional: P223 (not a shown difference)) | 0.27 | 0.191 | 0.574 |

## DESCRIPTIVE: P223 tg1 s2 minus M61 s2 (same seeds; scaffold opencode-v2-web-tg1 vs opencode-v2-web — never pooled)

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 22 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit python | 22 | -0.045 | [-0.14, +0.00] | wash (MDE 27 pp; directional: M61 (not a shown difference)) | 0.27 | 0.191 | 0.574 |
| Qwen3.8-27B-mlx-uniform-4bit go | 21 | +0.143 | [+0.00, +0.29] | wash (MDE 27 pp; directional: P223 (not a shown difference)) | 0.27 | 0.050 | 0.200 |

## Misses (all legs, all sessions, reload included)

| model | lang | session | item | kind | passed (lenient) | wall s | requests | output tokens charged | uncharged reasoning chars | uncharged streamed s | max identical run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | python/book-store | client_inactivity | False | 3661 | 1 | 177 | 130760 | 3648.934 | 1 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | go/alphametics | client_inactivity | False | 3663 | 3 | 322 | 126206 | 3639.97 | 1 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | python/book-store | client_inactivity | False | 3661 | 2 | 191 | 171729 | 3645.503 | 1 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | python/paasio | client_inactivity | False | 3661 | 2 | 261 | 260052 | 3636.015 | 1 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | python/beer-song | looping | True | 352 | 10 | 7889 |  |  | 8 |

## Runaway tax per session (descriptive, no interval)

| model | session | client_inactivity | looping | stalled | hard_ceiling | exec_timeout | budget_hit (flag) | dedup union / 43 | session wall h |
|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 3.8 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 3.2 |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 5.8 |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 4.6 |

## Web fetches (inline audit)

- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python s1 python/go-counting: {"url": "https://raw.githubusercontent.com/exercism/problem-specifications/main/exercises/go-counting/canonical-data.json", "status": "denied", "error": {"message": "Permission denied: webfetch"}, "pa
- Qwen3.8-27B-mlx-uniform-4bit python s1 python/grep: {"url": "https://raw.githubusercontent.com/exercism/problem-specifications/main/exercises/grep/canonical-data.json", "status": "denied", "error": {"message": "Permission denied: webfetch"}, "path": "$
- Qwen3.8-27B-mlx-uniform-4bit python s1 python/go-counting: {"url": "https://raw.githubusercontent.com/exercism/python/main/exercises/practice/go-counting/go_counting.py", "status": "denied", "error": {"message": "Permission denied: webfetch"}, "path": "$STACK
