I have enough verified evidence to write up my findings. Let me present them concisely.

---

## Cold design review — M76 spec v1 — findings

**F1 — MAJOR — O'Brien–Fleming boundaries miscalibrated for axes whose tier-1 information fraction ≠ 0.5 (decision rule misbehaves).**

- Location: `docs/specs/m76-tq4-certification.md` §8, "Intervals O'Brien–Fleming for two looks: 99.4 % at look 1, 95.2 % at look 2 (z 2.797 / 1.977)".
- Evidence: confirmed against the per-axis tier sizes in §7/§8. The fixed z = 2.797 / 1.977 is the Lan–DeMets OBF spending for information fractions t₁ = 0.5, t₂ = 1.0. The actual t₁ differs by axis:
  - A5: tier 1 = 5/rung, tier 2 = 10/rung → t₁ = 0.5. Boundaries correct.
  - Math500: tier 1 = 100, tier 2 = 300 → t₁ = 0.333. Correct OBF look-1 z ≈ 3.39 (99.93% CI). Spec uses 2.797 (99.4%) → **too narrow → inflated type-I error at look 1**. The spec's claim "a second chance to pass does not inflate the 5% error" is false for Math500: overspending at look 1 pushes total α above 5%.
  - tg1: tier 1 = 2 sessions, tier 2 = 3 → t₁ = 0.667. Correct OBF look-1 z ≈ 2.40 (98.4% CI). Spec uses 2.797 (99.4%) → **too wide → over-conservative → tg1 almost never decides at look 1 → forced tier 2**, the GPU waste the funnel exists to avoid.
- Problem: a single fixed boundary pair cannot control α across axes with different t₁; the decision rule both inflates error (Math500) and wastes GPU (tg1).
- Failure scenario: Math500 falsely PASSes at look 1 under a true loss just above 10 pp (the CI is too tight to rule it out); tg1 burns a tier-2 leg (s3, +2.7 h × 2 arms) that a correctly calibrated 98.4% look-1 interval would have decided.
- Proposed change: compute per-axis OBF boundaries from each axis's actual t₁ (Math500 0.333, tg1 0.667, A5 0.5), or pre-register the most conservative (smallest t₁) boundary for all axes and accept the conservatism. State the per-axis t₁ and z in §8.

**F2 — MAJOR — A5 tier 1 (n = 5/rung) is below the cluster-bootstrap minimum; A5 tier 2 is not in the GPU budget.**

- Location: §7 A5 row ("5 prompts per rung … mechanical (per rung, exact-match)"); §9 GPU budget (tier 2 lists Math500, tg1, tg2 but not A5).
- Evidence: confirmed against `benchmark/bench/stats.py:127` ("MINIMUM USABLE n: ~10 items; below that report the histogram instead") and `cluster_bootstrap`'s 1/N grid (n = 5 → 20 pp steps). A5 is scored "per rung" → each rung is a sub-axis with n = 5 at tier 1. With exact-match scoring and at most 5 items, the paired_delta CI is grid-coarse (the loss bound jumps in ≥20 pp increments), so every rung will read UNDECIDED at look 1 and force tier 2 (+5 prompts/rung × 4 rungs × 2 arms = 40 long-context legs at full/resolved 102 K-token budget). The §9 "expected path" books 0 h of tier 2 and the "worst case" (125 h) omits A5 tier 2 entirely.
- Problem: the funnel is supposed to add coverage only where a look leaves an axis undecided, but A5 tier 1 is structurally unable to decide, so tier 2 is mandatory, not conditional; the budget understates the run by roughly 40–80 h of GPU.
- Failure scenario: operator approves the run on the 67–70 h expected path; A5 alone adds ~40–80 h not budgeted, blowing the calendar and the per-look recalibration.
- Proposed change: either (a) make A5 one axis over all rungs pooled (n = 20 at tier 1, above the minimum) with rung as a stratum, not a verdict; or (b) start A5 at n = 10/rung (skip the n = 5 look) and add A5 tier 2 to the §9 worst case; or (c) state explicitly that A5 is descriptive-only at tier 1 and only tier 2 decides. Clarify whether A5 is one axis or four.

**F3 — MINOR — tg2's screen (k = 1, diagnostic) → decider (k = 2) is mapped onto a two-look OBF rule it cannot satisfy.**

- Location: §8 "A8 tg2: the screen is diagnostic … it triggers the decider (tier 2), read by the rule above."
- Evidence: confirmed against `docs/specs/m65-tg2-corpus.md:109` (SCREEN k = 1, diagnostic only) and `stats.py:104` (cluster_bootstrap needs k ≥ 2 draws per item). With k = 1 the screen produces no cluster-bootstrap CI, so it is not a formal "look 1" for OBF; the decider is the only formal look. Applying the look-2 boundary (95.2%, z 1.977) to a single-look decision is slightly conservative but not wrong; the spec's wording that the screen is "look 1" of an OBF pair is inaccurate.
- Problem: minor miscalibration and a confusing framing; the decider should be read as a single-look 95% test, not as the second look of a two-look OBF.
- Failure scenario: a clean screen followed by a decider that misses the 95.2% boundary by < 0.2 pp is reported as "loss not ruled out" where a single-look 95% interval would have PASSed.
- Proposed change: state that tg2 uses a single formal look (the decider) at 95%, and the screen is a non-binding trigger, not an OBF look.

**F4 — MINOR — Stage 2 FAIL leaves stage 3's quality legs confounded (KV-format + MTP-exactness) with no stated branch.**

- Location: §7 stage 2 verdict ("ON ≠ OFF1 → FAIL … → operator; else PASS"); §8 ("every quality leg MTP ON (stage 2 is what licenses skipping MTP-OFF quality legs: m72_exact ON ≡ OFF)"); §10 (ship requires stage 2 PASS).
- Evidence: confirmed against C319/S21-P9 (the S21-P9 correction: under seeded sampling MTP ON is distribution-identical, not token-identical, and only an exact verify preserves that; m72_exact's claim is greedy identity + exact target distribution, which stage 2 tests). If stage 2 FAILs, m72_exact MTP ON ≠ OFF in distribution, so X (MTP ON) vs N16 (MTP ON) no longer isolates the KV-format lever — it conflates KV-format with the MTP-exactness break. The spec gates *shipping* on stage 2 PASS but never says whether stage 3 should then add MTP-OFF legs (XO vs N16-OFF) to deconfound, or stop.
- Problem: a stage-2 FAIL path leaves the stage-3 evidence either confounded or undefined; the operator could be handed a stage-3 "PASS" that is not the KV-format comparison C322 asked for.
- Failure scenario: stage 2 FAILs on an E2 straddle cell; stage 3 proceeds as written, X vs N16 (both MTP ON) reads PASS, and the operator is told the KV-format lever is fine when the signal is contaminated by the predictor.
- Proposed change: add an explicit branch: on stage 2 FAIL, stage 3 either (a) adds the MTP-OFF pair (XO vs N16-OFF) to isolate KV-format, or (b) halts and goes to the operator before any tier-1 quality GPU is spent. State which.

**F5 — MINOR — "bench.arm_identity already hashes `--tq4-attention` (`28235601`)" is a commit hash, not a flag hash.**

- Location: §3 "Code map" bullet.
- Evidence: confirmed `benchmark/bench/arm_identity.py:19` already lists `--tq4-attention` in `OUTPUT_VALUE_FLAGS` (so the claim is functionally true), but `28235601` is a stack companion commit hash per `docs/reviews/m72-1.3-design/change-review-dispositions-report.md:74,78` ("companions 28235601 … `--tq4-attention` arm-identity class"), not the hash of the flag.
- Problem: literal mismatch with no material consequence (the flag is classified; the parenthetical just names the commit that added the class).
- Proposed change: reword to "bench.arm_identity already classifies `--tq4-attention` (added in companion `28235601`)".

**F6 — Scope request — Noise-floor diagnostic (S22-P9) is run only for agentic axes, not for Math500/A5, though those also use sampling and have a 2-block structure.**

- Location: §8 "Noise floor (S22-P9): for A7 (and A8 if the decider runs)".
- Evidence: confirmed the quality legs use deployed sampling (temperature 0.5 / top_p 0.95 / top_k 20 per `main_models.yaml`), and Math500/A5 each run two blocks (k = 2 draws per item). The X-vs-N16 discordance on Math500/A5 therefore also has a within-arm (N16 b1 vs N16 b2) noise component that is not printed.
- Problem: without the noise floor on Math500/A5, a lossy-looking X-vs-N16 delta on those axes cannot be read against the within-arm noise baseline the operator was promised for agentic axes; the loss bound is conservative (wider) but not separable from sampling noise.
- Proposed change (scope request): extend the S22-P9 noise-floor print to every mechanical axis with k ≥ 2 draws (Math500, A5, A7, A8-decider), not just agentic axes. If declined, state that Math500/A5 loss bounds include sampling noise by construction.

---

**Verified claims (no finding):** the S22-P10 assertion that TQ4 MTP OFF with the mode is unservable today is confirmed at `config.py:175-178` + `:256-260`, `tq4_attention.py:88-90`, `mtp_verify_scan.py:516-517` (B0 is necessary); the §9 wall anchors reproduce exactly (A1 4518, A2 3691, A3 433, A4 1659, M1 1536 are the sums of both S′ ON blocks in `benchmark/results/p426/SIGNALS.md`; N16 1885 s and TQ4 ≈ 3919 s reproduce from `p475/*/receipt.json` driver launch/exit); the E1c straddle thresholds (2048, 65536) reproduce at `tq4_fast.py:44` (`SINGLE_PASS_MAX = 2048`) and `:528` (D2 block-count tier above 65536); B0 does not break the shipped `Qwen3.8-27B-mlx-uniform-4bit` pick (its entry has `tq4_attention` absent, so `require_environment(None)` is a no-op) nor the `mtp` lever (B0 only relaxes a refusal for a new configuration).
