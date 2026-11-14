"""Delivery 3: `m76_ids` with its real signature (synthetic Math500 universe and prompt counts, no tokenizer, no network) — Math500 300
nested + deterministic, A5 items / n, and erratum-v1.2 item 3 (frozen per-item prompt counts; resolved = min(deployed, 262,144 −
prompt); B8-side equality of the row's count). Class (c) unless marked."""
from __future__ import annotations

import json
import random

import pytest

from bench import m76_ids as M, p426_ids
from bench.tests import test_m76_b3_fe_surface as G

CAP = 262144
DEPLOYED_MAX = 81920


@pytest.fixture(scope="module")
def p426():
    return p426_ids.build(G.REPO)


@pytest.fixture(scope="module")
def universe(p426):
    old = p426["axes"]["math500"]["block1"] + p426["axes"]["math500"]["block2"]
    return sorted(set(old) | {f"syn-{i:04d}" for i in range(400)})


def counts(n, base=1000):
    items, smoke, *_ = M.longctx_items(n)
    return {i["id"]: i["rung"] + base + k % 7 for k, i in enumerate(items + smoke)}


def doc(universe, n=48, max_tokens=DEPLOYED_MAX, thinking=4096):
    return M.build(G.REPO, a5_sizes=(n,), universe=universe, max_tokens=max_tokens, thinking_budget=thinking, prompt_tokens=counts(n))


# ----------------------------------------------------------------------------------------------- Math500 300
def test_math500_300_nested_unique_and_p426s_blocks_kept(universe, p426):
    ax = doc(universe)["axes"]["math500"]
    old = p426["axes"]["math500"]
    assert len(ax["order"]) == 300 and len(set(ax["order"])) == 300
    assert ax["order"][:100] == sorted(old["block1"] + old["block2"]) and ax["tier1"] == ax["order"][:100]
    assert ax["block1"] == old["block1"] and ax["block2"] == old["block2"] and ax["smoke"] == old["smoke"]
    t2 = ax["tier2"]
    assert set(t2["block1"]) | set(t2["block2"]) == set(ax["order"][100:]) and not set(t2["block1"]) & set(t2["block2"])
    assert len(t2["block1"]) == len(t2["block2"]) == 100


def test_math500_extra_200_are_random_7601_over_the_remaining_ids(universe, p426):
    ax = doc(universe)["axes"]["math500"]
    old = set(p426["axes"]["math500"]["block1"] + p426["axes"]["math500"]["block2"])
    remaining = sorted(set(universe) - old)
    assert ax["order"][100:] == random.Random(7601).sample(remaining, 200)       # independent re-derivation of the draw


def test_math500_is_deterministic_and_refuses_a_short_or_foreign_universe(universe, p426):
    assert doc(universe) == doc(universe)
    with pytest.raises(ValueError):
        M.build(G.REPO, a5_sizes=(48,), universe=universe[:250], max_tokens=1, thinking_budget=1, prompt_tokens=counts(48))
    with pytest.raises(ValueError):                   # a universe that lacks P426's ids
        M.build(G.REPO, a5_sizes=(48,), universe=[f"syn-{i:04d}" for i in range(400)], max_tokens=1, thinking_budget=1,
                prompt_tokens=counts(48))


def test_p426_ids_are_untouched_by_the_m76_generator(universe):
    before = json.dumps(p426_ids.build(G.REPO), sort_keys=True)
    doc(universe)
    assert json.dumps(p426_ids.build(G.REPO), sort_keys=True) == before


# ----------------------------------------------------------------------------------------------- A5 items and n
@pytest.mark.parametrize("n", [42, 48, 60, 120])
def test_a5_cells_are_equal_and_seeds_unique(n, universe):
    lc = doc(universe, n)["axes"]["longctx"]
    items = lc["items"]
    assert len(items) == n == lc["n"]
    cells = {}
    for i in items:
        cells.setdefault((i["task"], i["rung"]), []).append(i)
    assert set(cells) == {(t, r) for t in ("retrieval", "reasoning") for r in (131072, 159744, 196608)}
    assert {len(v) for v in cells.values()} == {n // 6}
    assert len({i["task_seed"] for i in items}) == n and len({i["request_seed"] for i in items}) == n
    assert sorted(lc["block1"] + lc["block2"]) == sorted(i["id"] for i in items)
    assert abs(len(lc["block1"]) - len(lc["block2"])) <= 1


def test_a5_items_are_deterministic_from_seed_7605():
    a, b = M.longctx_items(48), M.longctx_items(48)
    assert a == b
    rng = random.Random(7605)
    first = a[0][0]
    assert first["task_seed"] in range(1, 2 ** 31)
    assert first["task_seed"] == rng.randrange(1, 2 ** 31)          # the draw order of the spec's seed 7605


@pytest.mark.parametrize("bad", [0, 6, 36, 40, 41, 43, 126, 132, -6, 48.0, True])
def test_a5_n_outside_the_contract_is_refused(bad, universe):
    with pytest.raises(ValueError):
        M.check_a5_n(bad)
    with pytest.raises(ValueError):
        M.longctx_items(bad)


# REMOVED (delivery 5, spec v1.4): test_a5_n_comes_from_b7s_report_or_a_flag_and_is_refused_when_neither_exists and
# test_main_refuses_a_bad_a5_n_and_writes_nothing — `a5_n_from` and `--a5-n` no longer exist; A5's sizes are B7's `axis_plan("A5")`
# looks. Superseded by test_m76_b3_fe_fix_v15.py::test_a5_sizes_come_from_the_plan.


# ----------------------------------------------------------------------------------------------- item 3: frozen budgets
# (a) the v1 constant 512 / 65,536 is gone: the budget is the item's own prompt count
@pytest.mark.parametrize("prompt", [131_900, 160_001, 196_700, 197_100])
def test_item_budget_is_min_deployed_and_the_rest_of_the_window(prompt):
    b = M.item_budget(prompt, DEPLOYED_MAX, 4096)
    assert b["prompt_tokens"] == prompt
    assert b["resolved_max_tokens"] == min(DEPLOYED_MAX, CAP - prompt)
    assert b["total"] == prompt + b["resolved_max_tokens"] <= CAP
    if CAP - prompt < DEPLOYED_MAX:
        assert b["resolved_max_tokens"] == CAP - prompt and b["resolved_max_tokens"] != 65536 - 512
    assert b["resolved_thinking_budget"] <= 4096


def test_two_items_of_one_rung_with_different_prompts_resolve_differently():
    assert M.item_budget(196_700, DEPLOYED_MAX)["resolved_max_tokens"] != M.item_budget(196_900, DEPLOYED_MAX)["resolved_max_tokens"]


def test_item_budget_refuses_nothing_left_and_bad_counts():
    for bad in (CAP, CAP + 5, 0, -1, "9", True, None):
        with pytest.raises(ValueError):
            M.item_budget(bad, DEPLOYED_MAX)


def test_the_record_freezes_every_items_count_and_budget(universe):
    lc = doc(universe)["axes"]["longctx"]
    pc = counts(48)
    for i in lc["items"] + lc["smoke_items"]:
        b = lc["budget"][i["id"]]
        assert b["prompt_tokens"] == pc[i["id"]] and b["resolved_max_tokens"] == min(DEPLOYED_MAX, CAP - pc[i["id"]])
    assert M.budget_problems(lc) == []
    assert lc["budget_inputs"]["prompt_tokens"] == dict(sorted(pc.items()))


def test_an_item_without_a_frozen_count_refuses_the_build(universe):
    pc = counts(48)
    pc.pop(next(iter(pc)))
    with pytest.raises(ValueError):
        M.build(G.REPO, a5_sizes=(48,), universe=universe, max_tokens=DEPLOYED_MAX, thinking_budget=4096, prompt_tokens=pc)


# (a) B8's side: a served row's prompt count must EQUAL the frozen one; any difference is a problem
def test_budget_problems_require_the_rows_count_to_equal_the_frozen_one(universe):
    lc = doc(universe)["axes"]["longctx"]
    iid = lc["items"][0]["id"]
    frozen = lc["budget"][iid]["prompt_tokens"]
    assert M.budget_problems(lc, {iid: frozen}) == []
    assert M.budget_problems(lc, {iid: frozen + 1}) and M.budget_problems(lc, {iid: frozen - 1})
    assert M.budget_problems(lc, {"not-an-item": 5})
    assert M.budget_problems(lc, {iid: str(frozen)})


def test_a_tampered_record_is_refused(universe):
    lc = json.loads(json.dumps(doc(universe)["axes"]["longctx"]))
    iid = lc["items"][0]["id"]
    lc["budget"][iid]["resolved_max_tokens"] += 1
    assert M.budget_problems(lc)
    lc2 = json.loads(json.dumps(doc(universe)["axes"]["longctx"]))
    lc2["budget"][iid]["prompt_tokens"] = CAP
    assert M.budget_problems(lc2)


def test_resolved_of_a_served_row_uses_its_own_prompt_count():
    row = {"prompt_tokens": 196_800}
    assert M.resolved_of(row, DEPLOYED_MAX, CAP)[0] == CAP - 196_800
    assert M.resolved_of({"prompt_tokens": 131_100}, DEPLOYED_MAX, CAP)[0] == DEPLOYED_MAX
    assert M.resolved_of({}, DEPLOYED_MAX, CAP) == (None, None)
    assert M.resolved_of({"prompt_tokens": CAP + 1}, DEPLOYED_MAX, CAP) == (None, None)


def test_the_committed_ids_json_when_present_is_a_rebuild_of_its_inputs():
    if not (G.REPO / M.OUT).exists():
        pytest.skip("benchmark/results/m76/ids.json is not generated yet (needs the Math500 universe and the tokenizer)")
    d = M.load(G.REPO)
    sizes = d["a5"]["sizes"]                      # AMENDED (delivery 6, spec v1.4): a5 = {source, report_sha256, sizes}
    assert set(d["a5"]) >= {"source", "report_sha256", "sizes"} and d["a5"]["source"] == M.PLAN_SOURCE
    assert len(d["axes"]["longctx"]["items"]) == sizes[-1] and d["axes"]["longctx"]["sizes"] == sizes
    assert all(n % 6 == 0 and 42 <= n <= 120 for n in sizes) and sizes == sorted(set(sizes))
    assert "/Users/" not in (G.REPO / M.OUT).read_text() and "/home/" not in (G.REPO / M.OUT).read_text()


# (c) B7's REAL committed report is readable by the generator (the v1 candidate read `a5.n` and would have refused it)
def test_the_real_b7_plan_gives_valid_a5_sizes():                  # AMENDED (delivery 5, spec v1.4): sizes, from the plan
    if not (G.REPO / M.REPORT).exists():
        pytest.skip("no B7 report in this checkout")
    sizes, src = M.a5_sizes_from()
    from bench import m76_rule

    assert list(sizes) == [lk["size"] for lk in m76_rule.axis_plan("A5")["looks"]] and src["source"] == M.PLAN_SOURCE
    assert all(n % 6 == 0 and 42 <= n <= 120 for n in sizes)
