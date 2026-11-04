"""B6 Wave 1 flags (contract "Flags (Wave 1), each with its number and items") raised AND not raised, the zero-discordance cell of a
clean world, and the boundaries (exactly -5 pp, exactly 0.70, exactly +2 GB, exactly 48 GB).

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
A flag is detected by the number it carries (fraction or percent form, display-rounded) inside the sheet's `*flag*` subtree.
"""
from __future__ import annotations

import math

import pytest

from bench.tests.p613 import sigview as SV
from bench.tests.p613s2 import w1view as V
from bench.tests.p613s2 import wave1world as WW

D = WW.draft
NC = dict(WW.NONCONV)


def a(i):
    return f"test/algebra/{i}.json"


def fpool(sig):
    return SV.flag_numbers(sig)


def carries(sig, x, tol=1e-3):
    return V.has(fpool(sig), x, tol)


def carries_direct(sig, x, tol=1e-3):
    """Fraction form ONLY (no x100 reading): `150 / 300` is never read as 1.5 (amended, delivery 3)."""
    return any(abs(v - x) <= tol for v in fpool(sig))


def no_flags(sig):
    assert SV.flags_tree(sig), "the sheet has a flags section"
    assert SV.flag_numbers(sig) == [], SV.flag_text(sig)


# ------------------------------------------------------------------------------------------------------------ clean world
@pytest.fixture(scope="module")
def C(scenario):
    return lambda: scenario("C", n_math=50)


# class: new-behaviour (a clean pair raises nothing: the flags section exists and carries no number)
def test_clean_world_raises_no_flag(C):
    _, b8, sig = C()
    no_flags(sig)
    assert b8["cross_wave"]["flag"] is False


# class: new-behaviour (zero discordance: delta 0, CI [0, 0], loss bound = exact 1 - 0.05^(1/n) (n = 50 per block, 100 both), MDE default row)
def test_zero_discordance_bounds_and_mde(C):
    from bench import stats
    _, _, sig = C()
    pool = V.axis_pool(sig, "A1")
    for n in (50, 100):
        assert V.has(pool, 1 - 0.05 ** (1 / n), 1e-4), n
        assert V.has(pool, stats.mde(n), 1e-3), n
    assert V.has(pool, 0.0) and V.has(pool, 1.0)
    txt = V.axis_text(sig, "A1")
    assert "default" in txt.lower() or "0.2" in txt


# class: new-behaviour (zero-discordance bound 5.8 pp / 2.9 pp is <= 10 pp: no "loss not ruled out above X pp"; the label is WASH)
def test_zero_discordance_label_and_loss_text(C):
    _, _, sig = C()
    strs = SV.strings(V.axis_tree(sig, "A1"))
    assert SV.wash(strs) and not SV.shown(strs)
    assert not any("loss not ruled out" in s for s in strs)


# class: new-behaviour (identical outcomes: permutation p 1.0 and Holm-adjusted 1.0 for the three members, m = 3)
def test_zero_discordance_permutation_and_holm(C):
    _, _, sig = C()
    pool = SV.numbers(SV.subtree(sig, "family"))
    assert pool and V.has(pool, 3.0) and sum(1 for p in pool if abs(p - 1.0) < 1e-9) >= 3


# ------------------------------------------------------------------------------------------------------------- raised world
F_SPEC = dict(n_math=10, rows={
    ("math500", "on", "b1"): {**{a(i): {"ok": False, "decode_tps": 22.0} for i in (1, 2, 3, 4)},
                              **{a(i): {"decode_tps": 22.0} for i in range(5, 11)}},
    ("math500", "on", "b2"): {a(11): {"ok": False, **NC}, a(12): {"ok": False}, a(13): {"ok": False}, a(14): {"ok": False}},
    ("cjudge", "on", "b1"): {k: {"draft": D("on", 100, 50)} for k in ("dom-01", "dom-02", "pub-aaa")},
    ("cjudge", "on", "b2"): {"dom-04": {"converged": False, "nonconv_kind": "max_tokens", "finish_reason": "length",
                                        "completion_tokens": 102400}},
    ("vision", "on", "b2"): {k: {"draft": D("on", 100, 60)} for k in ("cocoval2017-002", "cocoval2017-003")},
    ("reasoning", "on", "b1"): {s: {"draft": D("on", 200, 110)} for s in (128000000, 128000001)},
    ("m1", "on", "b1"): {"peaks": {"prefill": WW.M1_PEAKS[("off", "b1")][0] + 2_500_000_000}},
}, w2={"main_models.yaml": WW.registry_text(other="b")})


@pytest.fixture(scope="module")
def F(scenario):
    return lambda: scenario("F", **F_SPEC)


# class: new-behaviour (A1 point < -5 pp raises, per block and both, carrying -40 pp and the OFF-only items)
def test_flag_a1_point_below_minus_5pp(F):
    _, _, sig = F()
    assert carries(sig, -0.4)
    txt = SV.flag_text(F()[2])
    assert "a1" in txt and a(1).lower() in txt and a(11).lower() in txt


# class: new-behaviour (A1 Holm p < .05 with OFF better raises, carrying the Holm-adjusted p of the permutation over 8 OFF-only items)
def test_flag_a1_holm_p_with_off_better(F):
    w, _, sig = F()
    diffs = V.a1_strict_diffs(w)        # both blocks sorted (block, id), as the contract fixes
    assert sorted(diffs) == [-1.0] * 8 + [0.0] * 12
    p_raw = V.perm_p(diffs)
    adj = V.holm([p_raw, 1.0, 1.0])[0]
    assert adj < 0.05 and abs(p_raw - 2 / 256) < 2e-3
    assert carries(sig, adj, 1e-4), (adj, fpool(sig))
    assert "holm" in SV.flag_text(sig)


# class: new-behaviour (A1 decode ratio point < 1.3 raises, carrying the geometric mean 1.1 (ON tps 22 / OFF 20) of b1)
def test_flag_a1_decode_ratio_below_1_3(F):
    _, _, sig = F()
    assert carries(sig, 1.1, 2e-3)
    assert not carries_direct(sig, 1.5, 2e-3), "b2 (ratio 1.5) is not flagged"


# class: new-behaviour (acceptance < 0.70 per axis x (block, both): A2 b1 .5 and both .625, A3 b2 .6, A4 b1 .55)
def test_flag_acceptance_below_070_per_axis(F):
    _, _, sig = F()
    txt = SV.flag_text(sig)
    assert carries(sig, 0.5, 1e-4) and carries(sig, 0.625, 1e-4)      # A2 b1, A2 both
    assert carries(sig, 0.6, 1e-4)                                    # A3 b2
    assert carries(sig, 0.55, 1e-4)                                   # A4 b1
    for ax in ("a2", "a3", "a4"):
        assert ax in txt, ax


# class: new-behaviour (acceptance flags NOT raised for cells at or above 0.70: A2 b2 .75, A3 b1 .72, A4 b2 .9, A1 .8)
def test_acceptance_flags_not_raised_above_070(F):
    _, _, sig = F()
    for x in (0.75, 0.72, 0.9, 0.8):
        assert not carries_direct(sig, x, 1e-4), x


# class: new-behaviour (M1: ON prefill peak > OFF + 2e9 bytes raises (b1: +2.5 GB), carrying the peak; b2 (+0.314 GB) does not)
def test_flag_m1_prefill_over_off_plus_2gb(F):
    _, _, sig = F()
    pool = fpool(sig)
    on1 = WW.M1_PEAKS[("off", "b1")][0] + 2_500_000_000
    assert any(abs(p - on1) < 1 for p in pool) or any(abs(p - round(on1 / 1e9, 3)) < 1e-3 for p in pool), pool
    assert not any(abs(p - 0.314) < 1e-3 for p in pool)
    assert "m1" in SV.flag_text(sig)


# class: new-behaviour (a nonconv_kind present in ON and absent in OFF raises per axis and block, naming the kind and the item)
def test_flag_nonconv_kind_on_only(F):
    _, _, sig = F()
    txt = SV.flag_text(sig)
    assert "budget_hit" in txt and a(11).lower() in txt           # A1 b2
    assert "max_tokens" in txt and "dom-04" in txt                # A2 b2


# class: new-behaviour (the B8 cross-wave flag is listed with files, entry_equal, globals_equal; it is a flag, not a refusal)
def test_flag_cross_wave_lists_files_and_evidence(F):
    w, b8, sig = F()
    txt = SV.flag_text(sig)
    assert "main_models.yaml" in txt
    import re
    assert re.search(r"entry[_ ]equal", txt) and re.search(r"globals[_ ]equal", txt)
    assert b8["cross_wave"]["flag"] is True and V.accepted_all(b8)


# class: invariant (no A7 flag is raised by Wave 1 changes: the A7 world is clean)
def test_flags_do_not_name_a7(F):
    _, _, sig = F()
    assert "a7" not in SV.flag_text(sig)


# ------------------------------------------------------------------------------------------------------ not raised: boundaries
NB_SPEC = dict(n_math=20, rows={
    ("math500", "on", "b1"): {a(1): {"ok": False}, a(2): NC},          # strict 18/20 vs OFF 19/20 = exactly -5 pp (a(2) nonconv in both arms)
    ("math500", "off", "b1"): {a(2): NC},
    ("cjudge", "on", "b1"): {k: {"draft": D("on", 100, 70)} for k in ("dom-01", "dom-02", "pub-aaa")},      # exactly 0.70
    ("vision", "on", "b1"): {k: {"turn2": {"prompt_tokens": 672, "completion_tokens": 162, "wall_s": 4.9, "finish_reason": "stop",
                                            "converged": True, "draft": D("on", 100, 5), "seed": 1, "session_id": "t2"}}
                             for k in ("cocoval2017-000", "cocoval2017-001")},                             # turn 2 acceptance .05: not counted
    ("m1", "on", "b1"): {"peaks": {"prefill": WW.M1_PEAKS[("off", "b1")][0] + 2_000_000_000}},            # exactly OFF + 2e9
    ("m1", "off", "b2"): {"peaks": {"prefill": 47_000_000_000}},
    ("m1", "on", "b2"): {"peaks": {"prefill": 48_000_000_000}},                                           # exactly 48e9, +1e9
})


# class: new-behaviour (boundaries are NOT flags: exactly -5 pp, exactly 0.70, exactly OFF + 2e9, exactly 48e9, turn-2 acceptance, a kind in both arms)
def test_boundaries_raise_nothing(scenario):
    w, b8, sig = scenario("NB", **NB_SPEC)
    assert V.accepted_all(b8)
    no_flags(sig)


# class: new-behaviour (an ON GAIN raises no point / Holm flag even when the permutation p < .05)
def test_gain_raises_no_flag(scenario):
    rows = {("math500", "off", "b1"): {a(i): {"ok": False} for i in (1, 2, 3, 4)},
            ("math500", "off", "b2"): {a(i): {"ok": False} for i in (11, 12, 13, 14)}}
    w, b8, sig = scenario("G", n_math=10, rows=rows)
    no_flags(sig)


# class: new-behaviour (M1 absolute rule: ON prefill peak > 48e9 bytes raises even when ON - OFF < 2e9)
def test_flag_m1_prefill_over_48gb(scenario):
    rows = {("m1", "off", "b2"): {"peaks": {"prefill": 47_500_000_000}}, ("m1", "on", "b2"): {"peaks": {"prefill": 48_500_000_000}}}
    w, b8, sig = scenario("M48", rows=rows)
    pool = fpool(sig)
    assert any(abs(p - 48_500_000_000) < 1 for p in pool) or any(abs(p - 48.5) < 1e-3 for p in pool), pool


# class: new-behaviour (A3 acceptance flag counts turn 1: a turn-1 acceptance under 0.70 raises it even when turn 2 is above it)
def test_flag_a3_uses_turn_one(scenario):
    t2 = {"prompt_tokens": 672, "completion_tokens": 162, "wall_s": 4.9, "finish_reason": "stop", "converged": True,
          "draft": D("on", 100, 99), "seed": 1, "session_id": "t2"}
    rows = {("vision", "on", "b1"): {k: {"draft": D("on", 100, 40), "turn2": t2} for k in ("cocoval2017-000", "cocoval2017-001")}}
    w, b8, sig = scenario("A3T1", rows=rows)
    assert carries(sig, 0.4, 1e-4)
    assert not carries(sig, 0.695, 1e-3), "turn 1 + turn 2 pooled would be .695"
