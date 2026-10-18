"""P371 deterministic real-guard tests. ROOT CAUSE (proven): `proc_guard.ProcessGuard`'s cleanup sweep lists every same-uid live
process; a launchd-parented (ppid 1) process in another session that started during the item window and is not tracked lands in
`orphans_unattributed` (macOS Spotlight's `mdworker_shared` fits exactly), so the A14 goldens / differentials depended on box
activity. `hermetic_scan.FamilyScan` limits the sweep's view to the guarded process family. These tests: (a) unit-test the scan,
(b) STRESS the four item scenarios on both sides of the baseline harness, and an in-process real-guard abort, with an ambient
generator of Spotlight-like processes running."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from contextlib import contextmanager
from pathlib import Path

import psutil
import pytest

GENERATOR = textwrap.dedent("""
    import os, sys, time
    end = time.time() + float(sys.argv[1])
    while time.time() < end:
        pid = os.fork()
        if pid == 0:
            os.setsid()
            if os.fork() == 0:
                os.execvp("sleep", ["sleep", "1.5"])
            os._exit(0)
        os.waitpid(pid, 0)
        time.sleep(0.3)
""")


@contextmanager
def ambient(seconds=900):
    """A generator of short-lived launchd-parented, setsid'd same-uid processes (like Spotlight's mdworker), itself fully
    detached (double fork + setsid) so it is no descendant of this process and its session is never observed."""
    pidfile = Path(tempfile.mkdtemp(prefix="p371-ambient-")) / "pid"
    if os.fork() == 0:
        os.setsid()
        if os.fork() == 0:
            pidfile.write_text(str(os.getpid()))
            os.execvp(sys.executable, [sys.executable, "-c", GENERATOR, str(seconds)])
        os._exit(0)
    os.wait()
    for _ in range(100):
        if pidfile.exists() and pidfile.read_text():
            break
        time.sleep(0.05)
    pid = int(pidfile.read_text())
    try:
        yield pid
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for _ in range(100):
            if not psutil.pid_exists(pid):
                break
            time.sleep(0.05)
        assert not psutil.pid_exists(pid), "the ambient generator survived"


def _spawn(code):
    return subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)


# ------------------------------------------------------------------------------------------------ (a) unit
def test_a_foreign_session_process_started_during_a_scan_is_invisible():
    from bench.tests import hermetic_scan as hs
    scan = hs.FamilyScan(os.getpid())
    scan()
    pidfile = Path(tempfile.mkdtemp(prefix="p371-foreign-")) / "pid"
    code = ("import os,time\nif os.fork()==0:\n os.setsid()\n if os.fork()==0:\n  open(%r,'w').write(str(os.getpid()))\n"
            "  time.sleep(30)\n os._exit(0)\n" % str(pidfile))
    subprocess.run([sys.executable, "-c", code], timeout=20)
    for _ in range(100):
        if pidfile.exists() and pidfile.read_text():
            break
        time.sleep(0.05)
    foreign = int(pidfile.read_text())
    try:
        assert psutil.Process(foreign).ppid() == 1 and os.getsid(foreign) != os.getsid(0)
        assert foreign in {p.pid for p in psutil.process_iter()}              # the real scan WOULD list it
        assert foreign not in {p.pid for p in scan()}
    finally:
        os.kill(foreign, signal.SIGKILL)


def test_a_double_forked_descendant_without_setsid_is_visible():
    from bench.tests import hermetic_scan as hs
    code = ("import os,time\nif os.fork()==0:\n print('grandchild', os.getpid(), flush=True)\n time.sleep(30)\n os._exit(0)\n"
            "time.sleep(30)\n")
    child = subprocess.Popen([sys.executable, "-u", "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        grand = int(child.stdout.readline().split()[1])
        seen = {p.pid for p in hs.FamilyScan(os.getpid())()}
        assert child.pid in seen and grand in seen
    finally:
        for pid in (child.pid,):
            os.kill(pid, signal.SIGKILL)
        try:
            os.kill(grand, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()


def test_the_session_of_an_observed_descendant_stays_visible_after_its_parent_dies():
    from bench.tests import hermetic_scan as hs
    code = ("import os,sys,time\nos.setsid()\nprint('go', flush=True)\nsys.stdin.readline()\n"
            "if os.fork()==0:\n print('orphan', os.getpid(), flush=True)\n time.sleep(30)\n os._exit(0)\nos._exit(0)\n")
    child = subprocess.Popen([sys.executable, "-u", "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    scan = hs.FamilyScan(os.getpid())
    try:
        child.stdout.readline()
        assert child.pid in {p.pid for p in scan()}                  # observed as a descendant: its session is recorded
        child.stdin.write("\n")
        child.stdin.flush()
        orphan = int(child.stdout.readline().split()[1])
        child.wait()
        for _ in range(100):
            if psutil.Process(orphan).ppid() == 1:
                break
            time.sleep(0.05)
        assert psutil.Process(orphan).ppid() == 1 and orphan in {p.pid for p in scan()}
    finally:
        for pid in (orphan,):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, UnboundLocalError):
                pass


def test_install_patches_the_default_scan_only_when_none_is_given():
    from bench.tests import hermetic_scan as hs

    class Guard:
        def __init__(self, roots, *, scan=None):
            self.scan = scan

    undo = hs.install(Guard, os.getpid())
    try:
        assert isinstance(Guard([]).scan, hs.FamilyScan)
        sentinel = object()
        assert Guard([], scan=sentinel).scan is sentinel
    finally:
        undo()
    assert Guard([]).scan is None


# ------------------------------------------------------------------------------------------------ (b) stress
ITEM_SCENARIOS = ["item_transport_abort", "item_resume_refusal", "item_normal_pass", "item_cooperative_cancel"]


def test_the_real_guard_reports_no_orphans_in_process_while_spotlight_like_processes_churn(tmp_path, monkeypatch):
    from bench.tests import test_p371_a3_core as a3
    from bench.tests.arm_neutral import NeutralArm
    from bench.tests.p371_world import neutral_world

    class Reporting(NeutralArm):
        report_gate_on_abort = True
    with ambient(120):
        world = neutral_world(monkeypatch, tmp_path)
        msg, stamp = a3.abort_of(world, a3.source(world, [dict(cls="task", seed=a3.SEED)]), adapter=Reporting(world.host))
        assert stamp["cleanup_status"]["orphans_unattributed"] == [] and stamp["cleanup_status"]["completed"] is True


def test_the_four_item_scenarios_match_their_goldens_on_both_sides_three_times_under_ambient_churn():
    from bench.tests.p371_baseline import bundle as B, compare as cmp_mod, new_side, runner as R
    with ambient(1500):
        with tempfile.TemporaryDirectory(prefix="p371-stress-") as tmp:
            bundle = Path(tmp) / "bundle"
            B.make_bundle(bundle)
            for name in ITEM_SCENARIOS:
                golden = R.load_golden(name)
                for i in range(3):
                    old = R.run_old_side(bundle, R.load_scenario(name))
                    assert {k: v for k, v in old.items() if not k.startswith("_")} == golden, (name, "bundle", i)
                    new = R.run_new_side(R.load_scenario(name))
                    res = cmp_mod.compare(golden, new, cmp_mod.TABLE, rederive=new_side.rederive(new))
                    assert res.ok, (name, "new", i, res.failures)
