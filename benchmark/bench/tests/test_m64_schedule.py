"""M64 spec 8.1: the seeded, permutation-balanced block schedule (`schedules.blocks`; P371 phase 3b moved its callers off
`m64_schedule`, which is gone; the pinned golden values of the old builder are in
`fixtures/p371_blocks_golden.json`)."""
from __future__ import annotations

import collections
import itertools
import json

import pytest

from bench import schedules as ms

PICK1 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PICK2 = "Qwen3.8-27B-mlx-uniform-4bit"
NAMES = {"python": [f"p{i:02d}" for i in range(22)], "go": [f"g{i:02d}" for i in range(21)]}
ARMS3 = ("oc", "pi", "dsh")


def build(arms=ARMS3, **kw):
    return ms.blocks(arms, NAMES, picks=(PICK1, PICK2), **kw)


def cells(schedule):
    return [(load, cell) for load in schedule["loads"] for cell in load["cells"]]


def test_the_spec_shape_two_sessions_two_picks_two_languages_plus_reload():
    s = build()
    assert [(l["session"], l["pick"]) for l in s["loads"]] == [
        ("s1", PICK1), ("s1", PICK2), ("s2", PICK2), ("s2", PICK1), ("reload", PICK1)]
    assert [l["seed_base"] for l in s["loads"]] == [1001, 1001, 2002, 2002, 1001]
    assert [[c["lang"] for c in l["cells"]] for l in s["loads"]] == [["python", "go"]] * 4 + [["python"]]
    assert s["block_size"] == 3 and s["arms"] == list(ARMS3)


def test_python_is_seven_blocks_plus_a_residual_item_and_go_seven_blocks():
    s = build()
    for load, cell in cells(s):
        if load["session"] == "reload":
            continue
        sizes = [len(b["items"]) for b in cell["blocks"]]
        assert sizes == ([3] * 7 + [1] if cell["lang"] == "python" else [3] * 7)
        assert sorted(i for b in cell["blocks"] for i in b["items"]) == sorted(NAMES[cell["lang"]])
        assert [i for b in cell["blocks"] for i in b["items"]] == cell["order"]


def test_every_block_runs_every_arm_once_in_one_permutation():
    for load, cell in cells(build()):
        for b in cell["blocks"]:
            assert sorted(b["arms"]) == sorted(ARMS3) and len(set(b["arms"])) == 3


def test_permutations_are_balanced_within_each_pick_session_language_cell():
    """7 blocks over 6 permutations: each exactly once plus one drawn (the residual item draws its own)."""
    perms = set(itertools.permutations(ARMS3))
    for load, cell in cells(build()):
        if load["session"] == "reload":
            continue
        full = [tuple(b["arms"]) for b in cell["blocks"] if len(b["items"]) == 3]
        assert len(full) == 7
        counts = collections.Counter(full)
        assert set(counts) == perms and sorted(counts.values()) == [1, 1, 1, 1, 1, 2]


def test_the_schedule_is_deterministic_and_seeded():
    a, b = build(), build()
    assert a == b and ms.schedule_sha256(a) == ms.schedule_sha256(b)
    assert len(ms.schedule_sha256(a)) == 64


def test_sessions_use_distinct_item_orders_and_picks_are_seeded_apart():
    s = build()
    orders = {(l["session"], l["pick"], c["lang"]): c["order"] for l, c in cells(s)}
    assert orders[("s1", PICK1, "python")] != orders[("s2", PICK1, "python")]
    assert orders[("s1", PICK1, "python")] != orders[("s1", PICK2, "python")]


def test_the_reload_control_is_pick1_python_the_first_five_s1_items_with_the_s1_seed():
    s = build()
    reload = s["loads"][-1]
    s1 = next(l for l in s["loads"] if l["session"] == "s1" and l["pick"] == PICK1)
    (cell,) = reload["cells"]
    assert cell["order"] == s1["cells"][0]["order"][:5] and reload["seed_base"] == s1["seed_base"] == 1001
    assert [len(b["items"]) for b in cell["blocks"]] == [3, 2]
    assert not build(reload_control=False)["loads"][-1]["session"] == "reload"


def test_the_arm_set_decides_the_permutations_one_arm_is_one_permutation():
    s = build(arms=("oc",))
    for load, cell in cells(s):
        assert all(b["arms"] == ["oc"] for b in cell["blocks"])
    two = build(arms=("oc", "pi"))
    assert {tuple(b["arms"]) for l, c in cells(two) for b in c["blocks"] if len(b["items"]) == 3} == {("oc", "pi"), ("pi", "oc")}


def test_unknown_or_duplicate_arms_refuse():
    with pytest.raises(ValueError, match="arms"):
        build(arms=("oc", "oc"))
    with pytest.raises(ValueError, match="arms"):
        build(arms=())
    with pytest.raises(ValueError, match="arm"):
        build(arms=("oc", "zz"))


def test_smoke_shrinks_every_cell_but_keeps_a_full_block_and_a_residual():
    s = build(smoke=True)
    for load, cell in cells(s):
        if load["session"] != "reload":
            assert [len(b["items"]) for b in cell["blocks"]] == [3, 1]
    full = build()
    for ls, lf in zip(s["loads"], full["loads"]):
        for cs, cf in zip(ls["cells"], lf["cells"]):
            assert cs["order"] == cf["order"][:len(cs["order"])]


def test_legs_flatten_in_run_order_and_realized_order_is_checked_exactly():
    s = build(arms=("oc", "pi"))
    legs = ms.legs(s)
    assert len(legs) == sum(len(b["arms"]) for l, c in cells(s) for b in c["blocks"])
    assert legs[0]["arm"] == s["loads"][0]["cells"][0]["blocks"][0]["arms"][0] and legs[0]["block"] == 0
    assert [leg["index"] for leg in legs] == list(range(len(legs)))
    realized = [ms.leg_key(leg) for leg in legs]
    ms.check_realized(s, realized)
    with pytest.raises(ValueError, match="realized order"):
        ms.check_realized(s, realized[:-1])
    swapped = realized[:]
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(ValueError, match="realized order"):
        ms.check_realized(s, swapped)


def test_a_frozen_schedule_must_equal_the_regenerated_one():
    s = build()
    ms.require_frozen(s, ms.schedule_sha256(s))
    with pytest.raises(ValueError, match="schedule"):
        ms.require_frozen(build(arms=("oc",)), ms.schedule_sha256(s))
    changed = json.loads(json.dumps(s))
    changed["loads"][0]["cells"][0]["order"].reverse()
    with pytest.raises(ValueError, match="schedule"):
        ms.require_frozen(changed, ms.schedule_sha256(s))
