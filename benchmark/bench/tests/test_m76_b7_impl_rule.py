"""M76 B7 criteria 1 / 4 / 7: `m76_rule.verdict` boundaries, the descriptive session-disagreement listing,
`axis_plan` (calibrated, from the report), `verdict_a5` and its region / exact size, `session_interaction`."""
import hashlib
import json

import pytest

import bench.stats as S
from bench import m76_rule as R


@pytest.mark.parametrize("delta,lo,hi,want,ann", [
    (-0.03, -0.04, -0.02, "PASS", "loss_shown_within_tolerance"),   # −3 pp, [−4, −2]
    (-0.05, -0.10, 0.02, "PASS", None),                              # both boundaries exactly
    (-0.05, -0.10, -0.01, "PASS", "loss_shown_within_tolerance"),
    (0.0, -0.10, 0.10, "PASS", None),
    (0.0, -0.1000001, 0.05, "UNDECIDED", None),                      # bound just over 10 pp
    (-0.0500001, -0.08, 0.02, "UNDECIDED", None),                    # point just under the floor, CI includes 0
    (-0.0500001, -0.08, -0.01, "LOSS", None),                        # point under floor, CI excludes 0
    (-0.06, -0.09, -0.03, "LOSS", None),
    (-0.06, -0.20, 0.0, "UNDECIDED", None),                          # hi == 0 does not exclude 0
    (-0.04, -0.12, -0.01, "UNDECIDED", None),                        # point ok, loss bound too wide, hi < 0
    (0.02, -0.15, 0.20, "UNDECIDED", None),
    (0.05, 0.01, 0.09, "PASS", None),                                # X better
])
def test_verdict_boundaries(delta, lo, hi, want, ann):
    v = R.verdict(delta, lo, hi)
    assert v == want
    assert v.annotation == ann and v["annotation"] == ann and v["verdict"] == want
    assert v.loss_bound == pytest.approx(-lo)


def test_verdict_float_slack_on_computed_boundary():
    assert R.verdict(0.95 - 1.0, -0.1, 0.0) == "PASS"                # −0.05000000000000004
    assert R.verdict(0.0, 0.9 - 1.0, 0.1) == "PASS"                  # −0.09999999999999998


def test_verdict_custom_thresholds_and_mutual_exclusion():
    assert R.verdict(-0.03, -0.06, 0.01, point_floor=-0.02, loss_margin=0.10) == "UNDECIDED"
    assert R.verdict(-0.03, -0.06, -0.01, point_floor=-0.02) == "LOSS"
    for d, lo, hi in [(-0.2, -0.3, -0.1), (0.0, -0.01, 0.01), (-0.04, -0.2, 0.1)]:
        assert R.verdict(d, lo, hi) in (R.PASS, R.LOSS, R.UNDECIDED)


def test_verdict_of_uses_exact_bound_for_zero_discordance():
    a = {j: {1: 1} for j in range(40)}
    r = S.paired_session_delta(a, {j: dict(v) for j, v in a.items()}, iters=100, exact_alpha=0.025)
    v = R.verdict_of(r, exact_alpha=0.025)
    assert v == "PASS" and v.loss_bound == pytest.approx(0.0881, abs=1e-4)
    small = {j: {1: 1} for j in range(20)}
    r2 = S.paired_session_delta(small, {j: dict(v) for j, v in small.items()}, iters=100, exact_alpha=0.025)
    assert R.verdict_of(r2, exact_alpha=0.025) == "UNDECIDED"        # 1 − 0.025^(1/20) = 16.8 pp > 10 pp


def test_verdict_of_requires_alpha_never_default():
    """Finding 2: no silent default α — a default-alpha degenerate result raises."""
    a = {j: [1] for j in range(40)}
    r = S.paired_delta(a, {j: list(v) for j, v in a.items()}, iters=100)
    assert r["degenerate"] and r["discordance_upper95"] is not None and "exact_alpha" not in r
    with pytest.raises(ValueError, match="exact_alpha is required"):
        R.verdict_of(r)
    with pytest.raises(ValueError, match="exact_alpha is required"):
        R.loss_interval(r)
    rs = S.paired_session_delta({j: {1: 1} for j in a}, {j: {1: 1} for j in a}, iters=100)
    with pytest.raises(ValueError, match="exact_alpha is required"):
        R.verdict_of(rs)
    # the explicit α is used, never the 0.05 bound
    assert R.loss_interval(r, exact_alpha=0.001)[1] == pytest.approx(-(1 - 0.001 ** (1 / 40)))
    # non-default metadata is accepted; a conflicting explicit α raises
    rm = S.paired_delta(a, {j: list(v) for j, v in a.items()}, iters=100, interval_alpha=0.02, exact_alpha=0.01)
    assert R.loss_interval(rm)[1] == pytest.approx(-(1 - 0.01 ** (1 / 40)))
    with pytest.raises(ValueError, match="differs"):
        R.loss_interval(rm, exact_alpha=0.025)


# --------------------------------------------------------------------------- finding 1: the shipped bound (axis_verdict)
def _rows1(n, nb, nc):
    """Single-session X / N16 rows: items 0..nb−1 losses, the next nc gains, the rest both pass."""
    a, b = {}, {}
    for i in range(n):
        x, y = (0, 1) if i < nb else ((1, 0) if i < nb + nc else (1, 1))
        a[i], b[i] = {"s1": x}, {"s1": y}
    return a, b


def test_a1_look1_resample_passes_exact_rule_undecided():
    """The constructed A1 look-1 case: 3 losses / 0 gains in 100 items. The 10,000-resample `paired_delta` at the
    look-1 α reads lo −0.10 → PASS; the exact bootstrap (simulated and shipped) gives lo −0.11 → UNDECIDED."""
    alpha = R.axis_plan("A1")["looks"][0]["alpha"]
    a, b = _rows1(100, 3, 0)
    r = S.paired_delta({i: [a[i]["s1"]] for i in a}, {i: [b[i]["s1"]] for i in b},
                       interval_alpha=2 * alpha, exact_alpha=alpha)
    assert R.verdict_of(r) == "PASS" and r["lo"] == pytest.approx(-0.10)
    v = R.axis_verdict("A1", 1, a, b)
    assert v["alpha"] == alpha and v["verdict"] == "UNDECIDED"
    assert v["lo"] == pytest.approx(-0.11) and v["loss_bound"] == pytest.approx(0.11)
    assert v["delta"] == pytest.approx(-0.03) and v["size_warnings"] == []
    assert v["interaction"] is None and v["interaction_flag"] is False
    assert v["per_session_alpha"] == 0.025                             # v1.4: descriptive, not at the look α
    assert v["per_session"]["s1"]["lo"] == R.loss_bound(a, b, alpha=0.025)["lo"]


def test_axis_verdict_per_session_descriptive_at_0025_not_alpha_star(tmp_path):
    """v1.4: per-session results beside an agentic verdict are at one-sided 0.025 (95 % two-sided), never α*."""
    rep = {"axes": {"A7": {"calibration": {"alpha_star": 0.001, "binding_cell": None, "look1": {"keep": False}}},
                    "A8": {"calibration": {"alpha_star": 0.005, "binding_cell": None}, "alpha_star_fixed": 0.001}}}
    p = tmp_path / "report.json"
    p.write_text(json.dumps(rep))
    a = {i: {"s1": 1, "s2": 1} for i in range(80)}
    b = {i: {"s1": 1, "s2": 1} for i in range(80)}
    for i in range(4):
        a[i]["s1"] = 0
    for i in range(4, 7):
        b[i]["s2"] = 0
    v = R.axis_verdict("A8", 1, a, b, report=p)
    assert v["alpha"] == 0.001 and v["per_session_alpha"] == 0.025 == R.PER_SESSION_ALPHA
    assert v["lo"] == R.loss_bound(a, b, alpha=0.001)["lo"]
    for s in ("s1", "s2"):
        one_a, one_b = {i: {s: a[i][s]} for i in a}, {i: {s: b[i][s]} for i in b}
        at_025, at_star = R.loss_bound(one_a, one_b, alpha=0.025), R.loss_bound(one_a, one_b, alpha=0.001)
        got = v["per_session"][s]
        assert (got["delta"], got["lo"], got["hi"], got["verdict"]) == (
            at_025["delta"], at_025["lo"], at_025["hi"], str(at_025["verdict"]))
        assert at_star["lo"] <= got["lo"] and got["hi"] <= at_star["hi"]        # nested in, and not, the α* one
        assert (got["lo"], got["hi"]) != (at_star["lo"], at_star["hi"])
    seven = {i: {**a[i], "s3": 1} for i in range(43)}, {i: {**b[i], "s3": 1} for i in range(43)}
    v7 = R.axis_verdict("A7", 1, *seven, report=p)
    assert v7["alpha"] == 0.001 and v7["per_session_alpha"] == 0.025
    assert v7["per_session"]["s1"]["lo"] == R.loss_bound({i: {"s1": seven[0][i]["s1"]} for i in range(43)},
                                                         {i: {"s1": seven[1][i]["s1"]} for i in range(43)},
                                                         alpha=0.025)["lo"]


def test_loss_bound_matches_exact_interval_values_and_strata():
    a, b = _rows1(60, 4, 2)
    strata = {i: i % 3 for i in a}
    r = R.loss_bound(a, b, alpha=0.01, strata=strata)
    groups = [[(a[i]["s1"] - b[i]["s1"]) for i in a if i % 3 == g] for g in range(3)]
    (want,) = R.exact_interval_values(groups, 1, [0.01], any_discordant=True)
    assert (r["lo"], r["hi"], r["delta"]) == (want["lo"], want["hi"], want["delta"])
    assert r["n_items"] == 60 and r["n_sessions"] == 1 and r["discordant_items"] == 6
    with pytest.raises(ValueError, match="without a stratum"):
        R.loss_bound(a, b, alpha=0.01, strata={0: 0})
    with pytest.raises(ValueError):
        R.loss_bound(a, b, alpha=0.6)


def test_loss_bound_zero_discordance_uses_exact_bound_at_alpha():
    a = {i: {"s1": 1, "s2": 0} for i in range(80)}
    r = R.loss_bound(a, {i: dict(v) for i, v in a.items()}, alpha=0.001)
    assert r["exact_bound_used"] and r["lo"] == pytest.approx(-(1 - 0.001 ** (1 / 80)))
    assert r["verdict"] == "PASS"                                     # 1 − 0.001^(1/80) = 8.3 pp ≤ 10 pp
    small = {i: {"s1": 1, "s2": 0} for i in range(40)}
    assert R.loss_bound(small, {i: dict(v) for i, v in small.items()}, alpha=0.001)["verdict"] == "UNDECIDED"


def test_axis_verdict_reads_alpha_from_plan_and_reports_sessions(tmp_path):
    rep = {"axes": {"A5": {"n": 72},
                    "A7": {"calibration": {"alpha_star": 0.01, "binding_cell": None, "look1": {"keep": False}}},
                    "A8": {"calibration": {"alpha_star": 0.005, "binding_cell": None}, "alpha_star_fixed": 0.001}}}
    p = tmp_path / "report.json"
    p.write_text(json.dumps(rep))
    a, b = {}, {}
    for i in range(80):
        a[i] = {"s1": 1, "s2": 1}
        b[i] = {"s1": 1, "s2": 1}
    for i in range(6):
        a[i]["s1"] = 0                                    # session s1 loses on 6 items, s2 identical
    v = R.axis_verdict("A8", 1, a, b, report=p)
    assert v["alpha"] == 0.001 and v["n_sessions"] == 2 and v["size_warnings"] == []
    want = R.loss_bound(a, b, alpha=0.001)
    assert (v["delta"], v["lo"], v["hi"], v["verdict"]) == (want["delta"], want["lo"], want["hi"], want["verdict"])
    assert set(v["per_session"]) == {"s1", "s2"} and v["per_session"]["s2"]["delta"] == 0.0
    assert v["per_session"]["s1"]["delta"] == pytest.approx(-6 / 80)
    assert v["interaction"] == R.session_interaction(a, b) and v["interaction_flag"] == v["interaction"]["flag"]
    a7 = R.axis_verdict("A7", 1, {i: {**a[i], "s3": 1} for i in range(43)}, {i: {**b[i], "s3": 1} for i in range(43)},
                        report=p)
    assert a7["alpha"] == 0.01 and a7["size_warnings"] == []
    assert R.axis_verdict("A8", 1, {i: a[i] for i in range(70)}, {i: b[i] for i in range(70)},
                          report=p)["size_warnings"] == ["70 items, plan look 1 expects 80"]
    with pytest.raises(ValueError, match="looks 1..1"):
        R.axis_verdict("A8", 2, a, b, report=p)


def test_axis_verdict_a5_routes_to_verdict_a5(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"axes": {"A5": {"n": 72}}}))
    a, b = _rows1(72, 1, 1)
    v = R.axis_verdict("A5", 1, a, b, report=p)
    w = R.verdict_a5(1, 1, 72)
    assert v["verdict"] == w.verdict and v["loss_bound"] == w.bound and v["a5"] == w.as_dict()
    assert v["alpha"] == 0.025 and v["interaction"] is None
    with pytest.raises(ValueError, match="single session"):
        R.axis_verdict("A5", 1, {i: {"s1": 1, "s2": 1} for i in range(72)},
                       {i: {"s1": 1, "s2": 1} for i in range(72)}, report=p)
    with pytest.raises(ValueError, match="single session"):
        R.axis_verdict("A1", 1, {i: {"s1": 1, "s2": 1} for i in range(100)},
                       {i: {"s1": 1, "s2": 1} for i in range(100)})



def _s(d, lo, hi):
    return dict(delta=d, lo=lo, hi=hi)


def test_session_disagreement_glm_f3_example():
    # GLM F3: s1 −6 pp [−9, −3], s2 +1 pp [−4, +6] — opposite signs, each interval excludes the other's point
    assert R.session_disagreement({"s1": _s(-0.06, -0.09, -0.03), "s2": _s(0.01, -0.04, 0.06)}) == [("s1", "s2")]


def test_session_disagreement_cases():
    # one direction only: s2's interval contains s1's point
    assert R.session_disagreement({"s1": _s(-0.06, -0.09, -0.03), "s2": _s(0.01, -0.07, 0.06)}) == []
    # same sign
    assert R.session_disagreement({"s1": _s(-0.06, -0.09, -0.03), "s2": _s(-0.01, -0.02, 0.0)}) == []
    # a zero point has no sign
    assert R.session_disagreement({"s1": _s(0.0, -0.01, 0.01), "s2": _s(0.05, 0.02, 0.08)}) == []
    # three sessions: pairwise
    ps = {"s1": _s(-0.06, -0.09, -0.03), "s2": _s(0.01, -0.04, 0.06), "s3": _s(0.05, 0.02, 0.08)}
    assert R.session_disagreement(ps) == [("s1", "s2"), ("s1", "s3")]


def test_axis_plan_a1():
    p = R.axis_plan("A1")
    l1, l2 = p["looks"]
    assert (l1["size"], l2["size"]) == (100, 300) and l1["fraction"] == pytest.approx(1 / 3)
    assert l1["alpha"] == S.obf_alpha(1 / 3, 0.025)
    assert l2["alpha"] == pytest.approx(0.025 - l1["alpha"])
    assert l1["interval_alpha"] == 2 * l1["alpha"] and l1["exact_alpha"] == l1["alpha"]
    d = R.axis_plan("A1", keep_look1=False)
    assert len(d["looks"]) == 1 and d["looks"][0]["size"] == 300 and d["looks"][0]["alpha"] == 0.025


def test_axis_plan_uncalibrated_reference():
    p = R.axis_plan("A7", calibrated=False)
    assert [lk["size"] for lk in p["looks"]] == [2, 3] and p["looks"][0]["unit"] == "sessions"
    assert p["looks"][0]["alpha"] == S.obf_alpha(2 / 3, 0.025)
    assert p["statistic"] == R._EXACT_STAT and p["calibrated"] is False
    assert "exact_interval_values" in p["statistic"]
    a8 = R.axis_plan("A8", calibrated=False)
    assert len(a8["looks"]) == 1 and a8["looks"][0]["interval_alpha"] == 0.05 and a8["sessions"] == 2
    with pytest.raises(ValueError):
        R.axis_plan("A9")


def test_axis_plan_a5():
    a5 = R.axis_plan("A5", n=48)
    assert len(a5["looks"]) == 1 and a5["looks"][0]["alpha"] == 0.025 and a5["looks"][0]["size"] == 48
    assert a5["statistic"] == "exact_paired_loss" and a5["looks"][0]["test"] == "exact_paired_loss"
    assert R.axis_plan("A5", report="/nonexistent/report.json")["looks"][0]["size"] is None
    for bad in (30, 40, 126, 48.0):
        with pytest.raises(ValueError):
            R.axis_plan("A5", n=bad)


def _fake_report(tmp_path, a7_keep=False, a8_star=0.005):
    rep = {"axes": {
        "A5": {"n": 66},
        "A7": {"calibration": {"alpha_star": 0.01, "binding_cell": "m=0.9|D=0.2|sigma=0.5",
                               "look1": {"keep": a7_keep, "alpha_star": 0.001, "alpha_star_look2": 0.0075}}},
        "A8": {"calibration": {"alpha_star": a8_star, "binding_cell": "m=0.5|D=0.3|sigma=0.25"}},
    }}
    p = tmp_path / "report.json"
    p.write_text(json.dumps(rep))
    return p


def test_axis_plan_reads_calibrated_alpha_star(tmp_path):
    p = _fake_report(tmp_path)
    a7 = R.axis_plan("A7", report=p)
    assert a7["calibrated"] and a7["alpha_star"] == 0.01 and not a7["two_look"]
    (lk,) = a7["looks"]
    assert lk["size"] == 3 and lk["alpha"] == 0.01 and lk["interval_alpha"] == 0.02 and lk["exact_alpha"] == 0.01
    assert a7["report_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="does not keep"):
        R.axis_plan("A7", report=p, keep_look1=True)
    a8 = R.axis_plan("A8", report=p)
    assert a8["looks"][0]["alpha"] == 0.005 and a8["binding_cell"] == "m=0.5|D=0.3|sigma=0.25"
    assert R.axis_plan("A5", report=p)["looks"][0]["size"] == 66


def test_axis_plan_a7_two_looks_when_kept(tmp_path):
    p = _fake_report(tmp_path, a7_keep=True)
    a7 = R.axis_plan("A7", report=p)
    assert a7["two_look"] and [lk["alpha"] for lk in a7["looks"]] == [0.001, 0.0075]
    assert [lk["size"] for lk in a7["looks"]] == [2, 3]
    assert len(R.axis_plan("A7", report=p, keep_look1=False)["looks"]) == 1


def test_axis_plan_refuses_missing_calibration(tmp_path):
    p = _fake_report(tmp_path, a8_star=None)
    with pytest.raises(ValueError, match="no committed calibrated"):
        R.axis_plan("A8", report=p)
    with pytest.raises(ValueError, match="no committed calibrated"):
        R.axis_plan("A7", report=tmp_path / "absent.json")


def test_axis_plan_fixed_alpha_star_overrides_calibration(tmp_path):
    """v1.3 (C336): a committed `alpha_star_fixed` is the plan's α*; the calibration is context only."""
    p = _fake_report(tmp_path)
    rep = json.loads(p.read_text())
    rep["axes"]["A8"].update(alpha_star_fixed=0.001, alpha_star_source="fixed by operator ruling C336 (spec v1.3)")
    p.write_text(json.dumps(rep))
    a8 = R.axis_plan("A8", report=p)
    assert a8["alpha_star"] == 0.001 and a8["calibrated_alpha_star"] == 0.005 and not a8["two_look"]
    (lk,) = a8["looks"]
    assert lk["size"] == 80 and lk["alpha"] == 0.001 and lk["interval_alpha"] == 0.002 and lk["exact_alpha"] == 0.001
    assert a8["alpha_star_source"].startswith("fixed") and a8["report_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="one look"):
        R.axis_plan("A8", report=p, keep_look1=True)
    assert R.axis_plan("A7", report=p)["alpha_star"] == 0.01                  # A7 unaffected


def test_axis_plan_committed_report_matches():
    rep, _ = R.load_report()
    assert rep is not None
    assert R.axis_plan("A5")["looks"][0]["size"] == rep["axes"]["A5"]["n"]
    for ax in ("A7", "A8"):
        star = rep["axes"][ax]["calibration"]["alpha_star"]
        assert star is not None, ax
        plan = R.axis_plan(ax)
        want = 0.001 if ax == "A8" else star                    # v1.3 (C336): A8 fixed at 0.001
        assert plan["alpha_star"] == want
        assert plan["looks"][-1]["alpha"] == want or plan["two_look"]
    assert R.axis_plan("A8")["alpha_star"] == 0.001
    assert R.axis_plan("A8")["calibrated_alpha_star"] == rep["axes"]["A8"]["calibration"]["alpha_star"]


# ------------------------------------------------------------------------------------------------------ A5 (v1.1)
def test_verdict_a5_cases():
    v = R.verdict_a5(1, 1, 72)
    assert v == ("PASS", v.bound) and v.verdict == "PASS" and v["verdict"] == "PASS" and v.annotation is None
    verdict, bound = v
    assert bound == v["bound"] and 0 < bound <= 0.10
    # delta just under the floor with a rejected H0 is not a PASS
    assert R.verdict_a5(4, 0, 72).verdict == "UNDECIDED"          # δ −5.6 pp; exact binomial p 0.125 → not LOSS
    lo = R.verdict_a5(12, 1, 72)                                  # δ −15.3 pp; binomial p ≈ 0.0034, b > c
    assert lo.verdict == "LOSS" and lo.loss_pvalue <= 0.05
    assert R.verdict_a5(1, 12, 72).verdict == "PASS"              # X better
    und = R.verdict_a5(2, 0, 42)
    assert und.verdict == "UNDECIDED" and und.bound > 0.10


def test_verdict_a5_annotation_loss_shown():
    # 150 items, 7 losses, 0 gains: δ −4.7 pp ≥ floor, loss bound ≤ 10 pp, exact binomial p 0.0156 (loss shown)
    v = R.verdict_a5(7, 0, 150)
    assert v.verdict == "PASS" and v.annotation == R.LOSS_SHOWN and v.reject and v.bound <= 0.10
    assert R.verdict_a5(6, 0, 120).verdict == "UNDECIDED"        # same shape at 120 items: bound still > 10 pp


def test_a5_region_matches_exact_paired_loss():
    n = 42
    region = R.a5_rejection_region(n)
    for b in range(0, 12):
        for c in range(0, 6):
            assert ((b, c) in region) == S.exact_paired_loss(b, c, n)["reject"], (b, c)
    assert R.a5_rejection_region(n) is region                    # cached


@pytest.mark.parametrize("n", list(range(42, 121, 6)))
def test_a5_exact_size_at_most_alpha(n):
    assert R.a5_exact_size(n) <= 0.025


# ------------------------------------------------------------------------------------ session × arm interaction
def _maps(rows):
    a = {i: {f"s{s}": (1 if d == 1 else (0 if d == -1 else 1)) for s, d in enumerate(r)} for i, r in enumerate(rows)}
    b = {i: {f"s{s}": (0 if d == 1 else 1) for s, d in enumerate(r)} for i, r in enumerate(rows)}
    return a, b


def test_session_interaction_identical_sessions_p_one():
    rows = [(0, 0, 0)] * 20 + [(-1, -1, -1)] * 5 + [(1, 1, 1)] * 3
    a, b = _maps(rows)
    r = R.session_interaction(a, b, iters=500)
    assert r["pvalue"] == 1.0 and r["flag"] is False and r["statistic"] == 0.0


def test_session_interaction_detects_and_reproduces():
    rows = [(-1, 0)] * 15 + [(0, 0)] * 25
    a, b = _maps(rows)
    r = R.session_interaction(a, b, iters=2000, seed=426)
    assert r["flag"] is True and r["pvalue"] < 0.01
    assert r["per_session_delta"] == {"s0": -15 / 40, "s1": 0.0}
    assert R.session_interaction(a, b, iters=2000, seed=426) == r


def test_session_interaction_null_case_not_flagged():
    rows = [(-1, 0), (0, -1)] * 8 + [(0, 0)] * 20
    a, b = _maps(rows)
    r = R.session_interaction(a, b, iters=2000)
    assert r["pvalue"] > 0.5 and not r["flag"]


def test_session_interaction_refuses_mismatch():
    a, b = _maps([(0, 0)] * 5)
    del b[2]
    with pytest.raises(ValueError, match="item sets differ"):
        R.session_interaction(a, b)
    a, b = _maps([(0, 0)] * 5)
    b[1] = {"s0": 1, "s9": 1}
    with pytest.raises(ValueError, match="session sets differ"):
        R.session_interaction(a, b)
    with pytest.raises(ValueError):
        R.session_interaction(*_maps([(0, 0)] * 5), iters=0)


_RESAMPLE_FNS = ("paired_delta", "paired_session_delta")


def _statistic_fields(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "statistic" and isinstance(v, str):
                yield v
            yield from _statistic_fields(v)
    elif isinstance(node, list):
        for v in node:
            yield from _statistic_fields(v)


def test_no_plan_or_report_names_resample_functions_as_decision_statistic():
    """Spec v1.4: the decision statistic is the exact item bootstrap; the resample functions stay descriptive."""
    for axis in ("A1", "A7", "A8"):
        for calibrated in (True, False):
            st = R.axis_plan(axis, calibrated=calibrated)["statistic"]
            assert "exact_interval_values" in st and not any(f in st for f in _RESAMPLE_FNS)
    assert R.axis_plan("A5", n=48)["statistic"] == "exact_paired_loss"
    assert all(not any(f in sp["statistic"] for f in _RESAMPLE_FNS) for sp in R._AXES.values())
    report = json.loads(R.REPORT_JSON.read_text())
    stats = list(_statistic_fields(report))
    assert stats and not [s for s in stats if any(f in s for f in _RESAMPLE_FNS)]
    md = (R.REPORT_JSON.parent / "REPORT.md").read_text()
    assert not any(f in md for f in _RESAMPLE_FNS)
