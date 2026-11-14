"""M76 B7.1 spec v1.3 / v1.4 (C338, C339).

v1.3: TD (the decider always runs) is the committed A8 path; T0–T3 are alternatives only; A7-5S has no clean-PASS estimate;
the worst final look is reported on the committed grid with the C336 residual beside it.
v1.4: `m76_rule.axis_plan("A5")` registers A5-2L's two looks (n 72 at α 0.003808, n 120 at 0.021192, read from the report);
`verdict_a5(..., alpha=)` takes the look's α (default 0.025 unchanged); `axis_verdict("A5", look, …)` runs per look (look-1
PASS or LOSS stops, UNDECIDED → look 2 on the cumulative 120 rows) with the per-task point gates at the deciding look;
`A8_HOLD_PP = −0.20` and `a8_hold` (any language's decider point < −20 pp, −20 pp exactly does not fire); the committed plan
in the report is TD + A5-2L.

References (class (b)): my own PASS / LOSS masks per (b, c) cell built from `stats` (`_a5_masks`: the exact rejection region
and the exact binomial LOSS test), my A5-2L exact-size enumerator, a direct joint simulation of TD + A5-2L, and exact
integer / Fraction arithmetic for the HOLD. (a) = stated by the specification; (c) = the candidate's layout.
"""
import inspect
from fractions import Fraction

import pytest

from bench.tests.test_m76_b7_1_fe_fix_plan import _per_arm
from bench.tests.test_m76_b7_1_fe_support import (COMMITTED, _a5_masks, a5_two_look_size, committed_report, direct_joint,
                                                  mc_tol, task_gates_ok)


def _plan():
    from bench import m76_rule as R
    return R.axis_plan("A5")


# ------------------------------------------------------------------------------------- v1.3: TD committed throughout
def test_report_names_spec_v14_and_the_committed_plan_is_td_plus_a5_2l():  # (a)+(c)
    rep = committed_report()
    j = rep["joint"]
    assert j["spec"].endswith("m76-b7-1-joint-plan.md v1.4")
    cp = j["committed_plan"]
    assert cp["name"] == "TD + A5-2L" and cp["a8_option"] == "TD" and cp["a5"] == "A5-2L" and cp["hold"] == "lt20"
    assert cp["a8_hold_pp"] == -20
    assert [(lk["size"], lk["alpha"]) for lk in cp["a5_looks"]] == [(72, 0.003808), (120, 0.021192)]
    v = rep["variants"]
    assert v["A5-2L"]["status"].startswith("adopted") and v["A7-5S"]["status"].startswith("not adopted")
    assert v["A7-2L"]["status"].startswith("not adopted")
    so = v["screen_options"]
    assert so["TD"]["committed"] is True and so["TD"]["status"].startswith("committed")
    for o in ("T0", "T1", "T2", "T3"):
        assert so[o]["committed"] is False and "superseded by C338" in so[o]["status"]


def test_td_is_the_a8_path_in_every_joint_term():  # (a)+(c)
    """Every joint term / scenario runs the decider on every plan (trigger 1) and equals the nested TD path."""
    j = committed_report()["joint"]
    n = j["a8_nested"]
    for cell, blk in j["cells"].items():
        for loss in ("loss=0.0", "loss=0.1"):
            p = blk["terms"][loss]["A8_path"]
            assert p["option"] == "TD" and p["trigger"]["k"] == p["trigger"]["n"], (cell, loss)
            assert p["clean"] == n[loss]["paths"]["TD"]["lt20"]["clean"]


def test_committed_plan_clean_pass_is_the_product_of_a1_a5_2l_a7_and_td_path():  # (a)+(c)
    rep = committed_report()
    j = rep["joint"]
    t = j["cells"]["nearest_realisable"]["terms"]["loss=0.0"]
    path = j["a8_nested"]["loss=0.0"]["paths"]["TD"]["lt20"]["clean"]["rate"]
    want = t["A1"]["clean"]["rate"] * rep["variants"]["A5-2L"]["clean0"]["rate"] * t["A7"]["clean"]["rate"] * path
    assert abs(j["committed_plan"]["clean_pass0"]["rate"] - want) <= 2e-5
    tp = j["cells"]["planning"]["terms"]["loss=0.0"]
    assert abs(j["committed_plan"]["clean_pass0_by_cell"]["planning"]["lt20"]["rate"]
               - tp["A1"]["clean"]["rate"] * rep["variants"]["A5-2L"]["clean0"]["rate"] * tp["A7"]["clean"]["rate"] * path) <= 2e-5


@pytest.mark.parametrize("a5_2l", [False, True])
def test_committed_plan_clean_pass_matches_my_direct_joint_simulation(a5_2l):  # (b)+(c)
    """TD + A5-2L (and the single-look A5 reference, `joint.committed_plan.reference`) against my own replication-level
    simulation of the whole plan: the decider on every plan (nested items), A5 as the registered two-look rule with its
    per-task gates at the deciding look, HOLD < −20 pp; 4000 replications at the headline cell; 3.5 σ_MC."""
    rep = committed_report()
    cp = rep["joint"]["committed_plan"]
    alphas = (0.003808, 0.021192) if a5_2l else None
    ref = (cp["clean_pass0"] if a5_2l else cp["reference"]["clean_pass0"])["rate"]
    mine = direct_joint(rep, 0.0, 4000, seed=51 if a5_2l else 52, a5_alphas=alphas)["clean"]
    assert abs(mine - ref) <= mc_tol(ref, 4000, 20000), (a5_2l, mine, ref)


def test_committed_plan_hours_reproduce_by_independent_arithmetic():  # (b)
    rep = committed_report()
    a1 = rep["axes"]["A1"]
    p_a1 = a1["cells"]["sigma=0.25|loss=0.0"]["look1"]["UNDECIDED"]["rate"] if a1["final"] == "two_look" else 1.0
    u1 = rep["variants"]["A5-2L"]["p_undecided_look1"]
    h = rep["joint"]["committed_plan"]["hours"]
    assert h["expected"] == pytest.approx(2 * _per_arm(p_a1, 72 + 48 * u1, 3, 1.0), abs=1e-3)
    assert h["worst"] == pytest.approx(2 * _per_arm(1.0, 120, 3, 1.0), abs=1e-3)
    assert h["whole_stage_expected"] == pytest.approx(h["expected"] + 5.6, abs=1e-3)


def test_a7_5s_has_no_clean_pass_estimate_and_says_so():  # (a)+(c)
    v = committed_report()["variants"]["A7-5S"]
    assert v.get("clean_pass0") is None and v.get("clean_pass0_by_cell") is None
    assert v["pays"] is None or v["pays"] is False
    md = (COMMITTED / "REPORT.md").read_text()
    assert "clean PASS not estimated (interaction flag unsimulated)" in md


def test_worst_final_look_is_on_the_committed_grid_with_the_c336_residual():  # (a)+(b)
    """`worst_final_false_pass10`: grid 'committed'; the residual is B7's own: the realisable SD 0.5 cells of A8's full grid
    over 0.025 (read from `axes.A8.full_grid_at_fixed`), its max upper bound; the A5 entry is the exact two-look size (my
    enumeration, within 1e-4)."""
    rep = committed_report()
    w = rep["joint"]["committed_plan"]["worst_final_false_pass10"]          # the committed plan (A5-2L)
    fg = rep["axes"]["A8"]["full_grid_at_fixed"]
    # the joint-level block still describes the single-look A5 reference (implementer P19): same grid label and residual
    wj = rep["joint"]["worst_final_false_pass10"]
    assert wj["grid"] == "committed" and wj["a8_residual"] == w["a8_residual"]
    over = fg["over_target_realisable"]
    assert w["grid"] == "committed"
    assert w["a8_residual"]["cells"] == len(over) == 3
    assert abs(w["a8_residual"]["max_hi"] - max(fg["cells"][c]["hi"] for c in over)) <= 1e-6
    assert all("sigma=0.5" in c for c in over) and "2.82" in w["a8_residual"]["text"]
    size, _ = a5_two_look_size(alphas=[0.003808, 0.021192])
    assert abs(w["by_axis"]["A5"] - size) <= 1e-4
    md = (COMMITTED / "REPORT.md").read_text()
    assert "worst on the committed grid" in md and "C336 residual" in md


# ------------------------------------------------------------------------------------------ v1.4: the A5 plan (a)
def test_registered_a5_plan_is_the_reports_a5_2l_never_retyped():  # (a)+(c)
    rep = committed_report()
    plan = _plan()
    v = rep["variants"]["A5-2L"]
    assert plan["two_look"] is True and plan["statistic"] == "exact_paired_loss"
    assert [(lk["size"], lk["alpha"]) for lk in plan["looks"]] == [(lk["size"], lk["alpha"]) for lk in v["looks"]]
    assert [(lk["size"], lk["alpha"]) for lk in plan["looks"]] == [(72, 0.003808), (120, 0.021192)]
    assert plan["look1_loss_stops"] is True and plan["plan_source"] == "variants.A5-2L"
    assert abs(plan["looks"][0]["alpha"] + plan["looks"][1]["alpha"] - 0.025) < 1e-9       # the total α is spent exactly


def test_registered_plan_exact_size_matches_my_enumeration_and_is_safe():  # (b)
    plan = _plan()
    mine, _ = a5_two_look_size(alphas=[lk["alpha"] for lk in plan["looks"]])
    assert mine <= 0.025 and plan["exact_size"] <= 0.025
    assert abs(plan["exact_size"] - mine) <= 1e-3, (plan["exact_size"], mine)


def test_b7_single_look_a5_plan_is_still_available_by_explicit_n():  # (a)
    from bench import m76_rule as R
    p = R.axis_plan("A5", n=72, calibrated=False)
    assert [(lk["size"], lk["alpha"]) for lk in p["looks"]] == [(72, 0.025)] and p["two_look"] is False


# --------------------------------------------------------------------------- v1.4: two-look verdicts (b), my masks
def _rows(n, loss_idx, gain_idx):
    """X (a) vs N16 (b) rows, one session: items in `loss_idx` are N16-pass / X-fail (d = −1), `gain_idx` X-pass / N16-fail
    (d = +1), the rest both pass."""
    a = {i: {"s1": 1} for i in range(n)}
    b = {i: {"s1": 1} for i in range(n)}
    for i in loss_idx:
        a[i]["s1"] = 0
    for i in gain_idx:
        b[i]["s1"] = 0
    return a, b


def _bc_rows(n, bcount, ccount):
    return _rows(n, range(bcount), range(bcount, bcount + ccount))


def _mine(masks, bc):
    p, l = masks
    return "PASS" if p[bc] else "LOSS" if l[bc] else "UNDECIDED"


def _verdict(look, a, b, **kw):
    from bench import m76_rule as R
    return R.axis_verdict("A5", look, a, b, **kw)


@pytest.fixture(scope="module")
def masks():
    plan = _plan()
    a1, a2 = (lk["alpha"] for lk in plan["looks"])
    return dict(m1=_a5_masks(72, a1), m2=_a5_masks(120, a2), m025=_a5_masks(72, 0.025))


CELLS = [(0, 0), (1, 0), (0, 2), (1, 1), (2, 1), (3, 2), (2, 4), (4, 4), (6, 2), (5, 1), (8, 3), (10, 2), (12, 1), (9, 9)]


@pytest.mark.parametrize("bcnt,ccnt", CELLS)
def test_look1_verdict_is_my_mask_at_the_registered_alpha_and_stop_logic(masks, bcnt, ccnt):  # (b)
    """Look 1 on 72 items at α₁ = 0.003808: the verdict equals my PASS / LOSS / UNDECIDED mask (exact rejection region at
    α₁; LOSS = exact binomial); PASS and LOSS stop, UNDECIDED goes to look 2 (`stop` False, `next_look` 2)."""
    a, b = _bc_rows(72, bcnt, ccnt)
    res = _verdict(1, a, b)
    want = _mine(masks["m1"], (bcnt, ccnt))
    assert str(res["verdict"]) == want, (bcnt, ccnt, res["verdict"], want)
    assert res["alpha"] == pytest.approx(_plan()["looks"][0]["alpha"])
    assert res["stop"] is (want != "UNDECIDED") and res["next_look"] == (None if want != "UNDECIDED" else 2)
    assert res["size_warnings"] == []


def test_there_is_a_cell_that_passes_at_the_single_look_alpha_but_is_undecided_at_look_1(masks):  # (b)
    """The registered α is what is used: some (b, c) PASS at 0.025 on 72 items but are UNDECIDED at 0.003808, and
    `axis_verdict` reports UNDECIDED / next_look 2 for them (a single-look plan would have stopped with PASS)."""
    p025, _ = masks["m025"]
    p1, l1 = masks["m1"]
    cells = [(b, c) for b in range(10) for c in range(10) if p025[b, c] and not p1[b, c] and not l1[b, c]]
    assert cells, "no such cell: α₁ would equal the single look's α"
    b_, c_ = cells[0]
    res = _verdict(1, *_bc_rows(72, b_, c_))
    assert str(res["verdict"]) == "UNDECIDED" and res["stop"] is False and res["next_look"] == 2


def test_look1_loss_stops(masks):  # (b)
    p1, l1 = masks["m1"]
    cells = [(b, c) for b in range(30) for c in range(8) if l1[b, c]]
    assert cells
    b_, c_ = cells[0]
    res = _verdict(1, *_bc_rows(72, b_, c_))
    assert str(res["verdict"]) == "LOSS" and res["stop"] is True and res["next_look"] is None


def test_look2_runs_on_the_cumulative_120_rows_at_alpha2(masks):  # (b)
    """Take a look-1 UNDECIDED cell, add 48 items with no discordance: look 2 reads the CUMULATIVE (b, c) on n = 120 at
    α₂ = 0.021192 — the verdict equals my n = 120 mask; the final look always stops."""
    p1, l1 = masks["m1"]
    found = None
    for b in range(0, 12):
        for c in range(0, 12):
            if not p1[b, c] and not l1[b, c] and masks["m2"][0][b, c]:
                found = (b, c)
                break
        if found:
            break
    assert found, "no look-1 UNDECIDED cell that passes at look 2 with 48 more clean items"
    a, b = _bc_rows(120, *found)
    r1 = _verdict(1, {i: a[i] for i in range(72)}, {i: b[i] for i in range(72)})
    r2 = _verdict(2, a, b)
    assert str(r1["verdict"]) == "UNDECIDED" and r1["next_look"] == 2
    assert str(r2["verdict"]) == "PASS" == _mine(masks["m2"], found)
    assert r2["alpha"] == pytest.approx(_plan()["looks"][1]["alpha"]) and r2["n_items"] == 120
    assert r2["stop"] is True and r2["next_look"] is None and r2["size_warnings"] == []


@pytest.mark.parametrize("bcnt,ccnt", [(0, 0), (3, 3), (6, 1), (9, 2), (14, 4), (20, 3)])
def test_look2_verdict_is_my_mask_and_the_final_look_always_stops(masks, bcnt, ccnt):  # (b)
    res = _verdict(2, *_bc_rows(120, bcnt, ccnt))
    assert str(res["verdict"]) == _mine(masks["m2"], (bcnt, ccnt))
    assert res["stop"] is True and res["next_look"] is None


def test_look_out_of_range_and_wrong_size_are_flagged():  # (a)
    from bench import m76_rule as R
    with pytest.raises(ValueError):
        R.axis_verdict("A5", 3, *_bc_rows(120, 0, 0))
    res = _verdict(1, *_bc_rows(120, 0, 0))                       # 120 rows at look 1 (expects 72)
    assert any("72" in w for w in res["size_warnings"])


# -------------------------------------------------------------------------------------------- per-task gates (b)
def test_task_gates_at_the_deciding_look_and_exact_boundary(masks):  # (b)
    """Tasks by item parity. 2 N16-pass / X-fail items in ONE task of 36 = −5.56 pp (< −5 pp): the gate fails (`clean`
    False) although the pooled verdict is PASS, and a gate failure never triggers look 2 (`stop` stays True); one such item
    (−2.78 pp) passes; spread over both tasks it passes."""
    p1, _ = masks["m1"]
    pass_cells = [(b, c) for b in range(2, 6) for c in range(0, 12) if p1[b, c]]
    assert pass_cells, "need a look-1 PASS cell with ≥ 2 N16-pass / X-fail items"
    b_, c_ = pass_cells[0]
    tasks = {i: i % 2 for i in range(72)}
    even = [i for i in range(72) if i % 2 == 0]
    odd = [i for i in range(72) if i % 2 == 1]
    # all losses in task 0, all gains in task 1
    bad = _rows(72, even[:b_], odd[:c_])
    r = _verdict(1, *bad, tasks=tasks)
    assert str(r["verdict"]) == "PASS" and r["stop"] is True
    assert r["task_gates_pass"] is False and r["clean"] is False
    assert r["task_gates"][0]["pass"] is False and r["task_gates"][0]["delta"] == pytest.approx(-b_ / 36)
    assert r["task_gates"][1]["pass"] is True
    # the same counts spread evenly over both tasks: each task −b/2 .. gates pass when b/2 ≤ 1 (−2.78 pp)
    spread = _rows(72, (even[:b_ // 2] + odd[:b_ - b_ // 2]), (even[:c_ // 2] + odd[:c_ - c_ // 2]))
    rs = _verdict(1, *spread, tasks=tasks)
    d_spread = [[spread[0][i]["s1"] - spread[1][i]["s1"]] for i in range(72)]
    assert rs["task_gates_pass"] is task_gates_ok(d_spread)                                  # my predicate, same rows
    assert rs["clean"] == (str(rs["verdict"]) == "PASS" and rs["task_gates_pass"])
    # exact boundary on my predicate and the candidate's: −1 of 36 passes, −2 fails
    one = _rows(72, even[:1], [])
    two = _rows(72, even[:2], [])
    assert _verdict(1, *one, tasks=tasks)["task_gates"][0]["pass"] is True
    assert _verdict(1, *two, tasks=tasks)["task_gates"][0]["pass"] is False
    assert task_gates_ok([[(-1 if i in set(even[:1]) else 0)] for i in range(72)]) is True
    assert task_gates_ok([[(-1 if i in set(even[:2]) else 0)] for i in range(72)]) is False


def test_task_gates_default_to_none_and_tasks_must_cover_every_item():  # (a)
    res = _verdict(1, *_bc_rows(72, 0, 0))
    assert res["task_gates"] is None and res["task_gates_pass"] is None and res["clean"] is None
    with pytest.raises(ValueError):
        _verdict(1, *_bc_rows(72, 0, 0), tasks={i: i % 2 for i in range(70)})


def test_tasks_and_languages_are_refused_on_the_wrong_axis():  # (a)
    from bench import m76_rule as R
    a, b = _bc_rows(72, 0, 0)
    with pytest.raises(ValueError):
        R.axis_verdict("A1", 1, a, b, tasks={i: 0 for i in range(72)})
    with pytest.raises(ValueError):
        R.axis_verdict("A5", 1, a, b, languages={i: 0 for i in range(72)})


# ----------------------------------------------------------------------- verdict_a5's default output unchanged (b)
def test_verdict_a5_default_alpha_and_semantics_are_unchanged():  # (a)+(b)
    """Default α is 0.025 and, over a grid of (b, c) at n 42 and 72, the verdict equals the B7 rule rebuilt from `stats`
    alone: PASS ⇔ delta ≥ −5 pp ∧ `exact_paired_loss` rejects at 0.025; LOSS ⇔ delta < −5 pp ∧ b > c ∧ exact binomial
    ≤ 0.05; else UNDECIDED. `verdict_a5(b, c, n)` ≡ `verdict_a5(b, c, n, alpha=0.025)`."""
    from bench import m76_rule as R
    from bench import stats
    assert inspect.signature(R.verdict_a5).parameters["alpha"].default == 0.025
    cases = [(42, b, c) for b, c in ((0, 0), (1, 0), (0, 3), (2, 2), (6, 1), (9, 2))] + \
            [(72, b, c) for b, c in ((0, 0), (1, 1), (3, 2), (5, 1), (8, 3), (12, 2), (15, 0))]
    for n, b, c in cases:
        r = stats.exact_paired_loss(b, c, n, margin=0.10, alpha=0.025)
        delta = (c - b) / n
        if delta >= -0.05 - 1e-12 and r["reject"]:
            want = "PASS"
        elif delta < -0.05 and b > c and stats.mcnemar_exact(b, c) <= 0.05:
            want = "LOSS"
        else:
            want = "UNDECIDED"
        v = R.verdict_a5(b, c, n)
        assert str(v.verdict) == want and v.bound == pytest.approx(r["bound"]), (n, b, c, v.verdict, want)
        assert R.verdict_a5(b, c, n).as_dict() == R.verdict_a5(b, c, n, alpha=0.025).as_dict()


# ------------------------------------------------------------------------------------------------- HOLD (a)/(b)
def test_a8_hold_constant_and_boundaries():  # (a)
    """Any language's decider point estimate < −20 pp → HOLD (blocking); −20 pp exactly does not fire."""
    from bench import m76_rule as R
    assert R.A8_HOLD_PP == -0.20
    assert R.a8_hold({"rust": Fraction(-1, 5)})["hold"] is False                 # exactly −20 pp
    assert R.a8_hold({"rust": -8 / 40})["hold"] is False                          # −8 of 40 = −0.2 as a float
    assert R.a8_hold({"rust": 0.2 * -1})["hold"] is False
    assert R.a8_hold({"rust": Fraction(-9, 40)})["hold"] is True                  # −22.5 pp
    assert R.a8_hold({"rust": -0.2000001})["hold"] is True
    assert R.a8_hold({"rust": -0.19, "java": 0.0})["hold"] is False
    r = R.a8_hold({"rust": -0.1, "java": -0.3, "cpp": -0.25, "js": 0.0})
    assert r["hold"] is True and r["blocking"] is True and r["languages"] == ["cpp", "java"]
    assert R.a8_hold({"x": {"delta": -0.21}})["hold"] is True                     # dict form
    with pytest.raises(ValueError):
        R.a8_hold({})


def test_a8_hold_agrees_with_the_simulations_integer_rule():  # (b)
    """On the decider's integer scale (a language's Σ d over 20 items × 2 sessions = 40 outcomes) the registered `a8_hold`
    and the simulation's `hold_fires` agree for every sum; −8 (exactly −20 pp) does not fire, −9 does."""
    from bench import m76_rule as R
    from bench import m76_sim as M
    for s in range(-40, 6):
        assert R.a8_hold({"x": Fraction(s, 40)})["hold"] == M.hold_fires(s, -20) == (100 * s < -20 * 40), s
    assert M.hold_fires(-9, -20) and not M.hold_fires(-8, -20)
    assert M.HOLD_THRESHOLDS[-1] == ("lt20", -20) or ("lt20", -20) in M.HOLD_THRESHOLDS


def _a8_rows(loss_in_first_language):
    """80 items (4 languages × 20), 2 sessions; X fails `loss_in_first_language` of the first language's 40 item-sessions."""
    b = {i: {"s1": 1, "s2": 1} for i in range(80)}
    a = {i: {"s1": 1, "s2": 1} for i in range(80)}
    k = 0
    for i in range(20):
        for s in ("s1", "s2"):
            if k < loss_in_first_language:
                a[i][s] = 0
                k += 1
    return a, b, {i: i // 20 for i in range(80)}


@pytest.mark.parametrize("losses,fires", [(0, False), (7, False), (8, False), (9, True), (14, True)])
def test_axis_verdict_a8_reports_the_hold_from_per_language_rows(losses, fires):  # (a)+(b)
    """The decider's per-language point = Σ d / (20 items × 2 sessions): 8 of 40 = −20 pp exactly does not fire, 9 does; a
    firing HOLD is blocking and is listed with its language."""
    from bench import m76_rule as R
    a, b, lang = _a8_rows(losses)
    res = R.axis_verdict("A8", 1, a, b, languages=lang, interaction_iters=200)
    assert res["hold"]["hold"] is fires and res["hold"]["languages"] == ([0] if fires else [])
    assert res["blocking"] is (fires or res["interaction_flag"])
    none = R.axis_verdict("A8", 1, a, b, interaction_iters=200)
    assert none["hold"] is None


# ------------------------------------------------------------------------------- B7 unchanged outside the plan (a)
def test_other_axis_plans_are_untouched_by_the_registration():  # (a)
    from bench import m76_rule as R
    assert [lk["alpha"] for lk in R.axis_plan("A8")["looks"]] == [0.001]
    assert [lk["alpha"] for lk in R.axis_plan("A7")["looks"]] == [0.001]
    assert [(lk["size"], round(lk["alpha"], 6)) for lk in R.axis_plan("A1")["looks"]] == [(100, 0.000104), (300, 0.024896)]
