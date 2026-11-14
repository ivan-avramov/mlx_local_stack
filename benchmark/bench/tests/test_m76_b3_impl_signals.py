"""M76 B3 (B6-style signals under `lever=kv`), spec v1.2: every mechanical verdict is B7's final entry point
`bench.m76_rule.axis_verdict(axis, look, a, b)` — the REAL B7 module of this copy (no shim) — kept with its α, bound, verdict,
per-session results, interaction flag and `size_warnings` (each a blocking flag); `paired_delta` / `paired_session_delta` are
descriptive columns only; A5 strict scoring uses each row's own resolved budget; decode is P426's T2 estimator."""
from __future__ import annotations

import sys

import pytest

from bench import m76_rule
from bench import p426_signals as S


@pytest.fixture
def spy(monkeypatch):
    """Records every `axis_verdict` call and returns B7's real result (a spy, never a stand-in)."""
    calls = []
    real = m76_rule.axis_verdict

    def axis_verdict(axis, look, a, b, **kw):
        calls.append((axis, look, len(a)))
        return real(axis, look, a, b, **kw)
    monkeypatch.setattr(m76_rule, "axis_verdict", axis_verdict)
    return calls


def _single(m):
    return {i: {"s1": int(v)} for i, v in m.items()}


def test_without_b7_the_kv_sheet_refuses(monkeypatch):
    import bench

    monkeypatch.setitem(sys.modules, "bench.m76_rule", None)
    monkeypatch.delattr(bench, "m76_rule", raising=False)
    with pytest.raises(S.RefusalError, match="m76_rule"):
        S.kv_b7()


# ------------------------------------------------------------------------------------------------------------ A1
ORDER = [f"i{k:03d}" for k in range(300)]


def test_a1_every_look_is_axis_verdict(spy):
    ref = {i: 1 for i in ORDER}
    test = dict(ref, **{i: 0 for i in ORDER[::50]})
    rec = S.kv_a1(test, ref, ORDER)
    assert spy == [("A1", 1, 100), ("A1", 2, 300)]
    for lk, plan in zip(rec["looks"], m76_rule.axis_plan("A1")["looks"]):
        n = plan["size"]
        want = m76_rule.axis_verdict("A1", plan["look"], _single({i: test[i] for i in ORDER[:n]}),
                                     _single({i: ref[i] for i in ORDER[:n]}))
        for k in ("verdict", "alpha", "loss_bound", "lo", "hi", "delta", "label", "size_warnings"):
            assert lk[k] == want[k], k
        assert lk["descriptive"]["statistic"].startswith("paired_delta")
        assert lk["size_warnings"] == []


def test_a1_tier1_only_leaves_look_2_pending_and_decides_at_look_1_when_it_can():
    ref = {i: 1 for i in ORDER[:100]}
    rec = S.kv_a1(dict(ref), ref, ORDER)
    assert rec["looks"][0]["verdict"] == "PASS" and rec["looks"][1]["status"].startswith("pending")
    assert rec["final_look"] == 1


def test_a1_undecided_at_look_1_decides_at_look_2():
    ref = {i: 1 for i in ORDER}
    test = dict(ref, **{i: 0 for i in ORDER[:4]})                         # 4 losses in tier 1: undecided at α 0.0001
    rec = S.kv_a1(test, ref, ORDER)
    assert rec["looks"][0]["verdict"] == "UNDECIDED"
    assert rec["final_look"] == 2 and rec["looks"][1]["verdict"] == m76_rule.axis_verdict(
        "A1", 2, _single(test), _single(ref))["verdict"]


# ------------------------------------------------------------------------------------------------------------ A5
def _a5_rows(n_per=7, fail=()):
    rows = {}
    for task in ("retrieval", "reasoning"):
        for rung in (131072, 159744, 196608):
            for k in range(n_per):
                iid = f"{task}-{rung}-{k:02d}"
                ok = iid not in fail
                prompt = rung + 300
                cap = min(102400, 262144 - prompt)
                row = dict(prompt_tokens=prompt, resolved_max_tokens=cap, resolved_thinking_budget=min(81920, int(cap * 0.8)),
                           thinking_budget=81920, finish_reason="stop", completion_tokens=100)
                row.update(dict(hits=[True] * 5 if ok else [True] * 4 + [False]) if task == "retrieval" else
                           dict(score=1.0 if ok else 0.0, budget_hit=False))
                rows[iid] = dict(row, task=task, rung=rung)
    return rows


def test_a5_is_axis_verdict_via_verdict_a5(spy):
    ref = _a5_rows(n_per=12)
    test = _a5_rows(n_per=12, fail=("retrieval-196608-00", "retrieval-196608-01"))
    sig = S.kv_a5(ref, test)
    assert spy == [("A5", 1, 72)]
    v = sig["verdict"]
    plan1 = m76_rule.axis_plan("A5")["looks"][0]
    assert plan1["size"] == 72
    want = m76_rule.verdict_a5(2, 0, 72, alpha=plan1["alpha"])              # the plan's look-1 α, never the default
    assert (v["verdict"], v["loss_bound"], v["a5"]["b"], v["a5"]["c"]) == (want.verdict, want.bound, 2, 0)
    assert v["alpha"] == plan1["alpha"] and sig["final_look"] == 1
    assert v["size_warnings"] == []                                         # n = B7's planned 72
    g = sig["gates"]
    assert g["retrieval"]["acc"] == {"ref": 1.0, "test": pytest.approx(34 / 36)} and g["reasoning"]["pass"] is True
    assert sig["per_cell"]["retrieval|196608"]["delta_pp"] == pytest.approx(-100 * 2 / 12)


def test_a5_undecided_at_look_1_decides_at_look_2_on_the_cumulative_120(spy):
    """The real B7.1 two-look plan: look 1 (tier 1, 72) UNDECIDED at its α → look 2 on tier 1 + tier 2 (cumulative 120)."""
    plan = m76_rule.axis_plan("A5")["looks"]
    assert [lk["size"] for lk in plan] == [72, 120]
    ref = _a5_rows(n_per=20)
    fail = ("retrieval-196608-00", "retrieval-196608-01")                  # both in tier 1
    test = _a5_rows(n_per=20, fail=fail)
    cells = [(t, r) for t in ("retrieval", "reasoning") for r in (131072, 159744, 196608)]
    order = ([f"{t}-{r}-{k:02d}" for t, r in cells for k in range(12)]
             + [f"{t}-{r}-{k:02d}" for t, r in cells for k in range(12, 20)])
    sig = S.kv_a5(ref, test, order=order, tiers=[72, 120])
    assert spy == [("A5", 1, 72), ("A5", 2, 120)]
    assert "tier_mismatch" not in sig
    l1, l2 = sig["looks"]
    w1 = m76_rule.verdict_a5(2, 0, 72, alpha=plan[0]["alpha"])
    w2 = m76_rule.verdict_a5(2, 0, 120, alpha=plan[1]["alpha"])
    assert w1.verdict == "UNDECIDED" and w2.verdict in ("PASS", "LOSS")   # the fixture exercises the two-look path
    assert (l1["verdict"], l1["loss_bound"], l1["alpha"], l1["n_items"]) == (w1.verdict, w1.bound, plan[0]["alpha"], 72)
    assert (l2["verdict"], l2["loss_bound"], l2["alpha"], l2["n_items"]) == (w2.verdict, w2.bound, plan[1]["alpha"], 120)
    assert (l2["a5"]["b"], l2["a5"]["c"]) == (2, 0) and l2["size_warnings"] == []
    assert sig["final_look"] == 2 and sig["n"] == 120 and sig["verdict"] == l2
    g = sig["gates"]
    assert g["retrieval"]["n"] == 60 and g["retrieval"]["acc"] == {"ref": 1.0, "test": pytest.approx(58 / 60)}
    assert g["reasoning"]["pass"] is True
    assert sig["per_cell"]["retrieval|196608"]["n"] == 20
    assert sig["per_cell"]["retrieval|196608"]["delta_pp"] == pytest.approx(-100 * 2 / 20)


def test_a5_off_plan_size_is_a_blocking_warning():
    sig = S.kv_a5(_a5_rows(), _a5_rows(), tiers=[42])                       # 42 items (ids' tier 1); the plan is 72
    assert sig["verdict"]["size_warnings"] == ["42 items, plan look 1 expects 72"]
    flags = S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A5=sig, A1={}, A7={})))
    assert any(f["flag"] == "size_warning" and f["member"] == "A5" and f["blocking"] for f in flags)


def test_a5_strict_uses_the_rows_own_resolved_budget():
    """v1.2: converged = stop AND below the row's resolved max_tokens AND its resolved thinking budget (never the declared
    81,920 / `budget_hit`, never a per-rung planner constant)."""
    base = dict(task="retrieval", rung=196608, prompt_tokens=196000, hits=[True] * 5, finish_reason="stop", thinking_budget=81920,
                resolved_max_tokens=66144, resolved_thinking_budget=52915)
    assert S.a5_strict(dict(base, completion_tokens=52000)) == 1
    assert S.a5_strict(dict(base, completion_tokens=53000)) == 0             # forced close at the row's thinking budget
    assert S.a5_strict(dict(base, completion_tokens=5, finish_reason="length")) == 0
    assert S.a5_strict(dict(base, completion_tokens=5, hits=[True] * 4 + [False])) == 0
    chain = dict(base, task="reasoning", score=1.0, budget_hit=False)
    del chain["hits"]
    assert S.a5_strict(dict(chain, completion_tokens=52000)) == 1
    assert S.a5_strict(dict(chain, completion_tokens=60000)) == 0           # `budget_hit` (declared 81,920) says False
    assert S.a5_strict(dict(chain, completion_tokens=100, resolved_max_tokens=None)) == 0     # no resolved budget: not scored
    assert S.a5_strict(None) == 0


def test_a5_gate_needs_each_arm_at_0_85():
    ref = _a5_rows(fail=tuple(f"reasoning-131072-{k:02d}" for k in range(4)))       # ref reasoning 17/21 = 0.81
    sig = S.kv_a5(ref, ref, tiers=[42])
    assert sig["gates"]["reasoning"]["pass"] is False and sig["gates"]["retrieval"]["pass"] is True


# ------------------------------------------------------------------------------------------------------------ A7
def _a7(n=43, fail_test=(), fail_ref=()):
    sessions = ("s1", "s2", "s3")
    ref = {f"py/{k}": {s: int((k, s) not in fail_ref) for s in sessions} for k in range(n)}
    test = {f"py/{k}": {s: int((k, s) not in fail_test) for s in sessions} for k in range(n)}
    return test, ref


def test_a7_is_axis_verdict_at_the_plans_final_look(spy):
    test, ref = _a7(fail_test=[(k, "s2") for k in range(0, 43, 7)], fail_ref=[(k, "s1") for k in range(0, 43, 9)])
    rec = S.kv_a7(test, ref, ref_arm="n16")
    assert spy == [("A7", 1, 43)]
    want = m76_rule.axis_verdict("A7", 1, test, ref)
    for k in ("verdict", "alpha", "loss_bound", "lo", "hi", "per_session", "interaction_flag", "size_warnings"):
        assert rec[k] == S._jsonable(want[k]), k
    assert rec["alpha"] == 0.001 and rec["interaction"]["pvalue"] == want["interaction"]["pvalue"]
    assert rec["descriptive"]["statistic"].startswith("paired_session_delta")
    nf = rec["noise_floor"]["n16_within"]
    assert set(nf) == {"s1-s2", "s1-s3", "s2-s3"} and nf["s1-s2"]["discordant"] == len(range(0, 43, 9))


def test_a7_interaction_flag_blocks():
    test, ref = _a7(fail_test=[(k, "s1") for k in range(20)])            # every loss in one session
    rec = S.kv_a7(test, ref, ref_arm="n16")
    assert rec["interaction_flag"] is True
    flags = S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A7=rec, A1={}, A5={})))
    assert any(f["flag"] == "session_interaction" and f["blocking"] for f in flags)


def test_a7_noise_floor_only_for_the_incumbent():
    test, ref = _a7(n=10)
    assert "noise_floor" not in S.kv_a7(test, ref, ref_arm="x")


# ------------------------------------------------------------------------------------------------------------ panel
def test_the_holm_panel_family_and_flags():
    members = {"A1": dict(judged=12, vector=[-0.5] * 12, mean=0.0), "A2": dict(judged=40, vector=[0.0] * 40, mean=0.5),
               "A5": dict(judged=3, vector=[0.5] * 3, mean=1.0), "A7-s3": dict(judged=6, vector=[0.0] * 6, mean=0.5,
                                                                           single_family=dict(label="operator ok"))}
    panel = S.kv_panel_family(members)
    assert panel["family"] == ["A1", "A2", "A5", "A7-s3"] and panel["tested"] == ["A1", "A2", "A7-s3"]
    assert panel["members"]["A1"]["holm_p"] < 0.05
    flags = S.kv_panel_flags(panel)
    assert any(f["flag"] == "panel_holm_reference_better" and f["member"] == "A1" for f in flags)
    assert any(f["flag"] == "panel_single_family" and f["member"] == "A7-s3" for f in flags)


# ------------------------------------------------------------------------------------------------------------ end to end
def test_compute_kv_on_the_verified_world(tmp_path, monkeypatch, spy):
    from bench import p426_verify as V
    from bench.tests.test_m76_b3_impl_verify import World

    w = World(tmp_path, monkeypatch)
    lc = w.ids["axes"]["longctx"]
    fail = [i for i in lc["block1"] if i.startswith("retrieval-")][:1]
    w.leg("longctx", "x", "b1", row_hook=lambda r: dict(r, hits=[True] * 4 + [False]) if r["content"].endswith(fail[0]) else r)
    b8 = V.verify_all_kv(w.rows, w.repo, ("n16", "x"), kinds=("cjudge", "longctx"))
    sig = S.compute_kv(w.rows, b8)
    assert ("A5", 1, 42) in spy
    a5 = sig["axes"]["A5"]["verdict"]
    assert (a5["a5"]["b"], a5["a5"]["c"]) == (1, 0) and a5["verdict"] == m76_rule.verdict_a5(1, 0, 42).verdict
    assert any(f["flag"] == "size_warning" for f in sig["flags"])          # 42 A5 items vs B7's 72: blocking
    assert all(f["blocking"] for f in sig["flags"])
    assert all("verdict" not in lk for lk in sig["axes"]["A1"]["looks"])    # no Math500 pair: pending, never verdicted
    assert sig["axes"]["A7"] == {"status": "pending (no Wave 2 record)"}
    assert set(sig["decode"]) == {"cjudge", "longctx"}
    dec = sig["decode"]["cjudge"]
    assert dec["estimator"].startswith("P426 T2") and dec["arms"] == {"off": "n16", "on": "x"}
    assert dec["both"]["n"] == len(w.ids["axes"]["cjudge"]["block1"]) + len(w.ids["axes"]["cjudge"]["block2"])
    assert dec["both"]["geomean_ratio"] == pytest.approx(25.0 / 30.0)       # per-key treatment / reference decode_tps
    assert sig["header"]["label"] == "X − N16" and sig["coverage"]["accepted"]
    again = S.compute_kv(w.rows, b8)
    assert S.render_kv(sig) == S.render_kv(again)
    md = S.render_kv(sig)
    assert "## A5 long context (X − N16" in md and "axis_verdict" in md and "SIZE WARNINGS" in md
    (w.rows / "m76" / "ids.json").write_text((w.rows / "m76" / "ids.json").read_text() + " ")
    with pytest.raises(S.RefusalError, match="changed"):
        S.compute_kv(w.rows, b8)


# ------------------------------------------------------------------------------------- A5 two looks (spec v1.4, B7.1 stand-in)
A5_LOOKS = ((72, 0.003808), (120, 0.021192))       # B7.1 v1.4 (`docs/specs/m76-b7-1-joint-plan.md`): looks n 72 / 120


@pytest.fixture
def two_look_plan(monkeypatch):
    """A stand-in for B7.1's two-look `axis_plan("A5")`, in the TEST only; B7's real `axis_verdict` / `verdict_a5` read it."""
    real = m76_rule.axis_plan

    def axis_plan(axis, **kw):
        if axis != "A5":
            return real(axis, **kw)
        return dict(axis="A5", looks=[dict(look=k + 1, size=n, unit="items", alpha=a, exact_alpha=a)
                                      for k, (n, a) in enumerate(A5_LOOKS)], sessions=1, items=120, report_sha256="e" * 64)
    monkeypatch.setattr(m76_rule, "axis_plan", axis_plan)


def _a5_order(n_tier1=12, n_tier2=8):
    cells = [(t, r) for t in ("retrieval", "reasoning") for r in (131072, 159744, 196608)]
    return ([f"{t}-{r}-{k:02d}" for t, r in cells for k in range(n_tier1)]
            + [f"{t}-{r}-{k:02d}" for t, r in cells for k in range(n_tier1, n_tier1 + n_tier2)])


def test_a5_look1_undecided_decides_at_look2_on_tier1_plus_tier2(two_look_plan, spy):
    ref = _a5_rows(n_per=20)
    test = _a5_rows(n_per=20, fail=("retrieval-196608-00",))                # b 1: UNDECIDED at 72 / α 0.003808
    sig = S.kv_a5(ref, test, order=_a5_order(), tiers=[72, 120])
    assert spy == [("A5", 1, 72), ("A5", 2, 120)]
    l1, l2 = sig["looks"]
    assert l1["verdict"] == m76_rule.verdict_a5(1, 0, 72, alpha=0.003808).verdict == "UNDECIDED" and l1["alpha"] == 0.003808
    assert l2["verdict"] == m76_rule.verdict_a5(1, 0, 120, alpha=0.021192).verdict == "PASS" and l2["alpha"] == 0.021192
    assert l1["size_warnings"] == l2["size_warnings"] == []
    assert sig["final_look"] == 2 and sig["verdict"] is l2 and sig["n"] == 120
    assert sig["gates"]["retrieval"]["n"] == 60 and sig["gates"]["retrieval"]["acc"]["test"] == pytest.approx(59 / 60)
    assert sig["per_cell"]["retrieval|196608"]["n"] == 20                   # the table at the deciding look
    assert "tier_mismatch" not in sig
    flags = S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A5=sig, A1={}, A7={})))
    assert not [f for f in flags if f["member"].startswith("A5")]


def test_a5_look1_loss_stops(two_look_plan, spy):
    ref = _a5_rows(n_per=20)
    test = _a5_rows(n_per=20, fail=tuple(f"reasoning-131072-{k:02d}" for k in range(6)))   # b 6: LOSS at look 1
    sig = S.kv_a5(ref, test, order=_a5_order(), tiers=[72, 120])            # tier-2 rows present: look 2 still not taken
    assert spy == [("A5", 1, 72)]
    assert sig["looks"][0]["verdict"] == "LOSS" and "not taken" in sig["looks"][1]["status"] and "verdict" not in sig["looks"][1]
    assert sig["final_look"] == 1 and sig["n"] == 72 and sig["gates"]["reasoning"]["n"] == 36
    flags = S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A5=sig, A1={}, A7={})))
    assert any(f["flag"] == "loss" and f["member"] == "A5" for f in flags)


def test_a5_look1_pass_stops(two_look_plan, spy):
    rows = _a5_rows(n_per=20)
    sig = S.kv_a5(rows, rows, order=_a5_order(), tiers=[72, 120])
    assert spy == [("A5", 1, 72)] and sig["looks"][0]["verdict"] == "PASS" and sig["final_look"] == 1
    assert "not taken" in sig["looks"][1]["status"]


def test_a5_undecided_without_tier2_is_pending_and_blocks(two_look_plan, spy):
    ref = _a5_rows(n_per=12)
    test = _a5_rows(n_per=12, fail=("retrieval-196608-00",))
    sig = S.kv_a5(ref, test, order=_a5_order(n_tier2=0) + _a5_order()[72:], tiers=[72, 120])   # tier 2 not run (no rows)
    assert spy == [("A5", 1, 72)]
    assert sig["looks"][0]["verdict"] == "UNDECIDED" and sig["looks"][1]["status"].startswith("pending")
    assert sig["final_look"] == 1
    flags = S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A5=sig, A1={}, A7={})))
    assert any(f["flag"] == "undecided" and f["member"] == "A5" and f["blocking"] for f in flags)


def test_a5_sizes_are_the_plans_never_constants(two_look_plan, spy, monkeypatch):
    """The look sizes and α come from `axis_plan("A5")`: another plan, other looks."""
    monkeypatch.setattr(sys.modules[__name__], "A5_LOOKS", ((48, 0.004), (96, 0.02)))
    ref = _a5_rows(n_per=16)
    test = _a5_rows(n_per=16, fail=("retrieval-196608-00",))
    sig = S.kv_a5(ref, test, order=_a5_order(8, 8), tiers=[48, 96])
    assert spy == [("A5", 1, 48), ("A5", 2, 96)] and sig["looks"][0]["alpha"] == 0.004 and sig["looks"][1]["alpha"] == 0.02
    assert sig["looks"][0]["size_warnings"] == []


def test_a5_ids_tiers_not_the_plans_are_a_blocking_flag(two_look_plan, spy):
    rows = _a5_rows(n_per=12)
    sig = S.kv_a5(rows, rows, order=_a5_order(n_tier2=0), tiers=[72])     # ids built from a one-look plan
    assert sig["tier_mismatch"] and sig["looks"][0]["verdict"] == "PASS" and sig["looks"][1]["status"].startswith("not taken")
    flags = S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A5=sig, A1={}, A7={})))
    assert any(f["flag"] == "size_warning" and f["member"] == "A5" and f["blocking"] for f in flags)


def test_compute_kv_refuses_a_mtp_b8(tmp_path):
    with pytest.raises(S.RefusalError, match="lever-kv"):
        S.compute_kv(tmp_path, {"axes": {"A7": {}, "wave1": {}}})


def test_render_labels_and_no_p426():
    sig = S.kv_sheet_skeleton(("n16", "x"))
    md = S.render_kv(sig)
    assert md.startswith("# M76 signals — X − N16") and "p426s2" not in md
    assert S.kv_sheet_skeleton(("x", "v"))["header"]["label"] == "V − X"
    assert S.kv_sheet_skeleton(("n16", "v"))["header"]["label"] == "V − N16"
