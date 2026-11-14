"""Delivery 3: erratum-v1.2 items 1, 4, 8, 9 — the lever surface of the existing functions, axis-specific A4 / A5 names, s3, and the V
refusal before any leg. Class: (a) reproduces a failure the erratum fixes, (b) invariant, (c) new behaviour.
Real registry texts / argv (fixtures/m76_b3_fe)."""
from __future__ import annotations

import json
import re

import pytest

from bench import p426_leg, p426_plan as P, p426_wave1 as W1, p426_wave2 as W2, schedules
from bench.tests import test_m76_b3_fe_surface as G

E = G.ENTRY
AXES = ("math500", "cjudge", "vision", "reasoning", "m1", "longctx")


# ----------------------------------------------------------------------------------------------- item 8: the lever surface
# (c) registry_delta_problems(lever="kv", arms=) accepts each pair, refuses a changed MTP / non-KV key and a mislabelled arm
@pytest.mark.parametrize("a,b", [("n16", "x"), ("x", "v"), ("n16", "v")])
def test_registry_delta_lever_kv_accepts_each_pair(a, b):
    assert p426_leg.registry_delta_problems(G.text(a), G.text(b), E, lever="kv", arms=(a, b)) == []
    assert p426_leg.registry_delta_problems(G.text(a), G.text(b), E, lever="kv") == []          # arms default: own KV state


@pytest.mark.parametrize("old,new", [
    ("mtp_verify_scan: joint_v1", "mtp_verify_scan: per_query"), ("draft_kind: mtp", "draft_kind: none"),
    (f"draft_model: {G.DRAFTER}", "draft_model: someone/else-drafter"), ("prefill_step_size: 512", "prefill_step_size: 1024"),
    ("max_kv_cache_size: 262144", "max_kv_cache_size: 131072")])
def test_registry_delta_lever_kv_refuses_a_changed_key(old, new):
    bad = G.text("x").replace(old, new, 1)
    assert bad != G.text("x")
    assert p426_leg.registry_delta_problems(bad, G.text("n16"), E, lever="kv", arms=("x", "n16"))


def test_registry_delta_lever_kv_refuses_the_mtp_off_arm_and_one_state_twice():
    assert p426_leg.registry_delta_problems(G.text("x"), G.text("xo"), E, lever="kv", arms=("x", "n16"))
    assert p426_leg.registry_delta_problems(G.text("x"), G.text("x"), E, lever="kv", arms=("x", "x"))


# (c) model_argv_problems(lever="kv", arm=)
@pytest.mark.parametrize("arm", ["n16", "x", "v"])
def test_model_argv_lever_kv_accepts_each_arms_real_argv(arm):
    cmd = " ".join(G.worker_argv(arm.upper()))
    assert p426_leg.model_argv_problems(cmd, G.text(arm), E, lever="kv", arm=arm) == []
    assert p426_leg.model_argv_problems(cmd, G.text(arm), E, lever="kv") == []                   # arm from the registry's state


@pytest.mark.parametrize("arm,as_", [("n16", "x"), ("x", "n16"), ("x", "v"), ("v", "x"), ("n16", "v"), ("v", "n16")])
def test_model_argv_lever_kv_refuses_another_arms_argv(arm, as_):
    cmd = " ".join(G.worker_argv(arm.upper()))
    assert p426_leg.model_argv_problems(cmd, G.text(as_), E, lever="kv", arm=as_)


def test_model_argv_lever_kv_refuses_a_worker_without_mtp_flags_and_a_wrong_model():
    assert p426_leg.model_argv_problems(" ".join(G.worker_argv("XO")), G.text("x"), E, lever="kv", arm="x")
    cmd = " ".join(G.worker_argv("X")).replace(f"caslca/{E}", "caslca/other-model")
    assert p426_leg.model_argv_problems(cmd, G.text("x"), E, lever="kv", arm="x")


# (b) the default lever of both is today's
def test_default_lever_of_both_checks_is_today_s():
    assert p426_leg.registry_delta_problems(G.text("x"), G.text("n16"), E)
    assert p426_leg.model_argv_problems(" ".join(G.worker_argv("X")), G.text("x"), E) == []
    for fn in (p426_leg.registry_delta_problems, p426_leg.model_argv_problems):
        with pytest.raises(ValueError):
            fn(*((G.text("x"), G.text("n16"), E) if fn is p426_leg.registry_delta_problems else ("", G.text("x"), E)), lever="bogus")


# (c) names, paths, schedule, argv
@pytest.mark.parametrize("axis", [a for a in AXES if a != "longctx"])
@pytest.mark.parametrize("arm", ["n16", "x", "v"])
def test_leg_name_lever_kv_is_m76(axis, arm):
    assert P.leg_name(axis, arm, 1, "s3", lever="kv") == f"{axis}-m76-{arm}-b1"
    assert P.leg_name(axis, arm, "smoke", "s3", lever="kv") == f"{axis}-m76-{arm}-smoke"
    assert W1.leg_name(axis, arm, 2, "s3", lever="kv") == f"{axis}-m76-{arm}-b2"


def test_leg_name_and_frozen_path_default_lever_unchanged_and_kv_needs_s3(tmp_path):
    assert P.leg_name("math500", "on", 1) == "math500-p426-on-b1"
    assert P.leg_name("math500", "off", 2, "s2") == "math500-p426s2-off-b2"
    assert P.frozen_path(tmp_path, "s2") == tmp_path / "p426" / "frozen.s2.json"
    assert P.frozen_path(tmp_path, "s3", lever="kv") == tmp_path / "m76" / "p426" / "frozen.s3.json"
    for bad in ("s", "s2"):
        with pytest.raises(ValueError):
            P.leg_name("math500", "x", 1, bad, lever="kv")
        with pytest.raises(ValueError):
            P.frozen_path(tmp_path, bad, lever="kv")


def test_schedule_lever_kv_orders_and_names_both_arms():
    legs = W1.schedule(axes=("math500", "longctx"), lever="kv", arms=("n16", "x"))
    assert [l[:3] for l in legs[:4]] == [("math500", "n16", "smoke"), ("math500", "x", "smoke"), ("longctx", "n16", "smoke"),
                                         ("longctx", "x", "smoke")]
    per_axis = [l[:3] for l in legs if l[0] == "math500" and l[2] != "smoke"]
    assert per_axis == [("math500", "n16", 1), ("math500", "x", 1), ("math500", "x", 2), ("math500", "n16", 2)]
    assert not any(l[1] in ("off", "on") for l in legs)
    assert "longctx" in dict.fromkeys(l[0] for l in W1.schedule(lever="kv", arms=("n16", "x")))   # default axes include A5
    assert W1.schedule()[0] == ("math500", "off", "smoke") and "longctx" not in {l[0] for l in W1.schedule()}   # (b)
    with pytest.raises(ValueError):
        W1.schedule(axes=("longctx",))


def test_leg_argv_lever_kv_runs_from_the_arms_worktree_and_names_the_lever():
    argv = W1.leg_argv("/WT", "/WD", None, "/RC", "math500", "x", 1, "s3", lever="kv")
    assert argv[argv.index("--lever") + 1] == "kv" and argv[argv.index("--build") + 1] == "s3" and argv[argv.index("--arm") + 1] == "x"
    assert "--registry-on" not in argv and argv[argv.index("--stack-root") + 1] == "/WT"


# ----------------------------------------------------------------------------------------------- item 4: A4 / A5 never collide
# (a) the A5 tune differs from A4's (`reasoning`) AND from every other axis' for the same arm / block
@pytest.mark.parametrize("arm", ["n16", "x"])
@pytest.mark.parametrize("sel", [1, 2, "smoke"])
def test_a5_tune_stem_and_leg_name_differ_from_a4(arm, sel):
    a4, a5 = P.leg_name("reasoning", arm, sel, "s3", lever="kv"), P.leg_name("longctx", arm, sel, "s3", lever="kv")
    assert a4 != a5
    assert re.fullmatch(rf"longctx-m76-{arm}-lc-(smoke|b[12])", a5), a5
    tune4, tune5 = a4.split("reasoning-")[1], a5.split("longctx-")[1]
    assert tune4 != tune5 and "lc" not in tune4


# (a) a runner's out-tag for an A5 item can never be a prefix-collision of A4's `reasoning.<tune>` stem
def test_a5_out_tags_do_not_share_a_stem_with_a4():
    tune4 = P.kv_tune("x", 1, False, axis="reasoning")
    tune5 = P.kv_tune("x", 1, False, axis="longctx")
    stems4 = {f"reasoning.{tune4}"}
    stems5 = {f"reasoning.{tune5}.item", f"retrieval.{tune5}.item"}
    assert not any(s.startswith(f"{t}.") or s == t for s in stems5 for t in stems4)
    assert tune4 == "m76-x-b1" and tune5 == "m76-x-lc-b1"


# ----------------------------------------------------------------------------------------------- item 9: V refused before any leg
# (c)
def test_preflight_refuses_a_pair_naming_v():
    legs = W1.schedule(axes=("math500",), lever="kv", arms=("x", "v"))
    assert W1.preflight_kv(("x", "v"), legs, {})
    assert W1.preflight_kv(("n16", "v"), W1.schedule(axes=("math500",), lever="kv", arms=("n16", "v")), {})


def test_preflight_requires_the_tq4_arms_certified_by_and_refuses_a_foreign_one(tmp_path):
    legs = W1.schedule(axes=("math500", "m1"), lever="kv", arms=("n16", "x"))
    assert W1.preflight_kv(("n16", "x"), legs, {})                                       # x m1 without --certified-by
    rec = tmp_path / "stage2.json"
    rec.write_text("{}")
    assert W1.preflight_kv(("n16", "x"), legs, {"x": str(tmp_path / "missing.json")})   # named file absent
    assert W1.preflight_kv(("n16", "x"), legs, {"x": str(rec), "n16": str(rec)})        # N16 has nothing to certify
    assert W1.preflight_kv(("n16", "x"), legs, {"x": str(rec), "v": str(rec)})          # outside the pair
    assert W1.preflight_kv(("n16", "x"), legs, {"x": str(rec)}) == []                    # the good case
    assert W1.preflight_kv(("n16", "x"), W1.schedule(axes=("math500",), lever="kv", arms=("n16", "x")), {}) == []   # no m1 leg


def test_main_kv_refuses_v_before_anything_runs(tmp_path):
    import os
    import subprocess
    import sys

    env = {"PYTHONPATH": str(G.REPO / "benchmark"), "PATH": "/usr/bin:/bin:/opt/homebrew/bin", "HOME": str(tmp_path),
           "STACK_WORKDIR": str(tmp_path)}
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    out = tmp_path / "out"
    proc = subprocess.run([sys.executable, "-m", "bench.p426_wave1", "--lever", "kv", "--build", "s3", "--pair", "x,v", "--arm-root",
                           f"x={a}", "--arm-root", f"v={b}", "--main-root", str(tmp_path / "main"), "--workdir", str(tmp_path),
                           "--out", str(out), "--axes", "math500"], cwd=G.REPO / "benchmark", capture_output=True, text=True,
                          timeout=300, env=env)
    assert proc.returncode != 0
    assert "V" in proc.stderr + proc.stdout
    assert not (out / "receipts").exists() or not any((out / "receipts").iterdir())


@pytest.mark.parametrize("pair", ["x,v", "n16,v"])
def test_wave2_refuses_v_at_preflight(pair):
    import argparse

    from bench import p426_freeze as fz

    a = argparse.Namespace(lever="kv", pair=pair, arm_worktree=[], worktree_off=None, worktree_on=None)
    with pytest.raises(fz.Refusal, match="V"):
        W2._check_lever_args(a)


# ----------------------------------------------------------------------------------------------- item 1: s3 and the plan's sessions
# (c) s3 exists only under the M76 flag; P426's tables and shas are byte-identical without it
def test_s3_is_behind_the_m76_flag_only():
    import inspect

    assert "s3" in inspect.signature(schedules.tg1_legs_table).parameters
    assert inspect.signature(schedules.tg1_legs_table).parameters["s3"].default is False
    assert schedules.TG1_SEEDS_M76["s3"] == 3003 and "s3" not in schedules.TG1_SEEDS
    assert schedules.TG1_SEEDS_M76 == dict(schedules.TG1_SEEDS, s3=3003)
    assert schedules.MAKEUP_SESSION_ORDER_M76 == ("s1", "s2", "s3")


def test_a7_sessions_come_from_b7s_plan_and_the_table_follows():
    from bench import m76_rule

    look = m76_rule.axis_plan("A7")["looks"][-1]
    sessions = P.kv_a7_sessions()
    assert look["unit"] == "sessions" and sessions == tuple(f"s{i}" for i in range(1, look["size"] + 1))
    t = W2.kv_legs("n16", "x")
    names = [l["name"] for l in t["run"]]
    for s in sessions:
        assert f"tg1-m76-n16-{s}" in names and f"tg1-m76-x-{s}" in names
    assert names[0] == "tg1-m76-n16-pilot" and "tg1-m76-x-reload" in names and "tg1-m76-n16-reload" in names


def test_kv_legs_alternate_the_first_arm_per_session_and_never_name_p426():
    t = W2.kv_legs("n16", "x", sessions=("s1", "s2", "s3"))
    order = [(l["name"].rsplit("-", 1)[1], l["arm"]) for l in t["run"] if l["name"].rsplit("-", 1)[1] in ("s1", "s2", "s3")]
    assert order == [("s1", "n16"), ("s1", "x"), ("s2", "x"), ("s2", "n16"), ("s3", "n16"), ("s3", "x")]
    assert all("p426" not in l["name"] and l["name"].startswith("tg1-m76-") for l in t["run"] + t["makeup"] + t["rehearsal"])


def test_kv_legs_refuse_sessions_outside_s1_to_s3():
    for bad in (("s1",), ("s1", "s2", "s3", "s4"), ("s2", "s3")):
        with pytest.raises(ValueError):
            W2.kv_legs("n16", "x", sessions=bad)
