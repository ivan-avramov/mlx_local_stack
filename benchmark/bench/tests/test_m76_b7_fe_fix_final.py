"""M76 B7 (spec v1.4) — fix rounds 5-6: (1) `recheck` at an unrealisable observed nuisance (N16 pass rate exactly 0 or 1)
returns a flagged record without recalibrating (delivery 3 measured a `ValueError: gammavariate` crash there); (2) the
per-session results in `axis_verdict` are descriptive, at one-sided 0.025, independent of the look's alpha*.

Classes: (a) specification / docstring-stated behaviour; (b) independent reference (`exact_interval_values`, itself checked
against brute-force enumeration in `test_m76_b7_fe_fix_bound.py`); (c) record keys not named by the specification.
New-API imports are inside the tests (baseline failures are per test).
"""
import inspect
import json
import random
import re

import pytest


# ----------------------------------------------------------------------------- recheck at pass rate 0 / 1
def _recheck(n16, x, out, monkeypatch=None):
    from bench import m76_sim
    if monkeypatch is not None:
        def boom(*a, **k):
            raise AssertionError("calibrate must not run at an unrealisable observed nuisance")
        monkeypatch.setattr(m76_sim, "calibrate", boom)
    sig = inspect.signature(m76_sim.recheck)
    kw = {}
    for name in sig.parameters:
        if re.fullmatch(r"(n_?)?rep(lication)?s?|n_?reps?|replications", name):
            kw[name] = 20
        if re.fullmatch(r"out(_?dir)?|output(_?dir)?", name):
            kw[name] = str(out)
    return m76_sim.recheck("A8", n16, x, **kw)


@pytest.mark.parametrize("rate", [1, 0])
def test_recheck_degenerate_pass_rate_returns_flagged_record_without_recalibrating(rate, tmp_path, monkeypatch):  # (c)
    n = 40
    n16 = {i: {"s1": rate, "s2": rate} for i in range(n)}
    x = {i: dict(n16[i]) for i in n16}                      # no discordance at all
    rec = _recheck(n16, x, tmp_path, monkeypatch)
    assert rec["observed_unrealisable"] is True
    assert rec["operator_review"] is True
    assert rec["inside"] is False
    assert rec["alpha_star_applied"] == pytest.approx(0.001)         # the fixed A8 alpha*, never loosened
    assert rec["recalibration_attempted"] is False
    on_disk = json.loads(next(tmp_path.glob("recheck-*.json")).read_text())
    assert on_disk["observed_unrealisable"] is True and on_disk["operator_review"] is True


@pytest.mark.parametrize("rate", [1, 0])
def test_recheck_degenerate_pass_rate_with_discordance_is_also_flagged(rate, tmp_path, monkeypatch):  # (c)
    n = 40
    n16 = {i: {"s1": rate, "s2": rate} for i in range(n)}
    x = {i: dict(n16[i]) for i in n16}
    for i in range(0, n, 4):                                # 20 % of item-sessions discordant (X differs from N16)
        x[i]["s1"] = 1 - rate
        x[i]["s2"] = 1 - rate
    rec = _recheck(n16, x, tmp_path, monkeypatch)
    assert rec["observed_unrealisable"] is True and rec["operator_review"] is True
    assert rec["alpha_star_applied"] == pytest.approx(0.001)


def test_recheck_degenerate_pass_rate_does_not_depend_on_the_arm_effect(tmp_path, monkeypatch):  # (a) never reads the effect
    n = 40
    n16 = {i: {"s1": 1, "s2": 1} for i in range(n)}
    x_loss = {i: dict(n16[i]) for i in n16}
    for i in range(0, n, 4):
        x_loss[i]["s1"] = 0
    ra = _recheck(n16, x_loss, tmp_path / "a", monkeypatch)
    n16b = {i: {"s1": 1, "s2": 1} for i in range(n)}
    x_same = {i: dict(n16b[i]) for i in n16b}
    for i in range(1, n, 4):
        x_same[i]["s2"] = 0                                 # same discordance count, other cells
    rb = _recheck(n16b, x_same, tmp_path / "b", monkeypatch)
    assert ra["estimates"]["discordance"] == pytest.approx(rb["estimates"]["discordance"])
    assert {k: v for k, v in ra.items() if k != "estimates"} == {k: v for k, v in rb.items() if k != "estimates"}


# ----------------------------------------------------------------------------- per-session results at 0.025
def _rows(n, k, seed, p=0.8, loss=0.12):
    rng = random.Random(seed)
    sessions = [f"s{j + 1}" for j in range(k)]
    b = {i: {s: int(rng.random() < p) for s in sessions} for i in range(n)}
    a = {i: {s: (0 if b[i][s] and rng.random() < loss else b[i][s]) for s in sessions} for i in range(n)}
    return a, b, sessions


@pytest.mark.parametrize("axis,n,k", [("A8", 80, 2), ("A7", 43, 3)])
def test_per_session_results_are_at_0025_not_at_the_look_alpha(axis, n, k):  # (b)
    from bench.m76_rule import PER_SESSION_ALPHA, axis_plan, axis_verdict, exact_interval_values
    a, b, sessions = _rows(n, k, seed=3)
    res = axis_verdict(axis, 1, a, b)
    alpha_star = axis_plan(axis)["looks"][0]["alpha"]
    assert alpha_star == pytest.approx(0.001) and res["alpha"] == pytest.approx(0.001)
    assert PER_SESSION_ALPHA == pytest.approx(0.025) and res["per_session_alpha"] == pytest.approx(0.025)
    ids = sorted(a)
    assert set(res["per_session"]) == set(sessions)
    widths_at_star = []
    for s in sessions:
        vals = [a[i][s] - b[i][s] for i in ids]
        (ref,) = exact_interval_values([vals], 1, [0.025], any_discordant=any(vals))
        (ref_star,) = exact_interval_values([vals], 1, [alpha_star], any_discordant=any(vals))
        ps = res["per_session"][s]
        assert ps["delta"] == pytest.approx(ref["delta"], abs=1e-12)
        assert ps["lo"] == pytest.approx(ref["lo"], abs=1e-12) and ps["hi"] == pytest.approx(ref["hi"], abs=1e-12)
        assert ps["loss_bound"] == pytest.approx(ref["loss_bound"], abs=1e-12)
        assert ps["lo"] > ref_star["lo"], "construction: the 0.025 interval is narrower than the alpha* one"
        widths_at_star.append(ref_star["lo"])
    assert widths_at_star


def test_per_session_results_do_not_move_with_the_plan_alpha():  # (a) independence from alpha*
    """Same rows, A8 (alpha* 0.001) vs A7 look (alpha* 0.001 too) would hide the dependence; instead compare against the
    uncalibrated OBF plan's alpha through the loss_bound function directly: per-session intervals equal the 0.025 ones
    whatever alpha the look carries."""
    from bench.m76_rule import axis_verdict, loss_bound
    a, b, sessions = _rows(80, 2, seed=8)
    res = axis_verdict("A8", 1, a, b)
    for s in sessions:
        rs = loss_bound({i: {s: a[i][s]} for i in a}, {i: {s: b[i][s]} for i in b}, alpha=0.025)
        assert res["per_session"][s]["lo"] == pytest.approx(rs["lo"], abs=1e-12)
        assert res["per_session"][s]["hi"] == pytest.approx(rs["hi"], abs=1e-12)
    # and the overall verdict still sits at the look's alpha*
    overall = loss_bound(a, b, alpha=res["alpha"])
    assert res["lo"] == pytest.approx(overall["lo"], abs=1e-12)
    assert res["loss_bound"] == pytest.approx(overall["loss_bound"], abs=1e-12)


def test_a1_single_session_result_carries_per_session_at_0025():  # (c) docstring: per_session_alpha for A1 / A7 / A8
    from bench.m76_rule import axis_verdict
    a = {i: {"s": 1} for i in range(100)}
    b = {i: {"s": 1} for i in range(100)}
    res = axis_verdict("A1", 1, a, b)
    assert "per_session" in res
    assert res.get("per_session_alpha", 0.025) == pytest.approx(0.025)


# ----------------------------------------------------------------------------- dispersion cases under spec v1.4
def _dispersed_rows(hi, lo_, seed=7, n=80, disc=0.20):
    """N16 rows with item propensity hi / lo_ alternating (sessions agree more the further apart they are)."""
    rng = random.Random(seed)
    n16 = {i: {s: int(rng.random() < (hi if i % 2 == 0 else lo_)) for s in ("s1", "s2")} for i in range(n)}
    ones = [(i, s) for i in n16 for s in n16[i] if n16[i][s] == 1]
    rng.shuffle(ones)
    x = {i: dict(n16[i]) for i in n16}
    for (i, s) in ones[:int(round(disc * n * 2))]:
        x[i][s] = 0
    return n16, x


def test_moderate_dispersion_is_outside_and_recalibrates_every_cell_at_the_observed_kappa(tmp_path):  # (c)
    """Replaces, for a REALISABLE concentration, delivery 3's extreme case (kappa-hat 0.19, which v1.4 now treats as
    unrealisable: the pi cap binds, no recalibration)."""
    n16, x = _dispersed_rows(0.75, 0.25)
    rec = _recheck(n16, x, tmp_path)
    assert rec["inside"] is False
    assert any("concentration" in r for r in rec["outside_reasons"]), rec["outside_reasons"]
    assert 0.3 < rec["observed_kappa"] < rec["committed_kappa"] == pytest.approx(4.0)
    assert rec["observed_unrealisable"] is False
    assert rec["recalibration_attempted"] is True and rec["recalibrated_all_cells"] is True
    assert rec["new_cells_kappa"] == pytest.approx(rec["observed_kappa"])
    assert rec["extended_grid"] is not None
    assert rec["alpha_star_applied"] <= 0.001 + 1e-12


def test_extreme_dispersion_is_unrealisable_and_not_recalibrated_spec_v14(tmp_path, monkeypatch):  # (c) documents the rule
    """Spec v1.4: when the model cannot realise the observed nuisance, no recalibration is attempted; the record flags
    `observed_unrealisable` and `operator_review`. At kappa-hat ~0.19 the pi cap binds (realised D 0.1895 < 0.2)."""
    n16, x = _dispersed_rows(0.95, 0.05)
    rec = _recheck(n16, x, tmp_path, monkeypatch)
    assert rec["observed_kappa"] < 0.3
    assert rec["observed_unrealisable"] is True and rec["operator_review"] is True
    assert rec["recalibration_attempted"] is False
    assert rec["alpha_star_applied"] == pytest.approx(0.001)
