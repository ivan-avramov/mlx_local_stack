"""Delivery 5: spec v1.4 (A5 tier 2 nested; two-look A5 signals from `axis_plan("A5")`) and v1.5 / v1.5a (offline counter counts
`input_ids`; refuses bad counts / calibrations; prompts within [−3 %, 0 %] of the rung; deviation recorded). References are
re-derived independently here. B7's committed plan has one A5 look in this copy, so the two-look path uses a stand-in `axis_plan`
installed in the test only. Class (c)."""
from __future__ import annotations

import collections
import json
import random
import types
from collections import UserDict

import pytest

from bench import m76_ids as M, m76_rule, p426_signals as S
from bench.tests import test_m76_b3_fe_surface as G

RUNGS = (131072, 159744, 196608)
TASKS = ("retrieval", "reasoning")
SIZES = (72, 120)
PLAN2 = {"looks": [{"look": 1, "size": 72, "unit": "items", "alpha": 0.003808, "interval_alpha": 0.007616, "exact_alpha": 0.003808},
                   {"look": 2, "size": 120, "unit": "items", "alpha": 0.021192, "interval_alpha": 0.042384, "exact_alpha": 0.021192}],
         "report_sha256": "a" * 64}


@pytest.fixture
def two_looks(monkeypatch):
    real = m76_rule.axis_plan
    full = dict(real("A5"), **PLAN2)                      # B7's real A5 plan keys (sessions, items, …) with the two-look sizes

    def plan(axis, **kw):
        return dict(full) if axis == "A5" else real(axis, **kw)

    monkeypatch.setattr(m76_rule, "axis_plan", plan)
    return PLAN2


# ----------------------------------------------------------------------------------------------- A5 tier 2 (v1.4)
def reference_draw(sizes):
    """The spec's generator, re-derived: Random(7605); tier 1 = per task × rung (task_seed, request_seed) pairs in that order;
    the two smoke items; tier 2 continues the same generator over the same cells."""
    rng, used = random.Random(7605), set()

    def draw():
        while True:
            s = rng.randrange(1, 2 ** 31 - 1)
            if s not in used:
                used.add(s)
                return s

    per1 = sizes[0] // 6
    t1 = [(t, r, k, draw(), draw()) for t in TASKS for r in RUNGS for k in range(per1)]
    smoke = [(t, draw(), draw()) for t in TASKS]
    t2 = [(t, r, k, draw(), draw()) for t in TASKS for r in RUNGS for k in range(per1, per1 + (sizes[1] - sizes[0]) // 6)] \
        if len(sizes) == 2 else []
    return t1, smoke, t2


def test_tier2_is_the_same_generators_continuation_and_tier1_is_unchanged():
    one, two = M.longctx_draw((72,)), M.longctx_draw(SIZES)
    assert two["items"][:72] == one["items"] and two["smoke"] == one["smoke"]
    assert two["block1"] == one["block1"] and two["block2"] == one["block2"] and two["tier1"] == one["tier1"]
    t1, smoke, t2 = reference_draw(SIZES)
    got = [(i["task"], i["rung"], int(i["id"].rsplit("-", 1)[1]), i["task_seed"], i["request_seed"]) for i in two["items"]]
    assert got == t1 + t2                                                      # tier 1 then tier 2, seeds from the one generator
    assert [(s["task"], s["task_seed"], s["request_seed"]) for s in two["smoke"]] == smoke
    assert one["tier2"] is None


def test_tier2_has_48_items_8_per_cell_with_continued_ids_and_unique_seeds():
    d = M.longctx_draw(SIZES)
    t2 = d["tier2"]
    assert len(d["items"]) == 120 and len(t2["items"]) == 48 and t2["per_cell"] == 8
    cells = collections.Counter((i["task"], i["rung"]) for i in d["items"] if i["id"] in set(t2["items"]))
    assert set(cells.values()) == {8} and len(cells) == 6
    for i in d["items"]:
        if i["id"] in set(t2["items"]):
            assert int(i["id"].rsplit("-", 1)[1]) >= 12                       # tier 1 holds 12 per cell
    assert len({i["id"] for i in d["items"]}) == 120
    assert len({i["task_seed"] for i in d["items"]} | {i["request_seed"] for i in d["items"]}
               | {s["task_seed"] for s in d["smoke"]} | {s["request_seed"] for s in d["smoke"]}) == 2 * 120 + 4


def test_tier2_blocks_split_each_cell_equally_and_stay_disjoint_from_tier1():
    d = M.longctx_draw(SIZES)
    t2 = d["tier2"]
    assert set(t2["block1"]) | set(t2["block2"]) == set(t2["items"]) and not set(t2["block1"]) & set(t2["block2"])
    by = {}
    for i in d["items"]:
        if i["id"] in set(t2["items"]):
            by.setdefault((i["task"], i["rung"]), [0, 0])[0 if i["id"] in t2["block1"] else 1] += 1
    assert all(a == b == 4 for a, b in by.values())
    assert not (set(t2["block1"]) | set(t2["block2"])) & (set(d["block1"]) | set(d["block2"]))
    assert set(d["block1"]) | set(d["block2"]) == set(d["tier1"])


def test_the_record_has_both_tiers_budgets_for_every_item_and_a_deviation_per_cell():
    d = M.longctx_draw(SIZES)
    counts = {i["id"]: i["rung"] - 1500 for i in d["items"] + d["smoke"]}
    rec = M.longctx(SIZES, 81920, 4096, prompt_tokens=counts)
    assert rec["n"] == 120 and rec["sizes"] == [72, 120] and len(rec["items"]) == 120 and rec["tier1"] == d["tier1"]
    assert set(rec["tier2"]) >= {"block1", "block2", "items"}
    assert set(rec["budget"]) == {i["id"] for i in d["items"] + d["smoke"]} == set(rec["sampler_seeds"])
    dev = rec["prompt_deviation"]
    assert dev["band"] == [-0.03, 0.0]
    for task in TASKS:
        for rung in RUNGS:
            c = dev["cells"][f"{task}-{rung}"]
            assert c["n"] == 20 and c["min"] == c["max"] == pytest.approx(-1500 / rung) and c["mean"] == pytest.approx(-1500 / rung)
    assert all(dev["cells"][f"smoke-{t}-131072"]["n"] == 1 for t in TASKS)


def test_a5_sizes_come_from_the_plan(two_looks):
    sizes, src = M.a5_sizes_from()
    assert sizes == (72, 120) and src["report_sha256"] == "a" * 64 and src["source"] == M.PLAN_SOURCE
    assert M.a5_sizes_from({"looks": [{"size": 54}]})[0] == (54,)
    for bad in ({"looks": []}, {"looks": [{"size": None}]}, {"looks": [{"size": 72}, {"size": 72}]},
                {"looks": [{"size": 120}, {"size": 72}]}, {"looks": [{"size": 40}]}, {"looks": [{"size": 50}]},
                {"looks": [{"size": 72}, {"size": 100}]}, {"looks": [{"size": 42}, {"size": 84}, {"size": 126}]}, {}):
        with pytest.raises(ValueError):
            M.a5_sizes_from(bad)


def synthetic(sizes=SIZES):
    old = p426 = __import__("bench.p426_ids", fromlist=["x"]).build(G.REPO)["axes"]["math500"]
    universe = sorted(set(old["block1"] + old["block2"]) | {f"syn-{i:04d}" for i in range(400)})
    d = M.longctx_draw(sizes)
    counts = {i["id"]: i["rung"] - 1500 for i in d["items"] + d["smoke"]}
    return universe, counts


def test_load_binds_the_recorded_sizes_and_report_sha_to_the_current_plan(two_looks):
    universe, counts = synthetic()
    source = dict(source=M.PLAN_SOURCE, report_sha256="a" * 64)
    doc = M.build(G.REPO, a5_sizes=SIZES, universe=universe, max_tokens=81920, thinking_budget=4096, a5_source=source,
                  prompt_tokens=counts)
    text = json.dumps(doc, indent=1, sort_keys=True)
    assert M.load(G.REPO, text, plan=PLAN2) == json.loads(text)
    with pytest.raises(ValueError):
        M.load(G.REPO, text, plan=dict(PLAN2, report_sha256="b" * 64))                # the report changed
    with pytest.raises(ValueError):
        M.load(G.REPO, text, plan={"looks": [{"size": 72}], "report_sha256": "a" * 64})  # B7 now plans one look
    tampered = json.loads(text)
    tampered["axes"]["longctx"]["tier1"] = tampered["axes"]["longctx"]["tier1"][::-1]
    with pytest.raises(ValueError):
        M.load(G.REPO, json.dumps(tampered), plan=PLAN2)


# ----------------------------------------------------------------------------------------------- two-look A5 signals
def row(task, rung, ok=True):
    r = dict(task=task, rung=rung, finish_reason="stop", completion_tokens=100, resolved_max_tokens=60000,
             resolved_thinking_budget=40000)
    if task == "retrieval":
        r["hits"] = [True] * 5 if ok else [True] * 4 + [False]
    else:
        r["score"] = 1.0 if ok else 0.0
    return r


def world(n_items=120, lost=0, lost_from=0):
    """order of ids, ref rows (all pass), test rows (`lost` failures starting at position `lost_from`)."""
    d = M.longctx_draw(SIZES)
    items = d["items"][:n_items]
    ref = {i["id"]: row(i["task"], i["rung"]) for i in items}
    bad = {i["id"] for i in items[lost_from:lost_from + lost]}
    test = {i["id"]: row(i["task"], i["rung"], ok=i["id"] not in bad) for i in items}
    return [i["id"] for i in items], ref, test


@pytest.fixture
def spy(monkeypatch, two_looks):
    calls = []
    real = m76_rule.axis_verdict

    def wrapper(axis, look, a, b, **kw):
        out = real(axis, look, a, b, **kw)
        calls.append((axis, look, len(a), out))
        return out

    monkeypatch.setattr(m76_rule, "axis_verdict", wrapper)
    return calls


def test_look1_pass_stops_and_look2_is_not_taken(spy):
    order, ref, test = world(lost=0)
    out = S.kv_a5(ref, test, order)
    assert [(c[0], c[1], c[2]) for c in spy] == [("A5", 1, 72)]
    assert out["looks"][0]["verdict"] == "PASS" and out["final_look"] == 1 and out["n"] == 72
    assert "not taken" in out["looks"][1]["status"] and "verdict" not in out["looks"][1]


def test_look1_loss_stops(spy):
    order, ref, test = world(lost=25)                      # 25 of the first 72 lost: delta −0.35, exact test rejects
    out = S.kv_a5(ref, test, order)
    assert [c[1] for c in spy] == [1]
    assert out["looks"][0]["verdict"] == "LOSS" and out["final_look"] == 1
    assert "not taken" in out["looks"][1]["status"]


def find_undecided_losses(order_len=120):
    for lost in range(1, 15):
        order, ref, test = world(lost=lost)
        v = m76_rule.axis_verdict("A5", 1, S._single({i: S.a5_strict(test[i]) for i in order[:72]}),
                                  S._single({i: S.a5_strict(ref[i]) for i in order[:72]}))
        if v["verdict"] == "UNDECIDED":
            return lost
    return None


def test_look1_undecided_goes_to_look2_on_the_cumulative_items(spy):
    lost = find_undecided_losses()
    assert lost is not None, "no loss count gives UNDECIDED at look 1 under the stand-in plan"
    spy.clear()
    order, ref, test = world(lost=lost)
    out = S.kv_a5(ref, test, order)
    assert [(c[1], c[2]) for c in spy] == [(1, 72), (2, 120)]                     # look 2 reads all 120, not tier 2 alone
    assert out["looks"][0]["verdict"] == "UNDECIDED"
    assert out["looks"][1]["verdict"] in ("PASS", "LOSS", "UNDECIDED")
    assert out["final_look"] == 2 and out["n"] == 120
    b = sum(1 for i in order if S.a5_strict(ref[i]) == 1 and S.a5_strict(test[i]) == 0)
    assert b == lost and spy[1][3]["verdict"] == out["looks"][1]["verdict"]


def test_undecided_without_the_tier2_items_is_pending_and_the_deciding_look_stays_look1(spy):
    lost = find_undecided_losses()
    order, ref, test = world(n_items=72, lost=lost)
    spy.clear()
    out = S.kv_a5(ref, test, order)
    assert [c[1] for c in spy] == [1]
    assert out["looks"][1]["status"].startswith("pending")
    assert out["looks"][0]["verdict"] == "UNDECIDED" and out["final_look"] == 1


def test_the_look_alpha_is_the_plans_not_a_constant(spy):
    order, ref, test = world(lost=0)
    S.kv_a5(ref, test, order)
    v = spy[0][3]
    alpha = v.get("alpha", v.get("exact_alpha"))
    assert alpha in (None, 0.003808) or alpha == pytest.approx(0.003808)
    assert S.kv_plan("A5")["looks"][0]["alpha"] == 0.003808


def test_tiers_that_are_not_the_plans_sizes_are_recorded_and_flag(spy):
    order, ref, test = world(lost=0)
    out = S.kv_a5(ref, test, order, tiers=(60, 120))
    assert "tier_mismatch" in out
    ok = S.kv_a5(ref, test, order, tiers=(72, 120))
    assert "tier_mismatch" not in ok
    flags = S.kv_flags({"header": {"label": "X − N16"}, "axes": {"A5": out}})
    assert any(f["flag"] == "tier_mismatch" or "tier" in f["text"] for f in flags)


def test_a5_gates_are_computed_at_the_deciding_look(spy):
    order, ref, test = world(lost=0)
    out = S.kv_a5(ref, test, order)
    assert sum(g["n"] for g in out["gates"].values()) == 72                      # look 1 decided: its 72 items
    assert all(g["pass"] for g in out["gates"].values())


# ----------------------------------------------------------------------------------------------- the counter (v1.5)
class Batch(UserDict):
    """A `BatchEncoding`-like mapping (transformers >= 5 returns this from apply_chat_template(tokenize=True))."""


def test_token_count_counts_input_ids_whatever_the_container():
    ids = list(range(1, 101))
    assert M.token_count(ids) == 100 and M.token_count(tuple(ids)) == 100
    assert M.token_count(Batch(input_ids=ids, attention_mask=[1] * 100)) == 100          # not 2, the number of keys
    assert M.token_count({"input_ids": ids}) == 100
    assert M.token_count(Batch(input_ids=[ids])) == 100                                  # a single-row batch
    assert M.token_count(types.SimpleNamespace(tolist=lambda: ids) if False else Batch(input_ids=types.SimpleNamespace(tolist=lambda: ids))) == 100


@pytest.mark.parametrize("bad", [{}, Batch(attention_mask=[1, 1]), Batch(input_ids=[[1, 2], [3, 4]]), Batch(input_ids=["a", "b"]),
                                 [], [True, False], "text", 7, None, Batch(input_ids=[]), [1.5, 2.5]])
def test_token_count_refuses_anything_else_and_an_empty_count(bad):
    with pytest.raises(ValueError):
        M.token_count(bad)


@pytest.mark.parametrize("bad", [0, -3, 2.5, None, True, "9"])
def test_count_prompts_refuses_a_count_that_is_not_a_positive_int(bad):
    items = M.longctx_draw((42,))["items"][:2]
    with pytest.raises(ValueError):
        M.count_prompts(items, lambda msgs: bad, 4.5)


class FakeTok:
    chat_template = "{{ template }}"

    def __init__(self, mode, overhead=52, cpt=4.6):
        self.mode, self.overhead, self.cpt = mode, overhead, cpt

    def apply_chat_template(self, messages, add_generation_prompt=True, tokenize=True):
        n = self.overhead + int(sum(len(m["content"]) for m in messages) / self.cpt)
        ids = list(range(1, n + 1))
        if self.mode == "batch":
            return Batch(input_ids=ids, attention_mask=[1] * n)
        if self.mode == "keys_only":                       # the defect: a mapping with two entries, counted by its keys
            return Batch(a=1, b=2)
        return ids


def test_offline_counter_counts_a_batchencoding_like_result_by_its_ids():
    for mode in ("batch", "list"):
        count, cpt, meta = M.offline_counter(tokenizer=FakeTok(mode))
        assert 1.0 <= cpt <= 10.0 and meta["chars_per_token"] == cpt and "transformers_version" in meta
        assert count([{"role": "user", "content": "x" * 4600}]) == 52 + 1000
    assert M.offline_counter(tokenizer=FakeTok("batch"))[1] == pytest.approx(M.offline_counter(tokenizer=FakeTok("list"))[1])


def test_offline_counter_refuses_the_two_keys_defect_and_an_insane_calibration():
    with pytest.raises(ValueError):
        M.offline_counter(tokenizer=FakeTok("keys_only"))                                # the pre-v1.5 count of 2 → 7,400 chars/token
    for cpt in (0.2, 0.99, 10.5, 7400.0, float("nan")):
        with pytest.raises(ValueError):
            M.check_calibration(cpt)
    for cpt in (1.0, 4.55, 10.0):
        assert M.check_calibration(cpt) == cpt


def real_tokenizer():
    try:
        from transformers import AutoTokenizer
        from bench.model_params import _registry_models

        hf = (_registry_models().get(G.ENTRY) or {}).get("hf_path") or G.ENTRY
        return AutoTokenizer.from_pretrained(hf, local_files_only=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"the entry's tokenizer is not in the local HF cache / transformers unavailable ({type(exc).__name__})")


def test_the_real_tokenizer_count_equals_an_independent_input_ids_length():
    tok = real_tokenizer()
    count, cpt, meta = M.offline_counter(tokenizer=tok)
    assert 1.0 <= cpt <= 10.0 and meta["transformers_version"]
    msgs = [{"role": "user", "content": "The quick brown fox jumps over the lazy dog. " * 50}]
    text = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    assert count(msgs) == len(tok(text, add_special_tokens=False)["input_ids"]) > 100       # reference: tokenise the rendered text
    assert count(msgs) > 2


# ----------------------------------------------------------------------------------------------- the band (v1.5a)
def item(rung, task="retrieval", iid="x"):
    return {"id": iid, "task": task, "rung": rung}


def test_band_bounds_are_minus_three_percent_to_zero_never_above():
    r = 131072
    lo = r - int(0.03 * r)                                    # 127,140: −0.02999 %
    assert M.prompt_band_problems([item(r)], {"x": r}) == []
    assert M.prompt_band_problems([item(r)], {"x": r - 1500}) == []
    assert M.prompt_band_problems([item(r)], {"x": r + 1}) != []                                  # above the rung: refused
    assert M.prompt_band_problems([item(r)], {"x": lo}) == []
    assert M.prompt_band_problems([item(r)], {"x": lo - 2}) != []                                 # below −3 %
    assert M.prompt_band_problems([item(r)], {"x": 2}) != []                                      # the 1,600× / two-key defects


@pytest.mark.parametrize("val", [None, "131000", 131000.0, True, 0])
def test_band_refuses_a_missing_or_non_int_count(val):
    assert M.prompt_band_problems([item(131072)], {"x": val}) != []
    assert M.prompt_band_problems([item(131072)], {}) != []


def test_check_prompt_band_raises_and_names_every_offender_count():
    with pytest.raises(ValueError, match="outside the rung band"):
        M.check_prompt_band([item(131072, iid="a"), item(159744, iid="b")], {"a": 131073, "b": 159744})
    M.check_prompt_band([item(131072, iid="a")], {"a": 131000})


def test_main_refuses_a_prompt_above_the_rung_and_writes_nothing(monkeypatch, two_looks):
    out = G.REPO / M.OUT
    before = out.read_bytes() if out.exists() else None
    monkeypatch.setattr(M, "deployed_budget", lambda: (81920, 4096))
    monkeypatch.setattr(M, "offline_counter", lambda: (lambda msgs: 10 ** 6, 4.5, {"transformers_version": "x"}))
    monkeypatch.setattr(M, "count_prompts", lambda items, count, cpt, **kw: {i["id"]: i["rung"] + 5 for i in items})
    assert M.main([]) == 2
    assert (out.read_bytes() if out.exists() else None) == before


def test_the_real_tokenizer_puts_generated_prompts_within_the_band():
    tok = real_tokenizer()
    count, cpt, meta = M.offline_counter(tokenizer=tok)
    d = M.longctx_draw((42,))
    pick = {}
    for it in d["items"] + d["smoke"]:
        pick.setdefault(M.cell_of(it), it)
    chosen = [pick[k] for k in sorted(pick)]
    counts = M.count_prompts(chosen, count, cpt)
    assert M.prompt_band_problems(chosen, counts) == [], {k: (counts[v["id"]] - v["rung"]) / v["rung"] for k, v in pick.items()}
    assert all(counts[i["id"]] <= i["rung"] for i in chosen)                         # prompt + budget must fit: never above
