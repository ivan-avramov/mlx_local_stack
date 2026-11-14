"""M76 B7.1 (implementer): spec amendment v1.3 — TD is the committed A8 path (C338), A7-5S reports no clean-PASS estimate,
the worst final look is "worst on the committed grid" with the C336 A8 residual beside it."""
import inspect
import json
from pathlib import Path

import pytest

from bench import m76_sim as M

REPORT = Path(M.__file__).resolve().parent.parent / "results" / "m76" / "b7-simulation"
CELLS = ("nearest_realisable", "planning")
NOTE_5S = "clean PASS not estimated (interaction flag unsimulated)"


def _committed():
    return json.loads((REPORT / "report.json").read_text())


def _md_joint():
    md = (REPORT / "REPORT.md").read_text()
    return md[md.index("## Joint plan (B7.1)"):]


# ------------------------------------------------------------------------------------------- TD committed (C338)
def test_committed_option_is_td_and_spec_v13():
    assert M.COMMITTED_OPTION == "TD"
    assert M.B71_SPEC == "docs/specs/m76-b7-1-joint-plan.md v1.4"      # v1.4 supersedes the v1.3 header
    assert inspect.signature(M.simulate_joint).parameters["option"].default == "TD"
    assert inspect.signature(M.a8_path_from).parameters["option"].default == "TD"


def test_simulate_joint_td_always_runs_the_decider():
    rep = _committed()
    d = M.simulate_joint(rep["axes"], 0.0, 200, seed=17)
    assert d["option"] == "TD" and d["counts"]["trig"] == 200


def test_committed_joint_uses_td_throughout():
    rep = _committed()
    j = rep["joint"]
    assert j["spec"] == M.B71_SPEC and j["option"] == "TD"
    for cell in CELLS:
        for L in ("loss=0.0", "loss=0.1"):
            t = j["cells"][cell]["terms"][L]
            assert t["A8_path_by_hold"] == j["a8_nested"][L]["paths"]["TD"]
            assert t["A8_path"] == j["a8_nested"][L]["paths"]["TD"][M.HEADLINE_HOLD]
            assert t["A8_path"]["trigger"]["rate"] == 1.0
    for chk in j["direct_check"].values():
        assert chk["direct_terms"]["trig"]["rate"] == 1.0


def test_committed_hours_run_the_decider_always():
    rep = _committed()
    j = rep["joint"]
    p_a1 = (rep["axes"]["A1"]["cells"]["sigma=0.25|loss=0.0"]["look1"]["UNDECIDED"]["rate"]
            if rep["axes"]["A1"]["final"] == "two_look" else None)
    want = M._plan_hours(p_a1, (rep["axes"]["A5"]["n"],), 0.0, (3,), 0.0, 1.0)
    for k in ("expected", "worst", "whole_stage_expected", "whole_stage_worst"):
        assert j["hours"][k] == pytest.approx(want[k], abs=1e-6)


def test_committed_headline_equals_td_option_and_alternatives_superseded():
    rep = _committed()
    opts = rep["variants"]["screen_options"]
    td = opts["TD"]
    assert td["committed"] is True
    assert td["clean_pass0"]["rate"] == pytest.approx(rep["joint"]["headline"]["clean_pass"]["rate"], abs=1e-6)
    assert td["clean_pass0_by_cell"] == {
        c: rep["joint"]["cells"][c]["scenarios"]["all_loss0"]["clean_pass_by_hold"] for c in rep["joint"]["cells"]}
    assert td["hours"] == rep["joint"]["hours"]
    for name in ("T0", "T1", "T2", "T3"):
        assert opts[name]["committed"] is False and "superseded by C338" in opts[name]["status"]


def test_committed_variants_use_td_path():
    rep = _committed()
    j, a5 = rep["joint"], rep["variants"]["A5-2L"]
    t = j["cells"]["nearest_realisable"]["terms"]["loss=0.0"]
    want = (t["A1"]["clean"]["rate"] * a5["clean0"]["rate"] * t["A7"]["clean"]["rate"] *
            j["a8_nested"]["loss=0.0"]["paths"]["TD"][M.HEADLINE_HOLD]["clean"]["rate"])
    assert a5["clean_pass0"]["rate"] == pytest.approx(want, abs=2e-6)
    assert rep["variants"]["screen_options"]["TD"]["clean_pass0_a5_2l"] == a5["clean_pass0"]
    assert a5["hours"]["expected"] == pytest.approx(rep["variants"]["screen_options"]["TD"]["hours_a5_2l"]["expected"],
                                                    abs=1e-6)


def test_md_names_v13_and_td_committed():
    sec = _md_joint()
    assert "docs/specs/m76-b7-1-joint-plan.md v1.4" in sec              # v1.4 supersedes the v1.3 header
    assert "TD (C338)" in sec
    assert "superseded by C338" in sec


# ------------------------------------------------------------------------------------------------- A7-5S
def test_committed_a7_5s_has_no_clean_pass_estimate():
    v = _committed()["variants"]["A7-5S"]
    assert v["available"] and v["safe"]
    assert v["clean_pass0"] is None and v["clean_pass0_by_cell"] is None and v["delta_clean_pass0"] is None
    assert v["clean_pass_note"] == NOTE_5S
    assert v["pays"] is None
    for c in CELLS:
        assert v["pass0_by_cell"][c] == v["by_cell"][c]["single"]["PASS"]
    assert v["hours"]["expected"] > 0


def test_md_a7_5s_row_reports_own_pass_and_note():
    sec = _md_joint()
    row = next(line for line in sec.splitlines() if line.startswith("| A7-5S "))
    assert NOTE_5S in row and "undetermined" in row
    v = _committed()["variants"]["A7-5S"]
    assert M._rng3(v["pass0_by_cell"]["nearest_realisable"]) in row


# ------------------------------------------------------------------------------------------- worst final look
def test_plan_worst_carries_committed_grid_and_a8_residual():
    rep = _committed()
    w = M._plan_worst_fp10(rep["axes"])
    assert w["grid"] == "committed"
    r = w["a8_residual"]
    res = rep["axes"]["A8"]["residual_cells"]
    assert r["cells"] == len(res) == 3
    assert r["max_hi"] == pytest.approx(max(c["hi"] for c in res.values()))
    assert r["max_hi"] == pytest.approx(0.028194, abs=1e-6)
    assert "C336" in r["text"]
    w2 = M._with_axis(w, "A5", 0.001)
    assert w2["a8_residual"] == r and w2["grid"] == "committed"


def test_committed_every_plan_shows_the_residual():
    rep = _committed()
    r = rep["joint"]["worst_final_false_pass10"]["a8_residual"]
    for name in ("A5-2L", "A7-5S"):
        assert rep["variants"][name]["worst_final_false_pass10"]["a8_residual"] == r
    sec = _md_joint()
    hdr = next(line for line in sec.splitlines() if line.startswith("| plan / variant |"))
    assert "worst on the committed grid" in hdr and "final-look" not in hdr
    for lab in ("| committed plan", "| A5-2L ", "| A7-5S "):
        row = next(line for line in sec.splitlines() if line.startswith(lab))
        assert "C336 residual: 3 realisable SD 0.5 cells, up to 2.82 %" in row
