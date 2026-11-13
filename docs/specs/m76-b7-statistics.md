# M76 B7 — statistics for the M76 decision rule and its simulation — SPEC v1, 2026-11-13 (four-eyes light; C325, C324)

## Goal

M76 stage 3 / 4 (`docs/specs/m76-tq4-certification.md` v1.2 §8) decides each mechanical axis by a pre-registered rule — PASS
(point estimate ≥ −5 pp AND loss bound ≤ 10 pp), LOSS (interval excludes 0, N16 better, point < −5 pp), else UNDECIDED — at one or
two looks whose α is spent per axis by Lan–DeMets O'Brien–Fleming, with a look kept only if a simulation of the whole rule shows it
pays (PASS probability ≥ 0.5 at no loss) and is safe (false-PASS ≤ α at a 10 pp loss). `bench.stats` cannot compute that rule today:
`paired_delta` hard-codes 2.5 / 97.5 % percentiles and a one-sided 0.05 exact zero-discordance bound, it resamples each arm's draws
within an item independently (so multi-session agentic axes lose their session pairing), and nothing spends α or simulates the rule.
Solving it means: additive statistics functions that compute §8 exactly, a pre-registered simulation that reports power and error per
axis and look, and the per-axis plan it implies — with every existing function and output byte-identical.

## Scope (files)

`benchmark/bench/stats.py` (additive); new `benchmark/bench/m76_rule.py` (the §8 rule: verdicts, looks, flags) and
`benchmark/bench/m76_sim.py` (the simulation + its generated report); tests `benchmark/bench/tests/test_m76_b7_*.py`. Read-only:
every other module (`p426_signals*`, `compare*` keep calling today's functions).

## Settled constraints

- (C172 / C173 / C323 / C324) the verdict rule and its thresholds as M76 §8; agentic loss bound by item resampling that keeps each
  item's per-session paired differences together; per-session deltas reported beside it; a session-disagreement flag.
- (AGENTS.md) two-stage cluster bootstrap; seeds explicit (426); no composites.

## Interfaces

**`bench.stats` (additive; defaults byte-identical).**
- `paired_delta(..., interval_alpha=0.05, exact_alpha=0.05)`: two-sided interval at `1 − interval_alpha` (percentiles
  `interval_alpha / 2`, `1 − interval_alpha / 2`); the zero-discordance bound `1 − exact_alpha^(1/n)`, returned under the existing key
  `discordance_upper95` when both alphas are the defaults, and additionally as `discordance_upper` for any alpha. Defaults reproduce
  today's output dict exactly (golden test written green first).
- `paired_session_delta(a, b, *, iters=10000, seed=426, interval_alpha=0.05, exact_alpha=0.05, strata=None)`: `a` / `b` map
  `item_id → {session_id: 0/1}` with identical item and session sets (else ValueError naming the difference); resample items (within
  strata), then for each resampled item use its full vector of per-session differences `d_s = a_s − b_s` (never resample the two arms'
  sessions independently); statistic = mean over items of the mean over sessions; returns `delta, lo, hi, n_items, n_sessions,
  degenerate, discordant_items, discordance_upper, per_session: {s: paired_delta(...) of that session}`.
- `obf_alpha(t, alpha_total)`: Lan–DeMets O'Brien–Fleming spending `α(t) = 2 · (1 − Φ(z_{1−α/2} / √t))` for one-sided total `α`
  at information fraction `t ∈ (0, 1]` (so `α(1) = α`); and
  `obf_looks(fractions, alpha_total)` → per-look nominal one-sided alphas (look 1 = α(t₁), look 2 = α(1) − α(t₁)).

**`bench.m76_rule`.**
- `verdict(delta, lo, hi, *, point_floor=-0.05, loss_margin=0.10)` → `PASS` (point ≥ floor and −lo ≤ margin; annotated
  `loss_shown_within_tolerance` when hi < 0), `LOSS` (hi < 0 and point < floor), else `UNDECIDED` — mutually exclusive, in that order.
- `session_disagreement(per_session)` → list of session pairs whose point estimates have opposite signs AND each session's 95 %
  interval excludes the other's point.
- `axis_plan(axis)` for the pre-registered axes (A1 Math500: n₁ 100, n₂ 300, t₁ 1/3; A7 tg1: sessions 2 → 3, t₁ 2/3; A5: single look;
  A8 tg2 decider: single look), returning the looks and their alphas.

**`bench.m76_sim` (CPU; `python -m bench.m76_sim --out benchmark/results/m76/b7-simulation/`).** Data model (pre-registered):
per-item N16 pass probability drawn from a Beta fitted by moments to the stored N16 rows of the axis (A1: `benchmark/results/p426/`
S′ A1 rows; A7: P426 S′ A7 rows, both sessions; A8: the tg2 pilot `benchmark/results/m65_pilot/` if present, else p = 0.5 with the
planning discordance; A5: p = 1.0 with the planning discordance only); a per-session random effect on the logit scale, SD 0.25
(sensitivity 0 and 0.5); the TQ4 arm = N16 with a per-item shift so the mean loss is 0 / 5 / 10 / 12 pp and the discordance rate is the
planning value (A1 0.06, A7 0.10, A5 0.05, A8 0.182); ≥ 20,000 replications per cell, seed 426; Monte Carlo 95 % intervals on every
rate. Reports per axis and look: PASS probability at loss 0, false-PASS at loss 10 pp (and 12), UNDECIDED / LOSS rates, expected items
run; the look-keeping rule of M76 §8 applied (keep look 1 iff PASS(0) ≥ 0.5 AND the upper MC bound of false-PASS(10) ≤ 0.025); for A5
the smallest n in 40…80 with PASS(0) ≥ 0.8. Output: generated `REPORT.md` + `report.json` (never hand-edited).

## Acceptance criteria

1. Red-first: golden of `paired_delta`'s default output on fixed inputs (green before the change); `paired_delta` with other alphas;
   `paired_session_delta` keeps per-item session vectors together (a constructed case where independent resampling and paired
   resampling give different intervals), refuses mismatched item / session sets, its per-session results; `obf_alpha(1, α) == α`, known
   values (t = 1/3, 2/3 at α = 0.025); `verdict` on every boundary (incl. the −3 pp / [−4, −2] case → PASS annotated); the disagreement
   flag cases (incl. the GLM F3 example); `axis_plan`.
2. The simulation runs end to end on CPU in ≤ 30 min at 20,000 replications (or reports its replications), its report regenerates
   byte-identically with the same seed, and a test asserts the realized false-PASS of the §8 rule at loss 10 pp is ≤ 0.025 (upper MC
   bound) for every final look it keeps.
3. Existing `bench.stats` consumers and their tests unchanged; the stack suite passes or fails only as on the baseline.

## Non-goals

Wiring into `p426_signals*` (B3); the panel statistics (unchanged P426 §8).
