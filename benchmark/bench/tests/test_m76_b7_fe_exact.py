"""M76 B7 (spec v1.1) — A5 exact unconditional loss test: `bench.stats.exact_paired_loss`,
`bench.m76_rule.verdict_a5` and `bench.m76_rule.a5_rejection_region`.

Test classes: (a) behaviour fixed by the specification text / a mathematical identity;
(b) behaviour fixed by an independent brute-force reference written in this file from the specification's
description (Tango 1998 score statistic at the margin with the constrained MLE, p-value = sup over the nuisance
of the exactly enumerated trinomial tail); (c) behaviour the specification leaves open (return shape).

All imports of the new API are inside the tests so a baseline run fails per test (ImportError), not at collection.
"""
import math

import pytest

MARGIN = 0.10
ALPHA = 0.025


# ----------------------------------------------------------------------------- independent reference
def _tango_t(b, c, n, delta=MARGIN):
    """Tango score statistic for H0: p_b - p_c = delta, constrained MLE of the nuisance (p_c = q, p_b = q + delta)."""
    m = n - b - c

    def f(q):
        v = b / (q + delta) - 2 * m / (1 - 2 * q - delta)
        if c:
            v += c / q
        return v

    lo, hi = 1e-15, (1 - delta) / 2 - 1e-15
    if f(lo) <= 0:
        q = 0.0
    elif f(hi) >= 0:
        q = (1 - delta) / 2
    else:
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid) > 0:
                lo = mid
            else:
                hi = mid
        q = (lo + hi) / 2
    var = n * (2 * q + delta - delta * delta)
    return (b - c - n * delta) / math.sqrt(var)


def _pmf(n, b, c, pb, pc):
    p0 = 1 - pb - pc
    # AMENDED (delivery 3): at the nuisance endpoint p_c = (1 - margin)/2 the float 1 - pb - pc is about -1e-17, not 0;
    # treating that as "impossible" dropped all the mass of the (b + c = n) cells there. Clamp rounding noise only.
    if -1e-12 < p0 < 0:
        p0 = 0.0
    if p0 < 0:
        return 0.0
    m = n - b - c
    lg = math.lgamma(n + 1) - math.lgamma(b + 1) - math.lgamma(c + 1) - math.lgamma(m + 1)
    out = lg
    for k, p in ((b, pb), (c, pc), (m, p0)):
        if k:
            if p <= 0:
                return 0.0
            out += k * math.log(p)
    return math.exp(out)


def _ref_pvalue(b, c, n, grid, delta=MARGIN):
    table = {(i, j): _tango_t(i, j, n, delta) for i in range(n + 1) for j in range(n + 1 - i)}
    t_obs = round(table[(b, c)], 9)
    region = [k for k, t in table.items() if round(t, 9) <= t_obs]
    return max(sum(_pmf(n, i, j, q + delta, q) for i, j in region) for q in grid)


def _fine_grid(points=2001):
    top = (1 - MARGIN) / 2
    return [top * k / (points - 1) for k in range(points)]


def _bin_two_sided(b, c):
    k = b + c
    lo = min(b, c)
    p = sum(math.comb(k, i) for i in range(0, lo + 1)) / 2 ** k
    return min(1.0, 2 * p)


def _field(res, *names):
    """Read a named field from a dict / object / (pvalue, reject, bound[, ...]) result."""
    for nm in names:
        if isinstance(res, dict) and nm in res:
            return res[nm]
        if hasattr(res, nm):
            return getattr(res, nm)
    raise AssertionError(f"result {res!r} has none of the fields {names}")


# ----------------------------------------------------------------------------- exact_paired_loss
def test_exact_pvalue_matches_bruteforce_on_explicit_grid():  # (b)
    from bench.stats import exact_paired_loss
    grid = [0.0, 0.1, 0.25, 0.45]
    for n in (6, 8, 10):
        for b, c in ((0, 0), (1, 0), (0, 2), (2, 1), (1, 3), (3, 3), (n - 1, 0)):
            if b + c > n:
                continue
            got = exact_paired_loss(b, c, n, margin=MARGIN, alpha=ALPHA, grid=grid)
            ref = _ref_pvalue(b, c, n, grid)
            assert _field(got, "pvalue") == pytest.approx(ref, abs=1e-9), (n, b, c)


def test_exact_pvalue_default_grid_matches_fine_reference_sup():  # (b)
    from bench.stats import exact_paired_loss
    for n, b, c in ((8, 0, 0), (8, 1, 2), (10, 0, 1), (10, 2, 2), (12, 1, 1)):
        got = exact_paired_loss(b, c, n)
        ref = _ref_pvalue(b, c, n, _fine_grid())
        assert _field(got, "pvalue") == pytest.approx(ref, abs=2e-3), (n, b, c)


def test_exact_reject_iff_pvalue_le_alpha_and_delta_formula():  # (a)
    from bench.stats import exact_paired_loss
    for n, b, c in ((40, 0, 0), (40, 3, 1), (40, 10, 0), (60, 2, 5)):
        r = exact_paired_loss(b, c, n, margin=MARGIN, alpha=ALPHA)
        p = _field(r, "pvalue")
        assert 0.0 <= p <= 1.0
        assert bool(_field(r, "reject")) == (p <= ALPHA)
        assert _field(r, "delta") == pytest.approx((c - b) / n, abs=1e-12)


def test_exact_zero_discordance_n40_rejects_and_pvalue_floor():  # (a)
    """b = c = 0: the point (0, 0) itself carries probability (1 - margin)^n at nuisance 0, so p >= 0.9^40 = 0.0148;
    it still rejects at alpha 0.025."""
    from bench.stats import exact_paired_loss
    r = exact_paired_loss(0, 0, 40)
    assert _field(r, "pvalue") >= 0.9 ** 40 - 1e-9
    assert _field(r, "reject") is True or _field(r, "reject") == True  # noqa: E712
    assert _field(r, "bound") <= 0.10 + 1e-9


def test_exact_clear_loss_does_not_reject():  # (a)
    from bench.stats import exact_paired_loss
    r = exact_paired_loss(10, 0, 40)
    assert not _field(r, "reject")
    assert _field(r, "pvalue") > 0.5
    assert _field(r, "delta") == pytest.approx(-0.25)


def test_exact_bound_is_smallest_001_grid_margin_that_rejects():  # (a)
    from bench.stats import exact_paired_loss
    for n, b, c in ((40, 0, 0), (42, 2, 1), (48, 3, 3)):
        bound = _field(exact_paired_loss(b, c, n), "bound")
        assert bound == pytest.approx(round(bound, 3), abs=1e-9), "bound lies on the 0.001 grid"
        at = exact_paired_loss(b, c, n, margin=bound)
        assert _field(at, "reject"), (n, b, c, bound)
        if bound >= 0.001:
            below = exact_paired_loss(b, c, n, margin=round(bound - 0.001, 3))
            assert not _field(below, "reject"), (n, b, c, bound)


def test_exact_bound_monotone_in_b_at_fixed_c():  # (a) acceptance 4
    from bench.stats import exact_paired_loss
    for n, c in ((42, 0), (42, 2)):
        bounds = [_field(exact_paired_loss(b, c, n), "bound") for b in range(0, 8)]
        assert bounds == sorted(bounds), (n, c, bounds)


def test_exact_pvalue_monotone_in_b_at_fixed_c():  # (a)
    from bench.stats import exact_paired_loss
    ps = [_field(exact_paired_loss(b, 1, 30), "pvalue") for b in range(0, 6)]
    assert all(x <= y + 1e-12 for x, y in zip(ps, ps[1:])), ps


# ----------------------------------------------------------------------------- rejection region / size
def _region(n):
    from bench.m76_rule import a5_rejection_region
    return {tuple(k) for k in a5_rejection_region(n)}


def test_region_contains_origin_and_is_monotone():  # (a)
    for n in (42, 60):
        reg = _region(n)
        assert (0, 0) in reg
        for (b, c) in reg:
            assert 0 <= b and 0 <= c and b + c <= n
            if b > 0:
                assert (b - 1, c) in reg, (n, b, c)  # fewer N16-only passes is stronger evidence
            if b + c + 1 <= n:
                assert (b, c + 1) in reg, (n, b, c)  # more X-only passes is stronger evidence


def test_region_agrees_with_exact_paired_loss_on_samples():  # (a)
    from bench.stats import exact_paired_loss
    n = 42
    reg = _region(n)
    for b, c in ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (2, 3), (5, 1), (6, 4)):
        assert ((b, c) in reg) == bool(_field(exact_paired_loss(b, c, n), "reject")), (b, c)


def test_region_size_at_most_alpha_for_every_a5_n():  # (a) acceptance 4 — exact size, own trinomial computation
    top = (1 - MARGIN) / 2
    grid = [top * k / 90 for k in range(91)]
    for n in range(42, 121, 6):
        reg = {(b, c) for (b, c) in _region(n) if (c - b) / n >= -0.05 - 1e-12}
        worst = 0.0
        for q in grid:
            size = sum(_pmf(n, b, c, q + MARGIN, q) for b, c in reg)
            worst = max(worst, size)
        assert worst <= ALPHA + 1e-9, (n, worst)


def test_region_nonempty_beyond_origin_at_larger_n():  # (a) power sanity: more evidence than just zero discordance
    assert len(_region(120)) > 10


# ----------------------------------------------------------------------------- verdict_a5
def _v5(b, c, n):
    from bench.m76_rule import verdict_a5
    res = verdict_a5(b, c, n)
    if isinstance(res, str):
        return res, None
    if isinstance(res, dict):
        return res.get("verdict"), res.get("bound")
    if hasattr(res, "verdict"):
        return res.verdict, getattr(res, "bound", None)
    return res[0], res[1] if len(res) > 1 else None


def _name(v):
    v = str(v).upper()
    for k in ("UNDECIDED", "PASS", "LOSS"):
        if v.startswith(k):
            return k
    return v


def test_verdict_a5_zero_discordance_passes():  # (b) uses spec: PASS iff delta >= -0.05 and reject
    v, bound = _v5(0, 0, 60)
    assert _name(v) == "PASS"
    assert bound is not None and bound <= 0.10 + 1e-9


def test_verdict_a5_clear_loss_is_loss():  # (a)
    v, _ = _v5(12, 0, 60)
    assert _name(v) == "LOSS"
    assert _bin_two_sided(12, 0) <= 0.05


def test_verdict_a5_small_loss_with_weak_evidence_is_undecided():  # (a) delta < -0.05, binomial 5:1 is p = 0.219
    assert _bin_two_sided(5, 1) > 0.05
    v, _ = _v5(5, 1, 60)
    assert _name(v) == "UNDECIDED"


def test_verdict_a5_point_above_floor_but_not_rejected_is_undecided():  # (b)
    from bench.stats import exact_paired_loss
    n = 42
    found = None
    for b in range(0, 4):
        for c in range(0, 4):
            if (c - b) / n >= -0.05 and not _field(exact_paired_loss(b, c, n), "reject"):
                found = (b, c)
                break
        if found:
            break
    assert found is not None, "expected some small-discordance cell at n=42 that is not rejected"
    v, _ = _v5(*found, n)
    assert _name(v) == "UNDECIDED"


def test_verdict_a5_pass_iff_floor_and_reject_over_a_sweep():  # (b)
    from bench.stats import exact_paired_loss
    n = 42
    for b, c in ((0, 0), (1, 0), (2, 0), (3, 0), (1, 1), (4, 2), (2, 3)):
        r = exact_paired_loss(b, c, n)
        want_pass = (c - b) / n >= -0.05 and bool(_field(r, "reject"))
        v, _ = _v5(b, c, n)
        assert (_name(v) == "PASS") == want_pass, (b, c)
