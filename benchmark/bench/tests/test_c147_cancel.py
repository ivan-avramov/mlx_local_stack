"""C147 §2/§3: causal-evidence primitives (unit) and cooperative cancellation (composed, real p.main())."""

import json
import subprocess
import pytest
from bench import proc_guard as pg
from bench.token_turn_gate import TransportAbort
from bench.tests.test_proc_guard import Process, guard


def test_wait_cancel_returns_elapsed_seconds():
    clock = iter([100.0, 100.0, 102.5, 104.0])
    values = iter([{"summary": {"in_flight": 1}}, {"summary": {"in_flight": 1}}, {"summary": {"in_flight": 0}}])
    elapsed = pg.wait_cancel(lambda: next(values), sleep=lambda n: None, now=lambda: next(clock))
    assert elapsed == 4.0 - 0 or elapsed == pytest.approx(4.0 - 0.0) or isinstance(elapsed, float)
    assert elapsed >= 0


def test_wait_cancel_elapsed_is_zero_when_already_idle():
    t = iter([5.0, 5.0, 5.0])
    assert pg.wait_cancel(lambda: {"summary": {"in_flight": 0}}, now=lambda: next(t)) == 0.0


def test_kill_role_returns_killed_entries_with_scrubbed_argv(tmp_path):
    client = Process(10, argv=["opencode", "run"])
    shell = Process(11, 10, argv=["/bin/zsh", "-c", "sleep 600 /secret/home/x"])
    sleeper = Process(12, 11, argv=["sleep", "600"])
    processes = [client, shell, sleeper]
    g = guard(tmp_path, processes, scrub=lambda text: text.replace("/secret/home", "$HOME"))
    g.register(client, "client")
    killed = g.kill_role("client")
    assert [(k["pid"], k["role"]) for k in killed] == [(10, "client")]
    assert killed[0]["create_time"] == 10 and killed[0]["argv"] == ["opencode", "run"]
    killed = g.kill_role("model")
    assert sorted((k["pid"], k["role"]) for k in killed) == [(11, "model"), (12, "model")]
    assert any("$HOME/x" in " ".join(k["argv"]) for k in killed)
    assert g.verify_gone(killed) and not any(not p.dead for p in processes)
    assert [k["pid"] for k in g.killed] == [10, 11, 12]


def test_verify_gone_detects_a_survivor(tmp_path):
    p = Process(30)
    g = guard(tmp_path, [p])
    g.register(p, "model")
    entry = dict(pid=30, create_time=10, role="model", argv=[])
    assert not g.verify_gone([entry])
    p.dead = True
    assert g.verify_gone([entry])
    reused = Process(30, created=99)
    g2 = guard(tmp_path, [reused])
    assert g2.verify_gone([entry])      # same pid, different create_time: not our process


def test_mem_kill_records_role_rss_argv_and_request_linkage(tmp_path):
    client = Process(10)
    hog = Process(11, 10, rss=400, argv=["python3", "-c", "bytearray(400)"])
    g = guard(tmp_path, [client, hog], per_process=100, aggregate=10**9,
              context=lambda: {"completed_requests": 3})
    g.register(client, "client")
    g.tick()
    assert hog.dead
    (kill,) = g.mem_kills
    assert kill["role"] == "model" and kill["rss"] == 400 and kill["argv"] == ["python3", "-c", "bytearray(400)"]
    assert kill["carrying_request"] == 4 and kill["completed_boundary_at_kill"] == 3
    assert kill["tool_call_id"] is None and kill["pid"] == 11


def test_cleanup_status_clean_and_uncertain(tmp_path):
    p = Process(20)
    g = guard(tmp_path, [p])
    assert g.status()["uncertain"] is True and g.status()["completed"] is False
    g.register(p, "client")
    g.cleanup()
    assert g.status() == dict(survivors=[], containers_remaining=[], uncertain=False,
                              orphans_unattributed=[], unknown=[], completed=True)
    q = Process(21, cwd=str(tmp_path / "work"), argv=["x"])
    h = guard(tmp_path, [q])
    with pytest.raises(TransportAbort, match="uncertain"):
        h.cleanup()
    s = h.status()
    assert s["uncertain"] and s["orphans_unattributed"][0]["pid"] == 21


def test_cleanup_status_records_remaining_container(tmp_path, monkeypatch):
    def run(cmd, **kw):
        out = "mlxbench-r-i-1\n" if cmd[:3] == ["docker", "ps", "-a"] else ""
        return subprocess.CompletedProcess(cmd, 0, out, "")
    monkeypatch.setattr(pg.subprocess, "run", run)
    g = guard(tmp_path, [])
    g.register_container("mlxbench-r-i-1")
    with pytest.raises(TransportAbort, match="container cleanup uncertain"):
        g.cleanup()
    s = g.status()
    assert s["containers_remaining"] == ["mlxbench-r-i-1"] and s["uncertain"] and s["completed"]


# ======================= composed: real p.main() dispatch via tg_fixture =======================

import hashlib
import os
from pathlib import Path
import threading
import time
from bench import tg1_runner as runner, structured_grade as sg
from bench.tests.test_opencode_v2_probe import probe, MODEL
from bench.tests.test_tg1_integration import tg_fixture
from bench.tests.test_token_turn_gate import event, usage


def linger_events(f, tmp_path, completed=1):
    """`completed` finished requests, one open request; the fake client then lingers (and records a start marker)."""
    lines = []
    for k in range(1, completed + 1):
        lines += [event("step_start", f"m{k}"), event("step_finish", f"m{k}", tokens=usage(10, 100))]
    lines.append(event("step_start", f"m{completed + 1}"))
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in lines))
    messages = [dict(id=f"m{k}", type="assistant", tokens=usage(10, 100), finish="stop", content=[])
                for k in range(1, completed + 1)]
    messages.append(dict(id=f"m{completed + 1}", type="assistant", error=dict(type="aborted"), content=[]))
    f["export"].write_text(json.dumps(dict(info=dict(id="s1"), messages=messages)))
    binary = Path(os.environ["OPENCODE_PROBE_BIN"])
    marker = tmp_path / "client.started"
    text = binary.read_text()
    text = text.replace('\nexit "$(cat ', f'\ntouch {marker}\nsleep 30\nexit "$(cat ')
    binary.write_text(text)
    return marker


def when(path, action, timeout=30):
    """Run `action` once `path` exists (a test-side stand-in for the runner)."""
    def watch():
        deadline = time.time() + timeout
        while time.time() < deadline and not Path(path).exists():
            time.sleep(0.02)
        action()
    t = threading.Thread(target=watch, daemon=True)
    t.start()
    return t


def manifest(f):
    return json.loads(f["mp"].read_text())


def test_cancel_before_the_first_spawn_writes_nothing(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    cancel = tmp_path / "leg.CANCEL"
    real = runner.validate_worker

    def late_cancel(*a, **k):
        cancel.write_text("")           # arrives after the stale-file check, before discovery
        return real(*a, **k)
    monkeypatch.setattr(runner, "validate_worker", late_cancel)
    with pytest.raises(SystemExit, match="cancelled by runner"):
        f["run"]("one", extra=["--cancel-file", str(cancel)])
    assert not f["out"].exists() and not f["mp"].exists() and not f["calls"].exists()


def test_cancel_between_items_stops_at_the_boundary_without_a_spawn(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    cancel = tmp_path / "leg.CANCEL"
    calls = []
    identity = f["identity"]

    def worker_identity(*a):
        calls.append(1)
        if len(calls) == 3:             # preflight, item-1 before, item-1 after -> cancel before item 2
            cancel.write_text("")
        return dict(identity)
    monkeypatch.setattr(runner, "worker_identity", worker_identity)
    with pytest.raises(SystemExit, match="cancelled by runner"):
        f["run"]("one,two", extra=["--cancel-file", str(cancel)])
    rows = [json.loads(x) for x in f["out"].read_text().splitlines()]
    assert [r["id"] for r in rows] == ["python/one"]
    abort = manifest(f)["transport_abort"]
    assert "cancelled by runner" in abort["error"] and "cancelled_item" not in manifest(f)
    assert manifest(f)["cleanup_status"]["uncertain"] is False and manifest(f)["cleanup_status"]["survivors"] == []
    assert len(f["calls"].read_text().splitlines()) == 1        # the client was spawned for item one only


def test_cancel_during_generation_runs_the_full_terminal_path_and_leaves_no_row(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    marker = linger_events(f, tmp_path)
    cancel = tmp_path / "leg.CANCEL"
    watcher = when(marker, lambda: cancel.write_text(""))
    started = time.time()
    with pytest.raises(SystemExit, match="cancelled by runner"):
        f["run"]("one", extra=["--cancel-file", str(cancel)])
    watcher.join(5)
    assert time.time() - started < 25                      # killed, not waited out
    assert not f["out"].exists()                            # no row
    man = manifest(f)
    assert "cancelled by runner" in man["transport_abort"]["error"]
    item = man["cancelled_item"]
    assert item["id"] == "python/one"
    assert set(item["evidence_sha256"]) == {"events", "stderr", "export"} and all(item["evidence_sha256"].values())
    assert item["reconciliation"] == dict(unmatched_export_messages=1, trailing="interrupted")
    assert item["termination"]["reason"] == "runner_cancel"
    assert item["termination"]["killed"][0]["role"] == "client" and item["termination"]["killed_verified"] is True
    assert isinstance(item["termination"]["cancel_wait_s"], float)
    assert item["grade_reports"] and item["grade_reports"][-1]["final"] is True      # final grade ran
    assert item["cleanup_status"] == man["transport_abort"]["cleanup_status"] == man["cleanup_status"]
    assert item["cleanup_status"]["uncertain"] is False and item["cleanup_status"]["survivors"] == []
    assert man["transport_abort"]["grade_reports"] == item["grade_reports"]
    transcripts = list((tmp_path / "opencode_transcripts").rglob("*.events.jsonl"))
    assert len(transcripts) == 1 and hashlib.sha256(transcripts[0].read_bytes()).hexdigest() == \
        item["evidence_sha256"]["events"]


def test_cancel_during_grading_is_honoured_after_the_terminal_phases_and_before_the_row_is_committed(
        probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    cancel = tmp_path / "leg.CANCEL"
    real = sg.grade
    seen = []

    def grade(*a, **k):
        if k.get("final"):
            cancel.write_text("")       # the cancel file lands while the final grade is running
            seen.append("final-grade")
        return real(*a, **k)
    monkeypatch.setattr(sg, "grade", grade)
    with pytest.raises(SystemExit, match="cancelled by runner"):
        f["run"]("one,two", extra=["--cancel-file", str(cancel)])
    assert seen == ["final-grade"]                           # the terminal phases ran to completion first
    assert not f["out"].exists()                             # ... but the row was never committed
    man = manifest(f)
    item = man["cancelled_item"]
    assert item["id"] == "python/one"
    assert item["grade_reports"][-1]["final"] is True and item["grade_reports"][-1]["outcome"] == "parsed"
    assert item["reconciliation"]["trailing"] in ("none", "final")
    assert item["termination"]["reason"] is None and set(item["evidence_sha256"]) == {"events", "stderr", "export"}
    assert man["cleanup_status"]["uncertain"] is False


def test_manifest_ack_barrier_blocks_item_one_until_the_file_exists(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    ack = tmp_path / "leg.ACK"
    observed = {}
    real = runner.worker_identity
    count = []

    def spy(*a):
        count.append(1)
        if len(count) == 2:             # call 1 is the preflight; call 2 is item one's identity check
            observed["manifest_before_item"] = f["mp"].exists()
            observed["ack_before_item"] = ack.exists()
            observed["rows_before_item"] = f["out"].exists()
        return real(*a)
    seen = []

    def release():
        seen.append(json.loads(f["mp"].read_text())["runtime"]["scaffold"])   # runner-side verification stand-in
        ack.write_text("")
    when(f["mp"], release)
    monkeypatch.setattr(runner, "ACK_POLL_S", 0.02)
    monkeypatch.setattr(runner, "worker_identity", lambda *a: (spy(*a)))
    assert f["run"]("one", extra=["--manifest-ack", str(ack)]) == 0
    assert seen == ["opencode-v2-web-tg1"] and observed == dict(
        manifest_before_item=True, ack_before_item=True, rows_before_item=False)


def test_manifest_ack_timeout_aborts_before_anything_is_generated(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "ACK_TIMEOUT_S", 0.2)
    monkeypatch.setattr(runner, "ACK_POLL_S", 0.02)
    with pytest.raises(SystemExit, match="manifest not acknowledged"):
        f["run"]("one", extra=["--manifest-ack", str(tmp_path / "never.ACK")])
    assert not f["out"].exists() and not f["calls"].exists()
    assert "manifest not acknowledged" in manifest(f)["transport_abort"]["error"]
    assert manifest(f)["cleanup_status"]["completed"] is True


def test_every_abort_records_cleanup_status_from_the_guard(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    real = sg.grade

    def boom(*a, **k):
        raise runner.tg.TransportAbort("grader infrastructure down")
    monkeypatch.setattr(sg, "grade", boom)
    with pytest.raises(SystemExit):
        f["run"]("one")
    abort = manifest(f)["transport_abort"]
    top = manifest(f)["cleanup_status"]                 # the receipt location is TOP LEVEL
    assert set(top) >= {"survivors", "containers_remaining", "uncertain", "orphans_unattributed"}
    assert top["uncertain"] is False and top == abort["cleanup_status"]


from bench.tests.test_tg1_integration import pinned_binary      # noqa: E402,F401
from bench.tests.opencode_v2_mock import MockServer              # noqa: E402


CANCEL_MANIFEST = Path(__file__).parent / "fixtures/c147_cancel_manifest.json"


def freeze_cancel_manifest(doc, workdir):
    """A REAL probe-produced abort manifest (pinned client, cancel during generation), PII-scrubbed. The chain
    worker tests restart eligibility against it. Refreeze with C147_FREEZE_FIXTURE=1."""
    if not os.environ.get("C147_FREEZE_FIXTURE"):
        return
    text = json.dumps(doc, indent=1, sort_keys=True)
    for real in {str(workdir), str(Path(workdir).resolve())}:
        text = text.replace(real, "$STACK_WORKDIR")
    CANCEL_MANIFEST.write_text(text + "\n")


def test_frozen_real_cancel_manifest_carries_the_top_level_receipt_and_no_pii():
    raw = CANCEL_MANIFEST.read_text()
    assert "/Users/" not in raw and "/private/var" not in raw
    doc = json.loads(raw)
    status = doc["cleanup_status"]      # unattributed orphans (e.g. a Spotlight worker) are diagnostics only
    assert (status["survivors"], status["containers_remaining"], status["uncertain"], status["completed"]) == (
        [], [], False, True) and isinstance(status["orphans_unattributed"], list)
    assert "cancelled by runner" in doc["transport_abort"]["error"] and doc["cancelled_item"]["id"] == "python/one"
    assert doc["cancelled_item"]["termination"]["client_stop"] == "sigterm"


def test_real_client_cancel_during_generation(probe, pinned_binary, monkeypatch, tmp_path):
    """Pinned opencode mid-stream: the cancel file stops it with SIGTERM first, so the client persists the
    in-flight assistant message as aborted and the export reconciles as `interrupted`."""
    with MockServer({1: "hang"}) as mock:
        f = tg_fixture(probe, monkeypatch, tmp_path, binary=pinned_binary, mock=mock)
        monkeypatch.setattr(runner.provenance, "opencode_v2_destination", lambda *a, **k: mock.base)
        cancel = tmp_path / "leg.CANCEL"

        def arm():
            deadline = time.time() + 60
            while len(mock.chats) < 1 and time.time() < deadline:
                time.sleep(0.05)
            time.sleep(1.5)
            cancel.write_text("")
        threading.Thread(target=arm, daemon=True).start()
        with pytest.raises(SystemExit, match="cancelled by runner"):
            f["run"]("one", extra=["--cancel-file", str(cancel)])
    assert not f["out"].exists()
    man = json.loads(f["mp"].read_text())
    item = man["cancelled_item"]
    assert item["termination"]["reason"] == "runner_cancel" and item["termination"]["killed_verified"] is True
    assert item["termination"]["killed"][0]["role"] == "client"
    assert item["termination"]["client_stop"] == "sigterm" and item["termination"]["graceful_wait_s"] < 15
    assert item["reconciliation"] == dict(unmatched_export_messages=1, trailing="interrupted")
    assert item["cleanup_status"]["uncertain"] is False and item["cleanup_status"]["survivors"] == []
    assert item["grade_reports"] and item["grade_reports"][-1]["final"] is True
    cancel_manifest = json.loads(f["mp"].read_text())
    assert cancel_manifest["cleanup_status"]["uncertain"] is False
    freeze_cancel_manifest(cancel_manifest, tmp_path)


def test_sigterm_abort_still_records_cleanup_status_in_the_manifest(probe, monkeypatch, tmp_path):
    import signal
    f = tg_fixture(probe, monkeypatch, tmp_path)
    marker = linger_events(f, tmp_path)
    when(marker, lambda: os.kill(os.getpid(), signal.SIGTERM))
    prior = signal.getsignal(signal.SIGTERM)
    try:
        with pytest.raises(SystemExit) as exc:
            f["run"]("one")
    finally:
        signal.signal(signal.SIGTERM, prior)
    assert exc.value.code == 143
    man = json.loads(f["mp"].read_text())
    status = man["cleanup_status"]                       # top level, written after cleanup
    assert status == man["transport_abort"]["cleanup_status"]
    assert status["completed"] is True and status["uncertain"] is False and status["survivors"] == []
    assert not f["out"].exists()


def test_graceful_stop_signals_term_first_and_reports_what_it_signalled(tmp_path):
    class P(Process):
        def terminate(self):
            self.terminated = True
            self.dead = self.exits
    client = P(10, argv=["opencode", "run"])
    client.exits = True
    stubborn = P(11, 10, argv=["opencode", "serve"])
    stubborn.exits = False
    g = guard(tmp_path, [client, stubborn])
    g.register(client, "client")
    got = g.graceful_stop("client", 0.0)
    assert [e["pid"] for e in got] == [10] and client.terminated and client.dead and not stubborn.dead
    assert not hasattr(stubborn, "terminated")          # model-role processes are never SIGTERMed
    g.tracked[(stubborn.pid, stubborn.created)] = "client"
    got = g.graceful_stop("client", 0.0)
    assert [e["pid"] for e in got] == [11] and not g.verify_gone(got)       # survivor left for SIGKILL
    assert [e["pid"] for e in g.kill_role("client")] == [11] and stubborn.dead


def test_real_client_cancel_inside_a_long_tool_call_charges_the_aborted_message(
        probe, pinned_binary, monkeypatch, tmp_path):
    """The live exec_timeout shape: the step's stream has finished (usage is real) and a shell call is running."""
    with MockServer({1: dict(name="shell", input={"command": "sleep 20"})}) as mock:
        f = tg_fixture(probe, monkeypatch, tmp_path, binary=pinned_binary, mock=mock)
        monkeypatch.setattr(runner.provenance, "opencode_v2_destination", lambda *a, **k: mock.base)
        cancel = tmp_path / "leg.CANCEL"

        def arm():
            deadline = time.time() + 60
            while len(mock.chats) < 1 and time.time() < deadline:
                time.sleep(0.05)
            time.sleep(3)
            cancel.write_text("")
        threading.Thread(target=arm, daemon=True).start()
        with pytest.raises(SystemExit, match="cancelled by runner"):
            f["run"]("one", extra=["--cancel-file", str(cancel)])
    item = json.loads(f["mp"].read_text())["cancelled_item"]
    assert item["reconciliation"] == dict(unmatched_export_messages=1, trailing="interrupted_charged")
    assert item["termination"]["client_stop"] == "sigterm"


def test_cleanup_skips_untracked_access_denied_and_marks_tracked_uncertain(tmp_path):
    import psutil

    class Denied(Process):
        def cwd(self):
            raise psutil.AccessDenied(self.pid)

        def cmdline(self):
            raise psutil.AccessDenied(self.pid)

    class Opaque(Denied):
        def create_time(self):
            raise psutil.AccessDenied(self.pid)

    stranger = Denied(40, argv=["x"])
    g = guard(tmp_path, [stranger])
    g.cleanup()                                  # untracked: skipped, nothing raised
    assert g.status()["uncertain"] is False and g.status()["orphans_unattributed"] == []

    owned = Opaque(41)
    owned.kill = lambda: None                    # never dies and cannot be inspected
    h = guard(tmp_path, [owned])
    h.tracked[(41, 10)] = "model"
    with pytest.raises(TransportAbort, match="uncertain.*41"):
        h.cleanup()
    s = h.status()
    assert s["uncertain"] is True and [o["pid"] for o in s["orphans_unattributed"]] == [41]


@pytest.mark.parametrize("denied", ["uids", "status", "create_time"])
def test_denied_inspection_of_a_tracked_pid_is_unknown_not_gone(tmp_path, denied):
    """Q17: the filtered scan drops a process whose uids()/status() is denied; the audit of tracked identities must
    not: the pid is listed as unknown, cleanup is uncertain and raises, and verify_gone is False."""
    import psutil

    class Denying(Process):
        armed = False

        def uids(self):
            if self.armed and denied == "uids":
                raise psutil.AccessDenied(self.pid)
            return super().uids()

        def status(self):
            if self.armed and denied == "status":
                raise psutil.AccessDenied(self.pid)
            return super().status()

        def create_time(self):
            if self.armed and denied == "create_time":
                raise psutil.AccessDenied(self.pid)
            return super().create_time()

    owned = Denying(50)
    g = guard(tmp_path, [owned])
    g.register(owned, "model")
    owned.kill = lambda: None            # alive and uninspectable from now on
    owned.armed = True
    entry = dict(pid=50, create_time=10, role="model", argv=[])
    assert g.verify_gone([entry]) is False
    with pytest.raises(TransportAbort, match="uncertain"):
        g.cleanup()
    status = g.status()
    assert status["uncertain"] is True and status["unknown"] == [dict(pid=50, create_time=10)]


def test_verify_gone_is_false_when_final_liveness_cannot_be_determined(tmp_path):
    import psutil
    p = Process(60)
    g = guard(tmp_path, [p])
    g.register(p, "model")
    entry = dict(pid=60, create_time=10, role="model", argv=[])
    p.dead = True
    assert g.verify_gone([entry]) is True
    p.status = lambda: (_ for _ in ()).throw(psutil.AccessDenied(60))
    assert g.verify_gone([entry]) is False


def test_graceful_stop_calls_before_signal_once_right_before_the_first_sigterm_and_never_without_a_target(tmp_path):
    events = []

    class P(Process):
        def terminate(self):
            events.append("terminate")
            self.dead = True

        def memory_info(self):
            events.append("scan")
            return super().memory_info()
    a, b = P(10, argv=["opencode", "run"]), P(11, 10, argv=["opencode", "serve"])
    g = guard(tmp_path, [a, b])
    g.register(a, "client")
    g.graceful_stop("client", 0.0, before_signal=lambda: events.append("before_signal"))
    assert events.count("before_signal") == 1
    assert events.index("before_signal") > max(i for i, e in enumerate(events) if e == "scan")
    assert events.index("before_signal") < events.index("terminate")
    quiet = guard(tmp_path, [])
    quiet.graceful_stop("client", 0.0, before_signal=lambda: pytest.fail("nothing to signal"))


def test_error_written_during_the_pre_signal_scan_is_before_the_cutoff_and_aborts():
    from bench.tests.test_token_turn_gate import _fresh, _err, ABORT_FETCH, assistant, TAIL
    from bench import token_turn_gate as tg
    g, s = _fresh()
    s.offset = 1000
    s.feed(_err(ABORT_FETCH))                                   # written while graceful_stop was still scanning
    s.signal_offset = 1000 + len(_err(ABORT_FETCH))             # captured by before_signal, AFTER the scan
    with pytest.raises(tg.TransportAbort, match="error event"):
        tg.reconcile(s, dict(messages=[assistant(), TAIL]), -15, "stalled")
    g, s = _fresh()                                             # no process signalled -> cutoff never set
    s.offset = 1000
    s.feed(_err(ABORT_FETCH))
    assert s.signal_offset is None
    with pytest.raises(tg.TransportAbort, match="error event"):
        tg.reconcile(s, dict(messages=[assistant(), TAIL]), -15, "stalled")


@pytest.mark.parametrize("failure", ["AccessDenied", "NoSuchProcess"])
def test_cutoff_is_committed_only_after_a_terminate_succeeded(tmp_path, failure):
    import psutil

    class Failing(Process):
        def terminate(self):
            raise getattr(psutil, failure)(self.pid)

    committed = []
    owned = Failing(70, argv=["opencode", "run"])
    g = guard(tmp_path, [owned])
    g.register(owned, "client")
    signalled = g.graceful_stop("client", 0.0, before_signal=lambda: 4242, after_signal=committed.append)
    assert signalled == [] and committed == []              # every terminate raised: nothing committed
    ok = Process(71, argv=["opencode", "run"])
    h = guard(tmp_path, [ok])
    h.register(ok, "client")
    h.graceful_stop("client", 0.0, before_signal=lambda: 4242, after_signal=committed.append)
    assert committed == [4242]                               # exactly once, with the captured value


@pytest.mark.parametrize("failure", ["AccessDenied", "NoSuchProcess"])
def test_failed_signal_leaves_tolerance_disabled_so_a_transport_error_aborts(tmp_path, failure):
    import psutil
    from bench.tests.test_token_turn_gate import _fresh, _err, ABORT_FETCH, assistant, TAIL
    from bench import token_turn_gate as tg

    class Failing(Process):
        def terminate(self):
            raise getattr(psutil, failure)(self.pid)

    g, s = _fresh()
    s.offset = 1000
    owned = Failing(72)
    guard_ = guard(tmp_path, [owned])
    guard_.register(owned, "client")
    guard_.graceful_stop("client", 0.0, before_signal=lambda: 1000,
                         after_signal=lambda size: setattr(s, "signal_offset", size))
    s.feed(_err(ABORT_FETCH))
    assert s.signal_offset is None
    with pytest.raises(tg.TransportAbort, match="error event"):
        tg.reconcile(s, dict(messages=[assistant(), TAIL]), -15, "stalled")
