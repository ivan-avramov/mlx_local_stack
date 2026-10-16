"""G1 round 2 (Cursor review of 5f9fdbc4, P1-P5): later read failures are recorded, root and descendant obligations
are separate, identities are exact with tri-state resolution, the monotonic deadline governs the whole scan/reconcile
loop, and the production default is exercised (clock/sleep injected; one bounded real-time test)."""
import time

import pytest

from bench import proc_guard as pg
from bench.token_turn_gate import TransportAbort
from bench.tests.test_proc_guard import Process, guard as _guard
from bench.tests.test_c157_proc_guard import Unreadable, _denied, guard

pytestmark = pytest.mark.usefixtures("fake_guard_clock")


class DeniesOnRead(Process):
    """start_order reads succeed (None: wall-clock fallback) except the ones numbered in `deny` (1-based)."""

    def __init__(self, *args, deny=(), vanish=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.deny, self.vanish, self.reads = set(deny), set(vanish), 0

    def start_order(self):
        import psutil
        self.reads += 1
        if self.reads in self.deny:
            raise _denied(self.pid)
        if self.reads in self.vanish:
            raise psutil.NoSuchProcess(self.pid)
        return None


# ------------------------------------------------------------------------------------------------- P5
def test_p5_the_production_deadline_is_ten_seconds_and_untouched_by_the_suite(tmp_path):
    assert pg.ProcessGuard.RECONCILE_DEADLINE_S == 10
    g = _guard(tmp_path, [])
    assert g.reconcile_deadline_s == 10


def test_p5_a_real_time_present_unreadable_waits_for_the_deadline_and_not_much_longer(tmp_path, monkeypatch):
    monkeypatch.setattr(pg.ProcessGuard, "_monotonic", staticmethod(time.monotonic))
    monkeypatch.setattr(pg.ProcessGuard, "_sleep", staticmethod(time.sleep))
    g = guard(tmp_path, [Unreadable(30)])
    g.reconcile_deadline_s = 0.5
    t = time.monotonic()
    with pytest.raises(TransportAbort, match="start order unreadable"):
        g.cleanup()
    assert 0.5 <= time.monotonic() - t < 3


# ------------------------------------------------------------------------------------------------- P1
def test_p1_a_denied_second_order_read_in_tick_is_recorded(tmp_path):
    p = DeniesOnRead(60, created=10, deny={2})        # eligibility read ok, the identity/order read after it denied
    g = _guard(tmp_path, [p])
    g.tick()
    assert (60, 10) in g._unreadable_seen
    with pytest.raises(TransportAbort, match=r"60.*unreadable record unresolved"):
        g.cleanup()                                   # readable, young, untracked, ppid 1: never silently clears


def test_p1_a_process_that_vanishes_at_the_second_read_is_not_recorded(tmp_path):
    g = _guard(tmp_path, [DeniesOnRead(60, vanish={2})])
    g.tick()
    assert not g._unreadable_seen


def test_p1_a_denied_later_order_read_in_cleanup_is_recorded(tmp_path):
    p = DeniesOnRead(60, created=10, deny={2})        # cleanup: _protected is read 1, the ppid-1 age check read 2
    g = guard(tmp_path, [p])
    with pytest.raises(TransportAbort, match=r"60.*unreadable record unresolved"):
        g.cleanup()


# ------------------------------------------------------------------------------------------------- P2
def test_p2_a_protected_root_retiring_keeps_its_young_child_obligation(tmp_path):
    processes = []
    child = Process(41, 40, created=11)
    root = Unreadable(40, created=5)                  # pre-existing (guard started at 8): protected once readable
    processes += [child, root]
    g = _guard(tmp_path, processes)
    g.started = 8
    g.tick()
    root.armed = False
    g.tick()                                          # the root proves protected: ITS obligation is discharged ...
    assert (41, 11) in g._unreadable_seen[(40, 5)]["children"]       # ... the child's is not
    processes.remove(root)
    child.parent = 1                                  # the root exits; the young child reparents to launchd
    with pytest.raises(TransportAbort, match=r"41.*child of vanished unreadable process"):
        g.cleanup()
    assert not child.dead


def test_p2_a_child_spawned_after_the_last_tick_of_a_readable_root_is_recorded_at_cleanup(tmp_path):
    processes = []
    root = Unreadable(40, created=10)
    processes.append(root)
    g = _guard(tmp_path, processes)
    g.tick()
    root.armed = False                                # recovered readable (young, unattributed: not resolved)
    g.tick()
    child = Process(41, 40, created=11)
    processes.append(child)                           # spawned after the last tick
    scans = []

    def scan():
        scans.append(1)
        if len(scans) == 2 and root in processes:     # the root exits during reconciliation; the child reparents
            processes.remove(root)
            child.parent = 1
        return list(processes)
    g.scan = scan
    g.kill_role = lambda role=None: []
    with pytest.raises(TransportAbort, match=r'"pid": 41.*child of vanished unreadable process'):
        g.cleanup()


def test_p2_a_readable_unprotected_root_keeps_refreshing_its_descendants_in_tick(tmp_path):
    processes = []
    root = Unreadable(40, created=10)
    processes.append(root)
    g = _guard(tmp_path, processes)
    g.tick()
    root.armed = False
    processes.append(Process(41, 40, created=11))
    g.tick()
    assert (41, 11) in g._unreadable_seen[(40, 10)]["children"]


# ------------------------------------------------------------------------------------------------- P3
def _no_create_root():
    import psutil

    class NoCreateUnreadable(Unreadable):
        def create_time(self):
            raise psutil.AccessDenied(self.pid)
    return NoCreateUnreadable(40)


def test_p3_an_occupied_unknown_identity_root_stays_unresolved_until_its_pid_is_absent(tmp_path):
    processes = [_no_create_root()]
    g = _guard(tmp_path, processes)
    g.started = 8
    g.tick()
    assert (40, None) in g._unreadable_seen
    processes[0] = Process(40, 2, created=10)         # young, untracked, not an orphan: the scan ignores it
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*40.*unreadable record unresolved"):
        g.cleanup()                                   # ... but it may be a replacement: not resolved by readability
    processes.clear()                                 # absent now
    g.cleanup()
    assert g.status()["uncertain"] is False


def test_p3_an_unknown_identity_pid_held_by_a_pre_existing_process_is_the_original(tmp_path):
    """A pid occupied by a process older than the guard cannot have been reassigned since the record."""
    processes = [_no_create_root()]
    g = _guard(tmp_path, processes)
    g.started = 8
    g.tick()
    processes[0] = Process(40, 2, created=5)
    g.cleanup()
    assert g.status()["uncertain"] is False


def test_p3_an_occupied_unknown_identity_child_stays_unresolved_until_its_pid_is_absent(tmp_path):
    import psutil

    class NoCreate(Process):
        def create_time(self):
            raise psutil.AccessDenied(self.pid)
    processes = []
    child, root = NoCreate(41, 40), Unreadable(40, created=10)
    processes += [child, root]
    g = _guard(tmp_path, processes)
    g.started = 8
    g.tick()
    processes.remove(root)
    processes[0] = Process(41, 2, created=10)         # young occupant of the recorded child's pid
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*41"):
        g.cleanup()


def test_p3_resolve_revalidates_the_identity_on_every_decisive_read(tmp_path):
    original = Process(30, 1, created=10)
    replacement = Process(30, 1, created=5)           # protected at guard start 8
    served = []

    def get(pid):
        served.append(1)
        return original if len(served) == 1 else replacement
    g = pg.ProcessGuard([tmp_path], scan=lambda: [], get=get)
    g.started = 8
    assert g._resolve(30, 10)[0] == "gone"            # the pid changed hands between the reads: the ORIGINAL is gone


def test_p3_resolve_is_tri_state_and_inspection_failures_are_unresolved(tmp_path):
    young = Process(30, 1, created=10)
    g = _guard(tmp_path, [young])
    g.started = 8
    assert g._resolve(30, 10)[0] == "unresolved"       # young, untracked, not path-attributed
    assert g._resolve(31, 10)[0] == "gone"
    g.started = 20
    assert g._resolve(30, 10)[0] == "resolved"         # pre-existing/protected
    g.started = 8
    g.tracked[(30, 10)] = "model"
    assert g._resolve(30, 10)[0] == "resolved"
    g.tracked.clear()
    young.directory = str(tmp_path / "work")
    assert g._resolve(30, 10)[0] == "resolved"         # path-attributed: the scan owns it
    young.directory = "/elsewhere"
    denied = DeniesOnRead(30, created=10, deny={1})
    g2 = _guard(tmp_path, [denied])
    g2.started = 20
    assert g2._resolve(30, 10)[0] == "unresolved"      # even a would-be-protected process: the inspection failed

    class NoCwd(Process):
        def cwd(self):
            raise _denied(self.pid)
    g3 = _guard(tmp_path, [NoCwd(30, 1, created=10)])
    g3.started = 8
    assert g3._resolve(30, 10)[0] == "unresolved"      # attribution unreadable is not "not attributed"


# ------------------------------------------------------------------------------------------------- P4
def _vanishing_scan(count, clock=None, step=0.0):
    serial = []

    def scan():
        if clock is not None:
            clock.now += step
        pid = 100 + len(serial)
        serial.append(pid)
        return [Unreadable(pid)] if len(serial) <= count else []
    return scan, serial


def _gone_get(pid):
    raise StopIteration


def test_p4_many_rapid_state_changing_rounds_converge_before_the_deadline(tmp_path, fake_guard_clock):
    scan, serial = _vanishing_scan(8, fake_guard_clock, 0.1)       # 8 rounds of change, 0.8 s of a 10 s deadline
    g = pg.ProcessGuard([tmp_path], scan=scan, get=_gone_get)
    g.started = 0
    g.kill_role = lambda role=None: []
    g.cleanup()                                       # no "scan did not converge" merely from rapid rounds
    assert g.status()["uncertain"] is False and len(serial) > 5


def test_p4_endless_change_is_uncertain_only_once_the_deadline_has_expired(tmp_path, fake_guard_clock):
    scan, serial = _vanishing_scan(10**6, fake_guard_clock, 1.0)
    g = pg.ProcessGuard([tmp_path], scan=scan, get=_gone_get)
    g.started = 0
    g.kill_role = lambda role=None: []
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*did not converge"):
        g.cleanup()
    assert fake_guard_clock.now >= 10 and len(serial) <= 15


def test_p4_sleeps_are_bounded_by_the_remaining_time(tmp_path, fake_guard_clock):
    g = guard(tmp_path, [Unreadable(30)])
    g.reconcile_deadline_s = 0.25
    with pytest.raises(TransportAbort, match="start order unreadable"):
        g.cleanup()
    assert fake_guard_clock.now == pytest.approx(0.25) and max(fake_guard_clock.sleeps) <= 0.1 + 1e-9


def test_p4_a_state_change_first_seen_at_expiry_is_unresolved(tmp_path, fake_guard_clock):
    p = Unreadable(30, created=10)
    processes = [p]

    def get(pid):
        if fake_guard_clock.now >= 0.25 and p in processes:
            processes.remove(p)                       # it exits exactly as the deadline expires
        return next(q for q in processes if q.pid == pid)
    g = pg.ProcessGuard([tmp_path], scan=lambda: list(processes), get=get)
    g.started = 0
    g.kill_role = lambda role=None: []
    g.reconcile_deadline_s = 0.25
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*did not converge"):
        g.cleanup()                                   # no time left for the confirming scan: never certified clean
