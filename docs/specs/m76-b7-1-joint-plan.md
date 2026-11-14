# M76 B7.1 — joint plan and pre-registered follow-up looks — SPEC v1.4, 2026-11-14 (four-eyes light; C337 (2), S23-P44 … P46; v1.1 = change-review dispositions; v1.2 = two harm-detection options; v1.3 = C338 + verify dispositions; v1.4 = C339 registration)

## Goal

B7 (`docs/specs/m76-b7-statistics.md` v1.4) makes each M76 stage-3 axis safe on its own (false-PASS ≤ 0.025 at a true 10 pp loss),
but the ship recommendation (`docs/specs/m76-tq4-certification.md` §8) needs every mechanical axis PASS, no blocking flag, and the
A8 path clean at once. The designer's rough product at no loss is ≈ 38–52 % (A5 0.82 × A7 0.64–0.87 × the interaction flag ≈ 0.96
× the A8 path ≈ 0.75, the last assuming the tg2 screen triggers the decider by chance about half the time), so stage 3 more likely
than not ends UNDECIDED → the operator, and coverage added after an UNDECIDED look would spend α the rule never budgeted. Solving it
means: the simulation reports the joint operating characteristics of the whole stage-3 plan (clean-PASS probability at no loss,
each axis's UNDECIDED rate, the A8 screen's trigger rate at no loss and its detection rate at a 10 pp loss, expected GPU hours
including follow-ups), evaluates pre-registered follow-up looks that keep every final look's false-PASS ≤ 0.025, and states which
variants pay — so the operator chooses the stage-3 plan at the Go with numbers, not after the fact.

## Scope (files)

`benchmark/bench/m76_sim.py` (additive: the joint section and the variants), `benchmark/bench/m76_rule.py` (only to register a
variant's looks in `axis_plan` once the operator picks it — not in this build), tests `benchmark/bench/tests/test_m76_b7_1_*.py`, the
generated `benchmark/results/m76/b7-simulation/` (B7's numbers unchanged byte for byte outside the new section).

## Settled constraints

- (C331 / C335 / C336 / C337) B7's per-axis rules, α*, n and grids as committed; the exact item bootstrap and the exact test are the
  decision statistics; every final look of every variant: false-PASS(10) upper MC bound ≤ 0.025 on the axis's committed grid (A8:
  the v1.2 grid; its SD 0.5 cells reported).
- (C324) A8's screen is a trigger, not a look; changing the trigger amends C324 → reported as options, never applied.
- (C323 funnel) tier 2 / follow-ups run both arms, paired; nothing runs without the operator's Go.

## Interfaces

**Joint section (current plan).** For the committed plan, at loss 0 and at 10 pp on every axis (and, descriptively, a 10 pp loss
on one axis at a time): P(clean PASS) = P(every mechanical axis PASS ∧ no interaction flag ∧ A8 path clean), the A8 path clean =
(screen not triggered) ∨ (screen triggered ∧ decider PASS ∧ no decider flag); per-axis P(PASS / UNDECIDED / LOSS); the screen's
trigger rate (macro < −5 pp ∨ any language < −15 pp; 10 items / language, k = 1) at loss 0 and 10 pp under A8's planning cell and
the v1.2 grid; axes independent (separate items and sessions; stated). Not simulated, stated as inputs: A5's per-task absolute gates
(each arm ≥ 0.85; a given, reported as "assumed met"), the panel's Holm flag (≤ 0.05 family-wise; reported as a bound).

**Variants (evaluated, not adopted).**
- A7-2L: two looks — s1 + s2 + s3 (t₁ = 3/5), then + s4 + s5 (seeds 4004, 5005) on UNDECIDED; O'Brien–Fleming spending at t₁ = 3/5
  of total 0.025; α* per look calibrated least-favourably on A7's grid (B7's `calibrate` method, the two-look rule's false-PASS(10)
  ≤ 0.025 at every realisable cell).
- A5-2L: two looks — n = 72, then + 48 (to 120) on UNDECIDED; exact unconditional test at each look with the OBF-spent α; exact size
  of the two-look rule computed by enumeration (≤ 0.025).
- A8 screen options (C324 amendment candidates, reported only): T0 = today's trigger; T1 = macro-average < −5 pp only; T2 = macro
  < −5 pp ∨ any language < −25 pp; per option: trigger rate at loss 0 and its detection rate at a 10 pp loss (macro and a 10 pp loss
  concentrated in one language).
Per variant: P(clean PASS) at loss 0, per-axis PASS / UNDECIDED, false-PASS(10) of every final look, expected and worst GPU hours.

**GPU hours.** Inputs (constants with their source, to be replaced by the timed smokes before the Go): per arm, Wave 1 ≈ 3.3 h; A5 ≈
4 h per 72 items (unmeasured; scaled linearly); tg1 ≈ 2.7 h per session; tg2 screen ≈ 3 h; decider ≈ 12 h (M76 spec §9); × 2 arms.
Expected hours = Σ P(path) × hours(path) at loss 0.

**Output.** `report.json` gains `joint` and `variants`; `REPORT.md` a "Joint plan" section with one table (plan / variant × clean
PASS at loss 0, axis UNDECIDED rates, worst final-look false-PASS(10), expected / worst GPU h) and the screen-option table; seed 426;
deterministic; byte-identical outside the new keys / section.

## Acceptance criteria

1. Red first: the joint P(clean PASS) equals the product of the per-axis simulated terms (independence) and a direct joint
   simulation of the same plan within MC bounds; the screen's trigger rate matches a brute-force enumeration at small n.
2. Every variant's every final look: false-PASS(10) upper bound ≤ 0.025 (A5-2L by exact enumeration); a test per variant.
3. B7's existing report keys and numbers unchanged (golden of the committed `report.json` minus the new keys); `axis_plan` unchanged.
4. The simulation runs in ≤ 60 min on CPU and regenerates byte-identically.

## Non-goals

Adopting a variant (the operator's Go); changing the screen trigger (C324 amendment → the operator); B3's signals for variant looks
(after the operator picks).

## Erratum v1.1 (2026-11-14, designer; the B7.1 change review's adopted dispositions)

- **A8 nesting:** the screen's 40 items are the decider's first 40 (`docs/specs/m65-tg2-corpus.md` draw rule 2); the screen is its own
  k = 1 session, the decider s1 / s2 (+ reload) are separate sessions over all 80. Simulate one A8 item set per replication (item
  parameters shared), the screen on its prefix, the decider on all items; no independence assumption between screen and decider.
  A test where prefix outcomes predict the decider verdict.
- **A5 clean term includes the per-task point gates** (retrieval and chain-4 each ≥ −5 pp) besides the pooled exact test; only the
  absolute per-arm ≥ 0.85 gates stay an assumption. Recompute the committed plan and A5-2L.
- **A8 large-harm HOLD:** no numeric threshold is pre-registered (m65 / M76 name it only). Simulate per-language decider outcomes and
  report the A8 path and the clean PASS at HOLD thresholds {none, any language decider point < −25 pp, < −20 pp}; the threshold is the
  operator's at the stage-3 Go (S23-P63); the headline is labelled with the threshold it assumes.
- **Cells:** every plan / variant row reports clean PASS at both A7 cells — the nearest realisable cell (headline, decision-relevant)
  and the extrapolated planning cell (secondary, labelled).
- **New variant A7-5S:** one look over s1 … s5 (seeds 1001 … 5005) at a calibrated α* (B7's `calibrate` method on A7's grid);
  report as the other variants (+ hours: always 5 sessions per arm).
- **A7-2L when both looks calibrate safe:** record `available: true, flag: "five-session interaction flag not simulated"` (no abort);
  a test monkeypatches the calibration to reach it.
- **Fail closed:** the build raises when the direct joint simulation disagrees with the product (|z| > 3).
- **`build_report(b71=False)` by default;** the CLI and B7.1's tests set it.
- **GPU hours:** two columns — modelled comparison legs, and whole-stage totals including the mandatory pilot / reload, smokes and
  idles from M76 §9 (sources listed).

## Amendment v1.2 (2026-11-14, designer; S23-P68: the A8 path misses a true 10 pp tg2 loss ≈ 17.5 % under T0, mostly via a screen that does not trigger)

Two more A8 options, reported exactly like T0 / T1 / T2 (never applied; C324 amendment candidates):
- **T3 — sensitive trigger:** macro-average < 0 pp ∨ any language < −10 pp.
- **TD — always the decider:** the screen still runs (diagnostic, C168) but the decider runs on every plan; the A8 path is clean iff
  decider PASS ∧ no flag ∧ no HOLD.
Per option, as for the others: trigger rate at loss 0, detection at a macro 10 pp loss and at a 10 pp loss in one language, the A8
path's false-clean rate at a macro 10 pp loss, the joint clean PASS (both A7 cells; with and without A5-2L), and modelled / whole-stage
GPU hours. Tests: TD's trigger rate is 1 and its false-clean rate equals the decider's false-PASS-and-no-flag rate.

## Amendment v1.3 (2026-11-14; C338 + the B7.1 verify's adopted findings)

- **The committed plan is TD (C338):** the decider always runs. Every joint quantity, direct check, variant, hours figure, rendering
  and test uses TD as the committed A8 path; T0–T3 are reported as alternatives only (labelled superseded by C338). The report's
  header names spec v1.3.
- **A7-5S:** its five-session interaction flag is not simulated, so no clean-PASS estimate is shown; the row reports A7-5S's own PASS
  rate and safety and says "clean PASS not estimated (interaction flag unsimulated)"; `pays` stays undetermined.
- **Worst final look:** the column is "worst on the committed grid"; every plan with A8 shows the C336 residual beside it (3 realisable
  SD 0.5 cells, up to 2.82 %).

## Amendment v1.4 (C339, 2026-11-14: register the chosen plan in `m76_rule`; folds the planned B7.2)

- `m76_rule.axis_plan("A5")` returns two looks: n 72 at one-sided α 0.003808 and n 120 at 0.021192 (O'Brien–Fleming at t₁ = 0.6; the
  values the committed report's A5-2L computed — read from `report.json`, never retyped), statistic `exact_paired_loss`; a look-1
  LOSS stops. `verdict_a5(b, c, n, *, alpha=…)` takes the look's α (default 0.025 = today's single look, unchanged) and
  `axis_verdict("A5", look, a, b)` passes it; the per-task point gates apply at the deciding look.
- `m76_rule.A8_HOLD_PP = -0.20` and `a8_hold(per_language)` (any language's decider point estimate < −20 pp → HOLD, blocking);
  `axis_verdict("A8", …)` reports it when per-language rows are given.
- The report's committed plan = TD + A5-2L (C338, C339); A7-5S and T0–T3 shown as not adopted. A1 / A7 / A8 rules unchanged.
- Tests: A5 two-look verdicts (look-1 PASS, UNDECIDED → look 2, LOSS stops) at the registered α; the exact two-look size matches the
  report; `verdict_a5`'s default output byte-identical to today's; HOLD boundaries (−20 pp exactly does not fire).
