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
    g.started_order = 100
    g.tick()
    processes[0] = Ordered(40, 2, created=5, order=1)     # monotonic proof: started before the guard
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


# ================================================================================ G1 round 3 (Cursor round 2, P6-P9)
class Ordered(Process):
    """A fake with a monotonic start order (what darwin's proc_pid_rusage provides)."""

    def __init__(self, *args, order=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order

    def start_order(self):
        return self.order


# ------------------------------------------------------------------------------------------------- P6
def test_p6_an_unknown_identity_root_that_became_readable_still_collects_new_children(tmp_path):
    processes = [_no_create_root()]
    g = _guard(tmp_path, processes)
    g.started = 8
    g.started_order = 100
    g.tick()
    assert (40, None) in g._unreadable_seen
    processes[0] = Ordered(40, 1, created=5, order=1)        # readable, proven older than the guard
    child = Process(41, 40, created=11)
    processes.append(child)                                   # spawned afterwards
    g.tick()
    assert (41, 11) in g._unreadable_seen[(40, None)]["children"]
    processes.remove(processes[0])
    child.parent = 1                                          # the root exits, the young child reparents
    with pytest.raises(TransportAbort, match=r'"pid": 41.*child of vanished unreadable process'):
        g.cleanup()


# ------------------------------------------------------------------------------------------------- P7
def test_p7_a_denied_ppid_after_eligibility_is_recorded_and_survives_its_parents_kill(tmp_path):
    from bench.tests.test_proc_guard import Exiting
    processes = []
    client = Process(10, argv=["opencode", "run"])
    child = Exiting(11, 10, fail=("ppid",), created=11)
    processes += [client, child]
    g = _guard(tmp_path, processes)
    g.register(client, "client")
    g.tick()                                                  # the child's parent cannot be read this tick
    assert (11, 11) in g._unreadable_seen
    child.fail = set()
    child.parent = 1                                          # parent killed between ticks: detached, untracked
    with pytest.raises(TransportAbort, match=r"11.*unreadable record unresolved"):
        g.cleanup()
    assert client.dead


def test_p7_a_denied_ppid_in_cleanup_is_recorded(tmp_path):
    from bench.tests.test_proc_guard import Exiting
    child = Exiting(11, 1, fail=("ppid",), created=11)
    g = guard(tmp_path, [child])
    with pytest.raises(TransportAbort, match=r"11.*unreadable record unresolved"):
        g.cleanup()


def test_p7_a_ppid_that_vanishes_is_not_recorded(tmp_path):
    import psutil

    class Gone(Process):
        def ppid(self):
            raise psutil.NoSuchProcess(self.pid)
    g = _guard(tmp_path, [Gone(11, 1, created=11)])
    g.tick()
    assert not g._unreadable_seen


# ------------------------------------------------------------------------------------------------- P8
def test_p8_a_reused_protected_pid_is_no_longer_protected(tmp_path):
    router = Process(50, 1, created=5)
    processes = [router]
    g = _guard(tmp_path, processes, protected_pids={50})
    g.started = 0
    assert g._protected(router) is True
    replacement = Process(50, 1, created=20)
    assert g._protected(replacement) is False


def test_p8_an_unknown_identity_is_never_resolved_by_an_excluded_pid_alone(tmp_path):
    processes = [_no_create_root()]
    g = _guard(tmp_path, processes, protected_pids={40})
    g.started = 8
    g.tick()
    processes[0] = Process(40, 2, created=10)                 # young occupant of an excluded pid
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*40.*unreadable record unresolved"):
        g.cleanup()


def test_p8_an_unknown_identity_needs_the_monotonic_age_proof_not_the_wall_clock(tmp_path):
    processes = [_no_create_root()]
    g = _guard(tmp_path, processes)
    g.started = 8
    g.tick()
    processes[0] = Process(40, 2, created=5)                  # wall-clock older only: no start order
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*40"):
        g.cleanup()


# ------------------------------------------------------------------------------------------------- P9
def test_p9_a_confirming_scan_that_finishes_after_the_deadline_is_not_a_clean_clear(tmp_path, fake_guard_clock):
    p = Unreadable(30, created=10)
    processes = [p]
    scans = []

    def scan():
        scans.append(1)
        if len(scans) > 1:
            fake_guard_clock.now += 5.0                       # the confirming scan starts in time, ends late
        return list(processes)

    def get(pid):
        if fake_guard_clock.now >= 0.05 and p in processes:
            processes.remove(p)
        return next(q for q in processes if q.pid == pid)
    g = pg.ProcessGuard([tmp_path], scan=scan, get=get)
    g.started = 0
    g.kill_role = lambda role=None: []
    g.reconcile_deadline_s = 1.0
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*did not converge"):
        g.cleanup()


def test_p9_every_retry_sleep_is_capped_by_the_remaining_time(tmp_path, fake_guard_clock):
    g = _guard(tmp_path, [])
    fake_guard_clock.now = 0.98
    g._nap(0.05, deadline=1.0)
    g._nap(0.05, deadline=0.5)                                # already expired: no sleep beyond it
    g._nap(0.05, deadline=None)
    assert fake_guard_clock.sleeps == pytest.approx([0.02, 0.0, 0.05])


# ================================================================================ G1 round 4 (Cursor round 3, P10-P13)
class Flaky(Process):
    """psutil-shaped fake: ANY read the guard makes can raise AccessDenied (`deny`) or NoSuchProcess (`gone`) from its
    n-th call on (`{"cwd": 1}` = every call; `{"create_time": 2}` = the first read succeeds, every later one is denied)."""

    METHODS = ("status", "uids", "ppid", "cwd", "cmdline", "create_time", "start_order", "memory_info")

    def __init__(self, *args, deny=None, gone=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.deny, self.gone, self.calls = dict(deny or {}), dict(gone or {}), {}

    def _gate(self, name):
        import psutil
        self.calls[name] = self.calls.get(name, 0) + 1
        if name in self.gone and self.calls[name] >= self.gone[name]:
            raise psutil.NoSuchProcess(self.pid)
        if name in self.deny and self.calls[name] >= self.deny[name]:
            raise psutil.AccessDenied(self.pid)

    def status(self):
        self._gate("status")
        return super().status()

    def uids(self):
        self._gate("uids")
        return super().uids()

    def ppid(self):
        self._gate("ppid")
        return super().ppid()

    def cwd(self):
        self._gate("cwd")
        return super().cwd()

    def cmdline(self):
        self._gate("cmdline")
        return super().cmdline()

    def create_time(self):
        self._gate("create_time")
        return super().create_time()

    def start_order(self):
        self._gate("start_order")
        return None

    def memory_info(self):
        self._gate("memory_info")
        return super().memory_info()


# ------------------------------------------------------------------------------------------------- P10
def test_p10_a_reconcile_that_crosses_the_deadline_cannot_certify_a_clean_confirmation(tmp_path, fake_guard_clock):
    p = Unreadable(30, created=10)
    processes = [p]

    def get(pid):
        if fake_guard_clock.now >= 0.05 and p in processes:
            processes.remove(p)
        return next(q for q in processes if q.pid == pid)
    g = pg.ProcessGuard([tmp_path], scan=lambda: list(processes), get=get)
    g.started = 0
    g.kill_role = lambda role=None: []
    g.reconcile_deadline_s = 1.0
    real, calls = g._resolve, []

    def slow_resolve(pid, created):
        calls.append(1)
        result = real(pid, created)
        if len(calls) >= 3:                               # the confirming reconcile itself runs past the deadline
            fake_guard_clock.now += 5.0
        return result
    g._resolve = slow_resolve
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*did not converge"):
        g.cleanup()


# ------------------------------------------------------------------------------------------------- P11
def _tracked_parent_case(tmp_path, error):
    client = Process(10, argv=["opencode", "run"])
    child = Process(11, 10, created=11)
    processes = [client, child]
    g = _guard(tmp_path, processes)
    g.register(client, "client")
    armed = [True]

    def get(pid):
        import psutil
        if pid == 10 and armed[0]:
            raise error(10)
        for q in processes:
            if q.pid == pid:
                return q
        raise psutil.NoSuchProcess(pid)
    g.get = get
    g.tick()
    armed[0] = False
    return g, client, child, processes


def test_p11_an_unknown_parent_validation_keeps_the_child_as_an_obligation(tmp_path):
    import psutil
    g, client, child, processes = _tracked_parent_case(tmp_path, psutil.AccessDenied)
    assert (11, 11) in g._unreadable_seen
    processes.remove(client)
    child.parent = 1                                      # the parent is gone, the child detached
    with pytest.raises(TransportAbort, match=r"11.*unreadable record unresolved"):
        g.cleanup()


def test_p11_a_parent_that_raced_away_keeps_the_child_as_an_obligation(tmp_path):
    import psutil
    g, client, child, processes = _tracked_parent_case(tmp_path, psutil.NoSuchProcess)
    assert (11, 11) in g._unreadable_seen


def test_p11_a_reused_parent_pid_is_not_our_parent_and_records_nothing(tmp_path):
    client = Process(10, argv=["opencode", "run"])
    child = Process(11, 10, created=11)
    processes = [client, child]
    g = _guard(tmp_path, processes)
    g.register(client, "client")
    g.get = lambda pid: Process(10, 1, created=99) if pid == 10 else next(p for p in processes if p.pid == pid)
    g.tick()
    assert not g._unreadable_seen and (11, 11) not in g.tracked


# ------------------------------------------------------------------------------------------------- P12 / P13
@pytest.mark.parametrize("deny", [
    {"cwd": 1}, {"cmdline": 1}, {"ppid": 1}, {"status": 1},
    {"create_time": 2}, {"start_order": 2},
], ids=lambda d: "-".join(f"{k}@{v}" for k, v in d.items()))
def test_p12_every_post_eligibility_denied_read_keeps_cleanup_uncertain(tmp_path, deny):
    """Same-uid, young, untracked, ppid 1, cwd outside the roots: only the denied read stands between it and a clear."""
    g = guard(tmp_path, [Flaky(70, 1, created=10, deny=deny)])
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*70"):
        g.cleanup()
    assert g.status()["uncertain"] is True


@pytest.mark.parametrize("name", ["cwd", "cmdline", "ppid", "status", "create_time", "start_order"])
def test_p12_a_process_that_vanishes_at_any_read_may_vanish(tmp_path, name):
    g = guard(tmp_path, [Flaky(70, 1, created=10, gone={name: 2 if name in ("create_time", "start_order") else 1})])
    g.cleanup()
    assert g.status()["uncertain"] is False


def test_p13_a_same_uid_process_with_a_denied_status_is_an_obligation_in_tick(tmp_path):
    g = _guard(tmp_path, [Flaky(70, 1, created=10, deny={"status": 1})])
    g.tick()
    assert (70, 10) in g._unreadable_seen


def test_p13_a_denied_uid_is_not_same_uid_and_may_be_skipped(tmp_path):
    g = guard(tmp_path, [Flaky(70, 1, created=10, deny={"uids": 1})])
    g.cleanup()
    assert g.status()["uncertain"] is False
