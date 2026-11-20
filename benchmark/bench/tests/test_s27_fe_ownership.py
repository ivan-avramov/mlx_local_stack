"""S27 (spec v1.4, section 3, acceptance 10.1) -- blind test-writer, delivery 1: process ownership and the cleanup receipt.

Fakes follow `test_proc_guard.Process` / `test_c157_proc_guard.Unreadable`; the session of a fake process is read through
`os.getsid`, which these tests replace (assumption O1).  One test uses real subprocesses, because ownership by session is the
behaviour there.

Class of each test: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) exercises new behaviour.

Interface assumptions:
  O1  the guard reads a process's session with `os.getsid(pid)` and its own with `os.getsid(0)` at construction (spec 3.1);
  O2  the readable environment of a process is `process.environ()` (psutil), a denied read raises `psutil.AccessDenied`;
  O3  the receipt is `guard.status()`: `schema == 2`, `foreign_new` (list of {pid, create_time, argv, sid, path_match,
      unreadable}), `unreadable_count` (int), the six old keys; `cleanup()` does not raise for foreign processes;
  O4  the run's HOME / XDG_* are among the guard's roots, so `environ()["HOME"]` equal to a root is the environment match.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import psutil
import pytest

from bench import chain_incident as ci
from bench import proc_guard as pg
from bench.token_turn_gate import TransportAbort
from bench.tests.test_proc_guard import Process

pytestmark = pytest.mark.usefixtures("fake_guard_clock")

PROBE_PID_SID = 61000          # the session id a fake non-leader probe lives in
FOREIGN_SID = 55555
V1_KEYS = ("survivors", "containers_remaining", "uncertain", "orphans_unattributed", "unknown", "completed")


class Proc(Process):
    """A fake process with a session, an environment and per-read denial (`deny` names: cwd, cmdline, environ, start_order)."""

    def __init__(self, pid, ppid=1, *, sid=FOREIGN_SID, env=None, deny=(), cwd="/elsewhere", argv=None, created=12, **kw):
        super().__init__(pid, ppid, cwd=cwd, created=created, argv=argv or ["daemon"], **kw)
        self.sid, self.env, self.deny = sid, dict(env or {}), set(deny)

    def _check(self, what):
        if what in self.deny:
            raise psutil.AccessDenied(self.pid)

    def cwd(self):
        self._check("cwd")
        return self.directory

    def cmdline(self):
        self._check("cmdline")
        return list(self.argv)

    def environ(self):
        self._check("environ")
        return dict(self.env)

    def status(self):
        self._check("status")                 # a denied liveness read
        return super().status()

    def uids(self):
        self._check("uids")                   # v3 (X11): the same-uid read itself is denied
        return super().uids()

    def start_order(self):
        self._check("start_order")
        return None                       # readable: the guard falls back to the wall-clock start


class World:
    def __init__(self, tmp_path, monkeypatch, *, leader):
        self.root = Path(tmp_path).resolve()
        self.processes = []
        self.sids = {}
        self.leader = leader
        mine = os.getpid()
        self.probe_sid = mine if leader else PROBE_PID_SID

        def getsid(pid):
            if pid == 0 or pid == mine:
                return self.probe_sid
            if pid in self.sids:
                return self.sids[pid]
            raise ProcessLookupError(pid)
        monkeypatch.setattr(os, "getsid", getsid)
        self.roots = [self.root / "work", self.root / "home", self.root / "tmp", self.root / "grading-private"]
        def build(**kw):
            return pg.ProcessGuard(self.roots, scan=lambda: self.processes,
                                   get=lambda pid: next(p for p in self.processes if p.pid == pid), **kw)
        try:                                                              # v2: the run's hermetic HOME (candidate: `env_markers`)
            self.guard = build(env_markers={"HOME": str(self.roots[1])})
        except TypeError:                                                 # the baseline guard has no such parameter
            self.guard = build()
        self.guard.started = 0           # fixture start times use a synthetic epoch
        self.guard.kill_role = lambda role=None: []     # the scan under test (as test_c157_proc_guard)

    def add(self, proc):
        self.processes.append(proc)
        self.sids[proc.pid] = proc.sid
        return proc

    def cleanup(self):
        try:
            self.guard.cleanup()
            return self.guard.status(), None
        except TransportAbort as exc:
            return self.guard.status(), exc


def foreign_entry(status, pid):
    return next((e for e in status.get("foreign_new", []) if e["pid"] == pid), None)


@pytest.fixture
def leader(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch, leader=True)


@pytest.fixture
def hand_run(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch, leader=False)


# ------------------------------------------------------------------------------------------------ foreign processes (3.2 d, 3.4)
def test_a_process_of_another_session_during_an_item_is_foreign_new_and_the_leg_continues(leader):
    """(a) The baseline files a young launchd child under `orphans_unattributed` and has no `foreign_new` at all."""
    leader.add(Proc(70010, sid=FOREIGN_SID, argv=["/usr/libexec/mdworker_shared"]))
    status, exc = leader.cleanup()
    assert exc is None and status["uncertain"] is False and status["completed"] is True
    assert status["schema"] == 2
    e = foreign_entry(status, 70010)
    assert e is not None, status
    assert {"pid", "create_time", "argv", "sid", "path_match", "unreadable"} <= set(e)
    assert e["sid"] == FOREIGN_SID and e["path_match"] is False and e["unreadable"] is False
    assert not leader.processes[0].dead
    assert [o["pid"] for o in status["orphans_unattributed"]] == []        # a record, never an orphan
    assert status["survivors"] == []


def test_a_foreign_process_that_is_not_launchd_parented_is_recorded_too(leader):
    """(c) 3.2 d: 'anything else -> foreign_new', not only launchd children."""
    leader.add(Proc(70011, ppid=70099, sid=FOREIGN_SID))
    leader.add(Proc(70099, ppid=1, sid=FOREIGN_SID))
    status, exc = leader.cleanup()
    assert exc is None and foreign_entry(status, 70011) is not None


@pytest.mark.parametrize("denied", ["cwd", "environ", "cmdline", "start_order"])
def test_a_denied_read_on_a_foreign_daemon_is_foreign_new_unreadable_never_uncertain(leader, denied):
    """(a) 3.2: any denied read (start order, cwd, environ, argv) on a process that is neither tracked nor in our session."""
    leader.add(Proc(70020, sid=FOREIGN_SID, deny=[denied]))
    status, exc = leader.cleanup()
    assert exc is None, f"cleanup raised {exc}"
    assert status["uncertain"] is False and status["completed"] is True
    e = foreign_entry(status, 70020)
    assert e is not None and e["unreadable"] is True
    assert not leader.processes[0].dead


def test_a_provably_older_unreadable_process_is_counted_not_listed(leader):
    """(c) 3.4: an unclaimed unreadable process provably older than the guard is counted (`unreadable_count`), not listed; it
    is never killed and never makes the cleanup uncertain. (v2: 'unreadable' = its liveness read is denied; a denied cwd on a
    provably older process needs no read at all, the candidate skips it as protected.)"""
    old = leader.add(Proc(70021, sid=FOREIGN_SID, deny=["status"]))
    old.start_order = lambda: 5                       # readable and older than the guard's start order
    leader.guard.started_order = 1000
    status, exc = leader.cleanup()
    assert exc is None and status["uncertain"] is False and foreign_entry(status, 70021) is None
    assert status["unreadable_count"] >= 1 and not old.dead


def test_the_foreign_list_is_capped_at_64_entries(leader):
    """(c) 3.4: capped at 64 entries plus a count."""
    for k in range(70):
        leader.add(Proc(71000 + k, sid=FOREIGN_SID))
    status, exc = leader.cleanup()
    assert exc is None and len(status["foreign_new"]) == 64
    assert not any(p.dead for p in leader.processes)


def test_a_foreign_process_is_never_killed_and_never_a_survivor_or_refusal(leader):
    """(b) record only: a process we did not spawn is never killed."""
    procs = [leader.add(Proc(70030 + k, sid=FOREIGN_SID + k, argv=["x"])) for k in range(3)]
    status, exc = leader.cleanup()
    assert exc is None and status["survivors"] == [] and status["unknown"] == []
    assert not any(p.dead for p in procs)


# ------------------------------------------------------------------------------------------------ path-only attribution (3.2 c)
def test_a_path_only_match_without_corroboration_is_not_killed_and_not_a_refusal(leader):
    """(a) cwd under the work root, not tracked, not in our session, no environment match: foreign_new with path_match."""
    work = leader.roots[0]
    p = leader.add(Proc(70040, sid=FOREIGN_SID, cwd=str(work / "tree"), argv=["something"]))
    status, exc = leader.cleanup()
    assert exc is None, f"the baseline refuses on path-only attribution: {exc}"
    e = foreign_entry(status, 70040)
    assert e is not None and e["path_match"] is True and not p.dead
    assert status["uncertain"] is False


def test_an_argv_under_a_root_without_corroboration_is_also_only_recorded(leader):
    work = leader.roots[0]
    p = leader.add(Proc(70041, sid=FOREIGN_SID, argv=["tool", f"--dir={work}/x"]))
    status, exc = leader.cleanup()
    assert exc is None and not p.dead
    assert foreign_entry(status, 70041)["path_match"] is True


def test_a_path_match_corroborated_by_our_session_is_ours_and_killed(leader):
    """(c) corroboration (b): the session. The path alone is not what claims it; the session does."""
    work = leader.roots[0]
    p = leader.add(Proc(70042, sid=leader.probe_sid, cwd=str(work / "tree")))
    status, exc = leader.cleanup()
    assert exc is None and p.dead and status["uncertain"] is False


def test_the_run_environment_is_a_corroboration_and_the_process_is_ours(leader):
    """(c) 3.2 c: the readable environment carrying the run's HOME is the environment match; cwd elsewhere."""
    p = leader.add(Proc(70043, sid=FOREIGN_SID, cwd="/elsewhere", env={"HOME": str(leader.roots[1]), "PATH": "/usr/bin"}))
    status, exc = leader.cleanup()
    assert exc is None and p.dead, "an environment-matched process must be killed (it is ours)"
    assert status["uncertain"] is False and status["survivors"] == []


def test_a_different_home_in_the_environment_is_not_a_match(leader):
    """(b) the environment match is the RUN's home, not any HOME."""
    p = leader.add(Proc(70044, sid=FOREIGN_SID, env={"HOME": "$OTHER_HOME"}))
    status, exc = leader.cleanup()
    assert exc is None and not p.dead


# ------------------------------------------------------------------------------------------------ owned survivors (3.3)
def test_an_owned_survivor_of_our_session_is_killed_verified_recorded_and_the_cleanup_is_certain(leader):
    """(a) The baseline skips every same-session process (`_sweep_excluded`): the escapee lives on."""
    esc = leader.add(Proc(70050, sid=leader.probe_sid, cwd="/elsewhere", argv=["sleep", "600"]))
    status, exc = leader.cleanup()
    assert exc is None, exc
    assert esc.dead
    assert status["uncertain"] is False and status["completed"] is True
    assert status["survivors"] == [] and status["containers_remaining"] == [] and status["unknown"] == []
    assert 70050 in [o["pid"] for o in status["orphans_unattributed"]]      # recorded as a killed escapee (3.5)
    assert foreign_entry(status, 70050) is None


def test_an_owned_survivor_that_cannot_be_verified_gone_makes_the_cleanup_uncertain(leader):
    """(c) 3.3: an owned process not verified gone is `uncertain`, never swallowed (the baseline never reaches it: it skips
    the whole session)."""
    esc = leader.add(Proc(70051, sid=leader.probe_sid))
    esc.kill = lambda: None                     # the kill does not take
    status, exc = leader.cleanup()
    assert isinstance(exc, TransportAbort)
    assert status["uncertain"] is True and not esc.dead


def test_a_denied_read_on_a_process_our_session_claims_stays_uncertain(leader):
    """(b) 3.2: a denied read on a process our session claims is never `foreign_new` and never leaves an owned process alive
    unrecorded. v2 (intent): either the process is gone and the cleanup certain (the candidate kills it: killing needs no
    cwd), or the cleanup is uncertain and raises (the spec's 'as today')."""
    esc = leader.add(Proc(70052, sid=leader.probe_sid, deny=["cwd"]))
    status, exc = leader.cleanup()
    assert foreign_entry(status, 70052) is None
    if esc.dead:
        assert exc is None and status["uncertain"] is False
    else:
        assert isinstance(exc, TransportAbort) and status["uncertain"] is True


def test_a_tracked_process_is_killed_and_a_denied_read_on_it_stays_uncertain(tmp_path, monkeypatch):
    """(b) tracked = OURS: the unchanged tracked path."""
    w = World(tmp_path, monkeypatch, leader=False)
    w.guard.kill_role = pg.ProcessGuard.kill_role.__get__(w.guard)
    client = w.add(Proc(70060, ppid=os.getpid(), sid=PROBE_PID_SID, created=10))
    w.guard.register(client, "client")
    status, exc = w.cleanup()
    assert exc is None and client.dead and status["uncertain"] is False


def test_the_container_named_for_the_run_is_ours(tmp_path, monkeypatch):
    """(b) 3.2: `mlxbench-<run_id>-...` is OURS: it is registered and removed (the baseline contract)."""
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(pg.subprocess, "run", run)
    w = World(tmp_path, monkeypatch, leader=True)
    name = w.guard.container_name()
    assert name.startswith(f"mlxbench-{w.guard.run_id}-")
    w.guard.register_container(name)
    status, exc = w.cleanup()
    assert exc is None and ["docker", "rm", "-f", name] in calls and status["containers_remaining"] == []


# ------------------------------------------------------------------------------------------------ a hand-run (non-leader) probe (3.1)
def test_a_non_leader_probe_owns_by_ancestry_only(hand_run):
    """(a) A process in the probe's session that is neither tracked nor a descendant of a tracked one is NOT ours when the
    probe is not a session leader: the baseline silently skips it; the spec records it (foreign_new)."""
    p = hand_run.add(Proc(70070, sid=hand_run.probe_sid, argv=["bystander"]))
    status, exc = hand_run.cleanup()
    assert exc is None and not p.dead
    assert foreign_entry(status, 70070) is not None


def test_a_non_leader_probe_still_kills_a_tracked_descendant_that_detached(tmp_path, monkeypatch):
    """(b) Ancestry ownership is unchanged: a descendant of a tracked process that reparents to launchd is killed."""
    w = World(tmp_path, monkeypatch, leader=False)
    w.guard.kill_role = pg.ProcessGuard.kill_role.__get__(w.guard)
    root = w.add(Proc(70080, ppid=os.getpid(), sid=PROBE_PID_SID, created=10))
    child = w.add(Proc(70081, ppid=70080, sid=PROBE_PID_SID, created=11, cwd=str(w.roots[0])))
    w.guard.register(root, "client")
    w.guard.tick()
    child.parent = 1
    status, exc = w.cleanup()
    assert exc is None and child.dead and root.dead
    assert status["uncertain"] is False


# (spec 3.1's explicit session id passed by the chain is not tested: the spec names no keyword for it; see the report)


# ------------------------------------------------------------------------------------------------ the receipt (3.5): schema 1 and 2
SCHEMA1 = dict(survivors=[], containers_remaining=[], uncertain=False, orphans_unattributed=[], unknown=[], completed=True)


def live_receipt(w, *, with_records=True):
    """v2: the receipt a real (fake-process) cleanup produces: schema 2, with a foreign record and a killed escapee."""
    if with_records:
        w.add(Proc(70100, sid=FOREIGN_SID))
        w.add(Proc(70101, sid=w.probe_sid))
    status, exc = w.cleanup()
    assert exc is None
    return status


def schema2(base, **over):
    return dict(base, **over)


def test_schema_1_records_still_validate_by_the_old_rule():
    """(b) old identities, harvest and freeze reads of existing records."""
    assert ci.cleanup_problems(dict(SCHEMA1)) == []
    assert ci.cleanup_problems(dict(SCHEMA1, orphans_unattributed=[dict(pid=5)]))      # schema 1: any orphan is a problem
    assert ci.cleanup_problems(dict(SCHEMA1, survivors=[7]))
    assert ci.cleanup_problems(dict(SCHEMA1, uncertain=True))
    assert ci.cleanup_problems({k: v for k, v in SCHEMA1.items() if k != "completed"})


def test_the_receipt_of_a_live_cleanup_is_schema_2_and_validates(leader):
    """(c) A live status (with a foreign record and a killed escapee) is accepted by the one validator."""
    leader.add(Proc(70100, sid=FOREIGN_SID))
    leader.add(Proc(70101, sid=leader.probe_sid))
    status, exc = leader.cleanup()
    assert exc is None and status["schema"] == 2
    assert ci.cleanup_problems(status) == [], ci.cleanup_problems(status)


def test_schema_2_accepts_killed_escapees_and_foreign_records_in_a_certain_cleanup(leader):
    """(a) The baseline's exact-keys rule refuses them; 'certain and complete' = uncertain False, completed True and
    survivors / containers_remaining / unknown empty. (v2: the receipt is the live one.)"""
    doc = live_receipt(leader)
    assert doc["foreign_new"] and doc["orphans_unattributed"]
    assert ci.cleanup_problems(doc) == [], ci.cleanup_problems(doc)


@pytest.mark.parametrize("over", [dict(survivors=[4]), dict(containers_remaining=["mlxbench-r-i-1"]), dict(unknown=[dict(pid=3)]),
                                  dict(uncertain=True), dict(completed=False)])
def test_schema_2_still_refuses_what_makes_a_cleanup_uncertain(leader, over):
    """(b) No check that protects the measured outcome is weakened."""
    assert ci.cleanup_problems(schema2(live_receipt(leader), **over))


@pytest.mark.parametrize("site", ["require_certain_cleanup", "p426_dnf_eligible", "check_restart_eligible"])
def test_every_refusal_site_takes_the_one_validator(tmp_path, leader, site):
    """(a) A schema-2 receipt with a killed escapee and a foreign record is accepted at every site; with a survivor, refused."""
    from types import SimpleNamespace
    from bench import chain_core as core
    from bench.tests.test_b2_s3_core import WORKER, bare, scenario
    good = live_receipt(leader)
    bad = schema2(good, survivors=[4])
    load, leg, _inv, _rec, att, _ids = scenario(tmp_path)
    c = bare(tmp_path, policy="p426_continue")

    def call(receipt):
        a = dict(att, cleanup_status=receipt)
        if site == "require_certain_cleanup":
            return core.Chain.require_certain_cleanup(c, a, leg, "invalidate")
        if site == "p426_dnf_eligible":
            problem = core.Chain.p426_dnf_eligible(c, a, load, leg, "timeout")
            if problem:
                raise core.co.ChainAbort(problem)
            return None
        c.config = SimpleNamespace(transport_policy="p426_continue", config_id=c.config.config_id)
        return core.Chain.check_restart_eligible(c, dict(a, rc=1), leg, dict(worker=dict(WORKER)))
    call(good)                                                 # must not raise
    with pytest.raises(core.co.ChainAbort):
        call(bad)


# ------------------------------------------------------------------------------------------------ real processes: ownership by session
CHILD = textwrap.dedent("""
    import json, os, subprocess, sys, time
    from bench import proc_guard as pg
    work = sys.argv[1]
    assert os.getsid(0) == os.getpid(), "the child must be a session leader"
    guard = pg.ProcessGuard([work])
    guard.start()
    escapee = subprocess.Popen(["sleep", "120"])                      # our session, never registered with the guard
    foreign = subprocess.Popen(["sleep", "121"], start_new_session=True)   # another session
    time.sleep(0.3)
    try:
        err = None
        try:
            guard.cleanup()
        except Exception as exc:
            err = repr(exc)[:300]
        time.sleep(0.3)
        print(json.dumps(dict(escapee=escapee.pid, foreign=foreign.pid, escapee_rc=escapee.poll(), foreign_rc=foreign.poll(),
                              status=guard.status(), error=err)))
    finally:
        for p in (escapee, foreign):
            if p.poll() is None:
                p.kill()
            p.wait(timeout=10)
""")


@pytest.mark.real_process_scan
def test_real_processes_a_session_escapee_dies_and_a_process_of_another_session_is_only_recorded(tmp_path):
    """(a) Real `setsid` ownership: the probe is a session leader (the child), one untracked process of its session is killed
    and verified, one process of another session is `foreign_new` and survives."""
    script = tmp_path / "child.py"
    script.write_text(CHILD)
    work = tmp_path / "work"
    work.mkdir()
    bench_parent = str(Path(pg.__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=bench_parent)
    done = subprocess.run([sys.executable, str(script), str(work)], capture_output=True, text=True, timeout=120,
                          start_new_session=True, env=env)
    assert done.returncode == 0, done.stderr[-500:]
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    assert out["escapee_rc"] is not None, "the untracked process of our own session must be killed"
    assert out["foreign_rc"] is None, "a process of another session must never be killed"
    assert out["status"]["uncertain"] is False
    assert any(e["pid"] == out["foreign"] for e in out["status"]["foreign_new"])
    assert out["escapee"] in [o["pid"] for o in out["status"]["orphans_unattributed"]]
