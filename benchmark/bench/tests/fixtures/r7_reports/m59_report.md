# M59 v2 re-baseline report

## Per (model, language, session) — acc_strict@budget (miss = fail or non-convergence)

| model | lang | arm | n | acc_strict | 95% CI (cluster bootstrap) | nonconv kinds | mean wall s | window s |
|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | 1.18 medium | 8 | 5/8 = 0.625 | [0.25, 0.88] | {'converged': 8} | 124 | 600 (1.18 wall) |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | 9 | 6/9 = 0.667 | [0.33, 1.00] | {'converged': 9} | 128 | 630 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | 9 | 6/9 = 0.667 | [0.33, 1.00] | {'converged': 9} | 128 | 630 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | 1.18 medium | 8 | 5/8 = 0.625 | [0.25, 0.88] | {'converged': 8} | 124 | 600 (1.18 wall) |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | 9 | 6/9 = 0.667 | [0.33, 1.00] | {'converged': 9} | 128 | 630 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | 9 | 6/9 = 0.667 | [0.33, 1.00] | {'converged': 9} | 128 | 630 |
| Qwen3.8-27B-mlx-uniform-4bit | python | 1.18 medium | 8 | 5/8 = 0.625 | [0.25, 0.88] | {'converged': 8} | 124 | 600 (1.18 wall) |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | 9 | 6/9 = 0.667 | [0.33, 1.00] | {'converged': 9} | 128 | 630 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | 9 | 6/9 = 0.667 | [0.33, 1.00] | {'converged': 9} | 128 | 630 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1@558 (superseded) | 0 | — | — | — | — | — |
| Qwen3.8-27B-mlx-uniform-4bit | go | 1.18 medium | 8 | 5/8 = 0.625 | [0.25, 0.88] | {'converged': 8} | 124 | 600 (1.18 wall) |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | 9 | 6/9 = 0.667 | [0.33, 1.00] | {'converged': 9} | 128 | 630 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | 9 | 6/9 = 0.667 | [0.33, 1.00] | {'converged': 9} | 128 | 630 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1@558 (superseded) | 0 | — | — | — | — | — |

## Per-item consistency across the two v2 sessions (discordant items)

- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python: discordant 0 []; missed in both ['python/item00', 'python/item03', 'python/item06']
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go: discordant 0 []; missed in both ['go/item00', 'go/item03', 'go/item06']
- Qwen3.8-27B-mlx-uniform-4bit python: discordant 0 []; missed in both ['python/item00', 'python/item03', 'python/item06']
- Qwen3.8-27B-mlx-uniform-4bit go: discordant 0 []; missed in both ['go/item00', 'go/item03', 'go/item06']

## Scaffold delta (descriptive, never pooled): v2 s1 minus 1.18 medium

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | p (approx) | Holm-adjusted |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 8 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 8 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit python | 8 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit go | 8 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |

## Scaffold delta (descriptive, never pooled): v2 s2 minus 1.18 medium

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | p (approx) | Holm-adjusted |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 8 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 8 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit python | 8 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit go | 8 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |

## Head-to-head v2 s1: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | p (approx) | Holm-adjusted |
|---|---|---|---|---|---|---|
| python | 9 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |
| go | 9 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |

## Head-to-head v2 s2: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | p (approx) | Holm-adjusted |
|---|---|---|---|---|---|---|
| python | 9 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |
| go | 9 | +0.000 | [+0.00, +0.00] | wash | 1.000 | 1.000 |

## P182 stall re-run (48K-token allowance, same item seeds, one fresh instance per model)

| model | session | item | chain window s | re-run first write s | re-run wall s | output tokens | result | kind |
|---|---|---|---|---|---|---|---|---|

### What the gate cost (descriptive; chain rows are unchanged and remain the record)

| model | lang | session | chain acc_strict | + allowance conversions | + variance conversions | still missed |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | 6/9 | +0 -> 6/9 | +0 | 3 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | 6/9 | +0 -> 6/9 | +0 | 3 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | 6/9 | +0 -> 6/9 | +0 | 3 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | 6/9 | +0 -> 6/9 | +0 | 3 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | 6/9 | +0 -> 6/9 | +0 | 3 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | 6/9 | +0 -> 6/9 | +0 | 3 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | 6/9 | +0 -> 6/9 | +0 | 3 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | 6/9 | +0 -> 6/9 | +0 | 3 |

## Flags

- memory-pressure event during Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed s2 python/food-chain (a model-written loop reached 117 GB before P183): row passed=None wall=None
- s1 pick-2 arm re-run after observing stalls (adaptive; C136 addendum); the 558 s arm is shown separately and never pooled.
- 1.18 medium rows: opencode 1.18.15, unseeded (C121), wall-clock 600 s stall window, k=1 — the scaffold delta mixes scaffold, seed and gate-policy changes.
