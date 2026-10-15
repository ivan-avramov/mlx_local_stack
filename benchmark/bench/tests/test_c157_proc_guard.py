"""C157 (M63 s2 abort, 2026-10-13): a same-uid process that vanishes between the guard's listing and its start-order
read is not "uncertain"; one that still exists stays uncertain (C151 R10). A vanished pid proves nothing about its
children (P297 U1), uncertainty must reconcile against the final process table (P297 review P2), and a process-monitor
failure is never hidden behind the uncertainty raise (P297 U2). The observed receipt is event-scripted below: the real
M63 abort was `cleanup uncertain ... [{"pid": 87652, "create_time": null, "reason": "start order unreadable"}]` for a
Spotlight mdworker that exited mid-cleanup."""
import pytest

from bench import proc_guard as pg
from bench.token_turn_gate import TransportAbort
from bench.tests.test_proc_guard import Process, guard as _guard


def guard(tmp_path, processes, **kwargs):
    """The cleanup SCAN under test: tick()/kill_role() would consume a scripted vanish before it runs."""
    g = _guard(tmp_path, processes, **kwargs)
    g.kill_role = lambda role=None: []
    return g


def _denied(pid):
    import psutil
    return psutil.AccessDenied(pid)


class Unreadable(Process):
    """Listed, then its start order is unreadable (macOS: a process mid-exit). `on_read(self)` scripts what happens
    at that instant (exit, pid reuse, reparenting)."""

    def __init__(self, *args, on_read=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_read = on_read

    def start_order(self):
        if self.on_read:
            self.on_read(self)
        raise _denied(self.pid)


def _exits(processes, *, children=()):
    def on_read(p):
        processes.remove(p)
        for child in children:
            child.parent = 1          # the orphan is reparented to launchd the instant its parent is gone
    return on_read


def test_a_process_that_vanished_after_listing_is_not_uncertain(tmp_path):
    processes = []
    processes.append(Unreadable(30, on_read=_exits(processes)))
    g = guard(tmp_path, processes)
    g.cleanup()                                    # must not raise
    status = g.status()
    assert status["uncertain"] is False and status["completed"] is True
    assert not [o for o in status["orphans_unattributed"] if o["pid"] == 30]


def test_a_still_existing_unreadable_process_stays_uncertain(tmp_path):
    processes = [Unreadable(30)]
    g = guard(tmp_path, processes)
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*start order unreadable"):
        g.cleanup()
    assert g.status()["uncertain"] is True


def test_exiting_after_the_first_recheck_still_clears_the_reason(tmp_path):
    """Uncertainty is reconciled against the FINAL process table, not frozen at the first recheck (P2)."""
    processes = []
    p = Unreadable(30)
    processes.append(p)
    reads = []

    def get(pid):
        if pid == 30:
            reads.append(pid)
            if len(reads) >= 2 and p in processes:
                processes.remove(p)
        return next(q for q in processes if q.pid == pid)
    g = pg.ProcessGuard([tmp_path], scan=lambda: list(processes), get=get)
    g.started = 0
    g.kill_role = lambda role=None: []
    g.cleanup()
    assert len(reads) >= 2 and g.status()["uncertain"] is False


def test_pid_reuse_clears_the_original_but_the_replacement_is_scanned(tmp_path):
    processes = []
    replacement = Process(30, 1, created=99, cwd=str(tmp_path / "work"))      # path-attributed to this run

    def reused(p):
        processes[processes.index(p)] = replacement
    processes.append(Unreadable(30, created=10, on_read=reused))
    g = guard(tmp_path, processes)
    with pytest.raises(TransportAbort, match="path-only attribution"):
        g.cleanup()


def test_a_live_reparented_child_of_a_vanished_unreadable_parent_refuses_clearance(tmp_path):
    processes = []
    child = Process(41, 40, created=11)
    processes += [child]
    processes.append(Unreadable(40, on_read=_exits(processes, children=[child])))
    g = guard(tmp_path, processes)
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*child of vanished unreadable process"):
        g.cleanup()
    assert g.status()["uncertain"] is True and not child.dead


def test_a_tracked_reparented_child_is_killed_and_does_not_block_clearance(tmp_path):
    processes = []
    child = Process(41, 40, created=11)
    processes.append(child)
    g = guard(tmp_path, processes)
    g.register(child, "client")
    processes.append(Unreadable(40, on_read=_exits(processes, children=[child])))
    g.cleanup()
    assert child.dead and g.status()["uncertain"] is False


def test_a_child_that_also_vanished_does_not_block_clearance(tmp_path):
    processes = []
    child = Process(41, 40, created=11)

    def both_exit(p):
        processes.remove(p)
        processes.remove(child)
    processes += [child, Unreadable(40, on_read=both_exit)]
    g = guard(tmp_path, processes)
    g.cleanup()
    assert g.status()["uncertain"] is False


def test_endless_vanishing_never_certifies_clean(tmp_path):
    """A pass that keeps losing processes has no clean snapshot: bounded retries, then uncertain."""
    serial = []

    def scan():
        pid = 100 + len(serial)
        serial.append(pid)
        listing = []
        listing.append(Unreadable(pid, on_read=lambda p: None))
        return listing

    def get(pid):
        raise StopIteration                          # every unreadable pid is gone at recheck
    g = pg.ProcessGuard([tmp_path], scan=scan, get=get)
    g.started = 0
    g.kill_role = lambda role=None: []
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*did not converge"):
        g.cleanup()
    assert len(serial) <= 12                         # bounded


def test_monitor_failure_is_raised_before_the_uncertainty_and_status_is_published(tmp_path):
    g = guard(tmp_path, [Unreadable(30)])
    g.failure = RuntimeError("psutil exploded")
    with pytest.raises(TransportAbort, match="process monitor died"):
        g.cleanup()
    status = g.status()
    assert status["completed"] is True and status["uncertain"] is True


def test_container_failure_still_precedes_the_monitor_failure(tmp_path):
    g = guard(tmp_path, [])
    g.register_container("mlxbench-x")
    g.remove_container = lambda name: (_ for _ in ()).throw(TransportAbort("container cleanup uncertain"))
    g.failure = RuntimeError("psutil exploded")
    with pytest.raises(TransportAbort, match="container cleanup uncertain"):
        g.cleanup()


def test_the_observed_m63_receipt_is_the_unreadable_orphan_shape(tmp_path):
    """Receipt regression (event-scripted above; this pins the record shape the runner and manifests consume)."""
    g = guard(tmp_path, [Unreadable(87652)])
    with pytest.raises(TransportAbort) as err:
        g.cleanup()
    assert '{"pid": 87652, "create_time": null, "reason": "start order unreadable"}' in str(err.value)
    assert {"pid": 87652, "create_time": None, "argv": [], "reason": "start order unreadable"} in \
        g.status()["orphans_unattributed"]
