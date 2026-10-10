"""M62 H1-H4 and observed silence; resource limits are lowered in fixtures."""

import json
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import pytest
from bench import proc_guard as pg
from bench.token_turn_gate import TransportAbort


class Process:
    def __init__(self, pid, ppid=1, rss=0, cwd="/elsewhere", created=10, argv=None):
        self.pid = pid
        self.parent = ppid
        self.rss = rss
        self.directory = cwd
        self.created = created
        self.dead = False
        self.argv = argv or []

    def ppid(self):
        return self.parent

    def create_time(self):
        return self.created

    def memory_info(self):
        return SimpleNamespace(rss=self.rss)

    def cwd(self):
        return self.directory

    def cmdline(self):
        return self.argv

    def uids(self):
        return SimpleNamespace(real=os.getuid())

    def status(self):
        return "zombie" if self.dead else "running"

    def kill(self):
        self.dead = True


def guard(tmp_path, processes, **kwargs):
    result = pg.ProcessGuard(
        [tmp_path],
        scan=lambda: processes,
        get=lambda pid: next(p for p in processes if p.pid == pid),
        **kwargs,
    )
    result.started = 0  # Fixture creation times use a synthetic epoch.
    return result


def test_detached_shell_pid_reuse_and_rapid_orphan(tmp_path):
    root = Process(10)
    shell = Process(11, 10)
    child = Process(12, 11)
    processes = [root, shell, child]
    g = guard(tmp_path, processes)
    g.started = 9
    g.register(root, "client")
    g.tick()
    child.parent = 1
    child.directory = "/escaped"
    escaped = Process(13, 1, created=11)
    processes.append(escaped)
    reused = Process(11, 1, created=20)
    processes[1] = reused
    g.cleanup()
    assert child.dead and root.dead and not reused.dead and not escaped.dead
    assert {x["pid"] for x in g.orphans_unattributed} >= {13}
    g.cleanup()


def test_sweep_attribution_and_uncertain_cleanup(tmp_path):
    p = Process(20, cwd=str(tmp_path / "work"))
    g = guard(tmp_path, [p])
    g.register(p, "model")
    p.kill = lambda: None
    with pytest.raises(TransportAbort, match="surviv"):
        g.cleanup()


def test_cleanup_defers_second_signal(tmp_path, monkeypatch):
    p = Process(10)
    g = guard(tmp_path, [p])
    g.register(p, "client")
    handlers = {}
    seen = []
    monkeypatch.setattr(
        pg.signal, "getsignal", lambda s: seen.append(s) or signal.SIG_DFL
    )
    monkeypatch.setattr(pg.signal, "signal", lambda s, h: handlers.__setitem__(s, h))

    def kill():
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        handlers[signal.SIGINT](signal.SIGINT, None)
        p.dead = True

    p.kill = kill
    g.cleanup()
    assert p.dead and handlers[signal.SIGTERM] == signal.SIG_DFL


def test_container_never_started_removed_and_verified(tmp_path, monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(pg.subprocess, "run", run)
    g = guard(tmp_path, [])
    g.register_container("mlxbench-run-item-1")
    g.cleanup()
    assert ["docker", "rm", "-f", "mlxbench-run-item-1"] in calls
    assert any(cmd[:3] == ["docker", "ps", "-a"] for cmd in calls)


def test_container_names_bind_run_item_and_sequence(tmp_path):
    g = pg.ProcessGuard([tmp_path], run_id="run123", item="go-book-store")
    assert g.container_name() == "mlxbench-run123-go-book-store-1"
    assert g.container_name() == "mlxbench-run123-go-book-store-2"


def test_host_grader_and_aggregate_memory(tmp_path):
    client = Process(10, rss=2)
    grader = Process(20, rss=9)
    small = [Process(30 + i, 10, rss=6) for i in range(3)]
    g = guard(
        tmp_path, [client, grader, *small], per_process=8, aggregate=16, client_limit=16
    )
    g.register(client, "client")
    g.register(grader, "grader")
    g.tick()
    assert grader.dead and g.grader_mem_kill
    assert sum(not p.dead for p in small) == 2 and len(g.mem_kills) == 1
    client.rss = 17
    g.tick()
    assert g.client_resource and client.dead


def test_monitor_death_aborts(tmp_path):
    g = guard(tmp_path, [])
    g.failure = RuntimeError("monitor died")
    with pytest.raises(TransportAbort, match="monitor"):
        g.check()


def test_silence_tracks_shell_ancestry_not_opencode_server(tmp_path):
    client = Process(10, argv=["opencode", "run"])
    server = Process(11, 10, argv=["opencode", "serve"])
    processes = [client, server]
    g = guard(tmp_path, processes)
    g.register(client, "client")
    g.tick()
    assert not g.descendants_alive()
    shell = Process(12, 11, argv=["/bin/zsh", "-c", "sleep 10"])
    child = Process(13, 12, argv=["sleep", "10"])
    processes += [shell, child]
    g.tick()
    shell.dead = True
    child.parent = 1
    assert g.descendants_alive()


@pytest.mark.parametrize(
    "busy,desc,expected",
    [(1, True, None), (1, False, None), (0, True, "exec_timeout"), (0, False, "client_exit_hang")],
)
def test_silence_observations(busy, desc, expected):
    if expected == "abort":
        with pytest.raises(TransportAbort, match="client silent, worker idle"):
            pg.silence({"summary": {"in_flight": busy}}, desc)
    else:
        assert pg.silence({"summary": {"in_flight": busy}}, desc) == expected


def test_cancellation_summary_and_timeout():
    values = iter([{"summary": {"in_flight": 1}}, {"summary": {"in_flight": 0}}])
    pg.wait_cancel(lambda: next(values), sleep=lambda n: None)
    with pytest.raises(TransportAbort, match="did not cancel"):
        pg.wait_cancel(lambda: {"summary": {"in_flight": 1}}, timeout=0)
    for data in [{}, {"in_flight": 0}, {"summary": {"in_flight": True}}]:
        with pytest.raises(TransportAbort):
            pg.in_flight(data)


def test_interrupted_atomic_write_and_torn_loader(tmp_path, monkeypatch):
    path = tmp_path / "rows.jsonl"
    pg.atomic_write(path, b'{"id":"one"}\n')

    def failed(*a):
        raise OSError("interrupted")

    with monkeypatch.context() as m:
        m.setattr(pg.os, "replace", failed)
        with pytest.raises(OSError):
            pg.atomic_write(path, b"new")
    assert path.read_bytes() == b'{"id":"one"}\n'
    path.write_text('{"id":"one"}')
    with pytest.raises(TransportAbort, match="torn"):
        pg.load_rows(path)


def test_identity_drift_append_and_exact_items():
    identity = dict(pid=1, create_time=2, model_path="model", registry_sha256="sha")
    pg.require_identity(identity, dict(identity))
    for key in identity:
        with pytest.raises(TransportAbort):
            pg.require_identity(identity, {**identity, key: None})
    pg.expect_items([{"id": "a"}, {"id": "b"}], ["b", "a"])
    for rows in [[{"id": "a"}], [{"id": "a"}, {"id": "a"}, {"id": "b"}]]:
        with pytest.raises(TransportAbort):
            pg.expect_items(rows, ["a", "b"])


def test_immutable_evidence_refuses(tmp_path):
    p = tmp_path / "evidence"
    pg.reserve_evidence(p)
    with pytest.raises(TransportAbort):
        pg.reserve_evidence(p)


def test_real_detached_child_and_host_grader_allocation(tmp_path):
    # No model or external server: a short-lived fixture shell and a 24 MiB Python grader.
    import psutil

    with pg.ProcessGuard(
        [tmp_path], per_process=20 * 1024**2, aggregate=64 * 1024**2, interval=0.01
    ) as g:
        shell = g.spawn(
            [sys.executable, "-c", "import os,time; os.setsid(); time.sleep(10)"],
            role="model",
            cwd=tmp_path,
        )
        child = psutil.Process(shell.pid)
        result = g.run_grader(
            [
                sys.executable,
                "-c",
                "import time; x=bytearray(24*1024**2); time.sleep(10)",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode != 0 and g.grader_mem_kill
    shell.wait(timeout=2)
    assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE


def test_real_rapid_fork_detach_chdir_is_attributed_or_diagnostic(tmp_path):
    import psutil

    scratch = tmp_path / "scratch"
    escaped = tmp_path / "escaped"
    scratch.mkdir()
    escaped.mkdir()
    marker = escaped / "pid"
    script = tmp_path / "fork_fixture.py"
    script.write_text(
        "import os,time,pathlib\n"
        "if os.fork(): os._exit(0)\n"
        "os.setsid()\n"
        "if os.fork(): os._exit(0)\n"
        f"os.chdir({str(escaped)!r})\n"
        f"pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(15)\n"
    )
    g = pg.ProcessGuard([scratch], interval=0.5).start()
    proc = g.spawn([sys.executable, str(script)], cwd=scratch)
    pid = None
    try:
        proc.wait(timeout=3)
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        pid = int(marker.read_text())
        g.cleanup()
        assert any(key[0] == pid for key in g.tracked) or any(
            entry["pid"] == pid for entry in g.orphans_unattributed
        )
    finally:
        g.cleanup()
        if pid and psutil.pid_exists(pid):
            psutil.Process(
                pid
            ).kill()  # This fixture knows its own child independently of H1.


class Exiting(Process):
    """macOS: reads of an own-uid process mid-exit raise AccessDenied (sysctl KERN_PROCARGS2 -> EINVAL), not
    NoSuchProcess (C148, observed in test_resume_accepts_gather_runtime_observations ~1 in 5 runs)."""

    def __init__(self, *args, fail=("cmdline",), **kwargs):
        super().__init__(*args, **kwargs)
        self.fail = set(fail)

    def _maybe(self, name, value):
        if name in self.fail:
            import psutil
            raise psutil.AccessDenied(self.pid)
        return value

    def cmdline(self):
        return self._maybe("cmdline", self.argv)

    def memory_info(self):
        return self._maybe("memory_info", SimpleNamespace(rss=self.rss))

    def ppid(self):
        return self._maybe("ppid", self.parent)

    def create_time(self):
        return self._maybe("create_time", self.created)


@pytest.mark.parametrize("fail", [("cmdline",), ("memory_info",), ("ppid",), ("create_time",),
                                  ("cmdline", "memory_info", "ppid", "create_time")])
def test_access_denied_on_exiting_process_is_transient_not_monitor_death(tmp_path, fail):
    client = Process(10, argv=["opencode", "run"])
    child = Exiting(11, 10, rss=1, argv=["bash", "-c", "x"], fail=fail)
    hog = Process(12, 10, rss=9)
    g = guard(tmp_path, [client, child, hog], per_process=8, aggregate=64, client_limit=64)
    g.register(client, "client")
    g.tick()                      # must not raise: one unreadable exiting process is skipped this tick
    assert hog.dead and not child.dead
    child.fail = set()
    g.tick()                      # readable again: classified and tracked normally
    assert g.tracked.get((11, 10)) == "model"
