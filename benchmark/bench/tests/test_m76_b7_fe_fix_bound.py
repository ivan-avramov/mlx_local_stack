"""M76 B7 (spec v1.3) — adopted findings 1 and 2: the shipped loss bound must be the simulated one (one exact-bootstrap
function), and `loss_interval` / `verdict_of` never fall back to the default-alpha bound.

Classes: (a) specification / identity; (b) independent brute-force reference written here; (c) shape or seed dependent.
New-API imports are inside the tests (baseline failures are per test).
"""
import itertools
import math
import random

import pytest


# ----------------------------------------------------------------------------- independent references
def _enum_exact_quantiles(groups, n_sessions, alpha):
    """Brute force: enumerate every item-index tuple of the within-stratum item bootstrap, build the exact distribution of
    the sum, return (lo, hi) = (F^-1(alpha), F^-1(1 - alpha)) / (n_items * n_sessions)."""
    n = sum(len(g) for g in groups)
    dist = {0: 1.0}
    for g in groups:
        k = len(g)
        part = {}
        for tup in itertools.product(range(k), repeat=k):
            s = sum(g[i] for i in tup)
            part[s] = part.get(s, 0.0) + k ** (-k)
        new = {}
        for s1, p1 in dist.items():
            for s2, p2 in part.items():
                new[s1 + s2] = new.get(s1 + s2, 0.0) + p1 * p2
        dist = new
    xs = sorted(dist)
    cum, acc = [], 0.0
    for x in xs:
        acc += dist[x]
        cum.append(acc)

    def q(level):
        for x, c in zip(xs, cum):
            if c >= level - 1e-12:
                return x
        return xs[-1]

    return q(alpha) / (n * n_sessions), q(1 - alpha) / (n * n_sessions)


def _binom_tail_ge(n, p, k):
    return sum(math.comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k, n + 1))


def _a1_rows(n, losses, gains=0, sid="s"):
    """X (a) vs N16 (b), single session: `losses` items N16-pass / X-fail, `gains` the reverse, the rest identical."""
    a, b = {}, {}
    for i in range(n):
        a[i], b[i] = {sid: 1}, {sid: 1}
    for i in range(losses):
        a[i][sid] = 0
    for i in range(losses, losses + gains):
        a[i][sid], b[i][sid] = 1, 0
    return a, b


# ----------------------------------------------------------------------------- finding 1: one bound, shipped = simulated
def test_exact_interval_values_matches_bruteforce_enumeration():  # (b)
    from bench.m76_rule import exact_interval_values
    rng = random.Random(3)
    for vals in ([0, 0, 0, -1, 0, -1], [1, 0, -1, 0, 0, 1], [0, 0, 0, 0, 0, -1], [-2, 0, 1, -1, 0, 0]):
        k = 2 if min(vals) < -1 or max(vals) > 1 else 1
        for alpha in (0.025, 0.1, 0.3):
            (r,) = exact_interval_values([vals], k, [alpha], any_discordant=any(vals))
            lo, hi = _enum_exact_quantiles([vals], k, alpha)
            assert r["lo"] == pytest.approx(lo, abs=1e-12), (vals, alpha)
            assert r["hi"] == pytest.approx(hi, abs=1e-12), (vals, alpha)
            assert r["delta"] == pytest.approx(sum(vals) / (len(vals) * k))
            assert r["loss_bound"] == pytest.approx(-r["lo"])
    assert rng is not None


def test_exact_interval_values_strata_resample_within_strata():  # (b)
    from bench.m76_rule import exact_interval_values
    groups = [[-1, 0, 0, 0], [0, 0, -1]]
    (r,) = exact_interval_values(groups, 1, [0.05], any_discordant=True)
    lo, hi = _enum_exact_quantiles(groups, 1, 0.05)
    assert r["lo"] == pytest.approx(lo, abs=1e-12) and r["hi"] == pytest.approx(hi, abs=1e-12)


def test_exact_interval_values_zero_discordance_uses_exact_bound_at_alpha():  # (a) spec §8: 1 - alpha^(1/n)
    from bench.m76_rule import exact_interval_values
    (r,) = exact_interval_values([[0] * 40], 1, [0.025], any_discordant=False)
    assert r["degenerate"] and r["exact_bound_used"]
    assert r["lo"] == pytest.approx(-(1 - 0.025 ** (1 / 40)))
    assert r["loss_bound"] == pytest.approx(1 - 0.025 ** (1 / 40))


def test_exact_interval_values_refuses_bad_input():  # (a)
    from bench.m76_rule import exact_interval_values
    with pytest.raises(ValueError):
        exact_interval_values([[]], 1, [0.025], any_discordant=False)
    with pytest.raises(ValueError):
        exact_interval_values([[0, -1]], 1, [0.6], any_discordant=True)
    with pytest.raises(ValueError):
        exact_interval_values([[0, -1]], 1, [0.025], any_discordant=False)   # nonzero values but flagged none


def test_a1_look1_resample_passes_but_exact_rule_is_undecided():  # (b)+(c) the constructed failing case, finding 1
    """100 items, 3 losses, 0 gains, at A1 look 1's one-sided alpha 1.04e-4 (two-sided 99.979 %). The independent exact
    bootstrap: the lower bound is -k/100 with k the largest count whose Binomial(100, 0.03) upper tail is >= alpha."""
    from bench.m76_rule import axis_verdict
    from bench.stats import obf_alpha
    a, b = _a1_rows(100, 3)
    alpha = obf_alpha(1 / 3, 0.025)
    k = max(j for j in range(0, 101) if _binom_tail_ge(100, 0.03, j) >= alpha - 1e-12)
    res = axis_verdict("A1", 1, a, b)
    assert res["alpha"] == pytest.approx(alpha)
    assert res["lo"] == pytest.approx(-k / 100, abs=1e-12)
    assert res["loss_bound"] == pytest.approx(k / 100, abs=1e-12)
    assert k / 100 > 0.10, "construction: the exact loss bound exceeds the 10 pp margin"
    assert str(res["verdict"]) == "UNDECIDED"
    assert res["delta"] == pytest.approx(-0.03)


def test_a1_look1_10k_resample_verdict_depends_on_the_seed_exact_does_not():  # (c) reproduction by seed scan
    """The same rows through the 10,000-resample `paired_delta` at the same alpha (two-sided 2 * alpha). Measured when
    written: over seeds 0..19 the resampled §8 verdict was PASS for 8 seeds and UNDECIDED for 12 (lower bound -0.10 or
    -0.11, and -0.12 for at least one seed, against the exact -0.11): the resampled bound at this tail is noise, and some seeds give a false PASS. The exact
    path is the same answer for every seed. (Delivery 3's first draft asserted PASS at seed 426 alone; that seed gives
    -0.1097, UNDECIDED.)"""
    from bench.m76_rule import axis_verdict, verdict
    from bench.stats import obf_alpha, paired_delta
    a, b = _a1_rows(100, 3)
    alpha = obf_alpha(1 / 3, 0.025)
    exact = axis_verdict("A1", 1, a, b)
    assert str(exact["verdict"]) == "UNDECIDED"
    verdicts = []
    for seed in range(20):
        pd = paired_delta({i: [a[i]["s"]] for i in a}, {i: [b[i]["s"]] for i in b}, iters=10000, seed=seed,
                          interval_alpha=2 * alpha)
        verdicts.append(str(verdict(pd["delta"], pd["lo"], pd["hi"])))
    assert "PASS" in verdicts, "no seed reproduced the resample false PASS"
    assert "UNDECIDED" in verdicts, "the resampled verdict should vary with the seed at this tail"
    assert exact["lo"] == axis_verdict("A1", 1, a, b)["lo"]


def test_axis_verdict_equals_exact_interval_values_and_simulator_vector():  # (a) one function, two callers
    from bench import m76_sim
    from bench.m76_rule import axis_plan, axis_verdict, exact_interval_values
    rng = random.Random(11)
    for trial in range(4):
        a, b = {}, {}
        for i in range(43):
            b[i] = {s: int(rng.random() < 0.9) for s in ("s1", "s2", "s3")}
            a[i] = {s: (0 if (b[i][s] and rng.random() < 0.1) else b[i][s]) for s in b[i]}
        res = axis_verdict("A7", 1, a, b)
        alpha = axis_plan("A7")["looks"][0]["alpha"]
        vals = [sum(a[i][s] - b[i][s] for s in b[i]) for i in sorted(a)]
        (ref,) = exact_interval_values([vals], 3, [alpha], any_discordant=any(vals))
        assert res["lo"] == pytest.approx(ref["lo"], abs=1e-12) and res["hi"] == pytest.approx(ref["hi"], abs=1e-12)
        assert res["loss_bound"] == pytest.approx(ref["loss_bound"], abs=1e-12)
        code = m76_sim.verdict_vector(vals, 43, 3, any(vals), alphas=(alpha,))
        assert code == {"PASS": "P", "LOSS": "L", "UNDECIDED": "U"}[str(res["verdict"])]


def test_axis_verdict_returns_per_session_and_interaction_for_multi_session_axes():  # (c) shape named in the docstring
    from bench.m76_rule import axis_verdict
    rng = random.Random(5)
    a, b = {}, {}
    for i in range(43):
        b[i] = {s: int(rng.random() < 0.9) for s in ("s1", "s2", "s3")}
        a[i] = dict(b[i])
    res = axis_verdict("A7", 1, a, b)
    assert set(res["per_session"]) == {"s1", "s2", "s3"}
    assert res["n_items"] == 43 and res["n_sessions"] == 3
    assert res["interaction"] is not None and res["interaction_flag"] is False
    assert res["delta"] == pytest.approx(0.0)
    # identical arms: no discordant item -> the exact zero-discordance bound at the plan's alpha, 1 - alpha^(1/43)
    from bench.m76_rule import axis_plan
    alpha = axis_plan("A7")["looks"][0]["alpha"]
    assert res["exact_bound_used"] is True
    assert res["loss_bound"] == pytest.approx(1 - alpha ** (1 / 43))


def test_axis_verdict_refuses_multi_session_a1_and_bad_look():  # (a)
    from bench.m76_rule import axis_verdict
    a = {i: {"s1": 1, "s2": 1} for i in range(100)}
    with pytest.raises(ValueError):
        axis_verdict("A1", 1, a, {i: dict(v) for i, v in a.items()})
    a1, b1 = _a1_rows(100, 0)
    with pytest.raises(ValueError):
        axis_verdict("A1", 3, a1, b1)
    with pytest.raises(ValueError):
        axis_verdict("A1", 0, a1, b1)


def test_axis_verdict_warns_when_sizes_differ_from_the_plan():  # (c) docstring: size_warnings, not an exception
    from bench.m76_rule import axis_verdict
    a, b = _a1_rows(60, 0)
    res = axis_verdict("A1", 1, a, b)
    assert res["size_warnings"], "60 items at A1 look 1 (plan: 100) must be listed for the operator"
    a, b = _a1_rows(100, 0)
    assert axis_verdict("A1", 1, a, b)["size_warnings"] == []


def test_axis_verdict_a5_goes_through_the_exact_rule():  # (b) verdict_a5 on pooled (b, c, n)
    from bench.m76_rule import axis_verdict, verdict_a5
    a, b = _a1_rows(72, 0)
    res = axis_verdict("A5", 1, a, b)
    ref = verdict_a5(0, 0, 72)
    assert str(res["verdict"]) == str(ref[0])
    assert res["loss_bound"] == pytest.approx(ref[1])
    assert res["lo"] is None and res["hi"] is None
    a, b = _a1_rows(72, 12)
    assert str(axis_verdict("A5", 1, a, b)["verdict"]) == "LOSS"


# ----------------------------------------------------------------------------- finding 2: no default-alpha bound
def _degenerate_default():
    from bench.stats import paired_delta
    a = {i: [1] for i in range(8)}
    return paired_delta(a, dict(a), iters=50, seed=1)


def test_loss_interval_default_alpha_degenerate_result_raises():  # (a) finding 2
    from bench.m76_rule import loss_interval
    res = _degenerate_default()
    assert res["degenerate"] and res["discordance_upper95"] is not None   # the 0.05 bound exists on the default result
    with pytest.raises(ValueError):
        loss_interval(res)


def test_verdict_of_default_alpha_degenerate_result_raises():  # (a) finding 2
    from bench.m76_rule import verdict_of
    with pytest.raises(ValueError):
        verdict_of(_degenerate_default())


def test_loss_interval_explicit_alpha_uses_that_alpha_never_the_005_bound():  # (a)
    from bench.m76_rule import loss_interval
    res = _degenerate_default()
    delta, lo, hi = loss_interval(res, exact_alpha=0.025)
    assert lo == pytest.approx(-(1 - 0.025 ** (1 / 8)))
    assert lo != pytest.approx(-(1 - 0.05 ** (1 / 8)))
    assert (delta, hi) == (0.0, 0.0)


def test_loss_interval_reads_alpha_from_result_metadata_and_refuses_conflict():  # (a)
    from bench.m76_rule import loss_interval
    from bench.stats import paired_delta
    a = {i: [1] for i in range(8)}
    res = paired_delta(a, dict(a), iters=50, seed=1, exact_alpha=0.025)
    assert loss_interval(res)[1] == pytest.approx(-(1 - 0.025 ** (1 / 8)))
    with pytest.raises(ValueError):
        loss_interval(res, exact_alpha=0.01)
    with pytest.raises(ValueError):
        loss_interval(res, exact_alpha=1.5)


def test_loss_interval_non_degenerate_result_still_requires_alpha():  # (c) behaviour of the candidate: raises regardless
    from bench.m76_rule import loss_interval
    from bench.stats import paired_delta
    a = {i: [i % 2] for i in range(20)}
    b = {i: [1] for i in range(20)}
    res = paired_delta(a, b, iters=200, seed=2)
    with pytest.raises(ValueError):
        loss_interval(res)
    d, lo, hi = loss_interval(res, exact_alpha=0.025)
    assert (d, lo, hi) == (res["delta"], res["lo"], res["hi"])


def test_loss_interval_session_delta_result_requires_alpha_and_uses_it():  # (a)
    from bench.m76_rule import loss_interval
    from bench.stats import paired_session_delta
    a = {i: {"s1": 1, "s2": 1} for i in range(10)}
    res = paired_session_delta(a, {i: dict(v) for i, v in a.items()}, iters=50, seed=1)
    with pytest.raises(ValueError):
        loss_interval(res)
    assert loss_interval(res, exact_alpha=0.025)[1] == pytest.approx(-(1 - 0.025 ** (1 / 10)))


# ----------------------------------------------------------------------------- finding 5: numpy integers
def test_exact_paired_loss_accepts_numpy_integers():  # (a) finding 5
    np = pytest.importorskip("numpy")
    from bench.stats import exact_paired_loss
    plain = exact_paired_loss(2, 1, 42)
    npy = exact_paired_loss(np.int64(2), np.int32(1), np.int64(42))
    assert npy["pvalue"] == pytest.approx(plain["pvalue"], abs=1e-15)
    assert npy["reject"] == plain["reject"] and npy["bound"] == plain["bound"]


def test_exact_paired_loss_still_refuses_floats_and_bools():  # (a)
    from bench.stats import exact_paired_loss
    for bad in ((1.0, 0, 40), (True, 0, 40), (0, 0, 40.0)):
        with pytest.raises(ValueError):
            exact_paired_loss(*bad)
    with pytest.raises(ValueError):
        exact_paired_loss(30, 20, 40)
