# M55 polyglot gap — Rust / Java / JavaScript, C37 22-exercise draws, opencode 1.18.30, draft OFF, deployed sampling

Rule C109: acc is paired PER SESSION (each session = a fresh loaded instance); the pooled rate is DESCRIPTIVE (22 tasks × 2 sessions), no interval. Nominal paired MDE at n=22 ≈ ±27 pp, at n=66 ≈ ±16 pp (p_d=0.2).

## Pass counts per language (s1 / s2 ; pooled descriptive) with stall / loop kills, sandbox rejections, mean wall s

| language | model | s1 | s2 | pooled | stall | loop | rejected | test_modified | wall mean s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rust | `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` | 19 | 19 | 38/44 | 5 | 1 | 0 | 0 | 381 |
| rust | `Qwen3.8-27B-mlx-uniform-4bit` | 15 | 14 | 29/44 | 14 | 0 | 1 | 0 | 422 |
| rust | `Ornith-1.0-35B-mlx-uniform-4bit` | 15 | 17 | 32/44 | 2 | 5 | 5 | 0 | 272 |
| java | `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` | 17 | 17 | 34/44 | 3 | 0 | 17 | 0 | 353 |
| java | `Qwen3.8-27B-mlx-uniform-4bit` | 15 | 12 | 27/44 | 12 | 0 | 11 | 1 | 403 |
| java | `Ornith-1.0-35B-mlx-uniform-4bit` | 11 | 14 | 25/44 | 4 | 0 | 12 | 0 | 196 |
| javascript | `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` | 15 | 19 | 34/44 | 2 | 1 | 7 | 0 | 320 |
| javascript | `Qwen3.8-27B-mlx-uniform-4bit` | 18 | 20 | 38/44 | 5 | 0 | 9 | 0 | 320 |
| javascript | `Ornith-1.0-35B-mlx-uniform-4bit` | 15 | 17 | 32/44 | 1 | 2 | 12 | 0 | 154 |

## Paired deltas vs the first pick, per session (cluster bootstrap 95 % CI, TOST ±5 pp, exact McNemar on discordant pairs)

| language | session | comparator | first pick | comparator | delta pp | 95 % CI | verdict | b:c | McNemar p | first-pick-only solves | comparator-only solves |
|---|---|---|---:|---:|---:|---|---|---|---:|---|---|
| rust | s1 | `Qwen3.8-27B-mlx-uniform-4bit` | 19 | 15 | +18.2 | [+0.0, +36.4] | inconclusive | 5:1 | 0.219 | alphametics, book-store, forth, scale-generator, xorcism | bowling |
| rust | s1 | `Ornith-1.0-35B-mlx-uniform-4bit` | 19 | 15 | +18.2 | [-4.5, +40.9] | inconclusive | 6:2 | 0.289 | dot-dsl, forth, poker, react, two-bucket, xorcism | bowling, fizzy |
| rust | s2 | `Qwen3.8-27B-mlx-uniform-4bit` | 19 | 14 | +22.7 | [+4.5, +40.9] | a_better | 5:0 | 0.062 | book-store, bowling, forth, scale-generator, xorcism | — |
| rust | s2 | `Ornith-1.0-35B-mlx-uniform-4bit` | 19 | 17 | +9.1 | [-13.6, +31.8] | inconclusive | 4:2 | 0.688 | book-store, ocr-numbers, scale-generator, xorcism | alphametics, fizzy |
| java | s1 | `Qwen3.8-27B-mlx-uniform-4bit` | 17 | 15 | +9.1 | [-18.2, +36.4] | inconclusive | 6:4 | 0.754 | bowling, connect, forth, hangman, ledger, poker | dominoes, food-chain, pov, zipper |
| java | s1 | `Ornith-1.0-35B-mlx-uniform-4bit` | 17 | 11 | +27.3 | [+0.0, +54.5] | inconclusive | 8:2 | 0.109 | alphametics, book-store, connect, forth, hangman, ledger, pig-latin, poker | dominoes, zipper |
| java | s2 | `Qwen3.8-27B-mlx-uniform-4bit` | 17 | 12 | +22.7 | [+0.0, +45.5] | inconclusive | 6:1 | 0.125 | alphametics, bowling, connect, dominoes, forth, hangman | book-store |
| java | s2 | `Ornith-1.0-35B-mlx-uniform-4bit` | 17 | 14 | +13.6 | [-9.1, +36.4] | inconclusive | 5:2 | 0.453 | bowling, connect, dominoes, hangman, poker | book-store, ledger |
| javascript | s1 | `Qwen3.8-27B-mlx-uniform-4bit` | 15 | 18 | -13.6 | [-40.9, +13.6] | inconclusive | 3:6 | 0.508 | bowling, connect, grade-school | affine-cipher, book-store, bottle-song, food-chain, go-counting, phone-number |
| javascript | s1 | `Ornith-1.0-35B-mlx-uniform-4bit` | 15 | 15 | +0.0 | [-31.8, +31.8] | inconclusive | 6:6 | 1.000 | bowling, connect, forth, grade-school, pig-latin, react | affine-cipher, book-store, food-chain, go-counting, ledger, phone-number |
| javascript | s2 | `Qwen3.8-27B-mlx-uniform-4bit` | 19 | 20 | -4.5 | [-22.7, +9.1] | inconclusive | 1:2 | 1.000 | alphametics | bowling, food-chain |
| javascript | s2 | `Ornith-1.0-35B-mlx-uniform-4bit` | 19 | 17 | +9.1 | [-13.6, +31.8] | inconclusive | 5:3 | 0.727 | bottle-song, go-counting, poker, react, two-bucket | bowling, food-chain, ledger |
| ALL | s1 | `Qwen3.8-27B-mlx-uniform-4bit` | 51 | 48 | +4.5 | [-9.1, +19.7] | inconclusive | 14:11 | 0.690 | java/bowling, java/connect, java/forth, java/hangman, java/ledger, java/poker, javascript/bowling, javascript/connect, javascript/grade-school, rust/alphametics, rust/book-store, rust/forth, rust/scale-generator, rust/xorcism | java/dominoes, java/food-chain, java/pov, java/zipper, javascript/affine-cipher, javascript/book-store, javascript/bottle-song, javascript/food-chain, javascript/go-counting, javascript/phone-number, rust/bowling |
| ALL | s1 | `Ornith-1.0-35B-mlx-uniform-4bit` | 51 | 41 | +15.2 | [+0.0, +30.3] | inconclusive | 20:10 | 0.099 | java/alphametics, java/book-store, java/connect, java/forth, java/hangman, java/ledger, java/pig-latin, java/poker, javascript/bowling, javascript/connect, javascript/forth, javascript/grade-school, javascript/pig-latin, javascript/react, rust/dot-dsl, rust/forth, rust/poker, rust/react, rust/two-bucket, rust/xorcism | java/dominoes, java/zipper, javascript/affine-cipher, javascript/book-store, javascript/food-chain, javascript/go-counting, javascript/ledger, javascript/phone-number, rust/bowling, rust/fizzy |
| ALL | s2 | `Qwen3.8-27B-mlx-uniform-4bit` | 55 | 46 | +13.6 | [+3.0, +24.2] | a_better | 12:3 | 0.035 | java/alphametics, java/bowling, java/connect, java/dominoes, java/forth, java/hangman, javascript/alphametics, rust/book-store, rust/bowling, rust/forth, rust/scale-generator, rust/xorcism | java/book-store, javascript/bowling, javascript/food-chain |
| ALL | s2 | `Ornith-1.0-35B-mlx-uniform-4bit` | 55 | 48 | +10.6 | [-3.0, +24.2] | inconclusive | 14:7 | 0.189 | java/bowling, java/connect, java/dominoes, java/hangman, java/poker, javascript/bottle-song, javascript/go-counting, javascript/poker, javascript/react, javascript/two-bucket, rust/book-store, rust/ocr-numbers, rust/scale-generator, rust/xorcism | java/book-store, java/ledger, javascript/bowling, javascript/food-chain, javascript/ledger, rust/alphametics, rust/fizzy |

## Session repeatability (same model, s1 vs s2: discordant items / 22)

| language | model | discordant | s1-only | s2-only |
|---|---|---:|---|---|
| rust | `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` | 2 | alphametics | bowling |
| rust | `Qwen3.8-27B-mlx-uniform-4bit` | 1 | bowling | — |
| rust | `Ornith-1.0-35B-mlx-uniform-4bit` | 8 | book-store, ocr-numbers, scale-generator | dot-dsl, forth, poker, react, two-bucket |
| java | `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` | 4 | book-store, ledger | dominoes, react |
| java | `Qwen3.8-27B-mlx-uniform-4bit` | 7 | alphametics, dominoes, food-chain, pov, zipper | poker, react |
| java | `Ornith-1.0-35B-mlx-uniform-4bit` | 9 | bowling, dominoes, zipper | alphametics, book-store, forth, ledger, pig-latin, react |
| javascript | `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` | 6 | bowling | affine-cipher, book-store, bottle-song, go-counting, phone-number |
| javascript | `Qwen3.8-27B-mlx-uniform-4bit` | 4 | alphametics | bowling, connect, grade-school |
| javascript | `Ornith-1.0-35B-mlx-uniform-4bit` | 8 | go-counting, poker, two-bucket | bowling, connect, forth, grade-school, pig-latin |
