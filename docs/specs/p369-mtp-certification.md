# P369 — MTP certification: prove exactness, reproduce and fix M2–M5 (PLAN, 2026-10-17)

Status: PLAN → Cursor `gpt-5.6-sol-high` review → execute (operator: "go on the plan. Always run plans by cursor too").
Origin: P368 layer 1 (`docs/reviews/p368-layer1-mtp-mechanism.cursor-gpt-5.6-sol-high.md`, VERDICT NOT NEUTRAL M3 M4).
Both B picks ship `draft_kind: mtp` (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-mlx-uniform-4bit`).

Operator: exactness is what must be CERTIFIED, not inferred from a code reading; earlier MTP issues exist (lab notebook:
`qwen3_5_moe → Qwen3_5MTPSplitter` wrote a broken sidecar; batched-verify numerics differ across MLX key-length thresholds,
M58; a pre-existing nvfp4 verifier `array_equal` failure; C84/A5 checks were greedy replays, 40/40 identical). No prior test
covers T > 0.

## E — evidence (each test-first in `../mlx-vlm`, through the PRODUCTION speculative code path, not a re-implementation)

- **E1 exactness at T > 0 (certifies M1):** a tiny random-weight model of the deployed architecture (qwen3_5, hybrid
  recurrent + attention, MTP head) with a small vocabulary, real `mlx_vlm.speculative` path, deployed sampling transforms
  (temperature / top_p / top_k / min_p as in `main_models.yaml` `generation_defaults`). Either exact enumeration of the
  output distribution over the first k tokens (vocab and k small enough) or ≥ 10⁵-sample frequency comparison ON vs OFF
  with a pre-registered test (chi-square / exact multinomial, α = 0.001, power stated for a 1 % total-variation shift).
  Drafter deliberately mismatched to the target (worst case) and matched (realistic).
- **E2 greedy identity (T = 0):** ON vs OFF token identity on the tiny model and on frozen real prompts (the C84 40-request
  set, plus long contexts crossing 1,024 / 8,192 / 32,768 / 65,536 keys); every divergence classified (M58 threshold
  near-tie = expected; anything else = defect).
- **E3 M4 reproduction:** force EOS as an accepted draft token followed by another accepted token; compare KV + recurrent
  state and the NEXT turn's output vs plain decoding (session cache path used by the daily driver and the bench).
- **E4 M3 budget boundary:** budget trips after the first token of a fully accepted block; OFF forces the closer next, ON must too.
- **E5 M2 processors:** continuous-batch MTP with a repetition penalty / logit bias that changes token 2 vs plain batching.
- **E6 M5 seeds:** same-seed ON reproducibility, cached B = 1 and continuous batching.
- **E7 firing rate on real traffic (small GPU job, ≈ 15 min, one model at a time, lean router, no chain):** instrument a
  counter for EOS-mid-block commits (M4) and budget-overshoot (M3) and replay the frozen C84 requests + 10 tg1 opencode
  transcripts' requests through both picks with MTP ON. Decides the interim daily-driver call.

## F — fixes in `../mlx-vlm` (fork rules: edit the parent fork, never `src/*`; test-first; Cursor code review)

- M4: commit only through the first stop token of the accepted prefix (KV and recurrent state); the emitted history and
  the cache label then agree.
- M3: per-token budget check inside an accepted block; force the closer at the same position as plain decoding.
- M2: carry logits-processor state through continuous-batch MTP, or fall back to plain decoding whenever any processor is
  active (fail closed).
- M5: carry per-request seeds into continuous-batch speculative generation, or refuse a seeded request there.
- Each fix: the corresponding E test red first, green after; E1/E2 re-run after all fixes.

## R — release and re-certification

- Fork commit → Cursor review cleared → fork push (operator go) → `git submodule` bump in mlx_local_stack (serving-path
  fingerprint changes; recorded) → full suite.
- Interim daily driver (decided by E7): keep MTP ON if the M4 firing rate is ~0 on real traffic; else switch the daily
  driver's registry to `draft_kind` OFF until the fix ships (registry change = all four client carriers checked, AGENTS.md).
- Re-certify ON per AGENTS.md (certify on every supporting axis; ship OFF if OFF wins beyond ±5 pp) after the fix, with the
  C172 wash rule; P368 layers 2–3 then decide whether heavy runs use ON.
- M63 (MTP-ON tg1) rows stay descriptive; note in campaign-results that they predate the fix.

## Acceptance

E1 passes (no detectable distribution shift at the stated power, matched and mismatched drafter); E2 divergences all
classified expected; E3–E6 red before / green after; E7 firing rates recorded; full suites green in both repos; Cursor
cleared on the fork diff.
