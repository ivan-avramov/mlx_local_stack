"""S27 §5.8: the chain's own second scan (`ChainOps.owned_scan`) kills and verifies an OURS survivor of the recorded probe
session, never a process of another session; a scan whose kill cannot be verified is not certain."""
from __future__ import annotations

import os
import subprocess
import sys
import time

import psutil

from bench import chain_ops as co


def ops(tmp_path):
    return co.ChainOps(tmp_path, tmp_path, tmp_path / "overlay.yaml", lambda m: None, sleep=time.sleep)


def spawn_session():
    """A `sleep` that leads its own session (as the chain launches the probe: `start_new_session=True`)."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def probe_start():
    """X10: the session is bounded by the probe's recorded start; this test process stands for the probe (it started first)."""
    from bench import proc_guard as pg
    return pg.start_time(psutil.Process(os.getpid()))


def test_the_second_scan_kills_and_verifies_a_survivor_of_the_probe_session_and_spares_a_foreign_one(tmp_path):
    ours, foreign = spawn_session(), spawn_session()
    try:
        sid = os.getsid(ours.pid)
        from bench import proc_guard as pg       # Y3: the session leader IS the recorded probe (its own start)
        started = pg.start_time(psutil.Process(ours.pid))
        scan = ops(tmp_path).owned_scan(sid=sid, not_before=started, roots=[], container_prefixes=(), deadline_s=10.0)
        ours.wait(timeout=10)
        assert scan["certain"] is True and [k["pid"] for k in scan["killed"]] == [ours.pid]
        assert foreign.poll() is None and psutil.pid_exists(foreign.pid)
    finally:
        for p in (ours, foreign):
            if p.poll() is None:
                p.kill()
                p.wait(timeout=10)


def test_an_environment_under_the_runs_hermetic_root_is_ours(tmp_path):
    home = tmp_path / "run-x" / "home"
    home.mkdir(parents=True)
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
                         env=dict(os.environ, HOME=str(home)), stdin=subprocess.DEVNULL)
    try:
        scan = ops(tmp_path).owned_scan(sid=None, roots=[tmp_path / "run-x"], container_prefixes=(), deadline_s=10.0)
        p.wait(timeout=10)
        assert p.pid in [k["pid"] for k in scan["killed"]] and scan["certain"] is True
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=10)


def test_a_session_id_that_names_no_process_kills_nothing(tmp_path):
    scan = ops(tmp_path).owned_scan(sid=2 ** 30 + 7, not_before=probe_start(), roots=[], container_prefixes=(), deadline_s=5.0)
    assert scan["certain"] is True and scan["killed"] == []
