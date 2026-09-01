"""Tests for bench.stats — the statistics core every quality axis reports through.

These tests are written against the FAILURE MODES, because every one of them has already
produced a wrong campaign claim at least once:

* a Wilson interval without the boundary clamp reports lo=-1e-17 / hi=1.0000000000000002,
  which then prints as "-0.000" and makes a reader distrust the whole table;
* a pass@1 that POOLS N*k trials silently reweights items by how many samples survived an
  interrupted resume (test_pass_at_1_averages_items_not_trials);
* a "cluster" bootstrap that resamples items but NOT the k draws inside them is just an item
  bootstrap wearing a hat — it reports a zero-width CI for a single item and understates every
  k>1 interval (test_bootstrap_resamples_draws_not_only_items);
* an unpaired delta over two differently-filtered item sets is the exact defect paired_delta
  exists to replace (test_paired_delta_rejects_mismatched_items).

Numbers asserted here are either closed-form (Wilson, MDE) or empirically stable across seeds
and iteration counts (checked at iters=2000/5000/10000 x seeds 0,1,2,7,42 before being frozen).
"""
import math

import pytest

import bench.stats as S


# ----------------------------------------------------------------------------------- wilson
def test_wilson_known_interval():
    lo, hi = S.wilson(8, 10)
    assert round(lo, 3) == 0.490
    assert round(hi, 3) == 0.943


def test_wilson_clamps_at_zero_boundary():
    # The closed form floats to ~-2.8e-17 here. Unclamped this prints as a negative pass rate.
    lo, hi = S.wilson(0, 5)
    assert lo == 0.0
    assert hi < 1.0
    assert hi > 0.0


def test_wilson_clamps_at_one_boundary():
    lo, hi = S.wilson(5, 5)
    assert hi == 1.0
    assert 0.0 < lo < 1.0


def test_wilson_zero_n_is_none_not_zero_division():
    assert S.wilson(0, 0) == (None, None)


def test_wilson_widens_as_n_shrinks():
    # 8/10 and 80/100 share a point estimate; only n moves. The interval must shrink with n.
    w_small = S.wilson(8, 10)
    w_big = S.wilson(80, 100)
    assert (w_small[1] - w_small[0]) > (w_big[1] - w_big[0])


def test_wilson_brackets_the_point_estimate():
    lo, hi = S.wilson(7, 20)
    assert lo < 7 / 20 < hi


def test_wilson_z_is_a_parameter():
    # A 99% interval (z=2.576) must be strictly wider than the 95% default.
    lo95, hi95 = S.wilson(8, 20)
    lo99, hi99 = S.wilson(8, 20, z=2.576)
    assert lo99 < lo95 and hi99 > hi95


def test_wilson_rejects_k_out_of_range():
    with pytest.raises(ValueError):
        S.wilson(6, 5)
    with pytest.raises(ValueError):
        S.wilson(-1, 5)


# --------------------------------------------------------------------------------- pass_at_1
def test_pass_at_1_mean_of_item_means():
    assert S.pass_at_1({"i1": [1, 1, 0], "i2": [0, 0, 0]}) == pytest.approx(1 / 3)


def test_pass_at_1_averages_items_not_trials():
    # ITEMS are the unit of analysis. Pooling trials would give 4/5 = 0.8 and would let one
    # item with a surviving resume outvote an item with a single sample.
    assert S.pass_at_1({"i1": [1, 1, 1, 1], "i2": [0]}) == pytest.approx(0.5)


def test_pass_at_1_accepts_graded_scores():
    assert S.pass_at_1({"a": [0.5, 1.0], "b": [0.0]}) == pytest.approx(0.375)


def test_pass_at_1_empty_is_none():
    assert S.pass_at_1({}) is None


def test_pass_at_1_skips_items_with_no_draws():
    # An interrupted generate/resume normally leaves items with zero rows. Those are absent
    # data, not zeros — scoring them 0 would fabricate failures.
    assert S.pass_at_1({"a": [], "b": [1, 1]}) == pytest.approx(1.0)


def test_pass_at_1_all_items_empty_is_none():
    assert S.pass_at_1({"a": [], "b": []}) is None


# --------------------------------------------------------------------------- cluster_bootstrap
K1_15 = {f"i{i}": [1.0 if i < 5 else 0.0] for i in range(15)}   # 5/15 successes, k=1


def test_bootstrap_point_equals_pass_at_1():
    per_item = {"a": [1, 1, 0], "b": [0, 1, 1], "c": [0, 0, 0]}
    out = S.cluster_bootstrap(per_item, iters=500, seed=0)
    assert out["point"] == pytest.approx(S.pass_at_1(per_item))
    assert out["n_items"] == 3
    assert out["iters"] == 500


def test_bootstrap_k1_brackets_wilson():
    # k=1 => resampling a 1-draw item is the identity, so this reduces to a plain item
    # bootstrap and must land near the Wilson interval for 5/15. Agreement is ~2pp HERE
    # because n=15 puts the bootstrap on a coarse 1/15 grid; at other splits the same
    # comparison is off by up to ~7pp (see test_bootstrap_k1_is_coarse_at_n15). Do not read
    # this as "bootstrap == Wilson"; it is a sanity check that the machinery is calibrated.
    out = S.cluster_bootstrap(K1_15, iters=4000, seed=0)
    w_lo, w_hi = S.wilson(5, 15)
    assert out["lo"] == pytest.approx(w_lo, abs=0.02)
    assert out["hi"] == pytest.approx(w_hi, abs=0.02)


def test_bootstrap_k1_is_coarse_at_n15():
    # Same machinery, a split where the 1/15 grid bites. Asserted so nobody "tightens" the
    # tolerance above and believes the bootstrap is exact at N=15.
    per_item = {f"i{i}": [1.0 if i < 12 else 0.0] for i in range(15)}
    out = S.cluster_bootstrap(per_item, iters=4000, seed=0)
    w_lo, w_hi = S.wilson(12, 15)
    assert max(abs(out["lo"] - w_lo), abs(out["hi"] - w_hi)) > 0.02


def test_bootstrap_resamples_draws_not_only_items():
    # THE clustering test. One item, k=8 alternating draws. An item-only bootstrap has nothing
    # to resample and returns a zero-width CI; a two-stage bootstrap must show draw variance.
    out = S.cluster_bootstrap({"i1": [1, 0, 1, 0, 1, 0, 1, 0]}, iters=2000, seed=0)
    assert out["point"] == pytest.approx(0.5)
    assert out["n_items"] == 1
    assert out["hi"] > out["lo"]
    assert out["lo"] < 0.5 < out["hi"]


def test_bootstrap_identical_items_still_shows_draw_variance():
    # Items identical to each other but NOT constant within: item resampling alone would give
    # every replicate exactly 0.5.
    out = S.cluster_bootstrap({"a": [1, 0], "b": [1, 0], "c": [1, 0]}, iters=2000, seed=0)
    assert out["hi"] > out["lo"]


def test_bootstrap_zero_width_when_nothing_varies():
    out = S.cluster_bootstrap({"a": [1, 1], "b": [1, 1]}, iters=200, seed=0)
    assert out["point"] == 1.0 and out["lo"] == 1.0 and out["hi"] == 1.0


def test_bootstrap_is_deterministic_for_a_seed():
    per_item = {"a": [1, 0, 1], "b": [0, 0, 1], "c": [1, 1, 1]}
    first = S.cluster_bootstrap(per_item, iters=300, seed=7)
    second = S.cluster_bootstrap(per_item, iters=300, seed=7)
    assert first == second
    # ...and the seed is actually WIRED IN (a hardcoded RNG would pass the equality above).
    # Checked over several seeds because any two percentile endpoints can coincide on the
    # coarse replicate grid a small item set produces.
    wide = {f"i{i}": [1, 0, 1] if i % 2 else [0, 0, 1] for i in range(25)}
    spread = {S.cluster_bootstrap(wide, iters=200, seed=s)["hi"] for s in range(6)}
    assert len(spread) > 1


def test_bootstrap_unequal_k_per_item():
    per_item = {"a": [1, 1], "b": [0], "c": [1, 0, 1, 1]}
    out = S.cluster_bootstrap(per_item, iters=500, seed=0)
    assert out["point"] == pytest.approx((1.0 + 0.0 + 0.75) / 3)
    assert out["n_items"] == 3
    assert out["lo"] <= out["point"] <= out["hi"]


def test_bootstrap_empty_is_none():
    out = S.cluster_bootstrap({}, iters=100, seed=0)
    assert out["point"] is None and out["lo"] is None and out["hi"] is None
    assert out["n_items"] == 0


def test_bootstrap_skips_empty_items():
    out = S.cluster_bootstrap({"a": [], "b": [1, 1], "c": [0, 0]}, iters=200, seed=0)
    assert out["n_items"] == 2
    assert out["point"] == pytest.approx(0.5)


def test_bootstrap_custom_statistic_gets_list_of_draw_lists():
    seen = []

    def worst_item(items):
        seen.append(items)
        return min(sum(d) / len(d) for d in items)

    out = S.cluster_bootstrap({"a": [1, 1], "b": [0, 0]}, iters=50, seed=0,
                              statistic=worst_item)
    assert out["point"] == 0.0
    assert all(isinstance(rep, list) and isinstance(rep[0], list) for rep in seen)
    assert all(len(rep) == 2 for rep in seen)      # items resampled to the same count


def test_bootstrap_more_items_narrows_the_ci():
    small = S.cluster_bootstrap({f"i{i}": [1.0 if i % 2 else 0.0] for i in range(10)},
                                iters=3000, seed=0)
    big = S.cluster_bootstrap({f"i{i}": [1.0 if i % 2 else 0.0] for i in range(100)},
                              iters=3000, seed=0)
    assert (big["hi"] - big["lo"]) < (small["hi"] - small["lo"])


# ------------------------------------------------------------- strata (M12, pooling-for-power)
def test_bootstrap_strata_none_is_byte_identical_to_pre_strata_behaviour():
    """The regression pin: adding the `strata` parameter must not perturb the RNG sequence (or
    any other behaviour) of an unstrat call — every existing caller (grade.py, run_m1_report.py)
    passes no `strata` and must see the SAME numbers as before this parameter existed.

    Pinned against LITERAL output captured from the PRE-change function (commit 5af51dc^,
    `git show 5af51dc^:benchmark/bench/stats.py`, offline in /tmp, before `strata` existed at
    all) rather than against `strata=None` on the CURRENT function: comparing the current
    function to itself with the kwarg merely omitted is a tautology that survives any mutation
    of the `strata is None` branch, since both calls run the exact same code path.

    A HOMOGENEOUS per-item fixture (every item carrying the identical draw list) is a bad
    mutation-catcher here even though it looks like a normal fixture: item-level (stage 1)
    resampling cannot change the composition when every item's content is the same, so a
    percentile CI computed over 1500 replicates can — and, checked empirically, DOES — land on
    the exact same discrete `lo`/`hi` even when the RNG stream feeding stage 1 is perturbed.
    This fixture is deliberately HETEROGENEOUS (each item's 3 draws differ by an id-derived
    pattern) so a perturbed RNG stream provably moves `hi` (checked against a one-line mutation
    that burns one extra `rng.random()` call in the `strata is None` branch before this pin was
    written — see the M12 fix-round commit for the burn/revert transcript)."""
    per_item = {f"i{i}": [1 if (i * 7 + j) % 5 < 3 else 0 for j in range(3)] for i in range(23)}
    out = S.cluster_bootstrap(per_item, iters=2000, seed=3)
    # captured via: git show 5af51dc^:benchmark/bench/stats.py -> cluster_bootstrap(per_item,
    # iters=2000, seed=3), the function as it existed the commit before `strata` was added.
    assert out == {"point": 0.6086956521739131, "lo": 0.46376811594202894,
                   "hi": 0.753623188405797, "iters": 2000, "n_items": 23}


def test_bootstrap_strata_preserves_each_stratum_n_on_every_draw():
    """Stratified stage-1 resampling must draw exactly n_bench1 positions from bench1's items
    and n_bench2 from bench2's on EVERY bootstrap replicate — never mixing counts across strata,
    which is what keeps a pooled bench-mix fixed instead of a lucky draw over-weighting one
    bench. Checked by monkeypatching Random.randrange to record every stratum-relative index."""
    per_item = {("bench1", f"i{i}"): [1, 0] for i in range(4)}
    per_item.update({("bench2", f"i{i}"): [1, 0] for i in range(7)})
    strata = {k: k[0] for k in per_item}

    import random
    seen_group_sizes = []
    orig = random.Random.randrange

    def spy(self, n):
        seen_group_sizes.append(n)
        return orig(self, n)

    import unittest.mock as mock
    with mock.patch.object(random.Random, "randrange", spy):
        S.cluster_bootstrap(per_item, iters=5, seed=0, strata=strata)
    # For each of the 5 iterations x 2 strata, the FIRST randrange call for that stratum's
    # block must be against the stratum's own size (4 or 7), never the pooled total (11).
    stratum_sizes = {4, 7}
    first_calls_per_stratum_block = [n for n in seen_group_sizes if n in stratum_sizes]
    assert 11 not in seen_group_sizes
    assert set(first_calls_per_stratum_block) == stratum_sizes


def test_bootstrap_strata_reproduces_correct_stratum_ns_via_resampled_output():
    """A statistic callable that just counts how many resampled items came from each stratum
    proves the n-per-stratum invariant end to end, not just via an RNG spy."""
    per_item = {("bench1", f"i{i}"): [1] for i in range(3)}
    per_item.update({("bench2", f"i{i}"): [0] for i in range(9)})
    strata = {k: k[0] for k in per_item}

    def count_bench1_fraction(resampled):
        # every resampled item's draws are [1] (bench1) or [0] (bench2); the fraction of 1s IS
        # the fraction drawn from bench1 -- and it must equal 3/12 on every replicate when
        # strata are respected (never varying with a lucky pooled draw).
        return sum(d[0] for d in resampled) / len(resampled)

    out = S.cluster_bootstrap(per_item, iters=50, seed=1, strata=strata,
                              statistic=count_bench1_fraction)
    # point (observed, unresampled) must be exactly 3/12
    assert out["point"] == pytest.approx(3 / 12)
    # lo == hi == 3/12: EVERY replicate draws exactly 3 bench1 + 9 bench2 items, so the
    # bench1 fraction of the resampled set cannot move at all.
    assert out["lo"] == pytest.approx(3 / 12)
    assert out["hi"] == pytest.approx(3 / 12)


# ------------------------------------------------------------------------------- reliability
REL_K3 = {"a": [1, 1, 1], "b": [1, 1, 0], "c": [0, 0, 0]}


def test_reliability_histogram_is_the_sufficient_statistic():
    out = S.reliability(REL_K3)
    assert out["k"] == 3
    assert out["histogram"] == {3: 1, 2: 1, 0: 1}


def test_reliability_u_stats_are_unbiased_subset_probabilities():
    out = S.reliability(REL_K3)
    # u2 = mean over items of C(c,2)/C(3,2): 3/3, 1/3, 0/3
    assert out["u_stats"][2] == pytest.approx((1.0 + 1 / 3 + 0.0) / 3)
    # u3 = mean of C(c,3)/C(3,3): 1, 0, 0
    assert out["u_stats"][3] == pytest.approx(1 / 3)


def test_reliability_u3_none_when_k_below_3():
    out = S.reliability({"a": [1, 1], "b": [1, 0]})
    assert out["k"] == 2
    assert out["u_stats"][2] == pytest.approx((1.0 + 0.0) / 2)
    assert out["u_stats"][3] is None


def test_reliability_all_k_is_the_extreme_order_statistic():
    assert S.reliability(REL_K3)["all_k"] == pytest.approx(1 / 3)
    assert S.reliability({"a": [1, 1, 1], "b": [1, 1, 1]})["all_k"] == 1.0


def test_reliability_all_k_is_not_comparable_across_k():
    # The documented reason all_k is display-only: a perfectly reliable-at-p item reads lower
    # as k grows, so an all_k column silently punishes the model that got more samples.
    at_k3 = S.reliability({f"i{i}": [1, 1, 1] if i < 73 else [1, 1, 0] for i in range(100)})
    at_k5 = S.reliability({f"i{i}": [1] * 5 if i < 59 else [1, 1, 1, 1, 0]
                           for i in range(100)})
    assert at_k3["all_k"] > at_k5["all_k"]
    # ...whereas u2 is on a k-independent scale and the two agree to within a few pp.
    assert at_k3["u_stats"][2] == pytest.approx(at_k5["u_stats"][2], abs=0.06)


def test_reliability_ragged_k_reports_none_not_a_guess():
    out = S.reliability({"a": [1, 1, 1], "b": [1, 0]})
    assert out["k"] is None
    assert out["u_stats"] == {2: None, 3: None}
    # histogram and all_k still work: both are defined per item.
    assert out["histogram"] == {3: 1, 1: 1}
    assert out["all_k"] == pytest.approx(0.5)


def test_reliability_rejects_non_binary():
    with pytest.raises(ValueError):
        S.reliability({"a": [0.5, 1.0]})


def test_reliability_empty_is_all_none():
    out = S.reliability({})
    assert out["k"] is None and out["all_k"] is None
    assert out["histogram"] == {}
    assert out["u_stats"] == {2: None, 3: None}


def test_reliability_skips_empty_items():
    out = S.reliability({"a": [], "b": [1, 1], "c": [1, 0]})
    assert out["k"] == 2
    assert out["histogram"] == {2: 1, 1: 1}


# ------------------------------------------------------------------------------ paired_delta
def test_paired_delta_detects_a_clear_win():
    a = {f"i{i}": [1] for i in range(20)}
    b = {f"i{i}": [0] for i in range(20)}
    out = S.paired_delta(a, b, iters=1000, seed=0)
    assert out["delta"] == pytest.approx(1.0)
    assert out["verdict"] == "a_better"
    assert out["n_items"] == 20


def test_paired_delta_sign_names_the_winner():
    a = {f"i{i}": [0] for i in range(20)}
    b = {f"i{i}": [1] for i in range(20)}
    out = S.paired_delta(a, b, iters=1000, seed=0)
    assert out["delta"] == pytest.approx(-1.0)
    assert out["verdict"] == "b_better"


def test_paired_delta_identical_runs_are_equivalent():
    # k=1 so there is no within-item draw noise to resample: every per-item difference is
    # exactly 0, item resampling cannot manufacture a difference, and the CI is [0,0].
    a = {f"i{i}": [1 if i < 14 else 0] for i in range(20)}
    out = S.paired_delta(a, dict(a), iters=1000, seed=0, margin=0.05)
    assert out["delta"] == pytest.approx(0.0)
    assert out["lo"] == 0.0 and out["hi"] == 0.0
    assert out["verdict"] == "equivalent"


def test_paired_delta_draws_are_resampled_independently_per_model():
    # Same data on both sides but k=2 WITH within-item variation. Model a's j-th sample and
    # model b's j-th sample are independent runs, not a matched pair, so the draw stage must
    # resample them separately — which leaves real noise here. Sharing draw indices would
    # cancel it and print a zero-width CI for two runs that only look identical.
    a = {f"i{i}": [1, 0] for i in range(15)}
    out = S.paired_delta(a, dict(a), iters=2000, seed=0)
    assert out["delta"] == pytest.approx(0.0)
    assert out["hi"] > out["lo"]


def test_paired_delta_small_n_is_inconclusive_not_equivalent():
    # 4/7 vs 3/7 with disagreements in BOTH directions. The CI covers 0 AND spills past the
    # margin: we have learned nothing. It must NOT come back "equivalent" — failing to reject
    # is not evidence of equivalence.
    a = {f"i{i}": [1 if i in (0, 1, 2, 3) else 0] for i in range(7)}
    b = {f"i{i}": [1 if i in (0, 1, 4) else 0] for i in range(7)}
    out = S.paired_delta(a, b, iters=2000, seed=0, margin=0.05)
    assert out["delta"] == pytest.approx(1 / 7)
    assert out["lo"] < 0 < out["hi"]
    assert out["verdict"] == "inconclusive"


def test_paired_delta_carries_the_axis_mde():
    a = {f"i{i}": [1 if i % 2 else 0] for i in range(15)}
    b = {f"i{i}": [1 if i % 3 else 0] for i in range(15)}
    out = S.paired_delta(a, b, iters=500, seed=0)
    assert out["mde"] == pytest.approx(S.mde(15), abs=1e-9)
    assert round(out["mde"], 3) == 0.323      # a 15-item axis cannot see anything under 32pp


def test_paired_delta_rejects_mismatched_items():
    a = {"i1": [1], "i2": [1], "i3": [0]}
    b = {"i1": [1], "i2": [0], "i4": [1]}
    with pytest.raises(ValueError) as exc:
        S.paired_delta(a, b, iters=10, seed=0)
    msg = str(exc.value)
    assert "i3" in msg and "i4" in msg          # the symmetric difference must be NAMED
    assert "i1" not in msg


def test_paired_delta_is_paired_not_two_independent_bootstraps():
    # Two models that agree on every item, at a mixed pass rate (10/15). Pairing means the same
    # resampled item ids feed both sides, so item difficulty cancels and the CI is exactly
    # [0,0]. Bootstrapping the two runs independently would give a CI of roughly +-0.3 here and
    # would make identical runs look like a coin flip.
    a = {f"i{i}": [1 if i < 10 else 0] for i in range(15)}
    b = {f"i{i}": [1 if i < 10 else 0] for i in range(15)}
    out = S.paired_delta(a, b, iters=800, seed=0)
    assert out["lo"] == out["hi"] == pytest.approx(0.0)


def test_paired_delta_is_deterministic_for_a_seed():
    a = {f"i{i}": [1, 0, 1] for i in range(10)}
    b = {f"i{i}": [0, 0, 1] for i in range(10)}
    assert (S.paired_delta(a, b, iters=400, seed=3) ==
            S.paired_delta(a, b, iters=400, seed=3))


def test_paired_delta_empty_shared_set_raises():
    with pytest.raises(ValueError):
        S.paired_delta({}, {}, iters=10, seed=0)


# ------------------------------------------------------------- strata (M12, pooling-for-power)
def test_paired_delta_strata_none_is_byte_identical_to_pre_strata_behaviour():
    """Same pin, same reason, for `paired_delta`: LITERAL output captured from the PRE-change
    function (commit 5af51dc^) via `git show 5af51dc^:benchmark/bench/stats.py`, offline in
    /tmp, before `strata` existed. `strata=None` compared against itself with the kwarg omitted
    is a tautology and survives any mutation of the `strata is None` branch."""
    a = {f"i{i}": [1, 0, 1] for i in range(12)}
    b = {f"i{i}": [0, 0, 1] for i in range(12)}
    out = S.paired_delta(a, b, iters=800, seed=2)
    # captured via: git show 5af51dc^:benchmark/bench/stats.py -> paired_delta(a, b, iters=800,
    # seed=2), the function as it existed the commit before `strata` was added.
    assert out == {"delta": 0.3333333333333333, "lo": 0.11111111111111116,
                   "hi": 0.5555555555555555, "verdict": "a_better", "n_items": 12,
                   "mde": 0.3616830682661502}


def test_paired_delta_pooled_n_and_delta_arithmetic():
    """(a) n = n1 + n2, and the pooled delta is the plain mean over the pooled item set — a
    hand-computable sanity check independent of the bootstrap."""
    a = {("bench1", f"i{i}"): [1] for i in range(5)}       # bench1: a=1.0
    a.update({("bench2", f"i{i}"): [1 if i < 6 else 0] for i in range(10)})  # bench2: a=0.6
    b = {("bench1", f"i{i}"): [0] for i in range(5)}       # bench1: b=0.0
    b.update({("bench2", f"i{i}"): [1 if i < 4 else 0] for i in range(10)})  # bench2: b=0.4
    strata = {k: k[0] for k in a}
    out = S.paired_delta(a, b, iters=500, seed=0, strata=strata)
    assert out["n_items"] == 15
    # pooled a = (5*1.0 + 10*0.6) / 15 = 11/15 ; pooled b = (5*0.0 + 10*0.4) / 15 = 4/15
    assert out["delta"] == pytest.approx(11 / 15 - 4 / 15)


def test_paired_delta_pooled_ci_excludes_zero_when_each_bench_alone_is_inconclusive():
    """(b) The whole point of pooling: the SAME small consistent effect (a correct on 8/12, b
    on 5/12, k=1 so there is no draw noise to hide behind) is inconclusive at n=12 alone in
    EITHER bench (grid-quantized lo lands on exactly 0.0), but pooling the two identical benches
    to n=24 items narrows the bootstrap enough for the CI to clear 0."""
    def one_bench(bench):
        a = {(bench, f"i{i}"): [1 if i < 8 else 0] for i in range(12)}
        b = {(bench, f"i{i}"): [1 if i < 5 else 0] for i in range(12)}
        return a, b

    a1, b1 = one_bench("bench1")
    a2, b2 = one_bench("bench2")
    a, b = {**a1, **a2}, {**b1, **b2}
    strata = {k: k[0] for k in a}

    alone1 = S.paired_delta(a1, b1, iters=3000, seed=0)
    alone2 = S.paired_delta(a2, b2, iters=3000, seed=0)
    pooled = S.paired_delta(a, b, iters=3000, seed=0, strata=strata)
    assert alone1["verdict"] == "inconclusive", alone1
    assert alone2["verdict"] == "inconclusive", alone2
    assert pooled["n_items"] == 24
    assert pooled["lo"] > 0, pooled
    assert pooled["verdict"] == "a_better", pooled


def test_paired_delta_strata_every_draw_keeps_each_stratum_n_fixed():
    """(c) With a fixed seed, every bootstrap replicate must resample exactly n1 items from
    bench1 and n2 from bench2 — checked directly on the RNG call sequence."""
    a = {("bench1", f"i{i}"): [1, 0] for i in range(4)}
    a.update({("bench2", f"i{i}"): [1, 0] for i in range(9)})
    b = {k: [0, 1] for k in a}
    strata = {k: k[0] for k in a}

    import random
    import unittest.mock as mock
    seen = []
    orig = random.Random.randrange

    def spy(self, n):
        seen.append(n)
        return orig(self, n)

    with mock.patch.object(random.Random, "randrange", spy):
        S.paired_delta(a, b, iters=6, seed=0, strata=strata)
    stratum_sizes = {4, 9}
    assert 13 not in seen, "must never resample the pooled 13 as one population"
    assert stratum_sizes <= set(seen)


# -------------------------------------------------------------------------------------- holm
def test_holm_known_example():
    # m=3: sorted 0.01,0.03,0.04 -> x3, x2, x1 = 0.03, 0.06, 0.04 -> monotone -> 0.03,0.06,0.06
    assert S.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_holm_preserves_input_order():
    assert S.holm([0.04, 0.01, 0.03]) == pytest.approx([0.06, 0.03, 0.06])


def test_holm_textbook_five():
    assert S.holm([0.005, 0.011, 0.02, 0.04, 0.13]) == pytest.approx(
        [0.025, 0.044, 0.06, 0.08, 0.13])


def test_holm_is_monotone_nondecreasing_in_rank():
    raw = [0.001, 0.049, 0.05, 0.2, 0.9]
    adj = S.holm(raw)
    ordered = [a for _, a in sorted(zip(raw, adj))]
    assert all(x <= y + 1e-12 for x, y in zip(ordered, ordered[1:]))


def test_holm_clamps_at_one():
    assert S.holm([0.5, 0.6]) == pytest.approx([1.0, 1.0])
    assert all(a <= 1.0 for a in S.holm([0.4, 0.4, 0.4, 0.4]))


def test_holm_single_and_empty():
    assert S.holm([0.03]) == pytest.approx([0.03])
    assert S.holm([]) == []


def test_holm_is_less_conservative_than_bonferroni():
    raw = [0.01, 0.02, 0.03]
    adj = S.holm(raw)
    bonf = [min(1.0, p * 3) for p in raw]
    assert adj[0] == pytest.approx(bonf[0])       # the smallest p pays the full m penalty
    assert adj[-1] < bonf[-1]                     # later steps pay less


def test_holm_rejects_out_of_range_pvalues():
    with pytest.raises(ValueError):
        S.holm([0.5, 1.5])
    with pytest.raises(ValueError):
        S.holm([-0.1])


# ---------------------------------------------------------------------------- mde and n_for
def test_mde_table():
    # delta_min = sqrt((z_a/2 + z_beta)^2 * p_d / n) = sqrt(7.849 * 0.20 / n)
    assert S.mde(15) == pytest.approx(0.323, abs=0.001)
    assert S.mde(40) == pytest.approx(0.198, abs=0.001)
    assert S.mde(100) == pytest.approx(0.125, abs=0.001)
    assert S.mde(164) == pytest.approx(0.098, abs=0.001)
    assert S.mde(378) == pytest.approx(0.064, abs=0.001)


def test_mde_scales_as_inverse_sqrt_n():
    assert S.mde(400) == pytest.approx(S.mde(100) / 2, rel=1e-9)


def test_mde_zero_n_is_infinite_not_zero_division():
    assert S.mde(0) == math.inf


def test_mde_rejects_negative_n():
    with pytest.raises(ValueError):
        S.mde(-5)


def test_n_for_table():
    # SPEC DISCREPANCY (reported, not silently "fixed"): the brief asks for round-UP AND
    # n_for(0.20)==39, which cannot both hold — the raw requirement is 39.244, and n=39 gives
    # mde(39)=0.2006 > 0.20, i.e. 39 is NOT sufficient. Round-up wins; 39 is a typo for 40.
    assert S.n_for(0.20) == 40
    assert S.mde(39) > 0.20 and S.mde(40) < 0.20
    assert S.n_for(0.15) == 70
    assert S.n_for(0.10) == 157
    assert S.n_for(0.05) == 628


def test_n_for_rounds_up_not_to_nearest():
    # 156.98 -> 157 either way; this pins the rule with a case where they differ.
    assert S.n_for(0.20) == math.ceil(7.848879 * 0.20 / 0.04)


def test_n_for_inverts_mde():
    for delta in (0.05, 0.1, 0.2, 0.35):
        n = S.n_for(delta)
        assert S.mde(n) <= delta
        assert S.mde(n - 1) > delta          # minimality: one fewer item is not enough


def test_n_for_rejects_nonpositive_delta():
    with pytest.raises(ValueError):
        S.n_for(0.0)
    with pytest.raises(ValueError):
        S.n_for(-0.2)


def test_mde_discordance_rate_matters():
    # p_d is the DISCORDANT-pair rate. Two models that disagree on half the items need a much
    # larger sample than two that disagree on 5% of them.
    assert S.mde(100, p_d=0.5) > S.mde(100, p_d=0.05)


def test_mde_supports_other_alpha_power_and_rejects_unknown():
    assert S.mde(100, power=0.90) > S.mde(100, power=0.80)
    assert S.mde(100, alpha=0.01) > S.mde(100, alpha=0.05)
    with pytest.raises(ValueError):
        S.mde(100, alpha=0.037)             # no scipy: only tabulated z-values exist
    with pytest.raises(ValueError):
        S.mde(100, power=0.85)


# --------------------------------------------------------------------------- time_to_success
def test_time_to_success_uses_means_of_both_lists():
    # p=0.5 => one expected failure per success: 100 + (0.5/0.5)*200 = 300s.
    out = S.time_to_success([100.0], [200.0], 0.5)
    assert out["expected_s"] == pytest.approx(300.0)
    assert out["successes_per_hour"] == pytest.approx(12.0)


def test_time_to_success_uses_the_mean_not_the_median():
    # THE point of the metric. Successes: median 870s (14.5 min) but a 2h tail. median/p would
    # report 1740s; the Wald expectation charges the model for its tail.
    t_success = [870.0, 870.0, 7200.0]
    out = S.time_to_success(t_success, [60.0], 0.5)
    naive_median = 870.0 / 0.5
    assert out["expected_s"] == pytest.approx(sum(t_success) / 3 + 60.0)
    assert out["expected_s"] > naive_median * 1.5


def test_time_to_success_p_one_ignores_failure_times():
    out = S.time_to_success([120.0, 180.0], [9999.0], 1.0)
    assert out["expected_s"] == pytest.approx(150.0)
    assert out["successes_per_hour"] == pytest.approx(24.0)


def test_time_to_success_p_zero_is_infinite_and_zero_rate():
    out = S.time_to_success([100.0], [200.0], 0.0)
    assert out["expected_s"] == math.inf
    assert out["successes_per_hour"] == 0.0


def test_time_to_success_punishes_the_loop_prone_model():
    fast_reliable = S.time_to_success([600.0], [600.0], 0.9)
    loop_prone = S.time_to_success([600.0], [7200.0], 0.4)
    assert loop_prone["successes_per_hour"] < fast_reliable["successes_per_hour"]


def test_time_to_success_missing_failure_observations():
    # A run with no recorded failures but p<1 (failures timed out and were dropped): charge
    # nothing rather than crash — the caller sees an optimistic bound, not a traceback.
    out = S.time_to_success([100.0], [], 0.5)
    assert out["expected_s"] == pytest.approx(100.0)


def test_time_to_success_requires_success_observations():
    with pytest.raises(ValueError):
        S.time_to_success([], [200.0], 0.5)


def test_time_to_success_rejects_p_out_of_range():
    with pytest.raises(ValueError):
        S.time_to_success([100.0], [200.0], 1.5)
    with pytest.raises(ValueError):
        S.time_to_success([100.0], [200.0], -0.1)


def test_time_to_success_rejects_negative_durations():
    with pytest.raises(ValueError):
        S.time_to_success([-1.0], [200.0], 0.5)
