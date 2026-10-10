# M58 gate 1 — PASSED 2026-10-06 (UTC 05:51–08:07), `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, fork 664c2ead / router 3f2c87c / stack m58-provenance e4d3652 (merged locally)

Lean router (`MLX_VLM_CACHE_SESSION_MAX=1`, `APC_ENABLED` absent), overlays under `$STACK_WORKDIR/m58/overlays/`.
Live self-test at load: `mtp_verify_scan=joint_v1 self-test: 2 cells in 0.04s` (largest eligible length identical; straddle known positive predicted and observed).

## G1a — same instance, production joint output served, shadow per-query compare (`joint_v1+ab`)
| set | requests | ctx | verify_ab_mismatch | verify_ab_invalid | straddle blocks/mismatch | fallback reasons |
|---|---|---|---|---|---|---|
| seeded pilot (decode_probe, 1536 tokens) | 10 | 8K ×5, 128K ×5 | 0 | 0 | 0/0 | {} |
| straddle probe (prompt T−64, 300-token decode) | 4 | crossings at 1024 / 8192 / 32768 / 65536 | 0 | 0 | 16/16 at every threshold | {} |
| capacity cold rungs | 4 | 8K / 64K / 128K / 256K | 0 | 0 | 0/0 | {} |
| decode_probe 64K/128K ×3 | 6 | 64K, 128K | 0 | 0 | 16/16 on two 64K prompts (crossing 65536 during decode) | {} |
Total 24 requests, ≈ 170K shadow-compared blocks; every predicted straddle mismatched, nothing else did. Peak memory 39.82 GB at 256K (AB mode).

## G1b — cross-load replay (`bench.parity_replay`, C84 frozen set, 20 requests of the first pick)
- control `per_query` → `per_query` (reload): 20/20 identical.
- `per_query` → `joint_v1`: 20/20 identical (content + reasoning digests, finish reason, completion tokens, MTP counters); joint path ran on 20/20 rows (`verify_blocks_joint_v1 > 0`); 0 C120 rows.

Decision: gate 1 PASS → latency arms authorised (spec P94).
