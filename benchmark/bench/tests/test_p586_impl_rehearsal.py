"""P589 (implementer's red-first tests): the rehearsal runs Go; R2 invalidates on the first Go item; the freeze checks that shape."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from bench import p426_hooks as ph
from bench import schedules
from bench.tests import test_b2_s4_reconcile as T

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
NAMES = {"python": [f"p{i}" for i in range(1, 9)], "go": [f"g{i}" for i in range(1, 9)]}


def order(lang, seed=1001):
    return random.Random(seed).sample(sorted(NAMES[lang]), len(NAMES[lang]))


def test_the_rehearsal_schedule_is_one_pilot_two_full_python_then_two_go():
    sched = schedules.tg1("chain", ["s1"], NAMES, picks=(MODEL,), p426=True, rehearsal=True)
    (block,) = sched["blocks"]
    py, go = block["legs"]
    assert (py["lang"], go["lang"]) == ("python", "go") and py["seed_base"] == go["seed_base"] == 1001
    assert py["full_names"] == order("python")[:3] and py["pilot_names"] == order("python")[:1]
    assert [(i["phase"], i["names"]) for i in py["invocations"]] == [("pilot", order("python")[:1]), ("full", order("python")[1:3])]
    assert schedules.REHEARSAL_GO_N == 2
    assert go["full_names"] == order("go")[:2]
    assert [(i["phase"], i["names"], i["expect"]) for i in go["invocations"]] == [
        ("full", order("go")[:2], [f"go/{n}" for n in order("go")[:2]])]
    assert sched["rehearsal"] is True


def test_the_non_rehearsal_schedules_are_unchanged():
    plain = schedules.tg1("chain", ["s1"], NAMES, picks=(MODEL,), p426=True)
    assert [l["lang"] for l in plain["blocks"][0]["legs"]] == ["python", "go"]
    assert len(plain["blocks"][0]["legs"][1]["full_names"]) == 8


# -- R2's injection: the first `done` of a Go item
SLOT_PY, SLOT_GO = f"0|A|{MODEL}|s1|python|a", f"0|A|{MODEL}|s1|go|b"


def injected_hooks(tmp_path):
    ops, _, out = T.make_hooks(tmp_path)
    hooks = ph.P426Hooks(ops=ops, out_root=out, arm="ON", settle_bound_s=10.0, clock=T.Clock(), sleep=T.Clock().sleep,
                         inject="reconcile-mismatch")
    hooks.bind_router(5, 2.0)
    return ops, hooks


def serve_item(ops, hooks, slot, lang_item, k):
    hooks.before_attempt(slot, T.ctx(slot=slot, item=lang_item.split("/")[1], k=k))
    ops.serve(*T.req(prompt=100, gen=10, draft=T.ON_DRAFT))
    return hooks.after_attempt(slot, dict(id=lang_item), T.ctx(T.row_of([(100, 10)]), slot=slot, item=lang_item.split("/")[1], k=k))


def test_the_injection_skips_python_items_and_perturbs_the_first_go_item(tmp_path):
    ops, hooks = injected_hooks(tmp_path)
    assert serve_item(ops, hooks, SLOT_PY, "python/a", 0).kind == "accept"
    d = serve_item(ops, hooks, SLOT_GO, "go/b", 1)
    assert d.kind == "invalidate" and d.reason == ph.INJECTED_MISMATCH


def test_the_injection_perturbs_only_the_first_go_item(tmp_path):
    ops, hooks = injected_hooks(tmp_path)
    assert serve_item(ops, hooks, SLOT_GO, "go/b", 0).kind == "invalidate"
    slot2 = f"0|A|{MODEL}|s1|go|c"
    assert serve_item(ops, hooks, slot2, "go/c", 1).kind == "accept"


def test_no_injection_leaves_a_go_item_alone(tmp_path):
    ops, _, out = T.make_hooks(tmp_path)
    hooks = ph.P426Hooks(ops=ops, out_root=out, arm="ON", settle_bound_s=10.0, clock=T.Clock(), sleep=T.Clock().sleep)
    hooks.bind_router(5, 2.0)
    assert serve_item(ops, hooks, SLOT_GO, "go/b", 0).kind == "accept"


# -- the freeze: the rehearsal's shape (hermetic: a chain.json with a ledger is all the helpers read)
PINS = Path(__file__).resolve().parents[3] / "src/mlx-vlm/dev/p369_phase2/pins.json"
needs_fork = pytest.mark.skipif(not PINS.exists(), reason="the freeze world fixtures need the src/mlx-vlm submodule checkout")


def ledger_root(tmp_path, langs):
    root = tmp_path / "leg"
    root.mkdir(parents=True)
    slots = [f"tg1-p426|oc|{MODEL}|s1|{lang}|{lang[0]}{i}" for lang, n in langs for i in range(n)]
    (root / "chain.json").write_text(json.dumps(dict(p426_ledger=[dict(slot=s, kind="row") for s in slots])))
    return root


def test_r1_shape_problems_accept_only_three_python_and_two_go(tmp_path):
    from bench import p426_freeze as fz
    assert fz.r1_shape_problems(ledger_root(tmp_path / "a", [("python", 3), ("go", 2)])) == []
    for i, shape in enumerate([[("python", 5)], [("python", 3), ("go", 1)], [("python", 2), ("go", 3)], [("python", 3), ("go", 2), ("rust", 1)]]):
        (p,) = fz.r1_shape_problems(ledger_root(tmp_path / f"b{i}", shape))
        assert "1 + 2 + 2" in p


def test_r2_slot_problems_need_a_go_slot():
    from bench import p426_freeze as fz
    assert fz.r2_slot_problems([dict(slot=f"tg1-p426|oc|{MODEL}|s1|go|g2")]) == []
    (p,) = fz.r2_slot_problems([dict(slot=f"tg1-p426|oc|{MODEL}|s1|python|p2")])
    assert p.startswith("R2") and "Go slot" in p
    assert fz.r2_slot_problems([])


def freeze_world(tmp_path, **leg_kw):
    from bench import p426_freeze as fz
    from bench.tests import b2_frozen_support as S
    from bench.tests import test_b2_frozen_s8_freeze as F
    manifest = S.write_record(tmp_path / "wd/rec" / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal/r1"))
    roots = [F.leg_root_with(tmp_path, f"{n}.a1", st, manifest=manifest, **leg_kw.get(n, {}))
             for n, st in (("tg1-p426-rehearsal-off", "VALID"), ("tg1-p426-rehearsal-on", "VALID"),
                           ("tg1-p426-rehearsal-mismatch", "INVALID"), ("tg1-p426-rehearsal-kill", "VALID"))]
    ops = type("Ops", (), dict(r1_differences=lambda self, a, b: []))()
    return fz.rehearsal_problems(*roots, ops, manifest_path=manifest, manifest_sha=json.loads(Path(manifest).read_text())["sha256"],
                                 wd=tmp_path / "wd")[0]


@needs_fork
def test_a_rehearsal_in_the_new_shape_passes_the_shape_checks(tmp_path):
    problems = freeze_world(tmp_path)
    assert [p for p in problems if "1 + 2 + 2" in p or "Go slot" in p] == [], problems


@needs_fork
def test_r1_legs_must_hold_one_pilot_two_full_python_and_two_go_items(tmp_path):
    problems = freeze_world(tmp_path, **{"tg1-p426-rehearsal-off": dict(shape=[("python", 5)])})
    assert any("R1 off" in p and "1 + 2 + 2" in p for p in problems), problems
    problems = freeze_world(tmp_path / "b", **{"tg1-p426-rehearsal-on": dict(shape=[("python", 3), ("go", 1)])})
    assert any("R1 on" in p and "1 + 2 + 2" in p for p in problems), problems


@needs_fork
def test_r2_invalidated_on_a_python_slot_is_refused(tmp_path):
    problems = freeze_world(tmp_path, **{"tg1-p426-rehearsal-mismatch": dict(invalid_lang="python")})
    assert any(p.startswith("R2") and "Go slot" in p for p in problems), problems


from bench.tests.test_b2_s8_freeze import world  # noqa: E402,F401  (the freeze suite's self-contained fixture)


def test_a_v8_freeze_of_the_new_rehearsal_shape_writes_the_client_step_cap(world, capsys):
    from bench.tests import test_b2_s8_freeze as TF
    rc, err, out, _m, _legs = TF.make_v8(world, capsys)
    assert rc == 0, err
    doc = json.loads(Path(out).read_text())
    assert doc["client_step_cap"] == dict(seconds=3600, bound_by="opencode_exe_sha256",
                                          source="opencode 2.0.20 LocationActivity timeToLive default (C154); not configurable")
    assert "scaffold_policy_sha256" in doc


def test_a_v8_freeze_refuses_an_r2_invalidated_on_a_python_slot(world, capsys):
    from bench.tests import test_b2_s8_freeze as TF
    manifest = TF.make_manifest(world, capsys)
    legs = TF.make_rehearsal_legs(world)
    chain = Path(legs["r2"]) / "chain.json"
    doc = json.loads(chain.read_text())
    doc["p426_invalid"][0]["slot"] = TF.S.slot("on", "s1", 0, "python")
    chain.write_text(json.dumps(doc))
    rc, err = TF.run(TF.v8_argv(world, manifest, legs, world["rec"] / "v8_base.json"), world["ops"], capsys=capsys)
    assert rc == 2 and "R2" in err and "Go slot" in err


def test_a_v8_freeze_refuses_an_r1_leg_of_the_old_shape(world, capsys):
    from bench.tests import test_b2_s8_freeze as TF
    manifest = TF.make_manifest(world, capsys)
    legs = TF.make_rehearsal_legs(world)
    chain = Path(legs["r1_off"]) / "chain.json"
    doc = json.loads(chain.read_text())
    doc["p426_ledger"] = doc["p426_ledger"][:3]
    chain.write_text(json.dumps(doc))
    rc, err = TF.run(TF.v8_argv(world, manifest, legs, world["rec"] / "v8_base.json"), world["ops"], capsys=capsys)
    assert rc == 2 and "R1 off" in err and "1 + 2 + 2" in err


def test_the_freeze_does_not_count_the_two_client_abort_cases_as_kill_cases():
    """X4 (fix round 1): R3 certifies the probe's kill; a client abort is not one (pinned the opposite before)."""
    from bench import p426_freeze as fz
    assert not {"kill_client_aborted", "kill_client_aborted_completed_unaccounted"} & set(fz.KILL_CASES)
    _ = pytest
