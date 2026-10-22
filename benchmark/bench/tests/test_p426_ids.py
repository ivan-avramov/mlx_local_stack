"""P426 B9: the committed ID sets of the Fable MTP re-certification (plan §3–§5).

Every axis's item set is recovered from the M40 ON rows (asserted unique and of the documented size), split into the two
AB / BA blocks by a seeded shuffle (seed 426), with a five-item seeded-random smoke set per axis; A4 gets distinct task seeds
per block plus an outside-set smoke seed, and an explicit per-draw request seed. The committed file must equal a rebuild.
"""

import json
from pathlib import Path

import pytest

from bench import p426_ids as ids
from bench.rowschema import sample_seed

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def built():
    return ids.build(REPO)


def test_each_axis_recovers_the_m40_item_set(built):
    for axis, n in (("math500", 100), ("cjudge", 40), ("vision", 20)):
        rows = [
            json.loads(line)
            for line in (REPO / ids.SOURCES[axis]).read_text().splitlines()
            if line.strip()
        ]
        source = [r["id"] for r in rows]
        assert len(source) == len(set(source)) == n
        a = built["axes"][axis]
        assert sorted(a["block1"] + a["block2"]) == sorted(source)
        assert not set(a["block1"]) & set(a["block2"])
        assert abs(len(a["block1"]) - len(a["block2"])) <= 1
        assert len(a["smoke"]) == 5 and set(a["smoke"]) <= set(source)


def test_the_build_is_deterministic_and_seeded(built):
    assert ids.build(REPO) == built
    assert built["seed"] == 426


def test_a4_seeds_are_distinct_paired_and_carry_request_seeds(built):
    a4 = built["axes"]["reasoning"]
    assert a4["block1"] == [128000000, 128000001, 128000002]
    assert a4["block2"] == [128000003, 128000004, 128000005]
    assert a4["smoke"] == [128000006]
    for task in a4["block1"] + a4["block2"] + a4["smoke"]:
        assert a4["request_seeds"][str(task)] == sample_seed(f"reasoning:{task}", 0, 426)


def test_the_committed_file_equals_a_rebuild(built):
    committed = json.loads((REPO / ids.OUT).read_text())
    assert committed == dict(built, sources_sha256=ids.source_shas(REPO))
