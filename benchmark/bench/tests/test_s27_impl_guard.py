"""S27 §3 (P12, D2): the process guard owns what the harness spawned — tracked identities and their ancestry, the probe's own
session when it leads it, a corroborated environment match — and records everything else as `foreign_new` (receipt schema 2)."""
from __future__ import annotations

import os

import pytest

from bench import chain_incident as ci
from bench import proc_guard as pg
from bench.tests.test_proc_guard import Process
from bench.token_turn_gate import TransportAbort

PROBE_SID, FOREIGN_SID = os.getpid(), 777      # X17: a leader's session id is its own pid (no explicit session parameter)


class Denied(Process):
    """A same-uid process whose start order / cwd / environ reads are denied (a foreign daemon mid-exec)."""

    def __init__(self, *a, deny=("start_order",), **k):
        super().__init__(*a, **k)
        self.deny = set(deny)

    def _denied(self):
        import psutil
        raise psutil.AccessDenied(self.pid)

    def start_order(self):
        if "start_order" in self.deny:
            self._denied()
        return None

    def cwd(self):
        if "cwd" in self.deny:
            self._denied()
        return super().cwd()

    def environ(self):
        if "environ" in self.deny:
            self._denied()
        return {}


class EnvProcess(Process):
    def __init__(self, *a, env=None, **k):
        super().__init__(*a, **k)
        self.env = dict(env or {})

    def environ(self):
        return dict(self.env)


def make(tmp_path, processes, *, sessions, leader=True, markers=None, roots=None):
    """A guard over scripted processes; `sessions[pid]` is each one's session id; with `leader` the probe leads its session
    PROBE_SID (§3.1: `getsid(0) == getpid()`, as when the chain launched it with `start_new_session=True`); without it the
    guard's own session is another one (a hand run). The session patch is undone by the caller (`mp.undo()`)."""
    def getsid(pid):
        if pid == 0:
            return PROBE_SID if leader else PROBE_SID + 100000
        if pid in sessions:
            return sessions[pid]
        raise ProcessLookupError(pid)
    mp = pytest.MonkeyPatch()
    mp.setattr(pg.os, "getsid", getsid)
    try:
        g = pg.ProcessGuard(roots or [tmp_path], scan=lambda: list(processes),
                            get=lambda pid: next(p for p in processes if p.pid == pid), env_markers=markers)
    except BaseException:
        mp.undo()
        raise
    g.started = 0
    g.kill_role = lambda role=None: []
    return g, mp


def test_a_foreign_session_process_is_foreign_new_and_the_cleanup_stays_certain(tmp_path):
    daemon = Process(81498, 1, created=11, argv=["/System/Library/PrivateFrameworks/HelpData.framework/helpd"])
    g, mp = make(tmp_path, [daemon], sessions={81498: FOREIGN_SID})
    try:
        g.cleanup()                                   # the leg continues: never a refusal
    finally:
        mp.undo()
    s = g.status()
    assert s["schema"] == 2 and s["uncertain"] is False and not daemon.dead
    (e,) = s["foreign_new"]
    assert e["pid"] == 81498 and e["sid"] == FOREIGN_SID and e["path_match"] is False and e["unreadable"] is False
    assert s["orphans_unattributed"] == [] and ci.cleanup_problems(s) == []


@pytest.mark.parametrize("deny", [("start_order",), ("cwd",), ("environ",)])
def test_a_denied_read_on_an_unclaimed_foreign_daemon_is_foreign_new_unreadable_never_uncertain(tmp_path, deny):
    daemon = Denied(70, 1, created=11, deny=deny, argv=["mdworker_shared"])
    g, mp = make(tmp_path, [daemon], sessions={70: FOREIGN_SID}, markers={"HOME": str(tmp_path / "home")},
                 roots=[tmp_path, tmp_path / "home"])
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert s["uncertain"] is False and not daemon.dead and ci.cleanup_problems(s) == []
    assert [e["pid"] for e in s["foreign_new"] if e["unreadable"] is True] == [70]


def test_a_path_only_match_without_corroboration_is_never_killed(tmp_path):
    p = Process(90, 1, created=11, cwd=str(tmp_path / "work"))
    g, mp = make(tmp_path, [p], sessions={90: FOREIGN_SID})
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert not p.dead and s["uncertain"] is False
    assert [(e["pid"], e["path_match"]) for e in s["foreign_new"]] == [(90, True)]


def test_a_path_match_corroborated_by_the_hermetic_environment_is_ours_killed_and_verified(tmp_path):
    home = tmp_path / "run" / "home"
    p = EnvProcess(91, 1, created=11, cwd=str(tmp_path / "work"), env={"HOME": str(home)})
    g, mp = make(tmp_path, [p], sessions={91: FOREIGN_SID}, markers={"HOME": str(home)}, roots=[tmp_path, home])
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert p.dead and s["uncertain"] is False and s["foreign_new"] == []
    assert [(e["pid"], e["claim"]) for e in s["orphans_unattributed"]] == [(91, "environment")]


def test_a_box_wide_home_is_never_a_marker(tmp_path):
    """A hand run's real HOME (not under a guard root) never claims a process by its environment."""
    g = pg.ProcessGuard([tmp_path / "work"], scan=lambda: [], get=lambda pid: next(iter(())),
                        env_markers={"HOME": os.path.expanduser("~")})
    assert g.env_markers == {}


def test_an_owned_survivor_of_the_probe_session_is_killed_verified_recorded_and_certain(tmp_path):
    child = Process(95, 1, created=11, argv=["node", "jest"])           # escaped the ancestry, still in the probe's session
    g, mp = make(tmp_path, [child], sessions={95: PROBE_SID})
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert child.dead and s["uncertain"] is False and s["survivors"] == []
    assert [(e["pid"], e["claim"]) for e in s["orphans_unattributed"]] == [(95, "session")]
    assert ci.cleanup_problems(s) == []                   # schema 2: a killed-and-verified escapee is no refusal


def test_an_owned_process_that_does_not_die_is_a_survivor_and_uncertain(tmp_path):
    child = Process(96, 1, created=11)
    child.kill = lambda: None
    g, mp = make(tmp_path, [child], sessions={96: PROBE_SID})
    try:
        with pytest.raises(pg.CleanupUncertain):
            g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert 96 in s["survivors"] and s["uncertain"] is True and ci.cleanup_problems(s)


def test_a_hand_run_probe_that_is_not_a_session_leader_owns_by_ancestry_only(tmp_path):
    member = Process(97, 1, created=11)
    g, mp = make(tmp_path, [member], sessions={97: PROBE_SID}, leader=False)     # getsid(0) != getpid(): not a leader
    try:
        assert g.session["leader"] is False and g.session_owner is None and g.session["source"] == "ancestry_only"
        g.cleanup()
    finally:
        mp.undo()
    assert not member.dead and [e["pid"] for e in g.status()["foreign_new"]] == [97]


def test_x17_there_is_no_explicit_session_parameter(tmp_path):
    """X17: the chain launches every probe with `start_new_session=True`; §3.1's leader test is the only session source."""
    import inspect
    from bench import arm_runner
    assert "session_id" not in inspect.signature(pg.ProcessGuard).parameters
    assert "session_id" not in inspect.signature(arm_runner._run_item).parameters
    with pytest.raises(TypeError):
        pg.ProcessGuard([tmp_path], scan=lambda: [], get=lambda pid: next(iter(())), session_id=1)


def test_a_denied_read_on_a_claimed_process_stays_uncertain(tmp_path):
    member = Denied(98, 1, created=11)                    # a session member whose start order stays unreadable
    g, mp = make(tmp_path, [member], sessions={98: PROBE_SID})
    try:
        with pytest.raises(pg.CleanupUncertain):
            g.cleanup()
    finally:
        mp.undo()
    assert g.status()["uncertain"] is True and g.status()["uncertain_records"]


def test_foreign_new_is_capped_at_64_with_a_count(tmp_path):
    procs = [Process(1000 + i, 1, created=11) for i in range(70)]
    g, mp = make(tmp_path, procs, sessions={p.pid: FOREIGN_SID for p in procs})
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert len(s["foreign_new"]) == pg.FOREIGN_NEW_CAP and s["foreign_new_count"] == 70


def test_an_unreadable_process_provably_older_than_the_guard_is_counted_not_listed(tmp_path):
    class OldDenied(Process):
        def start_order(self):
            return 1                                       # proven older (monotonic order < the guard's)

        def create_time(self):
            import psutil
            raise psutil.AccessDenied(self.pid)
    old = OldDenied(99, 1, created=11)
    g, mp = make(tmp_path, [old], sessions={99: FOREIGN_SID})
    g.started_order = 10
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert s["foreign_new"] == [] and s["unreadable_count"] == 1 and s["uncertain"] is False


# -- §3.5 the one validator: schema 1 by the old rule, schema 2 by the new
SCHEMA1 = dict(survivors=[], containers_remaining=[], uncertain=False, orphans_unattributed=[], unknown=[], completed=True)
SCHEMA2 = dict(SCHEMA1, schema=2, foreign_new=[], foreign_new_count=0, unreadable_count=0)


def test_schema_1_records_still_validate_by_the_old_rule():
    assert ci.cleanup_problems(SCHEMA1) == []
    assert ci.cleanup_problems(dict(SCHEMA1, orphans_unattributed=[{"pid": 2}]))          # the old rule refuses an orphan
    assert ci.cleanup_problems({k: v for k, v in SCHEMA1.items() if k != "completed"})


def test_schema_2_allows_escapees_and_foreign_new_but_not_survivors():
    assert ci.cleanup_problems(dict(SCHEMA2, orphans_unattributed=[{"pid": 2}], foreign_new=[{"pid": 3}],
                                    foreign_new_count=1)) == []
    for bad in (dict(SCHEMA2, survivors=[1]), dict(SCHEMA2, uncertain=True), dict(SCHEMA2, completed=False),
                dict(SCHEMA2, unknown=[{"pid": 1}]), dict(SCHEMA2, containers_remaining=["c"]), dict(SCHEMA2, schema=3),
                {k: v for k, v in SCHEMA2.items() if k != "foreign_new"}, dict(SCHEMA2, extra=1)):
        assert ci.cleanup_problems(bad), bad
    assert "orphans_unattributed" not in ci.CLEANUP_LISTS


def test_every_refusal_site_uses_the_one_validator():
    import inspect
    from bench import chain_core
    src = inspect.getsource(chain_core.Chain)
    for site in ("require_certain_cleanup", "check_restart_eligible", "p426_dnf_eligible", "record_incident"):
        body = inspect.getsource(getattr(chain_core.Chain, site))
        assert "cleanup_problems(" in body, site
    assert src.count("cleanup_problems(") >= 4


def test_the_guard_status_before_cleanup_is_schema_2_and_uncertain(tmp_path):
    g = pg.ProcessGuard([tmp_path], scan=lambda: [], get=lambda pid: next(iter(())))
    s = g.status()
    assert s["schema"] == 2 and s["uncertain"] is True and set(s) == set(ci.CLEANUP_KEYS_2)


def test_the_sweep_excluded_same_session_skip_is_gone():
    assert not hasattr(pg.ProcessGuard, "_sweep_excluded")


def test_a_cleanup_uncertainty_is_typed_for_the_abort_stamp():
    from bench import arm_runner
    assert issubclass(pg.CleanupUncertain, TransportAbort)
    assert arm_runner.harness_fault_cause(pg.CleanupUncertain("x")) == ("cleanup_uncertain", None)
