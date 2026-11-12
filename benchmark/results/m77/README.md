# M77 acceptance criterion 6 — real-model served check (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2026-11-12)

Serving build: stack `0441c805` + a temporary arm commit (local branch `m77-check`, never pushed: X = `0d15947f`, XO = `735bdc35`;
registries from `bench.p475_kv` campaign `f45`), fork `f9bf743f`, mlx-serve `3b02e4c`. Lean router (`MLX_VLM_CACHE_SESSION_MAX=1`,
`APC_ENABLED` absent), one model, 140 W / 28 V, GPU idle 0 % before. Instruments: `benchmark/spikes/m77_served_greedy.py`,
`benchmark/spikes/m72_13_served_smoke.py`.

| check | file | result |
|---|---|---|
| X (TQ4 + `m72_exact`, MTP ON) greedy, 3 prompts each at ≈ 8K / 32K tokens, 256 tokens, + a same-instance repeat each | `greedy-X.json` | mode `m72_exact`; routes `p2s`, `d2_verify`, `native:prefill` / `native:verify` moved, no `fallback:*`; MTP engaged; 6 / 6 repeats identical |
| XO (the same, MTP OFF) loads to READY and serves (M77) | `greedy-XO.json`, `smoke-XO.json` | mode `m72_exact`, no drafter fields; routes `p2s`, `d2`, `native:prefill` / `native:decode`, no `fallback:*`; a 32,853-token request with a session header and an 8,442-token request with none both served on the mode's routes; router PID unchanged |
| greedy XO = greedy X MTP ON (C319's identity, now across configurations) | `m77_served_greedy.py --compare greedy-X.json greedy-XO.json` | **6 / 6 identical**, repeat controls identical |
