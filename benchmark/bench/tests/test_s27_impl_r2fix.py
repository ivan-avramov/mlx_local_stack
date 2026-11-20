"""S27 change review r2 (ledger Y1–Y6): one red test (or more) per adopted finding."""
from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import psutil
import pytest

from bench import p426_hooks as ph


# ------------------------------------------------------------------------------------------------------------------ Y1
def _x2_case(**term):
    """The X2 anchored case (`test_s27_impl_r1fix._x2_case`), with `in_flight_at_kill` set — or dropped (`DROP`)."""
    from bench import p426_reconcile as pr
    from bench.tests import b2_frozen_support as S
    from bench.tests.test_b2_frozen_s4_reconcile import BEFORE, after, lines_of
    r = S.golden_row("item_stall_kill")
    u = r["request_usage"]
    n = len(u)
    signal_at = 1793524600.0
    ends = [100 * (k + 1) for k in range(n)]
    t = dict(r["termination"], in_flight_at_kill=0, signal_offset=ends[-1] + 80, signal_at=signal_at,
             step_end_offsets=ends, step_start_offsets=[e - 60 for e in ends] + [ends[-1] + 40])
    t.update(term)
    t = {k: v for k, v in t.items() if v is not DROP}
    r["termination"] = t
    lines = S.item_window(r["session_id"], u) + [S.started_line(), S.failed_line()]
    aft = after(u, failed=1)
    aft["last_error"] = dict(error=pr.STREAM_CLOSED, timestamp_unix=signal_at + 0.4)
    return pr.reconcile_item(r, lines_of(lines), BEFORE, aft)


DROP = object()


def test_y1_the_anchored_case_holds_when_the_sample_read_integer_zero():
    rep = _x2_case()
    assert rep.ok is True and rep.late_record["shape"] == "open_step_at_signal"


@pytest.mark.parametrize("value", [DROP, None, False, "0", 0.0], ids=["absent", "None", "bool", "str", "float"])
def test_y1_the_anchored_case_never_stands_in_for_a_missing_or_malformed_sample(value):
    rep = _x2_case(in_flight_at_kill=value)
    assert rep.ok is False and rep.checks["inflight_evidence"]["ok"] is False
    assert not (rep.late_record and rep.late_record.get("shape") == "open_step_at_signal")


# ------------------------------------------------------------------------------------------------------------------ Y2
class GoGuard:
    grader_mem_kill = False

    def __init__(self, oom=False):
        self.oom, self.removed = oom, []

    def register_container(self, name):
        pass

    def container_oom(self, name):
        if isinstance(self.oom, BaseException):
            raise self.oom
        return self.oom

    def remove_container(self, name):
        self.removed.append(name)


def test_y2_a_docker_launch_oserror_is_a_typed_spawn_fault(tmp_path):
    from bench import structured_grade as sg
    from bench import token_turn_gate as tg

    def run(cmd, **kw):
        raise FileNotFoundError(2, "No such file or directory", "docker")
    with pytest.raises(tg.GraderInfraError) as err:
        sg.grade("go", tmp_path, "a_test.go", tmp_path, run=run, guard=GoGuard())
    assert err.value.kind == "spawn" and tg.grader_infra_fault(err.value)


def test_y2_a_python_interpreter_oserror_stays_an_untyped_abort(tmp_path):
    from bench import structured_grade as sg
    from bench import token_turn_gate as tg

    def run(cmd, **kw):
        raise FileNotFoundError(2, "No such file or directory", "python")
    with pytest.raises(tg.TransportAbort) as err:
        sg.grade("python", tmp_path, "a_test.py", tmp_path, run=run)
    assert not tg.grader_infra_fault(err.value)


@pytest.mark.parametrize("outcome", [
    SimpleNamespace(returncode=1, stdout="", stderr="Cannot connect to the Docker daemon"),
    SimpleNamespace(returncode=0, stdout="", stderr=""),
    SimpleNamespace(returncode=0, stdout="<no value>\n", stderr=""),
    subprocess.TimeoutExpired("docker", 15),
    FileNotFoundError(2, "No such file or directory", "docker"),
], ids=["rc1", "empty", "garbage", "timeout", "oserror"])
def test_y2_an_unverifiable_oom_inspection_is_a_transport_fault_never_not_oom(outcome, monkeypatch):
    from bench import proc_guard as pg
    from bench import token_turn_gate as tg

    def run(*a, **k):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    monkeypatch.setattr(pg.subprocess, "run", run)
    with pytest.raises(tg.GraderInfraError) as err:
        pg.ProcessGuard.container_oom(None, "c")
    assert err.value.kind == "transport"


@pytest.mark.parametrize("value,want", [("true\n", True), ("false\n", False)])
def test_y2_a_verified_oom_inspection_reads_its_state(value, want, monkeypatch):
    from bench import proc_guard as pg
    monkeypatch.setattr(pg.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=value, stderr=""))
    assert pg.ProcessGuard.container_oom(None, "c") is want


def test_y2_an_unverified_oom_state_never_scores_the_item(tmp_path):
    from bench import structured_grade as sg
    from bench import token_turn_gate as tg

    def run(cmd, stdout=None, **kw):
        stdout.write(json.dumps(dict(Action="pass", Package="p", Test="TestA")) + "\n")
        return subprocess.CompletedProcess(cmd, 0, None, None)
    guard = GoGuard(oom=tg.GraderInfraError("container state unverifiable: rc=1", kind="transport"))
    with pytest.raises(tg.GraderInfraError):
        sg.grade("go", tmp_path, "a_test.go", tmp_path, run=run, guard=guard)
    assert guard.removed                                          # the container is still removed


# ------------------------------------------------------------------------------------------------------------------ Y3
def _ops(tmp_path):
    import time as _t
    from bench import chain_ops as co
    return co.ChainOps(tmp_path, tmp_path, tmp_path / "overlay.yaml", lambda m: None, sleep=_t.sleep)


def _leader():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _this_start():
    from bench import proc_guard as pg
    return pg.start_time(psutil.Process(os.getpid()))


def test_y3_a_reused_session_whose_leader_is_not_the_recorded_probe_is_never_claimed(tmp_path):
    """The recorded probe (here: this test process's start) led session `sid`; the pid now leads a NEW session (an unrelated
    process that started after the probe): it and its members are never claimed / killed; the reuse is recorded."""
    other = _leader()
    try:
        scan = _ops(tmp_path).owned_scan(sid=other.pid, not_before=_this_start(), roots=[], container_prefixes=(),
                                         deadline_s=5.0)
        assert other.poll() is None and scan["killed"] == [] and scan["certain"] is True
        assert scan["session_reused"]["pid"] == other.pid
    finally:
        other.kill()
        other.wait(timeout=10)


def test_y3_the_recorded_probe_leading_its_session_is_still_claimed(tmp_path):
    from bench import proc_guard as pg
    probe = _leader()
    try:
        started = pg.start_time(psutil.Process(probe.pid))
        scan = _ops(tmp_path).owned_scan(sid=probe.pid, not_before=started, roots=[], container_prefixes=(), deadline_s=10.0)
        probe.wait(timeout=10)
        assert [k["pid"] for k in scan["killed"]] == [probe.pid] and scan["session_reused"] is None
    finally:
        if probe.poll() is None:
            probe.kill()
            probe.wait(timeout=10)


def test_y3_an_unreadable_session_leader_leaves_the_scan_uncertain_and_claims_nothing(tmp_path, monkeypatch):
    from bench import chain_ops as co
    real_process = psutil.Process

    def Process(pid=None):
        if pid == 5150:
            raise psutil.AccessDenied(pid)
        return real_process(pid) if pid is not None else real_process()
    monkeypatch.setattr(psutil, "pids", lambda: [5150])          # Z2: the leader is validated inside the snapshot
    monkeypatch.setattr(psutil, "Process", Process)
    monkeypatch.setattr(co.os, "getsid", lambda pid: 5150)
    scan = _ops(tmp_path).owned_scan(sid=5150, not_before=1.0, roots=[], container_prefixes=(), deadline_s=2.0)
    assert scan["certain"] is False and any("leader" in p for p in scan["problems"]) and scan["killed"] == []


# ------------------------------------------------------------------------------------------------------------------ Y4
REASON = "hook infrastructure error at done: record_write_failed"


def acct_leg(tmp_path, *, record=True, named=True, recorded=True, row_of=0, **side):
    """A leg root (`b2_s8_support.write_leg_root`) whose first slot is an accounting fault: rows with their ids, the
    invocation's `slot_base`, the sealed sidecar (overridable), chain.json's recorded failure."""
    from bench.tests import b2_s8_support as S8
    root = S8.write_leg_root(tmp_path / "tg1-p426-off-s1.a1", arm="off", leg="tg1-p426-off-s1", items=2)
    chain = json.loads((root / "chain.json").read_text())
    slots = [e["slot"] for e in chain["p426_ledger"]]
    base = slots[0].rsplit("|", 1)[0]
    rows = [dict(id="python/" + s.rsplit("|", 1)[-1], wall_s=100.0 + i) for i, s in enumerate(slots)]
    (root / "s1" / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    chain["progress"]["invocations"][0]["slot_base"] = base
    chain["p426_ledger"][0]["accounting_fault"] = True
    if recorded:
        chain["p426_accounting_faults"] = [dict(slot=slots[0], rerun_index=0, reason=REASON, at="t",
                                                sidecar=f"items/{ph.record_name(slots[0], 0, 'accounting.json')}")]
    (root / "chain.json").write_text(json.dumps(chain))
    rec_path = root / "items" / ph.record_name(slots[0], 0, "json")
    rec = json.loads(rec_path.read_text())
    if not record:
        rec_path.unlink()
    doc = dict(slot=slots[0], rerun_index=0, row_sha256=ph.row_sha256(rows[row_of]),
               item_record_sha256=rec["sha256"] if (record and named) else None,
               failed_checks=[REASON] if not (record and named) else ["boundary_count"], disposition="accounting_fault")
    doc.update(side)
    ph.write_exclusive(ph.accounting_path(root, slots[0], 0), doc)
    return root, chain, slots


def _freeze(root):
    from bench import p426_freeze as fz
    return [p for p in fz.leg_items_problems(root, "off") if "accounting" in p or "item record" in p]


def _harvest(root, chain):
    from bench import p426_harvest as hv
    problems = []
    inv, roots = hv._inventory(root, root.parent, problems)
    problems = []
    hv._check_references(root, "VALID", chain, inv, roots, root.parent, problems)
    return [p for p in problems if "accounting" in p]


@pytest.mark.parametrize("kw", [dict(), dict(record=False), dict(record=False, recorded=False)],
                         ids=["names-its-record", "no-record-recorded-failure", "no-record-unrecorded"])
def test_y4_a_sidecar_bound_to_its_slot_attempt_row_and_record_is_accepted_by_freeze_and_harvest(tmp_path, kw):
    """Z3: a sidecar names no item record exactly when none exists (a recorded reason is not a condition)."""
    root, chain, _ = acct_leg(tmp_path, **kw)
    assert _freeze(root) == [] and _harvest(root, chain) == []


@pytest.mark.parametrize("kw", [
    dict(named=False),                                      # Z3: names no record (one exists), a failure recorded
    dict(named=False, recorded=False),                      # names no record (one exists), nothing recorded
    dict(row_of=1),                                         # names another row
    dict(slot="e|off|other|s1|python|item9"),               # another slot's sidecar at this path
    dict(rerun_index=1),                                    # another attempt's
    dict(disposition="harness_fault"),                      # another disposition
    dict(item_record_sha256="0" * 64),                      # another item record
], ids=["unnamed-recorded", "unnamed-unrecorded", "other-row", "other-slot", "other-rerun", "other-disposition",
        "other-record"])
def test_y4_freeze_and_harvest_refuse_a_sidecar_that_does_not_bind_the_slot_attempt(tmp_path, kw):
    root, chain, _ = acct_leg(tmp_path, **kw)
    assert _freeze(root) and _harvest(root, chain)


def test_y4_the_one_validator_is_used_by_the_chain_freeze_and_harvest():
    from bench import chain_core, p426_freeze, p426_harvest
    assert "ph.accounting_sealed_for(" in inspect.getsource(chain_core)
    assert "accounting_problems(" in inspect.getsource(ph.accounting_sealed_for)
    assert "ph.accounting_problems(" in inspect.getsource(p426_freeze)
    assert "ph.accounting_problems(" in inspect.getsource(p426_harvest)


def test_y4_the_chain_counts_an_existing_sidecar_of_its_own_recorded_failure_as_written(tmp_path):
    """Resume: the sidecar a previous chain process sealed for this slot attempt (no item record). Z3: it stands only while no
    item record exists; a recorded reason is not a condition."""
    slot = "e|off|m|s1|python|a"
    row = dict(id="python/a")
    ph.write_accounting(tmp_path, slot, 0, row, None, ["earlier failure"])
    assert ph.accounting_sealed_for(tmp_path, slot, 0, row) is True
    assert ph.accounting_sealed_for(tmp_path, slot, 0, dict(id="python/a", x=1)) is False   # another row
    ph.write_exclusive(tmp_path / ph.ITEMS_DIR / ph.record_name(slot, 0, "json"), dict(slot=slot))
    assert ph.accounting_sealed_for(tmp_path, slot, 0, row) is False                        # an item record exists


# ------------------------------------------------------------------------------------------------------------------ Y5
class FinishWorker:
    def __init__(self, fault):
        self.fault = fault

    def finish(self):
        return self.fault


def test_y5_a_returned_interim_infra_fault_is_recorded_on_every_join_path():
    from bench import arm_runner as ar
    term = {}
    fault = RuntimeError("Cannot connect to the Docker daemon")
    assert ar._record_finish(FinishWorker(fault), term) is fault
    assert term["interim_grade_fault"] == "RuntimeError: Cannot connect to the Docker daemon"
    term2 = {}
    assert ar._record_finish(FinishWorker(None), term2) is None and term2 == {}
    src = inspect.getsource(ar._run_item)
    assert "worker.finish()" not in src and src.count("_record_finish(worker, termination") == 2


# ------------------------------------------------------------------------------------------------------------------ Y6
@pytest.mark.parametrize("argv0", ["/opt/tool/bin/" + "x" * 200,
                                   "worker: indexing the customer archive for the quarterly migration review " * 3])
def test_y6_a_foreign_new_basename_is_capped_at_64_characters(tmp_path, argv0):
    from bench import proc_guard as pg
    from bench.tests.test_proc_guard import Process
    from bench.tests.test_s27_impl_guard import FOREIGN_SID, make
    p = Process(82, 1, created=11, argv=[argv0, "--flag"])
    g, mp = make(tmp_path, [p], sessions={82: FOREIGN_SID})
    try:
        g.cleanup()
    finally:
        mp.undo()
    (e,) = g.status()["foreign_new"]
    assert len(e["argv"][0]) == pg.FOREIGN_ARGV0_CAP == 64 and e["argc"] == 2


# --------------------------------------------------------------------------------------------- Y6 extended (path_only)
def test_y6_the_chain_scans_path_only_basename_is_capped_at_64_characters(tmp_path):
    """A path-only match (cwd under the run's root, no hermetic environment, no session claim) is listed by identity only:
    its executable basename capped like `foreign_new`'s."""
    from bench import proc_guard as pg
    root = tmp_path / "run-x"
    root.mkdir()
    title = "worker: indexing the customer archive for the quarterly migration review " * 3
    p = subprocess.Popen([title, "-c", "import time; time.sleep(60)"], executable=sys.executable, cwd=str(root),
                         start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    try:
        import time as _t
        deadline = _t.monotonic() + 5
        while _t.monotonic() < deadline:                    # the child's argv is readable once it has exec'd
            try:
                if psutil.Process(p.pid).cmdline()[:1] == [title]:
                    break
            except psutil.Error:
                pass
            _t.sleep(0.02)
        scan = _ops(tmp_path).owned_scan(sid=None, roots=[root], container_prefixes=(), deadline_s=5.0)
        (e,) = [x for x in scan["path_only"] if x["pid"] == p.pid]
        # Z5: the identity is the executable, never the title argv[0] (capped: `test_s27_impl_r3fix`)
        from pathlib import Path
        want = Path(psutil.Process(p.pid).exe()).name[:pg.FOREIGN_ARGV0_CAP]
        assert e["argv"] == [want] and "indexing" not in json.dumps(e) and e["argc"] == 3 and p.poll() is None
    finally:
        p.kill()
        p.wait(timeout=10)


# ------------------------------------------------------------------- clarification 2: a faulted interim grade's boundary
def _gate_after_requests(n):
    from bench import token_turn_gate as tg
    gate = tg.TokenTurnGate(5, policy=dict(tg.POLICY, no_progress_requests=2))
    for j in range(1, n + 1):
        gate.on_request(j, 10, 100, 81920)
    return gate


def _faulted_capture(gate):
    """One interim capture at boundary 1 whose grade hits a typed infrastructure fault; then the stall is crossed while the
    client still runs (the faulted boundary is pending: the rule waits on it), and the client exits."""
    import threading
    import time as _t
    from bench import arm_runner as ar
    from bench.tests.test_s27_impl_runner import INFRA, SnapCorpus

    def grade(snap):
        raise INFRA
    w = ar.GradeWorker(gate, threading.RLock(), "work", "private", grade, join_timeout_s=5, corpus=SnapCorpus())
    w.start()
    w.notify(1)
    deadline = _t.monotonic() + 5
    while w.failure is None and _t.monotonic() < deadline:
        _t.sleep(0.01)
    for j in (2, 3):
        gate.on_request(j, 10, 100, 81920)
    gate.check()
    return w


def test_c2_the_counterfactual_without_the_capture_stalls_at_the_terminal_decision():
    gate = _gate_after_requests(3)
    gate.terminal(None, None)
    assert "stalled" in gate.flags


def test_c2_a_faulted_interim_grade_returned_at_finish_leaves_the_terminal_decision_unchanged():
    gate = _gate_after_requests(1)
    w = _faulted_capture(gate)
    assert "stalled" not in gate.flags                    # while generating, the stall waits on the pending capture
    fault = w.finish()
    assert fault is not None and 1 not in gate.pending
    gate.terminal(None, None)
    assert "stalled" in gate.flags and gate.stop_reason == "stalled"
    assert all(b != 1 for b, *_ in gate.trajectory)       # discharged as ungraded: no grade is recorded for it
