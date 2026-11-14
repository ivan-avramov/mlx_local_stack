"""M76 B7.1 (implementer): the joint operating characteristics of the committed stage-3 plan (criterion 1) and the
committed report's joint section."""
import hashlib
import json
import math
from pathlib import Path

import pytest

from bench import m76_rule as R
from bench import m76_sim as M

REPORT = Path(M.__file__).resolve().parent.parent / "results" / "m76" / "b7-simulation"
B7_REPORT_JSON_SHA = "dac5869f4355d5b09dd6b7c0fc9382dafd05f777ffd04897fd1944708b28ded2"   # B7 at 4120d3c8
B7_REPORT_MD_SHA = "1a8d82506a051f53097e5fda9b9cf7ac1f755d36a1aeb8a8636c9d8a1c3cd1ef"


def _committed():
    return json.loads((REPORT / "report.json").read_text())


def _r(rate, lo=None, hi=None, k=None, n=None):
    return dict(rate=rate, lo=rate if lo is None else lo, hi=rate if hi is None else hi, k=k, n=n)


# ------------------------------------------------------------------------------------------------ unit
def test_product_is_independent_product_with_conservative_interval():
    terms = [_r(0.9, 0.88, 0.92), _r(0.5, 0.49, 0.51), _r(0.8, 0.79, 0.81)]
    p = M._product(terms)
    assert p["rate"] == pytest.approx(0.9 * 0.5 * 0.8)
    assert p["lo"] == pytest.approx(0.88 * 0.49 * 0.79) and p["hi"] == pytest.approx(0.92 * 0.51 * 0.81)
    assert p["se"] > 0


def test_term_clean_subtracts_pass_with_flag():
    blk = {v: dict(k=k, n=100, rate=k / 100, lo=0, hi=1) for v, k in (("PASS", 60), ("LOSS", 1), ("UNDECIDED", 39))}
    flag = dict(pass_with_flag=dict(k=4, n=100))
    t = M._term_from(blk, flag)
    assert t["clean"]["k"] == 56 and t["clean"]["rate"] == pytest.approx(0.56)
    assert M._term_from(blk)["clean"] is blk["PASS"]


def test_plan_hours():
    h = M._plan_hours(0.37, (72,), 0.0, (3,), 0.0, 0.5)
    per_arm = 3.3 + 2.5 * 0.37 + 4.0 + 2.7 * 3 + 3.0 + 12.0 * 0.5
    assert h["expected"] == pytest.approx(2 * per_arm)
    assert h["worst"] == pytest.approx(2 * (3.3 + 2.5 + 4.0 + 2.7 * 3 + 3.0 + 12.0))
    h2 = M._plan_hours(0.37, (72, 120), 0.2, (3, 5), 0.4, 0.5)
    per2 = 3.3 + 2.5 * 0.37 + 4.0 * (72 + 48 * 0.2) / 72 + 2.7 * (3 + 2 * 0.4) + 3.0 + 12.0 * 0.5
    assert h2["expected"] == pytest.approx(2 * per2)
    assert h2["whole_stage_expected"] == pytest.approx(2 * per2 + 2 * 0.3 + 5.0)


# --------------------------------------------------------------------------------------- committed report
def test_committed_joint_equals_product_of_axis_terms():
    """Criterion 1: P(clean PASS) = Π per-axis simulated terms (independence across axes), at loss 0 and 10 pp: A1
    and A7 from B7's per-axis results, A5 = PASS ∧ per-task gates (same stream as B7's A5), the A8 path from the
    nested screen → decider simulation."""
    rep = _committed()
    ax = rep["axes"]
    j = rep["joint"]
    pl = j["cells"]["planning"]
    for L, scen in (("0.0", "all_loss0"), ("0.1", "all_loss10")):
        key = f"sigma=0.25|loss={L}"
        a1 = ax["A1"]["cells"][key][ax["A1"]["final"]]["PASS"]["rate"]
        g = j["a5_gates"][f"loss={L}"]
        a5 = g["counts"]["G"] / g["reps"]
        c7 = ax["A7"]["cells"][key]
        a7 = (c7["single"]["PASS"]["k"] - c7["flag"]["pass_with_flag"]["k"]) / c7["single"]["PASS"]["n"]
        p8 = M.a8_path_from(j["a8_nested"][f"loss={L}"]["hist"], j["a8_nested"][f"loss={L}"]["reps"], "TD",
                            M.HEADLINE_HOLD)["clean"]["rate"]
        want = a1 * a5 * a7 * p8
        assert pl["scenarios"][scen]["clean_pass"]["rate"] == pytest.approx(want, abs=2e-6)
        terms = pl["terms"][f"loss={L}"]
        assert terms["A7"]["clean"]["rate"] == pytest.approx(a7, abs=1e-6)
        assert terms["A8_path"]["clean"]["rate"] == pytest.approx(p8, abs=1e-6)


def test_committed_direct_joint_simulation_agrees_within_mc():
    """Criterion 1: the direct joint simulation of the same plan agrees with the product within MC bounds."""
    chk = _committed()["joint"]["direct_check"]
    assert len(chk) == 12
    for c in chk.values():
        assert c["direct"]["n"] >= 20000
        assert c["consistent"] and abs(c["z"]) <= M.Z_CONSISTENT
    c0 = chk[f"nearest_realisable|loss=0.0|{M.HEADLINE_HOLD}"]
    assert c0["direct"]["lo"] <= c0["product"]["rate"] <= c0["direct"]["hi"]


def test_fresh_direct_joint_agrees_with_committed_product():
    rep = _committed()
    prod = rep["joint"]["cells"]["planning"]["scenarios"]["all_loss0"]["clean_pass"]
    d = M.simulate_joint(rep["axes"], 0.0, 1500, seed=4321)
    p = d["counts"][f"clean|{M.HEADLINE_HOLD}"] / d["reps"]
    se = math.sqrt(p * (1 - p) / d["reps"] + prod["se"] ** 2)
    assert abs(p - prod["rate"]) <= 4 * se


def test_committed_joint_reports_the_required_quantities():
    rep = _committed()
    j = rep["joint"]
    assert j["spec"] == M.B71_SPEC == "docs/specs/m76-b7-1-joint-plan.md v1.4"
    assert j["sigma"] == 0.25 and j["option"] == "TD"
    pl = j["cells"]["planning"]
    assert pl["a7_cell"]["extrapolated"] is True
    assert "nearest_realisable" in j["cells"]
    for L in ("loss=0.0", "loss=0.1"):
        t = pl["terms"][L]
        for ax in ("A1", "A5", "A7", "A8_decider"):
            assert set(t[ax]) >= {"PASS", "UNDECIDED", "LOSS", "clean"}
            tot = sum(t[ax][v]["k"] for v in ("PASS", "UNDECIDED", "LOSS"))
            assert tot == t[ax]["PASS"]["n"]
            assert t[ax]["clean"]["k"] <= t[ax]["PASS"]["k"]
        assert {"clean", "trigger", "triggered_UNDECIDED", "decider_clean_given_trigger"} <= set(t["A8_path"])
    sc = pl["scenarios"]
    assert set(sc) == {"all_loss0", "all_loss10"} | {f"only_{a}_loss10" for a in ("A1", "A5", "A7", "A8")}
    assert sc["all_loss0"]["panel_bound"] == pytest.approx(max(0.0, sc["all_loss0"]["clean_pass"]["rate"] - 0.05),
                                                           abs=1e-6)
    s = j["screen"]
    assert set(s["planning"]) == {"loss0", "macro10", "concentrated10", "one_language10"}
    assert len(s["grid"]) == 24 and {c["sigma"] for c in s["grid"].values()} == {0.0, 0.25}
    h = j["hours"]
    assert h["best"] <= h["expected"] <= h["worst"]
    assert set(j["gpu_hours_inputs"]) == set(M.GPU_HOURS)


def test_committed_screen_exact_agrees_with_simulation():
    s = _committed()["joint"]["screen"]["planning"]
    for name, blk in s.items():
        for o in ("T0", "T1", "T2"):
            r, ex = blk["rates"][o], blk["exact"][o]
            se = math.sqrt(max(ex * (1 - ex), 1e-6) / r["n"])
            assert abs(r["rate"] - ex) <= 4 * se + 2e-3, (name, o, r, ex)


def test_committed_report_md_has_joint_section_and_tables():
    rep = _committed()
    md = (REPORT / "REPORT.md").read_text()
    assert md == M.render_md(rep)
    sec = md[md.index("## Joint plan (B7.1)"):]
    assert "| plan / variant | clean PASS at loss 0, A7 nearest realisable cell" in sec
    assert "| option | trigger at loss 0 |" in sec
    for o in ("T0", "T1", "T2"):
        assert f"| {o}: " in sec
    assert "| A5-2L " in sec and "| A7-2L " in sec and "| A7-5S " in sec


# ------------------------------------------------------------------------------- criterion 3: B7 unchanged
def test_committed_report_minus_new_keys_is_b7_byte_for_byte():
    rep = _committed()
    assert {"joint", "variants"} <= set(rep)
    b7 = {k: v for k, v in rep.items() if k not in ("joint", "variants")}
    text = json.dumps(b7, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    assert hashlib.sha256(text.encode()).hexdigest() == B7_REPORT_JSON_SHA


def test_committed_report_md_before_joint_section_is_b7_byte_for_byte():
    md = (REPORT / "REPORT.md").read_bytes()
    cut = md.index("\n## Joint plan (B7.1)".encode())
    assert hashlib.sha256(md[:cut]).hexdigest() == B7_REPORT_MD_SHA


def test_axis_plan_unchanged():
    p1 = R.axis_plan("A1")
    assert [(lk["size"], round(lk["alpha"], 6)) for lk in p1["looks"]] == [(100, 0.000104), (300, 0.024896)]
    p7 = R.axis_plan("A7")
    assert not p7["two_look"] and [lk["alpha"] for lk in p7["looks"]] == [0.001] and p7["looks"][0]["size"] == 3
    p8 = R.axis_plan("A8")
    assert [lk["alpha"] for lk in p8["looks"]] == [0.001] and p8["calibrated_alpha_star"] == 0.005
    p5 = R.axis_plan("A5")                      # v1.4 (C339): the registered A5-2L two looks
    assert [(lk["size"], lk["alpha"]) for lk in p5["looks"]] == [(72, 0.003808), (120, 0.021192)]
    p5b7 = R.axis_plan("A5", n=72)              # B7's single look, unchanged
    assert [(lk["size"], lk["alpha"]) for lk in p5b7["looks"]] == [(72, 0.025)]


def test_build_report_without_b71_has_no_new_keys_and_same_b7_part():
    a = M.build_report(reps=120, a5_ns=[42, 72])
    b = M.build_report(reps=120, a5_ns=[42, 72], b71=True)
    assert "joint" not in a and "variants" not in a
    assert {k: v for k, v in b.items() if k not in ("joint", "variants")} == a
