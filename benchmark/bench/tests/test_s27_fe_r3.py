"""S27 -- test-writer delivery 5: scenario tests for the round-3 findings (Z1, Z2, Z3, Z5, Z6) beyond the implementer's
`test_s27_impl_r3fix.py` (read first): whole-tick leak checks on the watcher, real processes for identity, the two
consumers' item-record rule, the scan with a reused session, and a typed fault surviving a failing cleanup through the probe's own
final-grade regrade.

Class (a) = reproduces a candidate-3 defect (by inspection of `../scratch/fix-3.patch`: candidate 3 cannot be run beside
candidate 4), (b) = preserves an invariant, (c) = new behaviour.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from bench import p426_hooks as ph
from bench import proc_guard as pg
from bench.tests.test_s27_fe_r1 import _alive, _cleanup, _probe_with_member, _scan
from bench.tests.test_s27_fe_r2 import _problems
from bench.tests.test_s27_impl_r2fix import acct_leg

MARKER = "Z6-LEAK-MARKER-5f3a"
TITLE = "service: indexing the archive for the review"


def _stop(p):
    p.kill()
    p.wait(timeout=10)


# ------------------------------------------------------------------------------------------------ Z6: the watcher records no argument text
def test_z6_a_real_boxsampler_tick_carries_the_marker_of_a_busy_process_nowhere(tmp_path):
    """(a) spec v1.5 §8.1 / Z6: the watch journal is a `main` record the harvest requires; the sampled top-CPU processes carry
    the executable basename and `argc`, never argument text. The marker is an argument of a real busy process; it must not
    appear anywhere in the whole tick, nor in any alert (candidate 3 wrote the scrubbed argv)."""
    bw = importlib.import_module("m1.bench_watch")
    p = subprocess.Popen([sys.executable, "-c", "while True: pass", f"--token={MARKER}", MARKER],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        sampler = bw.BoxSampler(os.getpid(), tmp_path / "probe", scrub=str)
        sampler()
        seen, tick = False, {}
        for _ in range(25):
            time.sleep(0.3)
            tick = sampler()
            if any(r.get("pid") == p.pid for r in tick["top_cpu"]):
                seen = True
                break
        assert seen, "the busy process never reached the top five (the test would prove nothing)"
        assert MARKER not in json.dumps(tick, default=str)
        assert all("argv" not in r for r in tick["top_cpu"])
        streak = {}
        alerts = []
        for _ in range(bw.FOREIGN_CPU_ALERT_TICKS + 1):
            alerts = bw.box_alerts(dict(tick, top_cpu=[dict(r, ownership="foreign") for r in tick["top_cpu"]]), None, streak)
        assert MARKER not in json.dumps(alerts)
    finally:
        _stop(p)


# ------------------------------------------------------------------------------------------------ Z5: identity is the executable
def test_z5_a_real_foreign_process_with_a_title_and_secret_arguments_is_recorded_by_its_executable_only(tmp_path):
    """(a) Z5: `foreign_new` takes the executable's basename and argc, never argv[0] free text and never an argument."""
    from bench.tests.test_s27_impl_guard import FOREIGN_SID, make
    procs, sessions = [], {}
    g, mp = make(tmp_path, procs, sessions=sessions)                  # the guard first: the process is new, not older
    p = None
    try:
        p = subprocess.Popen([TITLE, "-c", "import time; time.sleep(60)", f"--token={MARKER}"], executable=sys.executable,
                             start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and psutil.Process(p.pid).cmdline()[:1] != [TITLE]:
            time.sleep(0.02)
        proc = psutil.Process(p.pid)
        want = Path(proc.exe()).name
        procs.append(proc)
        sessions[p.pid] = FOREIGN_SID
        g.cleanup()
        mp.undo()
        status = g.status()
        (entry,) = [e for e in status["foreign_new"] if e["pid"] == p.pid]
        assert entry["argv"] == [want] and entry["argc"] == 4
        assert MARKER not in json.dumps(status) and "indexing" not in json.dumps(status)
        assert p.poll() is None, "a foreign process is recorded, never killed"
    finally:
        mp.undo()
        if p is not None:
            _stop(p)


# ------------------------------------------------------------------------------------------------ Z2: a reused session
def test_z2_a_live_leader_that_is_not_the_recorded_probe_claims_nothing_and_its_other_members_leave_the_scan_uncertain():
    """(a) Z2 / Z7 and the designer's ruling C5: the leader pid is in the snapshot but its start is not the recorded probe's:
    nothing is claimed or killed (neither the leader nor its member), the reuse is recorded, and because members of that session
    id are left unclaimed the scan does not claim to be certain."""
    stranger, member = _probe_with_member("time.sleep(120)")
    try:
        time.sleep(0.3)
        real = pg.start_time(psutil.Process(stranger.pid))
        result = _scan(sid=stranger.pid, not_before=real - 10 ** 6)
        assert result["session_reused"] and result["session_reused"]["pid"] == stranger.pid
        assert result["killed"] == []
        assert _alive(stranger.pid) and _alive(member)
        assert result["certain"] is False
    finally:
        _cleanup(stranger, member)


def test_z2_the_recorded_probe_session_is_still_claimed_and_certain_after_the_snapshot_first_rule():
    """(b) the other side: the recorded probe leading its session claims its member, and the scan is not made uncertain by
    that."""
    probe, member = _probe_with_member("time.sleep(120)")
    try:
        time.sleep(0.3)
        result = _scan(sid=probe.pid, not_before=pg.start_time(psutil.Process(probe.pid)))
        assert result["session_reused"] is None
        assert any(k["pid"] == member for k in result["killed"])
    finally:
        _cleanup(probe, member)


# ------------------------------------------------------------------------------------------------ Z3: a sidecar naming no item record
@pytest.mark.parametrize("what, kw, accepted", [
    ("no item record exists and the sidecar names none (the hook never wrote it)", dict(record=False, recorded=False), True),
    ("no item record exists, a failure is recorded, the sidecar names none", dict(record=False, recorded=True), True),
    ("an item record exists and the sidecar names it", dict(), True),
    ("an item record exists, the sidecar names none, a failure is recorded", dict(named=False, recorded=True), False),
    ("an item record exists, the sidecar names none, nothing is recorded", dict(named=False, recorded=False), False),
    ("no item record exists but the sidecar names one", dict(record=False, item_record_sha256="a" * 64), False),
], ids=["absent-unrecorded", "absent-recorded", "named", "present-unnamed-recorded", "present-unnamed-unrecorded", "absent-but-named"])
def test_z3_freeze_and_harvest_take_a_null_item_record_only_when_the_record_is_absent(tmp_path, what, kw, accepted):
    """(a) Z3: a sidecar may name no item record if and only if none exists at the slot attempt's path; whatever the chain
    recorded does not authorise it (candidate 3 authorised it by ANY recorded accounting entry). Both consumers agree."""
    root, chain, _ = acct_leg(tmp_path, **kw)
    freeze, harvest = _problems(root, chain)
    if accepted:
        assert freeze == [] and harvest == [], what
    else:
        assert freeze and harvest, what


# ------------------------------------------------------------------------------------------------ Z1: a typed fault survives a failing cleanup
def test_z1_a_docker_status_fault_whose_container_removal_also_fails_is_still_regraded_inside_the_probe(tmp_path):
    """(a) Z1 / Y2: the probe's own final-grade loop regrades a TYPED grader infrastructure fault; the failing `docker rm` of
    the first attempt must not turn it into a plain abort (candidate 3's `finally` replaced the primary with the cleanup error).
    One generation is graded twice on the same snapshot; the second attempt passes."""
    from types import SimpleNamespace
    from bench import arm_runner as runner
    from bench import structured_grade as sg
    from bench.tests.test_s27_impl_r3fix import CleanupFailsGuard

    calls = []

    class Guard(CleanupFailsGuard):
        def kill_role(self, role=None):
            return []

    def run(cmd, stdout=None, stderr=None, **kw):
        calls.append(cmd)
        if len(calls) == 1:                                           # `docker run` itself fails
            stderr.write("docker: Error response from daemon: failed to create task")
            return subprocess.CompletedProcess(cmd, 125, None, None)
        stdout.write(json.dumps(dict(Action="pass", Package="p", Test="TestA")) + "\n")
        return subprocess.CompletedProcess(cmd, 0, None, None)

    guard = Guard(OSError(5, "Input/output error"))
    state = {"n": 0}
    real_remove = guard.remove_container

    def remove(name):
        state["n"] += 1
        if state["n"] > 1:                                            # only the first removal fails
            guard.removed.append(name)
            return None
        return real_remove(name)
    guard.remove_container = remove

    class Corpus:
        def grade(self, snap, prepared, private, guard, keep, seq, boundary, final):
            return sg.grade("go", tmp_path, "a_test.go", tmp_path, run=run, guard=guard)
    termination = {}
    result = runner.final_grade(Corpus(), None, None, tmp_path, guard, None, lambda: 1, 1, termination)
    assert result is not None and len(calls) == 2
    assert termination["final_regrades"] == 1 and len(termination["final_grade_faults"]) == 1
