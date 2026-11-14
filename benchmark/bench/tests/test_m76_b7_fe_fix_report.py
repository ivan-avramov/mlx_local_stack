"""M76 B7 (spec v1.2 / v1.3) — adopted finding 4 and the amendments' report acceptance: A8's alpha* 0.001 and its
labels, A7's planning-cell label, the capped A8 grid, the committed report's consistency with `axis_plan`.

These read the COMMITTED `benchmark/results/m76/b7-simulation/` files (generated; never edited by a test). Class (c):
the report schema is not in the specification — keys are those the candidate documents (`alpha_star_fixed`,
`residual_cells`, `calibration`, `planning`); the specification-stated facts asserted are the values.
"""
import json
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2]
OUT = BENCH / "results" / "m76" / "b7-simulation"


def _report():
    p = OUT / "report.json"
    assert p.is_file(), f"no committed report at {p}"
    return json.loads(p.read_text())


def _md():
    p = OUT / "REPORT.md"
    assert p.is_file(), f"no committed report at {p}"
    return p.read_text()


def test_axis_plan_a8_is_the_operator_fixed_001():  # (a) v1.3 acceptance
    from bench.m76_rule import axis_plan
    plan = axis_plan("A8")
    assert plan["alpha_star"] == pytest.approx(0.001)
    assert len(plan["looks"]) == 1 and plan["looks"][0]["alpha"] == pytest.approx(0.001)
    assert plan["looks"][0]["interval_alpha"] == pytest.approx(0.002)
    assert plan["two_look"] is False


def test_a8_calibration_runs_on_the_capped_grid_and_reports_005_as_context():  # (a) v1.2 / v1.3
    from bench.m76_rule import axis_plan
    cal = _report()["axes"]["A8"]["calibration"]
    assert sorted(cal["grid"]["sigmas"]) == [0.0, 0.25]
    assert 0.5 in cal["grid"].get("sensitivity_sigmas", [])
    assert cal["alpha_star"] == pytest.approx(0.005)
    assert axis_plan("A8").get("calibrated_alpha_star") == pytest.approx(0.005)


def test_a8_report_lists_residual_cells_over_alpha_at_001():  # (a) v1.3 + finding 4
    a8 = _report()["axes"]["A8"]
    assert a8.get("alpha_star_fixed") == pytest.approx(0.001)
    residual = a8["residual_cells"]
    assert residual, "the SD 0.5 cells over 0.025 at alpha 0.001 must be listed"
    items = residual.items() if isinstance(residual, dict) else enumerate(residual)
    for key, cell in items:
        if isinstance(cell, dict):
            hi = next((v for k, v in cell.items() if "hi" in k.lower() and isinstance(v, (int, float))), None)
            if hi is not None:
                assert hi > 0.025, (key, cell)
    text = _md()
    assert "C336" in text and "residual" in text.lower()


def test_a7_planning_cell_is_labelled_not_realisable_and_extrapolated():  # (a) finding 4
    a7 = _report()["axes"]["A7"]
    assert a7["planning"]["feasible"] is False
    assert a7["planning"]["infeasible_reasons"]
    text = _md().lower()
    assert "extrapolat" in text
    assert "not realisable" in text


def test_committed_report_a7_alpha_matches_plan_and_sha():  # (a) axis_plan reads the committed report
    from bench.m76_rule import REPORT_JSON, axis_plan, load_report
    rep, sha = load_report()
    assert REPORT_JSON.is_file()
    plan = axis_plan("A7")
    assert plan["report_sha256"] == sha
    assert plan["alpha_star"] == pytest.approx(rep["axes"]["A7"]["calibration"]["alpha_star"])
    assert axis_plan("A5")["items"] == rep["axes"]["A5"]["n"]


def test_report_headline_numbers_are_internally_consistent():  # (a) a regenerated report must not contradict its plan
    rep = _report()
    for ax in ("A1", "A5", "A7", "A8"):
        assert ax in rep["axes"]
    assert rep["axes"]["A5"]["n"] % 6 == 0 and 42 <= rep["axes"]["A5"]["n"] <= 120
    assert rep["axes"]["A5"]["exact_size"] <= 0.025
    for ax in ("A7", "A8"):
        cal = rep["axes"][ax]["calibration"]
        assert cal["alpha_star"] in cal["candidates"]


def test_report_states_final_plan_and_the_a8_001_in_markdown():  # (a) acceptance 8
    text = _md()
    assert "0.001" in text and "A8" in text
    assert "Final plan" in text
