"""P475 stage 1 second fix round (operator C294): Sol verify vP1–vP4 (dispositions "Verify — round 2 of 3")."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess

import pytest

from bench import p475_kv as K
from bench.tests.test_p475_impl_fixes import _unstable, args_for, edit_receipt, leg, legs_run, resign
from bench.tests.test_p475_impl_support import BASE, FakeOps, make_cfg


@pytest.fixture
def world(tmp_path):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    return ops, cfg


@pytest.fixture
def finished(world):
    ops, cfg = world
    assert K.run(args_for(cfg), ops) == 0
    return ops, cfg


def _last_leg_end(cfg):
    p = cfg.p475 / "LAST_LEG_END"
    return p.read_text() if p.exists() else None


# ================================================================== vP1: a VALID dossier holds its exact file inventory
def _replay_setup(ops, cfg):
    name, r = leg(ops, cfg)
    assert r["verdict"] == "VALID" and r["speed_valid"] and r["_harvest"] == "harvested", (r["problems"], r["speed_problems"])
    shutil.rmtree(cfg.dossier(name))                              # a crash before the rename: replay must redo the harvest
    ops.t += 5000.0                                                # a fresh LAST_LEG_END write would differ
    return name, r


@pytest.mark.parametrize("which", ["watch", "manifest", "rows"])
def test_a_valid_harvest_with_a_missing_source_refuses_and_leaves_last_leg_end(world, which):
    ops, cfg = world
    name, r = _replay_setup(ops, cfg)
    before = _last_leg_end(cfg)
    os.unlink(r["paths"][which])
    with pytest.raises(K.P475Error, match="missing"):
        K.harvest(name, ops, cfg)
    assert not cfg.dossier(name).exists() and not cfg.dossier(name).with_name(f"{name}.stage").exists()
    assert _last_leg_end(cfg) == before


def test_a_valid_leg_whose_driver_wrote_no_manifest_is_not_harvested(world):
    ops, cfg = world
    real_wait = ops.wait

    def wait(proc, timeout):
        rc = real_wait(proc, timeout)
        cfg.capacity_outputs("AF8", K.leg_name("AF8", 1, 1))["manifest"].unlink(missing_ok=True)
        return rc
    ops.wait = wait
    name, r = leg(ops, cfg)
    assert r["verdict"] == "VALID"
    assert r["_harvest"].startswith("harvest failed") and "manifest" in r["_harvest"]
    assert not cfg.dossier(name).exists() and _last_leg_end(cfg) is None


def test_a_valid_replay_with_every_source_present_still_harvests(world):
    ops, cfg = world
    name, _ = _replay_setup(ops, cfg)
    assert K.harvest(name, ops, cfg) == "harvested"
    want = {"receipt.json", "watch.jsonl", f"capacity_ladder.p475-{name}.jsonl", f"capacity_ladder.p475-{name}.manifest.json",
            "kv_line.json", "worker_argv.json"}
    man = json.loads((cfg.dossier(name) / "SCRUB_MANIFEST.json").read_text())
    assert set(man["files"]) == want


def test_an_invalid_leg_without_a_watch_journal_keeps_todays_rule(world):
    ops, cfg = world
    ops.leg_script["u4-af8-b1.a1"] = dict(driver_rc=1, watch_mode="absent")
    name, r = leg(ops, cfg)
    assert r["verdict"] == "INVALID" and r["_harvest"] == "harvested"
    assert not (cfg.dossier(name) / "watch.jsonl").exists()


def test_a_speed_invalid_leg_whose_receipt_records_no_watcher_report_is_harvested_and_replaced(world):
    # R11: a watcher that wrote no journal is a speed problem -> replacement, never a stopped run
    ops, cfg = world
    ops.leg_script["u4-af8-b1.a1"] = dict(watch_mode="absent")
    assert K.run(args_for(cfg), ops) == 0
    assert "u4-af8-b1.a2" in legs_run(ops)
    d = cfg.dossier("u4-af8-b1.a1")
    assert d.is_dir() and not (d / "watch.jsonl").exists()
    rec, problems = K.load_dossier(d)
    assert problems == [] and rec["usable"] is False


def _inventory_names(name):
    return ["watch.jsonl", f"capacity_ladder.p475-{name}.manifest.json", "kv_line.json", "worker_argv.json",
            f"capacity_ladder.p475-{name}.jsonl"]


@pytest.mark.parametrize("i", range(5), ids=["watch", "manifest", "kv_line", "worker_argv", "ladder"])
def test_a_valid_dossier_lacking_an_inventory_file_is_refused(finished, i):
    _, cfg = finished
    name = "u4-af8-b2.a1"
    d = cfg.dossier(name)
    target = _inventory_names(name)[i]
    (d / target).unlink()
    man = json.loads((d / "SCRUB_MANIFEST.json").read_text())
    del man["files"][target]
    (d / "SCRUB_MANIFEST.json").write_text(json.dumps(man))
    rec, problems = K.load_dossier(d)
    assert rec["usable"] is False and any(name in p for p in problems), problems
    rc, path = K.matrix(cfg)
    assert rc == 1 and path.name.endswith(".PARTIAL.md") and name in path.read_text()


@pytest.mark.parametrize("i", range(5), ids=["watch", "manifest", "kv_line", "worker_argv", "ladder"])
def test_a_valid_dossier_whose_scrub_manifest_lacks_an_inventory_file_is_refused(finished, i):
    _, cfg = finished
    name = "u4-af8-b2.a1"
    d = cfg.dossier(name)
    target = _inventory_names(name)[i]
    man = json.loads((d / "SCRUB_MANIFEST.json").read_text())
    del man["files"][target]
    (d / "SCRUB_MANIFEST.json").write_text(json.dumps(man))
    rec, problems = K.load_dossier(d)
    assert rec["usable"] is False and any(target in p and "SCRUB_MANIFEST" in p for p in problems), problems
    assert K.matrix(cfg)[0] == 1


def test_a_valid_dossier_whose_receipt_is_missing_from_the_scrub_manifest_is_refused(finished):
    _, cfg = finished
    d = cfg.dossier("u4-af8-b2.a1")
    man = json.loads((d / "SCRUB_MANIFEST.json").read_text())
    del man["files"]["receipt.json"]
    (d / "SCRUB_MANIFEST.json").write_text(json.dumps(man))
    rec, problems = K.load_dossier(d)
    assert rec["usable"] is False and any("receipt.json" in p for p in problems), problems


def test_a_valid_speed_valid_dossier_cannot_claim_no_watcher_report_to_drop_its_journal(finished):
    _, cfg = finished
    name = "u4-af8-b2.a1"
    d = cfg.dossier(name)
    (d / "watch.jsonl").unlink()
    man = json.loads((d / "SCRUB_MANIFEST.json").read_text())
    del man["files"]["watch.jsonl"]
    (d / "SCRUB_MANIFEST.json").write_text(json.dumps(man))
    edit_receipt(d, lambda r: r.setdefault("watcher", {}).update(problems=["no watcher report"]))
    rec, problems = K.load_dossier(d)
    assert rec["usable"] is False and any("watch.jsonl" in p for p in problems), problems


# ================================================================== vP2: RealOps.spawn never leaks a started process group
class _FakePopen:
    def __init__(self, script):
        self.pid = 4242
        self.script = script                                       # signals -> does the leader exit on it?
        self.alive = True
        self.signals = []
        self.waited = 0

    def wait(self, timeout=None):
        self.waited += 1
        if self.alive:
            raise subprocess.TimeoutExpired("x", timeout)
        return -15

    def poll(self):
        return None if self.alive else -15

    def send_signal(self, sig):
        self.signals.append(("leader", sig))
        if sig in self.script:
            self.alive = False

    def terminate(self):
        self.send_signal(signal.SIGTERM)

    def kill(self):
        self.send_signal(signal.SIGKILL)


@pytest.fixture
def realops(tmp_path, monkeypatch):
    from bench import chain_ops
    state = dict(popen=None, killpg=[], group=set())

    def popen(argv, **kw):
        p = _FakePopen(state["script"])
        state["popen"], state["kw"] = p, kw
        if kw.get("start_new_session"):
            state["group"] = {p.pid}
        return p

    def killpg(pgid, sig):
        state["killpg"].append((pgid, sig))
        p = state["popen"]
        if sig in state["script"]:
            p.alive = False
        if sig in state.get("members_die_on", state["script"]):
            state["group"] = set()

    def boom(pid):
        raise RuntimeError("create-time capture failed")

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(chain_ops, "default_create_time", boom)
    monkeypatch.setattr(K.time, "sleep", lambda s: None)
    ops = K.RealOps(tmp_path)
    monkeypatch.setattr(ops, "group_alive", lambda pgid: bool(state["group"]) and pgid in (4242,))
    return ops, state


def test_spawn_kills_and_reaps_its_group_when_create_time_capture_raises(realops, tmp_path):
    ops, st = realops
    st["script"] = {signal.SIGTERM}
    with pytest.raises(RuntimeError, match="create-time capture failed"):
        ops.spawn(["/bin/true"], {}, str(tmp_path), session=True)
    assert st["killpg"] == [(4242, signal.SIGTERM)]
    assert st["popen"].alive is False and st["popen"].waited >= 1 and not st["group"]
    assert 4242 not in ops._procs


def test_spawn_escalates_to_sigkill_when_the_group_survives_term(realops, tmp_path):
    ops, st = realops
    st["script"] = {signal.SIGKILL}
    with pytest.raises(RuntimeError, match="create-time capture failed"):
        ops.spawn(["/bin/true"], {}, str(tmp_path), session=True)
    assert [s for _, s in st["killpg"]] == [signal.SIGTERM, signal.SIGKILL]
    assert all(g == 4242 for g, _ in st["killpg"])
    assert st["popen"].alive is False and not st["group"]


def test_spawn_kills_a_lingering_group_member_after_the_leader_exits_on_term(realops, tmp_path):
    ops, st = realops
    st["script"] = {signal.SIGTERM}
    st["members_die_on"] = {signal.SIGKILL}                        # a child that ignores TERM
    with pytest.raises(RuntimeError):
        ops.spawn(["/bin/true"], {}, str(tmp_path), session=True)
    assert [s for _, s in st["killpg"]] == [signal.SIGTERM, signal.SIGKILL] and not st["group"]


def test_spawn_without_a_session_never_signals_the_callers_group(realops, tmp_path):
    ops, st = realops
    st["script"] = {signal.SIGTERM}
    with pytest.raises(RuntimeError):
        ops.spawn(["/bin/true"], {}, str(tmp_path), session=False)
    assert st["killpg"] == [] and ("leader", signal.SIGTERM) in st["popen"].signals and st["popen"].alive is False


def test_a_successful_spawn_signals_nothing(realops, tmp_path, monkeypatch):
    from bench import chain_ops
    ops, st = realops
    st["script"] = set()
    monkeypatch.setattr(chain_ops, "default_create_time", lambda pid: 7.5)
    rec = ops.spawn(["/bin/true"], {}, str(tmp_path), session=True)
    assert rec == dict(pid=4242, create_time=7.5)
    assert st["killpg"] == [] and st["popen"].signals == [] and ops._procs[4242] is st["popen"]


def test_a_popen_failure_raises_without_signalling(realops, tmp_path, monkeypatch):
    ops, st = realops

    def popen(argv, **kw):
        raise FileNotFoundError("no such interpreter")
    monkeypatch.setattr(subprocess, "Popen", popen)
    with pytest.raises(FileNotFoundError):
        ops.spawn(["/nonexistent"], {}, str(tmp_path), session=True)
    assert st["killpg"] == []


# ================================================================== vP3: only the recorded plan's blocks enter the matrix
def clone_dossier(cfg, src_leg, dst_leg, block):
    src, dst = cfg.dossier(src_leg), cfg.dossier(dst_leg)
    shutil.copytree(src, dst)
    old, new = f"p475-{src_leg}", f"p475-{dst_leg}"
    for p in list(dst.iterdir()):
        if old in p.name:
            p.rename(dst / p.name.replace(old, new))
    for p in dst.iterdir():
        if p.name != "SCRUB_MANIFEST.json":
            p.write_text(p.read_text().replace(src_leg, dst_leg))
    man = json.loads((dst / "SCRUB_MANIFEST.json").read_text())
    man["files"] = {k.replace(old, new): v for k, v in man["files"].items()}
    (dst / "SCRUB_MANIFEST.json").write_text(json.dumps(man))
    resign(dst)
    edit_receipt(dst, lambda r: r.update(block=block))
    rec, problems = K.load_dossier(dst)
    assert problems == [] and rec["usable"], problems           # usable on its own: only the plan binding refuses it
    return dst


def test_a_stale_off_plan_block_dossier_makes_the_matrix_partial(finished):
    _, cfg = finished
    clone_dossier(cfg, "u4-af8-b2.a1", "u4-af8-b4.a1", 4)
    rc, path = K.matrix(cfg)
    assert rc == 1 and path.name.endswith(".PARTIAL.md")
    text = path.read_text()
    assert "u4-af8-b4.a1" in text and "recorded plan" in text and "b4 (deciding)" not in text


def test_a_deciding_block_dossier_the_run_never_started_is_refused(finished):
    _, cfg = finished
    st = json.loads(cfg.state_path.read_text())
    assert not (st.get("deciding") or {}).get("started")
    clone_dossier(cfg, "u4-af8-b2.a1", "u4-af8-b3.a1", 3)
    rc, path = K.matrix(cfg)
    assert rc == 1 and "u4-af8-b3.a1" in path.read_text() and "b3 (deciding)" not in path.read_text()


def test_only_the_recorded_deciding_block_is_accepted(world):
    ops, cfg = world
    ops.metric = _unstable
    assert K.run(args_for(cfg), ops) == 0
    assert json.loads(cfg.state_path.read_text())["deciding"]["block"] == 3
    assert K.matrix(cfg)[0] == 0
    clone_dossier(cfg, "u4-af8-b3.a1", "u4-af8-b4.a1", 4)
    rc, path = K.matrix(cfg)
    assert rc == 1 and path.name.endswith(".PARTIAL.md")
    text = path.read_text()
    assert "b3 (deciding)" in text and "b4 (deciding)" not in text and "u4-af8-b4.a1" in text


def test_an_off_plan_dossier_stops_the_deciding_step(finished):
    ops, cfg = finished
    clone_dossier(cfg, "u4-af8-b2.a1", "u4-af8-b4.a1", 4)
    assert K.run(args_for(cfg), ops) == 1


# ================================================================== vP4: standalone `matrix` exits nonzero on an unresolved flag
def test_the_matrix_cli_exits_nonzero_on_an_unresolved_flag(world):
    ops, cfg = world
    ops.metric = _unstable
    assert K.run(args_for(cfg, "--max-deciding", "0"), ops) == 1
    argv = ["--workdir", str(cfg.workdir), "--repo", str(cfg.repo), "--base", BASE, "matrix"]
    assert K.main(argv, ops=ops) != 0
    canon, part = cfg.results / f"MATRIX.{K.PICK}.md", cfg.results / f"MATRIX.{K.PICK}.PARTIAL.md"
    assert canon.is_file() and not part.exists()                  # naming unchanged: every leg is complete
    assert "UNRESOLVED" in canon.read_text()


def test_the_matrix_cli_exits_zero_when_every_flag_is_resolved(world):
    ops, cfg = world
    ops.metric = _unstable
    assert K.run(args_for(cfg), ops) == 0
    argv = ["--workdir", str(cfg.workdir), "--repo", str(cfg.repo), "--base", BASE, "matrix"]
    assert K.main(argv, ops=ops) == 0
