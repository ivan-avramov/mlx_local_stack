"""S26 §2 (implementer tests): the Wave 2 sequencer's host-environment guard (C360) on the hermetic B2 s8 world (fake ops, fake
clock): the baseline written once at run entry, the pre-launch refusal, a post-leg change -> INVALID / systemic with its reason
(and the prior one), the exception path (logged, re-raised), the end-of-run check on both exits BEFORE publishing, a resumed run
on a changed host, an unreadable baseline, `host_env.json` published (run) / kept (rehearsal), fakes without the seam unchanged,
and the real ops' seam."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import p426_hooks as ph
from bench import p426_wave2 as w2
from bench.tests.test_b2_s8_wave2 import LEGS, go, leg_doc, seq, world, rehearsal, go_rehearsal  # noqa: F401  (fixtures)

BASE = dict(path="/opt/homebrew/bin:/usr/bin:/bin", tools={"cargo": "absent", "java": {"path": "/opt/j", "sha256": "a" * 64}},
            cellar=["openjdk@21/21.0.4", "rust/1.80.0"], bin_dirs={"/opt/homebrew/bin": ["cargo -> ../Cellar/rust"]},
            npm_global=None, home_toolchains={".cargo": "absent", "Library/Python": "absent"},
            files={"tg2 gradle.properties": "absent"})
JDK17 = "Homebrew Cellar: added openjdk@17/17.0.12"


def seam(w):
    """Give the fake ops the host seam; returns the mutable state (`state.fp`)."""
    state = SimpleNamespace(fp=copy.deepcopy(BASE), calls=0)

    def host_env():
        state.calls += 1
        return copy.deepcopy(state.fp)
    w.ops.host_env = host_env
    return state


def install_jdk17(state):
    state.fp["cellar"] = sorted(state.fp["cellar"] + ["openjdk@17/17.0.12"])


def log_of(w):
    path = w.out / "sequence.log"
    return path.read_text() if path.exists() else ""


def test_a_clean_run_writes_the_baseline_once_and_publishes_it_with_the_run_files(world):
    state = seam(world)
    assert go(world, "--through", "2") == 0
    path = world.out / w2.HOST_ENV_FILE
    doc = json.loads(path.read_text())
    assert ph.sealed_ok(doc) and doc["kind"] == "host_env" and doc["fingerprint"] == BASE
    first = path.read_bytes()
    assert go(world) == 0                                                  # the resumed run compares, never rewrites
    assert path.read_bytes() == first and log_of(world).count("host environment baseline recorded") == 1
    assert world.ops.names() == LEGS
    published = world.ops.published_run_files[-1]
    assert published[-2:] == [path, world.out / "sequence.json"]           # with the run files, before sequence.json
    assert all(l["state"] == "VALID" and "reason" not in l for l in seq(world)["legs"])
    assert "host_env_after_last_leg" not in seq(world)
    assert state.calls >= 2 * len(LEGS)                                     # before and after every leg


def test_the_baseline_is_recorded_before_the_first_leg(world):
    state = seam(world)
    seen = []
    world.ops.on_launch = lambda ops, name, root: seen.append((world.out / w2.HOST_ENV_FILE).is_file())
    assert go(world, "--through", "1") == 0
    assert seen == [True] and state.calls >= 3


def test_a_change_between_legs_refuses_the_next_launch(world):
    state = seam(world)
    harvest = world.ops.harvest

    def harvest_then_install(root, *, emails):
        res = harvest(root, emails=emails)
        if Path(root).name == "tg1-p426-off-pilot.a1":
            install_jdk17(state)
        return res
    world.ops.harvest = harvest_then_install
    assert go(world) == 1
    assert world.ops.names() == LEGS[:1]                                    # nothing launched after the change
    assert leg_doc(world, "tg1-p426-off-pilot.a1")["state"] == "VALID"      # the change came after its leg.json
    assert ("STOP: the host environment differs from the run's baseline before tg1-p426-on-pilot (nothing launched): "
            + JDK17) in log_of(world)


def test_a_change_during_a_leg_makes_it_invalid_systemic_harvested_and_stops(world):
    state = seam(world)
    world.ops.on_launch = lambda ops, name, root: install_jdk17(state) if name == "tg1-p426-off-s1" else None
    assert go(world) == 1
    assert world.ops.names() == LEGS[:3] and world.ops.names("harvest") == LEGS[:3]
    d = leg_doc(world, "tg1-p426-off-s1.a1")
    assert d["state"] == "INVALID" and d["class"] == "systemic"
    assert d["reason"] == "host environment changed during the leg: " + JDK17
    entry = seq(world)["legs"][-1]
    assert entry["state"] == "INVALID" and entry["reason"] == d["reason"]
    assert "is INVALID: host environment changed during the leg" in log_of(world)


def test_the_prior_reason_is_kept(world):
    state = seam(world)
    world.ops.scenario["tg1-p426-off-s1"] = dict(rc=2, status="invalidated",
                                                 invalid=[dict(stage="done", slot="s", reason="engagement", at="t")])
    world.ops.on_launch = lambda ops, name, root: install_jdk17(state) if name == "tg1-p426-off-s1" else None
    assert go(world) == 1
    d = leg_doc(world, "tg1-p426-off-s1.a1")
    assert d["reason"] == "host environment changed during the leg: " + JDK17 + " (prior: engagement)"
    assert d["class"] == "systemic"


def test_a_resumed_run_on_a_changed_host_refuses_until_the_host_equals_the_baseline(world):
    state = seam(world)
    world.ops.on_launch = lambda ops, name, root: install_jdk17(state) if name == "tg1-p426-off-s1" else None
    assert go(world) == 1
    world.ops.on_launch = None
    world.clock.t += 3600
    n = len(world.ops.launches)
    assert go(world, "--rerun", "tg1-p426-off-s1", "--rerun-reason", "host changed") == 1
    assert len(world.ops.launches) == n
    assert ("the host environment differs from the run's baseline before tg1-p426-off-s1 (nothing launched): " + JDK17
            ) in log_of(world)
    state.fp = copy.deepcopy(BASE)                                            # the operator restores the host
    world.clock.t += 3600
    assert go(world, "--rerun", "tg1-p426-off-s1", "--rerun-reason", "host restored") == 0
    assert (world.out / "tg1-p426-off-s1.a2" / "leg.json").is_file()


def test_an_unreadable_or_tampered_baseline_stops(world):
    seam(world)
    assert go(world, "--through", "1") == 0
    path = world.out / w2.HOST_ENV_FILE
    doc = json.loads(path.read_text())
    doc["fingerprint"]["cellar"] = []                                         # not resealed
    path.write_text(json.dumps(doc))
    n = len(world.ops.launches)
    assert go(world) == 1 and len(world.ops.launches) == n
    assert "host_env.json (the run's host-environment baseline) is unreadable or not a sealed baseline" in log_of(world)
    path.write_text("{")
    assert go(world) == 1 and len(world.ops.launches) == n


@pytest.mark.parametrize("change", [False, True], ids=["unchanged", "changed"])
def test_an_exception_inside_the_leg_region_is_logged_and_propagates(world, change):
    state = seam(world)

    def wait(handle):
        if change:
            install_jdk17(state)
        raise RuntimeError("boom in wait")
    world.ops.wait = wait
    with pytest.raises(RuntimeError, match="boom in wait"):
        go(world)
    log = log_of(world)
    want = ("changed: " + JDK17) if change else "is unchanged"
    assert f"tg1-p426-off-pilot.a1: an exception left the leg; the host environment {want}" in log
    assert not (world.out / "tg1-p426-off-pilot.a1" / "leg.json").exists()


def _snapshot_publication(world):
    seen = []
    publish = world.ops.publish_run_files

    def snap(paths, *, emails):
        seen.append(json.loads((world.out / "sequence.json").read_text()))
        return publish(paths, emails=emails)
    world.ops.publish_run_files = snap
    return seen


@pytest.mark.parametrize("through", [None, "2"], ids=["done-exit", "through-exit"])
def test_the_end_of_run_check_runs_before_the_run_files_are_published(world, through):
    state = seam(world)
    last = "tg1-p426-on-pilot.a1" if through else "tg1-p426-off-reload.a1"
    harvest = world.ops.harvest

    def harvest_then_install(root, *, emails):
        res = harvest(root, emails=emails)
        if Path(root).name == last:
            install_jdk17(state)
        return res
    world.ops.harvest = harvest_then_install
    seen = _snapshot_publication(world)
    assert go(world, *(("--through", through) if through else ())) == 1
    assert seq(world)["host_env_after_last_leg"] == [JDK17]
    assert seen and all(s.get("host_env_after_last_leg") == [JDK17] for s in seen)     # recorded before any publication
    log = log_of(world)
    assert "STOP: the host environment changed after the last leg: " + JDK17 in log
    assert "DONE:" not in log and "stopping as asked" not in log
    assert leg_doc(world, last)["state"] == "VALID"


def test_fakes_without_the_seam_are_unchanged(world):
    assert not hasattr(world.ops, "host_env")
    assert go(world) == 0
    assert not (world.out / w2.HOST_ENV_FILE).exists()
    assert all(w2.HOST_ENV_FILE not in [p.name for p in paths] for paths in world.ops.published_run_files)
    assert "host environment" not in log_of(world)


def test_a_rehearsal_keeps_the_baseline_in_its_out_base_and_publishes_nothing(rehearsal):
    w = rehearsal.w
    seam(w)
    w.ops.scenario["tg1-p426-rehearsal-mismatch"] = dict(rc=2, status="invalidated", items=1,
                                                         invalid=[dict(stage="done", slot="s", reason="injected", at="t")])
    assert go_rehearsal(rehearsal) == 0
    assert (w.out / w2.HOST_ENV_FILE).is_file() and w.ops.published_run_files == []


def test_a_host_change_stops_even_a_leg_whose_invalid_state_is_expected(rehearsal):
    w = rehearsal.w
    state = seam(w)
    w.ops.scenario["tg1-p426-rehearsal-mismatch"] = dict(rc=2, status="invalidated", items=1,
                                                         invalid=[dict(stage="done", slot="s", reason="injected", at="t")])
    w.ops.on_launch = lambda ops, name, root: install_jdk17(state) if name == "tg1-p426-rehearsal-mismatch" else None
    assert go_rehearsal(rehearsal) == 1
    assert w.ops.names()[-1] == "tg1-p426-rehearsal-mismatch"               # R3 never launched


def _host_stop_lines(w):
    return [line for line in log_of(w).splitlines() if "STOP:" in line and ("host" in line or w2.HOST_ENV_FILE in line)]


def test_the_baseline_stop_is_a_flat_fail_closed_statement(world):
    """Erratum 14 (GLM R2-2): an automatic stop of the guard names what failed and nothing else (no operator wording)."""
    seam(world)
    assert go(world, "--through", "1") == 0
    (world.out / w2.HOST_ENV_FILE).write_text("{")
    assert go(world) == 1
    lines = _host_stop_lines(world)
    assert any("is unreadable or not a sealed baseline" in line for line in lines)
    assert not [line for line in lines if "operator" in line], lines


def test_the_invalid_leg_stop_is_a_flat_fail_closed_statement(rehearsal):
    """Erratum 14 (GLM R2-2): as above, for the stop on a leg the host change made INVALID."""
    w = rehearsal.w
    state = seam(w)
    w.ops.scenario["tg1-p426-rehearsal-mismatch"] = dict(rc=2, status="invalidated", items=1,
                                                         invalid=[dict(stage="done", slot="s", reason="injected", at="t")])
    w.ops.on_launch = lambda ops, name, root: install_jdk17(state) if name == "tg1-p426-rehearsal-mismatch" else None
    assert go_rehearsal(rehearsal) == 1
    lines = _host_stop_lines(w)
    assert any("is INVALID: host environment changed during the leg" in line for line in lines)
    assert not [line for line in lines if "operator" in line], lines


def test_the_real_ops_have_the_seam(tmp_path, monkeypatch):
    from bench import host_env
    assert callable(getattr(w2.BoxSeqOps, "host_env", None))
    calls = []
    monkeypatch.setattr(host_env, "fingerprint_for_run", lambda *a, **kw: calls.append((a, kw)) or {"sentinel": 1})
    ops = w2.BoxSeqOps(tmp_path, main_root=tmp_path / "main", evidence_stage=tmp_path / "ev")
    assert ops.host_env() == {"sentinel": 1} and calls == [((), {})]          # erratum 4: no argument


def test_the_tg2_run_files_include_the_baseline(tmp_path):
    rec, out = tmp_path / "rec", tmp_path / "out"
    rec.mkdir()
    (out / "run").mkdir(parents=True)
    (rec / "v8_base.json").write_text("{}")
    (out / "run" / "recheck-s1.json").write_text("{}")
    ns = SimpleNamespace(record_dir=rec, out=out, corpus="tg2")
    ns.host_env_paths = lambda: w2.Sequencer.host_env_paths(ns)
    assert w2.Sequencer.run_file_paths(ns) == [rec / "v8_base.json", out / "run" / "recheck-s1.json", out / "sequence.json"]
    (out / w2.HOST_ENV_FILE).write_text("{}")
    assert w2.Sequencer.run_file_paths(ns)[-2:] == [out / w2.HOST_ENV_FILE, out / "sequence.json"]
