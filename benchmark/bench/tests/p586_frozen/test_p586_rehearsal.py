"""P589 (criterion 6) and P593's v8 field: the rehearsal schedule runs Python 1 pilot + 2 full, then Go = the first
REHEARSAL_GO_N = 2 items of s1's seeded Go order (seed 1001) in one `full` invocation; R3's stall-kill stays on the first
Python item; `p426_freeze v8` refuses an R2 invalidated on a Python slot and R1 legs without the 1 + 2 + 2 items; the v8 base
records `client_step_cap`.

The freeze world is the s8 freeze world (fake ops / checks, `bench.tests.b2_s8_support.write_leg_root`), rebuilt here.

Classes: [R] reproduces the failure the spec fixes, [I] preserves an invariant, [N] exercises new behaviour."""
from __future__ import annotations

import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import p426_freeze as fz
from bench import p426_plan
from bench import schedules
from bench.tests import b2_s8_support as S

PICK = schedules.PICK1
NAMES = {"python": [f"py-{i:02d}" for i in range(12)], "go": [f"go-{i:02d}" for i in range(9)]}


def _rehearsal():
    return schedules.tg1("chain", ["s1"], NAMES, picks=[PICK], p426=True, rehearsal=True)


def _seeded(lang):
    pool = sorted(NAMES[lang])
    return random.Random(1001).sample(pool, len(pool))


# =============================================================================================== the schedule
def test_rehearsal_schedule_is_python_1_plus_2_then_go_2(kit):
    """[R] criterion 6: one s1 block of the pick; legs Python then Go; Python = pilot [o0] + full [o1, o2] of the seeded
    Python order (unchanged); Go = ONE `full` invocation of the first 2 of s1's seeded Go order (baseline: Python only)."""
    doc = _rehearsal()
    assert schedules.REHEARSAL_GO_N == 2
    legs = schedules.legs(doc)
    assert [(lg["session"], lg["model"], lg["lang"]) for lg in legs] == [("s1", PICK, "python"), ("s1", PICK, "go")]
    py, go = _seeded("python"), _seeded("go")
    (block,) = doc["blocks"]
    pyleg, goleg = block["legs"]
    assert [(i["phase"], i["names"]) for i in pyleg["invocations"]] == [("pilot", py[:1]), ("full", py[1:3])]
    assert pyleg["full_names"] == py[:3]
    assert [(i["phase"], i["names"], i["expect"]) for i in goleg["invocations"]] == [("full", go[:2], [f"go/{n}" for n in go[:2]])]
    assert goleg["full_names"] == go[:2] and goleg["seed_base"] == 1001
    assert sum(len(lg["items"]) for lg in legs) == 5


def test_the_rehearsal_python_leg_is_unchanged(kit):
    """[I] the Python leg of the rehearsal is exactly the baseline's (1 pilot + 2 full of the seeded order, seed 1001)."""
    doc = _rehearsal()
    pyleg = doc["blocks"][0]["legs"][0]
    py = _seeded("python")
    assert pyleg["lang"] == "python" and pyleg["pilot_names"] == py[:1] and pyleg["full_names"] == py[:3]
    assert doc["p426"] is True and doc["rehearsal"] is True


def test_the_non_rehearsal_p426_schedule_is_unchanged(kit):
    """[I] the Wave-2 (non-rehearsal) schedule's sha does not move: the same dict as building it with the baseline rules."""
    doc = schedules.tg1("chain", ["s1"], NAMES, picks=[PICK], p426=True)
    py, go = _seeded("python"), _seeded("go")
    (block,) = doc["blocks"]
    assert [lg["lang"] for lg in block["legs"]] == ["python", "go"]
    assert [(i["phase"], i["names"]) for i in block["legs"][0]["invocations"]] == [("pilot", py[:5]), ("full", py[5:])]
    assert [(i["phase"], i["names"]) for i in block["legs"][1]["invocations"]] == [("full", go)]
    assert "rehearsal" not in doc


def test_the_rehearsal_shape_is_still_refused_outside_chain_s1(kit):
    """[I] `rehearsal=True` stays one P426 `chain s1` leg."""
    for kw in (dict(p426=False), dict(sessions=["s1", "s2"])):
        args = dict(mode="chain", sessions=["s1"], names=NAMES, picks=[PICK], p426=True, rehearsal=True)
        args.update(kw)
        with pytest.raises(ValueError):
            schedules.tg1(args.pop("mode"), args.pop("sessions"), args.pop("names"), **args)


# =============================================================================================== R3 stays on the first Python item
def test_r3_stall_kill_stays_on_the_first_python_item(kit, tmp_path):
    """[I] `--inject stall-kill`: the probe flags reach only the invocation holding the first Python item, never a Go one."""
    c = kit.bare_chain(tmp_path)
    c.a = SimpleNamespace(predictor="off", inject="stall-kill")
    c.schedule = _rehearsal()
    py = _seeded("python")
    seen = []
    for block in c.schedule["blocks"]:
        for leg in block["legs"]:
            for step in leg["invocations"]:
                seen.append((leg["lang"], step["phase"], c.p426_inject_stall(leg, step)))
    assert seen[0] == ("python", "pilot", (f"python/{py[0]}", 30))
    assert all(x[2] is None for x in seen[1:]), seen


# =============================================================================================== the freeze (s8 world, rebuilt)
BUILD = p426_plan.EXPECTED_BUILDS["s2"]
OFF_HEAD, ON_HEAD = "1" * 40, "2" * 40
DATE = "Tue Oct 27 2026"
R2_REASON = "reconciliation mismatch (injected)"


class FOps:
    def __init__(self, wd, off, on):
        self.wd = Path(wd)
        gl = {"src/mlx-vlm": BUILD["mlx_vlm"], "src/mlx-serve": BUILD["mlx_serve"]}
        self.state = {str(off): dict(head=OFF_HEAD, clean=True, gitlinks=dict(gl)),
                      str(on): dict(head=ON_HEAD, clean=True, gitlinks=dict(gl))}
        self.ident = {k: "d" * 64 for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")}
        self.inputs = dict(build="s2", production_ref=BUILD["production_ref"], grader_image_id="sha256:" + "e" * 64,
                           frozen_prompt_date=DATE, stack_suite_receipt_sha256="f" * 64)
        self.walls = dict(w_python_s=400.0, w_go_s=500.0, max_request_elapsed_s=60.0)

    def worktree_state(self, path):
        return self.state[str(path)]

    def identity(self, path):
        return dict(self.ident)

    def build_inputs(self):
        return dict(self.inputs)

    def historical_walls(self):
        return dict(self.walls)


@pytest.fixture
def world(tmp_path, monkeypatch):
    wd = tmp_path / "wd"
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    off, on = wd / "p426" / "stack-p426-off", wd / "p426" / "stack-p426-on"
    for wt in (off, on):
        pins = wt / "src/mlx-vlm/dev/p369_phase2/pins.json"
        pins.parent.mkdir(parents=True)
        pins.write_text('{"pins": true}')
    return dict(wd=wd, off=off, on=on, ops=FOps(wd, off, on), rehearsal=wd / "p426" / "rehearsal", rec=wd / "p426" / "record")


def _run(argv, ops, capsys):
    argv = [str(a) for a in argv]
    if argv[0] == "rehearsal":
        argv += ["--frozen-prompt-date", DATE]
    rc = fz.main(argv, ops=ops, checks=lambda kind, **kw: [])
    return rc, capsys.readouterr().err


def _slots(arm, langs):
    return [f"e|{arm}|{S.MODEL}|s1|{lang}|item{i}" for i, lang in enumerate(langs)]


R1_LANGS = ["python", "python", "python", "go", "go"]


def _schedule_like(root, slots):
    """Rewrite the leg root's frozen schedule (and chain.json's sha of it) to the rehearsal shape its slots have: per language
    one leg, Python = pilot [first] + full [rest], Go = one full invocation (the helper writes a one-language schedule)."""
    by = {}
    for s in slots:
        lang, item = s.split("|")[-2:]
        by.setdefault(lang, []).append(item)
    legs = []
    for lang, items in by.items():
        if lang == "python":
            invs = [dict(phase="pilot", names=items[:1], limit=1, expect=[f"python/{n}" for n in items[:1]])]
            if items[1:]:
                invs.append(dict(phase="full", names=items[1:], limit=None, expect=[f"python/{n}" for n in items[1:]]))
        else:
            invs = [dict(phase="full", names=items, limit=None, expect=[f"{lang}/{n}" for n in items])]
        legs.append(dict(lang=lang, full_names=list(items), invocations=invs))
    sched = dict(builder="tg1", blocks=[dict(session="s1", legs=legs)])
    (Path(root) / "schedule.json").write_text(json.dumps(sched))
    chain = json.loads((Path(root) / "chain.json").read_text())
    chain["schedule_sha256"] = schedules.schedule_sha256(sched)
    (Path(root) / "chain.json").write_text(json.dumps(chain))
    return root


def _legs(world, *, r1_langs=R1_LANGS, r2_lang="go"):
    base = world["rehearsal"]
    manifest = base / "manifest.json"
    ref = dict(path=fz.portable(manifest, world["wd"]), sha256=json.loads(manifest.read_text())["sha256"])
    r1_off = _schedule_like(S.write_leg_root(base / "tg1-p426-rehearsal-off.a1", arm="off", leg="tg1-p426-rehearsal-off",
                                             slots=_slots("off", r1_langs), frozen_record=ref), _slots("off", r1_langs))
    r1_on = _schedule_like(S.write_leg_root(base / "tg1-p426-rehearsal-on.a1", arm="on", leg="tg1-p426-rehearsal-on",
                                            slots=_slots("on", r1_langs), frozen_record=ref), _slots("on", r1_langs))
    r2_slots = _slots("on", ["python", "python", "python"])
    bad = f"e|on|{S.MODEL}|s1|{r2_lang}|item9"
    r2 = S.write_leg_root(base / "tg1-p426-rehearsal-mismatch.a1", arm="on", leg="tg1-p426-rehearsal-mismatch", slots=r2_slots,
                          state="INVALID", klass="systemic", reason=R2_REASON, rc=2, status="invalidated",
                          invalid=[dict(stage="done", slot=bad, reason=R2_REASON, at="t")], frozen_record=ref,
                          inject="reconcile-mismatch")
    r3 = S.write_leg_root(base / "tg1-p426-rehearsal-kill.a1", arm="off", leg="tg1-p426-rehearsal-kill", items=2, kill=True,
                          frozen_record=ref, inject="stall-kill")
    return dict(r1_off=r1_off, r1_on=r1_on, r2=r2, r3=r3)


def _v8(world, capsys, **kw):
    manifest = world["rehearsal"] / "manifest.json"
    rc, err = _run(["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root",
                    world["rehearsal"] / "stage", "--out", manifest], world["ops"], capsys)
    assert rc == 0, err
    legs = _legs(world, **kw)
    out = world["rec"] / "v8_base.json"
    rc, err = _run(["v8", "--off-worktree", world["off"], "--on-worktree", world["on"], "--rehearsal-manifest", manifest,
                    "--r1-off", legs["r1_off"], "--r1-on", legs["r1_on"], "--r2", legs["r2"], "--r3", legs["r3"], "--out", out],
                   world["ops"], capsys)
    return rc, err, out


def test_v8_accepts_the_go_rehearsal_shape(world, capsys):
    """[I] R1 legs with 3 Python + 2 Go items, R2 invalidated on a Go slot: v8 is written."""
    rc, err, out = _v8(world, capsys)
    assert rc == 0, err
    assert out.exists()


def test_v8_base_records_the_client_step_cap(world, capsys):
    """[N] P593: the v8 base record carries `client_step_cap = {seconds: 3600, source, bound_by: opencode_exe_sha256}`;
    `scaffold_policy_sha256` is the identity's, unchanged."""
    rc, err, out = _v8(world, capsys)
    assert rc == 0, err
    doc = json.loads(out.read_text())
    assert doc["client_step_cap"] == dict(seconds=3600, source=S_CAP_SOURCE, bound_by="opencode_exe_sha256")
    assert doc["scaffold_policy_sha256"] == "d" * 64


S_CAP_SOURCE = "opencode 2.0.20 LocationActivity timeToLive default (C154); not configurable"


def test_v8_refuses_an_r2_invalidated_on_a_python_slot(world, capsys):
    """[R] criterion 6: R2's invalidated slot must be a Go slot (baseline: any slot)."""
    rc, err, out = _v8(world, capsys, r2_lang="python")
    assert rc == 2 and err.startswith("REFUSED:") and "R2" in err
    assert not out.exists()


@pytest.mark.parametrize("langs", [["python", "python", "python"], ["python"] * 5, ["python", "python", "python", "go"],
                                   ["python", "python", "python", "go", "go", "go"]],
                         ids=["python-only-3", "python-only-5", "one-go", "three-go"])
def test_v8_refuses_r1_legs_without_the_1_2_2_items(world, capsys, langs):
    """[R] criterion 6: R1's legs hold the 1 + 2 + 2 items (3 Python, 2 Go); anything else refuses naming R1."""
    rc, err, out = _v8(world, capsys, r1_langs=langs)
    assert rc == 2 and err.startswith("REFUSED:") and "R1" in err
    assert not out.exists()
