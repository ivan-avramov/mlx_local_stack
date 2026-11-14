"""M76 B7 (spec v1.1) — `bench.stats` additions: `paired_delta` alphas, `paired_session_delta`, `obf_alpha`, `obf_looks`.

Classes: (a) fixed by the specification text / a mathematical identity; (b) fixed by an independent reference written
here from the specification, or by the golden values captured by running the BASELINE `paired_delta`; (c) the
specification leaves the detail open (noted per test).
New-API imports are inside the tests so that baseline failures are per test, not at collection.
"""
import math
import random
from statistics import NormalDist

import pytest

import bench.stats as S

# ----------------------------------------------------------------------------- paired_delta golden (baseline)
_A = {i: [1, 1] if i < 6 else ([1, 0] if i < 8 else [0, 0]) for i in range(10)}
_B = {i: [1, 1] if i < 5 else ([0, 1] if i < 8 else [0, 0]) for i in range(10)}
_GOLDEN_1 = {'delta': 0.04999999999999993, 'lo': -0.12624999999999992, 'hi': 0.25, 'verdict': 'wash', 'n_items': 10,
             'mde': 0.3962039503141028, 'degenerate': False, 'discordance_upper95': None, 'directional': 'a'}
_GOLDEN_2 = {'delta': 0.0, 'lo': 0.0, 'hi': 0.0, 'verdict': 'wash', 'n_items': 8, 'mde': 0.4429694829281415,
             'degenerate': True, 'discordance_upper95': 0.31234397806636793, 'directional': 'tie'}


def test_paired_delta_default_golden_nondegenerate():  # (b) golden from baseline run; green before the change
    out = S.paired_delta(_A, _B, iters=500, seed=7)
    assert out == _GOLDEN_1
    assert list(out) == list(_GOLDEN_1), "key order unchanged"


def test_paired_delta_default_golden_zero_discordance():  # (b) golden from baseline run
    a = {i: [1] for i in range(8)}
    out = S.paired_delta(a, dict(a), iters=200, seed=1)
    assert out == _GOLDEN_2
    assert list(out) == list(_GOLDEN_2)


def test_paired_delta_default_has_no_new_key():  # (a) spec v1.1: discordance_upper only for non-default alpha
    out = S.paired_delta(_A, _B, iters=200, seed=7)
    assert "discordance_upper" not in out
    a = {i: [1] for i in range(8)}
    assert "discordance_upper" not in S.paired_delta(a, dict(a), iters=50, seed=1)


def test_paired_delta_explicit_default_alphas_equal_golden():  # (a)
    out = S.paired_delta(_A, _B, iters=500, seed=7, interval_alpha=0.05, exact_alpha=0.05)
    assert out == _GOLDEN_1


def test_paired_delta_interval_alpha_sets_percentiles():  # (a) same seed+iters => same replicates, other percentiles
    wide = S.paired_delta(_A, _B, iters=2000, seed=3)
    mid = S.paired_delta(_A, _B, iters=2000, seed=3, interval_alpha=0.10)
    narrow = S.paired_delta(_A, _B, iters=2000, seed=3, interval_alpha=0.50)
    assert wide["lo"] <= mid["lo"] <= narrow["lo"] <= narrow["hi"] <= mid["hi"] <= wide["hi"]
    assert (wide["lo"], wide["hi"]) != (mid["lo"], mid["hi"])
    assert mid["delta"] == wide["delta"]
    assert "discordance_upper" in mid


def test_paired_delta_interval_alpha_matches_percentile_of_reference_replicates():  # (b) independent re-implementation
    """Re-run the documented two-stage bootstrap here (same rng call order as the baseline) and read the percentiles."""
    ids = sorted(_A)
    n = len(ids)
    rng = random.Random(11)
    reps = []
    for _ in range(1000):
        sa = sb = 0.0
        for _ in range(n):
            idx = rng.randrange(n)
            da, db = _A[ids[idx]], _B[ids[idx]]
            sa += sum(da[rng.randrange(len(da))] for _ in range(len(da))) / len(da)
            sb += sum(db[rng.randrange(len(db))] for _ in range(len(db))) / len(db)
        reps.append((sa - sb) / n)
    reps.sort()
    got = S.paired_delta(_A, _B, iters=1000, seed=11, interval_alpha=0.01)
    # percentile interpolation convention is the module's own; allow one order-statistic of slack
    assert reps[0] <= got["lo"] <= reps[15]
    assert reps[984] <= got["hi"] <= reps[-1]


def test_paired_delta_exact_alpha_bound_values():  # (a) closed form 1 - alpha^(1/n)
    a = {i: [1] for i in range(8)}
    for ea in (0.025, 0.01):
        out = S.paired_delta(a, dict(a), iters=50, seed=1, exact_alpha=ea)
        assert out["discordance_upper"] == pytest.approx(1 - ea ** (1 / 8))
    # default exact_alpha with a non-default interval alpha: the bound is the 0.05 one, under the new key
    out = S.paired_delta(a, dict(a), iters=50, seed=1, interval_alpha=0.10)
    assert out["discordance_upper"] == pytest.approx(1 - 0.05 ** (1 / 8))


def test_paired_delta_exact_alpha_does_not_move_interval():  # (a)
    x = S.paired_delta(_A, _B, iters=500, seed=7)
    y = S.paired_delta(_A, _B, iters=500, seed=7, exact_alpha=0.025)
    assert (x["lo"], x["hi"], x["delta"]) == (y["lo"], y["hi"], y["delta"])


# ----------------------------------------------------------------------------- paired_session_delta
def _psd():
    from bench.stats import paired_session_delta
    return paired_session_delta


def _anti_case():
    """20 items x 2 sessions. Items 0-9: session 1 X-fail/N16-pass... d = (+1, -1): each item's two sessions cancel.
    Items 10-19: no difference. Paired (item-vector) resampling => every resampled item has mean difference 0."""
    a, b = {}, {}
    for i in range(20):
        if i < 10:
            a[i], b[i] = {"s1": 1, "s2": 0}, {"s1": 0, "s2": 1}
        else:
            a[i], b[i] = {"s1": 1, "s2": 1}, {"s1": 1, "s2": 1}
    return a, b


def _independent_width(a, b, iters=2000, seed=5):
    """Reference: resample items for each session INDEPENDENTLY (what the spec forbids)."""
    items = sorted(a)
    sess = sorted(a[items[0]])
    rng = random.Random(seed)
    reps = []
    for _ in range(iters):
        tot = 0.0
        for s in sess:
            tot += sum(a[i][s] - b[i][s] for i in (items[rng.randrange(len(items))] for _ in items)) / len(items)
        reps.append(tot / len(sess))
    reps.sort()
    return reps[int(0.975 * iters)] - reps[int(0.025 * iters)]


def test_session_delta_keeps_item_session_vectors_together():  # (a)+(b) the constructed case of acceptance 1
    a, b = _anti_case()
    out = _psd()(a, b, iters=2000, seed=5)
    assert out["delta"] == pytest.approx(0.0)
    assert out["lo"] == pytest.approx(0.0, abs=1e-12) and out["hi"] == pytest.approx(0.0, abs=1e-12)
    assert out["degenerate"] is True or out["degenerate"] == True  # noqa: E712
    assert _independent_width(a, b) > 0.2, "reference: independent resampling would give a wide interval"


def test_session_delta_point_estimate_and_counts():  # (a)
    a = {1: {"s1": 1, "s2": 1, "s3": 0}, 2: {"s1": 0, "s2": 0, "s3": 0}, 3: {"s1": 1, "s2": 0, "s3": 1}}
    b = {1: {"s1": 0, "s2": 1, "s3": 0}, 2: {"s1": 0, "s2": 1, "s3": 0}, 3: {"s1": 0, "s2": 0, "s3": 0}}
    out = _psd()(a, b, iters=300, seed=426)
    # item means of d: 1/3, -1/3, 2/3 -> mean 2/9
    assert out["delta"] == pytest.approx(2 / 9)
    assert out["n_items"] == 3 and out["n_sessions"] == 3
    assert out["lo"] <= out["delta"] <= out["hi"]


def test_session_delta_per_session_results():  # (a)
    a, b = _anti_case()
    out = _psd()(a, b, iters=500, seed=5)
    ps = out["per_session"]
    assert set(ps) == {"s1", "s2"}
    assert ps["s1"]["delta"] == pytest.approx(0.5) and ps["s2"]["delta"] == pytest.approx(-0.5)
    for s in ps:
        assert ps[s]["n_items"] == 20
        assert ps[s]["lo"] <= ps[s]["delta"] <= ps[s]["hi"]
    assert ps["s1"]["lo"] > 0 > ps["s2"]["hi"], "each session's own interval is not the pooled (degenerate) one"


def test_session_delta_single_session_close_to_paired_delta():  # (c) seeds differ in rng order; only closeness is claimed
    rng = random.Random(9)
    a = {i: {"s": int(rng.random() < 0.8)} for i in range(60)}
    b = {i: {"s": int(rng.random() < 0.7)} for i in range(60)}
    out = _psd()(a, b, iters=4000, seed=426)
    ref = S.paired_delta({i: [a[i]["s"]] for i in a}, {i: [b[i]["s"]] for i in b}, iters=4000, seed=426)
    assert out["delta"] == pytest.approx(ref["delta"])
    assert out["lo"] == pytest.approx(ref["lo"], abs=0.04)
    assert out["hi"] == pytest.approx(ref["hi"], abs=0.04)


def test_session_delta_refuses_mismatched_items():  # (a)
    a, b = _anti_case()
    del b[3]
    with pytest.raises(ValueError, match="3"):
        _psd()(a, b, iters=50)


def test_session_delta_refuses_mismatched_sessions():  # (a)
    a, b = _anti_case()
    b[4] = {"s1": 0, "s3": 1}
    with pytest.raises(ValueError, match="s2|s3"):
        _psd()(a, b, iters=50)


def test_session_delta_refuses_session_set_differing_across_items():  # (a) "identical item and session sets"
    a, b = _anti_case()
    a[7] = {"s1": 1}
    b[7] = {"s1": 0}
    with pytest.raises(ValueError):
        _psd()(a, b, iters=50)


def test_session_delta_deterministic_under_seed_and_seed_matters():  # (a)
    rng = random.Random(2)
    a = {i: {s: int(rng.random() < 0.7) for s in "xyz"} for i in range(25)}
    b = {i: {s: int(rng.random() < 0.6) for s in "xyz"} for i in range(25)}
    one = _psd()(a, b, iters=800, seed=426)
    two = _psd()(a, b, iters=800, seed=426)
    other = _psd()(a, b, iters=800, seed=427)
    assert one == two
    assert (one["lo"], one["hi"]) != (other["lo"], other["hi"])


def test_session_delta_alphas():  # (a)
    rng = random.Random(4)
    a = {i: {s: int(rng.random() < 0.7) for s in "xy"} for i in range(30)}
    b = {i: {s: int(rng.random() < 0.55) for s in "xy"} for i in range(30)}
    f = _psd()
    d05 = f(a, b, iters=2000, seed=1)
    d01 = f(a, b, iters=2000, seed=1, interval_alpha=0.01)
    assert d01["lo"] <= d05["lo"] and d01["hi"] >= d05["hi"] and (d01["lo"], d01["hi"]) != (d05["lo"], d05["hi"])
    assert d01["delta"] == d05["delta"]


def test_session_delta_zero_discordance_exact_bound():  # (a)
    a = {i: {"s1": i % 2, "s2": 1} for i in range(10)}
    b = {i: dict(a[i]) for i in a}
    f = _psd()
    out = f(a, b, iters=200, seed=426)
    assert out["degenerate"] and out["discordant_items"] == 0 and out["delta"] == 0
    assert out["discordance_upper"] == pytest.approx(1 - 0.05 ** (1 / 10))
    out2 = f(a, b, iters=200, seed=426, exact_alpha=0.025)
    assert out2["discordance_upper"] == pytest.approx(1 - 0.025 ** (1 / 10))


def test_session_delta_strata_hold_stratum_sizes():  # (a) within-stratum resampling keeps the stratum mix fixed
    a = {i: {"s1": 1, "s2": 1} for i in range(10)}
    b = {i: {"s1": 1, "s2": 1} for i in range(10)}
    for i in range(5):
        b[i] = {"s1": 0, "s2": 0}           # stratum "X": d = 1 on both sessions; stratum "Y": d = 0
    strata = {i: ("X" if i < 5 else "Y") for i in range(10)}
    f = _psd()
    with_s = f(a, b, iters=500, seed=3, strata=strata)
    without = f(a, b, iters=500, seed=3)
    assert with_s["delta"] == pytest.approx(0.5)
    assert with_s["lo"] == pytest.approx(0.5) and with_s["hi"] == pytest.approx(0.5)
    assert without["lo"] < 0.5 < without["hi"]


# ----------------------------------------------------------------------------- Lan-DeMets O'Brien-Fleming
def _ref_obf(t, alpha):
    nd = NormalDist()
    return 2 * (1 - nd.cdf(nd.inv_cdf(1 - alpha / 2) / math.sqrt(t)))


def test_obf_alpha_at_one_is_total_alpha():  # (a)
    from bench.stats import obf_alpha
    for a in (0.025, 0.05, 0.01):
        assert obf_alpha(1, a) == pytest.approx(a, rel=1e-9)
        assert obf_alpha(1.0, a) == pytest.approx(a, rel=1e-9)


def test_obf_alpha_known_values():  # (a)+(b) closed form recomputed here; literal bands from the spec's 99.979 / 98.79 %
    from bench.stats import obf_alpha
    a13, a23 = obf_alpha(1 / 3, 0.025), obf_alpha(2 / 3, 0.025)
    assert a13 == pytest.approx(_ref_obf(1 / 3, 0.025), rel=1e-6)
    assert a23 == pytest.approx(_ref_obf(2 / 3, 0.025), rel=1e-6)
    assert 1 - 2 * a13 == pytest.approx(0.99979, abs=2e-5)   # look-1 two-sided interval level, Math500
    assert 1 - 2 * a23 == pytest.approx(0.9879, abs=2e-4)    # tg1


def test_obf_alpha_monotone_in_t_and_in_alpha():  # (a)
    from bench.stats import obf_alpha
    ts = [0.1, 0.25, 1 / 3, 0.5, 2 / 3, 0.9, 1.0]
    v = [obf_alpha(t, 0.025) for t in ts]
    assert v == sorted(v) and v[0] > 0
    assert obf_alpha(0.5, 0.01) < obf_alpha(0.5, 0.025) < obf_alpha(0.5, 0.05)


def test_obf_looks_two_looks():  # (a)
    from bench.stats import obf_alpha, obf_looks
    looks = obf_looks([1 / 3, 1.0], 0.025)
    assert len(looks) == 2
    assert looks[0] == pytest.approx(obf_alpha(1 / 3, 0.025))
    assert looks[1] == pytest.approx(0.025 - obf_alpha(1 / 3, 0.025))
    assert sum(looks) == pytest.approx(0.025)
    assert 0 < looks[0] < looks[1]


def test_obf_looks_single_look_and_three_looks():  # (a)
    from bench.stats import obf_alpha, obf_looks
    assert list(obf_looks([1.0], 0.025)) == pytest.approx([0.025])
    three = obf_looks([0.25, 0.5, 1.0], 0.025)
    assert sum(three) == pytest.approx(0.025)
    assert three[0] == pytest.approx(obf_alpha(0.25, 0.025))
    assert three[1] == pytest.approx(obf_alpha(0.5, 0.025) - obf_alpha(0.25, 0.025))
