"""B6 A7 flags (recert §1): each raised AND not raised, each carrying the number that raised it.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
A flag is detected by the number it carries (fraction or percent form, display-rounded) inside the sheet's `*flag*` subtree.
"""
from __future__ import annotations

import pytest

from bench.tests.p613 import a7world as W
from bench.tests.p613 import sigview as V

IDS8 = W.DEFAULT_IDS["s1"]
CATS = ("budget_hit", "turn_cap", "exec_timeout", "client_inactivity", "looping", "stalled")


def carries(sig, x, tol=6e-3):
    return V.has_num_loose(V.flag_numbers(sig), x, tol)


def no_flags(sig):
    assert V.flags_tree(sig), "the sheet has a flags section"
    assert V.flag_numbers(sig) == [], V.flag_text(sig)


# class: new-behaviour (a clean pair raises nothing: the flags section exists and carries no number)
def test_clean_tree_raises_no_flag(pipeline):
    _, _, sig = pipeline()
    no_flags(sig)


# ----------------------------------------------------------------------------------------------- point < -5 pp
# class: new-behaviour (strict delta -12.5 pp in s1)
def test_flag_point_below_minus_5pp(pipeline):
    _, _, sig = pipeline(rows={("on", "s1"): {"python/a3": {"passed": False}}})
    assert carries(sig, -0.125), V.flag_text(sig)
    assert "s1" in V.flag_text(sig)


# class: new-behaviour (-2.5 pp at n = 40 is above the line: not raised)
def test_no_flag_for_small_drop(pipeline):
    ids = [f"python/p{i}" for i in range(1, 26)] + [f"go/q{i}" for i in range(1, 16)]
    on = {i: {"passed": i != "python/p1"} for i in ids}
    _, _, sig = pipeline(ids={"s1": ids}, rows={("on", "s1"): on})
    no_flags(sig)


# class: new-behaviour (an ON gain is never flagged)
def test_no_flag_for_gain(pipeline):
    _, _, sig = pipeline(rows={("off", "s1"): {"python/a3": {"passed": False}, "go/g1": {"passed": False}}})
    no_flags(sig)


# class: new-behaviour (the flag is per session: a loss in s2 names s2)
def test_flag_names_the_session(pipeline):
    _, _, sig = pipeline(rows={("on", "s2"): {"python/b2": {"passed": False}}})
    assert carries(sig, -0.125)
    assert "s2" in V.flag_text(sig)


# ----------------------------------------------------------------------------------------------- Holm p < .05, OFF better
# class: new-behaviour (OFF better with Holm-adjusted p ~ 0.03 < .05: raised, carrying the adjusted p)
def test_flag_holm_with_off_better(pipeline):
    ids = IDS8
    on, off = {i: {"passed": i == ids[0]} for i in ids}, {i: {"passed": True} for i in ids}
    _, _, sig = pipeline(rows={("on", "s1"): on, ("off", "s1"): off})
    pool = V.flag_numbers(sig)
    assert any(0.017 <= v <= 0.047 or 1.7 <= v <= 4.7 for v in pool), pool        # 2 x p, p ~ 0.0157 +- 0.0074
    assert carries(sig, -0.875), "the same session also drops by 87.5 pp"


# class: new-behaviour (the same significance with ON better is not a flag at all)
def test_no_holm_flag_when_on_is_better(pipeline):
    ids = IDS8
    on, off = {i: {"passed": True} for i in ids}, {i: {"passed": i == ids[0]} for i in ids}
    _, _, sig = pipeline(rows={("on", "s1"): on, ("off", "s1"): off})
    no_flags(sig)


# class: new-behaviour (not significant after Holm (p = 1.0): a -12.5 pp point raises only the point flag)
def test_holm_flag_not_raised_when_not_significant(pipeline):
    # amended (delivery 3): read the flag list itself; digit-scraping of flag text also parses "A7-s1" and the threshold
    _, _, sig = pipeline(rows={("on", "s1"): {"python/a3": {"passed": False}}})
    assert [f["flag"] for f in sig["flags"]] == ["strict_point_below_-5pp"]
    assert sig["flags"][0]["value"] == pytest.approx(-12.5)


# ----------------------------------------------------------------------------------------------- decode ratio < 1.3
# class: new-behaviour (ON 20 % faster: point 1.2 < 1.3)
def test_flag_decode_ratio_below_1_3(pipeline):
    on = {i: {"rate": 24.0} for i in IDS8}
    _, _, sig = pipeline(speed={("on", "s1"): on})
    assert V.has_num_loose(V.flag_numbers(sig), 1.2, 6e-3) and "s1" in V.flag_text(sig)


# class: new-behaviour (ON 31 % faster: above the line, not raised)
def test_no_decode_flag_at_1_31(pipeline):
    on = {i: {"rate": 26.2} for i in IDS8}
    _, _, sig = pipeline(speed={("on", "s1"): on})
    no_flags(sig)


# class: new-behaviour (power-invalid pairs leave speed inference: no ratio flag even when the ratio is poor)
def test_no_decode_flag_for_power_invalid_pair(pipeline):
    on = {i: {"rate": 10.0} for i in IDS8}
    _, _, sig = pipeline(speed={("on", "s1"): on}, legs={("on", "s1"): {"speed_valid": False}})
    no_flags(sig)


# ----------------------------------------------------------------------------------------------- acceptance < 0.70
# class: new-behaviour (552 / 800 = 0.69)
def test_flag_acceptance_below_070(pipeline):
    on = {i: {"accepted": 69, "proposed": 100} for i in IDS8}
    _, _, sig = pipeline(speed={("on", "s1"): on})
    assert carries(sig, 0.69), V.flag_text(sig)


# class: new-behaviour (exactly 0.70 and 0.71 are not below the line)
@pytest.mark.parametrize("acc", [70, 71])
def test_no_acceptance_flag_at_or_above_070(pipeline, acc):
    on = {i: {"accepted": acc, "proposed": 100} for i in IDS8}
    _, _, sig = pipeline(speed={("on", "s1"): on})
    no_flags(sig)


# ----------------------------------------------------------------------------------------------- tax category ON-only
def pair_failing(session_ids, who_has, cat, via):
    """Both arms fail g1 (equal strict outcome, no delta); `who_has` arms record the category on it."""
    base = {"passed": False, "converged": True, "nonconv_kind": None, "nonconv_flags": []}
    flagged = dict(base, converged=False)
    if via == "kind":
        flagged["nonconv_kind"] = cat
    else:
        flagged["nonconv_flags"] = [cat]
    return {arm: {"go/g1": flagged if arm in who_has else base} for arm in ("on", "off")}


# class: new-behaviour (each of the six categories, recorded in nonconv_flags or in nonconv_kind, present in ON only)
@pytest.mark.parametrize("via", ["flags", "kind"])
@pytest.mark.parametrize("cat", CATS)
def test_flag_tax_category_in_on_only(pipeline, cat, via):
    r = pair_failing(IDS8, {"on"}, cat, via)
    _, _, sig = pipeline(rows={("on", "s1"): r["on"], ("off", "s1"): r["off"]})
    t = V.flag_text(sig)
    assert cat in t and "s1" in t, t


# class: new-behaviour (present in both arms, or in OFF only: not a flag)
@pytest.mark.parametrize("who", [{"on", "off"}, {"off"}])
def test_no_tax_flag_when_off_has_it(pipeline, who):
    r = pair_failing(IDS8, who, "looping", "flags")
    _, _, sig = pipeline(rows={("on", "s1"): r["on"], ("off", "s1"): r["off"]})
    no_flags(sig)


# class: new-behaviour (per session: ON has looping in s1 only where OFF lacks it; s2 has it in both)
def test_tax_flag_is_per_session(pipeline):
    r1 = pair_failing(IDS8, {"on"}, "looping", "flags")
    ids2 = W.DEFAULT_IDS["s2"]
    flagged = {"passed": False, "converged": False, "nonconv_kind": "looping", "nonconv_flags": ["looping"]}
    _, _, sig = pipeline(rows={("on", "s1"): r1["on"], ("off", "s1"): r1["off"],
                               ("on", "s2"): {"go/h1": flagged}, ("off", "s2"): {"go/h1": flagged}})
    t = V.flag_text(sig)
    assert "looping" in t and "s1" in t


# ----------------------------------------------------------------------------------------------- several at once
# class: new-behaviour (two independent triggers raise two flags; both numbers are carried)
def test_two_flags_carry_both_numbers(pipeline):
    on = {i: {"accepted": 60, "proposed": 100, "rate": 24.0} for i in IDS8}
    _, _, sig = pipeline(speed={("on", "s1"): on})
    assert carries(sig, 0.60) and carries(sig, 1.2)


# class: new-behaviour (flags never veto: the sheet still carries the statistics next to a raised flag)
def test_flags_do_not_remove_the_statistics(pipeline):
    _, _, sig = pipeline(rows={("on", "s1"): {"python/a3": {"passed": False}}})
    assert V.has_num(sig, "s1", -0.125, sess_tree=V.scope(sig, "s1"))
