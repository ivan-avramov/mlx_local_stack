# P475 — KV-cache format matrix for the two top picks — SPEC v1, 2026-10-24 (four-eyes light; not yet reviewed)

## Goal

Ship `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` and `Qwen3.8-27B-mlx-uniform-4bit` in their ideal KV-cache format. The operator weighs
the choice as a whole tradeoff (memory, prefill speed, decode speed, quality), with no pass line (C218, P475). Today the first serves
native16 KV and the second TurboQuant 4-bit (PROVISIONAL, C202); their numbers come from different dates, code and instruments. Solving
it means: a matched, order-balanced measurement of each candidate format for each pick, taken through the shipped stack (mlx-serve →
mlx-vlm loading a committed `main_models.yaml`, C218), with the format verified engaged, reported as a generated tradeoff table the
operator can decide from — before the P426 Wave 2 spends its GPU hours on a format that might change.

## Settled constraints

- C218 / AGENTS.md: arms are stack commits served as shipped; lean benchmark router (`MLX_VLM_CACHE_SESSION_MAX=1`, no OWUI, `APC_ENABLED`
  absent); one resident model; ≥ 10 min idle between legs; arms order-balanced; 140 W / 28 V / battery > 20 % every tick; a 5-minute
  daemon; transport errors abort; full registry names; anything citable committed.
- Selection uses predictor-OFF (AGENTS.md): the matrix runs MTP OFF (the committed state); the chosen format then gets its ON vs OFF
  certification (P426 process).
- No server code change (one serving build: fork `0f30522c`, mlx-serve `86921f02`).

## Arms (per pick)

| Arm | Registry keys of the entry (everything else unchanged) | Note |
|---|---|---|
| N16 | `kv_bits: 0` | native16 (fused SDPA path) |
| TQ4 | `kv_bits: 4`, `kv_quant_scheme: turboquant` | today's `Qwen3.8-27B-mlx-uniform-4bit` |
| AF8 | `kv_bits: 8`, `kv_quant_scheme: uniform` | affine 8-bit KV (middle ground) |
| TQ4s | `kv_bits: 4`, `kv_quant_scheme: turboquant`, `quantized_kv_start: 131072` | native16 up to 131,072 tokens, quantized beyond |

Each arm is a commit on a local branch `p475-<pick-short>-<arm>` off the P476 commit, changing only that entry's KV keys (and a
`PROVISIONAL P475 arm` comment); checked out in a temporary worktree, removed after its legs are harvested (AGENTS.md). The arm whose
keys equal the committed registry uses the base commit itself.

## Measurement

- Instrument: the existing router-path capacity ladder `bench.run_capacity` (M42 / C82, M50-checked), `--grid 8192,131072,260096`
  (260,096 = 262,144 − the server's 2,048 minimum output), `--sampling-profile deployed`, `--seed 0`, a fresh `--out-tag` per leg; per
  rung: the worker's `peak_memory_gb` (process high-water; rungs ascend, so each rung's reading is that rung's peak), prefill seconds and
  tok/s, decode tok/s over its bounded 256 tokens, and the retrieval co-score (a sanity check, not a quality measure).
- Engagement: the worker argv carries exactly the arm's KV flags, and the worker log's `KV cache resolved` line reports the arm's
  `kv_bits` / scheme / start; a mismatch invalidates the leg (P405 lesson).
- Order: per pick two blocks, block 1 N16 → TQ4 → AF8 → TQ4s, block 2 the reverse; picks sequential; each leg a fresh lean router + load
  from the arm worktree; ≥ 600 s idle before every leg; 16 legs.
- Orchestration (the one new build): `bench.p475_kv` — per leg: pre-check (power, nothing busy, the gate lock C227, destinations absent),
  start the lean router from the arm worktree (`ChainOps.start_router`), verify worker argv + KV log line, an independent `bench_watch`
  bound to the driver pid with a power receipt (C224), run `bench.run_capacity`, stop the stack, receipt (VALID / INVALID, speed valid),
  harvest to `benchmark/results/p475/<leg>/`; stop the run on the first non-VALID leg.
- Estimate: per pick per block ≈ N16 15 min, TQ4 45, AF8 25, TQ4s 25 + 4 × 10 min idle ≈ 2.5 h → ≈ 5 h per pick, ≈ 10 h total (lower
  bounds from Wave-1 M1 and P428; + 30 % allowance).

## Output

A generated table (`benchmark/results/p475/MATRIX.md`, never hand-copied): per pick × arm × rung the two blocks' values and their mean
for peak GB, prefill tok/s and decode tok/s, plus ratios vs N16; labelled descriptive (two order-balanced legs per arm, no interval
claimed). The operator weighs it; a lossy winner then gets its quality study (R6) before adoption; N16 needs none. Then the P426 Wave 2
runs on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`'s chosen format.

## Acceptance criteria

1. `bench.p475_kv` tested (mocked ops, real argv / env / receipts; red first): arm-commit checks, engagement check, ABBA order, idle,
   power / busy / lock refusals, stop on non-VALID, harvest.
2. A smoke leg (N16, grid 8192 only) VALID before the full run.
3. 16 legs VALID (speed-valid or labelled), MATRIX.md generated from the harvested receipts and rows.

## Non-goals

Quality of lossy formats (R6), MTP ON measurements, a fused quantized-KV kernel (P477), other entries.

## Open questions

- Q1: add TurboQuant 6 (`kv_bits: 6`) as a fifth arm (+≈ 1.5 h)? Recommendation: not now — TQ4 and AF8 bracket it; add if they are close.
