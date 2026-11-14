"""M76 B7.1 acceptance criterion 1 — the joint section of `report.json` (spec `docs/specs/m76-b7-1-joint-plan.md` v1).

Class legend: (a) the specification states the behaviour and the key; (b) a behaviour the specification implies, tested
against an independent reference built here; (c) the specification does not name the key below `joint` / `variants`:
the quantity is discovered in the report by documented-field tokens (see `test_m76_b7_1_fe_support.py`) and the test
fails with the candidate paths when it cannot be found.

Reduced replications: the report fixture is `build_report(reps=1000, a5_ns=[72])` and the direct joint simulation runs
4000 replications, so every statistical comparison is TOLERANT: |difference| ≤ 3.5 · sqrt(p(1 − p) · Σ 1/reps) (floor
0.01); the bound is stated in each docstring. Instrument-validation tests (b) do not depend on the implementation and
are green on the baseline.
"""
import math

import pytest

from bench.tests.test_m76_b7_1_fe_support import (OPTIONS, REPORT_REPS, committed_report, direct_joint, joint_clean,
                                                  joint_trigger, mc_tol, rate_in_unit, screen_trigger_rate, section, small_report,
                                                  trigger_prob_bruteforce, trigger_prob_dp)

DIRECT_REPS = 4000
LOSSES = (0.0, 0.10)


# ------------------------------------------------------------------------------------- instrument validation (b)
@pytest.mark.parametrize("langs,per", [(4, 2), (2, 4), (3, 3)])
@pytest.mark.parametrize("d,om", [(0.3, 0.5), (0.182, 0.8), (0.5, 0.95)])
def test_instrument_screen_trigger_dp_equals_bruteforce_enumeration(langs, per, d, om):  # (b)
    """Brute-force enumeration of all 3^(langs·per) outcomes vs the exact convolution reference, for every screen
    option (T0 macro < −5 pp ∨ lang < −15 pp; T1 macro only; T2 macro ∨ lang < −25 pp). Tolerance 1e-12 (both exact)."""
    for name, rule in OPTIONS.items():
        bf = trigger_prob_bruteforce(d, om, langs, per, rule)
        assert abs(bf - trigger_prob_dp(d, om, langs, per, rule)) < 1e-12, (name, langs, per)


def test_instrument_screen_options_are_nested_events():  # (b)
    """Event inclusion by construction: T1 (macro only) ⊆ T2 (macro ∨ lang < −25 pp) ⊆ T0 (macro ∨ lang < −15 pp);
    with 2 languages × 4 items the −25 / −15 pp thresholds separate (per-language steps of 25 pp)."""
    for d, om in [(0.3, 0.5), (0.182, 0.8), (0.4, 0.9)]:
        p = {n: trigger_prob_bruteforce(d, om, 2, 4, r) for n, r in OPTIONS.items()}
        assert p["T1"] <= p["T2"] + 1e-12 <= p["T0"] + 2e-12
        assert p["T2"] < p["T0"] - 1e-6, "the 2 × 4 configuration must separate T0 from T2"


def test_instrument_trigger_boundaries_are_strict():  # (b)
    """−5 pp macro and −15 pp language do NOT trigger ('<'): 40 items with total −2 (−5.0 pp) and a language at exactly
    −0.15 is unreachable at 10 items, so check a 20-item language (per = 20: −3 → −0.15) and the macro boundary."""
    from bench.tests.test_m76_b7_1_fe_support import triggered
    assert triggered([-2, 0, 0, 0], 10, OPTIONS["T0"])                      # one language −20 pp < −15 pp
    assert not triggered([-1, -1, 0, 0], 10, OPTIONS["T0"])                 # macro −5 pp exactly, languages −10 pp
    assert triggered([-1, -1, -1, 0], 10, OPTIONS["T0"])                    # macro −7.5 pp
    assert not triggered([-3, 0, 0, 0], 20, {"macro": None, "lang": -0.15})  # exactly −15 pp
    assert triggered([-4, 0, 0, 0], 20, {"macro": None, "lang": -0.15})


def test_instrument_exact_trigger_rate_matches_direct_simulation():  # (b)
    """The quadrature reference vs my own replication-level draw of the screen (`direct_joint`'s trigger fraction) at the
    planning cell, loss 0 and 10 pp, σ 0.25 — tolerance 3.5 σ_MC at 4000 replications."""
    rep = committed_report()
    for loss in LOSSES:
        exact = screen_trigger_rate(loss, 0.25, OPTIONS["T0"])
        got = direct_joint(rep, loss, DIRECT_REPS, seed=11, option="T0")["trigger"]   # AMENDED (v1.3): TD is the default
        assert abs(got - exact) <= mc_tol(exact, DIRECT_REPS), (loss, got, exact)


def test_instrument_direct_axes_match_committed_report():  # (b)
    """My direct draws of A1, A5, A7 (PASS ∧ no flag) and the A8 path agree with the committed B7 per-axis cells
    (20,000 replications) within 3.5 σ_MC at 4000 replications — validates the direct joint simulation before it is
    used against the implementation."""
    # AMENDED (v1.1): A5 is PASS ∧ per-task gates and A7 is at the headline cell, so those two are compared with the
    # report's terms (A5's gate term is checked independently, to the exact calculation, in test_m76_b7_1_fe_fix_a5gates.py;
    # A8 path in test_m76_b7_1_fe_fix_a8nested.py). A1 stays B7's committed cell.
    rep = committed_report()
    got = direct_joint(rep, 0.0, DIRECT_REPS, seed=12)
    head = rep["joint"]["cells"][rep["joint"]["headline"]["cell"]]["terms"]["loss=0.0"]
    ref = {"a1": rep["axes"]["A1"]["cells"]["sigma=0.25|loss=0.0"]["two_look"]["PASS"]["rate"],
           "a5": head["A5"]["clean"]["rate"], "a7_clean": head["A7"]["clean"]["rate"]}
    for k, v in ref.items():
        assert abs(got[k] - v) <= mc_tol(v, DIRECT_REPS, 20000), (k, got[k], v)


# ----------------------------------------------------------------------------------------------- the joint section
def test_report_gains_joint_and_variants_keys():  # (a)
    rep = small_report()
    for k in ("joint", "variants"):
        assert k in rep and isinstance(rep[k], dict) and rep[k], f"report.json must carry a non-empty `{k}` section"


def _cell(rep, axis, loss):
    return rep["axes"][axis]["cells"][f"sigma=0.25|loss={loss}"]


def _per_axis_terms(rep, loss, t=None):
    """AMENDED (v1.1): the per-axis clean terms at the headline cell and headline HOLD, read from the report's own
    `joint.cells.<headline>.terms` — A1 PASS, A5 PASS ∧ per-task gates, A7 PASS ∧ no flag (at the headline A7 cell), A8
    path clean (nested; HOLD) — each verified against its own independent reference elsewhere (A1 / A7 against B7's
    cells at the planning cell below; A5 and A8 in the fix_* files). `t` is unused (kept for the old signature)."""
    terms = rep["joint"]["cells"][rep["joint"]["headline"]["cell"]]["terms"][f"loss={loss}"]
    return tuple(terms[k]["clean"]["rate"] if k != "A8_path" else terms[k]["clean"]["rate"]
                 for k in ("A1", "A5", "A7", "A8_path"))


@pytest.mark.parametrize("loss", LOSSES)
def test_joint_clean_pass_equals_independence_product_of_axis_terms(loss):  # (c)
    """P(clean PASS) = P(A1 PASS) · P(A5 PASS ∧ per-task gates) · P(A7 PASS ∧ no flag) · P(A8 path clean) (axes
    independent; spec "Joint section" / v1.1), the terms read from the report's own per-axis terms at the headline
    cell. The product must hold to rounding (the report multiplies its terms): |difference| ≤ 1e-5. AMENDED from the v1
    version, which read B7's ungated A5 and the independence-formula A8 path."""
    rep = small_report()
    clean = rate_in_unit(joint_clean(loss), "clean PASS")
    prod = math.prod(_per_axis_terms(rep, loss))
    assert abs(clean - prod) <= 1e-5, (clean, prod)


@pytest.mark.parametrize("loss", LOSSES)
def test_joint_a1_and_a7_terms_are_b7s_per_axis_cells(loss):  # (c)
    """The A1 term is B7's A1 cell; at the planning cell the A7 term is B7's PASS minus pass-with-flag (B7 unchanged)."""
    rep = small_report()
    ax = rep["axes"]
    t = rep["joint"]["cells"]["planning"]["terms"][f"loss={loss}"]
    a1 = _cell(rep, "A1", loss)[ax["A1"]["final"]]["PASS"]["rate"]
    a7 = _cell(rep, "A7", loss)
    want7 = (a7["single"]["PASS"]["k"] - a7["flag"]["pass_with_flag"]["k"]) / a7["single"]["PASS"]["n"]
    assert abs(t["A1"]["clean"]["rate"] - a1) <= 1e-5
    assert abs(t["A7"]["clean"]["rate"] - want7) <= 1e-5


@pytest.mark.parametrize("loss", LOSSES)
def test_joint_clean_pass_matches_direct_joint_simulation(loss):  # (c)
    """The reported P(clean PASS) (headline cell, HOLD < −20 pp) vs my own replication-level simulation of the whole
    committed plan (A1; A5 with its per-task gates; A7 at the headline cell with its flag; A8 on one nested item set —
    screen on the prefix, decider on all 80, HOLD < −20 pp; one stream; 4000 replications). AMENDED for v1.1 (the
    direct simulation gained the gates, the nesting and the HOLD). Tolerance 3.5 σ_MC for estimates at 1000 and 4000
    replications."""
    rep = small_report()
    clean = rate_in_unit(joint_clean(loss), "clean PASS")
    mine = direct_joint(rep, loss, DIRECT_REPS, seed=21)["clean"]
    assert abs(clean - mine) <= mc_tol(max(clean, mine), REPORT_REPS, DIRECT_REPS), (clean, mine)


@pytest.mark.parametrize("loss", LOSSES)
def test_joint_screen_trigger_rate_matches_exact_reference(loss):  # (c)
    """The screen's trigger rate under today's trigger (macro < −5 pp ∨ any language < −15 pp; 4 languages × 10 items,
    k = 1) at loss 0 / 10 pp under A8's planning cell (m 0.5, D 0.182, κ 4, σ 0.25) vs the exact quadrature of the
    brute-force-validated reference. Tolerance 3.5 σ_MC at 1000 replications."""
    rep = small_report()
    t = rate_in_unit(joint_trigger(loss), "trigger rate")
    exact = screen_trigger_rate(loss, 0.25, OPTIONS["T0"])
    assert abs(t - exact) <= mc_tol(exact, REPORT_REPS), (t, exact)


def test_joint_clean_pass_at_no_loss_is_not_above_any_axis_term():  # (b)
    """Sanity of the composition itself: a conjunction of independent events cannot exceed any conjunct."""
    rep = small_report()
    clean = joint_clean(0.0)
    for term in _per_axis_terms(rep, 0.0):
        assert clean <= term + 1e-9, (clean, term)
