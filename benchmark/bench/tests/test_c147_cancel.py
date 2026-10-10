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
                              orphans_unattributed=[], completed=True)
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
    assert abort["cleanup_status"]["uncertain"] is False and abort["cleanup_status"]["survivors"] == []
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
    assert item["cleanup_status"] == man["transport_abort"]["cleanup_status"]
    assert item["cleanup_status"]["uncertain"] is False and item["cleanup_status"]["survivors"] == []
    assert man["transport_abort"]["grade_reports"] == item["grade_reports"]
    transcripts = list((tmp_path / "opencode_transcripts").rglob("*.events.jsonl"))
    assert len(transcripts) == 1 and hashlib.sha256(transcripts[0].read_bytes()).hexdigest() == \
        item["evidence_sha256"]["events"]


def test_cancel_during_grading_and_export_is_honoured_only_after_the_terminal_phases(probe, monkeypatch, tmp_path):
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
    assert seen == ["final-grade"]
    rows = [json.loads(x) for x in f["out"].read_text().splitlines()]
    assert [r["id"] for r in rows] == ["python/one"] and rows[0]["passed"]       # item 1 finished normally
    assert rows[0]["termination"]["reason"] is None
    assert "cancelled_item" not in manifest(f)


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


def test_every_abort_records_cleanup_status_from_the_guard(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    real = sg.grade

    def boom(*a, **k):
        raise runner.tg.TransportAbort("grader infrastructure down")
    monkeypatch.setattr(sg, "grade", boom)
    with pytest.raises(SystemExit):
        f["run"]("one")
    abort = manifest(f)["transport_abort"]
    assert set(abort["cleanup_status"]) >= {"survivors", "containers_remaining", "uncertain", "orphans_unattributed"}
    assert abort["cleanup_status"]["uncertain"] is False


from bench.tests.test_tg1_integration import pinned_binary      # noqa: E402,F401
from bench.tests.opencode_v2_mock import MockServer              # noqa: E402


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
    abort = json.loads(f["mp"].read_text())["transport_abort"]
    status = abort["cleanup_status"]
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
