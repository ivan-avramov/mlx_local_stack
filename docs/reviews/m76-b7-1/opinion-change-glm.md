## Findings

**F1 — MAJOR (confirmed) — Headline P(clean PASS) is at a non-realisable A7 cell; the decision-relevant number is a secondary row.**
Location: `m76_sim.py:1187-1300` (`_joint_scenario`, `_joint`), `report.json` `joint.cells.planning.scenarios.all_loss0.clean_pass`; rendered `REPORT.md` "Joint plan" table row 1.
The headline P(clean PASS) = 39.42% [38.39, 40.44] uses the A7 *planning* cell m=0.965, D=0.1, which is **not realisable** under the data model (`D/2 = 0.05 > min(m, 1−m) = 0.0349`; `axes.A7.planning.pass0_extrapolated = True`). The nearest realisable cell (m=0.96, D=0.05) gives **54.60%** [53.45, 55.73] — above 50%, so the committed plan "pays" on its own at the only cell the data model can produce. The report does show the realisable row (row 2), but the primary/headline row and the per-axis UND rates column (A7 UND 35.68%) are the extrapolated ones.
Problem: an operator who anchors on the 39.42% headline (below 50%) concludes the committed plan is marginal and leans toward a variant, when at the realisable cell the plan is adequate. The operator could choose wrongly (over-invest in a variant) under a condition the spec supports — the spec headlines the extrapolated cell because B7's A7 planning cell is extrapolated by design.
Proposed change: headline the nearest-realisable-cell P(clean PASS) (54.60%) and demote the extrapolated reading to a secondary row, or at minimum state in the table caption that the realisable row is the decision-relevant one. This is a spec-design choice inherited from B7, but B7.1 controls the headline placement.

**F2 — MAJOR (confirmed) — A5-2L's clean PASS is reported only at the extrapolated A7 cell, so the operator cannot compare the variant to the committed plan at the realisable cell.**
Location: `m76_sim.py:1530-1537` (`_variants` builds `a5["clean_pass0"]` from `t0` = the planning/extrapolated terms); `report.json` `variants.A5-2L.clean_pass0` = 0.464373, no `nearest_realisable` key.
The committed plan reports both extrapolated (39.42%) and realisable (54.60%) clean PASS. A5-2L reports only 46.44% (extrapolated). The operator comparing A5-2L (46.44%) to the committed plan at the realisable cell (54.60%) sees A5-2L as *worse*, though at the same (realisable) cell A5-2L dominates (it only replaces the A5 term, 97% vs 82%). The "pays" rule (`a5["pass0"]["lo"] > t0["A5"]["clean"]["hi"]`: 0.9677 > 0.8265) is cell-independent and correctly True, so the *decision* is unaffected — but the clean-PASS magnitude comparison the operator is asked to make "with numbers" is incomplete at the decision-relevant cell.
Proposed change: also compute and render A5-2L's clean_pass0 at the nearest-realisable A7 cell (replace the A7 term in the product with the realisable A7 term), so the variant and the committed plan are comparable at the same cell.

**F3 — MAJOR (confirmed, hypothesis on reachability) — A7-2L's "both looks safe" branch raises `NotImplementedError` and aborts the whole report build.**
Location: `m76_sim.py:1517` (`_variant_a7_2l` end: `raise NotImplementedError("A7-2L: both looks calibrated safe — the five-session interaction flag is not simulated …")`).
Today A7-2L is unavailable (F4), so this branch is unreachable and no test covers it. If a future grid/candidate change or recalibration makes both looks safe, `_b71` → `_variants` → `build_report` aborts, blocking not just the variant but the entire B7.1 (and B7) report. The implementer acknowledges this (IMPLEMENTER-REPORT P1). It should record `"available": True, "flag": "unsimulated"` and continue, not abort.
Proposed change: replace the `raise` with `out.update(available=True, safe=None, flag="unsimulated (five-session interaction flag not modelled in B7.1 v1)", reason=...)` and render the row as "available, flag unsimulated → operator". Add a test that monkeypatches `calibrate_a7_2l` to return safe alphas and asserts the build does not abort.

**F4 — MINOR (confirmed) — The direct-vs-product consistency check is not fail-closed.**
Location: `m76_sim.py:1267-1278` (`_joint_check` sets `consistent` but never raises); `m76_sim.py:1313-1317` (`_joint` stores `check` in the report, build continues).
If a regression makes the direct joint simulation disagree with the product (|z| > 3), the report is written with `consistent: false` but the build succeeds. The implementer's test `test_committed_direct_joint_simulation_agrees_within_mc` asserts `c["consistent"]` on the *committed* report, so a regression is caught at test time — but only if the tests run; a report consumed without the test would carry a silent inconsistency. (The implementer's P4 notes a prior false-inconsistency at 10 pp from a floored variance, now fixed in the variance, not in fail-closed.)
Proposed change: in `build_report`, after `_b71`, assert `all(c["consistent"] for c in joint["direct_check"].values())` (or raise on |z| > Z_CONSISTENT), so the build fails closed.

**F5 — MINOR (confirmed) — `b71=True` is the default, so every existing `build_report`/`write_report` caller (including B7's own tests) now also runs the B7.1 section.**
Location: `m76_sim.py:1611` (`def build_report(reps=REPS, seed=SEED, results=_RESULTS, a5_ns=None, b71=True)`).
`b71=False` reproduces B7 exactly and `test_build_report_without_b71_has_no_new_keys_and_same_b7_part` covers it. B7's golden keys are unchanged. This is a performance/regression-hygiene issue only (B7's suite is slower), not a correctness defect.
Proposed change: default `b71=False` and set `b71=True` only in the CLI / B7.1's own tests.

**F6 — Tests miss (confirmed):**
- No test asserts that the headline clean-PASS is at a non-realisable cell, or that the realisable row is the decision-relevant number (F1). `test_committed_joint_reports_the_required_quantities` asserts `a7_cell.extrapolated is True` and `nearest_realisable` is present, but not which is headline or that the operator is guided to the realisable one.
- No test asserts A5-2L's clean PASS at the realisable cell (F2).
- No test covers the A7-2L `NotImplementedError` branch (F3).
- No test asserts the build fails closed on a `_joint_check` inconsistency (F4).
- The test-writer's frozen `test_m76_b7_1_fe_variants.py::test_a7_two_look_variant_final_look_false_pass10_independent_simulation` asserts `al is not None` (both per-look alphas present); on the candidate's "unavailable" A7-2L (alphas null) it fails. The test-writer acknowledged this (TESTWRITER-REPORT-delivery2 P2: "The A7-2L tests cannot pass at all"). This is a test-side assumption (the spec implies A7-2L is calibratable; the candidate correctly finds it is not), not a candidate defect — but the frozen tests need an unavailable-case branch.

**F7 — Scope requests (beyond the spec, no severity):**
- `one_language10` screen scenario (10 pp in one language, macro 2.5 pp) — `m76_sim.py:981`. The spec asks only for "macro and a 10 pp loss concentrated in one language"; the candidate adds the other reading as a descriptive column (IMPLEMENTER-REPORT P2).
- `grid_ranges_realisable` (min–max across the v1.2 grid) per screen option — `m76_sim.py:1119-1123`. The spec asks for the planning-cell rate; the grid range is extra.
- `a8_path_clean0`, `a8_path_clean_at_loss10`, `clean_pass0` per screen option — `m76_sim.py:1546-1557`. Screen options are "reported only, never applied"; the candidate computes the joint clean PASS for each (helpful, but beyond "per option: trigger rate and detection rate").
- `a1_tier2` GPU input (Math500 +200 ≈ 2.5 h/arm) — `m76_sim.py:997`. The B7.1 spec's GPU input list omits it; the candidate fills it from M76 §9 (IMPLEMENTER-REPORT P3).
- `pays` / `pays_rule` definition — `m76_sim.py:1539-1540`. The spec says "states which variants pay" without defining "pays"; the candidate defines it as the replaced axis term's PASS(0) lower MC bound > the committed upper. Reasonable, but a definition the spec doesn't give.

**Confirmed correct (no finding):**
- Joint composition: product of independent per-axis terms; A8 path = (1−t)+t·q with conservative Π-lo/hi intervals; direct joint simulation agrees (z = −0.15 at loss 0, z = −0.06 at loss 10) — `m76_sim.py:1131-1267`.
- Screen trigger: exact integer comparison `100·s < pp·n`, strict `<`, T0/T1/T2, brute-force enumeration validated — `m76_sim.py:1004-1093`.
- A5-2L OBF spending: t₁ = 0.6 = 3/5, α₁ = 0.003808, α₂ = 0.021192, sum 0.025; exact two-look size 0.021637 ≤ 0.025, cross-checked by independent double enumeration — `m76_sim.py:1332-1438`.
- A7-2L "unavailable" is **correct, not an artefact**: look-1 false-PASS(10) at the smallest candidate α=0.001 is 1.94% (binding `m=0.96|D=0.05|sigma=0`), which exceeds the OBF spend α(3/5) = 0.003808. The point-estimate condition (point ≥ −5 pp at a true 10 pp loss) fires ~1.9% of the time with 3 sessions and is **independent of α** (lowering α only tightens the loss bound, not the point estimate), so no candidate can meet the spend. This is a real statistical property of 3-session look 1 against an OBF spend at t = 0.6 — `m76_sim.py:1463-1519`.
- GPU hours: formula reproduces 48.94 h expected / 65.8 h worst (both arms); sources listed; excludes smokes/idles/pilot/reload/panel as documented — `m76_sim.py:1196-1211`.
- B7 unchanged: `report.json` minus `joint`/`variants` hashes to B7's `dac5869f…`; `REPORT.md` before the "Joint plan" section hashes to `1a8d8250…`; `axis_plan` unchanged except `report_sha256` (unavoidable) — verified.

**Bottom line on the question:** The operator is unlikely to choose wrongly on the *mechanical* safety (every final look is ≤ 0.025; A7-2L correctly fails closed; A5-2L pays). The real risk is F1+F2: the headline and the variant's clean PASS are both at the non-realisable A7 cell (39.42% / 46.44%), while the realisable cell reads 54.60% and A5-2L is not reported there — so an operator who anchors on the headline overestimates the plan's marginality and may over-invest in A5-2L. The report shows the realisable row for the committed plan, which mitigates F1, but F2 (no realisable-cell number for the variant) leaves the variant comparison incomplete at the decision-relevant cell.
