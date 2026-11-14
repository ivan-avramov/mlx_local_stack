# M76 B7 — statistics for the M76 decision rule and its simulation — SPEC v1.3, 2026-11-13 (four-eyes light; C325, C324; v1.1 = C331, §Amendment; v1.2 = C335; v1.3 = C336)

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

## Amendment v1.1 (C331, 2026-11-13; supersedes v1 where they differ)

Why: candidate 1's simulation showed the v1 rule unsafe at A5 / A8's final looks (false-PASS(10) upper bound 10.6 % / 5.2 % vs
0.025) and the session-disagreement flag firing 25 % / 14 % at no loss (S22-P25 / P26). Designer erratum to C331's wording: a
Clopper–Pearson bound on the discordant split conditions on the observed discordance count and is not safe (false-PASS(10) 6.6–22.6 %
for n 40–120, checked by exact enumeration); C331's intent — an exact, assumption-free A5 bound — is met by the exact unconditional
test below (worst case over the nuisance ≤ 0.024 at every n 40–120).

**A5 — exact unconditional loss test (replaces the bootstrap bound for A5 only).** Per item `d = X − N16 ∈ {−1, 0, +1}`; `b` = count
of `d = −1` (N16 pass, X fail), `c` = count of `d = +1`, over all A5 items pooled (strata stay for the point estimate's report and the
per-task gates). New `bench.stats.exact_paired_loss(b, c, n, *, margin=0.10, alpha=0.025, grid=None)`:
- H0: `p_b − p_c ≥ margin` vs H1: `< margin`. Ordering statistic: Tango's score statistic for a paired difference of proportions
  (Tango 1998, Statistics in Medicine 17:891) evaluated at `margin` with the constrained MLE; ties ordered together.
- p-value = sup over the nuisance `p_c ∈ [0, (1 − margin) / 2]` (with `p_b = p_c + margin`; the boundary of H0 suffices) of
  P(T ≤ t_obs) under the trinomial(n; p_b, p_c), by exact enumeration of all (b, c) with b + c ≤ n; nuisance grid ≥ 1,000 points plus
  the endpoints (default) or the given grid. Returns `pvalue, reject (pvalue ≤ alpha), bound` where `bound` = the smallest margin on a
  0.001 grid in [0, 1] at which H0 is rejected (the reported loss bound in pp), and `delta = (c − b) / n`.
- A5 PASS ⇔ `delta ≥ −0.05` AND `reject` at margin 0.10; LOSS ⇔ `delta < −0.05` AND the two-sided exact test of `p_b = p_c`
  (exact binomial on b | b + c, α 0.05) rejects with b > c; else UNDECIDED. `m76_rule.verdict_a5(b, c, n)` returns that and the
  bound.
- `m76_rule.a5_rejection_region(n)` (cached) = the set of (b, c) that reject; the simulation and the test-writer may use it. Its size
  check is exact: max over the nuisance grid of P(region ∧ delta ≥ −0.05) at margin 0.10 must be ≤ 0.025 (an acceptance test, every
  n in the A5 range).
- Sizing: A5 n = the smallest multiple of 6 in 42 … 120 (two tasks × three rungs, equal cells) with PASS(0) ≥ 0.8 under the
  simulation's A5 data model at planning discordance 0.05; if none, report the largest n's PASS(0) and stop (→ the operator). Residual
  (recorded): items are heterogeneous (a sum of non-identical trinomials); the simulation reports the realised false-PASS(10) under its
  heterogeneous data model beside the exact size.

**A7 / A8 — least-favourable calibrated α (the cluster bootstrap stays).** The loss bound is `paired_session_delta`'s lower
percentile at a nominal one-sided α* chosen by `m76_sim.calibrate(axis)`: the largest α* in {0.025, 0.02, 0.015, 0.0125, 0.01, 0.0075,
0.005, 0.0035, 0.0025, 0.001} such that, at every nuisance cell, the upper 95 % MC bound of false-PASS(10) ≤ 0.025 (one bootstrap per
replication, every candidate α* read from it). Nuisance grids (pre-registered): A8 — mean per-item N16 pass rate {0.3, 0.5, 0.7,
0.9} × discordance {0.10, 0.20, 0.30} × session SD {0, 0.25, 0.5}; A7 — pass rate {0.8, 0.9, 0.96} × discordance {0.05, 0.10, 0.20}
× session SD {0, 0.25, 0.5}. Per-item heterogeneity at each cell: Beta with the cell's mean and the dispersion of the axis's stored
rows where identified, else Beta(2, 2)-shaped (designer choice; reported). A cell the data model cannot realise (e.g. discordance above what the pass rate allows at no loss) is skipped and listed in the report. A7's plan stays one look over s1 + s2 + s3 unless look 1 is
safe at every cell with its own calibrated α*; A8 one look over the decider (80 items × 2 sessions). Report α*, the binding cell, and
PASS(0) at the planning cell for each axis; `m76_rule.axis_plan` returns the calibrated α* (read from the committed `report.json`).
If no candidate is safe, report that and stop (→ the operator).

**A8 — pre-registered re-check on real data.** `m76_sim.recheck(axis, n16_rows, x_rows)` (rows as `item_id → {session_id: 0/1}`, the
tg2 SCREEN's): estimates only the nuisance — the N16 mean pass rate, its Beta dispersion, and the discordance rate (discordant
item-sessions / all, sign ignored) — never the arm effect; if the estimates fall inside the A8 grid's hull the committed α* stands, else
it re-runs `calibrate` on the grid extended to include the estimates and returns min(committed α*, new α*). Output a JSON record
(estimates, inside / outside, α* applied, report sha) under `benchmark/results/m76/b7-simulation/recheck-<axis>.json`; frozen seed
426; deterministic.

**P26 — session × arm interaction test (replaces `session_disagreement`).** `m76_rule.session_interaction(a, b, *, iters=10000,
seed=426)` over the same `item_id → {session_id: 0/1}` maps: statistic = the variance across sessions of the per-session mean
difference; null by permuting, within each item independently, which session each item's `d_s` belongs to (exchangeability of
sessions under no interaction); p-value = (1 + #{perm ≥ obs}) / (1 + iters); `flag = p < 0.05`. The flag still blocks a ship
recommendation (→ the operator). The simulation reports its firing rate at loss 0 and 10 pp, session SD 0 (the null: must be ≤ 0.05
within MC bounds — an acceptance test) and SD 0.25 / 0.5 (sensitivity, descriptive). `session_disagreement` is removed from the rule
(it may stay in code as a descriptive per-session listing, not a flag).

**Settled from candidate 1's report.** `discordance_upper` appears only when an alpha is not the default (default output unchanged
byte for byte). The data model as candidate 1 implemented it (per-item discordance ∝ p(1 − p) averaging D; direction logit(ω) + session
effect, calibrated to the planning loss and discordance) is accepted. The exact (enumerated) bootstrap in the simulation is accepted.
§8's "≈ 99.9 % / ≈ 98.4 %" are superseded by the B7 formula (99.979 % / 98.79 %; M76 spec erratum). A1's v1 rule stays (safe: 0.33 %).

**Acceptance criteria (v1.1 additions).** 4. `exact_paired_loss`: known small-n p-values by brute enumeration in the test; exact size
≤ 0.025 at margin 0.10 for every A5 n (42 … 120, step 6); `bound` monotone in b at fixed c. 5. `calibrate`: deterministic; the
chosen α* is safe at every grid cell (upper MC bound ≤ 0.025) and the next larger candidate is not safe at the binding cell (or α* is
0.025). 6. `recheck`: inside-hull rows keep α*; outside-hull rows re-calibrate and never loosen; never reads the arm effect (rows with
the same nuisance and different net loss give the same record). 7. `session_interaction`: SD-0 firing ≤ 0.05 (MC upper bound
reported); identical sessions → p = 1. 8. The regenerated report covers all of the above and states A5's n, A7 / A8's α*, and the
final plan; the simulation runs in ≤ 60 min on CPU (or reports its replications).

## Amendment v1.2 (C335, 2026-11-13)

- A8's calibration grid: session SD {0, 0.25} (pass rate and discordance unchanged). α* = the largest candidate safe at every
  realisable cell of that grid. The SD 0.5 cells are still simulated and reported as a sensitivity reading (per cell: the worst
  upper bound at the chosen α* and the smallest candidate safe there, or "none"); they never set α*. `recheck("A8", …)` uses the v1.2
  grid. A7 unchanged (concentration 4; SD {0, 0.25, 0.5}).
- Acceptance: criterion 5 holds on the v1.2 A8 grid; `axis_plan("A8")` returns the committed α*; the report states the SD 0.5
  sensitivity for A8.

## Amendment v1.3 (C336, 2026-11-13)

- A8's decider α* is fixed at 0.001 (the smallest candidate; operator ruling), not chosen by the capped grid. `calibrate("A8")`
  still runs on the v1.2 grid and reports its result (α* 0.005) as context; the report adds, per cell of the full grid (SD 0, 0.25,
  0.5), the false-PASS(10) upper bound at 0.001 and states the cells over 0.025. `axis_plan("A8")` returns 0.001.
- `recheck("A8", …)`: applies min(0.001, re-calibrated α*); when the observed nuisance falls outside the grid and no candidate is
  safe there, the record says so (`alpha_star_applied` 0.001, `unsafe_at_observed: true`) → the operator.
- Acceptance: `axis_plan("A8")` = 0.001; the report states A8's PASS(0) at 0.001 (planning cell) and the full-grid table.
