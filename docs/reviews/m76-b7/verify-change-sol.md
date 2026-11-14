Resolution ledger

- P1 resolved in code: simulation and `axis_verdict` share `exact_interval_values`. Documentation remains inconsistent; see P11.
- P2 resolved: missing or conflicting α raises.
- P3 not fully resolved: lower κ triggers recalibration, higher observed κ does not; see P12.
- P4 resolved as adapted: A8 is labelled safe only on the v1.2 grid and exposes `residual_cells`.
- P5 not resolved by design; the accepted C336 residual is disclosed and the interaction test remains the detector.
- P6 resolved in code; the specification still uses the old name; see P11.
- P7 resolved: SD-0 tests require the MC upper bound ≤ 0.05.
- P8 not resolved by design; numpy is pinned and versions recorded, matching the disposition.
- P9 resolved: A7 PASS(0) is marked extrapolated with the nearest realisable cell.
- P10 retained as accepted scope behavior.

P11 — Normative material still specifies the superseded finite bootstrap
- Location: `docs/specs/m76-b7-statistics.md:104-105,132-133,157-159`; `docs/specs/m76-tq4-certification.md:268-276`; `benchmark/bench/m76_sim.py:800,1062`; generated `REPORT.md:51`.
- Severity: major.
- Evidence: confirmed by source tracing.
- Problem: the code correctly makes the exact bootstrap the stage path, but both specifications and the A1 report still describe the 10,000-resample/percentile rule. The spec also retains `unsafe_at_observed`.
- Failure scenario: a stage-3 consumer follows §8 or `REPORT.md` and calls the finite bootstrap, which the regression case demonstrates can return PASS where `axis_verdict` returns UNDECIDED.
- Proposed change: amend the specifications and generated report text to designate `axis_verdict`/`exact_interval_values` as authoritative and document `unsafe_on_extended_grid`.

P12 — Higher observed concentration bypasses required recalibration
- Location: `benchmark/bench/m76_sim.py:693-698,723-743`.
- Severity: minor.
- Evidence: confirmed by source tracing.
- Problem: only `κ̂ < 4` makes the observation outside. Any `κ̂ > 4` remains inside, despite the disposition requiring full recalibration at the observed concentration. The claim that κ=4 is least-favourable is not established by the committed grid.
- Failure scenario: in-hull `(m̂,D̂)` with `κ̂=8` retains the κ=4 calibration without testing κ=8.
- Proposed change: treat every identified κ materially different from the committed value as outside and recalibrate all cells, or pre-register and verify a conservative κ range.

P13 — `recheck` crashes at pass rate 0 or 1
- Location: `benchmark/bench/m76_sim.py:236-237,573-575,739-743`.
- Severity: minor.
- Evidence: confirmed by control flow.
- Problem: `cell_feasibility` marks the observed endpoint unrealizable, but `calibrate` still simulates it; `betavariate` then receives a zero Beta shape.
- Failure scenario: all 80×2 N16 outcomes pass (`m̂=1`) causes `recheck` to raise instead of writing an operator-review record.
- Proposed change: exclude endpoint cells from simulation while preserving `observed_unrealisable=true` and `operator_review=true`.

P14 — Per-session intervals are no longer the specified 95%
- Location: `benchmark/bench/m76_rule.py:584-588`; `docs/specs/m76-tq4-certification.md:270`.
- Severity: minor.
- Evidence: confirmed by source tracing.
- Problem: `axis_verdict` computes each per-session interval using the axis α, e.g. 0.001 for A8, rather than the required descriptive 95% interval.
- Failure scenario: A8 reports 99.8% per-session intervals, potentially hiding a session-level effect the specified 95% display would show.
- Proposed change: compute descriptive per-session intervals separately at one-sided α=0.025 while retaining the calibrated α for the pooled decision.

P15 — Scope request: strict size enforcement
- Location: `benchmark/bench/m76_rule.py:564-572`.
- Evidence: confirmed.
- Problem: mismatched planned item/session counts yield a normal verdict plus `size_warnings`.
- Proposed change: if automatic consumers will use this API, reject mismatches by default or return `verdict_valid=false`. The current specification does not mandate raising.
