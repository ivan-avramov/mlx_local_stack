"""S27 change review r3 (ledger Z1–Z6, Z8, Z9; Z7 merged into Z2): one red test (or more) per finding."""
from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from bench import p426_hooks as ph


# ------------------------------------------------------------------------------------------------------------------ Z1
class CleanupFailsGuard:
    """A Go grade guard whose container removal fails (`cleanup`: the exception `remove_container` raises)."""
    grader_mem_kill = False

    def __init__(self, cleanup, oom=False):
        self.cleanup, self.oom, self.removed = cleanup, oom, []

    def register_container(self, name):
        pass

    def container_oom(self, name):
        if isinstance(self.oom, BaseException):
            raise self.oom
        return self.oom

    def remove_container(self, name):
        self.removed.append(name)
        raise self.cleanup


def _passing_run(cmd, stdout=None, **kw):
    stdout.write(json.dumps(dict(Action="pass", Package="p", Test="TestA")) + "\n")
    return subprocess.CompletedProcess(cmd, 0, None, None)


CLEANUPS = [lambda: __import__("bench.token_turn_gate", fromlist=["x"]).TransportAbort("container cleanup uncertain"),
            lambda: OSError(5, "Input/output error"),
            lambda: subprocess.TimeoutExpired(["docker", "rm"], 30)]


@pytest.mark.parametrize("cleanup", CLEANUPS, ids=["uncertain", "oserror", "timeout"])
def test_z1_a_cleanup_failure_never_replaces_the_typed_primary_fault(tmp_path, cleanup):
    from bench import structured_grade as sg
    from bench import token_turn_gate as tg
    primary = tg.GraderInfraError("container state unverifiable: rc=1", kind="transport")
    guard = CleanupFailsGuard(cleanup(), oom=primary)
    with pytest.raises(tg.GraderInfraError) as err:
        sg.grade("go", tmp_path, "a_test.go", tmp_path, run=_passing_run, guard=guard)
    assert err.value is primary and guard.removed
    assert any("cleanup" in n for n in getattr(err.value, "__notes__", []))      # the cleanup failure is evidence


def test_z1_a_cleanup_failure_never_replaces_a_typed_docker_status_fault(tmp_path):
    from bench import structured_grade as sg
    from bench import token_turn_gate as tg

    def run(cmd, stdout=None, stderr=None, **kw):
        stderr.write("docker: Error response from daemon: failed to create task")
        return subprocess.CompletedProcess(cmd, 125, None, None)
    guard = CleanupFailsGuard(OSError(5, "Input/output error"))
    with pytest.raises(tg.GraderInfraError) as err:
        sg.grade("go", tmp_path, "a_test.go", tmp_path, run=run, guard=guard)
    assert err.value.kind == "spawn"


def test_z1_the_primary_exception_of_an_abort_propagates_past_a_cleanup_failure(tmp_path):
    from bench import structured_grade as sg

    def run(cmd, **kw):
        raise SystemExit(143)
    guard = CleanupFailsGuard(OSError(5, "Input/output error"))
    with pytest.raises(SystemExit):
        sg.grade("go", tmp_path, "a_test.go", tmp_path, run=run, guard=guard)


@pytest.mark.parametrize("cleanup", CLEANUPS, ids=["uncertain", "oserror", "timeout"])
def test_z1_a_cleanup_failure_that_is_the_primary_failure_is_a_typed_grader_infrastructure_fault(tmp_path, cleanup):
    """The grade itself succeeded; only the container removal failed: typed (regraded in the probe), never a plain abort."""
    from bench import structured_grade as sg
    from bench import token_turn_gate as tg
    with pytest.raises(tg.GraderInfraError) as err:
        sg.grade("go", tmp_path, "a_test.go", tmp_path, run=_passing_run, guard=CleanupFailsGuard(cleanup()))
    assert err.value.kind == "transport" and tg.grader_infra_fault(err.value)


# ------------------------------------------------------------------------------------------------------------------ Z2
def _ops(tmp_path):
    from bench import chain_ops as co
    return co.ChainOps(tmp_path, tmp_path, tmp_path / "overlay.yaml", lambda m: None, sleep=time.sleep)


class FakeProc:
    def __init__(self, pid, start, sid):
        self.pid, self.start, self.sid, self.dead = pid, start, sid, False

    def uids(self):
        return SimpleNamespace(real=os.getuid())

    def create_time(self):
        return self.start

    def cwd(self):
        return "/elsewhere"

    def cmdline(self):
        return ["/usr/bin/fake", "-x"]

    def exe(self):
        return "/usr/bin/fake"

    def environ(self):
        return {}

    def status(self):
        return psutil.STATUS_ZOMBIE if self.dead else psutil.STATUS_RUNNING

    def kill(self):
        self.dead = True


def _world(monkeypatch, table, *, on_pids=None):
    """A scripted process table: `psutil.pids()` lists it (after `on_pids` mutates it: a reuse at enumeration time),
    `psutil.Process(pid)` returns its entry, `os.getsid` reads its session; `start_time` reads the fake's start."""
    from bench import chain_ops as co
    from bench import proc_guard as pg

    def pids():
        if on_pids:
            on_pids(table)
        return list(table)

    def Process(pid=None):
        if pid not in table:
            raise psutil.NoSuchProcess(pid)
        entry = table[pid]
        if isinstance(entry, BaseException):
            raise entry
        return entry

    def getsid(pid):
        if pid == 0:
            return os.getpid() + 10 ** 6
        entry = table.get(pid)
        if entry is None:
            raise ProcessLookupError(pid)
        if isinstance(entry, BaseException):
            raise PermissionError(pid)
        return entry.sid
    monkeypatch.setattr(psutil, "pids", pids)
    monkeypatch.setattr(psutil, "Process", Process)
    monkeypatch.setattr(co.os, "getsid", getsid)
    monkeypatch.setattr(pg, "start_time", lambda p: p.create_time())


SID, PROBE_START = 5150, 100.0


def test_z2_a_leader_pid_reused_after_an_earlier_leader_check_is_never_claimed(tmp_path, monkeypatch):
    """The probe's session died; its leader pid is reused by a NEW session leader while the scan enumerates. A leader check
    taken before the snapshot (it saw no leader) must not authorize a session claim on the snapshot's reused leader."""
    stranger = FakeProc(SID, 200.0, SID)

    def reuse(table):
        table[SID] = stranger
    _world(monkeypatch, {}, on_pids=reuse)
    scan = _ops(tmp_path).owned_scan(sid=SID, not_before=PROBE_START, roots=[], container_prefixes=(), deadline_s=2.0)
    assert not stranger.dead and scan["killed"] == []
    assert scan["session_reused"] and scan["session_reused"]["pid"] == SID


def test_z2_a_reused_sessions_unclaimed_member_leaves_the_scan_uncertain(tmp_path, monkeypatch):
    stranger, member = FakeProc(SID, 200.0, SID), FakeProc(6001, 201.0, SID)
    _world(monkeypatch, {SID: stranger, 6001: member})
    scan = _ops(tmp_path).owned_scan(sid=SID, not_before=PROBE_START, roots=[], container_prefixes=(), deadline_s=2.0)
    assert not stranger.dead and not member.dead and scan["killed"] == []
    assert scan["certain"] is False and any("6001" in p for p in scan["problems"])


def test_z2_z7_a_reused_sessions_unreadable_would_be_member_leaves_the_scan_uncertain(tmp_path, monkeypatch):
    stranger = FakeProc(SID, 200.0, SID)
    _world(monkeypatch, {SID: stranger, 6002: psutil.AccessDenied(6002)})
    scan = _ops(tmp_path).owned_scan(sid=SID, not_before=PROBE_START, roots=[], container_prefixes=(), deadline_s=2.0)
    assert scan["certain"] is False and [u["pid"] for u in scan["unreadable"]] == [6002] and scan["killed"] == []


def test_z2_a_reused_leader_alone_in_its_session_leaves_the_scan_certain(tmp_path, monkeypatch):
    stranger = FakeProc(SID, 200.0, SID)
    _world(monkeypatch, {SID: stranger})
    scan = _ops(tmp_path).owned_scan(sid=SID, not_before=PROBE_START, roots=[], container_prefixes=(), deadline_s=2.0)
    assert scan["certain"] is True and scan["killed"] == [] and scan["session_reused"]["pid"] == SID


def test_z2_an_unreadable_leader_in_the_snapshot_claims_nothing(tmp_path, monkeypatch):
    member = FakeProc(6003, 201.0, SID)
    _world(monkeypatch, {SID: psutil.AccessDenied(SID), 6003: member})
    scan = _ops(tmp_path).owned_scan(sid=SID, not_before=PROBE_START, roots=[], container_prefixes=(), deadline_s=2.0)
    assert not member.dead and scan["killed"] == [] and scan["certain"] is False
    assert any("leader" in p for p in scan["problems"])


def test_z2_the_probe_session_without_its_leader_still_claims_its_members(tmp_path, monkeypatch):
    """Control: the leader exited (absent from the snapshot); a member started after the probe is ours."""
    member = FakeProc(6004, 201.0, SID)
    _world(monkeypatch, {6004: member})
    scan = _ops(tmp_path).owned_scan(sid=SID, not_before=PROBE_START, roots=[], container_prefixes=(), deadline_s=2.0)
    assert member.dead and [k["pid"] for k in scan["killed"]] == [6004] and scan["session_reused"] is None


def test_z2_the_recorded_probe_leading_its_session_is_claimed_with_its_member(tmp_path, monkeypatch):
    probe, member = FakeProc(SID, PROBE_START, SID), FakeProc(6005, 201.0, SID)
    _world(monkeypatch, {SID: probe, 6005: member})
    scan = _ops(tmp_path).owned_scan(sid=SID, not_before=PROBE_START, roots=[], container_prefixes=(), deadline_s=2.0)
    assert probe.dead and member.dead and scan["certain"] is True and scan["session_reused"] is None


# ------------------------------------------------------------------------------------------------------------------ Z3
def _acct(tmp_path, **kw):
    from bench.tests.test_s27_impl_r2fix import acct_leg
    return acct_leg(tmp_path, **kw)


def _consumers(root, chain):
    from bench.tests.test_s27_impl_r2fix import _freeze, _harvest
    return _freeze(root), _harvest(root, chain)


def test_z3_a_sidecar_naming_no_record_is_refused_when_the_item_record_exists_whatever_is_recorded(tmp_path):
    """The item record exists; the sidecar names none; chain.json records an (unrelated) accounting failure: refused by both."""
    root, chain, _ = _acct(tmp_path, named=False, recorded=True)
    freeze, harvest = _consumers(root, chain)
    assert freeze and harvest


def test_z3_a_sidecar_naming_no_record_is_accepted_when_the_item_record_does_not_exist(tmp_path):
    root, chain, _ = _acct(tmp_path, record=False, recorded=False)
    freeze, harvest = _consumers(root, chain)
    assert freeze == [] and harvest == []


def test_z3_the_shared_validator_takes_record_existence_not_a_recorded_reason():
    slot, row = "e|off|m|s1|python|a", dict(id="python/a")
    rec = ph.seal(dict(slot=slot, verdict="reconciled"))
    null = ph.seal(dict(slot=slot, rerun_index=0, row_sha256=ph.row_sha256(row), item_record_sha256=None,
                        failed_checks=["x"], disposition="accounting_fault"))
    named = ph.seal(dict(null, item_record_sha256=rec["sha256"]))
    assert ph.accounting_problems(null, slot, 0, row=row, item_record=None) == []
    assert ph.accounting_problems(null, slot, 0, row=row, item_record=rec)              # it exists: must be named
    assert ph.accounting_problems(named, slot, 0, row=row, item_record=rec) == []
    assert ph.accounting_problems(named, slot, 0, row=row, item_record=None)            # names a record that does not exist
    forged = dict(rec, verdict="forged")                                                # not self-sealed
    assert ph.accounting_problems(ph.seal(dict(null, item_record_sha256=forged["sha256"])), slot, 0, row=row,
                                  item_record=forged)
    assert "recorded" not in inspect.signature(ph.accounting_problems).parameters


def _chain_sidecar(tmp_path):
    slot, row = "e|off|m|s1|python|a", dict(id="python/a")
    path = tmp_path / ph.ITEMS_DIR / ph.record_name(slot, 0, "json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return slot, row, path


def test_z3_z9_the_chain_reads_the_item_record_regular_only_never_through_a_symlink(tmp_path):
    slot, row, path = _chain_sidecar(tmp_path)
    rec = ph.seal(dict(slot=slot, verdict="reconciled"))
    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps(rec))
    path.symlink_to(real)
    ph.write_accounting(tmp_path, slot, 0, row, rec, ["boundary_count"])
    assert ph.accounting_sealed_for(tmp_path, slot, 0, row) is False


def test_z3_the_chain_refuses_a_null_sidecar_when_the_item_record_exists(tmp_path):
    slot, row, path = _chain_sidecar(tmp_path)
    ph.write_exclusive(path, dict(slot=slot, verdict="reconciled"))
    ph.write_accounting(tmp_path, slot, 0, row, None, ["boundary_count"])
    assert ph.accounting_sealed_for(tmp_path, slot, 0, row) is False


def test_z3_the_chain_accepts_its_sidecar_naming_its_regular_sealed_item_record(tmp_path):
    slot, row, path = _chain_sidecar(tmp_path)
    rec = ph.write_exclusive(path, dict(slot=slot, verdict="reconciled"))
    ph.write_accounting(tmp_path, slot, 0, row, rec, ["boundary_count"])
    assert ph.accounting_sealed_for(tmp_path, slot, 0, row) is True


def test_z3_freeze_refuses_a_symlinked_item_record_of_an_accounting_slot(tmp_path):
    root, chain, slots = _acct(tmp_path)
    path = root / "items" / ph.record_name(slots[0], 0, "json")
    real = path.with_name("real-record.json")
    real.write_text(path.read_text())
    path.unlink()
    path.symlink_to(real)
    from bench.tests.test_s27_impl_r2fix import _freeze
    assert _freeze(root)


# ------------------------------------------------------------------------------------------------------------------ Z4
def test_z4_a_tracked_pid_reused_after_an_unreadable_seed_read_is_never_killed_nor_its_children(tmp_path):
    """The tracked identity (50, start 5) is gone and pid 50 was reused (start 99); the closure's read of it was denied, so it
    seeded by pid. The later readable identity differs: neither it nor its child is ours."""
    from bench.tests.test_proc_guard import Process
    from bench.tests.test_s27_impl_guard import FOREIGN_SID, make
    state = dict(deny=False)

    class P(Process):
        def create_time(self):
            if state["deny"]:
                raise psutil.AccessDenied(self.pid)
            return self.created
    reused, child = P(50, 1, created=99), P(51, 50, created=100)
    g, mp = make(tmp_path, [reused, child], sessions={50: FOREIGN_SID, 51: FOREIGN_SID})
    g.tracked[(50, 5)] = "client"
    real = g._ancestry

    def ancestry(listing, edges):
        state["deny"] = True
        try:
            return real(listing, edges)
        finally:
            state["deny"] = False
    g._ancestry = ancestry
    try:
        g.cleanup()
    except Exception:  # noqa: BLE001 — the receipt is what is judged
        pass
    finally:
        mp.undo()
    assert not reused.dead and not child.dead
    assert all(e.get("claim") != "ancestry" for e in g.status()["orphans_unattributed"])


def test_z4_the_exact_tracked_identity_and_its_child_are_still_owned_by_ancestry(tmp_path):
    from bench.tests.test_proc_guard import Process
    from bench.tests.test_s27_impl_guard import FOREIGN_SID, make
    root, child = Process(60, 1, created=5), Process(61, 60, created=6)
    g, mp = make(tmp_path, [root, child], sessions={60: FOREIGN_SID, 61: FOREIGN_SID})
    g.tracked[(60, 5)] = "client"
    try:
        g.cleanup()
    finally:
        mp.undo()
    assert root.dead and child.dead


# ------------------------------------------------------------------------------------------------------------------ Z5
TITLE = "worker: indexing the customer archive for the quarterly migration review"


def _titled(cwd=None):
    """A real process whose argv[0] is free text (a title), its executable this interpreter."""
    p = subprocess.Popen([TITLE, "-c", "import time; time.sleep(60)"], executable=sys.executable, cwd=cwd,
                         start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            if psutil.Process(p.pid).cmdline()[:1] == [TITLE]:
                break
        except psutil.Error:
            pass
        time.sleep(0.02)
    return p


def _stop(p):
    p.kill()
    p.wait(timeout=10)


def test_z5_the_chain_scans_path_only_identity_is_the_executable_never_the_title(tmp_path):
    root = tmp_path / "run-x"
    root.mkdir()
    p = _titled(cwd=str(root))
    try:
        want = Path(psutil.Process(p.pid).exe()).name
        scan = _ops(tmp_path).owned_scan(sid=None, roots=[root], container_prefixes=(), deadline_s=5.0)
        (e,) = [x for x in scan["path_only"] if x["pid"] == p.pid]
        assert e["argv"] == [want] and e["argc"] == 3 and "indexing" not in json.dumps(e)
    finally:
        _stop(p)


def test_z5_foreign_new_identity_is_the_executable_never_the_title(tmp_path):
    from bench.tests.test_s27_impl_guard import FOREIGN_SID, make
    procs, sessions = [], {}
    g, mp = make(tmp_path, procs, sessions=sessions)      # the guard starts first: the process is new, not older
    p = None
    try:
        p = _titled()
        proc = psutil.Process(p.pid)
        want = Path(proc.exe()).name
        procs.append(proc)
        sessions[p.pid] = FOREIGN_SID
        g.cleanup()
        mp.undo()
        (e,) = [x for x in g.status()["foreign_new"] if x["pid"] == p.pid]
        assert e["argv"] == [want] and e["argc"] == 3 and "indexing" not in json.dumps(e) and p.poll() is None
    finally:
        mp.undo()
        if p is not None:
            _stop(p)


def test_z5_an_unreadable_executable_is_unknown_never_argv0(monkeypatch):
    from bench import proc_guard as pg
    p = _titled()
    try:
        proc = psutil.Process(p.pid)
        monkeypatch.setattr(psutil.Process, "exe", lambda self: (_ for _ in ()).throw(psutil.AccessDenied(self.pid)))
        assert pg.exe_identity(proc) == ("unknown", 3)
    finally:
        _stop(p)


def test_z5_argv0_names_the_process_only_as_an_absolute_alias_of_its_own_executable(tmp_path):
    """A link to the executable (a venv's `python`) is a filesystem name of the binary; a title, a relative name or a path to
    another file never is."""
    from bench import proc_guard as pg
    exe = str(Path(psutil.Process(os.getpid()).exe()))
    alias = tmp_path / "alias-python"
    alias.symlink_to(exe)
    other = tmp_path / "other-binary"
    other.write_text("")
    for argv0, want in ((str(alias), "alias-python"), (TITLE, Path(exe).name), ("alias-python", Path(exe).name),
                        (str(other), Path(exe).name)):
        p = subprocess.Popen([argv0, "-c", "import time; time.sleep(60)"], executable=exe, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    if psutil.Process(p.pid).cmdline()[:1] == [argv0]:
                        break
                except psutil.Error:
                    pass
                time.sleep(0.02)
            assert pg.exe_identity(psutil.Process(p.pid)) == (want, 3), argv0
        finally:
            _stop(p)


def test_z5_the_executable_basename_is_capped(monkeypatch):
    from bench import proc_guard as pg
    p = _titled()
    try:
        proc = psutil.Process(p.pid)
        monkeypatch.setattr(psutil.Process, "exe", lambda self: "/opt/tool/bin/" + "x" * 200)
        name, argc = pg.exe_identity(proc)
        assert name == "x" * pg.FOREIGN_ARGV0_CAP and argc == 3
    finally:
        _stop(p)


# ------------------------------------------------------------------------------------------------------------------ Z6
def _bw():
    import importlib
    return importlib.import_module("m1.bench_watch")


def test_z6_the_watchers_top_cpu_records_executable_and_argc_never_arguments(tmp_path):
    bw = _bw()
    secret = "--token=Z6-SECRET-VALUE"
    p = subprocess.Popen([sys.executable, "-c", "while True: pass", secret, "Z6-PRIVATE-ARGUMENT"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        from bench import proc_guard as pg
        want = pg.exe_identity(psutil.Process(p.pid))[0]
        assert want in (Path(sys.executable).name, Path(psutil.Process(p.pid).exe()).name)
        sampler = bw.BoxSampler(os.getpid(), tmp_path / "probe", scrub=str)
        sampler()
        rows = []
        for _ in range(20):
            time.sleep(0.3)
            rows = [r for r in sampler()["top_cpu"] if r["pid"] == p.pid]
            if rows:
                break
        (r,) = rows
        assert r["exe"] == want and r["argc"] == 5 and "argv" not in r
        assert "SECRET" not in json.dumps(r) and "PRIVATE" not in json.dumps(r)
    finally:
        _stop(p)


def test_z6_a_foreign_alert_names_the_executable_and_argc():
    bw = _bw()
    streak = {}
    row = dict(pid=9, sid=7, start=1.0, exe="mds_stores", argc=2, cpu_pct=400.0, ownership="foreign")
    sample = dict(swap_used_mb=0, pressure=None, top_cpu=[row], launch=None)
    alerts = []
    for _ in range(bw.FOREIGN_CPU_ALERT_TICKS):
        alerts = bw.box_alerts(sample, None, streak)
    assert any("mds_stores" in a for a in alerts)


# ------------------------------------------------------------------------------------------------------------------ Z8
def test_z8_finish_with_an_interim_infra_fault_also_discharges_a_capture_queued_after_the_worker_died():
    from bench.tests.test_s27_impl_r2fix import _faulted_capture, _gate_after_requests
    gate = _gate_after_requests(1)
    w = _faulted_capture(gate)
    w.notify(3)                                           # queued after the worker died: never graded
    assert w.queued == 3 and 3 in gate.pending
    fault = w.finish()
    assert fault is not None and 3 not in gate.pending and 1 not in gate.pending and w.queued is None
    assert gate.stall_wait is None or 3 not in gate.stall_wait
    gate.terminal(None, None)
    assert "stalled" in gate.flags


# ------------------------------------------------------------------------------------------------------------------ Z9
def test_z9_owned_scan_documents_the_kernel_reservation_and_the_exact_leader_comparison():
    from bench import chain_ops as co
    doc = inspect.getdoc(co.ChainOps.owned_scan)
    assert "kernel" in doc and "reuse" in doc and "exact" in doc


def test_z9_the_leader_start_comparison_is_exact_to_the_recorded_value(tmp_path, monkeypatch):
    """A leader whose start differs from the recorded value by any amount is not the recorded probe (no tolerance)."""
    near = FakeProc(SID, PROBE_START + 1e-6, SID)
    _world(monkeypatch, {SID: near})
    scan = _ops(tmp_path).owned_scan(sid=SID, not_before=PROBE_START, roots=[], container_prefixes=(), deadline_s=2.0)
    assert not near.dead and scan["session_reused"]
