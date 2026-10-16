Review of commit `cc740a03` — `fix(bench): P346 — paired_delta flags a degenerate...`

P1 — should-fix — `benchmark/bench/compare_predictor.py:365-366`  
`_verdict()` still returns `PASS` for any interval inside ±5 pp, including degenerate `[0,0]`. The existing n=5 identical-arm test therefore certifies PASS despite a discordance upper bound around 45%. Fix by returning `INCONCLUSIVE` when `chosen["degenerate"]` is true; update `test_compare_predictor.py:330-339`.

P2 — should-fix — `benchmark/bench/judge_gate.py:373-376`  
The independent judge ranking path still calls deterministic `[0.5,0.5]` ties `equivalent_95ci_within_5pp`. `test_judge_gate.py:345-360` explicitly requires the unsound result. Detect a collapsed interval and report equivalence not established.

P3 — should-fix — `benchmark/bench/agentbench_compare.py:455-459`, `benchmark/bench/run_m1_report.py:178-184`  
Both still publish raw `paired_delta["verdict"]`, so identical arms print `equivalent`. AgentBench’s test at `test_agentbench_compare.py:333-339` locks this behavior in. Apply the same degenerate-aware presentation used by the three regenerated reports.

P4 — should-fix — `docs/campaign-results.md:38`  
The campaign summary still says every M63 cell was “equivalent or inconclusive,” contradicting the corrected reports and README. Change it to “inconclusive or without observed discordance; equivalence not established.”

Checks:
- `lo == hi` correctly detects a collapsed returned percentile interval, though the comment at `stats.py:314` incorrectly equates that with every replicate being identical.
- The bound `1 - 0.05**(1/n)` and n=20–22 report rounding are correct.
- Multi-draw discordance compares per-item means, consistent with independently resampled draws. Add a regression asserting equal multi-draw means with within-item variation are non-degenerate and receive no bound.
- All 22 regenerated report changes are label-only; README wording is accurate.
- Targeted suite: 216 passed.

cleared after fixes P1, P2, P3, P4
