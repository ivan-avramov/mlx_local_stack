"""M76 B7 criteria 1 / 4: `paired_delta` alphas, `paired_session_delta`, O'Brien–Fleming spending,
`exact_paired_loss` (v1.1)."""
import math
import random

import pytest

import bench.stats as S

from bench.tests.test_m76_b7_impl_golden import A, B, A1, B1


# ------------------------------------------------------------------------------------------ paired_delta alphas
def test_paired_delta_interval_alpha_widens_and_matches_percentiles():
    d95 = S.paired_delta(A, B, iters=2000, seed=426)
    d99 = S.paired_delta(A, B, iters=2000, seed=426, interval_alpha=0.01)
    assert d99["lo"] <= d95["lo"] and d99["hi"] >= d95["hi"]
    assert d99["delta"] == d95["delta"]
    assert d99["interval_alpha"] == 0.01 and d99["exact_alpha"] == 0.05
    assert d99["discordance_upper"] is None and d99["discordance_upper95"] is None   # not degenerate


def test_paired_delta_exact_alpha_bound():
    d = S.paired_delta(A1, B1, iters=500, seed=426, interval_alpha=0.05, exact_alpha=0.025)
    assert d["degenerate"] is True
    assert d["discordance_upper"] == pytest.approx(1 - 0.025 ** (1 / 12))
    assert d["discordance_upper95"] is None           # the 95 % key is not the 0.025 bound
    d2 = S.paired_delta(A1, B1, iters=500, seed=426, interval_alpha=0.01)
    assert d2["discordance_upper"] == d2["discordance_upper95"] == pytest.approx(1 - 0.05 ** (1 / 12))


def test_paired_delta_default_dict_has_no_new_keys():
    d = S.paired_delta(A, B, iters=200, seed=1)
    assert "discordance_upper" not in d and "interval_alpha" not in d


@pytest.mark.parametrize("bad", [0, 1, -0.1, 1.5])
def test_paired_delta_refuses_bad_alpha(bad):
    with pytest.raises(ValueError):
        S.paired_delta(A, B, iters=10, interval_alpha=bad)


# ------------------------------------------------------------------------------------------ paired_session_delta
def _case():
    """Items whose two sessions move together: an item where X loses in s1 also loses in s2."""
    a, b = {}, {}
    for j in range(30):
        if j < 6:
            a[j], b[j] = {"s1": 0, "s2": 0}, {"s1": 1, "s2": 1}
        elif j < 9:
            a[j], b[j] = {"s1": 1, "s2": 1}, {"s1": 0, "s2": 0}
        else:
            a[j], b[j] = {"s1": 1, "s2": 1}, {"s1": 1, "s2": 1}
    return a, b


def _independent_session_bootstrap(a, b, iters, seed):
    """What C324 forbids: resample items, then each arm's sessions independently."""
    rng = random.Random(seed)
    ids = sorted(a)
    n = len(ids)
    reps = []
    for _ in range(iters):
        t = 0.0
        for _ in range(n):
            i = ids[rng.randrange(n)]
            ss = sorted(a[i])
            sa = sum(a[i][ss[rng.randrange(len(ss))]] for _ in ss) / len(ss)
            sb = sum(b[i][ss[rng.randrange(len(ss))]] for _ in ss) / len(ss)
            t += sa - sb
        reps.append(t / n)
    reps.sort()
    return S._percentile(reps, 0.025), S._percentile(reps, 0.975)


def test_paired_session_delta_keeps_session_vectors_together():
    a, b = _case()
    r = S.paired_session_delta(a, b, iters=4000, seed=426)
    assert r["delta"] == pytest.approx(-0.1)
    assert r["n_items"] == 30 and r["n_sessions"] == 2 and r["discordant_items"] == 9
    # paired resampling: each item contributes −1, +1 or 0 as a unit — the replicate grid is k/30
    lo, hi = r["lo"], r["hi"]
    assert abs(lo * 30 - round(lo * 30)) < 1e-9 and abs(hi * 30 - round(hi * 30)) < 1e-9


def test_paired_session_delta_differs_from_independent_session_resampling():
    # 12 items where both arms agree per session but the sessions differ (a = b = (1, 0)): paired d = (0, 0) always;
    # resampling each arm's sessions independently invents noise there and widens the interval
    a, b = {}, {}
    for j in range(30):
        if j < 12:
            a[j], b[j] = {"s1": 1, "s2": 0}, {"s1": 1, "s2": 0}
        elif j < 16:
            a[j], b[j] = {"s1": 0, "s2": 0}, {"s1": 1, "s2": 1}
        else:
            a[j], b[j] = {"s1": 1, "s2": 1}, {"s1": 1, "s2": 1}
    r = S.paired_session_delta(a, b, iters=4000, seed=426)
    ilo, ihi = _independent_session_bootstrap(a, b, 4000, 426)
    assert r["delta"] == pytest.approx(-4 / 30)
    assert ihi - ilo > (r["hi"] - r["lo"]) + 0.05
    assert r["hi"] <= 0.0 < ihi                       # paired: no positive replicate is possible; independent: it is


def test_paired_session_delta_cross_session_cancel_differs_from_pooled_draws():
    # item-level vectors (−1, +1): pairing keeps the cancellation inside the item → v = 0 for every item → degenerate
    a = {j: {"s1": 0, "s2": 1} for j in range(10)}
    b = {j: {"s1": 1, "s2": 0} for j in range(10)}
    r = S.paired_session_delta(a, b, iters=1000, seed=426)
    assert r["lo"] == r["hi"] == 0.0 and r["degenerate"] is True
    assert r["discordant_items"] == 10 and r["discordance_upper"] is None
    # the session-by-session view sees opposite, large effects
    assert r["per_session"]["s1"]["delta"] == -1.0 and r["per_session"]["s2"]["delta"] == 1.0


def test_paired_session_delta_zero_discordance_exact_bound():
    a = {j: {1: 1, 2: 1} for j in range(40)}
    r = S.paired_session_delta(a, {j: dict(v) for j, v in a.items()}, iters=200, exact_alpha=0.025, interval_alpha=0.05)
    assert r["degenerate"] and r["discordant_items"] == 0
    assert r["discordance_upper"] == pytest.approx(1 - 0.025 ** (1 / 40))
    assert r["discordance_upper"] == pytest.approx(0.0881, abs=1e-4)


def test_paired_session_delta_per_session_is_paired_delta():
    a, b = _case()
    r = S.paired_session_delta(a, b, iters=1500, seed=11)
    for s in ("s1", "s2"):
        ref = S.paired_delta({i: [a[i][s]] for i in a}, {i: [b[i][s]] for i in b}, iters=1500, seed=11)
        assert r["per_session"][s] == ref


def test_paired_session_delta_alpha_and_strata():
    a, b = _case()
    r95 = S.paired_session_delta(a, b, iters=3000, seed=426)
    r99 = S.paired_session_delta(a, b, iters=3000, seed=426, interval_alpha=0.01)
    assert r99["lo"] <= r95["lo"] and r99["hi"] >= r95["hi"]
    st = {i: i % 3 for i in a}
    rs = S.paired_session_delta(a, b, iters=3000, seed=426, strata=st)
    assert rs["delta"] == r95["delta"]
    assert S.paired_session_delta(a, b, iters=3000, seed=426, strata=st) == rs   # reproducible


def test_paired_session_delta_refuses_mismatched_items():
    a, b = _case()
    del b[3]
    with pytest.raises(ValueError, match=r"item sets differ.*a-only=\[3\]"):
        S.paired_session_delta(a, b, iters=10)


def test_paired_session_delta_refuses_mismatched_sessions():
    a, b = _case()
    b[4] = {"s1": 1, "s3": 1}
    with pytest.raises(ValueError, match=r"item 4.*session sets differ.*a-only=\['s2'\].*b-only=\['s3'\]"):
        S.paired_session_delta(a, b, iters=10)


def test_paired_session_delta_refuses_ragged_sessions():
    a, b = _case()
    a[5] = {"s1": 1}
    b[5] = {"s1": 1}
    with pytest.raises(ValueError, match="sessions"):
        S.paired_session_delta(a, b, iters=10)


# ------------------------------------------------------------------------------------------ O'Brien–Fleming
def test_obf_alpha_at_one_is_alpha():
    for a in (0.025, 0.05, 0.01):
        assert S.obf_alpha(1, a) == a
        assert S.obf_alpha(1.0, a) == a


def test_obf_alpha_known_values():
    # α(t) = 2(1 − Φ(z_{0.9875}/√t)), z_{0.9875} = 2.241403
    z = 2.2414027276049473
    assert S._phi_inv(1 - 0.025 / 2) == pytest.approx(z, abs=1e-9)
    assert S.obf_alpha(1 / 3, 0.025) == pytest.approx(math.erfc(z * math.sqrt(3) / math.sqrt(2)), rel=1e-9)
    assert S.obf_alpha(2 / 3, 0.025) == pytest.approx(math.erfc(z / math.sqrt(2 / 3) / math.sqrt(2)), rel=1e-9)
    assert S.obf_alpha(1 / 3, 0.025) == pytest.approx(1.0351e-4, rel=1e-3)
    assert S.obf_alpha(2 / 3, 0.025) == pytest.approx(6.05e-3, rel=5e-3)


def test_obf_looks():
    l1, l2 = S.obf_looks([1 / 3, 1.0], 0.025)
    assert l1 == S.obf_alpha(1 / 3, 0.025)
    assert l2 == pytest.approx(0.025 - l1)
    assert sum(S.obf_looks([2 / 3, 1], 0.025)) == pytest.approx(0.025)
    assert S.obf_looks([1.0], 0.025) == [0.025]
    with pytest.raises(ValueError):
        S.obf_looks([0.5, 0.5], 0.025)
    with pytest.raises(ValueError):
        S.obf_alpha(0, 0.025)
    with pytest.raises(ValueError):
        S.obf_alpha(1.2, 0.025)


# ------------------------------------------------------------------------------------------ exact_paired_loss
def _tango_ref(b, c, n, m):
    """Tango (1998) eq. for x12 = b, x21 = c, δ = m: p̂21 from the quadratic, T = (b − c − nδ)/√(n(2p̂21 + δ(1 − δ)))."""
    A = 2 * n
    B = -b - c + (2 * n - b + c) * m
    C = -c * m * (1 - m)
    p21 = (-B + math.sqrt(B * B - 4 * A * C)) / (2 * A)
    var = n * (2 * p21 + m * (1 - m))
    num = b - c - n * m
    if num == 0:
        return 0.0
    return num / math.sqrt(var) if var > 0 else math.copysign(math.inf, num)


def _pvalue_ref(b, c, n, m, grid):
    t_obs = _tango_ref(b, c, n, m)
    best = 0.0
    for pc in grid:
        pb = pc + m
        p0 = 1 - pb - pc
        s = 0.0
        for x in range(n + 1):
            for y in range(n - x + 1):
                if _tango_ref(x, y, n, m) <= t_obs + 1e-9 * (1 + abs(t_obs)):
                    r = n - x - y
                    s += math.comb(n, x) * math.comb(n - x, y) * pb ** x * pc ** y * (p0 ** r if r else 1.0)
        best = max(best, s)
    return best


@pytest.mark.parametrize("b,c,n", [(1, 0, 10), (0, 0, 10), (2, 1, 12), (0, 3, 12), (3, 3, 15), (0, 1, 8)])
def test_exact_paired_loss_pvalue_by_brute_enumeration(b, c, n):
    grid = [0.45 * j / 30 for j in range(31)]
    r = S.exact_paired_loss(b, c, n, grid=grid)
    assert r["pvalue"] == pytest.approx(_pvalue_ref(b, c, n, 0.10, grid), rel=1e-9, abs=1e-14)
    assert r["reject"] == (r["pvalue"] <= 0.025)
    assert r["delta"] == (c - b) / n


def test_exact_paired_loss_default_grid_and_tango():
    g = S._nuisance_grid(0.10, None, 0.10)
    assert len(g) == 1002 and g[0] == 0.0 and g[-1] == pytest.approx(0.45)
    for b, c, n, m in [(3, 1, 42, 0.1), (0, 0, 20, 0.1), (5, 9, 30, 0.2), (2, 2, 10, 0.0)]:
        assert float(S._tango(b, c, n, m)) == pytest.approx(_tango_ref(b, c, n, m), rel=1e-12, abs=1e-12)
    # default grid against a brute reference on the same 1002 points at small n
    r = S.exact_paired_loss(0, 2, 10)
    assert r["pvalue"] == pytest.approx(_pvalue_ref(0, 2, 10, 0.10, list(g)), rel=1e-9)


def test_exact_paired_loss_bound_monotone_in_b():
    for n in (42, 72):
        for c in (0, 1, 3):
            bounds = [S.exact_paired_loss(b, c, n)["bound"] for b in range(0, 9)]
            assert bounds == sorted(bounds), (n, c, bounds)
            assert all(0.0 <= x <= 1.0 for x in bounds)


def test_exact_paired_loss_bound_is_smallest_rejecting_margin():
    # the skip of margins with t_obs ≥ 0 must not change the result: compare with the plain scan
    n = 20
    for b, c in [(0, 0), (2, 0), (4, 1), (7, 2)]:
        r = S.exact_paired_loss(b, c, n)
        full = None
        for j in range(1001):
            m = j / 1000
            if S._exact_pvalue(n, m, float(S._tango(b, c, n, m)), None, 0.10) <= 0.025:
                full = m
                break
        assert r["bound"] == full and r["bound_attained"] is True
        if r["bound"] > 0:
            below = round(r["bound"] - 0.001, 3)
            assert S.exact_paired_loss(b, c, n, margin=below)["reject"] is False
        assert S.exact_paired_loss(b, c, n, margin=r["bound"])["reject"] is True


def test_exact_paired_loss_bound_not_attained_at_b_equals_n():
    r = S.exact_paired_loss(5, 0, 5)
    assert r["bound"] == 1.0 and r["bound_attained"] is False


@pytest.mark.parametrize("kw", [dict(b=-1, c=0, n=10), dict(b=6, c=5, n=10), dict(b=1, c=0, n=0),
                                dict(b=1.0, c=0, n=10), dict(b=1, c=0, n=10, margin=1.5),
                                dict(b=1, c=0, n=10, alpha=0.0)])
def test_exact_paired_loss_refuses_bad_input(kw):
    with pytest.raises(ValueError):
        S.exact_paired_loss(**kw)


def test_exact_loss_region_is_prefix_and_size():
    n = 48
    region = S.exact_loss_region(n)
    assert region and (0, 0) in region and (n, 0) not in region
    t = {cell: float(S._tango(cell[0], cell[1], n, 0.10)) for cell in region}
    thr = max(t.values())
    for b in range(n + 1):
        for c in range(n - b + 1):
            tt = float(S._tango(b, c, n, 0.10))
            assert ((b, c) in region) == (tt <= thr + 1e-9 * (1 + abs(thr)))
    assert S.exact_loss_size(n, region) <= 0.025
    assert S.exact_loss_size(n, frozenset()) == 0.0


def test_exact_functions_accept_numpy_integers():
    np = pytest.importorskip("numpy")
    want = S.exact_paired_loss(2, 1, 42)
    got = S.exact_paired_loss(np.int64(2), np.int32(1), np.int64(42))
    assert got == want and type(got["b"]) is int and type(got["n"]) is int
    assert S.exact_loss_region(np.int64(42)) == S.exact_loss_region(42)
    with pytest.raises(ValueError):
        S.exact_paired_loss(True, 0, 42)
    with pytest.raises(ValueError):
        S.exact_paired_loss(np.float64(2.0), 0, 42)
