"""M76 B7.1 spec v1.2 ("Amendment v1.2"): two more A8 options, reported exactly like T0 / T1 / T2 and never applied
(C324 amendment candidates; the operator's choice of TD for the stage-3 plan, C338, is outside the report):
- T3 — sensitive trigger: macro-average < 0 pp ∨ any language < −10 pp;
- TD — always the decider (the screen still runs, diagnostic, C168): the A8 path is clean iff decider PASS ∧ no flag ∧ no HOLD.
Spec tests: TD's trigger rate is 1 and its false-clean rate equals the decider's false-PASS-and-no-flag rate.

Class (a): stated by the amendment; (b): independent reference built here — an exact quadrature of the screen's trigger
probability with PER-LANGUAGE losses (so the concentrated scenarios too), my nested A8 simulation (separate code and RNG),
and B7's own unconditional A8 decider cell; (c): through the candidate's layout. Report comparisons use the COMMITTED
20,000-replication report; tolerance 3.5 σ_MC.
"""
import math
import random

import numpy as np
import pytest

from bench.tests.test_m76_b7_1_fe_fix_a8nested import _agg, my_nested
from bench.tests.test_m76_b7_1_fe_fix_plan import _per_arm
from bench.tests.test_m76_b7_1_fe_support import (COMMITTED, OPTIONS, _need, committed_report, mc_tol, triggered)

NAMES = ("T0", "T1", "T2", "T3")
HOLDS = ("none", "lt25", "lt20")
SCENARIOS = {"trigger0": (0.0, 0.0, 0.0, 0.0), "detect_macro10": (0.1,) * 4, "detect_concentrated10": (0.4, 0.0, 0.0, 0.0),
             "detect_one_language10": (0.1, 0.0, 0.0, 0.0)}


def _opt(o):
    return committed_report()["variants"]["screen_options"][o]


# ---------------------------------------------------------------------------------------------- T3 / TD definitions (a)
def test_option_list_and_definitions():  # (a)
    from bench import m76_sim as M
    assert tuple(o[0] for o in M.SCREEN_OPTIONS) == NAMES + ("TD",)
    d = {o[0]: o[1:] for o in M.SCREEN_OPTIONS}
    assert d["T3"] == (0, -10) and d["TD"] == (None, None)
    assert d["T0"] == (-5, -15) and d["T1"] == (-5, None) and d["T2"] == (-5, -25)       # unchanged


@pytest.mark.parametrize("sums,expect", [
    ((0, 0, 0, 0), False),
    ((1, 1, 0, 0), False),
    ((-1, 1, 0, 0), False),          # macro 0 pp (not < 0), language −10 pp exactly (not < −10)
    ((-1, 0, 0, 0), True),           # macro −2.5 pp < 0
    ((2, -1, 0, 0), False),          # macro +2.5 pp; language −10 pp exactly
    ((2, -2, 0, 0), True),           # language −20 pp < −10
    ((3, 3, 3, -2), True),           # one language −20 pp even though the macro is positive
    ((5, -1, -1, -1), False),        # macro +5/40 = +12.5 pp ... languages −10 pp exactly
])
def test_t3_boundaries(sums, expect):  # (a)
    """T3: macro < 0 pp strict, any language < −10 pp strict (10 items per language: language steps of 10 pp)."""
    from bench import m76_sim as M
    _, mp, lp = next(o for o in M.SCREEN_OPTIONS if o[0] == "T3")
    assert M.screen_trigger(list(sums), 10, mp, lp) is expect
    assert triggered(list(sums), 10, OPTIONS["T3"]) is expect


def test_screen_trigger_agrees_with_my_predicate_on_random_sums_for_every_option():  # (b)
    from bench import m76_sim as M
    rng = random.Random(12)
    for _ in range(4000):
        sums = [rng.randint(-6, 4) for _ in range(4)]
        for name, mp, lp in M.SCREEN_OPTIONS:
            if name == "TD":
                assert M.screen_trigger(sums, 10, mp, lp) is True
            else:
                assert M.screen_trigger(sums, 10, mp, lp) == triggered(sums, 10, OPTIONS[name]), (name, sums)


def test_options_are_nested_events_with_t3_the_widest_threshold_rule():  # (b)
    """Event inclusion: T1 ⊆ T2 ⊆ T0 ⊆ T3 ⊆ TD."""
    from bench import m76_sim as M
    order = ["T1", "T2", "T0", "T3", "TD"]
    spec = {o[0]: o[1:] for o in M.SCREEN_OPTIONS}
    rng = random.Random(3)
    for _ in range(4000):
        sums = [rng.randint(-5, 3) for _ in range(4)]
        t = [M.screen_trigger(sums, 10, *spec[o]) for o in order]
        assert all((not a) or b for a, b in zip(t, t[1:])), (sums, t)


# --------------------------------------------------------------------------------------- exact quadrature reference (b)
def exact_trigger(losses, sigma, rule, m=0.5, d=0.182, kappa=4.0, per=10):
    """Exact P(trigger) with per-language losses: one session effect z shared by the languages (the screen is one k = 1
    load unit), Gauss–Hermite over z (80 nodes); given z the items are independent trinomials with P(−1) = E[π]·ω,
    P(+1) = E[π]·(1 − ω) (E[π] = the model's realised discordance); per-language sums by convolution. `rule` None = TD."""
    if rule is None:
        return 1.0
    from bench import m76_sim as M
    mods = [M.Model("A8", d, L, sigma, M.cell_beta(m, kappa)) for L in losses]
    xs, ws = ([0.0], [1.0]) if sigma == 0 else np.polynomial.hermite_e.hermegauss(80)
    ws = np.asarray(ws) / np.sum(ws)
    vals = np.arange(-per, per + 1)
    keep = np.array([not (rule["lang"] is not None and v / per < rule["lang"] - 1e-12) for v in vals])
    tot_vals = np.arange(-per * len(mods), per * len(mods) + 1)
    ok = np.array([not (rule["macro"] is not None and v / (per * len(mods)) < rule["macro"] - 1e-12) for v in tot_vals])
    out = 0.0
    for x, w in zip(xs, ws):
        dist = np.array([1.0])
        for mod in mods:
            om = mod.omega0 if (sigma == 0 or mod.omega0 in (0.0, 1.0)) else M._expit(M._logit(mod.omega0) + sigma * x)
            p = mod.d_real
            lang = np.array([1.0])
            for _ in range(per):
                lang = np.convolve(lang, [p * om, 1 - p, p * (1 - om)])
            dist = np.convolve(dist, np.where(keep, lang, 0.0))
        out += w * (1.0 - float(dist[ok].sum()))
    return out


def test_instrument_exact_reference_reproduces_the_single_loss_quadrature():  # (b)
    """Validation: with equal losses my per-language reference equals the support module's single-loss quadrature."""
    from bench.tests.test_m76_b7_1_fe_support import screen_trigger_rate
    for loss in (0.0, 0.1):
        for n in NAMES:
            assert abs(exact_trigger((loss,) * 4, 0.25, OPTIONS[n]) - screen_trigger_rate(loss, 0.25, OPTIONS[n])) < 2e-3


@pytest.mark.parametrize("key", list(SCENARIOS))
@pytest.mark.parametrize("opt", ["T0", "T1", "T2", "T3"])
def test_reported_trigger_and_detection_rates_match_the_exact_reference(opt, key):  # (c)
    """Trigger at loss 0, detection at a macro 10 pp loss, at 40 pp in one language (macro 10 pp concentrated) and at one
    language at 10 pp, for T0–T3, vs my exact quadrature. T3's are the new numbers; T0–T2 get the concentrated scenarios
    checked too."""
    got = _opt(opt)[key]["rate"]
    ex = exact_trigger(SCENARIOS[key], 0.25, OPTIONS[opt])
    assert abs(got - ex) <= mc_tol(ex, 20000, floor=0.005), (opt, key, got, ex)


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_td_trigger_is_one_in_every_scenario(key):  # (a)+(c)
    r = _opt("TD")[key]
    assert r["rate"] == 1.0 and r["k"] == r["n"]


def test_td_trigger_is_one_in_the_nested_paths_at_every_loss_and_hold():  # (a)+(c)
    n = committed_report()["joint"]["a8_nested"]
    for loss in ("loss=0.0", "loss=0.1"):
        for h in HOLDS:
            t = n[loss]["paths"]["TD"][h]["trigger"]
            assert t["k"] == t["n"], (loss, h, t)


# ------------------------------------------------------------------------------------- TD false-clean = decider (a)/(b)
def _decider_clean_from_hist(hist, hold_pp):
    """Count of replications with decider PASS ∧ no flag ∧ no HOLD, recomputed from the replication histogram
    ("<bits>|<code>|<flag>|<min language Σ d>" → count): the decider's PASS-and-no-flag-and-no-HOLD rate."""
    k = n = 0
    for key, c in hist.items():
        _, code, flag, mn = key.split("|")
        held = hold_pp is not None and 100 * int(mn) < hold_pp * 40
        k += c * (code == "P" and flag == "0" and not held)
        n += c
    return k, n


@pytest.mark.parametrize("loss", ["loss=0.0", "loss=0.1"])
@pytest.mark.parametrize("hold,pp", [("none", None), ("lt25", -25), ("lt20", -20)])
def test_td_a8_path_clean_equals_the_deciders_clean_rate_from_the_histogram(loss, hold, pp):  # (a)+(c)
    a8 = committed_report()["joint"]["a8_nested"][loss]
    k, n = _decider_clean_from_hist(a8["hist"], pp)
    p = a8["paths"]["TD"][hold]
    assert p["clean"]["k"] == k and p["clean"]["n"] == n == a8["reps"], (loss, hold, p["clean"], k)
    assert p["decider_clean"]["k"] == k


def test_td_false_clean_at_a_macro_10pp_loss_matches_b7s_unconditional_decider_cell():  # (b)
    """No HOLD: TD's A8 path is just the decider, so its false-clean rate at a 10 pp loss equals B7's own unconditional A8
    cell (PASS minus pass-with-flag; same law, drawn independently); σ 0.25, planning α*."""
    rep = committed_report()
    c8 = rep["axes"]["A8"]["cells"]["sigma=0.25|loss=0.1"]
    b7 = (c8["single"]["PASS"]["k"] - c8["flag"]["pass_with_flag"]["k"]) / c8["single"]["PASS"]["n"]
    got = rep["joint"]["a8_nested"]["loss=0.1"]["paths"]["TD"]["none"]["clean"]["rate"]
    assert abs(got - b7) <= mc_tol(b7, 20000, 20000, floor=0.003), (got, b7)


@pytest.mark.parametrize("loss,tag", [(0.0, "loss=0.0"), (0.1, "loss=0.1")])
@pytest.mark.parametrize("hold,pp", [("none", None), ("lt20", -20)])
def test_td_false_clean_matches_my_nested_simulation(loss, tag, hold, pp):  # (b)+(c)
    """The report's TD path clean (decider PASS ∧ no flag ∧ no HOLD) vs my own 20,000-replication nested simulation
    (separate code and RNG). The 10 pp value is ≈ 0.4 %, so the tolerance is 4 σ_MC + 0.001."""
    rows = my_nested(loss, 20000, 91)
    held = lambda mn: pp is not None and 100 * mn < pp * 40
    mine = sum(c and not held(mn) for _, c, mn in rows) / len(rows)
    got = committed_report()["joint"]["a8_nested"][tag]["paths"]["TD"][hold]["clean"]["rate"]
    tol = 4 * math.sqrt(max(mine, got, 1e-4) * (1 - min(mine, got)) * (1 / 20000 + 1 / 20000)) + 0.001
    assert abs(got - mine) <= tol, (loss, hold, got, mine)


def test_report_option_row_uses_the_decider_clean_rate_at_10pp():  # (c)
    o = _opt("TD")
    n = committed_report()["joint"]["a8_nested"]["loss=0.1"]["paths"]["TD"]
    assert o["a8_path_clean_at_loss10"] == n["lt20"]["clean"]
    for h in HOLDS:
        assert o["a8_path_clean_at_loss10_by_hold"][h] == n[h]["clean"]
    assert o["trigger0_nested"]["rate"] == 1.0


# ----------------------------------------------------------------------------- joint clean PASS per option (a)/(c)
@pytest.mark.parametrize("opt", ["T3", "TD"])
@pytest.mark.parametrize("cell", ["nearest_realisable", "planning"])
@pytest.mark.parametrize("hold", HOLDS)
def test_option_clean_pass_is_the_product_with_that_options_path(opt, cell, hold):  # (a)+(c)
    """P(clean PASS) at loss 0 = A1 × A5 (gated) × A7 (cell) × A8 path of the option at the HOLD (nested)."""
    rep = committed_report()
    t = rep["joint"]["cells"][cell]["terms"]["loss=0.0"]
    path = rep["joint"]["a8_nested"]["loss=0.0"]["paths"][opt][hold]["clean"]["rate"]
    want = t["A1"]["clean"]["rate"] * t["A5"]["clean"]["rate"] * t["A7"]["clean"]["rate"] * path
    got = _opt(opt)["clean_pass0_by_cell"][cell][hold]["rate"]
    assert abs(got - want) <= 2e-5, (opt, cell, hold, got, want)


@pytest.mark.parametrize("opt", ["T0", "T1", "T2", "T3", "TD"])
def test_option_clean_pass_with_a5_2l_replaces_only_the_a5_term(opt):  # (a)+(c)
    rep = committed_report()
    head = rep["joint"]["headline"]
    t = rep["joint"]["cells"][head["cell"]]["terms"]["loss=0.0"]
    path = rep["joint"]["a8_nested"]["loss=0.0"]["paths"][opt][head["hold"]]["clean"]["rate"]
    a5 = rep["variants"]["A5-2L"]["clean0"]["rate"]
    want = t["A1"]["clean"]["rate"] * a5 * t["A7"]["clean"]["rate"] * path
    got = _opt(opt)["clean_pass0_a5_2l"]["rate"]
    assert abs(got - want) <= 2e-5, (opt, got, want)
    for cell, blk in _opt(opt)["clean_pass0_a5_2l_by_cell"].items():
        assert set(blk) == set(HOLDS), cell


def test_td_costs_clean_pass_and_t3_sits_between_t0_and_td():  # (c)
    """Direction the report must show: a more sensitive trigger lowers the headline clean PASS (more decider runs, each a
    PASS-and-no-flag gamble at no loss) and lowers the false-clean rate at 10 pp."""
    hp = {o: _opt(o)["clean_pass0"]["rate"] for o in ("T0", "T3", "TD")}
    fc = {o: _opt(o)["a8_path_clean_at_loss10"]["rate"] for o in ("T0", "T3", "TD")}
    assert hp["T0"] > hp["T3"] > hp["TD"]
    assert fc["T0"] > fc["T3"] > fc["TD"]


@pytest.mark.parametrize("key", ["trigger0", "detect_macro10", "detect_concentrated10", "detect_one_language10"])
def test_option_rates_are_nested_t1_t2_t0_t3_td(key):  # (c)
    """Event inclusion on the same replications (T1 ⊆ T2 ⊆ T0 ⊆ T3 ⊆ TD) ⇒ rates are monotone in that order."""
    v = [_opt(o)[key]["k"] for o in ("T1", "T2", "T0", "T3", "TD")]
    assert v == sorted(v), (key, v)


@pytest.mark.parametrize("opt", ["T3", "TD"])
@pytest.mark.parametrize("loss", ["loss=0.0", "loss=0.1"])
def test_hold_only_removes_clean_outcomes_for_the_new_options(opt, loss):  # (c)
    p = committed_report()["joint"]["a8_nested"][loss]["paths"][opt]
    k = [p[h]["clean"]["k"] for h in HOLDS]
    assert k[0] >= k[1] >= k[2], k


# ---------------------------------------------------------------------------------------------------- hours (b)
@pytest.mark.parametrize("opt", ["T0", "T1", "T2", "T3", "TD"])
def test_option_hours_reproduce_by_independent_arithmetic(opt):  # (b)
    """Expected GPU hours = 2 × (3.3 + 2.5·P(A1 UND at look 1) + 4 + 2.7 × 3 + 3 + 12 · P(decider runs)); P(decider runs)
    = the option's nested trigger rate (TD: 1, hence 62.65 h); with A5-2L the A5 term is 4 × (72 + 48·P(look-1 UND))/72;
    whole stage adds 5.6 h."""
    rep = committed_report()
    a1 = rep["axes"]["A1"]
    p_a1 = a1["cells"]["sigma=0.25|loss=0.0"]["look1"]["UNDECIDED"]["rate"] if a1["final"] == "two_look" else 1.0
    o = _opt(opt)
    t = o["trigger0_nested"]["rate"]
    assert o["hours"]["expected"] == pytest.approx(2 * _per_arm(p_a1, 72, 3, t), abs=1e-3)
    u1 = rep["variants"]["A5-2L"]["p_undecided_look1"]
    assert o["hours_a5_2l"]["expected"] == pytest.approx(2 * _per_arm(p_a1, 72 + 48 * u1, 3, t), abs=1e-3)
    assert o["hours"]["whole_stage_expected"] == pytest.approx(o["hours"]["expected"] + 5.6, abs=1e-3)
    if opt == "TD":
        assert t == 1.0 and o["hours"]["expected"] == pytest.approx(62.65, abs=0.01)


# ----------------------------------------------------------------------------------------- presentation (a)
def test_all_five_options_are_still_presented_and_none_is_applied():  # (a)
    """The operator's choice of TD (C338) is outside the report: it still lists every option, labelled as C324 amendment
    candidates, and the committed A8 plan (screen trigger, α* 0.001) is unchanged."""
    from bench import m76_rule as R
    md = (COMMITTED / "REPORT.md").read_text()
    sec = md[md.index("## Joint plan"):]
    for o in ("T0", "T1", "T2", "T3", "TD"):
        assert f"| {o}" in sec, o
    assert "never applied" in sec or "reported only" in sec or "alternatives only" in sec
    assert R.axis_plan("A8")["looks"][0]["alpha"] == 0.001
    # AMENDED (spec v1.3 / v1.4): TD is now the committed A8 path (C338) and A5-2L the committed A5 plan (C339); the note says
    # so and labels T0–T3 as alternatives only, superseded by C338 (no longer "reported only")
    note = committed_report()["variants"]["note"]
    assert "TD" in note and "C338" in note and "alternatives only" in note and "superseded" in note
