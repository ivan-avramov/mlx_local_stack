# M59 v2 re-baseline report

## Per (model, language, session) — acc_strict@budget (miss = fail or non-convergence)

| model | lang | arm | n | acc_strict | 95% CI (cluster bootstrap) | nonconv kinds | mean wall s | window s |
|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | 1.18 medium | 22 | 22/22 = 1.000 | [1.00, 1.00] | {'converged': 22} | 226 | 600 (1.18 wall) |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | 22 | 21/22 = 0.955 | [0.86, 1.00] | {'converged': 21, 'stalled': 1} | 184 | 662 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | 22 | 20/22 = 0.909 | [0.77, 1.00] | {'converged': 20, 'stalled': 2} | 264 | 662 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | 1.18 medium | 22 | 22/22 = 1.000 | [1.00, 1.00] | {'converged': 22} | 278 | 600 (1.18 wall) |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | 22 | 20/22 = 0.909 | [0.77, 1.00] | {'converged': 20, 'stalled': 1, 'hard_ceiling': 1} | 407 | 662 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | 22 | 20/22 = 0.909 | [0.77, 1.00] | {'converged': 20, 'stalled': 2} | 269 | 662 |
| Qwen3.8-27B-mlx-uniform-4bit | python | 1.18 medium | 22 | 19/22 = 0.864 | [0.73, 1.00] | {'converged': 19, 'stalled': 3} | 248 | 600 (1.18 wall) |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | 22 | 20/22 = 0.909 | [0.77, 1.00] | {'converged': 20, 'stalled': 2} | 215 | 630 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | 22 | 20/22 = 0.909 | [0.77, 1.00] | {'converged': 20, 'stalled': 2} | 227 | 630 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1@558 (superseded) | 22 | 19/22 = 0.864 | [0.73, 1.00] | {'converged': 19, 'stalled': 3} | 226 | 558 |
| Qwen3.8-27B-mlx-uniform-4bit | go | 1.18 medium | 22 | 16/22 = 0.727 | [0.55, 0.91] | {'stalled': 6, 'converged': 16} | 334 | 600 (1.18 wall) |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | 22 | 18/22 = 0.818 | [0.64, 0.95] | {'stalled': 4, 'converged': 18} | 320 | 630 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | 22 | 18/22 = 0.818 | [0.64, 0.95] | {'converged': 18, 'stalled': 4} | 343 | 630 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1@558 (superseded) | 22 | 17/22 = 0.773 | [0.59, 0.91] | {'converged': 17, 'stalled': 5} | 342 | 558 |

## Per-item consistency across the two v2 sessions (discordant items)

- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python: discordant 1 ['python/poker']; missed in both ['python/paasio']
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go: discordant 4 ['go/alphametics', 'go/book-store', 'go/connect', 'go/counter']; missed in both []
- Qwen3.8-27B-mlx-uniform-4bit python: discordant 0 []; missed in both ['python/book-store', 'python/paasio']
- Qwen3.8-27B-mlx-uniform-4bit go: discordant 4 ['go/alphametics', 'go/bowling', 'go/connect', 'go/markdown']; missed in both ['go/book-store', 'go/ledger']

## Scaffold delta (descriptive, never pooled): v2 s1 minus 1.18 medium

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | p (approx) | Holm-adjusted |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 22 | -0.045 | [-0.14, +0.00] | inconclusive | 0.191 | 0.468 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 22 | -0.091 | [-0.23, +0.00] | inconclusive | 0.117 | 0.468 |
| Qwen3.8-27B-mlx-uniform-4bit python | 22 | +0.045 | [+0.00, +0.14] | inconclusive | 0.191 | 0.468 |
| Qwen3.8-27B-mlx-uniform-4bit go | 22 | +0.091 | [+0.00, +0.23] | inconclusive | 0.117 | 0.468 |

## Scaffold delta (descriptive, never pooled): v2 s2 minus 1.18 medium

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | p (approx) | Holm-adjusted |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 22 | -0.091 | [-0.23, +0.00] | inconclusive | 0.117 | 0.468 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 22 | -0.091 | [-0.23, +0.00] | inconclusive | 0.117 | 0.468 |
| Qwen3.8-27B-mlx-uniform-4bit python | 22 | +0.045 | [+0.00, +0.14] | inconclusive | 0.191 | 0.468 |
| Qwen3.8-27B-mlx-uniform-4bit go | 22 | +0.091 | [-0.09, +0.27] | inconclusive | 0.327 | 0.468 |

## Head-to-head v2 s1: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | p (approx) | Holm-adjusted |
|---|---|---|---|---|---|---|
| python | 22 | +0.045 | [+0.00, +0.14] | inconclusive | 0.191 | 0.383 |
| go | 22 | +0.091 | [-0.09, +0.27] | inconclusive | 0.327 | 0.383 |

## Head-to-head v2 s2: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | p (approx) | Holm-adjusted |
|---|---|---|---|---|---|---|
| python | 22 | +0.000 | [-0.14, +0.14] | inconclusive | 1.000 | 1.000 |
| go | 22 | +0.091 | [+0.00, +0.23] | inconclusive | 0.117 | 0.234 |

## P182 stall re-run (48K-token allowance, same item seeds, one fresh instance per model)

| model | session | item | chain window s | re-run first write s | re-run wall s | output tokens | result | kind |
|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s1 | go/counter | 662 | 118 | 145 | 2946 | pass | variance |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s1 | python/paasio | 662 | 953 | 1012 | 21549 | pass | allowance |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | go/book-store | 662 | 1729 | 1918 | 39142 | pass | allowance |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | go/connect | 662 | 500 | 561 | 12352 | pass | variance |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | python/poker | 662 | 88 | 150 | 3016 | pass | variance |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | python/paasio | 662 | 635 | 686 | 14469 | pass | variance |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | go/bowling | 630 | 582 | 636 | 13853 | pass | variance |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | go/alphametics | 630 | None | 1893 | 324 | stalled | real miss |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | go/book-store | 630 | 936 | 1893 | 39290 | stalled | real miss |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | go/ledger | 630 | 564 | 661 | 14466 | pass | variance |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | python/book-store | 630 | 1214 | 1382 | 30105 | pass | allowance |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | python/paasio | 630 | 1203 | 1267 | 26362 | pass | allowance |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | go/markdown | 630 | 486 | 531 | 12252 | pass | variance |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | go/book-store | 630 | 1073 | 1117 | 24774 | pass | allowance |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | go/connect | 630 | None | 1893 | 389 | stalled | real miss |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | go/ledger | 630 | 887 | 1515 | 31604 | pass | allowance |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | python/book-store | 630 | None | 1893 | 161 | stalled | real miss |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | python/paasio | 630 | 872 | 906 | 19345 | pass | allowance |

### What the gate cost (descriptive; chain rows are unchanged and remain the record)

| model | lang | session | chain acc_strict | + allowance conversions | + variance conversions | still missed |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | 21/22 | +1 -> 22/22 | +0 | 0 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | 20/22 | +0 -> 20/22 | +2 | 0 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | 20/22 | +0 -> 20/22 | +1 | 1 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | 20/22 | +1 -> 21/22 | +1 | 0 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | 20/22 | +2 -> 22/22 | +0 | 0 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | 20/22 | +1 -> 21/22 | +0 | 1 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | 18/22 | +0 -> 18/22 | +2 | 2 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | 18/22 | +2 -> 20/22 | +1 | 1 |

## Flags

- memory-pressure event during Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed s2 python/food-chain (a model-written loop reached 117 GB before P183): row passed=True wall=680.7
- s1 pick-2 arm re-run after observing stalls (adaptive; C136 addendum); the 558 s arm is shown separately and never pooled.
- 1.18 medium rows: opencode 1.18.15, unseeded (C121), wall-clock 600 s stall window, k=1 — the scaffold delta mixes scaffold, seed and gate-policy changes.
