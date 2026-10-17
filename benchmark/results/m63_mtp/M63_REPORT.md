# M63 report — MTP-ON vs predictor-OFF on the tg1 agentic axis (both picks, k=2)

## Per leg, acc_strict@budget

| model | lang | session | ON | OFF | ON nonconv | OFF nonconv | ON wall h | OFF wall h | ON out tokens | OFF out tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | 22/22 | 22/22 | — | — | 0.68 | 1.02 | 83209 | 83611 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | 21/21 | 20/21 | — | ['client_inactivity'] | 0.92 | 2.73 | 120930 | 129792 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | 21/22 | 21/22 | ['looping'] | ['client_inactivity'] | 0.53 | 1.90 | 64300 | 68687 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | 21/21 | 21/21 | — | — | 0.94 | 1.35 | 119210 | 105128 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | 22/22 | 20/22 | — | ['client_inactivity'] | 1.70 | 3.36 | 206717 | 114181 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | 20/21 | 21/21 | ['stalled'] | — | 2.45 | 2.40 | 280308 | 201229 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | 21/22 | 21/22 | ['looping'] | ['looping'] | 1.13 | 2.18 | 147117 | 183420 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | 21/21 | 21/21 | — | — | 1.58 | 2.44 | 198785 | 203460 |

## Paired ON−OFF (pre-registered)


### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed, s1: all rows

| comparison | n | ON−OFF | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| go | 21 | +0.048 | [+0.00, +0.14] | wash (MDE 27 pp; directional: ON (not a shown difference)) | 0.27 | 0.191 | 0.383 |

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed, s2: all rows

| comparison | n | ON−OFF | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | +0.000 | [-0.14, +0.14] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

### Qwen3.8-27B-mlx-uniform-4bit, s1: all rows

| comparison | n | ON−OFF | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | +0.091 | [+0.00, +0.23] | wash (MDE 27 pp; directional: ON (not a shown difference)) | 0.27 | 0.117 | 0.234 |
| go | 21 | -0.048 | [-0.14, +0.00] | wash (MDE 27 pp; directional: OFF (not a shown difference)) | 0.27 | 0.191 | 0.234 |

### Qwen3.8-27B-mlx-uniform-4bit, s2: all rows

| comparison | n | ON−OFF | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | +0.000 | [-0.14, +0.14] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed, s1: excluding client_inactivity items (dropped ['go/alphametics'])

| comparison | n | ON−OFF | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| go | 20 | +0.000 | [+0.00, +0.00] | wash (MDE 28 pp; directional: tie) | 0.28 | 1.000 | 1.000 |

### Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed, s2: excluding client_inactivity items (dropped ['python/book-store'])

| comparison | n | ON−OFF | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 21 | -0.048 | [-0.14, +0.00] | wash (MDE 27 pp; directional: OFF (not a shown difference)) | 0.27 | 0.191 | 0.383 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

### Qwen3.8-27B-mlx-uniform-4bit, s1: excluding client_inactivity items (dropped ['python/book-store', 'python/paasio'])

| comparison | n | ON−OFF | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 20 | +0.000 | [+0.00, +0.00] | wash (MDE 28 pp; directional: tie) | 0.28 | 1.000 | 1.000 |
| go | 21 | -0.048 | [-0.14, +0.00] | wash (MDE 27 pp; directional: OFF (not a shown difference)) | 0.27 | 0.191 | 0.383 |

### Qwen3.8-27B-mlx-uniform-4bit, s2: excluding client_inactivity items (dropped none)

| comparison | n | ON−OFF | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | +0.000 | [-0.14, +0.14] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

## P293: ON outcome of every OFF client_inactivity item

| model | session | item | OFF | ON kind | ON passed | ON wall s | ON output tokens |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | python/book-store | client_inactivity | converged | True | 149 | 5999 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s1 | go/alphametics | client_inactivity | converged | True | 181 | 6455 |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | python/book-store | client_inactivity | converged | True | 549 | 21143 |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | python/paasio | client_inactivity | converged | True | 553 | 17800 |

## Discordant items (strict)

| model | session | item | ON | OFF | ON kind | OFF kind |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s1 | go/alphametics | 1 | 0 | — | client_inactivity |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | python/book-store | 1 | 0 | — | client_inactivity |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | python/react | 0 | 1 | looping | — |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | python/book-store | 1 | 0 | — | client_inactivity |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | python/paasio | 1 | 0 | — | client_inactivity |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | go/alphametics | 0 | 1 | stalled | — |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | python/beer-song | 1 | 0 | — | looping |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | python/poker | 0 | 1 | looping | — |

## Reload control (pick 1, fresh instance, s1 seed)

- ON: reload strict 5/5; agreement with s1 on the same items 5/5
- OFF: reload strict 5/5; agreement with s1 on the same items 5/5

## Session totals (descriptive; runaway tax in tokens, C71)

| model | session | ON strict | OFF strict | ON wall h | OFF wall h | speed-up | ON output tokens | OFF output tokens |
|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s1 | 43/43 | 42/43 | 1.60 | 3.75 | 2.35× | 204139 | 213403 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | 42/43 | 42/43 | 1.47 | 3.24 | 2.21× | 183510 | 173815 |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | 42/43 | 41/43 | 4.16 | 5.76 | 1.39× | 487025 | 315410 |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | 42/43 | 42/43 | 2.71 | 4.62 | 1.71× | 345902 | 386880 |

Output tokens are charged (completed requests); OFF `client_inactivity` requests streamed ≈ 70–79K uncharged tokens each (C154).
