"""P279 (2026-10-11): `--smoke` — a short live rehearsal of the chain-only paths before the 20 h P223 chain.

The fake probe hid three runner/probe contract gaps (P276, P276b) that only live runs found, and the pilot mode runs
one pick-1 Python leg. Smoke mode runs the REAL schedule (both models, both languages, the block switch, the reload
control) with every leg shrunk to a 1-item pilot and a 2-item full leg, a 60 s arm idle, under its own out-root
(`$STACK_WORKDIR/c147-smoke`; the real chain's `c147/` is refused). Smoke rows are rehearsal evidence only."""
import json
from pathlib import Path

import pytest

from bench.tests.test_c147_chain_runner import CHAIN, R, chain_json, env, run   # noqa: F401  (fixture)

SMOKE = ["chain", "s1", "reload", "--probe-code-sha", "9" * 64, "--smoke"]


def test_smoke_schedule_shrinks_every_leg_and_keeps_the_real_order():
    names = R.load_universe()
    real = R.schedule("chain", ["s1", "reload"], names, "/o")
    smoke = R.schedule("chain", ["s1", "reload"], names, "/o", smoke=True)
    assert [(b["session"], b["model"], [x["lang"] for x in b["legs"]]) for b in smoke] == \
        [(b["session"], b["model"], [x["lang"] for x in b["legs"]]) for b in real]
    for b in smoke:
        for leg in b["legs"]:
            assert len(leg["pilot_names"]) == R.SMOKE_PILOT_N == 1
            assert set(leg["pilot_names"]) <= set(leg["full_names"])
            assert len(leg["full_names"]) == (1 if b["session"] == "reload" else R.SMOKE_FULL_N)
            assert set(leg["full_names"]) <= set(names[leg["lang"]])
    blk = smoke[0]
    assert [s["limit"] for s in R.steps_for(blk, 0)] == [1, None]       # the pilot step's --limit follows its size


def test_real_schedule_unchanged_by_the_smoke_option():
    names = R.load_universe()
    for b in R.schedule("chain", ["s1", "s2", "reload"], names, "/o"):
        for leg in b["legs"]:
            assert len(leg["pilot_names"]) == R.PILOT_N
    assert [s["limit"] for s in R.steps_for(R.schedule("chain", ["s1"], names, "/o")[0], 0)] == [R.PILOT_N, None]


def test_smoke_arguments_and_out_root(tmp_path):
    a = R.parse_args(SMOKE)
    assert a.smoke and a.arm_idle_s == R.SMOKE_ARM_IDLE_S == 60.0
    assert R.parse_args(SMOKE + ["--arm-idle-s", "5"]).arm_idle_s == 5.0
    assert R.resolve_out_root(a, tmp_path) == tmp_path / "c147-smoke"
    assert R.resolve_out_root(R.parse_args(CHAIN), tmp_path) == tmp_path / "c147"
    with pytest.raises(SystemExit):
        R.resolve_out_root(R.parse_args(SMOKE + ["--out-root", str(tmp_path / "c147")]), tmp_path)
    with pytest.raises(SystemExit):
        R.parse_args(["pilot", "--smoke"])


def test_smoke_chain_runs_end_to_end_against_the_fake_probe(env):
    env["out"] = Path(env["out"]).parent / "c147-smoke"        # the harness's default out-root is the real c147/
    Path(env["out"]).mkdir(parents=True, exist_ok=True)
    assert run(env, SMOKE) == 0
    doc = chain_json(env)
    assert doc["smoke"] is True and doc["status"] == "finished"
    sizes = [(a["step"], len(a["argv"][a["argv"].index("--items") + 1].split(","))) for a in doc["attempts"]]
    assert ("pilot", 1) in sizes and ("full", 2) in sizes and all(n <= 2 for _, n in sizes)
