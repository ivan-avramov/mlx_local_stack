"""B2 slice s7 (spec docs/specs/p426-b2-tg1-wave2.md v3.2, section 9 and the section 3 Entry / Item `ready` rows, 16.4): the exclusion
locks (arbiter, `SEQUENCER.lock`, `LEG.lock`, `gate/RUNNING`) in `bench.p426_locks`, their use by `bench.local_gate` and the P426
chain, the idle gap against `LAST_LEG_END`, every Entry check refusing before the router, and the ready barrier's checks.
Hermetic: temp lock files, the local gate with git / clone faked, the frozen P426 world (FakeOps + the item-barrier fake probe) for
the chain; no router, worker, model, network or GPU. Any registry a test reads is the sha256-pinned OFF copy (P518 / C246)."""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import chain_core as core
from bench import chain_hooks as ch
from bench import chain_ops as co
from bench import local_gate as lg
from bench import p426_hooks as ph
from bench import p426_locks as pl
from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S
from bench.tests.test_b2_s1_cli import X64, pinned_off_registry
from bench.tests.test_c147_chain_runner import env, run                                   # noqa: F401  (fixture: env)


# ------------------------------------------------------------------------------------------------ helpers
def flocked(path):
    """True when another open file description holds an exclusive flock on `path` (BSD flock conflicts inside one process)."""
    path = Path(path)
    if not path.exists():
        return False
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


class Hold:
    """Hold `flock(LOCK_EX | LOCK_NB)` on `path` from this test's own open file description."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        os.close(self.fd)


def rel(wd, name):
    return Path(wd) / name


GATE, SEQ, LEG, ARB = "gate/RUNNING", "p426/SEQUENCER.lock", "p426/LEG.lock", "locks/ARBITER.lock"


# ================================================================================================ the lock module
def test_lock_files_live_under_the_configured_stack_workdir(tmp_path):
    assert (pl.ARBITER, pl.RUNNING, pl.SEQUENCER, pl.LEG) == (ARB, GATE, SEQ, LEG)
    with pl.acquire("chain", tmp_path):
        assert (tmp_path / LEG).is_file() and (tmp_path / ARB).is_file()


@pytest.mark.parametrize("actor,own,opposing", [
    ("gate", GATE, [SEQ, LEG]), ("sequencer", SEQ, [GATE]), ("chain", LEG, [GATE])])
def test_each_direction_refuses_while_an_opposing_lock_is_held_and_takes_nothing(tmp_path, actor, own, opposing):
    for held in opposing:
        with Hold(tmp_path / held):
            with pytest.raises(pl.LockRefused, match=Path(held).name):
                pl.acquire(actor, tmp_path)
            assert not flocked(tmp_path / own)                       # nothing of its own was taken
            assert not flocked(tmp_path / ARB)                       # the arbiter is released on a refusal
    with pl.acquire(actor, tmp_path) as got:                         # control: with nothing held it runs
        assert flocked(tmp_path / own) and got.actor == actor
    assert not flocked(tmp_path / own) and not flocked(tmp_path / ARB)


def test_the_sequencer_and_the_chain_do_not_oppose_each_other(tmp_path):
    """§9: the sequencer never takes `LEG.lock`; each chain it launches does - so a chain runs under a held `SEQUENCER.lock`."""
    with pl.acquire("sequencer", tmp_path):
        with pl.acquire("chain", tmp_path):
            assert flocked(tmp_path / SEQ) and flocked(tmp_path / LEG)


@pytest.mark.parametrize("actor", ["gate", "sequencer", "chain"])
def test_an_actor_started_twice_refuses_the_second_start(tmp_path, actor):
    with pl.acquire(actor, tmp_path):
        with pytest.raises(pl.LockRefused):
            pl.acquire(actor, tmp_path)
        assert not flocked(tmp_path / ARB)


def test_an_unknown_actor_is_refused(tmp_path):
    with pytest.raises(ValueError):
        pl.acquire("operator", tmp_path)


def test_acquisition_waits_for_the_arbiter_then_proceeds(tmp_path):
    box = {}
    with Hold(tmp_path / ARB):
        th = threading.Thread(target=lambda: box.update(got=pl.acquire("gate", tmp_path)), daemon=True)
        th.start()
        time.sleep(0.4)
        assert "got" not in box                                       # blocked on the arbiter, not past it
    th.join(10)
    assert box["got"].actor == "gate"
    box["got"].release()


def test_the_arbiter_wait_is_bounded(tmp_path):
    with Hold(tmp_path / ARB):
        t0 = time.monotonic()
        with pytest.raises(pl.LockRefused, match="arbiter"):
            pl.acquire("gate", tmp_path, arbiter_timeout_s=0.3)
        assert 0.25 <= time.monotonic() - t0 < 5
        assert not flocked(tmp_path / GATE)
    assert pl.ARBITER_TIMEOUT_S == 30.0


def test_locks_are_close_on_exec_and_a_spawned_child_holds_none(tmp_path):
    with pl.acquire("chain", tmp_path) as got:
        assert fcntl.fcntl(got.fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
        assert not os.get_inheritable(got.fd)
        child = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(30)"])
    try:
        # the holder released while its child is still alive: had the child inherited the open file description the lock would stay
        assert not flocked(tmp_path / LEG)
    finally:
        child.kill()
        child.wait()


def test_a_child_sees_no_descriptor_on_the_lock_file(tmp_path):
    code = ("import os, sys\nt, hits = os.stat(sys.argv[1]), []\nfor fd in range(3, 256):\n    try:\n        s = os.fstat(fd)\n"
            "    except OSError:\n        continue\n    if (s.st_dev, s.st_ino) == (t.st_dev, t.st_ino):\n        hits.append(fd)\nprint(hits)\n")
    with pl.acquire("chain", tmp_path):
        out = subprocess.run([sys.executable, "-I", "-c", code, str(tmp_path / LEG)], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_release_is_idempotent_and_frees_the_lock(tmp_path):
    got = pl.acquire("gate", tmp_path)
    got.release()
    got.release()
    assert not flocked(tmp_path / GATE)
    with pl.acquire("gate", tmp_path):
        pass


def test_two_simultaneous_starters_end_with_exactly_one_running_threads(tmp_path):
    for round_ in range(40):
        wd = tmp_path / f"r{round_}"
        bar, results = threading.Barrier(2), {}

        def start(actor):
            bar.wait()
            try:
                results[actor] = pl.acquire(actor, wd)
            except pl.LockRefused as exc:
                results[actor] = exc
        ths = [threading.Thread(target=start, args=(a,), daemon=True) for a in ("gate", "chain")]
        for t in ths:
            t.start()
        for t in ths:
            t.join(40)
        ran = [a for a, r in results.items() if isinstance(r, pl.Held)]
        assert len(ran) == 1 and len(results) == 2, (round_, results)
        for r in results.values():
            if isinstance(r, pl.Held):
                r.release()


def test_two_simultaneous_starters_end_with_exactly_one_running_processes(tmp_path):
    code = ("import os, sys, time\nsys.path.insert(0, sys.argv[1])\nfrom bench import p426_locks as pl\n"
            "while not os.path.exists(sys.argv[3]):\n    time.sleep(0.001)\n"
            "try:\n    held = pl.acquire(sys.argv[4], sys.argv[2])\nexcept pl.LockRefused:\n    print('refused', flush=True)\n"
            "else:\n    print('ran', flush=True)\n    time.sleep(5)\n")
    pkg_root = str(Path(pl.__file__).resolve().parents[1])
    go = tmp_path / "GO"
    procs = [subprocess.Popen([sys.executable, "-I", "-c", code, pkg_root, str(tmp_path), str(go), actor], stdout=subprocess.PIPE,
                              text=True) for actor in ("gate", "chain")]
    time.sleep(1.5)                                                   # both interpreters are up, spinning on the start file
    go.write_text("go")
    outs = [p.communicate(timeout=60)[0].strip() for p in procs]
    assert sorted(outs) == ["ran", "refused"], outs


# ------------------------------------------------------------------------------------------------ the idle gap
@pytest.mark.parametrize("gap,ok", [(None, True), (599.9, False), (600.0, True), (601.0, True), (0.0, False), (-5.0, False)])
def test_the_idle_gap_is_600_seconds_since_last_leg_end(gap, ok):
    now = 1_800_000_000.0
    last = None if gap is None else now - gap
    assert pl.IDLE_GAP_S == 600.0
    problem = pl.idle_gap_problem(last, now)
    assert (problem is None) is ok
    if not ok:
        assert "LAST_LEG_END" in problem and "600" in problem


def test_chain_ops_reads_last_leg_end_from_the_stack_workdir(tmp_path):
    ops = co.ChainOps(tmp_path / "repo", tmp_path, tmp_path / "x.yaml", lambda m: None)
    assert ops.last_leg_end() is None                                 # no LAST_LEG_END yet
    (tmp_path / "p426").mkdir()
    (tmp_path / "p426" / "LAST_LEG_END").write_text("1800000000.5\n")
    assert ops.last_leg_end() == 1800000000.5
    for bad in ("", "soon", "nan", "-1"):
        (tmp_path / "p426" / "LAST_LEG_END").write_text(bad)
        with pytest.raises(co.ChainAbort, match="LAST_LEG_END"):
            ops.last_leg_end()


# ================================================================================================ bench.local_gate
def gate_world(monkeypatch, wd):
    """`local_gate.main(["run", "--repo", "stack"])` with git, the busy census and the clone faked; the fake clone records the
    state of `gate/RUNNING` and raises `Reached`."""
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    seen = dict(reached=False, running_locked=None)

    class Reached(Exception):
        pass

    def git(cwd, *a, check=True):
        if a[:3] == ("remote", "get-url", "origin"):
            return "https://github.com/" + lg.CANONICAL["stack"] + ".git"
        return "a" * 40 if a and a[0] == "rev-parse" else ""

    def clone(live, sha, dest):
        seen.update(reached=True, running_locked=flocked(Path(wd) / GATE))
        raise Reached()
    monkeypatch.setattr(lg, "_git", git)
    monkeypatch.setattr(lg, "clone_scratch", clone)
    monkeypatch.setitem(lg.run.__kwdefaults__, "busy", lambda: [])
    seen["Reached"] = Reached
    return seen


def gate_main(seen):
    try:
        return lg.main(["run", "--repo", "stack"])
    except seen["Reached"] as exc:
        return exc


@pytest.mark.parametrize("held", [SEQ, LEG])
def test_the_gate_refuses_while_an_opposing_p426_lock_is_held(tmp_path, monkeypatch, capsys, held):
    seen = gate_world(monkeypatch, tmp_path)
    with Hold(tmp_path / held):
        assert gate_main(seen) == 1
    assert seen["reached"] is False and not flocked(tmp_path / GATE) and not flocked(tmp_path / ARB)
    err = capsys.readouterr().err
    assert "REFUSED" in err and Path(held).name in err


def test_the_gate_holds_gate_running_while_it_works_and_frees_it_after(tmp_path, monkeypatch):
    seen = gate_world(monkeypatch, tmp_path)
    assert isinstance(gate_main(seen), seen["Reached"]) and seen["running_locked"] is True
    assert not flocked(tmp_path / GATE) and not flocked(tmp_path / ARB)      # released when `run` ended (here: raised)


def test_a_second_gate_refuses_while_one_runs(tmp_path, monkeypatch):
    seen = gate_world(monkeypatch, tmp_path)
    with Hold(tmp_path / GATE):
        assert gate_main(seen) == 1
    assert seen["reached"] is False and not flocked(tmp_path / ARB)


def test_the_gate_waits_for_the_arbiter(tmp_path, monkeypatch):
    seen = gate_world(monkeypatch, tmp_path)
    box = {}
    with Hold(tmp_path / ARB):
        th = threading.Thread(target=lambda: box.update(got=gate_main(seen)), daemon=True)
        th.start()
        time.sleep(0.5)
        assert seen["reached"] is False
    th.join(40)
    assert isinstance(box["got"], seen["Reached"]) and seen["reached"] is True


def test_the_pre_push_check_takes_no_lock(tmp_path, monkeypatch):
    """`check` runs inside git's push: it is not a test window and never excluded (it must not block on a running chain)."""
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setattr(lg, "_git", lambda cwd, *a, check=True: "https://github.com/" + lg.CANONICAL["stack"] + ".git")
    monkeypatch.setattr(lg, "check_lines", lambda *a, **k: [])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda: ""))
    with Hold(tmp_path / LEG):
        assert lg.main(["check", "--repo-dir", str(tmp_path), "origin"]) == 0


# ================================================================================================ the chain: locks and entry checks
def leg(tmp_path, monkeypatch, *, arm="off", mode=("pilot",), before=None, probe_env=None, out_name=None, timeout=240):
    env = A.world(tmp_path, monkeypatch, arm=arm, out_name=out_name)
    env["ops"].extra_env.update(probe_env or {})
    if before:
        before(env)
    argv, rfd = S.p426_argv(env, mode)
    try:
        rc = S.run_p426(env, argv, rfd=rfd, timeout=timeout)
    finally:
        env["ops"].cancel()
    return rc, env


def refusals(env):
    return [ln for ln in env["lines"] if "REFUSED: " in ln and "unrecognized arguments" not in ln]


def started(env):
    return bool(env["ops"].names("start_router")) or bool(S.invocations(env))


def barrier(env):
    return S.barrier_files(env["out"])


def has(env, suffix):
    return any(f.endswith(suffix) for f in barrier(env))


def said(env, text):
    return any(text in ln for ln in env["lines"])


def test_a_clean_leg_with_no_previous_leg_runs_and_frees_its_locks(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch)
    assert rc == 0, "\n".join(env["lines"][-12:])
    assert not flocked(tmp_path / LEG) and not flocked(tmp_path / ARB) and not refusals(env)


def test_the_chain_holds_its_leg_lock_before_and_while_the_router_starts(tmp_path, monkeypatch):
    seen = []

    def spy(env):
        original = env["ops"].start_router

        def start():
            seen.append(flocked(tmp_path / LEG))
            return original()
        env["ops"].start_router = start
    rc, env = leg(tmp_path, monkeypatch, before=spy)
    assert rc == 0 and seen == [True]


def test_the_chain_refuses_while_the_gate_runs_and_leaves_no_trace(tmp_path, monkeypatch):
    holds = []

    def hold(env):
        holds.append(Hold(tmp_path / GATE))
    try:
        rc, env = leg(tmp_path, monkeypatch, before=hold)
    finally:
        for h in holds:
            h.__exit__()
    assert rc == 2 and refusals(env) and any("RUNNING" in ln for ln in refusals(env))
    assert not started(env) and not Path(env["out"]).exists() and not flocked(tmp_path / ARB)


def test_a_second_chain_refuses_while_a_leg_runs(tmp_path, monkeypatch):
    holds = []

    def hold(env):
        holds.append(Hold(tmp_path / LEG))
    try:
        rc, env = leg(tmp_path, monkeypatch, before=hold)
    finally:
        for h in holds:
            h.__exit__()
    assert rc == 2 and refusals(env) and not started(env)


def test_a_chain_does_not_refuse_under_a_held_sequencer_lock(tmp_path, monkeypatch):
    holds = []

    def hold(env):
        holds.append(Hold(tmp_path / SEQ))
    try:
        rc, env = leg(tmp_path, monkeypatch, before=hold)
    finally:
        for h in holds:
            h.__exit__()
    assert rc == 0, "\n".join(env["lines"][-8:])


def test_the_lock_is_released_when_the_leg_fails(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_SKEW_ITEMS": S.p426_order([f"p{i}" for i in range(1, 7)], 1001)[1]})
    assert rc == 2 and not flocked(tmp_path / LEG) and not flocked(tmp_path / ARB)


def test_a_spawned_probe_holds_no_lock_descriptor(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, probe_env={"B2_LOCK_PROBE": str(tmp_path / LEG)})
    assert rc == 0, "\n".join(env["lines"][-8:])
    assert json.loads((env["ops"].state / "lockcheck.json").read_text())["inherited_fds"] == []


def test_of_a_simultaneous_gate_and_chain_exactly_one_runs(tmp_path, monkeypatch):
    env = A.world(tmp_path, monkeypatch)
    seen = gate_world(monkeypatch, tmp_path)
    done = threading.Event()

    def clone(live, sha, dest):                      # the gate holds its lock while it works, until the chain resolved
        seen.update(reached=True, running_locked=flocked(tmp_path / GATE))
        done.wait(60)
        raise seen["Reached"]()
    monkeypatch.setattr(lg, "clone_scratch", clone)
    argv, rfd = S.p426_argv(env, ("pilot",))

    def chain():
        try:
            return S.run_p426(env, argv, rfd=rfd)
        finally:
            done.set()
    try:
        gate_res, chain_rc = S.simultaneous(lambda: gate_main(seen), chain, timeout=180)
    finally:
        env["ops"].cancel()
    chain_ran, gate_ran = bool(env["ops"].names("start_router")), seen["reached"] is True
    assert chain_ran != gate_ran, (gate_res, chain_rc)
    if gate_ran:
        assert chain_rc == 2 and refusals(env)
    else:
        assert gate_res == 1 and chain_rc == 0


# ---- the Entry row: every check refuses BEFORE the router starts (rc 2, `REFUSED:`, NOT_STARTED)
def set_(**kw):
    return lambda env: [setattr(env["ops"], k, v) for k, v in kw.items()]


GOOD_STATE = {"watts": 140, "volts": 28, "batt": 80, "free_mem_mb": 1, "orphans_clean": True, "busy": []}
ENTRY = [
    ("busy", set_(start_state=lambda: dict(GOOD_STATE, busy=["4242 python -m bench.run_lcb --model other"])), "busy"),
    ("survivor", set_(start_state=lambda: dict(GOOD_STATE, busy=["4243 opencode run --model x"])), "busy"),
    ("listener", set_(listeners=lambda: [4244]), ":8000"),
    ("idle gap", set_(last_leg_end=lambda: time.time() - 10.0), "LAST_LEG_END"),
    ("idle gap 599 s", set_(last_leg_end=lambda: time.time() - 590.0), "LAST_LEG_END"),
    ("future LAST_LEG_END", set_(last_leg_end=lambda: time.time() + 3600.0), "LAST_LEG_END"),
    ("power watts", set_(power_state=lambda: {"watts": 96, "volts": 28, "batt": 80}), "power"),
    ("power volts", set_(power_state=lambda: {"watts": 140, "volts": 20, "batt": 80}), "power"),
    ("power battery", set_(power_state=lambda: {"watts": 140, "volts": 28, "batt": 20}), "power"),
    ("power unreadable", set_(power_state=lambda: {"watts": None, "volts": None, "batt": None}), "power"),
    ("registry unreadable", set_(overlay_sha=lambda: None), "registry"),
    ("head", lambda env: env["state"].update(head="c" * 40), "HEAD"),
    ("dirty", lambda env: env["state"].update(clean=False), "not clean"),
    ("gitlink", lambda env: setattr(env["ops"], "worktree_state", lambda *a: dict(
        head=env["state"]["head"], clean=True, gitlinks={"src/mlx-vlm": "d" * 40, "src/mlx-serve": S.BASE_GITLINKS["src/mlx-serve"]})),
     "gitlink"),
    ("probe identity", lambda env: env["ops"].extra_env.update(FAKE_PROBE_CODE_SHA="8" * 64), "probe identity"),
]


@pytest.mark.parametrize("name,setup,text", ENTRY, ids=[e[0] for e in ENTRY])
def test_a_failed_entry_check_refuses_before_the_router(tmp_path, monkeypatch, name, setup, text):
    rc, env = leg(tmp_path, monkeypatch, before=setup)
    assert rc == 2 and refusals(env), env["lines"][-6:]
    assert any(text in ln for ln in refusals(env)), (text, refusals(env))
    assert not env["ops"].names("start_router") and not env["ops"].names("load") and not S.invocations(env)
    assert not flocked(tmp_path / LEG) and not flocked(tmp_path / ARB)


def test_a_missing_entry_seam_refuses_never_skips(tmp_path, monkeypatch):
    def drop(env):
        env["ops"].last_leg_end = None
    rc, env = leg(tmp_path, monkeypatch, before=drop)
    assert rc == 2 and any("last_leg_end" in ln for ln in refusals(env)) and not env["ops"].names("start_router")


@pytest.mark.parametrize("what", ["kind", "self-hash"])
def test_a_wrong_record_refuses_before_the_router_and_leaves_no_lock_held(tmp_path, monkeypatch, what):
    def bad(env):
        rec = Path(env["records"]["v8"])
        if what == "kind":
            env["records"]["v8"] = env["records"]["reh"]                 # a rehearsal manifest is not a pilot's record
        else:
            rec.write_text(json.dumps(dict(json.loads(rec.read_text()), pilot_deadline_s=1.0)))
    rc, env = leg(tmp_path, monkeypatch, before=bad)
    assert rc == 2 and refusals(env) and not env["ops"].names("start_router") and not flocked(tmp_path / LEG)


def test_a_leg_whose_gap_is_over_600_seconds_runs(tmp_path, monkeypatch):
    rc, env = leg(tmp_path, monkeypatch, before=set_(last_leg_end=lambda: time.time() - 700.0))
    assert rc == 0, "\n".join(env["lines"][-8:])
    assert not refusals(env)


def spy_method(ops, name, calls):
    original = getattr(ops, name)

    def wrapped(*a, **k):
        calls.append((name, bool(ops.names("start_router"))))          # (seam, had the router started when it was read)
        return original(*a, **k)
    setattr(ops, name, wrapped)


def test_every_entry_seam_is_read_before_the_router_starts(tmp_path, monkeypatch):
    calls = []

    def spy(env):
        for name in ("start_state", "power_state", "last_leg_end", "worktree_state", "overlay_sha"):
            spy_method(env["ops"], name, calls)
    rc, env = leg(tmp_path, monkeypatch, before=spy)
    assert rc == 0
    before_router = {n for n, router_started in calls if not router_started}
    assert {"start_state", "power_state", "last_leg_end", "worktree_state", "overlay_sha"} <= before_router


# ---- legacy chains are unchanged
LEGACY = ["chain", "s1", "--probe-code-sha", X64, "--models", core.PICK1]


def test_a_legacy_chain_takes_no_lock_and_needs_no_entry_seam(env, tmp_path):
    assert run(env, LEGACY, registry=pinned_off_registry()) == 0
    assert not (tmp_path / "p426").exists() and not (tmp_path / "locks").exists()
    assert not hasattr(env["ops"], "last_leg_end")                       # the fake offers no entry seam; the chain never asked


def test_no_chain_harness_serves_the_live_registry(env, tmp_path, monkeypatch):
    """P531 / P518 / C246: the legacy harness's default served registry is the pinned OFF copy, never `REPO / "main_models.yaml"`
    (whose entry state moves with the shipped MTP default). Guards the shared `FakeOps` and the runner's `served_registry`."""
    import bench.tests.test_c147_chain_runner as t1c
    live = (t1c.REPO / "main_models.yaml").resolve()
    pinned = pinned_off_registry().resolve()
    assert pinned != live and Path(t1c.FakeOps(tmp_path).overlay).resolve() == pinned
    seen = []
    real = t1c.R.served_registry
    monkeypatch.setattr(t1c.R, "served_registry", lambda registry, ops: seen.append(Path(real(registry, ops)).resolve()) or seen[-1])
    assert run(env, LEGACY) == 0                                      # no `registry=`: the harness default
    assert seen == [pinned] and live not in seen
    assert real(None, None).resolve() == live                         # control: with no ops the runner itself WOULD pick the live file


def test_a_legacy_chain_runs_under_a_held_gate_lock(env, tmp_path):
    """The locks exclude the P426 chain only: a non-P426 tg1 chain neither takes nor honours them (legacy behaviour unchanged)."""
    with Hold(tmp_path / GATE):
        assert run(env, LEGACY, registry=pinned_off_registry()) == 0


# ================================================================================================ the Item `ready` row
def after_item(n, fn):
    """Apply `fn` to the world once item `n`'s barrier answered `.continue` (so no entry or invocation check can see it)."""
    def mutate(env):
        fn(env, lambda: bool(list(Path(env["out"]).rglob(f"*.item{n}.continue"))))
    return mutate


def test_a_changed_registry_sha_at_ready_invalidates_before_go(tmp_path, monkeypatch):
    def change(env, after):
        base = env["ops"].overlay_sha
        env["ops"].overlay_sha = lambda: "0" * 64 if after() else base()
    rc, env = leg(tmp_path, monkeypatch, before=after_item(1, change))
    assert rc == 2 and has(env, ".item2.ready") and has(env, ".item2.stop") and not has(env, ".item2.go")
    assert len(S.invocations(env)) == 1 and "invalidate" in (Path(env["out"]) / "chain.json").read_text(), env["lines"][-6:]
    assert said(env, "registry")


def test_a_dirty_worktree_at_ready_invalidates_before_go(tmp_path, monkeypatch):
    def dirty(env, after):
        base = env["ops"].worktree_state
        env["ops"].worktree_state = lambda *a: dict(base(*a), clean=False) if after() else base(*a)
    rc, env = leg(tmp_path, monkeypatch, before=after_item(1, dirty))
    assert rc == 2 and has(env, ".item2.ready") and has(env, ".item2.stop") and not has(env, ".item2.go")
    assert said(env, "not clean") or said(env, "worktree")
    assert "invalidate" in (Path(env["out"]) / "chain.json").read_text() and len(S.invocations(env)) == 1


def test_a_drifted_lifecycle_hash_at_ready_invalidates_before_go(tmp_path, monkeypatch):
    def drift(env, after):
        real = co.lifecycle_drift
        monkeypatch.setattr(core.co, "lifecycle_drift", lambda *a, **k: ["chain_core.py"] if after() else real(*a, **k))
    rc, env = leg(tmp_path, monkeypatch, before=after_item(1, drift))
    assert rc == 2 and has(env, ".item2.ready") and has(env, ".item2.stop") and not has(env, ".item2.go")
    assert said(env, "changed since chain creation")


def test_a_replaced_router_at_ready_still_invalidates_before_go(tmp_path, monkeypatch):
    def replace(env, after):
        base = env["ops"].create_time
        env["ops"].create_time = lambda pid: 99.0 if after() and pid == 1 else base(pid)
    rc, env = leg(tmp_path, monkeypatch, before=after_item(1, replace))
    assert rc == 2 and has(env, ".item2.stop") and not has(env, ".item2.go")


def test_a_failed_ready_check_writes_no_ready_record_and_no_go(tmp_path, monkeypatch):
    def dirty(env, after):
        base = env["ops"].worktree_state
        env["ops"].worktree_state = lambda *a: dict(base(*a), clean=False) if after() else base(*a)
    rc, env = leg(tmp_path, monkeypatch, before=after_item(1, dirty))
    ready = sorted(Path(env["out"]).rglob("items/*.ready.json"))
    assert rc == 2 and len(ready) == 2 and not has(env, ".item2.go")        # items 0 and 1 only


def after_go(n, fn):
    """Apply `fn` once item `n` was released (`.go`): the ready checks passed, the item is running; only a `done` check can see it."""
    def mutate(env):
        fn(env, lambda: bool(list(Path(env["out"]).rglob(f"*.item{n}.go"))))
    return mutate


@pytest.mark.parametrize("n", [2, 4], ids=["mid-invocation item", "the invocation's and leg's last item"])
def test_a_worktree_edited_during_an_item_invalidates_at_its_done_barrier(tmp_path, monkeypatch, n):
    """P54: spec 3, `done` barrier = the `ready` checks + reconciliation."""
    def dirty(env, running):
        base = env["ops"].worktree_state
        env["ops"].worktree_state = lambda *a: dict(base(*a), clean=False) if running() else base(*a)
    rc, env = leg(tmp_path, monkeypatch, before=after_go(n, dirty))
    assert rc == 2, "\n".join(env["lines"][-6:])
    assert has(env, f".item{n}.done") and has(env, f".item{n}.stop") and not has(env, f".item{n}.continue")
    invalid = [json.loads(p.read_text()) for p in Path(env["out"]).rglob("items/*.json")
               if not p.name.endswith((".ready.json", ".dnf.json")) and json.loads(p.read_text())["verdict"] == "invalid"]
    assert len(invalid) == 1 and "not clean" in json.dumps(invalid[0]["problems"])
    assert any(r["stage"] == "done" for r in json.loads((Path(env["out"]) / "chain.json").read_text())["p426_invalid"])


@pytest.mark.parametrize("what", ["registry", "lifecycle"])
def test_a_registry_or_lifecycle_change_during_an_item_invalidates_at_done(tmp_path, monkeypatch, what):
    def change(env, running):
        if what == "registry":
            base = env["ops"].overlay_sha
            env["ops"].overlay_sha = lambda: "0" * 64 if running() else base()
        else:
            real = co.lifecycle_drift
            monkeypatch.setattr(core.co, "lifecycle_drift", lambda *a, **k: ["chain_core.py"] if running() else real(*a, **k))
    rc, env = leg(tmp_path, monkeypatch, before=after_go(2, change))
    assert rc == 2 and has(env, ".item2.stop") and not has(env, ".item2.continue")


def test_done_runs_the_bound_ready_checks_and_still_writes_the_item_record(tmp_path):
    from bench.tests.test_b2_s4_reconcile import SLOT, ctx, make_hooks, row_of
    ops, hooks, out = make_hooks(tmp_path)
    hooks.before_attempt(SLOT, ctx())
    hooks.bind_ready_checks(lambda: ["worktree is not clean"])
    d = hooks.after_attempt(SLOT, dict(), ctx(row_of([])))
    assert d.kind == "invalidate" and "worktree is not clean" in d.reason
    rec = json.loads(next(p for p in (out / "items").glob("*.json") if not p.name.endswith(".ready.json")).read_text())
    assert rec["verdict"] == "invalid" and rec["checks"]["ready_checks"]["ok"] is False


def test_a_done_ready_check_that_cannot_run_is_a_hook_infrastructure_error(tmp_path):
    from bench.tests.test_b2_s4_reconcile import SLOT, ctx, make_hooks, row_of
    ops, hooks, out = make_hooks(tmp_path)
    hooks.before_attempt(SLOT, ctx())

    def boom():
        raise RuntimeError("git went away")
    hooks.bind_ready_checks(boom)
    with pytest.raises(ch.HookInfrastructureError, match="git went away"):
        hooks.after_attempt(SLOT, dict(), ctx(row_of([])))


# ---- P55: the listener seam is required, never optional
def test_the_listeners_seam_is_an_entry_seam_and_a_missing_one_refuses(tmp_path, monkeypatch):
    assert "listeners" in core.P426_ENTRY_SEAMS

    def drop(env):
        env["ops"].listeners = None
    rc, env = leg(tmp_path, monkeypatch, before=drop)
    assert rc == 2 and any("listeners" in ln for ln in refusals(env)) and not env["ops"].names("start_router")


# ---- P56: probing an opposing lock never creates it
def test_the_gate_creates_no_p426_lock_file_or_directory(tmp_path):
    with pl.acquire("gate", tmp_path):
        assert not (tmp_path / "p426").exists()
    assert (tmp_path / GATE).is_file()                          # its own lock file is created
    with pl.acquire("sequencer", tmp_path):
        pass
    assert (tmp_path / SEQ).is_file()


def test_probing_a_missing_opposing_lock_creates_nothing_but_the_actors_own_files(tmp_path):
    with pl.acquire("chain", tmp_path):
        assert not (tmp_path / GATE).exists()
    assert (tmp_path / LEG).is_file() and not (tmp_path / "gate").exists()


@pytest.mark.parametrize("shape", ["directory", "parent_is_a_file"])
def test_an_opposing_lock_that_cannot_be_opened_is_a_refusal_never_free(tmp_path, shape):
    if shape == "directory":
        (tmp_path / LEG).mkdir(parents=True)
    else:
        tmp_path.mkdir(exist_ok=True)
        (tmp_path / "p426").write_text("not a directory")
    with pytest.raises(pl.LockRefused, match=r"(SEQUENCER|LEG)\.lock cannot be probed"):
        pl.acquire("gate", tmp_path)
    assert not flocked(tmp_path / ARB) and not flocked(tmp_path / GATE)


def test_a_held_opposing_lock_is_still_refused_without_create(tmp_path):
    with Hold(tmp_path / LEG):
        with pytest.raises(pl.LockRefused, match="LEG.lock"):
            pl.acquire("gate", tmp_path)


def test_a_ready_check_that_cannot_run_is_a_hook_infrastructure_error(tmp_path):
    ops = SimpleNamespace(worker_ident=lambda m: dict(pid=5, create_time=1.0), server_log_path=lambda: tmp_path / "log",
                          create_time=lambda pid: 1.0, worker_metrics=lambda: {"summary": {}})
    hooks = ph.P426Hooks(ops=ops, out_root=tmp_path, arm="OFF", settle_bound_s=900.0)
    ctx = dict(stage="ready", slot="s", item="p1", k=0, ready={}, row=None,
               load=dict(idx=0, load_gen=1, worker=dict(pid=5, create_time=1.0), session="pilot", model="m", arm="OFF"))

    def boom():
        raise RuntimeError("git went away")
    hooks.bind_ready_checks(boom)
    with pytest.raises(ch.HookInfrastructureError, match="git went away"):
        hooks.before_attempt("s", ctx)


def test_the_ready_checks_bound_to_the_hooks_invalidate_with_every_problem(tmp_path):
    ops = SimpleNamespace(worker_ident=lambda m: dict(pid=5, create_time=1.0), server_log_path=lambda: tmp_path / "log",
                          create_time=lambda pid: 1.0, worker_metrics=lambda: {"summary": {}})
    hooks = ph.P426Hooks(ops=ops, out_root=tmp_path, arm="OFF", settle_bound_s=900.0)
    ctx = dict(stage="ready", slot="s", item="p1", k=0, ready={}, row=None,
               load=dict(idx=0, load_gen=1, worker=dict(pid=5, create_time=1.0), session="pilot", model="m", arm="OFF"))
    hooks.bind_ready_checks(lambda: ["registry sha256 changed", "worktree is not clean"])
    d = hooks.before_attempt("s", ctx)
    assert d.kind == "invalidate" and "registry sha256 changed" in d.reason and "worktree is not clean" in d.reason
    assert not list(tmp_path.rglob("*.ready.json"))


def test_unbound_hooks_behave_as_before(tmp_path):
    """No chain bound ready checks (a hooks-only caller): the owned-identity checks alone, as at s4."""
    assert ph.P426Hooks(ops=SimpleNamespace(), out_root=tmp_path, arm="OFF", settle_bound_s=900.0).ready_checks is None
