# c144-base report — both picks re-recorded on probe d4319705 (opencode-v2-web-tg1, predictor OFF, k=2 + reload)

Scaffold `opencode-v2-web-tg1`, opencode 2.0.20, probe sha `d4319705…`, box `m5max-128`; s1 2026-10-15 (attempt 1), s2 + reload 2026-10-16 (attempt 2 after a guard-residual abort; attempt 1 archived with a sha256 manifest), rc 0, every leg validated. Status (C165): descriptive / power-input evidence, not the M64 baseline. acc_strict@budget = pass AND converged (any nonconv kind fails strict). `client_inactivity` = opencode 2.0.20's 60-min single-request interrupt (C154).

## Per leg (answer_key.report_rows, inline web audit)

| model | lang | session | acc_strict | 95% CI | lenient | nonconv kinds | web fetches | answer-key contact | audit incomplete | provisional | mean wall s | leg wall h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | 21/22 = 0.955 | [0.86, 1.00] | 22/22 | {'converged': 21, 'stalled': 1} | 1 | 0 | 0 | False | 265 | 1.6 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | 21/22 = 0.955 | [0.86, 1.00] | 21/22 | {'converged': 21, 'looping': 1} | 0 | 0 | 0 | False | 225 | 1.4 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s1 | 21/21 = 1.000 | [1.00, 1.00] | 21/21 | {'converged': 21} | 0 | 0 | 0 | False | 236 | 1.4 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | go | s2 | 21/21 = 1.000 | [1.00, 1.00] | 21/21 | {'converged': 21} | 0 | 0 | 0 | False | 282 | 1.6 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s1 | 22/22 = 1.000 | [1.00, 1.00] | 22/22 | {'converged': 22} | 0 | 0 | 0 | False | 288 | 1.8 |
| Qwen3.8-27B-mlx-uniform-4bit | python | s2 | 22/22 = 1.000 | [1.00, 1.00] | 22/22 | {'converged': 22} | 0 | 0 | 0 | False | 297 | 1.8 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s1 | 21/21 = 1.000 | [1.00, 1.00] | 21/21 | {'converged': 21} | 0 | 0 | 0 | False | 388 | 2.3 |
| Qwen3.8-27B-mlx-uniform-4bit | go | s2 | 21/21 = 1.000 | [1.00, 1.00] | 21/21 | {'converged': 21} | 0 | 0 | 0 | False | 487 | 2.8 |

## Per-item consistency across sessions

- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python: discordant ['python/grade-school', 'python/poker']; missed in both []
- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go: discordant []; missed in both []
- Qwen3.8-27B-mlx-uniform-4bit python: discordant []; missed in both []
- Qwen3.8-27B-mlx-uniform-4bit go: discordant []; missed in both []

## Head-to-head s1: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | -0.045 | [-0.14, +0.00] | wash (MDE 27 pp; directional: Qwen3.8-27B-mlx-uniform-4bit (not a shown difference)) | 0.27 | 0.191 | 0.383 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

## Head-to-head s2: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed minus Qwen3.8-27B-mlx-uniform-4bit

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | -0.045 | [-0.14, +0.00] | wash (MDE 27 pp; directional: Qwen3.8-27B-mlx-uniform-4bit (not a shown difference)) | 0.27 | 0.191 | 0.383 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

## C154 sensitivity s1: head-to-head excluding items where either pick ended client_inactivity (dropped none)

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | -0.045 | [-0.14, +0.00] | wash (MDE 27 pp; directional: Qwen3.8-27B-mlx-uniform-4bit (not a shown difference)) | 0.27 | 0.191 | 0.383 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

## C154 sensitivity s2: head-to-head excluding items where either pick ended client_inactivity (dropped none)

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| python | 22 | -0.045 | [-0.14, +0.00] | wash (MDE 27 pp; directional: Qwen3.8-27B-mlx-uniform-4bit (not a shown difference)) | 0.27 | 0.191 | 0.383 |
| go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

## Reload control (pick 1, fresh instance, s1 seed, the s1 pilot items)

- 5 items ['python/beer-song', 'python/book-store', 'python/dominoes', 'python/grep', 'python/pig-latin']; reload strict 5/5, s1 strict on the same items 5/5; agreement 5/5

## DESCRIPTIVE replication: c144-base s1 minus P223 s1 (same scaffold and seeds; probe d4319705 vs 8d1b4c84 — never pooled)

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 22 | -0.045 | [-0.14, +0.00] | wash (MDE 27 pp; directional: P223 (not a shown difference)) | 0.27 | 0.191 | 0.574 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 21 | +0.048 | [+0.00, +0.14] | wash (MDE 27 pp; directional: c144-base (not a shown difference)) | 0.27 | 0.191 | 0.574 |
| Qwen3.8-27B-mlx-uniform-4bit python | 22 | +0.091 | [+0.00, +0.23] | wash (MDE 27 pp; directional: c144-base (not a shown difference)) | 0.27 | 0.117 | 0.468 |
| Qwen3.8-27B-mlx-uniform-4bit go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

## DESCRIPTIVE replication: c144-base s2 minus P223 s2 (same scaffold and seeds; probe d4319705 vs 8d1b4c84 — never pooled)

| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python | 22 | +0.000 | [-0.14, +0.14] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |
| Qwen3.8-27B-mlx-uniform-4bit python | 22 | +0.045 | [+0.00, +0.14] | wash (MDE 27 pp; directional: c144-base (not a shown difference)) | 0.27 | 0.191 | 0.765 |
| Qwen3.8-27B-mlx-uniform-4bit go | 21 | +0.000 | [+0.00, +0.00] | wash (MDE 27 pp; directional: tie) | 0.27 | 1.000 | 1.000 |

## Paired discordance (input to the M64 power simulation)

- s1 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python: c144-base vs P223 discordant ['python/grade-school'] of 22
- s1 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go: c144-base vs P223 discordant ['go/alphametics'] of 21
- s1 Qwen3.8-27B-mlx-uniform-4bit python: c144-base vs P223 discordant ['python/book-store', 'python/paasio'] of 22
- s1 Qwen3.8-27B-mlx-uniform-4bit go: c144-base vs P223 discordant [] of 21
- s2 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python: c144-base vs P223 discordant ['python/book-store', 'python/poker'] of 22
- s2 Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed go: c144-base vs P223 discordant [] of 21
- s2 Qwen3.8-27B-mlx-uniform-4bit python: c144-base vs P223 discordant ['python/beer-song'] of 22
- s2 Qwen3.8-27B-mlx-uniform-4bit go: c144-base vs P223 discordant [] of 21
- s1 python: pick 1 vs pick 2 discordant ['python/grade-school'] of 22
- s1 go: pick 1 vs pick 2 discordant [] of 21
- s2 python: pick 1 vs pick 2 discordant ['python/poker'] of 22
- s2 go: pick 1 vs pick 2 discordant [] of 21

## Misses (all legs, all sessions, reload included)

| model | lang | session | item | kind | passed (lenient) | wall s | requests | output tokens charged | uncharged reasoning chars | uncharged streamed s | max identical run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s1 | python/grade-school | stalled | True | 437 | 45 | 9706 |  |  | 1 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | python | s2 | python/poker | looping | False | 208 | 22 | 4291 |  |  | 8 |

## Runaway tax per session (descriptive, no interval)

| model | session | client_inactivity | looping | stalled | hard_ceiling | exec_timeout | budget_hit (flag) | dedup union / 43 | session wall h |
|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s1 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 3.0 |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | s2 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 3.0 |
| Qwen3.8-27B-mlx-uniform-4bit | s1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4.0 |
| Qwen3.8-27B-mlx-uniform-4bit | s2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4.7 |

## Web fetches (inline audit)

- Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed python s1 python/connect: {"url": "https://raw.githubusercontent.com/exercism/problem-specifications/main/exercises/connect/canonical-data.json", "status": "denied", "error": {"message": "Permission denied: webfetch"}, "path":
