"""B2 slice s8, part 1 (spec docs/specs/p426-b2-tg1-wave2.md v3.2, sections 1, 10.1, 10.2, 16.1, 16.2, 16.7): `bench.p426_freeze` - the
rehearsal manifest, the v8 base and the timeout amendment. Hermetic: every workdir is under `tmp_path`, `ops` / `checks` are fakes
(no git, no docker, no probe process); no registry is read."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bench import p426_freeze as fz
from bench import p426_hooks as ph
from bench import p426_plan
from bench import p426_record
from bench.tests import b2_s8_support as S

BUILD = p426_plan.EXPECTED_BUILDS["s2"]
OFF_HEAD, ON_HEAD = "1" * 40, "2" * 40
PINS = '{"pins": true}'
DATE = "Tue Oct 27 2026"


class FOps:
    """The `ops` seams of `p426_freeze` (spec 16.4 `worktree_state`, 16.7 `build_inputs`), faked."""

    def __init__(self, wd, off, on):
        self.wd = Path(wd)
        gl = {"src/mlx-vlm": BUILD["mlx_vlm"], "src/mlx-serve": BUILD["mlx_serve"]}
        self.state = {str(off): dict(head=OFF_HEAD, clean=True, gitlinks=dict(gl)),
                      str(on): dict(head=ON_HEAD, clean=True, gitlinks=dict(gl))}
        self.ident = {k: "d" * 64 for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")}
        self.ident_by = {}
        self.inputs = dict(build="s2", production_ref=BUILD["production_ref"], grader_image_id="sha256:" + "e" * 64,
                           frozen_prompt_date=DATE, stack_suite_receipt_sha256="f" * 64)
        self.walls = dict(w_python_s=400.0, w_go_s=500.0, max_request_elapsed_s=60.0)

    def worktree_state(self, path):
        return self.state[str(path)]

    def identity(self, path):
        return dict(self.ident_by.get(str(path), self.ident))

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
        pins.write_text(PINS)
    return dict(wd=wd, off=off, on=on, ops=FOps(wd, off, on), rehearsal=wd / "p426" / "rehearsal", rec=wd / "p426" / "record")


def run(argv, ops, checks=None, capsys=None, date=True):
    argv = [str(a) for a in argv]
    if date and argv[0] == "rehearsal" and "--frozen-prompt-date" not in argv:          # §16.8: the rehearsal command requires it
        argv += ["--frozen-prompt-date", DATE]
    rc = fz.main(argv, ops=ops, checks=checks or (lambda kind, **kw: []))
    err = capsys.readouterr().err if capsys else ""
    return rc, err


def make_manifest(world, capsys=None):
    out = world["rehearsal"] / "manifest.json"
    rc, err = run(["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root", world["rehearsal"] / "stage",
                   "--out", out], world["ops"], capsys=capsys)
    assert rc == 0, err
    return out


def make_rehearsal_legs(world, *, r2_reason="reconciliation mismatch (injected)", r2_state="INVALID", r3_kill=True,
                        r1_on_env=None, r1_state="VALID", r3_state="VALID", r1_elapsed=50.0):
    base = world["rehearsal"]
    manifest = base / "manifest.json"             # the legs ran under THIS manifest (fix round 3, item 7): its path and sha256
    ref = dict(path=fz.portable(manifest, world["wd"]), sha256=doc_of(manifest)["sha256"]) if manifest.exists() else None
    r1_off = S.write_leg_root(base / "tg1-p426-rehearsal-off.a1", arm="off", leg="tg1-p426-rehearsal-off", items=3, elapsed=r1_elapsed,
                              frozen_record=ref)
    r1_on = S.write_leg_root(base / "tg1-p426-rehearsal-on.a1", arm="on", leg="tg1-p426-rehearsal-on", items=3, state=r1_state,
                             receipt_doc=S.receipt("on", env_extra=r1_on_env), elapsed=r1_elapsed, frozen_record=ref)
    r2 = S.write_leg_root(base / "tg1-p426-rehearsal-mismatch.a1", arm="on", leg="tg1-p426-rehearsal-mismatch", items=1,
                          state=r2_state, klass="systemic", reason=r2_reason, rc=2, status="invalidated",
                          invalid=[dict(stage="done", slot="x", reason=r2_reason, at="t")], frozen_record=ref,
                          inject="reconcile-mismatch")
    r3 = S.write_leg_root(base / "tg1-p426-rehearsal-kill.a1", arm="off", leg="tg1-p426-rehearsal-kill", items=2, kill=r3_kill,
                          state=r3_state, frozen_record=ref, inject="stall-kill")
    return dict(r1_off=r1_off, r1_on=r1_on, r2=r2, r3=r3)


def v8_argv(world, manifest, legs, out):
    return ["v8", "--off-worktree", world["off"], "--on-worktree", world["on"], "--rehearsal-manifest", manifest,
            "--r1-off", legs["r1_off"], "--r1-on", legs["r1_on"], "--r2", legs["r2"], "--r3", legs["r3"], "--out", out]


def make_v8(world, capsys=None, **kw):
    manifest = make_manifest(world, capsys)
    legs = make_rehearsal_legs(world, **kw)
    out = world["rec"] / "v8_base.json"
    rc, err = run(v8_argv(world, manifest, legs, out), world["ops"], capsys=capsys)
    return rc, err, out, manifest, legs


def doc_of(path):
    return json.loads(Path(path).read_text())


# ----------------------------------------------------------------------------------------------- rehearsal manifest
def test_rehearsal_manifest_is_sealed_exclusive_and_portable(world, capsys):
    out = make_manifest(world, capsys)
    doc = doc_of(out)
    assert ph.sealed_ok(doc)
    assert doc["kind"] == "p426_rehearsal" and doc["rehearsal"] is True
    assert (doc["off_commit"], doc["on_commit"]) == (OFF_HEAD, ON_HEAD)
    assert doc["off_worktree"] == "$STACK_WORKDIR/p426/stack-p426-off" and doc["on_worktree"] == "$STACK_WORKDIR/p426/stack-p426-on"
    assert doc["out_root"] == "$STACK_WORKDIR/p426/rehearsal/stage" and doc["created"]
    assert doc["frozen_prompt_date"] == DATE                                           # §16.8: the date and ops.identity(off_worktree)
    assert {k: doc[k] for k in fz.IDENTITY_KEYS} == world["ops"].ident
    assert str(world["wd"]) not in out.read_text()
    before = out.read_bytes()
    rc, err = run(["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root",
                   world["rehearsal"] / "stage2", "--out", out], world["ops"], capsys=capsys)
    assert rc == 2 and err.startswith("REFUSED:") and "exists" in err
    assert out.read_bytes() == before


@pytest.mark.parametrize("mutate,needle", [
    (lambda w: w["ops"].state[str(w["off"])].update(clean=False), "not clean"),
    (lambda w: w["ops"].state[str(w["on"])].update(clean=False), "not clean"),
    (lambda w: w["ops"].state[str(w["on"])].update(head=OFF_HEAD), "same commit"),
    (lambda w: w["ops"].state[str(w["on"])]["gitlinks"].update({"src/mlx-vlm": "9" * 40}), "gitlink"),
])
def test_rehearsal_refuses_a_changed_input(world, capsys, mutate, needle):
    mutate(world)
    out = world["rehearsal"] / "manifest.json"
    rc, err = run(["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root", world["rehearsal"] / "stage",
                   "--out", out], world["ops"], capsys=capsys)
    assert rc == 2 and err.startswith("REFUSED:") and needle in err
    assert not out.exists()


def test_rehearsal_out_root_must_lie_under_the_rehearsal_directory(world, capsys):
    out = world["rehearsal"] / "manifest.json"
    rc, err = run(["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root",
                   world["wd"] / "p426" / "wave2", "--out", out], world["ops"], capsys=capsys)
    assert rc == 2 and "--out-root" in err and not out.exists()


def test_rehearsal_failed_precondition_writes_nothing(world, capsys):
    out = world["rehearsal"] / "manifest.json"
    rc, err = run(["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root", world["rehearsal"] / "s",
                   "--out", out], world["ops"], checks=lambda kind, **kw: ["venv .venv-bench is not synced to its lock"], capsys=capsys)
    assert rc == 2 and "venv .venv-bench" in err and not out.exists()


def test_rehearsal_requires_a_valid_frozen_prompt_date(world, capsys):
    out = world["rehearsal"] / "manifest.json"
    args = ["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root", world["rehearsal"] / "s", "--out", out]
    rc, err = run(args, world["ops"], capsys=capsys, date=False)
    assert rc == 2 and "--frozen-prompt-date" in err and not out.exists()
    rc, err = run([*args, "--frozen-prompt-date", "today"], world["ops"], capsys=capsys)
    assert rc == 2 and "--frozen-prompt-date" in err and not out.exists()


def test_the_restore_diff_goes_through_checks_not_an_ops_seam(world, capsys):
    """P59: the restore diff is a precondition (`checks`), the ops fake has no such seam, and a failing check refuses."""
    assert not hasattr(world["ops"], "restore_diff_problems")
    seen = []
    out = world["rehearsal"] / "manifest.json"
    args = ["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root", world["rehearsal"] / "s", "--out", out]
    rc, err = run(args, world["ops"], checks=lambda kind, **kw: seen.append(kind) or ["restore diff: the restore commit changes more"],
                  capsys=capsys)
    assert rc == 2 and "restore diff" in err and seen == ["rehearsal"] and not out.exists()


def test_the_default_checks_run_the_restore_diff(world, monkeypatch):
    calls = []
    monkeypatch.setattr(fz.p426_plan, "restore_diff_problems", lambda off, on, entry: calls.append((str(off), str(on))) or ["restore bad"])
    monkeypatch.setattr(fz, "entry_point_problems", lambda wt: [])
    got = fz.default_checks("rehearsal", off_worktree=world["off"], on_worktree=world["on"])
    assert got == ["restore diff: restore bad"] and calls == [(str(world["off"]), str(world["on"]))]


def test_a_failing_restore_diff_refuses_naming_it_through_the_default_checks(world, capsys, monkeypatch):
    """Item 0: the REFUSED line itself says `restore diff`, whatever text the plan's own problem carries."""
    monkeypatch.setattr(fz.p426_plan, "restore_diff_problems", lambda off, on, entry: ["the ON HEAD is not the OFF HEAD plus exactly one commit"])
    monkeypatch.setattr(fz, "entry_point_problems", lambda wt: [])
    out = world["rehearsal"] / "manifest.json"
    rc = fz.main(["rehearsal", "--off-worktree", str(world["off"]), "--on-worktree", str(world["on"]), "--out-root",
                  str(world["rehearsal"] / "s"), "--out", str(out), "--frozen-prompt-date", DATE], ops=world["ops"])
    err = capsys.readouterr().err
    assert rc == 2 and err.startswith("REFUSED:") and "restore diff" in err and err.count("\n") == 1 and not out.exists()


def test_checks_receive_the_kind_and_both_worktrees(world, capsys):
    seen = []
    out = world["rehearsal"] / "manifest.json"
    run(["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root", world["rehearsal"] / "s", "--out", out],
        world["ops"], checks=lambda kind, **kw: seen.append((kind, sorted(kw))) or [], capsys=capsys)
    assert seen == [("rehearsal", ["off_worktree", "on_worktree"])]


# ----------------------------------------------------------------------------------------------- v8 base
def test_v8_base_records_the_derived_inputs_sealed(world, capsys):
    rc, err, out, manifest, _legs = make_v8(world, capsys)
    assert rc == 0, err
    doc = doc_of(out)
    assert ph.sealed_ok(doc) and doc["kind"] == "p426_v8_base" and doc["build"] == "s2"
    assert (doc["off_commit"], doc["on_commit"]) == (OFF_HEAD, ON_HEAD)
    assert doc["off_worktree"].startswith("$STACK_WORKDIR/") and doc["on_worktree"].startswith("$STACK_WORKDIR/")
    assert doc["gitlinks"] == {"mlx_vlm": BUILD["mlx_vlm"], "mlx_serve": BUILD["mlx_serve"]}
    assert doc["production_ref"] == BUILD["production_ref"]
    for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256"):
        assert doc[k] == "d" * 64
    assert doc["pins_sha256"] == hashlib.sha256(PINS.encode()).hexdigest()
    assert doc["grader_image_id"] == "sha256:" + "e" * 64 and doc["frozen_prompt_date"] == DATE
    assert doc["pilot_deadline_s"] == 1.5 * 5 * 400.0 + 1800
    assert doc["settle_bound_s"] == 900.0 and doc["generic_pred_s"] == 250        # max(900, 2 x max(R1 50 s, historical 60 s))
    assert doc["volatile_env_keys"] == ["_", "OLDPWD", "PWD", "SHLVL", "TERM_SESSION_ID", "SECURITYSESSIONID", "__CF*"]
    assert doc["rehearsal_manifest_sha256"] == doc_of(manifest)["sha256"]
    assert doc["stack_suite_receipt_sha256"] == "f" * 64
    assert doc["r1_env_difference"] == [e for e in doc["r1_env_difference"] if e["field"] in ("argv.worker", "snapshots.drafter")
                                        or e["field"].startswith("env.")]
    assert {e["field"] for e in doc["r1_env_difference"]} >= {"argv.worker", "snapshots.drafter"}
    assert str(world["wd"]) not in out.read_text()


def test_v8_base_is_exclusive_created(world, capsys):
    rc, _err, out, manifest, legs = make_v8(world, capsys)
    before = out.read_bytes()
    rc, err = run(v8_argv(world, manifest, legs, out), world["ops"], capsys=capsys)
    assert rc == 2 and "exists" in err and out.read_bytes() == before


@pytest.mark.parametrize("kw,needle", [
    (dict(r1_state="INVALID"), "R1"),
    (dict(r2_state="VALID"), "R2"),
    (dict(r2_reason="the item barrier timed out"), "R2"),
    (dict(r2_reason="reconciliation mismatch"), "R2"),                                # §16.8: the exact reason, not a near miss
    (dict(r2_reason="reconciliation mismatch (injected) and more"), "R2"),
    (dict(r3_state="INVALID"), "R3"),
    (dict(r3_kill=False), "R3"),
    (dict(r1_on_env={"MLX_SOMETHING": "1"}), "R1"),
])
def test_v8_refuses_unless_r1_valid_r2_invalid_for_the_injected_reason_and_r3_valid(world, capsys, kw, needle):
    rc, err, out, _m, _l = make_v8(world, capsys, **kw)
    assert rc == 2 and err.startswith("REFUSED:") and needle in err
    assert not out.exists()


def test_v8_refuses_a_tampered_leg_record(world, capsys):
    manifest = make_manifest(world, capsys)
    legs = make_rehearsal_legs(world)
    p = legs["r1_off"] / "leg.json"
    p.write_text(p.read_text().replace('"VALID"', '"INVALID"'))
    rc, err = run(v8_argv(world, manifest, legs, world["rec"] / "v8_base.json"), world["ops"], capsys=capsys)
    assert rc == 2 and "sha256" in err


def test_v8_refuses_an_r1_on_leg_with_a_missing_engagement_counter(world, capsys):
    manifest = make_manifest(world, capsys)
    base = world["rehearsal"]
    legs = make_rehearsal_legs(world)
    import shutil
    shutil.rmtree(legs["r1_on"])
    legs["r1_on"] = S.write_leg_root(base / "tg1-p426-rehearsal-on.a1", arm="on", leg="tg1-p426-rehearsal-on", items=3,
                                     engagement_ok=False)
    rc, err = run(v8_argv(world, manifest, legs, world["rec"] / "v8_base.json"), world["ops"], capsys=capsys)
    assert rc == 2 and "R1" in err and "request" in err


@pytest.mark.parametrize("mutate,needle", [
    (lambda w: w["ops"].state[str(w["off"])].update(clean=False), "not clean"),
    (lambda w: w["ops"].state[str(w["on"])]["gitlinks"].update({"src/mlx-serve": "9" * 40}), "gitlink"),
    (lambda w: w["ops"].state[str(w["off"])]["gitlinks"].update({"src/mlx-serve": "9" * 40, "src/mlx-vlm": "9" * 40})
     or w["ops"].state[str(w["on"])]["gitlinks"].update({"src/mlx-serve": "9" * 40, "src/mlx-vlm": "9" * 40}), "build"),
    (lambda w: w["ops"].ident_by.update({str(w["on"]): {"probe_code_sha256": "0" * 64, "scaffold_policy_sha256": "d" * 64,
                                                       "generation_identity_sha256": "d" * 64}}), "probe_code_sha256"),
    (lambda w: w["ops"].inputs.update(production_ref="0" * 40), "production_ref"),
    (lambda w: w["ops"].inputs.update(frozen_prompt_date=None), "frozen_prompt_date"),
    (lambda w: w["ops"].inputs.update(frozen_prompt_date="today"), "frozen_prompt_date"),
    (lambda w: w["ops"].inputs.update(grader_image_id=""), "grader_image_id"),
    (lambda w: w["ops"].inputs.update(build="nope"), "build"),
    (lambda w: (w["on"] / "src/mlx-vlm/dev/p369_phase2/pins.json").write_text('{"pins": false}'), "pins"),
])
def test_v8_refuses_a_changed_input(world, capsys, mutate, needle):
    manifest = make_manifest(world, capsys)          # the manifest is made on the unmutated world
    legs = make_rehearsal_legs(world)
    mutate(world)
    out = world["rec"] / "v8_base.json"
    rc, err = run(v8_argv(world, manifest, legs, out), world["ops"], capsys=capsys)
    assert rc == 2 and err.startswith("REFUSED:") and needle in err
    assert not out.exists()


def test_v8_refuses_failing_preconditions_and_names_them(world, capsys):
    manifest = make_manifest(world, capsys)
    legs = make_rehearsal_legs(world)
    out = world["rec"] / "v8_base.json"
    rc, err = run(v8_argv(world, manifest, legs, out), world["ops"],
                  checks=lambda kind, **kw: ["no stack suite receipt", "venv drift"] if kind == "v8" else [], capsys=capsys)
    assert rc == 2 and "no stack suite receipt" in err and "venv drift" in err and not out.exists()


def test_v8_checks_get_the_restore_diff_inputs_and_the_production_tree_inputs(world, capsys):
    manifest = make_manifest(world, capsys)
    legs = make_rehearsal_legs(world)
    seen = {}
    rc, err = run(v8_argv(world, manifest, legs, world["rec"] / "v8_base.json"), world["ops"],
                  checks=lambda kind, **kw: seen.update({kind: kw}) or [], capsys=capsys)
    assert rc == 0, err
    kw = seen["v8"]
    assert kw["build"] == "s2" and kw["production_ref"] == BUILD["production_ref"]
    assert kw["gitlinks"] == {"mlx_vlm": BUILD["mlx_vlm"], "mlx_serve": BUILD["mlx_serve"]}


def git(cwd, *args):
    import subprocess
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_production_tree_problems_compare_the_fork_tree_with_the_refs_tree_excluding_tests(tmp_path):
    """P62: `git diff --quiet <ref> <gitlink> -- mlx_vlm ':!mlx_vlm/tests'` in the worktree's `src/mlx-vlm`."""
    wt, fork = tmp_path / "wt", tmp_path / "wt" / "src" / "mlx-vlm"
    (fork / "mlx_vlm" / "tests").mkdir(parents=True)
    git(fork, "init", "-q")
    (fork / "mlx_vlm" / "a.py").write_text("x = 1\n")
    (fork / "mlx_vlm" / "tests" / "t.py").write_text("t = 1\n")
    git(fork, "add", "-A")
    git(fork, "commit", "-qm", "ref")
    ref = git(fork, "rev-parse", "HEAD")
    (fork / "mlx_vlm" / "tests" / "t.py").write_text("t = 2\n")                    # a tests-only change is allowed
    (fork / "dev").mkdir()
    (fork / "dev" / "d.py").write_text("d = 1\n")                                   # outside mlx_vlm/ is not compared
    git(fork, "add", "-A")
    git(fork, "commit", "-qm", "tests only")
    assert fz.production_tree_problems(wt, ref, git(fork, "rev-parse", "HEAD")) == []
    (fork / "mlx_vlm" / "a.py").write_text("x = 2\n")
    git(fork, "add", "-A")
    git(fork, "commit", "-qm", "production")
    got = fz.production_tree_problems(wt, ref, git(fork, "rev-parse", "HEAD"))
    assert got and "production" in got[0] and ref[:12] in got[0]
    assert fz.production_tree_problems(wt, "0" * 40, git(fork, "rev-parse", "HEAD"))          # an unknown ref is a problem, not a crash


def test_default_checks_run_the_production_tree_check_for_both_arms_in_v8(world, monkeypatch):
    calls = []
    monkeypatch.setattr(fz.p426_plan, "restore_diff_problems", lambda off, on, entry: [])
    monkeypatch.setattr(fz, "entry_point_problems", lambda wt: [])
    monkeypatch.setattr(fz, "venv_problems", lambda wt, build: [])
    monkeypatch.setattr(fz, "help_problems", lambda wt: [])
    monkeypatch.setattr(fz, "production_tree_problems", lambda wt, ref, link: calls.append((Path(wt).name, ref, link)) or ["tree differs"])
    got = fz.default_checks("v8", off_worktree=world["off"], on_worktree=world["on"], build="s2", production_ref="r" * 40,
                            gitlinks={"mlx_vlm": "g" * 40, "mlx_serve": "h" * 40})
    assert calls == [("stack-p426-off", "r" * 40, "g" * 40), ("stack-p426-on", "r" * 40, "g" * 40)]
    assert got == ["off: tree differs", "on: tree differs"]


# -- settle bound (§4.2 / §16.8): derived, never typed
def test_v8_settle_bound_is_twice_the_largest_request_elapsed_of_r1_and_the_history(world, capsys):
    world["ops"].walls["max_request_elapsed_s"] = 800.0
    rc, err, out, *_ = make_v8(world, capsys, r1_elapsed=700.0)
    assert rc == 0, err
    assert doc_of(out)["settle_bound_s"] == 1600.0                                    # 2 x max(700, 800)
    world["ops"].walls["max_request_elapsed_s"] = 100.0


def test_v8_settle_bound_takes_the_larger_r1_elapsed_and_never_a_typed_input(world, capsys):
    world["ops"].inputs["settle_bound_s"] = 99999.0                                  # a typed bound is ignored
    rc, err, out, *_ = make_v8(world, capsys, r1_elapsed=1000.0)
    assert rc == 0, err
    assert doc_of(out)["settle_bound_s"] == 2000.0


def test_v8_settle_bound_refuses_without_elapsed_in_r1_or_the_history(world, capsys):
    del world["ops"].walls["max_request_elapsed_s"]
    rc, err, out, *_ = make_v8(world, capsys)
    assert rc == 2 and "max_request_elapsed_s" in err and not out.exists()
    world["ops"].walls["max_request_elapsed_s"] = 60.0
    import shutil
    shutil.rmtree(world["rehearsal"])
    rc, err, out, *_ = make_v8(world, capsys, r1_elapsed=None)                    # R1's item records carry no request elapsed_s
    assert rc == 2 and "elapsed_s" in err and not out.exists()


def test_v8_refuses_a_missing_seam_never_a_traceback(world, capsys):
    manifest = make_manifest(world, capsys)
    legs = make_rehearsal_legs(world)
    for seam in ("worktree_state", "identity", "historical_walls", "build_inputs"):
        ops = Without(world["ops"], seam)
        rc, err = run(v8_argv(world, manifest, legs, world["rec"] / f"v8-{seam}.json"), ops, capsys=capsys)
        assert rc == 2 and err.startswith("REFUSED:") and seam in err and err.count("\n") == 1, (seam, err)


class Without:
    """`ops` with one seam missing."""

    def __init__(self, ops, name):
        self._ops, self._name = ops, name

    def __getattr__(self, attr):
        if attr == self._name:
            raise AttributeError(attr)
        return getattr(self._ops, attr)


def test_rehearsal_and_amend_refuse_a_missing_seam(world, capsys):
    out = world["rehearsal"] / "manifest.json"
    for seam in ("worktree_state", "identity"):
        rc, err = run(["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root", world["rehearsal"] / "s",
                       "--out", out], Without(world["ops"], seam), capsys=capsys)
        assert rc == 2 and err.startswith("REFUSED:") and seam in err and not out.exists()
    make_v8(world, capsys)
    off, on = pilot_roots(world)
    rc, err = run(["amend", "--v8", world["rec"] / "v8_base.json", "--pilot-off", off, "--pilot-on", on, "--out", world["rec"] / "a.json"],
                  Without(world["ops"], "historical_walls"), capsys=capsys)
    assert rc == 2 and err.startswith("REFUSED:") and "historical_walls" in err


def test_v8_refuses_a_manifest_that_is_not_a_sealed_rehearsal_manifest(world, capsys):
    legs = make_rehearsal_legs(world)
    bogus = world["rehearsal"] / "manifest.json"
    ph.write_exclusive(bogus, dict(kind="p426_v8_base", rehearsal=True))
    rc, err = run(v8_argv(world, bogus, legs, world["rec"] / "v8_base.json"), world["ops"], capsys=capsys)
    assert rc == 2 and "rehearsal" in err
    bogus.write_text(bogus.read_text().replace("true", "false"))
    rc, err = run(v8_argv(world, bogus, legs, world["rec"] / "v8_2.json"), world["ops"], capsys=capsys)
    assert rc == 2 and "sha256" in err


def test_r1_difference_entries_outside_the_allowed_list_are_refused():
    ok = [dict(process="worker", field="argv.worker", off=None, on="--draft-kind mtp"),
          dict(process="-", field="snapshots.drafter", off=None, on="rev"),
          dict(process="probe", field="env.PWD", off="<volatile>", on=None),
          dict(process="router", field="env.__CFBundleIdentifier", off=None, on="x")]
    assert fz.r1_difference_problems(ok) == []
    for bad in (dict(process="router", field="env.MLX_FOO", off="1", on="2"), dict(process="worker", field="argv.router", off="a", on="b"),
                dict(process="-", field="snapshots.target", off="a", on="b"), dict(process="-", field="interpreters", off=1, on=2)):
        assert fz.r1_difference_problems(ok + [bad]) and bad["field"] in fz.r1_difference_problems(ok + [bad])[0]


def test_r1_differences_in_v8_with_an_out_of_list_entry_refuse(world, capsys):
    world["ops"].r1_differences = lambda off, on: [dict(process="router", field="env.MLX_FOO", off="1", on="2")]
    rc, err, out, *_ = make_v8(world, capsys)
    assert rc == 2 and "env.MLX_FOO" in err and not out.exists()


# ----------------------------------------------------------------------------------------------- amendment
def write_pilot_dossier(off, on, verdict="PASS", receipt_sha_off=None):
    """The pilot pair dossier `<out-base>/pairs/pilot__off-a<n>__on-a<m>.json` of two pilot roots (fix round 3, item 6)."""
    from bench import p426_receipt as pr
    off, on = Path(off), Path(on)
    harvests = {}
    for root in (off, on):
        harvests[root] = root.parent / "harvest" / root.name / "HARVEST.json"
        if not harvests[root].exists():
            ph.write_exclusive(harvests[root], dict(leg=root.name))
    name = f"pilot__off-a{off.name.rsplit('.a', 1)[1]}__on-a{on.name.rsplit('.a', 1)[1]}.json"
    path = off.parent / "pairs" / name
    pr.write_dossier(path, pair="pilot", off=dict(attempt=off.name, receipt=off / "receipt.json", harvest=harvests[off]),
                     on=dict(attempt=on.name, receipt=on / "receipt.json", harvest=harvests[on]), differences=[], verdict=verdict)
    if receipt_sha_off:
        doc = doc_of(path)
        doc["arms"]["off"]["receipt_sha256"] = receipt_sha_off
        path.write_text(json.dumps(ph.seal(doc)))
    return path


def pilot_roots(world, *, off_walls=(300.0, 450.0), on_walls=(320.0, 700.0), dossier=True, **kw):
    base = world["wd"] / "p426" / "wave2"
    off = S.write_leg_root(base / "tg1-p426-off-pilot.a1", arm="off", leg="tg1-p426-off-pilot", walls=off_walls, **kw)
    on = S.write_leg_root(base / "tg1-p426-on-pilot.a1", arm="on", leg="tg1-p426-on-pilot", walls=on_walls, **kw)
    if dossier and not kw.get("state", "VALID").startswith("INVALID"):
        try:
            write_pilot_dossier(off, on)
        except ValueError:                    # a pair that does not hold together has no PASS dossier (the gate then names it)
            write_pilot_dossier(off, on, verdict="FAIL")
    return off, on


def amend(world, capsys, off, on, out=None, v8=None):
    out = out or world["rec"] / "amendment.json"
    return run(["amend", "--v8", v8 or world["rec"] / "v8_base.json", "--pilot-off", off, "--pilot-on", on, "--out", out],
               world["ops"], capsys=capsys), out


def test_amendment_takes_the_largest_wall_and_links_the_v8_base(world, capsys):
    make_v8(world, capsys)
    off, on = pilot_roots(world)
    (rc, err), out = amend(world, capsys, off, on)
    assert rc == 0, err
    doc, v8 = doc_of(out), doc_of(world["rec"] / "v8_base.json")
    assert ph.sealed_ok(doc) and doc["kind"] == "p426_timeout_amendment" and doc["v8_base_sha256"] == v8["sha256"]
    assert doc["w_python_s"] == 700.0 and doc["w_go_s"] == 500.0              # max(pilot walls 450/700, historical 400); go: historical
    assert doc["leg_deadline_s"] == {"s1": 1.5 * (22 * 700.0 + 21 * 500.0) + 1800, "s2": 1.5 * (22 * 700.0 + 21 * 500.0) + 1800,
                                     "reload": 1.5 * 5 * 700.0 + 1800}
    assert doc["settle_bound_s"] == v8["settle_bound_s"] and doc["created"]


def test_amendment_settle_bound_is_the_larger_of_v8s_and_twice_the_pilots_largest_request(world, capsys):
    make_v8(world, capsys)
    off, on = pilot_roots(world, elapsed=700.0)
    (rc, err), out = amend(world, capsys, off, on)
    assert rc == 0, err
    assert doc_of(out)["settle_bound_s"] == 1400.0                                   # max(900, 2 x 700)


def test_amendment_settle_bound_keeps_v8s_when_it_is_larger(world, capsys):
    world["ops"].walls["max_request_elapsed_s"] = 1000.0                             # v8: 2000
    make_v8(world, capsys)
    off, on = pilot_roots(world, elapsed=100.0)
    (rc, _e), out = amend(world, capsys, off, on)
    assert rc == 0 and doc_of(out)["settle_bound_s"] == 2000.0


def test_amendment_refuses_pilots_without_request_elapsed(world, capsys):
    make_v8(world, capsys)
    off, on = pilot_roots(world, elapsed=None)
    (rc, err), out = amend(world, capsys, off, on)
    assert rc == 2 and "elapsed_s" in err and not out.exists()


def test_amendment_python_wall_never_drops_below_the_historical_value(world, capsys):
    make_v8(world, capsys)
    off, on = pilot_roots(world, off_walls=(10.0,), on_walls=(20.0,))
    (rc, _e), out = amend(world, capsys, off, on)
    assert rc == 0 and doc_of(out)["w_python_s"] == 400.0


def test_amendment_is_accepted_by_the_chain_record_reader_only_with_its_own_v8(world, capsys):
    _rc, _e, v8, manifest, legs = make_v8(world, capsys)
    off, on = pilot_roots(world)
    (rc, _e), out = amend(world, capsys, off, on)
    assert rc == 0
    assert p426_record.load(out, mode="chain")["base"]["sha256"] == doc_of(v8)["sha256"]
    other = world["rec"].parent / "other"
    other.mkdir()
    (other / "v8_base.json").write_text((world["rec"] / "v8_base.json").read_text().replace(OFF_HEAD, "3" * 40))
    (other / "amendment.json").write_text(out.read_text())
    with pytest.raises(p426_record.RecordError):
        p426_record.load(other / "amendment.json", mode="chain")


def test_records_fit_their_modes_only(world, capsys):
    _rc, _e, v8, manifest, _legs = make_v8(world, capsys)
    off, on = pilot_roots(world)
    (rc, _e), amendment = amend(world, capsys, off, on)
    assert p426_record.load(manifest, mode="chain", rehearsal=True)["doc"]["kind"] == "p426_rehearsal"      # --rehearsal: the manifest
    assert p426_record.load(v8, mode="pilot")["doc"]["kind"] == "p426_v8_base"                              # legs 1-2: v8
    assert p426_record.load(amendment, mode="chain")["doc"]["kind"] == "p426_timeout_amendment"             # legs 3-10: v8 + amendment
    for path, mode, rehearsal in ((v8, "chain", True), (amendment, "chain", True), (manifest, "pilot", False), (manifest, "chain", False),
                                  (v8, "chain", False), (amendment, "pilot", False)):
        with pytest.raises(p426_record.RecordError):
            p426_record.load(path, mode=mode, rehearsal=rehearsal)


@pytest.mark.parametrize("kw", [dict(state="INVALID", klass="systemic"), dict(state="VALID_WITH_DNF", dnf=1)])
def test_amendment_refuses_a_pilot_that_is_not_valid(world, capsys, kw):
    make_v8(world, capsys)
    off, on = pilot_roots(world, **kw)
    (rc, err), out = amend(world, capsys, off, on)
    assert rc == 2 and "pilot" in err and not out.exists()


def test_amendment_refuses_a_tampered_v8_and_an_existing_amendment(world, capsys):
    _rc, _e, v8, *_ = make_v8(world, capsys)
    off, on = pilot_roots(world)
    (rc, _e), out = amend(world, capsys, off, on)
    assert rc == 0
    before = out.read_bytes()
    (rc, err), _o = amend(world, capsys, off, on)
    assert rc == 2 and "exists" in err and out.read_bytes() == before
    v8.write_text(v8.read_text().replace("s2", "s9", 1))
    (rc, err), _o = amend(world, capsys, off, on, out=world["rec"] / "amendment2.json")
    assert rc == 2 and "sha256" in err


# ----------------------------------------------------------------------------------------------- helpers
def test_deadline_formula_is_one_and_a_half_times_the_sum_plus_1800():
    assert fz.deadline_formula({"python": 22, "go": 21}, {"python": 100.0, "go": 200.0}) == 1.5 * (2200 + 4200) + 1800
    assert fz.deadline_formula({"python": 5}, {"python": 10.0, "go": 99.0}) == 1.5 * 50 + 1800
    with pytest.raises(ValueError):
        fz.deadline_formula({"rust": 1}, {"python": 1.0, "go": 1.0})


def test_pilot_walls_come_from_the_rows_of_the_invocations_chain_json_names(tmp_path):
    root = S.write_leg_root(tmp_path / "tg1-p426-off-pilot.a1", arm="off", leg="tg1-p426-off-pilot", walls=(1.0, 2.0, 3.0, 4.0, 5.0))
    assert fz.pilot_walls(root) == [1.0, 2.0, 3.0, 4.0, 5.0]
    chain = json.loads((root / "chain.json").read_text())
    (root / "s1" / "old.jsonl").write_text(json.dumps(dict(slot="x", wall_s=999.0)) + "\n")
    chain["progress"]["invocations"].append(dict(file="s1/old.jsonl", status="archived", leg_key=[0, "python", 0]))
    (root / "chain.json").write_text(json.dumps(chain))
    assert fz.pilot_walls(root) == [1.0, 2.0, 3.0, 4.0, 5.0]                  # an archived invocation is not this leg's


def test_read_leg_verifies_the_self_hash(tmp_path):
    root = S.write_leg_root(tmp_path / "a.a1", arm="off", leg="a")
    assert fz.read_leg(root)["state"] == "VALID"
    p = root / "leg.json"
    p.write_text(p.read_text().replace("VALID", "INVALID"))
    with pytest.raises(fz.Refusal):
        fz.read_leg(root)
    with pytest.raises(fz.Refusal):
        fz.read_leg(tmp_path / "nowhere")


def test_leg_items_problems_names_a_missing_item_record(tmp_path):
    root = S.write_leg_root(tmp_path / "a.a1", arm="on", leg="a", items=2)
    assert fz.leg_items_problems(root, "on") == []
    next(p for p in sorted((root / "items").glob("*.json")) if not p.name.endswith(".ready.json")).unlink()
    assert any("item record" in p for p in fz.leg_items_problems(root, "on"))
    root2 = S.write_leg_root(tmp_path / "b.a1", arm="off", leg="b", items=1, verdict="invalid")
    assert any("reconciled" in p for p in fz.leg_items_problems(root2, "off"))


def test_live_problems_compares_the_record_with_the_live_worktrees(world, capsys):
    _rc, _e, v8, *_ = make_v8(world, capsys)
    base = doc_of(v8)
    assert fz.live_problems(base, world["ops"], world["wd"]) == []
    world["ops"].state[str(world["off"])]["head"] = "9" * 40
    world["ops"].state[str(world["on"])]["clean"] = False
    world["ops"].state[str(world["on"])]["gitlinks"]["src/mlx-vlm"] = "9" * 40
    got = " ".join(fz.live_problems(base, world["ops"], world["wd"]))
    assert "off" in got and "HEAD" in got and "not clean" in got and "gitlink" in got
    world["ops"].state[str(world["off"])]["head"] = OFF_HEAD
    world["ops"].ident_by[str(world["on"])] = dict(world["ops"].ident, probe_code_sha256="0" * 64)
    assert any("probe_code_sha256" in p for p in fz.live_problems(base, world["ops"], world["wd"]))


def test_default_entry_point_check_names_what_is_missing(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    got = fz.entry_point_problems(wt)
    assert any(".venv-bench/bin/python" in p for p in got) and any("run_tg1_chain.py" in p for p in got)
    for rel in fz.ENTRY_POINTS:
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text("")
    assert fz.entry_point_problems(wt) == []


def test_every_refusal_is_one_stderr_line_with_exit_2(world, capsys):
    rc, err = run(["amend", "--v8", world["rec"] / "nope.json", "--pilot-off", "x", "--pilot-on", "y", "--out", world["rec"] / "a.json"],
                  world["ops"], capsys=capsys)
    assert rc == 2 and err.count("\n") == 1 and err.startswith("REFUSED: ")
    rc, err = run(["bogus"], world["ops"], capsys=capsys)
    assert rc == 2 and err.startswith("REFUSED: ") and err.count("\n") == 1
    assert os.environ["STACK_WORKDIR"]
