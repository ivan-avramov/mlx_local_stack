"""M76 B7 (spec v1.1) — `bench.m76_rule`: `verdict`, `session_interaction`, `axis_plan`.

Classes: (a) fixed by the specification text; (b) fixed by an independent reference written here; (c) the specification
leaves the detail open (return shapes of `verdict` / `session_interaction` / `axis_plan` are not specified — these tests
read them through tolerant helpers and say so).
"""
import random

import pytest


def _verdict(delta, lo, hi, **kw):
    from bench.m76_rule import verdict
    res = verdict(delta, lo, hi, **kw)
    return res


def _name(res):
    if isinstance(res, dict):
        res = res.get("verdict", res)
    elif isinstance(res, (tuple, list)):
        res = res[0]
    elif hasattr(res, "verdict"):
        res = res.verdict
    s = str(getattr(res, "value", res)).upper()
    for k in ("UNDECIDED", "PASS", "LOSS"):
        if s.startswith(k):
            return k
    return s


def _annotated(res):
    """AMENDED (delivery 3): read the annotation from an `.annotation` attribute or an `annotation` / `label` mapping
    key first (the shape the candidate uses: a str subclass carrying attributes, which `repr` hides); fall back to the
    repr for a plain tuple/dict/str shape."""
    for nm in ("annotation",):
        val = res.get(nm) if isinstance(res, dict) else getattr(res, nm, None)
        if val:
            return "loss_shown_within_tolerance" in str(val).lower().replace(" ", "_")
    if isinstance(res, (tuple, list)) and len(res) > 1:
        return "loss_shown_within_tolerance" in repr(res[1:]).lower().replace(" ", "_")
    return "loss_shown_within_tolerance" in repr(res).lower().replace(" ", "_")


# ----------------------------------------------------------------------------- verdict boundaries
def test_verdict_pass_plain_no_annotation():  # (a)
    r = _verdict(0.0, -0.05, 0.05)
    assert _name(r) == "PASS" and not _annotated(r)


def test_verdict_spec_example_minus3_interval_m4_m2_is_pass_annotated():  # (a) named in acceptance 1
    r = _verdict(-0.03, -0.04, -0.02)
    assert _name(r) == "PASS" and _annotated(r)


def test_verdict_point_exactly_at_floor_passes():  # (a) point >= floor
    assert _name(_verdict(-0.05, -0.08, 0.02)) == "PASS"


def test_verdict_point_just_below_floor_is_not_pass():  # (a)
    assert _name(_verdict(-0.0501, -0.08, 0.02)) == "UNDECIDED"      # interval includes 0 -> not LOSS
    assert _name(_verdict(-0.0501, -0.08, -0.02)) == "LOSS"          # excludes 0, N16 better, point < floor


def test_verdict_loss_bound_exactly_at_margin_passes():  # (a) -lo <= 0.10
    assert _name(_verdict(-0.02, -0.10, 0.05)) == "PASS"


def test_verdict_loss_bound_just_over_margin_is_undecided():  # (a)
    assert _name(_verdict(-0.02, -0.1001, 0.05)) == "UNDECIDED"


def test_verdict_hi_exactly_zero_is_not_excluded():  # (a) "hi < 0" is strict
    r = _verdict(0.0, -0.05, 0.0)
    assert _name(r) == "PASS" and not _annotated(r)
    assert _name(_verdict(-0.07, -0.12, 0.0)) == "UNDECIDED"


def test_verdict_hi_just_below_zero_with_point_above_floor_is_pass_annotated():  # (a)
    r = _verdict(-0.01, -0.03, -1e-9)
    assert _name(r) == "PASS" and _annotated(r)


def test_verdict_order_pass_before_loss():  # (a) mutually exclusive, in that order
    # point below floor, excludes 0, loss bound <= margin: the point floor blocks PASS -> LOSS
    assert _name(_verdict(-0.07, -0.09, -0.04)) == "LOSS"
    # point above floor but loss bound beyond margin and excludes 0: not PASS, not LOSS -> UNDECIDED
    assert _name(_verdict(-0.04, -0.12, -0.01)) == "UNDECIDED"


def test_verdict_loss_and_undecided_with_wide_interval():  # (a)
    assert _name(_verdict(-0.20, -0.30, -0.10)) == "LOSS"
    assert _name(_verdict(-0.20, -0.40, 0.05)) == "UNDECIDED"
    assert _name(_verdict(0.20, 0.10, 0.30)) == "PASS"        # X better: loss bound negative, plain PASS
    assert not _annotated(_verdict(0.20, 0.10, 0.30))


def test_verdict_custom_floor_and_margin():  # (a)
    assert _name(_verdict(-0.03, -0.06, 0.01, point_floor=-0.02)) == "UNDECIDED"
    assert _name(_verdict(-0.03, -0.06, 0.01, point_floor=-0.05)) == "PASS"
    assert _name(_verdict(-0.01, -0.06, 0.01, loss_margin=0.05)) == "UNDECIDED"
    assert _name(_verdict(-0.01, -0.06, 0.01, loss_margin=0.06)) == "PASS"


def test_verdict_mutually_exclusive_over_a_grid():  # (b) reference restated from the spec
    pts = [x / 100 for x in range(-20, 11, 1)]
    for d in pts:
        for lo in (d - 0.08, d - 0.04, d - 0.01, d - 0.12):
            for hi in (d + 0.01, d + 0.06, -0.001 if d < 0 else d + 0.02):
                if not lo <= d <= hi:
                    continue
                want_pass = d >= -0.05 and -lo <= 0.10 + 1e-12
                want_loss = (not want_pass) and hi < 0 and d < -0.05
                want = "PASS" if want_pass else ("LOSS" if want_loss else "UNDECIDED")
                got = _name(_verdict(d, lo, hi))
                # skip float-knife-edge cells (-lo == 0.10 within rounding)
                if abs(-lo - 0.10) < 1e-9 or abs(d + 0.05) < 1e-9:
                    continue
                assert got == want, (d, lo, hi, got, want)


# ----------------------------------------------------------------------------- session_interaction (P26)
def _interaction(a, b, **kw):
    from bench.m76_rule import session_interaction
    res = session_interaction(a, b, **kw)
    if isinstance(res, dict):
        p = next(res[k] for k in ("p", "pvalue", "p_value") if k in res)
        flag = res.get("flag")
    else:
        p = next(getattr(res, k) for k in ("p", "pvalue", "p_value") if hasattr(res, k))
        flag = getattr(res, "flag", None)
    return p, flag


def test_interaction_identical_sessions_p_is_one():  # (a) acceptance 7
    rng = random.Random(1)
    a, b = {}, {}
    for i in range(30):
        x, y = int(rng.random() < 0.7), int(rng.random() < 0.6)
        a[i], b[i] = {"s1": x, "s2": x, "s3": x}, {"s1": y, "s2": y, "s3": y}
    p, flag = _interaction(a, b, iters=499, seed=426)
    assert p == pytest.approx(1.0)
    assert not flag


def test_interaction_strong_opposite_sessions_flags():  # (a)
    a = {i: {"s1": 1, "s2": 0} for i in range(30)}
    b = {i: {"s1": 0, "s2": 1} for i in range(30)}          # d = +1 on s1, -1 on s2 for every item
    p, flag = _interaction(a, b, iters=999, seed=426)
    assert p == pytest.approx(1 / 1000)                       # (1 + #{perm >= obs}) / (1 + iters), nothing else ties
    assert flag


def test_interaction_p_formula_resolution_and_determinism():  # (a)
    a = {i: {"s1": int(i % 3 == 0), "s2": int(i % 5 == 0)} for i in range(40)}
    b = {i: {"s1": 0, "s2": 0} for i in range(40)}
    p1, f1 = _interaction(a, b, iters=199, seed=426)
    p2, f2 = _interaction(a, b, iters=199, seed=426)
    assert (p1, f1) == (p2, f2)
    assert (p1 * 200) == pytest.approx(round(p1 * 200)), "p is (1 + k) / (1 + iters)"
    assert 1 / 200 <= p1 <= 1.0
    assert bool(f1) == (p1 < 0.05)


def test_interaction_null_firing_rate_within_mc_bounds():  # (b) reduced replication: 150 null datasets, tolerant bound
    """Sessions exchangeable (session SD 0, loss 0): firing rate must be <= 0.05 up to Monte Carlo error.
    Bound used: 0.05 + 3 * sqrt(0.05 * 0.95 / 150) = 0.103 — tolerant on purpose (reduced replications)."""
    rng = random.Random(77)
    reps, fired = 150, 0
    for r in range(reps):
        a, b = {}, {}
        for i in range(30):
            p = rng.betavariate(2, 2)
            a[i] = {s: int(rng.random() < p) for s in ("s1", "s2", "s3")}
            b[i] = {s: int(rng.random() < p) for s in ("s1", "s2", "s3")}
        _, flag = _interaction(a, b, iters=199, seed=426 + r)
        fired += bool(flag)
    assert fired / reps <= 0.103, fired / reps


def test_interaction_uses_only_within_item_permutation_of_session_labels():  # (a) item-level effects are not interaction
    """Items differ wildly in difficulty and in the arm effect, but the effect is the same on every session:
    exchangeable within item -> p = 1, no flag."""
    a, b = {}, {}
    for i in range(30):
        base = i % 2
        a[i] = {"s1": base, "s2": base}
        b[i] = {"s1": 0, "s2": 0}
    p, flag = _interaction(a, b, iters=299, seed=426)
    assert p == pytest.approx(1.0) and not flag


# ----------------------------------------------------------------------------- axis_plan
def _numbers(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _numbers(v, out)
    elif hasattr(obj, "__dict__"):
        _numbers(vars(obj), out)
    return out


def _has(nums, x, rel=1e-6):
    return any(abs(v - x) <= rel * max(1.0, abs(x)) for v in nums)


def test_axis_plan_a1_two_looks_100_300_with_obf_alphas():  # (c) shape unspecified; reads numbers anywhere in the plan
    from bench.m76_rule import axis_plan
    from bench.stats import obf_looks
    plan = axis_plan("A1")
    nums = _numbers(plan)
    assert _has(nums, 100) and _has(nums, 300)
    a1, a2 = obf_looks([1 / 3, 1.0], 0.025)
    assert _has(nums, a1, 1e-4) and _has(nums, a2, 1e-4)


def test_axis_plan_a5_and_a8_single_look_total_alpha_present():  # (c)
    from bench.m76_rule import axis_plan
    for ax in ("A5", "A8"):
        plan = axis_plan(ax)
        assert plan is not None
        assert _has(_numbers(plan), 0.025, 1e-9) or _has(_numbers(plan), 0.05, 1e-9), ax


def test_axis_plan_a7_exists_and_unknown_axis_refused():  # (c)
    from bench.m76_rule import axis_plan
    assert axis_plan("A7") is not None
    with pytest.raises((ValueError, KeyError)):
        axis_plan("A99")
