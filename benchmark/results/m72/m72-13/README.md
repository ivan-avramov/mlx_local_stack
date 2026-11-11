# M72 1.3 — real-model acceptance records (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, candidate 3, 2026-11-11)

Candidate 3 of the four-eyes strict run (fork temp commit `83fc3bc8`, mlx-serve `436fee6`, stack arms `b4b7052c` `m72_v1` /
`31625001` `m72_exact`; never pushed). Spec `docs/specs/m72-1.3-tq4-production.md` (v1.1 + errata a / b / c). 140 W every monitor
tick, GPU idle 0 % before each leg.

| criterion | file(s) | result |
|---|---|---|
| A5 memory (prompt 131,072, capacity 262,144 every leg; order X P P X, fresh process, 600 s idles) | `a5-131072-cap262144.json`, `a5-run.log` | production peak delta 7.815 GB ≤ dev 7.015 + layer-63 allowance 0.801 + 0.25 scratch 0.268 = 8.084 GB (production − dev = the native layer's bytes) |
| A6 speed sanity | same | production prefill 262.55 s vs dev 263.65 s (1.004×, bar ≥ 0.97) |
| A7 real values | same, `a4-*.json` `load.r1` | √D · max\|γ\| = 39.5 (limit 16,384); max \|codebook\| 0.169 (limit 1) |
| A4 (a) / (b) / (c) | `a4-exact-8192.json`, `a4-exact-32768.json`, `a4-v1-8192.json` | all pass: mode-off repeat control identical; (a) 256 greedy MTP OFF tokens + logprobs identical; (b) 0.030 ≤ 2 × 0.052 (8K), 0.065 ≤ 2 × 0.076 (32K); (c) `m72_exact` greedy MTP ON = OFF, seeded = mode-absent MTP ON; control mode-absent greedy ON = OFF |
| A6 served smoke (lean router from each arm, `MLX_VLM_CACHE_SESSION_MAX=1`) | `smoke-v1.json`, `smoke-exact.json` | both arms: 32,778-token request with a session header and an 8,023-token request with **no** session header, route counters move (`p2s`, `mma` or `d2_verify`, `d2`, `native:*`), `fallback:*` = 0, router PID unchanged; `Request completed` lines are not in the worker log at its level — the batching path would have counted `fallback:batch_cache` |
| A6 divergence diagnostic (not gated) | `diverge-v1.json`, `diverge-exact.json`, `diverge-compare.json` | 10 seeded prompts 8,757–28,008 tokens, deployed sampling, 1,024 tokens: `m72_v1` vs `m72_exact` first differing token 31–372 (median ≈ 110), 0 / 10 identical |

Superseded (not results; local archive only, `$STACK_WORKDIR/m72/real-s21/a4-*.invalid-unseeded-greedy.json`): the first A4 run
passed no temperature, and `generate_step` resolves `temperature=None` from the checkpoint's generation config, so its "greedy"
rows were unseeded sampling (its own mode-off repeat differed at token 1). `real-chain.log` / `real-steps.log` contain that run's
lines before "BEGIN a4 rerun"; the instrument now passes `temperature=0.0` and carries the repeat control.
