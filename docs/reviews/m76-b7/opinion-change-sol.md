P1
- Location: `benchmark/bench/m76_sim.py:324-369,499-523`; `benchmark/bench/stats.py:289-307,391-405`
- Severity: major
- Evidence: confirmed
- Problem: calibration simulates the ideal infinite bootstrap, but stage 3 calls the noisy 10,000-resample bootstrap. At A1 look 1, α≈0.000104 is represented by roughly one bootstrap order statistic, so the procedures can produce opposite decisions.
- Concrete failure scenario: with look-1 losses on items 11, 67, and 93, the real function returns `delta=-0.03`, `lo=-0.10`, hence PASS. The simulator returns UNDECIDED and the full 300-item look returns LOSS. Across the committed 20,000 loss-10 replications, simulated false-PASS was 0.25% [upper 0.33%], versus 0.42% [upper 0.52%] through the stage function. Tests compare the implementations only at α=0.025 and recompute safety using the ideal simulator itself.
- Proposed change: make stage 3 and simulation use the same exact discrete bootstrap quantile, or simulate the actual finite-bootstrap procedure. Do not keep A1 look 1 until that procedure is recalibrated.

P2
- Location: `benchmark/bench/m76_rule.py:72-85`; `benchmark/bench/stats.py:345-411`
- Severity: major
- Evidence: confirmed
- Problem: the extra `verdict_of`/`loss_interval` API silently accepts default-alpha statistics and falls back to `discordance_upper95`, although calibrated M76 axes require the α from `axis_plan`.
- Concrete failure scenario: for 43 A7 items with zero discordance, `verdict_of(paired_session_delta(a, a))` returns PASS using α=0.05 and a 6.73-pp bound. `axis_plan("A7")` requires α*=0.001, whose 14.84-pp bound makes the same rows UNDECIDED.
- Proposed change: require a plan/look argument or explicit alpha metadata and reject mismatches. Remove the `discordance_upper95` fallback from the M76 verdict path.

P3
- Location: `benchmark/bench/m76_sim.py:628-648,750-804`
- Severity: major
- Evidence: confirmed
- Problem: `recheck` estimates Beta dispersion but excludes it from the inside-hull decision. Outside the hull it changes the reported κ while reusing committed cells generated at the old κ, producing a mixed, mislabeled calibration. This can suppress `unsafe_at_observed`.
- Concrete failure scenario: 80 items × 2 sessions with N16 mean 0.9, discordance 0.2, and perfectly correlated N16 sessions yields estimated κ≈10⁻⁶. The code declares it inside the grid and retains α*=0.001 with `unsafe_at_observed=false`, although its own `cell_feasibility` says the calibrated model cannot realize that nuisance at either loss 0 or 10 pp. Tests vary arm-effect direction and mean/discordance, but not dispersion.
- Proposed change: include dispersion/model feasibility in the hull check; recalibrate every cell when κ changes rather than reusing κ=4 cells; flag observed but unrealizable nuisance combinations for the operator.The checks completed successfully; their results are already reflected in P1 and P3. No further action is needed.
