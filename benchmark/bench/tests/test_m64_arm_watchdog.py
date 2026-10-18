"""M64 step 4a: the adapter shell watchdog (spec 5.4): attribution to tool windows, the 600 s deadline, kill order, and
the contract positives (foreground, background, a child that detaches AFTER it was observed) on real processes."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import psutil
import pytest

from bench import arm_watchdog as wd


class Fake:
    """Scriptable process table + signal sink for the watchdog's three seams."""

    def __init__(self):
        self.now = 1000.0
        self.table = {}                 # pid -> Proc (live)
        self.signals = []               # (pid, ident, signame)
        self.descendants = None         # None: every live process is a descendant; else a set of pids

    def add(self, pid, wall_start, ppid=1, ident=None):
        self.table[pid] = wd.Proc(pid=pid, ident=ident if ident is not None else wall_start, wall_start=wall_start,
                                  ppid=ppid)

    def listing(self):
        return [p for pid, p in self.table.items() if self.descendants is None or pid in self.descendants]

    def alive(self, pid, ident):
        p = self.table.get(pid)
        return p is not None and p.ident == ident

    def send(self, pid, ident, sig):
        self.signals.append((pid, ident, sig.name))
        if sig == signal.SIGKILL or self.dies_on_term:
            self.table.pop(pid, None)

    dies_on_term = False

    def dog(self, **kw):
        kw.setdefault("limit_s", 600.0)
        kw.setdefault("grace_s", 5.0)
        return wd.ShellWatchdog(clock=lambda: self.now, listing=self.listing, alive=self.alive, send=self.send, **kw)


def test_defaults_are_the_spec_values():
    assert wd.LIMIT_S == 600.0 and wd.GRACE_S == 5.0


def test_a_descendant_started_inside_an_open_window_is_killed_after_600_s_term_then_kill():
    f = Fake()
    dog = f.dog()
    dog.open_window("t1", "shell", 1000.0)
    f.add(10, 1001.0)
    f.now = 1500.0
    assert dog.tick() == []                                   # 499 s old
    f.now = 1602.0                                            # 601 s old
    killed = dog.tick()
    assert [(k["pid"], k["action"]) for k in killed] == [(10, "SIGTERM")]
    assert f.signals == [(10, 1001.0, "SIGTERM")]
    f.now = 1604.0
    assert dog.tick() == [] and len(f.signals) == 1           # inside the 5 s grace: nothing more
    f.now = 1607.5
    assert [(k["pid"], k["action"]) for k in dog.tick()] == [(10, "SIGKILL")]
    assert f.signals[-1] == (10, 1001.0, "SIGKILL")
    assert dog.exec_timeout is True
    assert [k["pid"] for k in dog.kills] == [10]
    assert dog.kills[0]["window"]["name"] == "shell"


def test_no_sigkill_when_the_term_worked():
    f = Fake()
    f.dies_on_term = True
    dog = f.dog()
    dog.open_window("t1", "shell", 1000.0)
    f.add(10, 1001.0)
    f.now = 1700.0
    dog.tick()
    f.now = 1710.0
    assert dog.tick() == []
    assert [s[2] for s in f.signals] == ["SIGTERM"]


def test_a_helper_started_outside_any_window_is_never_attributed():
    f = Fake()
    dog = f.dog()
    f.add(20, 900.0)                                          # an LSP server / indexer: before any window
    dog.open_window("t1", "shell", 1000.0)
    dog.close_window("t1", 1010.0)
    f.add(21, 1020.0)                                         # started after the window closed
    f.now = 5000.0
    assert dog.tick() == [] and f.signals == []
    assert dog.exec_timeout is False


def test_a_closed_window_still_attributes_what_started_inside_it():
    f = Fake()
    dog = f.dog()
    dog.open_window("t1", "shell", 1000.0)
    f.add(10, 1005.0)
    dog.close_window("t1", 1010.0)                            # the tool returned; its background child lives on
    f.now = 1620.0
    assert [k["pid"] for k in dog.tick()] == [10]


def test_parallel_tool_calls_attribute_to_the_earliest_open_window():
    f = Fake()
    dog = f.dog()
    dog.open_window("a", "shell", 1000.0)
    dog.open_window("b", "shell", 1002.0)
    f.add(10, 1003.0)
    f.now = 1700.0
    killed = dog.tick()
    assert killed[0]["window"]["key"] == "a"


def test_attributed_descendants_of_an_offender_die_with_it_but_unattributed_ones_do_not():
    f = Fake()
    dog = f.dog()
    dog.open_window("t1", "shell", 1000.0)
    f.add(10, 1001.0, ppid=5)
    f.add(11, 1002.0, ppid=10)                                # child of the offender, started in the window
    f.add(12, 900.0, ppid=10)                                 # child of the offender but older than the window: not attributed
    f.now = 1700.0
    pids = [k["pid"] for k in dog.tick()]
    assert sorted(pids) == [10, 11] and 12 not in pids


def test_a_child_that_detaches_after_it_was_observed_is_still_killed():
    f = Fake()
    dog = f.dog()
    dog.open_window("t1", "shell", 1000.0)
    f.add(10, 1001.0, ppid=5)
    f.now = 1100.0
    assert dog.tick() == []                                   # observed here
    f.descendants = set()                                     # reparented to init: no longer a descendant of the client
    f.now = 1700.0
    killed = dog.tick()
    assert [k["pid"] for k in killed] == [10] and f.signals[0][2] == "SIGTERM"


def test_a_child_that_detached_before_it_was_ever_observed_is_the_disclosed_residual():
    f = Fake()
    dog = f.dog()
    dog.open_window("t1", "shell", 1000.0)
    f.descendants = set()
    f.add(10, 1001.0, ppid=1)
    f.now = 1700.0
    assert dog.tick() == [] and f.signals == []              # G2 residual: disclosed, not a pass criterion


def test_pid_reuse_is_never_signalled():
    f = Fake()
    dog = f.dog()
    dog.open_window("t1", "shell", 1000.0)
    f.add(10, 1001.0)
    dog.tick()
    f.now = 1700.0
    f.table[10] = wd.Proc(pid=10, ident=1650.0, wall_start=1650.0, ppid=1)   # the pid was reused by another process
    f.descendants = set()
    assert dog.tick() == [] and f.signals == []


def test_a_vanished_process_is_forgotten_and_never_signalled():
    f = Fake()
    dog = f.dog()
    dog.open_window("t1", "shell", 1000.0)
    f.add(10, 1001.0)
    dog.tick()
    del f.table[10]
    f.now = 1700.0
    assert dog.tick() == [] and f.signals == []


def test_set_windows_replaces_the_windows_from_an_event_stream():
    f = Fake()
    dog = f.dog()
    f.add(10, 1005.0)
    dog.tick()
    f.now = 1700.0
    assert dog.tick() == []                                   # no window known yet (opencode reports a tool at its end)
    dog.set_windows([(1000.0, 1010.0, "shell")])
    assert [k["pid"] for k in dog.tick()] == [10]


def test_a_tool_that_exceeds_the_deadline_is_flagged_even_without_a_child():
    f = Fake()
    dog = f.dog()
    dog.set_windows([(1000.0, 1700.0, "shell")])              # a 700 s tool window reported at its end
    f.now = 1701.0
    dog.tick()
    assert dog.window_overruns == [dict(name="shell", start=1000.0, end=1700.0, duration_s=700.0)]
    assert dog.exec_timeout is True


# ------------------------------------------------------------------ real processes (spec 6: contract positives)
def _live(pid):
    try:
        return psutil.Process(pid).status() not in ("zombie", "dead")
    except psutil.NoSuchProcess:
        return False


def _wait(predicate, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _tick_until(dog, cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        dog.tick()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_real_foreground_process_over_the_limit_is_terminated():
    start = time.time()
    proc = subprocess.Popen(["sleep", "60"])
    try:
        dog = wd.ShellWatchdog.for_client(os.getpid(), limit_s=1.0, grace_s=0.5, only={proc.pid})
        dog.open_window("t1", "shell", start - 0.5)
        dog.tick()
        assert proc.poll() is None                            # not yet over the limit
        assert _tick_until(dog, lambda: proc.poll() is not None)
        assert dog.exec_timeout and [k["pid"] for k in dog.kills] == [proc.pid]
    finally:
        proc.kill()
        proc.wait(10)


def test_real_background_process_over_the_limit_is_terminated_with_its_group_member():
    start = time.time()
    proc = subprocess.Popen(["sh", "-c", "sleep 60 & wait"])
    try:
        dog = wd.ShellWatchdog.for_client(os.getpid(), limit_s=1.0, grace_s=0.5)
        dog.open_window("t1", "shell", start - 0.5)
        pids = lambda: {proc.pid} | {c.pid for c in psutil.Process(proc.pid).children(recursive=True)} \
            if proc.poll() is None else set()
        assert _wait(lambda: len(pids()) == 2, 5)
        child = (pids() - {proc.pid}).pop()
        assert _tick_until(dog, lambda: proc.poll() is not None and not _live(child))
        assert dog.exec_timeout
    finally:
        proc.kill()
        proc.wait(10)


def test_real_child_that_detaches_after_being_observed_is_still_terminated(tmp_path):
    """sh forks `sleep 60`, the watchdog observes it as a descendant, then sh exits and the sleep is reparented to
    init (no longer a descendant): the (pid, start) identity recorded at observation still gets it killed."""
    gate = tmp_path / "go"
    start = time.time()
    proc = subprocess.Popen(["sh", "-c", f"sleep 60 & echo $! > {tmp_path}/pid; while [ ! -e {gate} ]; do sleep 0.05; done"])
    try:
        dog = wd.ShellWatchdog.for_client(os.getpid(), limit_s=1.0, grace_s=0.5)
        dog.open_window("t1", "shell", start - 0.5)
        assert _wait(lambda: (tmp_path / "pid").exists() and (tmp_path / "pid").read_text().strip(), 5)
        child = int((tmp_path / "pid").read_text())
        dog.tick()                                            # the sleep is observed while still a descendant
        gate.write_text("x")                                  # sh exits; the sleep is orphaned
        proc.wait(10)
        assert _live(child) and psutil.Process(child).ppid() != proc.pid
        assert _tick_until(dog, lambda: not _live(child))
        assert any(k["pid"] == child for k in dog.kills)
    finally:
        proc.kill()
        proc.wait(10)
