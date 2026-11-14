"""M76 B7.1 spec v1.1 erratum items: both A7 cells per row with the realisable one as headline; A7-5S; A7-2L's available
branch; fail-closed consistency; `build_report(b71=False)` by default; whole-stage GPU hours.

Class (a): stated by the erratum; (b): independent reference built here; (c): through the candidate's layout. All of the
(c) / (b) comparisons against the report use the COMMITTED 20,000-replication report unless stated.
"""
import inspect
import math
import random

import pytest

from bench.tests.test_m76_b7_1_fe_support import _need, committed_report, mc_tol


# ------------------------------------------------------------------------------------------------------- both cells
def test_both_a7_cells_are_reported_and_the_realisable_one_is_the_headline():  # (a)
    rep = committed_report()
    j = rep["joint"]
    nr = rep["axes"]["A7"]["planning"]["nearest_realisable"]
    assert set(j["cells"]) == {"nearest_realisable", "planning"}
    assert j["headline"]["cell"] == "nearest_realisable"
    assert j["headline"]["a7_cell"] == dict(m=nr["m"], D=nr["D"], extrapolated=False)
    assert j["cells"]["planning"]["a7_cell"]["extrapolated"] is True
    assert "headline" in j["cells"]["nearest_realisable"]["role"] and "extrapolated" in j["cells"]["planning"]["role"]
    head = j["cells"]["nearest_realisable"]["scenarios"]["all_loss0"]["clean_pass"]
    assert j["headline"]["clean_pass"] == head
    assert j["headline"]["hold"] == "lt20"          # labelled with the threshold it assumes


def test_nearest_cell_a7_term_agrees_with_b7s_nearest_realisable_pass():  # (c)
    """The A7 term at the nearest realisable cell (σ 0.25, loss 0): its PASS rate is B7's own nearest-cell PASS(0) (same cell,
    same planning α*), within MC; PASS ∧ no flag is below it."""
    rep = committed_report()
    nr = rep["axes"]["A7"]["planning"]["nearest_realisable"]["pass0"]["rate"]
    t = rep["joint"]["cells"]["nearest_realisable"]["terms"]["loss=0.0"]["A7"]
    assert abs(t["PASS"]["rate"] - nr) <= mc_tol(nr, 20000, 20000)
    assert t["clean"]["rate"] <= t["PASS"]["rate"] and t["clean"]["k"] <= t["PASS"]["k"]


def _cells_have_both(grid):
    assert set(grid) == {"nearest_realisable", "planning"}
    for c in grid.values():
        assert set(c) == {"none", "lt25", "lt20"}


def test_every_variant_row_reports_both_cells():  # (a)
    v = committed_report()["variants"]
    _cells_have_both(v["A5-2L"]["clean_pass0_by_cell"])
    for o in ("T0", "T1", "T2"):
        _cells_have_both(v["screen_options"][o]["clean_pass0_by_cell"])
    if v["A7-2L"]["available"]:
        _cells_have_both(v["A7-2L"]["clean_pass0_by_cell"])
    # AMENDED (spec v1.3): A7-5S's five-session interaction flag is unsimulated, so it has NO clean-PASS estimate in any cell
    a5s = v["A7-5S"]
    assert a5s.get("clean_pass0_by_cell") is None and a5s.get("clean_pass0") is None
    assert a5s["pays"] is None or a5s["pays"] is False


def test_report_md_table_has_headline_and_extrapolated_columns():  # (a)
    from bench.tests.test_m76_b7_1_fe_support import COMMITTED
    md = (COMMITTED / "REPORT.md").read_text()
    sec = md[md.index("## Joint plan"):]
    assert "headline" in sec and "extrapolated" in sec and "nearest realisable" in sec
    assert "A7-5S" in sec and "A7-2L" in sec and "HOLD" in sec


# ----------------------------------------------------------------------------------------------------------- A7-5S
def test_a7_5s_is_reported_as_one_look_over_five_sessions():  # (a)
    v = committed_report()["variants"]["A7-5S"]
    assert v["sessions"] == 5 and v["seeds"] == [1001, 2002, 3003, 4004, 5005]
    assert len(v["looks"]) == 1 and v["looks"][0]["sessions"] == 5 and v["looks"][0]["fraction"] == 1.0
    assert v["available"] is True and 0.0 < v["looks"][0]["alpha"] <= 0.025
    assert v["safe"] is True and v["final_false_pass10_hi"] <= 0.025
    assert v["flag"] == "five-session interaction flag not simulated"


def _five_session_false_pass(alpha, m, d, sigma, kappa, reps, seed):
    from bench import m76_sim as M
    model = M.Model("A7", d, 0.10, sigma, M.cell_beta(m, kappa))
    rng = random.Random(f"b71-fix-5s:{seed}:{m!r}:{d!r}:{sigma!r}")
    k = 0
    for _ in range(reps):
        rows = M._gen(model, 43, 5, lambda i, s: s, rng)
        code = M.verdict_vector([sum(r) for r in rows], 43, 5, any(x for r in rows for x in r), alphas=(alpha,))
        k += code == "P"
    return k / reps


def test_a7_5s_alpha_is_safe_on_a7s_grid_in_independent_simulation():  # (b)
    """At the candidate's α* the one-look five-session rule keeps false-PASS(10) ≤ 0.025 on A7's grid in my own
    simulation (screen 150 replications per realisable cell; the three worst re-run at 1500; tolerant bound
    0.025 + 3·sqrt(0.025·0.975/1500) = 0.0368)."""
    from bench import m76_sim as M
    rep = committed_report()
    alpha = rep["variants"]["A7-5S"]["looks"][0]["alpha"]
    cal = rep["axes"]["A7"]["calibration"]
    g, kappa = cal["grid"], cal["kappa"]
    cells = [(m, d, s) for m in g["pass_rates"] for d in g["discordance"] for s in g["sigmas"]
             if not M.cell_feasibility(m, d, kappa)]
    first = {c: _five_session_false_pass(alpha, *c, kappa, 150, 1) for c in cells}
    bound = 0.025 + 3 * math.sqrt(0.025 * 0.975 / 1500)
    for c in sorted(cells, key=lambda c: (-first[c], c))[:3]:
        r = _five_session_false_pass(alpha, *c, kappa, 1500, 2)
        assert r <= bound, (c, r, alpha)


def test_pays_is_never_true_while_the_five_session_flag_is_unsimulated():  # (a)
    """A7 term of A7-2L / A7-5S is PASS (an upper bound on PASS ∧ no flag): the candidate's `_pays` must read 'undetermined'
    (None), not True, where the bounds alone would say it pays; and False when unsafe or not better."""
    from bench import m76_sim as M
    assert M._pays(True, 0.9, 0.5) is True
    assert M._pays(True, 0.9, 0.5, flag_simulated=False) is None
    assert M._pays(True, 0.4, 0.5, flag_simulated=False) is False and M._pays(False, 0.9, 0.5) is False
    v = committed_report()["variants"]
    for name in ("A7-2L", "A7-5S"):
        assert v[name]["pays"] in (None, False), (name, v[name]["pays"])


# ------------------------------------------------------------------------------------ A7-2L available branch (a)
def test_a7_2l_available_branch_records_flag_and_does_not_abort(monkeypatch):  # (a)
    """Spec v1.1: when both looks calibrate safe, record `available: true, flag: "five-session interaction flag not
    simulated"` — no abort. Reached by monkeypatching the calibration (the real one finds no safe look-1 α*)."""
    from bench import m76_sim as M
    real = M.calibrate_a7_2l

    def fake(reps=M.REPS, seed=M.SEED):
        c = dict(real(reps, seed))
        c.update(alpha_star_look1=0.001, alpha_star_look2=0.001, binding_cell_look1="x", binding_cell_look2="y")
        return c
    monkeypatch.setattr(M, "calibrate_a7_2l", fake)
    axes = committed_report()["axes"]
    a2, a5s = M._variants_a7(axes, 60, 426)
    assert a2["name"] == "A7-2L" and a2["available"] is True
    assert a2["flag"] == "five-session interaction flag not simulated"
    assert isinstance(a2["safe"], bool) and set(a2["by_cell"]) == {"planning", "nearest_realisable"}
    for c in a2["by_cell"].values():
        assert c["term"]["clean"]["k"] == c["two_look"]["PASS"]["k"]     # term = PASS (flag not simulated)
    assert a5s["name"] == "A7-5S"


def test_a7_2l_unavailable_result_is_unchanged():  # (a)
    v = committed_report()["variants"]["A7-2L"]
    assert v["available"] is False and v["safe"] is None and v["pays"] is False
    assert "no candidate" in v["reason"]


# -------------------------------------------------------------------------------------------- fail closed (a)
def _checks(z_ok=True):
    return {"planning|loss=0.0|lt20": dict(consistent=True, z=0.4),
            "planning|loss=0.1|lt20": dict(consistent=z_ok, z=0.2 if z_ok else 4.5)}


def test_require_consistent_raises_on_an_inconsistent_check_only():  # (a)
    from bench import m76_sim as M
    M.require_consistent(_checks(True))
    with pytest.raises(Exception) as ei:
        M.require_consistent(_checks(False))
    assert "loss=0.1" in str(ei.value) and "disagrees" in str(ei.value)


def test_build_fails_closed_on_an_injected_inconsistency(monkeypatch):  # (a)
    """Spec v1.1: the build raises when the direct joint simulation disagrees with the product (|z| > 3). Injected: the
    direct simulation's clean counts are zeroed (a gross disagreement) at 150 replications; the unmodified build at the same
    replications completes (negative control)."""
    from bench import m76_sim as M
    rep = M.build_report(reps=150, a5_ns=[72], b71=True)             # control: no raise
    assert "joint" in rep and rep["joint"]["direct_check"]
    real = M.simulate_joint

    def broken(*a, **k):
        out = real(*a, **k)
        out["counts"] = {key: (0 if key.startswith("clean|") else v) for key, v in out["counts"].items()}
        return out
    monkeypatch.setattr(M, "simulate_joint", broken)
    with pytest.raises(Exception) as ei:
        M.build_report(reps=150, a5_ns=[72], b71=True)
    assert "disagrees" in str(ei.value)


# ----------------------------------------------------------------------------------------- b71 default (a)
def test_b71_is_off_by_default_and_the_cli_turns_it_on(monkeypatch, tmp_path):  # (a)
    from bench import m76_sim as M
    assert inspect.signature(M.build_report).parameters["b71"].default is False
    assert inspect.signature(M.write_report).parameters["b71"].default is False
    rep = M.build_report(reps=100, a5_ns=[72])
    assert "joint" not in rep and "variants" not in rep
    seen = {}

    def fake_write(out, **kw):
        seen.update(kw)
        return {"axes": {}}
    monkeypatch.setattr(M, "write_report", fake_write)
    assert M.main(["--out", str(tmp_path), "--reps", "10"]) == 0
    assert seen.get("b71") is True


# ------------------------------------------------------------------------------------------------ GPU hours (b)
MODEL_H = dict(wave1=3.3, a5_72=4.0, tg1_session=2.7, a1_tier2=2.5, screen=3.0, decider=12.0)
STAGE_H = dict(total=37.0, tg1_per_arm=5.7)     # M76 spec §9 stage-3 tier-1 row


def _per_arm(pa1, a5_items, tg1_sessions, trig):
    h = MODEL_H
    return h["wave1"] + h["a1_tier2"] * pa1 + h["a5_72"] * a5_items / 72 + h["tg1_session"] * tg1_sessions \
        + h["screen"] + h["decider"] * trig


def test_overhead_is_derived_from_m76_section_9():  # (b)
    """tg1 pilot / reload per arm = 5.7 − 2 × 2.7 = 0.3 h; smokes and idles (both arms) = 37 − 2 × (3.3 + 4 + 5.7 + 3) = 5 h;
    total mandatory overhead 2 × 0.3 + 5.0 = 5.6 h; whole stage = modelled + overhead."""
    j = committed_report()["joint"]
    pilot = STAGE_H["tg1_per_arm"] - 2 * MODEL_H["tg1_session"]
    smokes = STAGE_H["total"] - 2 * (MODEL_H["wave1"] + MODEL_H["a5_72"] + STAGE_H["tg1_per_arm"] + MODEL_H["screen"])
    over = 2 * pilot + smokes
    assert abs(over - 5.6) < 1e-9
    h = j["hours"]
    assert h["overhead"] == pytest.approx(over, abs=1e-4)
    for k in ("expected", "worst", "best"):
        assert h[f"whole_stage_{k}"] == pytest.approx(h[k] + over, abs=1e-4)
    assert set(j["stage_overhead_inputs"]) == {"tg1_pilot_reload_per_arm", "smokes_idles_total"}


def _inputs():
    rep = committed_report()
    a1 = rep["axes"]["A1"]
    p_a1 = (a1["cells"]["sigma=0.25|loss=0.0"]["look1"]["UNDECIDED"]["rate"] if a1["final"] == "two_look" else 1.0)
    # AMENDED (spec v1.3, C338): the committed A8 path is TD — the decider runs on every plan (P(decider runs) = 1)
    t = rep["joint"]["a8_nested"]["loss=0.0"]["paths"]["TD"]["lt20"]["trigger"]["rate"]
    assert t == 1.0
    return rep, p_a1, t


def test_committed_plan_hours_reproduce_by_independent_arithmetic():  # (b)
    """Expected = 2 × Σ P(path) × hours(path) at loss 0, from the report's own probabilities (A1 look-1 UNDECIDED, the A8
    trigger); worst = every follow-up; the A5 and tg1 parts of the committed plan are always 72 items / 3 sessions."""
    rep, p_a1, t = _inputs()
    h = rep["joint"]["hours"]
    assert h["expected"] == pytest.approx(2 * _per_arm(p_a1, 72, 3, t), abs=1e-3)
    assert h["worst"] == pytest.approx(2 * _per_arm(1.0, 72, 3, 1.0), abs=1e-3)
    assert h["best"] == pytest.approx(2 * _per_arm(0.0, 72, 3, 0.0), abs=1e-3)


def test_variant_hours_reproduce_by_independent_arithmetic():  # (b)
    rep, p_a1, t = _inputs()
    v = rep["variants"]
    u1 = v["A5-2L"]["p_undecided_look1"]
    h = v["A5-2L"]["hours"]
    assert h["expected"] == pytest.approx(2 * _per_arm(p_a1, 72 + 48 * u1, 3, t), abs=1e-3)
    assert h["worst"] == pytest.approx(2 * _per_arm(1.0, 120, 3, 1.0), abs=1e-3)
    h5 = v["A7-5S"]["hours"]                                       # always 5 sessions per arm
    assert h5["expected"] == pytest.approx(2 * _per_arm(p_a1, 72, 5, t), abs=1e-3)
    assert h5["worst"] == pytest.approx(2 * _per_arm(1.0, 72, 5, 1.0), abs=1e-3)
    for hh in (h, h5):
        assert hh["whole_stage_expected"] == pytest.approx(hh["expected"] + 5.6, abs=1e-3)
