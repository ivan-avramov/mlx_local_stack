"""P371 phase 3b: `chain_core.plan()` for the `blocks` and `tg2_tier` builders (A1, a fake FOUR-language corpus end to end,
the docker gate from the corpus, the frozen draw verified at every leg) and the immutable A4 receipts (A10: one per worker
(re)load and arm, `<out_root>/a4/<load>.<worker_n>.<arm>.json`, exclusive create, bound to the worker, sha in chain.json)."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
import threading
from pathlib import Path

import pytest

from bench import chain_core as core
from bench import chain_ops as co
from bench import chain_rows as cr
from bench import run_config as rc
from bench import schedules
from bench.tests import test_c147_chain_runner as T
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    FAP, FAP_PATH, M, PICK1, PICK2, REPO, SMOKE, SMOKE3, arg, calls, chain_json, env, invocations, log_has, run, schedule)
from bench.tests.test_p371_schedules import draw_sha, make_draw

LANGS4 = ("rust", "java", "javascript", "cpp")


def names4(n=4):
    return {lang: [f"{lang[:2]}{i:02d}" for i in range(n)] for lang in LANGS4}


def build_chain(env, argv, config, names, **kw):
    a = M.parse_args(argv + ["--python", sys.executable, "--out-root", str(env["out"]), "--arm-idle-s", "0",
                             "--probe", f"oc={FAP_PATH}", "--frozen-prompt-date", "Mon Jan 05 2026"])
    return core.Chain(config, a, env["ops"], M.Timers(**T.TIMERS), env["lines"].append, repo=REPO, out_root=env["out"],
                      names=names, lifecycle_files=M.lifecycle_files(REPO), **kw)


def run_chain(env, chain, timeout=120):
    res = {}
    th = threading.Thread(target=lambda: res.setdefault("rc", chain.run()), daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        env["ops"].cancel()
        pytest.fail("chain did not finish: " + "\n".join(env["lines"][-10:]))
    return res["rc"]


# ---------------------------------------------------------------- blocks over a four-language corpus
def test_a_fake_four_language_corpus_runs_the_blocks_chain_end_to_end(env):
    cfg = M.m64_config(M.parse_args(SMOKE), langs=LANGS4)
    chain = build_chain(env, SMOKE, cfg, names4(), needs_docker=lambda lang: False)
    assert run_chain(env, chain) == 0
    sched = schedule(env)
    legs = [leg for leg in schedules.legs(sched) if leg["session"] == "s1"]
    assert len(legs) == 2 * 4 * 2 and {leg["lang"] for leg in legs} == set(LANGS4)       # picks x langs x blocks [3, 1]
    cj = chain_json(env)
    assert cj["realized"] == [schedules.leg_key(leg) for leg in legs]
    t = cr.load_slots(cj, env["out"])
    assert len(t.scored) == 2 * 4 * 4 and not t.running
    assert [arg(i["argv"], "--lang") for i in invocations(env)[:2]] == [legs[0]["lang"], legs[1]["lang"]]
    assert {s.split("|")[4] for s in t.scored} == set(LANGS4)
    assert cj["chain_config"]["schedule"]["params"]["langs"] == list(LANGS4)


def test_the_docker_gate_comes_from_the_corpus_not_from_a_hard_coded_language(env):
    cfg = M.m64_config(M.parse_args(SMOKE), langs=LANGS4)
    env["ops"].docker = False
    chain = build_chain(env, SMOKE, cfg, names4(), needs_docker=lambda lang: lang == "cpp")
    assert run_chain(env, chain) == 2 and log_has(env, "docker gate FAIL")
    assert invocations(env) == []
    env2 = dict(env, out=env["out"].parent / "again", lines=[])
    env["ops"].docker = False
    chain = build_chain(env2, SMOKE, cfg, names4(), needs_docker=lambda lang: False)
    assert run_chain(env2, chain) == 0


def test_the_default_docker_rule_is_go_only(env):
    env["ops"].docker = False
    assert run(env, SMOKE) == 2 and log_has(env, "docker gate FAIL")


# ---------------------------------------------------------------- tg2_tier: the frozen draw
def tg2_config(doc, tier="screen"):
    return rc.ChainConfig(
        config_id="tg2-fake", arms=(rc.ArmBinding(arm="oc", probe="benchmark/chains/c147/fake_probe.py", label=co.SCAFFOLD,
                                                  arm_spec="oc"),),
        schedule={"builder": "tg2_tier", "params": {"picks": [PICK1, PICK2]}, "draw_sha256": draw_sha(doc), "tier": tier},
        out_root_family="c147", predictor="off", arm_switch_ops=(), transport_policy="abort_restart",
        resume_policy="restart_load", snapshot_complete_required=False)


@pytest.fixture
def tg2(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    ops = T.FakeOps(tmp_path)
    doc = make_draw()
    draw = tmp_path / "tg2_draw.json"
    draw.write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n")
    sys.path.insert(0, str(REPO / "benchmark/chains/c147"))
    ops.extra_env["FAKE_ITEM_S"] = "0.005"
    yield dict(wd=tmp_path, ops=ops, doc=doc, draw=draw, lines=[], out=tmp_path / "tg2")
    ops.cancel()


def tg2_chain(tg2, doc=None, draw=None, tier="screen"):
    a = T.R.parse_args(["chain", "s1", "--probe-code-sha", "9" * 64, "--probe", str(REPO / "benchmark/chains/c147/fake_probe.py"),
                        "--python", sys.executable, "--out-root", str(tg2["out"]), "--arm-idle-s", "0",
                        "--frozen-prompt-date", "Mon Jan 05 2026"])
    a.tg2_draw = str(draw or tg2["draw"])
    return core.Chain(tg2_config(doc or tg2["doc"], tier), a, tg2["ops"], T.R.Timers(**T.TIMERS), tg2["lines"].append,
                      repo=REPO, out_root=tg2["out"], names={}, lifecycle_files=T.R.lifecycle_files(REPO),
                      needs_docker=lambda lang: False)


def test_a_tg2_tier_chain_records_the_draw_sha_and_tier_in_schedule_json_and_the_config(tg2):
    chain = tg2_chain(tg2)
    assert run_chain(tg2, chain) == 0
    sched = json.loads((tg2["out"] / "schedule.json").read_text())
    assert sched["builder"] == "tg2_tier" and sched["tier"] == "screen" and sched["draw_sha256"] == draw_sha(tg2["doc"])
    cj = json.loads((tg2["out"] / "chain.json").read_text())
    assert cj["chain_config"]["schedule"]["draw_sha256"] == draw_sha(tg2["doc"]) and cj["chain_config"]["schedule"]["tier"] == "screen"
    assert cj["schedule_sha256"] == schedules.schedule_sha256(sched)
    legs = schedules.legs(sched)
    assert len(legs) == 4 and cj["realized"] == [schedules.leg_key(l) for l in legs]
    t = cr.load_slots(cj, tg2["out"])
    assert len(t.scored) == 2 * 4 * 10 and {s.split("|")[4] for s in t.scored} == set(LANGS4)


def test_a_changed_draw_artifact_refuses_before_anything_is_launched(tg2):
    doc = make_draw()
    doc["languages"]["rust"]["screen"] = list(reversed(doc["languages"]["rust"]["screen"]))
    other = tg2["wd"] / "other_draw.json"
    other.write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n")
    chain = tg2_chain(tg2, draw=other)
    assert run_chain(tg2, chain) == 2
    assert any("draw" in ln for ln in tg2["lines"]) and invocations_of(tg2) == []


def invocations_of(tg2):
    p = tg2["ops"].state / "invocations.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_the_draw_membership_is_verified_at_every_leg(tg2):
    ops = tg2["ops"]
    original = ops.a4_gate

    def gate(model, tag):
        if model == PICK2:                                           # the second block: the draw file changed on disk
            doc = make_draw()
            doc["languages"]["cpp"]["screen"] = doc["languages"]["cpp"]["screen"][:-1] + ["cpp/other"]
            tg2["draw"].write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n")
        return original(model, tag)
    ops.a4_gate = gate
    chain = tg2_chain(tg2)
    assert run_chain(tg2, chain) == 2
    assert any("draw" in ln for ln in tg2["lines"]) and len(invocations_of(tg2)) == 4


# ---------------------------------------------------------------- A10: immutable A4 receipts
def a4_files(env):
    return sorted(p.name for p in (env["out"] / "a4").glob("*.json"))


def test_two_arms_and_a_recovery_reload_leave_distinct_immutable_receipts_none_overwritten(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 1}, "normal"]}
    two = ["chain", "s1", "--smoke", "--arms", "oc,pi", "--probe-code-sha", "oc=" + "9" * 64, "--probe-code-sha", "pi=" + "9" * 64]
    assert run(env, two, plan=plan) == 0
    assert a4_files(env) == ["0.0.oc.json", "0.0.pi.json", "0.1.oc.json", "0.1.pi.json", "1.0.oc.json", "1.0.pi.json"]
    cj = chain_json(env)
    for load in cj["progress"]["loads"]:
        for w in load["workers"]:
            for arm, ref in w["a4_receipts"].items():
                path = env["out"] / ref["path"]
                raw = path.read_bytes()
                assert ref["sha256"] == hashlib.sha256(raw).hexdigest() and path.name == f"{load['load']}.{w['n']}.{arm}.json"
                doc = json.loads(raw)
                assert doc["pass"] is True and doc["run_id"].startswith("fake-a4-") and doc["scaffold"]
                assert doc["bench_binding"] == dict(worker=dict(pid=w["pid"], create_time=w["create_time"]),
                                                    load=load["load"], worker_n=w["n"], arm=arm, load_gen=0)
    runs = {json.loads((env["out"] / "a4" / n).read_text())["run_id"] for n in a4_files(env)}
    assert len(runs) == 6                                                         # six different gate runs, six files


def test_each_probe_gets_the_immutable_receipt_of_its_arm_and_current_worker(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 1}, "normal"]}
    two = ["chain", "s1", "--smoke", "--arms", "oc,pi", "--probe-code-sha", "oc=" + "9" * 64, "--probe-code-sha", "pi=" + "9" * 64]
    assert run(env, two, plan=plan) == 0
    cj = chain_json(env)
    for rec in cj["progress"]["invocations"]:
        load = cj["progress"]["loads"][rec["leg_key"][0]]
        arm = rec["slot_base"].split("|")[1]
        want = env["out"] / "a4" / f"{load['load']}.{rec['worker_n']}.{arm}.json"
        argv = next(c["argv"] for c in invocations(env) if arg(c["argv"], "--out").endswith(rec["file"]))
        assert arg(argv, "--a4-v2-receipt") == str(want)


def test_an_existing_receipt_path_is_never_overwritten(env):
    (env["out"] / "a4").mkdir(parents=True)
    (env["out"] / "a4" / "0.0.oc.json").write_text("{}")
    assert run(env, SMOKE) == 2 and log_has(env, "a4/0.0.oc.json") and log_has(env, "exists")
    assert (env["out"] / "a4" / "0.0.oc.json").read_text() == "{}" and invocations(env) == []


def test_a_receipt_changed_after_the_gate_aborts_before_the_next_launch(env):
    ops = env["ops"]
    original = ops.a4_gate

    def gate(model, tag, scaffold=None):
        if model == PICK2:
            (env["out"] / "a4" / "0.0.oc.json").write_text("{}")
        return original(model, tag, scaffold)
    ops.a4_gate = gate
    assert run(env, SMOKE) == 2 and log_has(env, "A4 receipt") and log_has(env, "sha256")
    assert len(invocations(env)) == 4


def test_a_gate_that_leaves_no_receipt_aborts(env):
    ops = env["ops"]
    ops.write_a4_receipt = lambda model: str(env["wd"] / "session_gate/missing.json")
    assert run(env, SMOKE) == 2 and log_has(env, "A4 receipt") and invocations(env) == []
