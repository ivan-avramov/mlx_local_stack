# P475 — KV-cache format matrix for the two top picks — SPEC v2, 2026-10-24 (four-eyes light)

v2 applies design review round 1 of 1 (`docs/reviews/p475/design-round1.*`; Cursor `gpt-5.6-sol-high` + `glm-5.2-high`): quality is part
of the decision (stage 2); TQ4s dropped (the server converts the WHOLE cache on crossing `quantized_kv_start` — a between-context switch,
not a native-prefix hybrid — and the cache-manifest validator refuses it); engagement proven by the live per-layer cache manifest, not the
config log line; backend prefill timings, exact-length decode, explicit MTP-OFF proof; AF4 and TQ8 arms added; two speed-valid legs per
arm with an instability rule; grid 8K / 128K / 192K / 256K. Changes after the round are not re-reviewed (light mode).

## Goal

Ship `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` and `Qwen3.8-27B-mlx-uniform-4bit` in their ideal KV-cache format. The operator weighs
the choice as a whole tradeoff (memory, prefill speed, decode speed, quality), with no pass line (C218, P475). Today the first serves
native16 KV and the second TurboQuant 4-bit (PROVISIONAL, C202); their numbers come from different dates, code and instruments. Solving
it means: a matched, order-balanced measurement of each candidate format for each pick, taken through the shipped stack (mlx-serve →
mlx-vlm loading a committed `main_models.yaml`, C218), with the format proven engaged, reported as a generated tradeoff table — and, for
the formats the operator keeps in contention, matched quality evidence — before the P426 Wave 2 spends its GPU hours on a format that
might change.

## Settled constraints

- C218 / AGENTS.md: arms are stack commits served as shipped; lean benchmark router (`MLX_VLM_CACHE_SESSION_MAX=1`, no OWUI, `APC_ENABLED`
  absent); one resident model; ≥ 10 min idle between legs; arms order-balanced; 140 W / 28 V / battery > 20 % every tick; an independent
  5-minute daemon (C224); transport errors abort; full registry names; anything citable committed.
- Selection uses predictor-OFF (AGENTS.md); the chosen format then gets its ON vs OFF certification (P426 process).
- No server code change (one serving build: fork `0f30522c`, mlx-serve `86921f02`).

## Arms (per pick)

| Arm | Registry keys of the entry (everything else unchanged) |
|---|---|
| N16 | `kv_bits: 0` (native16) |
| AF8 | `kv_bits: 8`, `kv_quant_scheme: uniform` (affine 8-bit) |
| TQ8 | `kv_bits: 8`, `kv_quant_scheme: turboquant` |
| AF4 | `kv_bits: 4`, `kv_quant_scheme: uniform` (affine 4-bit; what the historical certifications actually served, P405) |
| TQ4 | `kv_bits: 4`, `kv_quant_scheme: turboquant` (today's `Qwen3.8-27B-mlx-uniform-4bit`) |

`quantized_kv_start` stays 0 in every arm. Each arm is a commit on a local branch `p475-<pick-short>-<arm>` off the P476 commit, changing
only that entry's KV keys (+ a `PROVISIONAL P475 arm` comment); a temporary worktree per arm, removed after its legs are harvested. The
arm equal to the committed registry uses the base commit. Attention differs by pick and is kept as deployed (the first pick ships
`attention_policy: fused_v1`, the second the default): absolute numbers are not compared across picks.

## Stage 1 — memory / speed screen

- **Engagement preflight (per arm, before its first leg):** an in-process known-positive check on the arm's committed registry with the
  fork's per-layer cache-manifest validator (`dev/p369_phase2/kvmanifest`: the exact leaf classes and key / value widths per layer); a
  mismatch refuses the arm. On every router leg the worker argv must carry exactly the arm's KV flags and the worker log's `KV cache
  resolved` line must agree (secondary record).
- **Predictor-OFF proof (every leg):** no `--draft-kind` / `--draft-model` in the worker argv, the manifest's `runtime.draft_kind` null,
  and no draft fields on any request record; otherwise the leg is INVALID.
- **Instrument:** `bench.run_capacity` (M42 / C82, M50-checked) with `--grid 8192,131072,196608,260096` (260,096 = 262,144 − the
  server's 2,048 minimum output), `--sampling-profile deployed`, `--seed 0`, fresh `--out-tag`, extended test-first to:
  - persist and use the backend's own `prompt_ms`, `prompt_per_second`, `prompt_n` and `cache_n` (prefill from the backend, not wall −
    decode); every measured request `cache_n == 0` with a unique session id;
  - a fixed decode carrier per rung that runs to the token cap: exactly 256 completion tokens and `finish_reason == "length"`, else the
    rung is INVALID; decode tok/s from the backend's `predicted_per_second`;
  - memory reported as the worker's cumulative high-water (`peak_memory_gb`, process-lifetime, incl. the full-cap preallocation of the
    first request and the calibration) at each rung — never as a per-rung peak.
- **Order:** per pick two blocks, block 1 N16 → AF8 → TQ8 → AF4 → TQ4, block 2 the reverse; picks sequential, `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
  first, its table delivered as soon as its legs are harvested (P479); each leg a fresh lean router
  + load from the arm worktree; ≥ 600 s idle before every leg; 20 legs.
- **Validity:** every reported arm needs TWO speed-valid legs (power receipt, C224); a speed-invalid or INVALID leg is kept as evidence and
  REPLACED by a rerun. Instability rule: per arm and rung the two blocks' ratios vs N16 are reported side by side; a direction reversal or a
  spread larger than half the ratio's distance from 1.0 triggers a third (deciding) block for that pick.
- **Orchestration (the build):** `bench.p475_kv` — per leg: pre-check (power, nothing busy, the gate lock C227, destinations absent), lean
  router from the arm worktree (`ChainOps.start_router`), argv / KV-line / predictor-OFF checks, the independent `bench_watch` bound to
  the driver pid with a power receipt, `bench.run_capacity`, stack stop, receipt, harvest to `benchmark/results/p475/<leg>/`; stop the
  run on the first INVALID leg (a speed-invalid leg is queued for replacement).
- **Estimate:** ≈ 0.6 M prefill tokens per leg; per pick per block ≈ N16 25 min, AF8 35, TQ8 80, AF4 40, TQ4 76 + 5 × 10 min idle ≈ 5.1 h →
  ≈ 20 h for 20 legs + ≈ 1 h preflights [+ 30 % ≈ 27 h]; deciding blocks extra.

## Stage 2 — quality (its own spec, after stage 1)

Each pick's generated table goes to the operator as soon as it exists; the operator keeps only the formats worth a quality study (none by
default — P479); native16 needs none. N16 and
every lossy format kept get a matched predictor-OFF quality comparison on each pick's supporting axes (the R6 design: per-axis paired
`acc_strict@budget` + the two-judge panel over passing pairs), written as its own spec and reviewed before it runs. Selection happens only
after stage 2; native16 is the lossless reference, measured, not assumed. A format that is dominated in stage 1 needs no quality run.

## Output

`benchmark/results/p475/MATRIX.md`, generated from the harvested receipts and rows (never hand-copied): per pick × arm × rung each block's
value and the mean for cumulative-peak GB, backend prefill tok/s and decode tok/s, plus the paired block ratios vs N16 and the instability
flags; labelled descriptive (two order-balanced speed-valid legs per arm, no interval claimed).

## Acceptance criteria

1. `bench.p475_kv` and the `run_capacity` extensions tested (mocked ops, real argv / env / receipts; red first): arm-commit checks,
   manifest preflight refusal, argv / KV-line / predictor-OFF checks, backend timing fields, `cache_n` and exact-length refusals, ABBA
   order, idle, power / busy / lock refusals, replacement queue, instability trigger, harvest.
2. A smoke leg (N16, grid 8192 only) VALID before the full run; one manifest preflight per codec family passes on a known positive.
3. Every arm × pick with two speed-valid legs; MATRIX.md generated from them; replaced legs listed.

## Non-goals

Stage 2 runs (own spec), MTP ON measurements, a fused quantized-KV kernel (P477), `quantized_kv_start` thresholds, other entries.

## Residuals (named, not built against)

A single synthetic filler / retrieval prompt family carries the speed / memory measurement (kernel cost depends on length, not content;
content-sensitivity is a quality question for stage 2). TurboQuant 6 (and other widths) only if stage 1 shows a gap worth filling.
