"""P426 stack code round 1 K3 / K4: the leg planner derives everything a Wave-1 leg depends on from (axis, arm, block) and the
committed `benchmark/results/p426/ids.json` — never from a caller-supplied spec: the exact driver argv, every output / sidecar
that must not exist, the planned membership, the expected seeds per row and the expected request count.
"""

import json
from pathlib import Path

import pytest

from bench import p426_ids, p426_plan as PL
from bench.rowschema import sample_seed

REPO = Path(__file__).resolve().parents[3]
IDS = json.loads((REPO / p426_ids.OUT).read_text())
ENTRY = IDS["entry"]


def test_a_bench_leg_is_derived_from_its_block():
    leg = PL.plan_leg(REPO, "math500", "on", 1)
    sel = IDS["axes"]["math500"]["block1"]
    assert leg["planned"] == sel and leg["row_key"] == "id" and leg["expected_requests"] == len(sel)
    argv = leg["driver_argv"]
    assert argv[argv.index("--ids") + 1] == "math500=" + ":".join(sel)
    assert argv[argv.index("--tune") + 1] == "p426-on-b1"
    assert "--sampling-profile" in argv and argv[argv.index("--sampling-profile") + 1] == "deployed"
    assert leg["rows_path"].name == "math500.p426-on-b1.jsonl"
    assert leg["seeds"] == {i: {"sampler_seed": sample_seed(i, 0, base=0), "sample": 0, "seed_base": 0} for i in sel}


def test_the_smoke_uses_the_committed_smoke_set_and_its_own_namespace():
    leg = PL.plan_leg(REPO, "cjudge", "off", None, smoke=True)
    assert leg["planned"] == IDS["axes"]["cjudge"]["smoke"]
    assert leg["rows_path"].name == "cjudge.p426-off-smoke.jsonl"


def test_a_vision_leg_counts_two_requests_per_image_and_pins_turn_seeds():
    leg = PL.plan_leg(REPO, "vision", "off", 2)
    sel = IDS["axes"]["vision"]["block2"]
    assert leg["expected_requests"] == 2 * len(sel)
    assert leg["seeds"][sel[0]] == {"seed": sample_seed(sel[0], 0), "turn2_seed": sample_seed(sel[0], 1)}
    argv = leg["driver_argv"]
    assert argv[argv.index("--ids") + 1] == ":".join(sel) and leg["rows_path"].name == "vision_gate.p426-off-b2.jsonl"


def test_a_reasoning_leg_pins_task_and_request_seeds():
    leg = PL.plan_leg(REPO, "reasoning", "on", 2)
    tasks = IDS["axes"]["reasoning"]["block2"]
    assert leg["planned"] == tasks and leg["row_key"] == "seed"
    assert leg["expected_requests"] == len(tasks) + 1  # + the chars-per-token calibration request
    argv = leg["driver_argv"]
    assert argv[argv.index("--task-seed-base") + 1] == str(tasks[0])
    assert argv[argv.index("--request-seed-base") + 1] == "426"
    assert argv[argv.index("--samples") + 1] == str(len(tasks))
    assert leg["seeds"] == {t: {"sampler_seed": IDS["axes"]["reasoning"]["request_seeds"][str(t)]} for t in tasks}
    assert leg["rows_path"].name == "reasoning.p426-on-b2.partial.jsonl"


def test_every_existing_output_of_the_stem_refuses(tmp_path):
    leg = PL.plan_leg(REPO, "math500", "on", 1, results_root=tmp_path)
    assert PL.existing_outputs(leg) == []
    (tmp_path / ENTRY).mkdir()
    (tmp_path / ENTRY / "math500.p426-on-b1.manifest.json").write_text("{}")
    assert [p.name for p in PL.existing_outputs(leg)] == ["math500.p426-on-b1.manifest.json"]


@pytest.mark.parametrize("axis, block", [("math500", 3), ("nope", 1)])
def test_unknown_axes_and_blocks_refuse(axis, block):
    with pytest.raises(ValueError):
        PL.plan_leg(REPO, axis, "on", block)


def test_the_ids_file_must_be_the_committed_one(tmp_path):
    doc = dict(IDS)
    doc["seed"] = 1
    with pytest.raises(ValueError, match="ids.json"):
        PL.load_ids(REPO, text=json.dumps(doc))


@pytest.mark.parametrize(
    "row, ok",
    [
        ({"id": "a", "sampler_seed": 1, "sample": 0, "seed_base": 0}, True),
        ({"id": "a", "sampler_seed": 2, "sample": 0, "seed_base": 0}, False),
        ({"id": "a", "sampler_seed": 1, "sample": 1, "seed_base": 0}, False),
        ({"id": "a", "sample": 0, "seed_base": 0}, False),
    ],
)
def test_seed_problems(row, ok):
    expected = {"a": {"sampler_seed": 1, "sample": 0, "seed_base": 0}}
    assert (PL.seed_problems(expected, [row], "id") == []) is ok


def test_vision_seed_problems_read_turn_two():
    expected = {"v": {"seed": 5, "turn2_seed": 6}}
    good = {"id": "v", "seed": 5, "turn2": {"seed": 6}}
    assert PL.seed_problems(expected, [good], "id") == []
    assert PL.seed_problems(expected, [dict(good, turn2={"seed": 7})], "id")
