"""P585 (C265): psutil's macOS `proc_cmdline` can raise SystemError ("returned a result with an exception set") for a process
mid-exec / mid-exit; the guard treats it exactly as AccessDenied (unreadable this tick), never as a dead monitor."""
import psutil
import pytest

from bench import proc_guard as pg
from bench.tests.test_proc_guard import Process, guard


class SystemErrorArgv(Process):
    def cmdline(self):
        raise SystemError("<built-in function proc_cmdline> returned a result with an exception set")


class DeniedArgv(Process):
    def cmdline(self):
        raise psutil.AccessDenied(self.pid)


def test_cmdline_helper_turns_systemerror_into_access_denied():
    with pytest.raises(psutil.AccessDenied):
        pg._cmdline(SystemErrorArgv(77))
    assert pg._cmdline(Process(78, argv=["x", "y"])) == ["x", "y"]


def outcome(tmp_path, cls):
    """tick() and cleanup() of a guard whose box holds the client and one unrelated process whose argv cannot be read."""
    root = Process(10)
    stranger = cls(30, ppid=1, cwd=str(tmp_path / "work"), created=11)
    g = guard(tmp_path, [root, stranger])
    g.started = 9
    g.register(root, "client")
    result = {}
    for step in ("tick", "cleanup"):
        try:
            getattr(g, step)()
            result[step] = "ok"
        except Exception as exc:  # noqa: BLE001 — the outcome is compared, not asserted per type
            result[step] = f"{type(exc).__name__}: {exc}"
    result["orphans"] = sorted(x["pid"] for x in g.orphans_unattributed)
    return result


def test_a_systemerror_argv_read_behaves_exactly_like_access_denied(tmp_path):
    denied = outcome(tmp_path / "a", DeniedArgv)
    broken = outcome(tmp_path / "b", SystemErrorArgv)
    assert "SystemError" not in str(broken)
    assert broken == {k: (v.replace(str(tmp_path / "a"), str(tmp_path / "b")) if isinstance(v, str) else v)
                      for k, v in denied.items()}


# ---- widened (C265 as approved; v3 after the verify round): every per-process read, psutil's own objects never altered -------
import os

from bench.tests.test_proc_guard import guard as fake_guard


def raising(*a, **k):
    raise SystemError("<built-in function proc_x> returned a result with an exception set")


def impl_class():
    return type(psutil.Process(os.getpid())._proc)


def test_a_lookup_whose_construction_raises_systemerror_is_access_denied(tmp_path, monkeypatch):
    g = pg.ProcessGuard([tmp_path])
    monkeypatch.setattr(impl_class(), "create_time", raising)       # psutil.Process() reads it while constructing
    with pytest.raises(psutil.AccessDenied):
        g.get(os.getpid())


@pytest.mark.real_process_scan                                       # the default scan itself (asserts on this process only)
def test_the_scan_skips_a_process_it_cannot_construct_and_keeps_the_rest(tmp_path, monkeypatch):
    g = pg.ProcessGuard([tmp_path])
    real = impl_class().create_time
    me = os.getpid()

    def create_time(self, *a, **k):
        if self.pid == me:
            raise SystemError("<built-in function proc_x> returned a result with an exception set")
        return real(self, *a, **k)
    monkeypatch.setattr(impl_class(), "create_time", create_time)
    pids = {p.pid for p in g.scan()}
    assert me not in pids and len(pids) > 1


@pytest.mark.real_process_scan
def test_psutils_own_objects_are_never_altered_by_the_guard(tmp_path):
    pg.ProcessGuard([tmp_path]).scan()
    p = next(q for q in psutil.process_iter() if q.pid == os.getpid())
    assert type(p) is psutil.Process
    with p.oneshot():
        assert p.ppid() == os.getppid()
    assert "psutil.Process" in repr(p)


class SystemErrorUids(Process):
    def uids(self):
        raise SystemError("<built-in function proc_uids> returned a result with an exception set")


class DeniedUids(Process):
    def uids(self):
        raise psutil.AccessDenied(self.pid)


class SystemErrorStatus(Process):
    def status(self):
        raise SystemError("<built-in function proc_status> returned a result with an exception set")


class DeniedStatus(Process):
    def status(self):
        raise psutil.AccessDenied(self.pid)


@pytest.mark.parametrize("broken, denied", [(SystemErrorUids, DeniedUids), (SystemErrorStatus, DeniedStatus)])
def test_a_systemerror_read_inside_the_guards_handlers_is_taken_as_access_denied(tmp_path, broken, denied):
    def listing(cls):
        g = fake_guard(tmp_path, [Process(10), cls(31, ppid=1, created=11)])
        found = sorted(p.pid for p in g._processes())
        return found, sorted(g._live_denied)
    assert listing(broken) == listing(denied)


def test_start_time_turns_systemerror_into_access_denied(tmp_path, monkeypatch):
    p = psutil.Process(os.getpid())
    monkeypatch.setattr(impl_class(), "create_time", raising)
    with pytest.raises(psutil.AccessDenied):
        pg.start_time(p)


# ---- review r3 (sol, C266) finding 1: a process that cannot be constructed keeps its previous tick's object ----------------
class FakePsutil:
    """`pids()` / `Process(pid)` with scripted construction failures; the module the default scan is handed."""
    NoSuchProcess, AccessDenied = psutil.NoSuchProcess, psutil.AccessDenied

    def __init__(self, pids):
        self.live, self.fail = list(pids), {}

    def pids(self):
        return list(self.live)

    def Process(self, pid):  # noqa: N802 — psutil's name
        exc = self.fail.get(pid)
        if exc is not None:
            raise exc(pid) if exc is not SystemError else SystemError("returned a result with an exception set")
        return SimpleNamespace(pid=pid, made=object())


from types import SimpleNamespace  # noqa: E402


def test_a_tracked_parent_that_cannot_be_constructed_stays_visible_through_its_previous_object():
    fake, last = FakePsutil([1, 2, 3]), {}
    first = {p.pid: p for p in pg._scan(fake, last)}
    for exc in (SystemError, psutil.AccessDenied):
        fake.fail = {2: exc}
        again = {p.pid: p for p in pg._scan(fake, last)}
        assert set(again) == {1, 2, 3} and again[2] is first[2]            # the previous object, never dropped


def test_a_never_seen_unconstructable_process_is_skipped_and_a_vanished_one_is_forgotten():
    fake, last = FakePsutil([1, 2]), {}
    pg._scan(fake, last)
    fake.live, fake.fail = [1, 2, 9], {9: SystemError, 2: psutil.NoSuchProcess}
    assert {p.pid for p in pg._scan(fake, last)} == {1}                    # 9 never seen; 2 vanished
    fake.fail = {2: SystemError}
    assert {p.pid for p in pg._scan(fake, last)} == {1, 9}                 # 2 was forgotten when it vanished; 9 now constructs
