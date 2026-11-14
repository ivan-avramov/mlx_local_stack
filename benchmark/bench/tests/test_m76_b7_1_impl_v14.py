"""M76 B7.1 (implementer): spec amendment v1.4 (C339) — the chosen plan registered in `m76_rule`: A5's two looks read
from the committed report, `verdict_a5(..., alpha=)` default unchanged, `axis_verdict("A5", look, …)` at the look's α
(look-1 LOSS stops, UNDECIDED → look 2, per-task point gates at the deciding look), `A8_HOLD_PP` / `a8_hold`, and the
report's committed plan TD + A5-2L."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import pytest

from bench import m76_rule as R
from bench import m76_sim as M

REPORT = Path(__file__).resolve().parents[2] / "results" / "m76" / "b7-simulation"


def _rep():
    rep, sha = R.load_report()
    assert rep is not None
    return rep, sha


def _md_joint():
    md = (REPORT / "REPORT.md").read_text()
    return md[md.index("## Joint plan (B7.1)"):]


def _rows(b, c, n):
    """A5 rows (one session): the first `b` items N16-only passes, the next `c` X-only passes, the rest concordant."""
    a, bb = {}, {}
    for i in range(n):
        x, y = (0, 1) if i < b else (1, 0) if i < b + c else (1, 1)
        a[i], bb[i] = {"s1": x}, {"s1": y}
    return a, bb


def _a52l_report(tmp_path, looks, *, safe=True, available=True, n=72):
    rep = {"axes": {"A5": {"n": n}},
           "variants": {"A5-2L": dict(name="A5-2L", available=available, safe=safe, looks=looks,
                                      exact=dict(size=0.0216))}}
    p = tmp_path / "report.json"
    p.write_text(json.dumps(rep))
    return p


# ------------------------------------------------------------------------------------------------ A5 two-look plan
def test_a5_plan_has_the_committed_reports_two_looks():
    rep, sha = _rep()
    want = rep["variants"]["A5-2L"]["looks"]
    p = R.axis_plan("A5")
    assert p["two_look"] is True and p["statistic"] == "exact_paired_loss" and p["report_sha256"] == sha
    assert [(lk["look"], lk["size"], lk["alpha"]) for lk in p["looks"]] == [(1, 72, 0.003808), (2, 120, 0.021192)]
    assert [(lk["size"], lk["alpha"], lk["fraction"]) for lk in p["looks"]] == [
        (w["size"], w["alpha"], w["fraction"]) for w in want]
    assert all(lk["test"] == "exact_paired_loss" and lk["exact_alpha"] == lk["alpha"] for lk in p["looks"])
    assert p["items"] == 120 and p["look1_loss_stops"] is True and p["plan_source"] == "variants.A5-2L"
    assert p["exact_size"] == rep["variants"]["A5-2L"]["exact"]["size"]


def test_a5_plan_reads_the_report_never_retyped(tmp_path):
    p = _a52l_report(tmp_path, [dict(look=1, size=66, alpha=0.002, fraction=0.55),
                                dict(look=2, size=120, alpha=0.0229, fraction=1.0)])
    plan = R.axis_plan("A5", report=p)
    assert [(lk["size"], lk["alpha"]) for lk in plan["looks"]] == [(66, 0.002), (120, 0.0229)]
    assert plan["report_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()


def test_a5_plan_refuses_an_unsafe_or_unavailable_registered_variant(tmp_path):
    looks = [dict(look=1, size=72, alpha=0.003808, fraction=0.6), dict(look=2, size=120, alpha=0.021192, fraction=1.0)]
    for kw in (dict(safe=False), dict(available=False)):
        with pytest.raises(ValueError, match="A5-2L"):
            R.axis_plan("A5", report=_a52l_report(tmp_path, looks, **kw))
    with pytest.raises(ValueError, match="A5-2L"):
        R.axis_plan("A5", report=_a52l_report(tmp_path, looks[:1]))


def test_a5_b7_single_look_paths_unchanged():
    p = R.axis_plan("A5", n=72)
    assert not p["two_look"] and [(lk["size"], lk["alpha"]) for lk in p["looks"]] == [(72, 0.025)]
    assert len(R.axis_plan("A5", n=72, calibrated=False)["looks"]) == 1


def test_a5_exact_two_look_size_matches_the_report():
    rep, _ = _rep()
    (l1, l2) = R.axis_plan("A5")["looks"]
    ex = M.a5_two_look_size(l1["size"], l2["size"], l1["alpha"], l2["alpha"])
    assert round(ex["size"], 6) == rep["variants"]["A5-2L"]["exact"]["size"] <= R.ALPHA_TOTAL
    assert round(ex["size_look1"], 6) == rep["variants"]["A5-2L"]["exact"]["size_look1"]


# ------------------------------------------------------------------------------------------ A5 two-look verdicts
def test_axis_verdict_a5_look1_pass_stops_at_the_registered_alpha():
    a1 = R.axis_plan("A5")["looks"][0]["alpha"]
    v = R.axis_verdict("A5", 1, *_rows(0, 0, 72))
    assert v["alpha"] == a1 and v["verdict"] == "PASS" and v["a5"] == R.verdict_a5(0, 0, 72, alpha=a1).as_dict()
    assert v["stop"] is True and v["next_look"] is None and v["size_warnings"] == []


def test_axis_verdict_a5_look1_undecided_goes_to_look2():
    a1 = R.axis_plan("A5")["looks"][0]["alpha"]
    v = R.axis_verdict("A5", 1, *_rows(1, 1, 72))
    assert v["verdict"] == "UNDECIDED" and v["a5"] == R.verdict_a5(1, 1, 72, alpha=a1).as_dict()
    assert R.verdict_a5(1, 1, 72).verdict == "PASS"        # the registered α, not 0.025, decided it
    assert v["stop"] is False and v["next_look"] == 2


def test_axis_verdict_a5_look1_loss_stops():
    v = R.axis_verdict("A5", 1, *_rows(12, 0, 72))
    assert v["verdict"] == "LOSS" and v["stop"] is True and v["next_look"] is None


def test_axis_verdict_a5_look2_on_cumulative_rows():
    a2 = R.axis_plan("A5")["looks"][1]["alpha"]
    v = R.axis_verdict("A5", 2, *_rows(2, 2, 120))
    assert v["alpha"] == a2 and v["a5"] == R.verdict_a5(2, 2, 120, alpha=a2).as_dict() and v["verdict"] == "PASS"
    assert v["stop"] is True and v["next_look"] is None and v["size_warnings"] == []
    u = R.axis_verdict("A5", 2, *_rows(9, 3, 120))
    assert u["verdict"] == R.verdict_a5(9, 3, 120, alpha=a2).verdict and u["stop"] is True
    assert R.axis_verdict("A5", 2, *_rows(2, 2, 72))["size_warnings"] == ["72 items, plan look 2 expects 120"]


def test_axis_verdict_a5_task_gates_at_the_deciding_look():
    a, b = _rows(0, 0, 72)
    for i in range(0, 8, 2):                     # four N16-only passes among task-0 items (36): −11.1 pp
        a[i]["s1"] = 0
    tasks = {i: ("retrieval" if i % 2 == 0 else "chain-4") for i in range(72)}
    v = R.axis_verdict("A5", 1, a, b, tasks=tasks)
    g = v["task_gates"]
    assert g["retrieval"]["n"] == 36 and g["retrieval"]["pass"] is False and g["chain-4"]["pass"] is True
    assert v["task_gates_pass"] is False and v["clean"] is False
    if v["verdict"] == "PASS":
        assert v["stop"] is True                 # a gate failure never triggers look 2
    assert R.axis_verdict("A5", 1, *_rows(0, 0, 72))["task_gates"] is None
    ok = R.axis_verdict("A5", 1, *_rows(0, 0, 72), tasks=tasks)
    assert ok["task_gates_pass"] is True and ok["clean"] is True


def test_task_gate_boundary_is_exact():
    a, b = _rows(0, 0, 40)
    a[0]["s1"] = 0                                # 1 / 20 of task 0 → exactly −5 pp: gate holds
    tasks = {i: i % 2 for i in range(40)}
    g = R.axis_verdict("A5", 1, a, b, tasks=tasks)["task_gates"]
    assert g[0]["pass"] is True
    a[2]["s1"] = 0
    assert R.axis_verdict("A5", 1, a, b, tasks=tasks)["task_gates"][0]["pass"] is False


def test_axis_verdict_a5_tasks_must_cover_every_item():
    with pytest.raises(ValueError, match="task"):
        R.axis_verdict("A5", 1, *_rows(0, 0, 72), tasks={i: 0 for i in range(70)})


# --------------------------------------------------------------------------------- verdict_a5 default unchanged
_CASES = [(0, 0, 72), (1, 1, 72), (3, 0, 72), (0, 3, 72), (6, 2, 72), (12, 0, 72), (10, 10, 72), (2, 9, 72),
          (0, 0, 120), (5, 3, 120), (14, 4, 120), (20, 2, 120), (4, 4, 42)]
_CASES_SHA = "ae6c35026d5a2f469b5422cb32bdc7f7b3b29f990b290d0b8369fffe429ddc01"   # pinned before the v1.4 change


def test_verdict_a5_default_output_byte_identical():
    h = hashlib.sha256()
    for b, c, n in _CASES:
        d = R.verdict_a5(b, c, n).as_dict()
        assert d == R.verdict_a5(b, c, n, alpha=0.025).as_dict()
        h.update(json.dumps(d, sort_keys=True).encode())
    assert h.hexdigest() == _CASES_SHA


# ----------------------------------------------------------------------------------------------------- A8 HOLD
def test_a8_hold_constant_and_boundaries():
    assert R.A8_HOLD_PP == -0.20
    assert R.a8_hold({"py": -0.20, "ts": 0.0})["hold"] is False          # −20 pp exactly does not fire
    assert R.a8_hold({"py": Fraction(-1, 5)})["hold"] is False
    assert R.a8_hold({"py": -8 / 40})["hold"] is False
    h = R.a8_hold({"py": -0.21, "ts": 0.0, "go": -0.25})
    assert h["hold"] is True and h["languages"] == ["go", "py"] and h["threshold"] == -0.20 and h["blocking"] is True
    assert R.a8_hold({"py": Fraction(-9, 40)})["hold"] is True
    assert R.a8_hold({"py": {"delta": -0.3}})["hold"] is True
    with pytest.raises(ValueError):
        R.a8_hold({})


def _a8_rows(lang_sums):
    """80 items × s1 / s2, 20 per language; language j's Σ d = lang_sums[j] (−1 per (item, session) from the front)."""
    langs = ["py", "ts", "go", "rs"]
    a, b, lang = {}, {}, {}
    for j, ln in enumerate(langs):
        cells = [(j * 20 + i, s) for i in range(20) for s in ("s1", "s2")]
        for i in range(j * 20, j * 20 + 20):
            a[i], b[i], lang[i] = {"s1": 1, "s2": 1}, {"s1": 1, "s2": 1}, ln
        for i, s in cells[:-lang_sums[j]] if lang_sums[j] < 0 else []:
            a[i][s] = 0
    return a, b, lang


def test_axis_verdict_a8_reports_hold_from_per_language_rows():
    a, b, lang = _a8_rows([-8, 0, 0, 0])                 # py: −8 / 40 = −20 pp exactly → no HOLD
    v = R.axis_verdict("A8", 1, a, b, languages=lang, interaction_iters=200)
    assert v["hold"]["hold"] is False and v["hold"]["per_language"]["py"] == pytest.approx(-0.20)
    a, b, lang = _a8_rows([-9, 0, 0, 0])
    v = R.axis_verdict("A8", 1, a, b, languages=lang, interaction_iters=200)
    assert v["hold"]["hold"] is True and v["hold"]["languages"] == ["py"] and v["blocking"] is True
    assert R.axis_verdict("A8", 1, a, b, interaction_iters=200)["hold"] is None
    with pytest.raises(ValueError, match="language"):
        R.axis_verdict("A8", 1, a, b, languages={i: "py" for i in range(79)}, interaction_iters=200)


def test_sim_hold_threshold_is_the_registered_one():
    assert dict(M.HOLD_THRESHOLDS)[M.HEADLINE_HOLD] * 0.01 == pytest.approx(R.A8_HOLD_PP)
    assert M.hold_fires(-8, -20) is False and M.hold_fires(-9, -20) is True         # 20 items × 2 sessions


# ------------------------------------------------------------------------------------ report: TD + A5-2L committed
def test_spec_is_v14():
    rep, _ = _rep()
    assert M.B71_SPEC == "docs/specs/m76-b7-1-joint-plan.md v1.4" == rep["joint"]["spec"]


def test_report_committed_plan_is_td_plus_a5_2l():
    rep, _ = _rep()
    cp, v = rep["joint"]["committed_plan"], rep["variants"]
    assert cp["name"] == "TD + A5-2L" and cp["a8_option"] == "TD" and cp["a5"] == "A5-2L"
    assert cp["decisions"] == ["C338", "C339"] and cp["a8_hold_pp"] == -20 and cp["hold"] == M.HEADLINE_HOLD
    assert cp["a5_looks"] == v["A5-2L"]["looks"]
    assert [(lk["size"], lk["alpha"]) for lk in cp["a5_looks"]] == [
        (lk["size"], lk["alpha"]) for lk in R.axis_plan("A5")["looks"]]
    assert cp["clean_pass0"] == v["A5-2L"]["clean_pass0"] and cp["hours"] == v["A5-2L"]["hours"]
    assert cp["clean_pass0_by_cell"] == v["A5-2L"]["clean_pass0_by_cell"]
    assert cp["worst_final_false_pass10"] == v["A5-2L"]["worst_final_false_pass10"]
    assert cp["reference"]["clean_pass0"] == rep["joint"]["headline"]["clean_pass"]


def test_report_statuses_adopted_and_not_adopted():
    rep, _ = _rep()
    v = rep["variants"]
    assert v["A5-2L"]["status"] == "adopted (C339)"
    assert v["A7-5S"]["status"].startswith("not adopted (C339)")
    assert v["A7-2L"]["status"].startswith("not adopted")
    for name in ("T0", "T1", "T2", "T3"):
        assert v["screen_options"][name]["status"].startswith("not adopted")
    assert v["screen_options"]["TD"]["status"].startswith("committed")
    assert "C339" in v["note"] and "TD + A5-2L" in v["note"]


def test_md_committed_plan_row_and_headline():
    sec = _md_joint()
    rep, _ = _rep()
    cp = rep["joint"]["committed_plan"]
    assert "docs/specs/m76-b7-1-joint-plan.md v1.4" in sec
    head = next(line for line in sec.splitlines() if line.startswith("**Headline: P(clean PASS) at loss 0 = "))
    assert M._rng3(cp["clean_pass0"]) in head and "TD + A5-2L" in head
    row = next(line for line in sec.splitlines() if line.startswith("| committed plan (TD + A5-2L"))
    assert f"**{M._rng3(cp['clean_pass0'])}**" in row
    assert any(line.startswith("| single-look A5 reference") for line in sec.splitlines())
    a75 = next(line for line in sec.splitlines() if line.startswith("| A7-5S "))
    assert "not adopted (C339)" in a75
