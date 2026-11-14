# M76 B7.1 — joint plan and pre-registered follow-up looks — SPEC v1, 2026-11-14 (four-eyes light; C337 (2), S23-P44 … P46)

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
