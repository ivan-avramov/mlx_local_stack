Q1 — BLOCKER — `benchmark/m64/power_sim.py:50-56,98-110`  
Failure: the 0.16–0.18 boundary false-pass rate is genuine anti-conservatism, not clamping. At \(p_d=|\Delta|=.05\), no reference is clamped and \(K\sim Binomial(86,.05)\). The shift bootstrap passes for \(K=1\) or \(2\):

\[
P(K\in\{1,2\})=0.177867
\]

This exactly explains the report; the pick difference is Monte Carlo noise from only 400 simulations.  
Fix: replace bootstrap TOST with an exact unconditional matched-pair risk-difference TOST, maximizing over the discordance nuisance parameter, or a constrained-null test calibrated over sparse-boundary scenarios. The pooled alternative is invalid until then.

Q2 — HIGH — `benchmark/bench/stats.py:302-320`, `benchmark/bench/compare_predictor.py:365-369`  
Failure: `paired_delta` uses a different, 95% percentile rule, but it is also anti-conservative. Under the same n=86 boundary, raw false equivalence is about 6.71%; P346 removes the zero-discordance case but leaves the nondegenerate \(K=1\) case at 5.50%. Thus nondegenerate `equivalent`/`PASS` decisions can falsely certify a regression at the −5 pp margin.  
Fix: use the calibrated exact interval/test in `paired_delta`; meanwhile suppress positive equivalence verdicts for sparse binary cells. Regrade existing saved rows and audit decisions—no model reruns are needed.

Q3 — MEDIUM — `benchmark/m64/power_sim.py:59-83,89-90`  
Failure: the joint table and sampling are algebraically correct: marginals are \(r\) and \(r+\Delta\), discordance is \(p_d\), and \(E[C-R]=\Delta\). Exact cell sizes 21/22 are preserved and discreteness is simulated correctly. But clamping materially changes the claimed reference population: at Δ=0, \(p_d=.182\) clamps ceiling references to .909; \(p_d=.303\) clamps them to .8485. Those are not c144-base’s 95.5–100% references.  
Fix: sample differences directly as \(\{-1,0,+1\}\) with probabilities \(((p_d-\Delta)/2,1-p_d,(p_d+\Delta)/2)\). Reference accuracy is irrelevant to this statistic. If joint marginals are required, model uncertainty in latent reference accuracy and report infeasible scenarios instead of silently projecting them.

Q4 — MEDIUM — `benchmark/m64/power_sim.py:88-109`, `docs/specs/m64-scaffold-arms.md:302-304`  
Failure: every session/language cell is generated independently. Resampling sessions during analysis does not simulate shared loaded-instance effects, despite the spec requiring their validation; with two sessions, pooled calibration is especially fragile.  
Fix: add a session-level random-effect/correlation sensitivity grid and retain per-session inference as primary.

Q5 — MEDIUM — `benchmark/bench/tests/test_p357_power_sim.py:18-70`  
Failure: the helper tests are substantively useful, but every red-first failure was an `AttributeError` on new symbols. They do not prove that `run()` uses the corrected sampler; correct-but-unused helpers would pass.  
Fix: add a behavioral test through the production generation seam. Across repeated `run()` draws it should assert mean generated cell delta≈requested Δ, discordance split≈\((p_d±Δ)/2\), exact cell n, and that the corrected path—not a fixed-reference flip—is invoked. Add a lightweight deterministic report-wiring test.

Q6 — HIGH — `docs/open-questions.md:22,40`, `docs/specs/m64-scaffold-arms.md:276-278`, `benchmark/m64/POWER_SIM.md:38`  
Failure: P347’s raw regenerated figures and 7/172 correction are accurate, but its interpretation is not. It must identify 0.16–0.18 as failed calibration, not merely report “type-I error”; the “ceiling—challenger can only lose” explanation no longer describes the clamped Δ=0 simulation. The spec also retains stale 0.30–0.34 power. Finally, “0.000” from 0/400 needs either an exact discreteness proof or a Monte Carlo interval.  
Fix: state that the pooled rule is invalid, preserve P347’s estimation-only conclusion, synchronize the spec, and report Monte Carlo uncertainty.

VERDICT: NOT CLEARED
