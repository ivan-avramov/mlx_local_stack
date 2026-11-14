"""M76 B7.1 acceptance criteria 1–2 — the pre-registered variants in `report.json["variants"]` (spec
`docs/specs/m76-b7-1-joint-plan.md` v1): A7-2L, A5-2L and the A8 screen options T0 / T1 / T2.

Class legend: (a) stated by the spec, (b) tested against an independent reference built here, (c) the spec does not
name the key below `variants`: read through the candidate's layout (delivery 2; see `test_m76_b7_1_fe_support.py`).

Every final look of every variant must keep false-PASS(10) ≤ 0.025 (settled constraint):
- A5-2L: by exact enumeration (my reference: trinomial outcomes of both looks, the exact PASS regions of `m76_rule`
  at each look's alpha, a look-1 LOSS stops, p_c scanned over the whole H0 boundary);
- A7-2L: the specification's settled safety constraint says no look may be offered unless every final look is safe, and
  look 1 is calibrated against the O'Brien–Fleming spend α(3/5) = 0.003808. The candidate reports the variant
  UNAVAILABLE (fail closed). The tests below assert that result (this is the fail-closed outcome the constraint implies,
  not a sentence of the specification) and confirm it independently: my own simulation of look 1 (sessions 1–3) at the
  smallest candidate α 0.001 exceeds the spend at the candidate's binding cell.
"""
import math
import random

import numpy as np
import pytest

from bench.tests.test_m76_b7_1_fe_support import (OPTIONS, REPORT_REPS, _need, a5_final_pass_prob, a5_two_look_size,
                                                  committed_report, joint_trigger, mc_tol, rate_in_unit,
                                                  screen_trigger_rate, section)


def _v(*keys, what):
    return _need(section("variants"), *keys, what=what)


# ---------------------------------------------------------------------------------------------- presence (c)
def test_variants_section_names_both_two_look_variants_and_three_screen_options():  # (c)
    v = section("variants")
    assert "A7-2L" in v and "A5-2L" in v, sorted(v)
    # AMENDED (spec v1.2): the options are T0, T1, T2, T3 (sensitive trigger) and TD (always the decider)
    assert set(v.get("screen_options", {})) == {"T0", "T1", "T2", "T3", "TD"}


# ---------------------------------------------------------------------------------- A5-2L: exact enumeration (b)
def test_a5_two_look_reference_reproduces_single_look_exact_size():  # (b)
    """Instrument check: with no second look my enumerator gives B7's exact size of the n = 72 rule (|difference| ≤ 1e-4)."""
    from bench import m76_rule as R
    ref = R.a5_exact_size(72)
    mine = max(a5_final_pass_prob(72, 0, 0.025, 0.0, np.arange(0.0, 0.4501, 0.002)))
    assert abs(mine - ref) <= 1e-4, (mine, ref)


def test_a5_two_look_reference_detects_an_unspent_second_look():  # (b)
    """Positive control: spending 0.025 at BOTH looks exceeds 0.025 in my enumerator; the OBF increments do not."""
    size_bad, _ = a5_two_look_size(alphas=[0.025, 0.025])
    size_obf, _ = a5_two_look_size()
    assert size_bad > 0.025 > size_obf, (size_bad, size_obf)


def test_a5_two_look_variant_exact_size_by_enumeration_is_at_most_0025():  # (b)
    """A5-2L as specified: n = 72 then +48 (to 120) on UNDECIDED, exact test at each look with Lan–DeMets O'Brien–Fleming
    increments at t₁ = 72/120. Exact size by my enumeration ≤ 0.025."""
    size, pc = a5_two_look_size()
    assert size <= 0.025, (size, pc)


def test_a5_two_look_variant_reported_exact_size_is_at_most_0025():  # (c)
    assert rate_in_unit(_v("A5-2L", "exact", "size", what="A5-2L exact size"), "exact size") <= 0.025
    assert rate_in_unit(_v("A5-2L", "final_looks_false_pass10", "exact_size", what="final-look exact size"),
                        "final-look exact size") <= 0.025
    assert _v("A5-2L", "safe", what="A5-2L safe flag") is True


def test_a5_two_look_variant_reported_size_and_alphas_match_independent_enumeration():  # (c)
    """The reported alphas are the O'Brien–Fleming increments at t₁ = 0.6 and the reported exact size agrees with my
    enumeration at the REPORTED alphas (|difference| ≤ 2e-3: grid / tie-ordering only)."""
    from bench import stats
    looks = _v("A5-2L", "looks", what="A5-2L looks")
    assert [lk["size"] for lk in looks] == [72, 120]
    a = [lk["alpha"] for lk in looks]
    ref = stats.obf_looks([0.6, 1.0], 0.025)
    assert a == pytest.approx(ref, abs=2e-6), (a, ref)
    size, _ = a5_two_look_size(alphas=a)
    assert abs(_v("A5-2L", "exact", "size", what="exact size") - size) <= 2e-3


# ------------------------------------------------------------------------------------------------- A7-2L (b)/(c)
def test_a7_two_look_variant_is_reported_unavailable_fail_closed():  # (c)
    """Fail-closed result implied by the settled safety constraint: no safe look-1 α*, so the variant is unavailable and
    carries no adopted alphas / final look; its reason names the O'Brien–Fleming spend."""
    v = section("variants")["A7-2L"]
    assert v["available"] is False and v["safe"] is None
    assert "no candidate" in v["reason"] and "0.003808" in v["reason"]
    assert v["calibration"]["alpha_star_look1"] is None
    assert v["calibration"]["target_look1"] == pytest.approx(0.003808, abs=1e-6)
    assert all(lk["alpha"] is None for lk in v["looks"] if lk["look"] == 1)


def _look1_false_pass(alpha, m, d, sigma, kappa, reps, seed):
    """False-PASS(10) of A7-2L's look 1 (sessions 1–3) at nominal one-sided `alpha`, B7's data model and exact bootstrap."""
    from bench import m76_sim as M
    model = M.Model("A7", d, 0.10, sigma, M.cell_beta(m, kappa))
    rng = random.Random(f"b71-a7-look1:{seed}:{m!r}:{d!r}:{sigma!r}")
    k = 0
    for _ in range(reps):
        rows = M._gen(model, 43, 3, lambda i, s: s, rng)
        v = M.verdict_vector([sum(r) for r in rows], 43, 3, any(x for r in rows for x in r), alphas=(alpha,))
        k += v == "P"
    return k / reps


def test_a7_two_look_variant_unavailability_confirmed_by_independent_simulation():  # (b)
    """At the candidate's binding cell, look 1 at the SMALLEST candidate α (0.001) still has false-PASS(10) above the
    spend α(3/5) = 0.003808 in my own 3000-replication simulation (tolerance: rate − 3·SE > 0.003808), so no candidate
    look-1 α* exists and the fail-closed result is not an artefact of the candidate's code."""
    cal = section("variants")["A7-2L"]["calibration"]
    cell = cal["cells"][cal["binding_cell_look1"]]
    reps = 3000
    r = _look1_false_pass(0.001, cell["m"], cell["D"], cell["sigma"], cell["kappa"], reps, 5)
    se = math.sqrt(max(r * (1 - r), 1e-4) / reps)
    assert r - 3 * se > 0.003808, (cell["m"], cell["D"], cell["sigma"], r)


# ----------------------------------------------------------------------------------- A8 screen options (c) / (b)
def _opt(opt, key):
    return rate_in_unit(_v("screen_options", opt, key, "rate", what=f"{opt} {key}"), f"{opt} {key}")


@pytest.mark.parametrize("opt", ["T0", "T1", "T2"])
def test_screen_option_trigger_rate_at_no_loss_matches_exact_reference(opt):  # (c)
    got = _opt(opt, "trigger0")
    exact = screen_trigger_rate(0.0, 0.25, OPTIONS[opt])
    assert abs(got - exact) <= mc_tol(exact, REPORT_REPS), (opt, got, exact)


@pytest.mark.parametrize("opt", ["T0", "T1", "T2"])
def test_screen_option_macro_detection_at_10pp_matches_exact_reference(opt):  # (c)
    """Detection at a 10 pp loss on every language (the macro scenario; D_eff 0.182, σ 0.25)."""
    got = _opt(opt, "detect_macro10")
    exact = screen_trigger_rate(0.10, 0.25, OPTIONS[opt])
    assert abs(got - exact) <= mc_tol(exact, REPORT_REPS), (opt, got, exact)


def test_screen_options_are_nested_in_every_reported_scenario():  # (c)
    """Event inclusion: T1 ⊆ T2 ⊆ T0, so rates satisfy T1 ≤ T2 ≤ T0 in each scenario (loss 0; 10 pp macro; macro 10 pp
    concentrated in one language; one language at 10 pp). Same replications in the candidate → exact; slack 0 + 1e-9."""
    for key in ("trigger0", "detect_macro10", "detect_concentrated10", "detect_one_language10"):
        v = {o: _opt(o, key) for o in ("T0", "T1", "T2")}
        assert v["T1"] <= v["T2"] + 1e-9 and v["T2"] <= v["T0"] + 1e-9, (key, v)


def test_screen_option_t0_equals_the_joint_sections_trigger_rate():  # (c)
    """T0 = today's trigger: its reported rate at loss 0 is the joint section's."""
    assert abs(joint_trigger(0.0) - _opt("T0", "trigger0")) <= 1e-9


def test_screen_options_are_reported_not_applied():  # (a)
    """C324 (settled): the screen options are reported, never applied — the committed A8 plan is unchanged."""
    from bench import m76_rule as R
    assert R.axis_plan("A8")["looks"][0]["alpha"] == 0.001
    assert committed_report()["axes"]["A8"]["final_alpha"] == [0.001]
