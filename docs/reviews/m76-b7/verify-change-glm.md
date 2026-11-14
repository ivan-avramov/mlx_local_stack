I've verified the diff against the source, the committed report, the spec, and the tests. Here are my findings.

## Disposition verdicts

**F1 (Sol P1 / GLM F1 / test-writer F1) — simulated ≠ stage-3 bootstrap.** Resolved. `m76_rule.exact_interval_values` is now the single loss-bound computation; `m76_sim.analyse`/`verdict_vector` and `m76_rule.loss_bound`/`axis_verdict` both call it (`m76_rule.py:198-225`, `m76_sim.py:255-278`). Stage 3 no longer routes through the 10,000-resample `paired_session_delta`/`paired_delta`. `test_a1_look1_resample_passes_exact_rule_undecided` reproduces the opinion's case: `paired_delta` gives lo −0.10 → PASS, `axis_verdict` gives lo −0.11 → UNDECIDED. `test_stage_function_equals_simulator_decision_at_every_candidate_alpha` asserts equality at every candidate α and the OBF alphas. The change is in the conservative direction (exact lower quantile ≤ noisy percentile at small α).

**F2 (Sol P2 / GLM F2 / test-writer F2) — silent 0.05 fallback.** Resolved. `loss_interval` requires `exact_alpha` or result metadata, raises `ValueError` if neither and on conflict, and never reads `discordance_upper95` (`m76_rule.py:76-99`). `test_verdict_of_requires_alpha_never_default` confirms the default-alpha degenerate result raises and that the explicit α is used.

**F3 (Sol P3) — `recheck` ignores dispersion / mixes concentrations.** Resolved. `recheck` now counts outside when κ̂ < committed κ, flags `observed_unrealisable` via `cell_feasibility`, and when κ̂ is identified and differs sets `committed=None` (full recalibration at κ̂) (`m76_sim.py:718-755`). `test_recheck_dispersion_only_change_recalibrates_every_cell_at_observed_kappa` and `test_recheck_unrealisable_observed_nuisance_flags_operator` confirm.

**F4 (GLM F3) — A8 `final_safe` hides SD-0.5 cells.** Resolved per disposition (adapted). The A8 row reads "safe on the v1.2 grid; 3 realisable SD 0.5 cells over 0.025 (operator-accepted residual, C336)" and `report.json` carries `residual_cells` = the three σ=0.5 cells (`m76_sim.py:905-913`, report confirmed). `final_safe` stays `True` and the "safe" column reads "yes" — this is the disposition's choice (C336 residual), disclosed via the chk column. Residual noted below (A3).

**F5 (GLM F4) — `recheck` cannot estimate session SD.** Not resolved (declined by driver). `_estimate_nuisance` still estimates only (m̂, κ̂, D̂); the hull has no session-SD dimension. The driver's rationale (operator-accepted C336 residual; `session_interaction` is the detector) is reflected in the code. Residual noted below (A4).

**F6 (GLM F5) — `unsafe_at_observed` misnomer.** Resolved. Renamed `unsafe_on_extended_grid`; docstring states "not specific to the observed cell; false when inside" (`m76_sim.py:703-706`). Tests assert the old name is absent.

**F7 (GLM F6) — SD-0 interaction test under-enforced.** Resolved. `test_committed_interaction_null_firing_at_most_005` now asserts `fl["hi"] <= 0.05` only (the `or rate` clause removed). Committed values: max hi 3.64 % ≤ 5 %.

**F8 (GLM F7) — byte-identity vs numpy/interpreter.** Not resolved (declined by driver). `numpy==2.3.5` is pinned in `benchmark/requirements-bench.lock`; the report records versions. The interpreter is not pinned. Matches the declined disposition.

**F9 (GLM F8 / test-writer F4) — A7 planning cell unrealisable.** Resolved per disposition (adapted). A7 PASS(0) is marked "(extrapolated)" with the nearest realisable cell `m=0.96|D=0.05|σ=0.25` at 87.31 %; `report.json` carries `planning.pass0_extrapolated` and `planning.nearest_realisable`. `test_committed_report_labels_a8_residual_and_a7_extrapolation` recomputes that cell's PASS(0) at 20k reps and matches.

**S1/S2 (GLM S1/S2) — `discordance_upper95` nulling / A5 annotation.** Kept (harmless), per disposition. No change needed.

## Additional findings

**A1 — spec v1.3 text is now stale on the two points the dispositions changed (minor; documentation drift).**
- Location: `docs/specs/m76-b7-statistics.md:104` and `:158`.
- Evidence: confirmed. Line 104: "The loss bound is `paired_session_delta`'s lower percentile" — but stage 3 now uses `exact_interval_values` (exact bootstrap), and so does the simulation (the spec's own line 130 already accepts "The exact (enumerated) bootstrap in the simulation", making line 104 the stale wording). Line 158 (Amendment v1.3): `unsafe_at_observed: true` — but the code renamed it `unsafe_on_extended_grid` and `test_m76_b7_impl_sim.py:291` asserts the old name is absent from the record.
- Problem: a future auditor reading spec v1.3 expects `paired_session_delta` and `unsafe_at_observed` in the stage-3 path and finds neither. The code follows the adopted dispositions (authoritative per the brief), but the spec was not amended to match.
- Failure scenario: an operator or reviewer certifies against the spec text, finds the code deviates, and raises a false discrepancy.
- Proposed change: amend the spec (v1.4) to state stage 3 uses `m76_rule.exact_interval_values` and to rename `unsafe_at_observed` → `unsafe_on_extended_grid`.

**A2 — `recheck` classifies m̂ ∈ {0, 1} as unrealisable but still crashes before the flag is returned (minor; defect the diff leaves).**
- Location: `m76_sim.py:728-755` (`cell**A2 — `recheck` classifies m̂ ∈ {0, 1} as unrealisable but still crashes before the flag is returned (minor; defect the diff leaves).**
- Location: `m76_sim.py:728-755` (`cell_feasibility` guard + the else-branch `calibrate` call).
- Evidence: confirmed by reading. The new `cell_feasibility` guard (`m76_sim.py:237-238`) returns a non-empty reason for `m` ∉ (0,1) or κ ≤ 0, so `observed_unrealisable=True` and `inside=False` — but `recheck` then unconditionally calls `calibrate(..., grid=ext, ...)` whose `ext.pass_rates` includes m̂ = 0 or 1, and the downstream `simulate_multi`/`Model` cannot handle those values. The implementer's own open point P3 records this ("recheck still crashes if the observed pass rate is exactly 0 or 1 … I only guarded `cell_feasibility`").
- Problem: the new guard gives the appearance of handling the unrealisable-observed case (it produces the reason and sets `observed_unrealisable` in the record dict), but for the m̂ ∈ {0, 1} sub-case the flag is unreachable because `calibrate` crashes first. The `observed_unrealisable`/`operator_review` flags are only ever returned when `calibrate` survives.
- Failure scenario: a tg2 SCREEN where every N16 item passes (m̂ = 1) or fails (m̂ = 0) — extreme but possible on a small decider subset. `recheck` raises in `calibrate` instead of returning `observed_unrealisable: true` to the operator.
- Proposed change: when `observed_unrealisable` is true, skip the recalibration (apply the fixed/committed α* and return the flags) rather than calling `calibrate` on a grid containing an unrealisable m̂.

**A3 — A8's "safe" column still reads "yes" beside three realisable cells over 0.025 (minor; residual of the adapted F4).**
- Location: `m76_sim.py:1112` (`{'yes' if a['final_safe'] else 'NO'}`) and the A8 row of `REPORT.md`.
- Evidence: confirmed. `final_safe` is `True` for A8, so the final column reads "yes" while the chk column discloses "3 realisable SD 0.5 cells over 0.025". `test_committed_plan_final_looks_are_safe` asserts `final_safe` True.
- Problem: a reader scanning the "safe" column sees "yes" for A8; the residual is disclosed only in the adjacent chk text. This is the disposition's explicit choice (C336 operator-accepted residual), so it is not a defect — but the headline "safe: yes" is the field the request's protection ("every final look kept must have false-PASS ≤ 0.025") would be read against, and three realisable cells violate it.
- Failure scenario: an operator reads the Final plan table's "safe" column and treats A8 as fully safe without reading the chk cell.
- Proposed change (scope request, not a defect): consider changing the "safe" column for a fixed-α* axis with residuals to "yes (v1.2 grid)" or "partial", so the headline column alone does not overstate safety.

**A4 — `recheck` still cannot detect a high-session-SD SCREEN (residual of the declined F5; not a defect introduced by this diff).**
- Location: `m76_sim.py:677-685` (`_estimate_nuisance`).
- Evidence: confirmed. No session-SD estimate; the hull is (m̂, D̂, κ̂). An SD-0.5 SCREEN with in-hull (m̂, D̂) and κ̂ ≥ 4 is reported `inside=True` with α* 0.001 applied; the SD-0.5 unsafety is disclosed only via the report's static residual table, not detected by `recheck`. The `session_interaction` test in `axis_verdict` fires on per-session mean dispersion, but no test exercises a high-session-SD SCREEN through `recheck`, so detection is unverified.
- Problem: the one dimension that makes A8 unsafe at the fixed α* is invisible to the pre-registered re-check.
- Failure scenario: a tg2 SCREEN with session SD ≈ 0.5 and (m̂, D̂) inside the v1.2 hull → `inside=True`, α* 0.001 applied, no `operator_review` flag.
- Proposed change: this is the driver's declined finding; raising it again would be a scope request. At minimum, add a test that an SD-0.5-like SCREEN is either flagged or explicitly noted as an operator-accepted residual in `recheck`'s output.

## Bottom line

All eight adopted/adapted dispositions (F1, F2, F3, F4, F6, F7, F9, and the kept S1/S2) are implemented correctly and verified in source, tests, and the regenerated report (sha matches the implementer's claim, byte-identical across two runs). The two declined findings (F5, F8) match the driver's stated rationale. The diff introduces no blocker or major regression. The remaining items are minor: A1 (spec text stale on the two renamed/changed points), A2 (m̂ ∈ {0,1} still crashes despite the new guard), and A3/A4 are residuals of the adapted/declined dispositions, not new defects.
