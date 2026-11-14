"""M76 B7.1 (implementer): spec v1.1 erratum items — A8 nesting, A5 per-task gates, A8 large-harm HOLD thresholds, both
A7 cells, A7-5S, A7-2L when both looks calibrate safe, the fail-closed joint check, `build_report(b71=False)` by
default, whole-stage GPU hours."""
import inspect
import json
import math
import random
from pathlib import Path

import pytest

from bench import m76_rule as R
from bench import m76_sim as M

REPORT = Path(M.__file__).resolve().parent.parent / "results" / "m76" / "b7-simulation"
CELLS = ("nearest_realisable", "planning")
HOLDS = ("none", "lt25", "lt20")


def _committed():
    return json.loads((REPORT / "report.json").read_text())


class _Bimodal:
    """Items either always discordant (π = 1, probability `p_hi`) or never (π = 0); every discordance a TQ4 loss with
    probability `omega0`."""

    def __init__(self, p_hi, omega0):
        self.p_hi, self.omega0 = p_hi, omega0

    def item_pi(self, rng):
        return 1.0 if rng.random() < self.p_hi else 0.0


# ------------------------------------------------------------------------------------------------ A8 nesting
def test_nested_screen_items_are_the_deciders_first_items():
    """With π ∈ {0, 1} and every discordance a loss, the outcome is a function of the item alone: the screen's
    per-language sum equals the decider's sum over each language's first 10 items in every session (one item set)."""
    rng = random.Random(1)
    models = [_Bimodal(0.4, 1.0) for _ in range(M.SCREEN_LANGUAGES)]
    for _ in range(200):
        screen, rows = M.a8_nested_draw(models, 0.0, rng)
        assert len(rows) == M.SCREEN_LANGUAGES * M.A8_ITEMS_PER_LANGUAGE and all(len(r) == 2 for r in rows)
        for li in range(M.SCREEN_LANGUAGES):
            first = rows[li * 20:li * 20 + 10]
            assert screen[li] == sum(r[0] for r in first) == sum(r[1] for r in first)


def test_nested_prefix_outcomes_predict_the_decider_verdict():
    """Prefix outcomes predict the decider: P(decider PASS ∧ no flag | screen triggered) is far below P(… | not
    triggered) on one item set; the independence formula would make them equal."""
    models = [_Bimodal(0.025, 1.0) for _ in range(M.SCREEN_LANGUAGES)]     # item-determined losses, mean −2.5 pp
    reps = 3000
    r = M.simulate_a8_nested(None, 0.025, 0.0, (0.025,) * 4, reps, seed=7, models=models)
    p = M.a8_path_from(r["hist"], reps, "T0", "none")
    gt, gn = p["decider_clean_given_trigger"], p["decider_clean_given_no_trigger"]
    se = math.sqrt(gt["rate"] * (1 - gt["rate"]) / gt["n"] + gn["rate"] * (1 - gn["rate"]) / gn["n"])
    assert gn["rate"] - gt["rate"] > 6 * se, (gt, gn)
    # the A8 path is the direct reading, not 1 − t + t · q with the unconditional decider
    t, q = p["trigger"]["rate"], p["decider_clean"]["rate"]
    assert (1 - t + t * q) - p["clean"]["rate"] > 0.01, (t, q, p["clean"])


def test_nested_trigger_matches_screen_exact_at_planning_cell():
    reps = 3000
    for L in (0.0, 0.10):
        r = M.simulate_a8_nested(0.5, 0.182, 0.25, (L,) * 4, reps, seed=11)
        for o in ("T0", "T1", "T2"):
            got = M.a8_path_from(r["hist"], reps, o, "none")["trigger"]["rate"]
            ex = M.screen_trigger_exact(0.5, 0.182, 0.25, (L,) * 4, o)
            assert abs(got - ex) <= 4 * math.sqrt(ex * (1 - ex) / reps) + 2e-3, (L, o, got, ex)


def test_decider_read_uses_the_rule_and_language_minimum():
    rng = random.Random(3)
    rows = [[0, 0] for _ in range(80)]
    for i in range(20):                       # language 0: 10 items lost in both sessions → point −50 pp
        rows[i] = [-1, -1] if i < 10 else [0, 0]
    v, flag, mn = M.a8_decider_read(rows, M.CANDIDATES.index(0.001), rng)
    assert mn == -20 and v == M.verdict_vector([sum(r) for r in rows], 80, 2, True)[M.CANDIDATES.index(0.001)]
    assert flag is False or v == "P"


@pytest.mark.parametrize("mn, pp, fires", [(-10, -25, False), (-11, -25, True), (-8, -20, False), (-9, -20, True),
                                           (-40, None, False)])
def test_hold_threshold_boundaries(mn, pp, fires):
    # language point = Σ d / (20 items × 2 sessions); HOLD ⇔ point < threshold (strict)
    assert M.hold_fires(mn, pp) is fires


def test_a8_path_from_counts_and_hold():
    hist = {"111|P|0|-12": 10, "111|P|0|0": 20, "111|P|1|0": 5, "111|U|0|0": 15, "000|P|0|0": 30, "000|U|0|-15": 20}
    p = M.a8_path_from(hist, 100, "T0", "lt25")
    assert p["trigger"]["k"] == 50 and p["clean"]["k"] == 50 + 20       # held 10, flagged 5, UND 15 not clean
    assert p["triggered_PASS_held"]["k"] == 10 and p["triggered_PASS_flagged"]["k"] == 5
    assert p["decider_clean_given_trigger"]["k"] == 20 and p["decider_clean_given_no_trigger"]["k"] == 30
    assert M.a8_path_from(hist, 100, "T0", "none")["clean"]["k"] == 80


def test_committed_a8_path_is_nested_and_hold_monotone():
    rep = _committed()
    j = rep["joint"]
    assert "nested" in j["independence"] and "no independence assumed" in j["independence"]
    for L in ("loss=0.0", "loss=0.1"):
        n8 = j["a8_nested"][L]
        assert n8["reps"] >= 20000 and n8["alpha"] == rep["axes"]["A8"]["planning_alpha"]
        for o in ("T0", "T1", "T2"):
            c = [n8["paths"][o][h]["clean"]["k"] for h in HOLDS]
            assert c[0] >= c[1] >= c[2]
        for cell in CELLS:
            t = j["cells"][cell]["terms"][L]
            assert t["A8_path"] == n8["paths"]["TD"][M.HEADLINE_HOLD]          # v1.3: TD committed
            assert t["A8_path_by_hold"] == n8["paths"]["TD"]


# ------------------------------------------------------------------------------------------- A5 per-task gates
def test_a5_task_gates_boundaries():
    def rows(r_vals, c_vals):          # interleave: even = retrieval, odd = chain-4
        out = []
        for a, b in zip(r_vals, c_vals):
            out += [[a], [b]]
        return out
    assert M.a5_task_gates(rows([-1] + [0] * 19, [0] * 20))            # −5 pp exactly passes
    assert not M.a5_task_gates(rows([-1, -1] + [0] * 18, [0] * 20))    # retrieval −10 pp
    # pooled −0 pp (compensating chain-4 gains) but retrieval −10 pp → gate fails
    assert not M.a5_task_gates(rows([-1, -1] + [0] * 18, [1, 1] + [0] * 18))


def test_simulate_a5_gates_reproduces_b7_counts():
    for L in (0.0, 0.1):
        g = M.simulate_a5_gates(72, L, 0.25, 400)
        b = M.simulate_a5(72, L, 0.25, 400)
        assert {k: g["counts"][k] for k in "PLU"} == b["counts"]
        assert g["counts"]["G"] + g["counts"]["F"] == g["counts"]["P"]


def test_committed_a5_clean_term_includes_the_gates():
    rep = _committed()
    j = rep["joint"]
    for L in ("loss=0.0", "loss=0.1"):
        g = j["a5_gates"][L]["counts"]
        b7 = rep["axes"]["A5"]["cells"][f"sigma=0.25|{L}"]["single"]
        assert g["P"] == b7["PASS"]["k"]
        for cell in CELLS:
            t = j["cells"][cell]["terms"][L]["A5"]
            assert t["clean"]["k"] == g["G"] and t["pass_gate_failed"]["k"] == g["F"]
    assert "absolute" in j["assumed"]["a5_task_gates"] and "simulated" in j["assumed"]["a5_task_gates"]


def test_a5_2l_clean_counts_gates_at_the_deciding_look():
    a = M.simulate_a5_2l(0.0, 0.25, 400)
    assert a["final_clean"] <= a["final"]["P"]
    v = _committed()["variants"]["A5-2L"]
    assert v["clean0"]["k"] <= v["pass0"]["k"]
    assert v["pays"] in (True, False)


# ------------------------------------------------------------------------------------------- cells and holds
def test_committed_every_row_reports_both_a7_cells_at_every_hold():
    rep = _committed()
    j, v = rep["joint"], rep["variants"]
    assert j["headline"]["cell"] == "nearest_realisable" and j["headline"]["hold"] == M.HEADLINE_HOLD
    assert j["cells"]["nearest_realisable"]["a7_cell"]["extrapolated"] is False
    assert j["cells"]["planning"]["a7_cell"]["extrapolated"] is True
    assert j["headline"]["clean_pass"] == j["cells"]["nearest_realisable"]["scenarios"]["all_loss0"]["clean_pass"]
    for cell in CELLS:
        by = j["cells"][cell]["scenarios"]["all_loss0"]["clean_pass_by_hold"]
        assert set(by) == set(HOLDS) and by["none"]["rate"] >= by["lt25"]["rate"] >= by["lt20"]["rate"]
    for name in ("A5-2L", "A7-2L", "A7-5S"):
        x = v[name]
        if x["available"] and x.get("safe") and not x.get("clean_pass_note"):      # v1.3: A7-5S not estimated
            assert set(x["clean_pass0_by_cell"]) == set(CELLS)
            assert all(set(x["clean_pass0_by_cell"][c]) == set(HOLDS) for c in CELLS)
            assert x["clean_pass0"] == x["clean_pass0_by_cell"]["nearest_realisable"][M.HEADLINE_HOLD]


def test_committed_products_per_cell_and_hold():
    j = _committed()["joint"]
    for cell in CELLS:
        for L, scen in (("loss=0.0", "all_loss0"), ("loss=0.1", "all_loss10")):
            t = j["cells"][cell]["terms"][L]
            for h in HOLDS:
                want = (t["A1"]["clean"]["rate"] * t["A5"]["clean"]["rate"] * t["A7"]["clean"]["rate"] *
                        t["A8_path_by_hold"][h]["clean"]["rate"])
                got = j["cells"][cell]["scenarios"][scen]["clean_pass_by_hold"][h]["rate"]
                assert got == pytest.approx(want, abs=2e-6)


def test_committed_md_headline_and_columns():
    md = (REPORT / "REPORT.md").read_text()
    sec = md[md.index("## Joint plan (B7.1)"):]
    assert "**Headline: P(clean PASS) at loss 0 = " in sec and "HOLD at any language's decider point < −20 pp" in sec
    hdr = next(line for line in sec.splitlines() if line.startswith("| plan / variant |"))
    for h in ("no HOLD", "HOLD < −25 pp", "HOLD < −20 pp"):
        assert hdr.count(h) == 2
    assert "nearest realisable" in hdr and "planning cell" in hdr and "whole stage" in hdr
    for row in ("| committed plan (TD + A5-2L; C338, C339) |", "| single-look A5 reference ", "| A5-2L ", "| A7-2L ",
                "| A7-5S "):                                                  # v1.4: committed = TD + A5-2L
        assert row in sec


# ------------------------------------------------------------------------------------------------- A7-5S
def test_committed_a7_5s_is_b7_calibrate_method_on_a7_grid():
    v = _committed()["variants"]
    cal = v["A7-2L"]["calibration"]
    assert len(cal["cells"]) == 27 and cal["grid"] == {k: list(x) for k, x in M.CAL_GRID["A7"].items()}
    feas = [c for c in cal["cells"].values() if c["feasible"]]
    safe = [a for j, a in enumerate(M.CANDIDATES)
            if max(M._rate(M._single_counts(c["hist"], j), c["reps"])["hi"] for c in feas) <= R.ALPHA_TOTAL]
    assert cal["alpha_star_5s"] == (max(safe) if safe else None)
    x = v["A7-5S"]
    assert x["seeds"] == [1001, 2002, 3003, 4004, 5005] and x["sessions"] == 5
    if x["available"]:
        assert x["looks"][0]["alpha"] == cal["alpha_star_5s"]
        assert x["final_false_pass10_hi"] <= R.ALPHA_TOTAL and x["safe"]
        assert x["flag"] == M.FLAG_5S
        assert x["pays"] in (False, None)                        # flag not simulated → never a bare "pays"
        h = M._plan_hours(None, (72,), 0.0, (5,), 0.0, 0.5)
        per = 3.3 + 2.5 + 4.0 + 2.7 * 5 + 3.0 + 12.0 * 0.5
        assert h["expected"] == pytest.approx(2 * per)


# ----------------------------------------------------------------------------- A7-2L when both looks are safe
def test_a7_2l_available_records_flag_without_abort(monkeypatch):
    rep = _committed()
    real = M.calibrate_a7_2l(reps=40, seed=5)

    def fake(reps=M.REPS, seed=M.SEED):
        return dict(real, alpha_star_look1=0.001, alpha_star_look2=0.001)
    monkeypatch.setattr(M, "calibrate_a7_2l", fake)
    a72, a75 = M._variants_a7(rep["axes"], 40, 5)
    assert a72["available"] is True and a72["flag"] == "five-session interaction flag not simulated"
    assert set(a72["by_cell"]) == set(CELLS) and isinstance(a72["safe"], bool)
    for c in CELLS:
        b = a72["by_cell"][c]
        assert b["term"]["clean"] == b["two_look"]["PASS"]
        assert 3 <= b["expected_sessions"] <= 5


def test_pays_rule_fail_closed():
    assert M._pays(True, 0.9, 0.8) is True
    assert M._pays(True, 0.9, 0.8, flag_simulated=False) is None
    assert M._pays(True, 0.7, 0.8, flag_simulated=False) is False
    assert M._pays(False, 0.9, 0.8) is False


# ------------------------------------------------------------------------------------------------- fail closed
def test_require_consistent_raises():
    M.require_consistent({"a": dict(consistent=True, z=0.1)})
    with pytest.raises(RuntimeError, match="disagrees"):
        M.require_consistent({"a": dict(consistent=True, z=0.1), "b": dict(consistent=False, z=-5.0)})


def test_joint_build_fails_closed_on_disagreement(monkeypatch):
    rep = _committed()

    def bogus(axes, loss, reps, *, seed=M.SEED, option="T0", a7_cell=None):
        c = {f"clean|{h}": 0 for h in HOLDS}
        return dict(counts=c, reps=10 ** 6, loss=loss, option=option, a7_cell=a7_cell)
    monkeypatch.setattr(M, "simulate_joint", bogus)
    with pytest.raises(RuntimeError, match="disagrees"):
        M._joint(rep["axes"], 200, 9)


def test_committed_direct_checks_cover_cells_losses_holds():
    chk = _committed()["joint"]["direct_check"]
    assert set(chk) == {f"{c}|loss={L}|{h}" for c in CELLS for L in ("0.0", "0.1") for h in HOLDS}
    assert all(c["consistent"] and abs(c["z"]) <= M.Z_CONSISTENT and c["direct"]["n"] >= 20000 for c in chk.values())


# ------------------------------------------------------------------------------------------------ b71 default
def test_build_report_b71_defaults_false_and_cli_sets_it(monkeypatch, tmp_path):
    assert inspect.signature(M.build_report).parameters["b71"].default is False
    assert inspect.signature(M.write_report).parameters["b71"].default is False
    seen = {}

    def fake(out, **kw):
        seen.update(kw)
        return dict(axes={})
    monkeypatch.setattr(M, "write_report", fake)
    assert M.main(["--out", str(tmp_path)]) == 0
    assert seen["b71"] is True


# ------------------------------------------------------------------------------------------------- GPU hours
def test_whole_stage_hours_add_mandatory_work():
    h = M._plan_hours(None, (72,), 0.0, (3,), 0.0, 0.4)
    over = 2 * 0.3 + 5.0
    assert h["overhead"] == pytest.approx(over)
    for k in ("expected", "worst", "best"):
        assert h[f"whole_stage_{k}"] == pytest.approx(h[k] + over)
    j = _committed()["joint"]
    assert set(j["stage_overhead_inputs"]) == set(M.STAGE_OVERHEAD)
    assert all("§9" in x["source"] for x in j["stage_overhead_inputs"].values())
    assert j["hours"]["whole_stage_worst"] == pytest.approx(j["hours"]["worst"] + over, abs=1e-6)
