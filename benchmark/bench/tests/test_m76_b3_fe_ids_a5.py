"""M76 B3 / B5: `benchmark/results/m76/ids.json` — Math500 300 nested + deterministic, and the A5 `longctx` items (spec v1.1 §Wave 1
axes, §A5, §Erratum). Class of each test is in the comment above it: (a) reproduces a failure the spec fixes, (b) preserves an
invariant, (c) exercises new behaviour.

Surface assumed (the spec fixes the file, the generator module and `--a5-n`, not the Python signatures): `bench.m76_ids.build(repo,
a5_n=None) -> dict` shaped like `bench.p426_ids.build` (`axes[axis]`), A5 under `axes["longctx"]["items"]` (list of
`{id, task, rung, task_seed, request_seed}`), Math500 under `axes["math500"]` (lists of ids), and `main(argv)` taking `--a5-n`.
"""
from __future__ import annotations

import json
import re
from collections import Counter

import pytest

from bench import p426_ids
from bench.tests import test_m76_b3_fe_surface as G

IDS = G.REPO / "benchmark" / "results" / "m76" / "ids.json"
P426_IDS = G.REPO / "benchmark" / "results" / "p426" / "ids.json"
RUNGS = (131072, 159744, 196608)
TASKS = ("retrieval", "reasoning")
N_VALUES = (42, 48, 60, 120)


def committed():
    if not IDS.exists():
        pytest.fail(f"{IDS.relative_to(G.REPO)} is absent (the spec's committed id file)")
    return json.loads(IDS.read_text())


def math500_lists(doc):
    """Every list of ids under axes.math500 (the spec names tiers and blocks, not the key spelling)."""
    return {k: v for k, v in doc["axes"]["math500"].items() if isinstance(v, list) and v and all(isinstance(i, str) for i in v)}


def a5_items(doc):
    ax = doc["axes"]["longctx"]
    return ax["items"] if isinstance(ax, dict) else ax


def p426_math500():
    d = json.loads(P426_IDS.read_text())["axes"]["math500"]
    return set(d["block1"]) | set(d["block2"])


def build(n=None):
    from bench import m76_ids

    return m76_ids.build(G.REPO, a5_n=n) if n is not None else m76_ids.build(G.REPO)


# ----------------------------------------------------------------------------------------------- Math500 300
# (c) 300 unique ids, P426's 100 are a subset (nested), the other 200 are new
def test_math500_is_300_unique_ids_and_contains_p426s_100():
    # AMENDED (delivery 6): read the record's documented keys (`order`, `tier2`), not every id list (the 500-id universe is one)
    m = committed()["axes"]["math500"]
    allids = list(m["order"])
    old = p426_math500()
    assert len(old) == 100
    assert len(allids) == 300 and len(set(allids)) == 300
    assert old <= set(allids)
    assert len(set(allids) - old) == 200 and set(allids[100:]) == set(allids) - old
    assert set(m["tier2"]["block1"]) | set(m["tier2"]["block2"]) == set(allids) - old


# (c) tier 1 = the first 100 (= P426's 100), tier 2 = the other 200; a leg names its tier
def test_math500_tiers_are_nested_100_then_200():
    # AMENDED (delivery 6): tier 1 = the first 100 of `order` (the record may hold it as a count or a list); tier 2 = the rest
    m = committed()["axes"]["math500"]
    order = list(m["order"])
    tier1 = m["tier1"]
    n1 = tier1 if isinstance(tier1, int) else len(tier1)
    assert n1 == 100 and set(order[:100]) == p426_math500()
    if isinstance(tier1, list):
        assert tier1 == order[:100]
    tier2 = set(order[100:])
    assert len(tier2) == 200 and tier2.isdisjoint(p426_math500())
    assert set(m["tier2"]["block1"]) | set(m["tier2"]["block2"]) == tier2
    assert len(m["tier2"]["block1"]) == len(m["tier2"]["block2"]) == 100


# (c) within P426's 100 the block split is P426's (seed 426), i.e. identical blocks to benchmark/results/p426/ids.json
def test_math500_first_100_keep_p426_block_split():
    doc = committed()
    old = json.loads(P426_IDS.read_text())["axes"]["math500"]
    lists = [set(v) for v in math500_lists(doc).values()]
    assert set(old["block1"]) in lists and set(old["block2"]) in lists


# (c) the 200 new ids come from `random.Random(7601)` over the REMAINING Math500 ids: re-derivation (needs the dataset, else skip)
def test_math500_extra_200_are_drawn_by_random_7601_from_the_remaining_ids():
    import random

    doc = committed()
    extra = set().union(*map(set, math500_lists(doc).values())) - p426_math500()
    try:
        from datasets import load_dataset

        ds = load_dataset("HuggingFaceH4/MATH-500", split="test")
    except Exception as exc:  # noqa: BLE001 — unavailable dependency => skip with the reason
        pytest.skip(f"MATH-500 not loadable offline: {type(exc).__name__}")
    from bench import benchmarks

    try:
        universe = [f"math500_{i}" for i in range(len(ds))] if not hasattr(benchmarks, "math500_ids") else benchmarks.math500_ids()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"cannot enumerate Math500 ids: {exc}")
    if not extra <= set(universe):
        pytest.skip("the dataset's id spelling is not the committed spelling (cannot re-derive the draw)")
    rest = sorted(set(universe) - p426_math500())
    assert set(random.Random(7601).sample(rest, 200)) == extra


# DELETED (delivery 4): test_ids_json_equals_a_rebuild_and_builds_are_deterministic — it called v1's `build(repo, a5_n=…)`; v1.2's
# build needs the universe and prompt counts. Superseded by test_m76_b3_fe_fix_ids_budget.py (determinism, and `M.load` of the
# committed file once it exists).


# (b) the P426 ids file is untouched by the M76 generator
def test_p426_ids_still_a_rebuild_of_its_sources():
    from bench import p426_plan

    assert p426_plan.load_ids(G.REPO)["axes"]["math500"]["smoke"] == json.loads(P426_IDS.read_text())["axes"]["math500"]["smoke"]
    assert len(p426_ids.build(G.REPO)["axes"]["math500"]["block1"]) == 50


# ----------------------------------------------------------------------------------------------- A5 items
# DELETED (delivery 4): test_a5_items_split_equally_per_task_and_rung, test_a5_item_fields_and_uniqueness,
# test_a5_seeds_are_deterministic — all called v1's `build(repo, a5_n=…)`. Superseded by test_m76_b3_fe_fix_ids_budget.py
# (test_a5_cells_are_equal_and_seeds_unique, test_a5_items_are_deterministic_from_seed_7605).


# (c) the committed file records the n and it is a multiple of 6 in 42..120
def test_committed_a5_n_is_a_multiple_of_six_in_range():
    n = len(a5_items(committed()))
    assert n % 6 == 0 and 42 <= n <= 120


# DELETED (delivery 4): test_a5_n_outside_the_contract_is_refused — it called v1's `build(repo, a5_n=…)`. Superseded by
# test_m76_b3_fe_fix_ids_budget.py::test_a5_n_outside_the_contract_is_refused (check_a5_n / longctx_items).


# (c) the CLI refuses too: non-zero, and writes nothing
@pytest.mark.parametrize("bad", ["40", "41", "126"])
def test_a5_n_cli_refuses_and_leaves_the_committed_file(bad):
    from bench import m76_ids

    before = IDS.read_bytes() if IDS.exists() else None
    try:
        rc = m76_ids.main(["--a5-n", bad])
    except SystemExit as exc:
        rc = exc.code
    assert rc not in (0, None)
    assert (IDS.read_bytes() if IDS.exists() else None) == before


# (c) the ids file never carries an absolute home path / hostname (public repo)
def test_ids_json_has_no_absolute_paths():
    assert not re.search(r"/(Users|home)/", IDS.read_text()) if IDS.exists() else pytest.fail("absent")
