# M76 stage 3b (A8 tg2) — sizing report (generated)

Source: `benchmark/results/m76/wave2.tg2/` (pilot pair, both legs VALID, pilot gate PASS; amendment `7e75cd66…` v8). Generator: `docs/reviews/m76-s3b-sizing/sizing.py`. Per-item walls include the endpoint agent's per-launch overhead (S27-P5); compare them within this pair only.

## Pilot (one item per language per arm)

| language | n16 wall (s) | x wall (s) |
|---|---|---|
| rust | 89 | 80 |
| javascript | 118 | 131 |
| java | 92 | 148 |
| cpp | 80 | 87 |
| **sum** | 379 | 446 |
| leg elapsed (s) | 660 | 720 |
| per-leg overhead (s) | 281 | 274 |

Item wall over both arms: mean 103 s, max 148 s (n = 8). Amendment floors: w_rust 382 s, w_javascript 382 s, w_java 382 s, w_cpp 382 s.

## Projection per arm (hours)

Lower bound = items × mean wall; max-based = items × max pilot wall; tail = mean-based + 5 % of items at the P223 p95 (19.3 min) + one item at the P223 max (61 min). Each adds per leg 281 s overhead (the larger measured) + a 600 s idle gap.

| tier | items / arm | lower (mean) | max-based | with tail | budget M76 §9 / B7.1 joint plan | budget M65 v5 (M55 means) |
|---|---|---|---|---|---|---|
| screen (10 / language, k = 1, C168) | 40 | 1.4 | 1.9 | 3.0 | 12.0 | 18.5 |
| decider (s1 + s2 + reload) | 180 | 5.9 | 8.1 | 9.5 | 12.0 | 18.5 |

The amendment's leg deadlines (a cap, not an estimate): s1 14.25 h, s2 14.25 h, reload 4.70 h — 33.2 h per arm at most.

Caveats: four pilot items per arm (one per language) are a small sample of a heavy-tailed distribution; the tail column carries the P223 allowance for that. Pilot walls N16 vs X are one non-order-balanced pair: no speed claim (S27-P5).
