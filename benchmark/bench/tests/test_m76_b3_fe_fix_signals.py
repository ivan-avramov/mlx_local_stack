"""Delivery 3: erratum-v1.2 items 2, 3 (convergence), 5 (flags): the kv sheet's verdicts come from the REAL `bench.m76_rule.axis_verdict`
(spied, never replaced), the A5 strict score uses the row's own resolved budget, size warnings / gates / interaction block. Class (c)."""
from __future__ import annotations

import pytest

from bench import m76_rule, p426_signals as S


@pytest.fixture
def spy(monkeypatch):
    calls = []
    real = m76_rule.axis_verdict

    def wrapper(axis, look, a, b, **kw):
        out = real(axis, look, a, b, **kw)
        calls.append((axis, look, len(a), out))
        return out

    monkeypatch.setattr(m76_rule, "axis_verdict", wrapper)
    return calls


def sess(ids, f, sessions=("s1",)):
    return {i: {s: int(f(i, s)) for s in sessions} for i in ids}


# ----------------------------------------------------------------------------------------------- item 2
def test_a1_asks_b7_at_every_planned_look_it_can_read(spy):
    plan = m76_rule.axis_plan("A1")["looks"]
    order = [f"q{i:03d}" for i in range(plan[-1]["size"])]
    ref = {i: 1 for i in order}
    out = S.kv_a1(dict(ref), ref, order)
    assert [c[:2] for c in spy] == [("A1", lk["look"]) for lk in plan]
    assert [lk["verdict"] for lk in out["looks"]] == [c[3]["verdict"] for c in spy]
    assert out["final_look"] == 1                                              # look 1 decides when PASS / LOSS
    assert all("descriptive" in lk for lk in out["looks"])


def test_a1_a_look_whose_items_are_not_all_accepted_is_pending_not_verdicted(spy):
    plan = m76_rule.axis_plan("A1")["looks"]
    order = [f"q{i:03d}" for i in range(plan[-1]["size"])]
    half = {i: 1 for i in order[: plan[0]["size"]]}
    out = S.kv_a1(dict(half), dict(half), order)
    assert [c[1] for c in spy] == [1]
    assert out["looks"][1]["status"].startswith("pending") and "verdict" not in out["looks"][1]


def test_a1_undecided_at_look_1_decides_at_look_2(monkeypatch):
    plan = m76_rule.axis_plan("A1")["looks"]
    order = [f"q{i:03d}" for i in range(plan[-1]["size"])]
    verdicts = {1: "UNDECIDED", 2: "PASS"}
    real = m76_rule.axis_verdict

    def fake(axis, look, a, b, **kw):
        r = dict(real(axis, look, a, b, **kw))
        r["verdict"] = verdicts[look]
        return r

    monkeypatch.setattr(m76_rule, "axis_verdict", fake)
    ref = {i: 1 for i in order}
    assert S.kv_a1(dict(ref), ref, order)["final_look"] == 2


def test_a5_goes_through_axis_verdict_to_verdict_a5_with_the_exact_counts(spy):
    ref, test = {}, {}
    n = m76_rule.axis_plan("A5")["looks"][0]["size"]      # AMENDED (delivery 5, v1.4): the look's size is the plan's, not 48
    for k in range(n):
        iid = f"it{k:02d}"
        task = "retrieval" if k % 2 else "reasoning"
        row = dict(task=task, rung=131072, hits=[True] * 5, score=1.0, finish_reason="stop", completion_tokens=100,
                   resolved_max_tokens=50000, resolved_thinking_budget=40000)
        ref[iid] = dict(row)
        test[iid] = dict(row, hits=[True] * 4 + [False], score=0.0) if k < 3 else dict(row)      # 3 items lost
    out = S.kv_a5(ref, test)
    assert [c[:2] for c in spy][0] == ("A5", 1) and spy[0][2] == n
    direct = m76_rule.verdict_a5(3, 0, n, alpha=m76_rule.axis_plan("A5")["looks"][0]["alpha"])
    assert out["verdict"]["verdict"] == direct["verdict"] == spy[0][3]["verdict"]
    assert out["n"] == n and sum(out["strict"]["ref"].values()) == n and sum(out["strict"]["test"].values()) == n - 3


def test_a7_asks_b7_at_the_plans_final_look_over_every_planned_session(spy):
    plan = m76_rule.axis_plan("A7")["looks"][-1]
    sessions = tuple(f"s{i}" for i in range(1, plan["size"] + 1))
    items = [f"c{i:02d}" for i in range(40)]
    ref = sess(items, lambda i, s: 1, sessions)
    out = S.kv_a7(dict(ref), ref, "n16")
    assert [c[:2] for c in spy] == [("A7", plan["look"])]
    assert out["verdict"] == spy[0][3]["verdict"] and "descriptive" in out
    assert set(out["noise_floor"]["n16_within"]) == {f"{a}-{b}" for a in sessions for b in sessions if a < b}


def test_a7_b7_refuses_mismatched_sessions_and_the_sheet_refuses_with_it():
    ref = sess(["a", "b"], lambda i, s: 1, ("s1", "s2"))
    test = sess(["a", "b"], lambda i, s: 1, ("s1",))
    with pytest.raises(S.RefusalError):
        S.kv_a7(test, ref, "n16")


def test_size_warnings_and_loss_and_interaction_are_blocking_flags():
    a7 = dict(look=1, verdict="LOSS", delta=-0.2, label="L", size_warnings=["n too small"], interaction_flag=True,
              interaction=dict(pvalue=0.01))
    flags = S.kv_flags({"header": {"label": "X − N16"}, "axes": {"A7": a7}})
    kinds = {f["flag"] for f in flags}
    assert {"size_warning", "loss", "session_interaction"} <= kinds and all(f["blocking"] for f in flags)


def test_undecided_blocks_and_a_clean_pass_raises_nothing():
    und = dict(look=1, verdict="UNDECIDED", loss_bound=0.12, label="u")
    assert {f["flag"] for f in S.kv_flags({"header": {"label": "X − N16"}, "axes": {"A7": und}})} == {"undecided"}
    ok = dict(look=1, verdict="PASS", delta=0.0, label="p", size_warnings=[], interaction_flag=False)
    assert S.kv_flags({"header": {"label": "X − N16"}, "axes": {"A7": ok}}) == []


def test_an_a5_gate_below_085_or_minus_5pp_blocks():
    gates = {"retrieval": dict(n=8, acc=dict(ref=0.9, test=0.8), point_pp=-10.0, **{"pass": False}),
             "reasoning": dict(n=8, acc=dict(ref=0.9, test=0.9), point_pp=0.0, **{"pass": True})}
    flags = S.kv_flags({"header": {"label": "X − N16"}, "axes": {"A5": {"gates": gates}}})
    assert [f["member"] for f in flags if f["flag"] == "a5_gate"] == ["A5-retrieval"]


# ----------------------------------------------------------------------------------------------- item 3: convergence
def test_a5_strict_converges_at_the_rows_own_resolved_budget_not_a_constant():
    base = dict(task="retrieval", hits=[True] * 5, finish_reason="stop", resolved_thinking_budget=70000)
    # the same 65,100-token completion converges under a 65,536 cap and not under a 65,024 cap
    assert S.a5_strict(dict(base, completion_tokens=65100, resolved_max_tokens=65536)) == 1
    assert S.a5_strict(dict(base, completion_tokens=65100, resolved_max_tokens=65024)) == 0
    assert S.a5_strict(dict(base, completion_tokens=100, resolved_max_tokens=65024)) == 1


def test_a5_strict_needs_all_five_codes_converged_and_a_resolved_budget():
    ok = dict(task="retrieval", hits=[True] * 5, finish_reason="stop", completion_tokens=10, resolved_max_tokens=1000,
              resolved_thinking_budget=900)
    assert S.a5_strict(ok) == 1
    assert S.a5_strict(dict(ok, hits=[True] * 4 + [False])) == 0
    assert S.a5_strict(dict(ok, hits=[True] * 4)) == 0
    assert S.a5_strict(dict(ok, finish_reason="length")) == 0
    assert S.a5_strict(dict(ok, completion_tokens=900)) == 0                       # at the thinking budget
    assert S.a5_strict({k: v for k, v in ok.items() if k != "resolved_max_tokens"}) == 0
    assert S.a5_strict("not a row") == 0


def test_a5_strict_chain4_needs_exact_and_converged():
    ok = dict(task="reasoning", score=1.0, finish_reason="stop", completion_tokens=10, resolved_max_tokens=1000,
              resolved_thinking_budget=900)
    assert S.a5_strict(ok) == 1
    assert S.a5_strict(dict(ok, score=0.5)) == 0 and S.a5_strict(dict(ok, finish_reason="length")) == 0
