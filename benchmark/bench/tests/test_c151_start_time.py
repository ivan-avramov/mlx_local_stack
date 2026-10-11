"""C151 (2026-10-11): psutil's `create_time()` is not a stable process identity in a long-lived process on macOS.

psutil 7.x `_psosx.adjust_proc_create_time` adds `INIT_BOOT_TIME - boot_time()` to every `create_time()` once the two
differ by >= 1 s, and `boot_time()` is whole seconds, so a sub-second wall-clock correction that carries
`kern.boottime` across a second boundary shifts every later read by 1 s. C147 V3 attempt 1 aborted on it (probe
"worker identity missing or drifted", driver "not the recorded router identity", same PIDs). Identity sites must use
the unadjusted kernel start time. `boot_shift` pins psutil's boot time to a controlled value equal to
`INIT_BOOT_TIME` (no adjustment active, whatever happened earlier in this pytest process), then moves it."""
import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bench import chain_ops, proc_guard, tg1_runner
from bench.token_turn_gate import TransportAbort

psutil = pytest.importorskip("psutil")
darwin = pytest.mark.skipif(sys.platform != "darwin", reason="psutil boot-time adjustment is the macOS path")

BENCH = Path(__file__).resolve().parents[1]
REPO = BENCH.parents[1]


@pytest.fixture
def boot_shift(monkeypatch):
    from psutil import _psosx
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(_psosx, "boot_time", lambda: clock["t"])
    monkeypatch.setattr(_psosx, "INIT_BOOT_TIME", clock["t"])

    def shift(seconds=1.0):
        clock["t"] += seconds
    return shift


@pytest.fixture
def child():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield p
    p.kill()
    p.wait()


@darwin
@pytest.mark.parametrize("seconds", [1.0, -1.0])
def test_the_adjustment_is_real_on_this_psutil(boot_shift, child, seconds):
    # Guards the premise: if psutil stops adjusting, this fails and C151's helper can be revisited.
    before = psutil.Process(child.pid).create_time()
    boot_shift(seconds)
    assert psutil.Process(child.pid).create_time() == pytest.approx(before + seconds)


@darwin
@pytest.mark.parametrize("seconds", [1.0, -1.0])
def test_start_time_ignores_a_boot_time_shift(boot_shift, child, seconds):
    before = proc_guard.start_time(psutil.Process(child.pid))
    boot_shift(seconds)
    assert proc_guard.start_time(psutil.Process(child.pid)) == before


@darwin
def test_start_time_equals_the_unshifted_create_time(boot_shift, child):
    # Values already recorded in manifests came from unshifted reads; the helper must reproduce them exactly.
    assert proc_guard.start_time(psutil.Process(child.pid)) == psutil.Process(child.pid).create_time()


def test_start_time_falls_back_for_objects_without_a_psutil_impl():
    class Fake:
        def create_time(self):
            return 123.5
    assert proc_guard.start_time(Fake()) == 123.5


@darwin
def test_start_time_fails_closed_when_a_real_process_lacks_the_raw_path(child):
    p = psutil.Process(child.pid)
    p._proc = None
    with pytest.raises(TransportAbort):
        proc_guard.start_time(p)


@darwin
@pytest.mark.parametrize("seconds", [1.0, -1.0])
def test_chain_ops_identities_ignore_a_boot_time_shift(boot_shift, child, seconds):
    ct, chain = chain_ops.default_create_time(child.pid), chain_ops.default_parents(child.pid)
    boot_shift(seconds)
    assert chain_ops.default_create_time(child.pid) == ct
    assert chain_ops.default_parents(child.pid) == chain


@darwin
def test_default_parents_matches_psutil_ancestry(boot_shift, child):
    ours = chain_ops.default_parents(child.pid)
    p = psutil.Process(child.pid)
    assert [e["pid"] for e in ours] == [q.pid for q in [p, *p.parents()]]


@darwin
def test_tg1_worker_identity_survives_a_boot_time_shift(boot_shift, child, monkeypatch, tmp_path):
    reg = tmp_path / "registry.yaml"
    reg.write_text("mlx_port: 8091\n")
    monkeypatch.setattr(tg1_runner.provenance.paths, "registry_path", lambda: reg)

    class Probe:
        @staticmethod
        def _worker_load_identity(model, router):
            return {"pid": child.pid, "model_path": "org/model"}

    before = tg1_runner.worker_identity(Probe, "m", {"pid": os.getpid()})
    boot_shift()
    after = tg1_runner.worker_identity(Probe, "m", {"pid": os.getpid()})
    proc_guard.require_identity(before, after)          # raised "worker identity missing or drifted" before C151


def test_require_identity_names_the_drifted_field():
    a = {"pid": 7, "create_time": 1.0, "model_path": "m", "registry_sha256": "x"}
    with pytest.raises(TransportAbort, match=r"create_time"):
        proc_guard.require_identity(a, dict(a, create_time=2.0))


@darwin
def test_process_guard_identity_survives_a_boot_time_shift(boot_shift, child, tmp_path):
    g = proc_guard.ProcessGuard(roots=[tmp_path], protected_pids=())
    created = proc_guard.start_time(psutil.Process(child.pid))
    boot_shift()
    assert g._same_identity(child.pid, created)
    # the dangerous historical outcome: a live owned process certified gone after the shift
    assert g._identity_state(child.pid, created) == "alive"
    assert g.verify_gone([{"pid": child.pid, "create_time": created}]) is False


# (file, enclosing qualname, receiver, method): each exemption is tied to its one site (round-2 R9).
ALLOWED = {
    ("benchmark/bench/proc_guard.py", "start_time", "proc", "create_time"),      # the fake fallback
    ("benchmark/bench/proc_guard.py", "start_time", "impl", "create_time"),      # the unadjusted raw read
    ("benchmark/bench/proc_guard.py", "ProcessGuard.__init__", "psutil.Process()", "parents"),  # own ancestors' pids
    # ChainOps effect hooks (defaults: default_create_time / default_parents), at their exact methods
    *{("benchmark/bench/chain_ops.py", f"ChainOps.{m}", "self", "create_time")
      for m in ("start_router", "worker_ident", "load", "_alive")},
    ("benchmark/bench/chain_ops.py", "ChainOps.start_router", "self", "parents"),
    ("benchmark/chains/c147/run_tg1_chain.py", "Chain.run_step", "self.ops", "create_time"),
}


def _allowed(rel, qual, recv, meth):
    for f, q, r, m in ALLOWED:
        if f == rel and r == recv and m == meth and (q == qual or q == "*"
                                                       or (q.endswith(".*") and qual.startswith(q[:-1]))):
            return True
    return False


def test_no_adjusted_start_time_reads_outside_the_helper():
    # Platform-independent static guard over every non-test module: a start time feeding an identity must come
    # from proc_guard.start_time; psutil's parents()/parent() read the adjusted value internally.
    hits = []
    for root in ("benchmark", "scripts"):
        for path in sorted((REPO / root).rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if "/tests/" in rel or "/.venv" in rel or "/src/" in rel:
                continue
            tree = ast.parse(path.read_text(errors="replace"), filename=rel)   # a parse failure fails the test

            def visit(node, qual):
                for child in ast.iter_child_nodes(node):
                    q = qual
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        q = f"{qual}.{child.name}" if qual else child.name
                    if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                            and child.func.attr in ("create_time", "parents", "parent")):
                        recv = ast.unparse(child.func.value)
                        if not _allowed(rel, qual, recv, child.func.attr):
                            hits.append(f"{rel}:{child.lineno} {qual or '<module>'}: {recv}.{child.func.attr}()")
                    visit(child, q)
            visit(tree, "")
    assert not hits, "adjusted start-time reads (use proc_guard.start_time / explicit ppid walks): " + "; ".join(hits)


# R8 (round-2 review): ordering decisions (older than the guard, parent younger than child, orphan sweep) must not
# depend on wall-clock start times, which a backward clock step reorders. Identity stays start_time(); order is the
# monotonic start (macOS proc_pid_rusage ri_proc_start_abstime vs mach_absolute_time).
from bench.tests.test_proc_guard import Process as FakeProcess, guard as fake_guard  # noqa: E402


class OrderedFake(FakeProcess):
    def __init__(self, pid, order, **kw):
        super().__init__(pid, **kw)
        self.order = order

    def start_order(self):
        return self.order


def test_backward_step_child_of_tracked_client_is_owned_and_killed(tmp_path):
    # Reviewer's counterexample: tracked client at wall 110; after a backward step its child starts at wall 99 < started.
    client = OrderedFake(99501, order=1100, created=110)
    child = OrderedFake(99502, order=1200, ppid=client.pid, created=99)
    g = fake_guard(tmp_path, [client, child])
    g.started, g.started_order = 100, 1000
    g.register(client, "client")
    g.tick()
    assert g.tracked.get((child.pid, 99)) == "model"
    g.cleanup()
    assert child.dead, "post-step descendant of the tracked client survived a clean cleanup"


def test_pre_existing_process_stays_protected_after_a_forward_step(tmp_path):
    old = OrderedFake(99601, order=900, created=105)     # started before the guard; wall time reads later after a step
    g = fake_guard(tmp_path, [old])
    g.started, g.started_order = 100, 1000
    with pytest.raises(TransportAbort):
        g.register(old, "client")


@darwin
def test_real_grandchild_after_a_backward_step_is_tracked_and_cleaned(tmp_path):
    import time as _t
    g = proc_guard.ProcessGuard(roots=[tmp_path], protected_pids=())
    client = subprocess.Popen([sys.executable, "-c",
                               "import subprocess, sys, time; subprocess.Popen(['sleep', '60']); time.sleep(60)"])
    try:
        _t.sleep(0.5)
        g.started += 1000.0              # every later wall-clock start now reads "before the guard" (backward step)
        g.register(psutil.Process(client.pid), "client")
        g.tick()
        kids = psutil.Process(client.pid).children()
        assert kids and all((k.pid, proc_guard.start_time(k)) in g.tracked for k in kids)
        g.cleanup()
        assert all(not k.is_running() or k.status() == "zombie" for k in kids)
    finally:
        client.kill(); client.wait()


# Round 3: R10 (unreadable order must never yield a clean clearance), R11 (router ancestry on monotonic order).
class DeniedOrderFake(FakeProcess):
    def start_order(self):
        raise psutil.AccessDenied(self.pid)


def test_unreadable_order_for_an_eligible_process_makes_cleanup_uncertain(tmp_path):
    client = OrderedFake(99701, order=1100, created=110)
    stranger = DeniedOrderFake(99702, ppid=1, created=111)
    g = fake_guard(tmp_path, [client, stranger])
    g.started, g.started_order = 100, 1000
    g.register(client, "client")
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*99702"):
        g.cleanup()
    st = g.status()
    assert st["uncertain"] is True and st["completed"] is True and not stranger.dead


@darwin
@pytest.mark.parametrize("errno_, exc", [(3, "NoSuchProcess"), (1, "AccessDenied"), (13, "AccessDenied"),
                                         (22, "TransportAbort")])
def test_start_order_errno_mapping(monkeypatch, child, errno_, exc):
    class Lib:
        @staticmethod
        def proc_pid_rusage(pid, flavor, ref):
            return -1

    class C:
        @staticmethod
        def byref(x):
            return x

        @staticmethod
        def get_errno():
            return errno_
    d = proc_guard._darwin_lib()
    monkeypatch.setitem(proc_guard._DARWIN, "libproc", Lib)
    monkeypatch.setitem(proc_guard._DARWIN, "ctypes", C)
    expected = TransportAbort if exc == "TransportAbort" else getattr(psutil, exc)
    with pytest.raises(expected):
        proc_guard.start_order(psutil.Process(child.pid))
    assert d is proc_guard._DARWIN


@darwin
def test_default_parents_follows_a_parent_that_looks_younger_after_a_backward_step(monkeypatch, child):
    real = proc_guard.start_time
    monkeypatch.setattr(proc_guard, "start_time",
                        lambda p: real(p) - 1000.0 if p.pid == child.pid else real(p))   # child wall < parent wall
    chain = chain_ops.default_parents(child.pid)
    assert [e["pid"] for e in chain][:2] == [child.pid, os.getpid()]


@darwin
def test_default_parents_stops_at_a_reused_parent_pid(monkeypatch, child):
    real = proc_guard.start_order
    monkeypatch.setattr(proc_guard, "start_order",
                        lambda p: real(p) + 10**15 if p.pid == os.getpid() else real(p))  # parent born after child
    assert [e["pid"] for e in chain_ops.default_parents(child.pid)] == [child.pid]


# Round 4: R12 — a persistent unexpected order failure must not stop cleanup half way.
class BrokenOrderFake(FakeProcess):
    def start_order(self):
        raise TransportAbort("proc_pid_rusage(99802) failed: errno 22")


def test_persistent_order_failure_still_completes_cleanup_and_publishes_uncertain(tmp_path):
    client = OrderedFake(99801, order=1100, created=110)
    broken = BrokenOrderFake(99802, ppid=1, created=111)
    g = fake_guard(tmp_path, [client, broken])
    g.started, g.started_order = 100, 1000
    g.register(client, "client")
    removed = []
    g.containers.add("mlxbench-x-1")
    g.remove_container = lambda name: (removed.append(name), g.containers.discard(name))
    with pytest.raises(TransportAbort, match=r"order failure: proc_pid_rusage\(99802\) failed: errno 22"):
        g.cleanup()
    st = g.status()
    assert client.dead, "owned process not killed"
    assert removed == ["mlxbench-x-1"], "containers not handled"
    assert st["completed"] is True and st["uncertain"] is True


# Round 5: R15 (kill_role must not swallow a per-target failure), R16 (an identity read failure in cleanup).
class FlakyOrderFake(OrderedFake):
    broken = False

    def start_order(self):
        if self.broken:
            raise TransportAbort("proc_pid_rusage(%d) failed: errno 22" % self.pid)
        return self.order


def test_kill_role_reraises_a_per_target_failure_after_killing_the_rest(tmp_path):
    a = FlakyOrderFake(99901, order=1100, created=110)
    b = OrderedFake(99902, order=1101, created=111)
    g = fake_guard(tmp_path, [a, b])
    g.started, g.started_order = 100, 1000
    g.register(a, "client")
    g.register(b, "client")
    g.tick()
    a.broken = True
    g.tick = lambda: None                       # tick itself succeeds; only the per-target read fails
    with pytest.raises(TransportAbort):
        g.kill_role("client")
    assert b.dead and not a.dead


class FlakyIdentityFake(OrderedFake):
    broken = False

    def create_time(self):
        if self.broken:
            raise TransportAbort("psutil lost the unadjusted start-time path (C151); refusing identity")
        return self.created


def test_identity_read_failure_in_cleanup_publishes_uncertain(tmp_path):
    client = FlakyIdentityFake(99951, order=1100, created=110)
    g = fake_guard(tmp_path, [client])
    g.started, g.started_order = 100, 1000
    g.register(client, "client")
    client.broken = True
    with pytest.raises(TransportAbort, match=r"cleanup uncertain.*identity unreadable"):
        g.cleanup()
    st = g.status()
    assert st["completed"] is True and st["uncertain"] is True


# Round 6: R18 — a failing grader kill must not skip guard.cleanup() (kill_role now re-raises, R15).
def test_failing_grader_kill_still_runs_cleanup(tmp_path, monkeypatch):
    calls = []

    class Guard:
        client_resource = True

        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def spawn(self, *args, **kwargs):
            class Child:
                returncode = -9

                def poll(self):
                    return -9

                def wait(self, **kwargs):
                    return -9
            return Child()

        def kill_role(self, role):
            calls.append("kill-" + role)
            raise TransportAbort("proc_pid_rusage(1) failed: errno 22")

        def cleanup(self):
            calls.append("cleanup")

        def run_grader(self, *args, **kwargs):
            pytest.fail("export on error")
    monkeypatch.setattr(proc_guard, "ProcessGuard", Guard)
    monkeypatch.setattr(proc_guard, "wait_cancel", lambda *a, **k: calls.append("cancel"))
    with pytest.raises(TransportAbort):
        tg1_runner.run_item(None, model="fixture", work=tmp_path, prompt="fixture",
                            env={"TMPDIR": str(tmp_path / "itemtmp")}, binary="fixture",
                            evidence=tmp_path / "evidence/one", entry=dict(baseline_failing=1, leaves=[["a"]],
                                                                         lang="python"),
                            limit=262144, private=tmp_path, router={}, base="fixture")
    assert "kill-grader" in calls and "cleanup" in calls, calls


def test_uncertain_message_gives_every_entry_a_reason(tmp_path):
    client = FlakyIdentityFake(99961, order=1100, created=110)
    g = fake_guard(tmp_path, [client])
    g.started, g.started_order = 100, 1000
    g.register(client, "client")
    client.broken = True
    with pytest.raises(TransportAbort) as info:
        g.cleanup()
    import json as _json
    entries = _json.loads(str(info.value).split("remain ", 1)[1].split("; order failure", 1)[0])
    assert entries and all(e.get("reason") for e in entries), entries
    assert all(set(u) == {"pid", "create_time"} for u in g.status()["unknown"])   # published schema unchanged
