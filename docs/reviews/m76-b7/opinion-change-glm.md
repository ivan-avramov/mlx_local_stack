I have enough to write the findings.

---

# Findings — M76 B7 statistics (candidate, spec v1.3)

The candidate is largely faithful to the spec and the exact-test machinery, calibration, and determinism are sound where checked. The substantive failures are in **safety transfer**: the simulation certifies the *ideal* bootstrap, but stage 3 calls the *finite-resample* `paired_session_delta`/`paired_delta`; and the convenience wrapper `verdict_of` can silently apply the wrong (0.05) exact bound. Both can let a reported PASS be less safe than the report claims, under conditions the spec supports. Details below.

---

## F1 — The simulation certifies the ideal bootstrap, not the function stage 3 calls (major)

- **Location:** `benchmark/bench/m76_sim.py` `ideal_quantiles`/`verdict_vector`/`analyse` (lines ~250–370, ~480–520) vs `benchmark/bench/stats.py` `paired_session_delta`/`paired_delta` (lines ~340–410, ~228–335).
- **Severity:** major.
- **Evidence:** confirmed in source. `analyse`/`verdict_vector` compute the *exact* CDF of the item bootstrap (`_ideal_cdf` convolves the empirical distribution to convergence). `paired_session_delta`/`paired_delta` draw 10,000 Monte Carlo resamples and take `_percentile` (linear-interpolated) quantiles. The committed report's safety numbers (`final_false_pass10_hi`, the calibration's per-cell Wilson upper bounds) are all produced by `simulate_cell`/`simulate_multi`, i.e. the ideal bootstrap. `test_ideal_bootstrap_matches_paired_session_delta` (impl_sim.py:39) only asserts agreement at α = 0.025, to within one grid step — it does **not** test α* = 0.001, which is the calibrated α for both A7 and A8.
- **Problem:** The spec (§8 and acceptance 2) requires "Red tests assert (b) on the shipped code for each axis" and "a test asserts the realized false-PASS of the §8 rule at loss 10 pp is ≤ 0.025 (upper MC bound) for every final look it keeps." The candidate's `test_final_look_false_pass_recomputed_from_code` recomputes via `simulate_cell`/`simulate_multi` (ideal bootstrap), not via the shipped `paired_session_delta`/`paired_delta`. At α* = 0.001 the lower tail of the 10,000-resample percentile rests on ~10 order statistics; the test-writer's delivery-2 measurement (43 items × 3 sessions, 4 % loss) was 1.55 pp variation across 20 seeds at q = 0.001 (vs 0.78 pp at q = 0.025). That Monte Carlo noise can push the realized false-PASS of the shipped function above the 0.025 the report claims for the ideal bootstrap.
- **Failure scenario:** Stage 3 runs A7 (s1+s2+s3, 43 items) at α* = 0.001 via `paired_session_delta(..., interval_alpha=0.002, exact_alpha=0.001, seed=426)`. A replication whose 10,000-resample lower percentile lands ~1.5 pp higher than the ideal value flips UNDECIDED→PASS at a true 10 pp loss. The report says "safe (upper 1.05 %)"; the shipped function's realized false-PASS is > 0.025. A lossy TQ4 arm ships on A7.
- **Proposed change:** Add a reduced-replication test that runs the *shipped* `paired_session_delta` (and `paired_delta` for A1) at the committed α* on the binding cell's data model, over many seeds, and asserts the Wilson upper bound of false-PASS(10) ≤ 0.025 — or record the iteration count stage 3 must use (e.g. ≥ 100,000 at α* = 0.001) in the report and in `axis_plan`. The spec's §8 wording "Red tests assert (b) on the shipped code" makes this a required, not optional, test.

---

## F2 — `verdict_of`/`loss_interval` silently uses the 0.05 exact bound on default-alpha results (major)

- **Location:** `benchmark/bench/m76_rule.py` `loss_interval` (lines ~75–86) and `verdict_of` (lines ~87–89).
- **Severity:** major (a hazard the material introduces).
- **Evidence:** confirmed.
```python
75:76:77:78:79:80:benchmark/bench/m76_rule.py
def loss_interval(result):
    """... §8's zero-discordance substitution: ..."""
    upper = result.get("discordance_upper", result.get("discordance_upper95"))
    lo = result["lo"]
    if result.get("degenerate") and upper is not None:
        lo = min(lo, -upper)
    return result["delta"], lo, result["hi"]
```
  `paired_delta`/`paired_session_delta` emit `discordance_upper95` (the 0.05 bound) at the defaults and `discordance_upper` (the bound at `exact_alpha`) only when an alpha is non-default (stats.py:325–335, 408–410). On a default-alpha degenerate result, `discordance_upper` is absent, so `loss_interval` falls back to `discordance_upper95` = the 0.05 bound.
- **Problem:** §8 (m76-tq4-certification.md §8) explicitly states "the existing code's 0.05 exact bound is not used by M76"; M76 uses the spent one-sided α (0.025 at the final look). `1 − 0.05^(1/n)` < `1 − 0.025^(1/n)`, so the 0.05 bound is the *smaller* (less conservative) loss bound. `verdict_of` on a default-alpha degenerate result therefore reports a loss bound that is too small, and `verdict` can return PASS where the 0.025 bound would give UNDECIDED/LOSS. `verdict_of` is presented as the natural way to turn a stats result into a §8 verdict, and nothing warns the consumer to pass non-default alphas. The existing test `test_verdict_of_uses_exact_bound_for_zero_discordance` only exercises the `exact_alpha=0.025` path, never the default-alpha path.
- **Failure scenario:** A stage-3 caller does `r = paired_session_delta(n16, x, seed=426)` (defaults, as the function signature encourages) then `m76_rule.verdict_of(r)`. The cell is degenerate (no discordant items — plausible on a small tg2 decider subset). `loss_interval` reads the 0.05 bound, e.g. `1 − 0.05^(1/80) = 3.69 pp` ≤ 10 pp → PASS. The correct 0.025 bound is `1 − 0.025^(1/80) = 4.43 pp` (still ≤ 10 pp here, but at n = 20 the 0.05 bound is 13.9 pp vs the 0.025 bound 16.8 pp — and at n where the 0.05 bound is just under 10 pp the 0.025 bound is just over, flipping PASS→UNDECIDED). A lossy arm ships.
- **Proposed change:** Make `loss_interval` refuse a default-alpha result (require `discordance_upper` present, else raise), or require the spent α to be passed explicitly to `verdict_of`/`loss_interval` and read only `discordance_upper`. Add a test that `verdict_of` on a default-alpha degenerate result raises.

---

## F3 — A8's fixed α* = 0.001 is unsafe at three realisable SD-0.5 cells, and `final_safe` hides it (major)

- **Location:** `benchmark/bench/m76_sim.py` `_axis_multi`/`_full_grid_at` (lines ~920–985) and the committed `REPORT.md` "Full grid at the decider α* 0.001" table; `m76_rule.axis_plan("A8")` returns 0.001 unconditionally.
- **Severity:** major.
- **Evidence:** confirmed in the report. The full-grid table at 0.001 lists three realisable cells over 2.5 %: `m=0.3|D=0.3|sigma=0.5` (2.606 %), `m=0.5|D=0.3|sigma=0.5` (2.819 %), `m=0.7|D=0.3|sigma=0.5` (2.705 %). Yet `a8["final_safe"]` is `True` because `_axis_multi` judges safety only on the v1.2 grid (σ ∈ {0.0, 0.25}). The spec v1.3 says "the report adds, per cell of the full grid … the false-PASS(10) upper bound at 0.001 and states the cells over 0.025" — which the report does — but it does not say `final_safe` may ignore those cells. The operator ruling (C336) fixed α* at 0.001 *because* no candidate covers SD 0.5; that is a recorded residual, not a licence to call the look "safe".
- **Problem:** `final_safe` is the field `test_committed_plan_final_looks_are_safe` asserts, and it is the headline "safe yes" in the Final plan table. A reader of the report sees "A8 … safe: yes" while three realisable cells exceed the 0.025 the rule requires. The spec's residual note ("the simulation reports the realised false-PASS(10) under its heterogeneous data model beside the exact size") is for A5's heterogeneity, not a licence to relabel an unsafe cell as safe. The operator's ruling defers the SD-0.5 case to the operator; the code instead reports `final_safe = True`.
- **Failure scenario:** The tg2 SCREEN's observed nuisance falls at m ≈ 0.5, D ≈ 0.3 with session SD ≈ 0.5 (the spec explicitly supports SD 0.5 as a sensitivity, and `recheck` does not estimate session SD — see F5). `recheck` returns `inside = True` (pass rate × discordance in hull), α* = 0.001 applied. Stage 3 runs the decider at α* = 0.001; the realized false-PASS at that cell is ~2.8 % > 0.025. A lossy TQ4 arm passes the decider.
- **Proposed change:** Either set `final_safe = False` for A8 (the full grid has realisable cells over 0.025) and let the operator decide, or rename the field to `final_safe_v12_grid` and make the Final plan table say "safe on v1.2 grid; unsafe at 3 SD-0.5 cells → operator". As written, `final_safe = True` for A8 is misleading under the spec's own residual.

---

## F4 — `recheck` never estimates or tests session SD, so an SD-0.5 SCREEN is not detected (major)

- **Location:** `benchmark/bench/m76_sim.py` `_estimate_nuisance` (lines ~751–767) and `recheck` (lines ~768–810).
- **Severity:** major.
- **Evidence:** confirmed. `_estimate_nuisance` estimates `n16_mean`, `n16_cov`/`var_between` (kappa), and `discordance` (sign-ignored). It does **not** estimate the session random-effect SD. `inside` is judged on pass rate × discordance only. The implementer's fix-3 report flags this as P4 ("recheck still estimates no session SD, so an SD-0.5-like SCREEN would not be detected").
- **Problem:** The spec v1.2/v1.3 grid's binding unsafety at A8 is entirely in the SD-0.5 cells (F3). `recheck` is the pre-registered "re-check on real data" precisely to catch when the committed α* should not stand, yet it cannot detect the one dimension that makes A8 unsafe. The spec's `recheck` says "if the estimates fall inside the A8 grid's hull the committed α* stands, else it re-runs `calibrate`"; but the hull is only (pass rate × discordance), so an SD-0.5 SCREEN with in-hull (m, D) is reported `inside = True` and the unsafe α* = 0.001 is applied without flag.
- **Failure scenario:** Same as F3 — the SCREEN's per-session outcomes vary enough that the true session SD is ~0.5, but `recheck` sees only (m̂, D̂) in hull and returns `alpha_star_applied = 0.001, unsafe_at_observed = False`.
- **Proposed change:** Estimate the session SD (or a proxy from the per-session discordance dispersion) in `_estimate_nuisance`, include it in the hull test, and when the observed SD exceeds the v1.2 grid's max (0.25) run `calibrate` on the extended grid with SD 0.5 and apply `min(0.001, new)` with `unsafe_at_observed` set per the v1.3 rule. At minimum, record the SD proxy in the recheck JSON and add a test that an SD-0.5-like SCREEN is flagged.

---

## F5 — `recheck` outside-hull with no safe candidate flags `unsafe_at_observed` for the *whole* extended grid, not the observed cell (minor)

- **Location:** `benchmark/bench/m76_sim.py` `recheck` (lines ~790–802); implementer fix-3 report P2.
- **Severity:** minor.
- **Evidence:** confirmed. When `new["alpha_star"] is None`, `unsafe_at_observed = True`. `new` is `calibrate` on the extended grid; `alpha_star = None` means no candidate is safe at *some* cell of that grid (which includes the committed cells, not just the observed (m̂, D̂) cell).
- **Problem:** The flag's name says "unsafe at observed", but it fires for unsafety anywhere on the extended grid. The spec v1.3 says "when the observed nuisance falls outside the grid and no candidate is safe there" — "there" reads as the observed cell. The implemented semantics is broader (and safer), so this is a labelling/interpretation issue, not a safety regression.
- **Failure scenario:** The observed (m̂, D̂) is itself safe at 0.001, but some other committed cell is unsafe at 0.001 → `unsafe_at_observed = True` even though the observed cell is fine. The operator is alerted unnecessarily.
- **Proposed change:** Either restrict the check to the observed (m̂, D̂) cell (re-run `calibrate` on a grid containing just the observed cell), or rename the flag to `unsafe_on_extended_grid` and state the semantics in the report.

---

## F6 — `session_interaction` null firing rate at SD 0 is asserted only loosely, and the spec's "≤ 0.05 within MC bounds" is not enforced at the committed replication count (minor)

- **Location:** `benchmark/bench/m76_sim.py` `interaction_exact_p`/`fire_probability` (lines ~378–465); `test_committed_interaction_null_firing_at_most_005` (impl_sim.py:388–394).
- **Severity:** minor.
- **Evidence:** confirmed. The test asserts `fl["hi"] <= 0.05 or fl["rate"] <= 0.05` and `fl["lo"] <= 0.05`. The committed report's A8 SD-0 loss-0 firing rate is 2.99 % [2.76, 3.24] (hi 3.24 % ≤ 5 %) — fine. But the spec (v1.1 acceptance 7) says "SD-0 firing ≤ 0.05 (MC upper bound reported)" — i.e. the *upper* bound must be ≤ 0.05. The test's `or fl["rate"] <= 0.05` lets a cell pass even when its upper bound exceeds 0.05, as long as the point rate is ≤ 0.05. The committed numbers happen to satisfy the stricter reading, but the test would not catch a future regression where the upper bound crosses 0.05 while the rate stays just under.
- **Problem:** The test under-enforces the spec's acceptance criterion 7.
- **Failure scenario:** A future change raises the A8 SD-0 null firing rate to 4.5 % with upper bound 5.5 %; the test still passes (rate ≤ 0.05), but the spec criterion is violated.
- **Proposed change:** Assert `fl["hi"] <= 0.05 + 1e-9` for SD-0 cells (the spec's MC-upper reading), dropping the `or rate` clause.

---

## F7 — Determinism depends on interpreter/numpy version, byte-identity is not cross-interpreter (minor)

- **Location:** `benchmark/bench/m76_sim.py` `build_report` header (lines ~1018–1020) and `write_report`.
- **Severity:** minor.
- **Evidence:** confirmed. The header records `platform.python_version()` and `numpy.__version__` in the report text, and the ideal-bootstrap convolutions use numpy. The implementer's candidate-1 report notes "byte-identity holds only on the same interpreter."
- **Problem:** Acceptance 2 / 8 require the report to regenerate byte-identically with the same seed. That holds on one interpreter, butContinuing the findings list.

---

## F7 (continued) — Determinism depends on interpreter/numpy version (minor)

- **Problem (cont.):** a numpy minor-version bump (e.g. `np.convolve` rounding, `np.sort` tie ordering on the Tango statistic) could change `report.json` bytes while every test still passes, since the byte-identity tests only compare two runs on the *same* interpreter in one session.
- **Failure scenario:** The committed report is regenerated on a CI node with a newer numpy; the bytes differ; a downstream golden test (or an audit comparing to the checked-in `report.json`) fails for an unrelated reason, or worse, the regenerated report silently changes a safety number by an MC-noise-sized amount.
- **Proposed change:** Pin numpy in the bench lock to the version that produced the committed report (the header records it; enforce it), or strip the python/numpy version strings from the byte-identity surface and assert numerical equality with a tolerance instead of byte equality for the rate fields.

---

## F8 — `cell_feasibility` skips the A7 planning cell itself; PASS(0) there is reported but the cell is "not realisable" (minor)

- **Location:** `benchmark/bench/m76_sim.py` `cell_feasibility` (lines ~229–248) and `_axis_multi` planning cell (lines ~921–924); REPORT.md A7 "Planning cell m 0.965116, D 0.1, κ 4.0: NOT realisable".
- **Severity:** minor.
- **Evidence:** confirmed. `cell_feasibility(0.965, 0.10, 4.0)` returns a non-empty list (`D/2 = 0.05 > 1 − m = 0.0349` at no loss), so the A7 planning cell is marked infeasible. `_axis_multi` simulates it anyway and reports PASS(0) = 64.10 %, but the cell is not used for α*. The implementer's fix-1 report flags this as P2.
- **Problem:** The spec's planning cell for A7 (m from P426 S′ rows = 0.965, D = 0.10) is *not realisable* under the candidate's data model. The A7 plan (one look, α* 0.001) is reported with PASS(0) = 64.10 % at a cell the model says cannot exist. The spec's "raised to the loss where the loss exceeds it" handles the loss-≥ D case, but the no-loss infeasibility (D/2 > 1 − m) is a structural mismatch between the planning discordance (0.10) and the observed N16 pass rate (96.5 %). A7's plan is thus calibrated against a grid that excludes the very cell stage 3 will approach.
- **Failure scenario:** Stage 3 A7 runs at the real planning cell (m ≈ 0.965, D ≈ 0.10). The simulation's safety claim was never evaluated at that cell (it was skipped as infeasible); the realized false-PASS there is unbounded by the report. The operator reads "A7 safe: yes" without knowing the planning cell was skipped.
- **Proposed change:** Either extend the A7 grid to include the planning cell (e.g. m = 0.965, D = 0.10) and report its false-PASS upper bound at α* explicitly, or state in the report that the A7 planning cell is infeasible under the data model and the plan is extrapolated — and have `axis_plan("A7")` carry that caveat.

---

## F9 — What the tests miss (summary, no new severity)

- **No test exercises `paired_session_delta`/`paired_delta` at α* = 0.001** (the A7/A8 calibrated α). The bootstrap-agreement test (impl_sim.py:39) only checks α = 0.025. This is the test-side of F1.
- **No test exercises `verdict_of` on a default-alpha degenerate result** (F2). `test_verdict_of_uses_exact_bound_for_zero_discordance` always passes `exact_alpha=0.025`.
- **No test checks that `recheck` detects an SD-0.5 SCREEN** (F4). The recheck tests use rows with identical sessions per item (`_rows` makes `n16[i] = {"s1": v, "s2": v}`), so session SD is 0 by construction.
- **`test_committed_plan_final_looks_are_safe` asserts `final_safe`**, which is `True` for A8 despite the three realisable SD-0.5 cells over 0.025 (F3). The test passes but the property it checks does not match the spec's "every final look it keeps must have false-PASS ≤ 0.025".
- **The A5 sizing rule** (smallest n with PASS(0) ≥ 0.8) is asserted in `test_committed_a5_sizing_and_exact_size`, but only against the report's own `n_scan` — it does not independently recompute PASS(0) at each n from the shipped `simulate_a5`. The exact-size ≤ 0.025 check is independent (parametrised over n), which is good.
- **The `bound` inversion** is tested against a full-margin scan (impl_stats.py `test_exact_paired_loss_bound_is_smallest_rejecting_margin`) — confirmed correct, including the Greenberg–Mohri skip.
- **The permutation test's null** is verified two ways: `interaction_exact_p` matches the Monte Carlo `session_interaction` (impl_sim.py:115), and identical sessions give p = 1. Confirmed correct.

---

## What the candidate does beyond the specification (scope requests, no severity)

- **S1 — `discordance_upper95` is set to `None` when `exact_alpha != 0.05`.** The spec (v1.1 settled note) says only that `discordance_upper` appears for non-default alpha and the default output is byte-identical. The candidate additionally nulls `discordance_upper95` in the non-default dict. This is a reasonable disambiguation but is not in the spec; a consumer that reads `discordance_upper95` will get `None` where the spec is silent. (Scope request: confirm this is desired, or document it.)
- **S2 — `verdict_a5` adds a `loss_shown_within_tolerance` annotation for A5.** The spec's verdict_a5 text (v1.1) does not mention an annotation for A5; the annotation is defined only for the bootstrap `verdict`. The candidate mirrors it onto A5. Harmless, but beyond spec.
- **S3 — `loss_interval`/`verdict_of` are not named in the spec.** They are a convenience wrapper the candidate introduces. The spec describes the verdict as taking `(delta, lo, hi)`; the wrapper reads a stats result and applies the zero-discordance substitution. This is where F2 lives. (Scope request: the wrapper is useful but should enforce the alpha, per F2.)
- **S4 — The simulation uses an *exact* (converged) item bootstrap, not a 10,000-draw Monte Carlo.** The spec says "≥ 20,000 replications per cell" for the *outer* simulation and "10,000 resamples, seed 426" for the statistic (§8). The candidate's inner bootstrap is exact (convolved), which is *more* accurate than the spec's 10,000-resample statistic — but that is precisely the gap F1 identifies: the simulation is more accurate than the shipped function. (Scope request: either align the simulation to the shipped 10,000-resample statistic, or require stage 3 to use the exact bootstrap / a higher iteration count.)
- **S5 — `recheck`'s `unsafe_at_observed` semantics is broader than the spec's "there".** See F5.

---

## Checks that came out clean (confirmed)

- **Exact test size:** `a5_exact_size(n) ≤ 0.025` for every n in 42…120 step 6 (parametrised test, impl_rule.py:212; the report's largest is 2.496 % at n = 42). The Tango statistic matches an independent constrained-MLE reference to ~1e-12 (impl_stats.py `_tango_ref`). The bound is monotone in b at fixed c and equals a full-margin scan.
- **`calibrate` criterion 5:** α* is safe at every realisable cell and the next larger candidate fails at the binding cell (`_check_criterion_5`, impl_sim.py:155). Determinism is asserted.
- **`recheck` never reads the arm effect:** identical-nuisance/different-loss rows give byte-identical records (impl_sim.py:238).
- **`session_interaction` null:** matches the exact permutation null and the Monte Carlo function; identical sessions give p = 1; the p-value formula `(1 + #{perm ≥ obs})/(1 + iters)` is verified.
- **`obf_alpha(1, α) == α`** and the known values at t = 1/3, 2/3 are verified against an independent `NormalDist` reference.
- **Default `paired_delta` output is byte-identical** to baseline (golden tests, red-first).
- **Report regeneration** is byte-identical across two runs on the same interpreter (impl_sim.py:288; fe_sim.py:108).

---

## Bottom line

The exact-test, calibration, and determinism machinery is correct where checked. The material fails the request's core protection — "every final look it keeps must have false-PASS ≤ 0.025 at a true 10 pp loss" — in two ways that can let a reported PASS be less safe than claimed: **F1** (the simulation certifies the ideal bootstrap, but stage 3 calls the 10,000-resample `paired_session_delta`/`paired_delta`, and no test checks the shipped function at α* = 0.001) and **F2** (`verdict_of` silently uses the 0.05 exact bound on default-alpha degenerate results, contrary to §8). **F3/F4** further weaken A8's safety claim: the fixed α* = 0.001 is unsafe at three realisable SD-0.5 cells, yet `final_safe = True`, and `recheck` cannot detect an SD-0.5 SCREEN. F5–F8 are minor.
