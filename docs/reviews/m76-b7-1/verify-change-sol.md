P2 — Resolved: A8 nesting  
- Location: `benchmark/bench/m76_sim.py:1175-1287`
- Severity: none
- Evidence: confirmed
- Problem: One item set is now drawn per replication; the screen reads its prefix and the decider all 80 items.
- Failure scenario: none remaining.
- Proposed change: none.

P3 — Resolved: A5 point gates  
- Location: `benchmark/bench/m76_sim.py:1302-1352,1603-1626`
- Severity: none
- Evidence: confirmed
- Problem: Clean PASS now requires both task estimates ≥−5 pp, including A5-2L.
- Failure scenario: none remaining.
- Proposed change: none.

P4 — Resolved: A8 HOLD  
- Location: `benchmark/bench/m76_sim.py:979-984,1203-1270`
- Severity: none
- Evidence: confirmed
- Problem: All three requested thresholds are reported and the headline names `<−20 pp`.
- Failure scenario: none remaining.
- Proposed change: none.

P5 — Resolved: whole-stage GPU hours  
- Location: `benchmark/bench/m76_sim.py:1370-1389`; `benchmark/results/m76/b7-simulation/REPORT.md:292-307`
- Severity: none
- Evidence: confirmed
- Problem: Separate modelled-leg and whole-stage columns include the 5.6 mandatory hours.
- Failure scenario: none remaining.
- Proposed change: none.

P6 — Resolved: realisable headline  
- Location: `benchmark/bench/m76_sim.py:985,1480-1533`
- Severity: none
- Evidence: confirmed
- Problem: The nearest realisable A7 cell is the headline; the extrapolated planning cell is secondary.
- Failure scenario: none remaining.
- Proposed change: none.

P7 — Resolved: A5-2L comparison cell  
- Location: `benchmark/bench/m76_sim.py:1781-1838`
- Severity: none
- Evidence: confirmed
- Problem: A5-2L reports clean PASS at both A7 cells.
- Failure scenario: none remaining.
- Proposed change: none.

P8 — Resolved: A7-2L available branch  
- Location: `benchmark/bench/m76_sim.py:1730-1778`
- Severity: none
- Evidence: confirmed
- Problem: A safe calibration records availability and the unsimulated interaction flag without aborting.
- Failure scenario: none remaining.
- Proposed change: none.

P9 — Resolved: consistency check  
- Location: `benchmark/bench/m76_sim.py:1452-1511`
- Severity: none
- Evidence: confirmed
- Problem: The build raises when any direct/product check exceeds `|z|=3`.
- Failure scenario: none remaining.
- Proposed change: none.

P10 — Resolved: `b71` default  
- Location: `benchmark/bench/m76_sim.py:1899-1950`
- Severity: none
- Evidence: confirmed
- Problem: Library entry points default to `b71=False`; the CLI opts in.
- Failure scenario: none remaining.
- Proposed change: none.

P11 — Resolved: retained scope extras  
- Location: `benchmark/bench/m76_sim.py:995-999,1123-1155,1801-1875`
- Severity: none
- Evidence: confirmed
- Problem: The one-language reading, grid ranges, per-option clean PASS, and `pays` rule remain present.
- Failure scenario: none remaining.
- Proposed change: none.

P12 — The committed plan ignores C338  
- Location: `docs/specs/m76-tq4-certification.md:286-288`; `benchmark/bench/m76_sim.py:1341-1352,1393-1515,1529,1823-1875`; `benchmark/bench/tests/test_m76_b7_1_impl_joint.py:100-103`; `benchmark/bench/tests/test_m76_b7_1_impl_variants.py:149-160`
- Severity: major
- Evidence: confirmed
- Problem: C338 requires the decider on every plan, but the candidate commits T0 and treats TD as an unapplied option. Tests explicitly pin the superseded behavior. The report also identifies the governing joint specification as v1.1 although the file is v1.2.
- Failure scenario: The operator sees 49.11% clean PASS, 21.23% triggered-decider UNDECIDED, and 54.5 expected whole-stage hours. Under C338, the report’s own TD results are 30.28%, approximately 48.93%, and 68.3 hours. A5-2L similarly changes from 62.23% to 38.37%; A7-5S under TD is not reported.
- Proposed change: Make TD the committed path throughout products, direct checks, variants, hours, rendering, and tests; demote T0–T3 to alternatives and update the specification authority/version.

P13 — A7-5S has no actual clean-PASS result  
- Location: `benchmark/bench/m76_sim.py:1730-1778,1840-1849`; `benchmark/results/m76/b7-simulation/REPORT.md:293-310`
- Severity: major
- Evidence: confirmed
- Problem: Its “clean PASS” uses raw A7 PASS while omitting the blocking five-session interaction flag. The upper-bound warning and `pays=undetermined` avoid a false recommendation, but leave the requested variant comparison unresolved.
- Failure scenario: Flagged five-session passes are included in the displayed 56.42%, so the operator cannot determine whether A7-5S actually improves ship-eligible clean PASS.
- Proposed change: Simulate the five-session interaction flag and recompute the row, or mark A7-5S unavailable and omit its clean-PASS estimate.

P14 — “Worst final-look” omits the accepted A8 sensitivity residual  
- Location: `benchmark/bench/m76_sim.py:951-967,1878-1887`; `benchmark/results/m76/b7-simulation/REPORT.md:210-266,292-296`
- Severity: minor
- Evidence: confirmed
- Problem: The joint table reports 2.23% as the worst upper bound, while three realisable SD=0.5 A8 sensitivity cells reach 2.819%. C336 accepts these outside the committed v1.2 grid and the report discloses them elsewhere, but the table heading is unqualified.
- Failure scenario: A reader scanning only the decision table concludes every simulated realisable cell is ≤2.5%.
- Proposed change: Rename the column “worst on committed grid” and surface the C336 SD=0.5 residual beside every plan containing A8.
