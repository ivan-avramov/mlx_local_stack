"""S27 -- test-writer delivery 3: one scenario test per adopted finding of change review round 1 (X1, X2, X4, X7, X8, X10-X13,
X14, X15, X16, X19), written from the fix diff and the specification. Intent first (S28-P5): each test states the outcome the
finding requires; it is exact only where data validity depends on it (refusals, counts, pairing, row digests).

Class (a) = reproduces a candidate-1 defect, (b) preserves an invariant, (c) new behaviour. "candidate 1" cannot be run here
(the copy holds candidate 2, and nothing may be reverted): where a test would have failed on it, the docstring says
"candidate 1: ..." and that is CHECKED BY INSPECTION of `../scratch/fix-1.patch`; the baseline column of the report is real.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from bench import chain_core as core
from bench import chain_hooks as ch
from bench import chain_ops as co
from bench import p426_hooks as ph
from bench import p426_reconcile as pr
from bench import proc_guard as pg
from bench.token_turn_gate import TransportAbort
from bench.tests.test_b2_s4_reconcile import BEFORE, STREAM_CLOSED, completed, failed, lines_of, make_hooks, row_of, started, ctx, SLOT
from bench.tests.test_s27_fe_chain import Broken, SLOT_A, at_ready, bare, barrier, hold_state, stop_of, to_done
from bench.tests.test_s27_fe_ownership import FOREIGN_SID, Proc, World, foreign_entry

pytestmark = pytest.mark.usefixtures("fake_guard_clock")
TESTS = Path(__file__).resolve().parent


# ------------------------------------------------------------------------------------------------ X1: the probe CLIs take `interrupt`
@pytest.mark.parametrize("module, flag", [("run_tg1_probe", "--tg1-inject"), ("run_tg2_probe", "--tg2-inject"),
                                          ("run_oc_probe", "--tg1-inject")])
def test_x1_the_real_probe_parsers_accept_the_interrupt_kind_and_still_refuse_an_unknown_one(module, flag, monkeypatch, tmp_path):
    """(a) spec 4.5: the run is issued through each probe's own CLI. Baseline / candidate 1: `--tg*-inject` choices were the old
    three, so no positives record could contain the interrupt run."""
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    parser = importlib.import_module(module)._parser()
    action = next(a for a in parser._actions if flag in a.option_strings)
    assert "interrupt" in action.choices
    assert {"stall", "loop", "alloc"} <= set(action.choices)             # nothing is lost
    assert "bogus" not in action.choices


def test_x1_the_probe_the_verifier_and_the_inject_driver_share_one_kind_list():
    """(c) X1: one list of inject kinds, so no consumer can lag behind the others again."""
    from bench import run_config as rc
    from m62 import inject_verify as iv
    assert tuple(iv.KINDS) == tuple(rc.ALL_INJECT_KINDS) and "interrupt" in rc.ALL_INJECT_KINDS


# ------------------------------------------------------------------------------------------------ X2: kill_inflight_failed on recorded evidence
def x2_case(row_edit=None, after_edit=None, line_edit=None):
    """A kill whose `/metrics` sample read 0 in flight, with one trailing failed request (the client's next request, opened before
    the SIGTERM): the facts the spec's order-tolerant rule reads are all recorded."""
    n, session = 2, "ses_s27fe"
    raw = []
    for i in range(n):
        raw += [started(), completed(session, 1000 + i, 10 + i)]
    raw += [started(), failed(STREAM_CLOSED)]
    if line_edit:
        raw = line_edit(raw)
    lines = lines_of(*raw)
    c = [x for x in lines if x.kind == "completed"]
    s = [x for x in lines if x.kind == "started"]
    f = [x for x in lines if x.kind == "failed"]
    before = dict(BEFORE)
    after = dict(before, requests_started=before["requests_started"] + len(s), requests_completed=before["requests_completed"] + len(c),
                 requests_failed=before["requests_failed"] + len(f),
                 prompt_tokens_total=before["prompt_tokens_total"] + sum(int(x.fields["prompt_tokens"]) for x in c),
                 generated_tokens_total=before["generated_tokens_total"] + sum(int(x.fields["generated_tokens"]) for x in c),
                 last_error=dict(error=STREAM_CLOSED, timestamp_unix=1000.5))
    usage = [[f"m{i + 1}", 10 + i, 1000 + i, 81920] for i in range(n)]
    term = dict(reason="looping", killed_verified=True, in_flight_at_kill=0, requests_at_kill=n, ingested_offset_at_count=300,
                events_size_at_count=300, signal_offset=500, signal_at=1000.0, step_end_offsets=[100, 200],
                step_start_offsets=[50, 150, 300])
    row = dict(id="python/a", session_id=session, request_usage=usage, nonconv_kind="looping",
               gate=dict(requests_completed=n, requests_completed_at_kill=n), termination=term,
               reconciliation=dict(unmatched_export_messages=1, trailing="interrupted"))
    if row_edit:
        row_edit(row)
    if after_edit:
        after_edit(after)
    return row, lines, before, after


def test_x2_a_trailing_failed_request_opened_before_the_signal_is_accepted_on_recorded_evidence():
    """(a) X2 / S28-P7: the `/metrics` sample and the client's next request are independent events; with every anchor recorded the
    kill is a reconciled one (candidate 1: refused on `inflight_evidence`, a whole-leg INVALID: by inspection of the fix diff)."""
    rep = pr.reconcile_item(*x2_case())
    assert rep.ok, rep.problems
    assert rep.late_record and rep.late_record.get("shape") == "open_step_at_signal"


def test_x2_the_old_in_flight_evidence_path_is_unchanged():
    """(b) a sample that did read one request in flight is still the evidence, with none of the new fields."""
    def row_edit(row):
        row["termination"].update(in_flight_at_kill=1)
        for k in ("signal_offset", "signal_at", "step_end_offsets", "step_start_offsets"):
            row["termination"].pop(k)
    rep = pr.reconcile_item(*x2_case(row_edit=row_edit))
    assert rep.ok, rep.problems


@pytest.mark.parametrize("what, row_edit, after_edit, line_edit", [
    ("no signal was delivered", lambda r: r["termination"].update(signal_offset=None), None, None),
    ("the wall time of the signal is not recorded", lambda r: r["termination"].pop("signal_at"), None, None),
    ("the step start offsets are not recorded", lambda r: r["termination"].pop("step_start_offsets"), None, None),
    ("the step end offsets are not recorded", lambda r: r["termination"].pop("step_end_offsets"), None, None),
    ("two steps were open at the signal (one start too many)",
     lambda r: r["termination"].update(step_start_offsets=[50, 150, 250, 300]), None, None),
    ("the open step started after the signal", lambda r: r["termination"].update(step_start_offsets=[50, 150, 600]), None, None),
    ("the open step started before the n-th step ended", lambda r: r["termination"].update(step_start_offsets=[50, 150, 180]), None, None),
    ("the worker's failed delta is not 1", None, lambda a: a.update(requests_failed=a["requests_failed"] + 1), None),
    ("the failed line is older than the SIGTERM", None, lambda a: a.update(last_error=dict(error=STREAM_CLOSED, timestamp_unix=999.0)), None),
    ("the worker reports another last error", None, lambda a: a.update(last_error=dict(error="boom", timestamp_unix=1000.5)), None),
    ("the worker reports no last error", None, lambda a: a.pop("last_error"), None),
    ("the failed line has another error text", None, None, lambda raw: raw[:-1] + [failed("boom")]),
    ("the failed line is not the window's last", None, None, lambda raw: raw[:-2] + [started(), completed("ses_s27fe", 5000, 5), raw[-2], raw[-1]][:-1]),
])
def test_x2_each_missing_anchor_keeps_the_refusal(what, row_edit, after_edit, line_edit):
    """(b) fail closed: the rule accepts only the whole set of recorded facts; the unanchored variant stays off-table."""
    rep = pr.reconcile_item(*x2_case(row_edit=row_edit, after_edit=after_edit, line_edit=line_edit))
    assert not rep.ok, what


# ------------------------------------------------------------------------------------------------ X4: the accounting sidecar
ROW = {"id": "python/a", "gate": {}}                 # what `to_done` makes `chain_rows.read_rows` return


def _done_with_broken_hook(tmp_path, monkeypatch, prepare=None, not_evaluated=()):
    c = bare(tmp_path)
    bar = barrier(tmp_path, c)
    to_done(tmp_path, monkeypatch, c, bar)
    if prepare:
        prepare()

    class Hook(ch.ChainHooks):
        def after_attempt(self, slot, done, context=None):
            raise ch.HookInfrastructureError("record_write_failed", not_evaluated=not_evaluated)
    c.hooks = Hook()
    c.pump_barrier(bar)
    return c


def test_x4_a_sidecar_that_the_hook_already_sealed_for_this_row_is_not_written_twice_and_the_leg_goes_on(tmp_path, monkeypatch):
    """(b) 'already sealed' is a real state: the exact sidecar of this slot, attempt and row."""
    c = _done_with_broken_hook(tmp_path, monkeypatch, lambda: ph.write_accounting(tmp_path, SLOT_A, 0, ROW, None, ["x"]))
    assert (tmp_path / "b.item0.continue").exists() and not hold_state(c)


@pytest.mark.parametrize("what, prepare", [
    ("the items path is a file", lambda p: p.joinpath("items").write_text("not a directory")),
    ("the sidecar is a symlink to a valid sealed record", lambda p: _symlinked_sidecar(p)),
    ("the sidecar is another row's", lambda p: ph.write_accounting(p, SLOT_A, 0, {"id": "python/a", "gate": {"x": 1}}, None, ["x"])),
    ("the sidecar is another attempt's", lambda p: ph.write_accounting(p, SLOT_A, 1, ROW, None, ["x"]) and
     p.joinpath("items", "E__A__M__s1__python__a.accounting.json").write_text(
         p.joinpath("items", "E__A__M__s1__python__a.r1.accounting.json").read_text())),
    ("the sidecar is not sealed", lambda p: _junk_sidecar(p)),
    ("the sidecar path is a directory", lambda p: p.joinpath("items", "E__A__M__s1__python__a.accounting.json").mkdir(parents=True)),
])
def test_x4_anything_but_this_attempts_own_sealed_sidecar_pauses_the_leg(tmp_path, monkeypatch, what, prepare):
    """(a) X4 / spec 5.3: 'if the sidecar cannot be persisted, the leg is PAUSED' and never continues as if it were. Candidate 1
    took any FileExistsError (a file-shadowed `items`, a stale or forged file) for 'already sealed' (by inspection)."""
    c = _done_with_broken_hook(tmp_path, monkeypatch, lambda: prepare(tmp_path))
    assert not (tmp_path / "b.item0.continue").exists(), what
    assert c.p426_invalid == [] and (hold_state(c) or stop_of(tmp_path) == {"disposition": "hold"}), what


def _symlinked_sidecar(path):
    real = path / "elsewhere.json"
    real.parent.mkdir(parents=True, exist_ok=True)
    sealed = ph.seal(dict(slot=SLOT_A, rerun_index=0, row_sha256=ph.row_sha256(ROW), item_record_sha256=None,
                          failed_checks=["x"], disposition="accounting_fault"))
    real.write_text(json.dumps(sealed))
    (path / "items").mkdir(parents=True, exist_ok=True)
    (path / "items" / "E__A__M__s1__python__a.accounting.json").symlink_to(real)


def _junk_sidecar(path):
    (path / "items").mkdir(parents=True, exist_ok=True)
    (path / "items" / "E__A__M__s1__python__a.accounting.json").write_text("{}")


# ------------------------------------------------------------------------------------------------ X16: what the done hook never reached
def test_x16_the_done_hook_names_the_checks_an_infrastructure_error_kept_it_from_evaluating(tmp_path):
    """(c) X16 / record only: an unrunnable ready check stops the hook after `preconditions`; the checks from there on were not
    evaluated, and the error says so (the next `ready` re-checks)."""
    ops, hooks, out = make_hooks(tmp_path)
    hooks.before_attempt(SLOT, ctx())
    ops.serve(started(), completed("ses_1", 100, 10))

    def broken():
        raise RuntimeError("the lifecycle check cannot run")
    hooks.bind_ready_checks(broken)
    with pytest.raises(ch.HookInfrastructureError) as err:
        hooks.after_attempt(SLOT, dict(id="python/a"), ctx(row_of([(100, 10)])))
    not_evaluated = set(err.value.not_evaluated)
    assert {"ready_checks", "reconciliation", "engagement"} <= not_evaluated
    assert "preconditions" not in not_evaluated                      # it ran


def test_x16_the_sidecar_of_a_done_infrastructure_error_records_the_unevaluated_checks(tmp_path, monkeypatch):
    """(c) the chain's accounting sidecar carries them (so a reader of the record knows what was not checked)."""
    c = _done_with_broken_hook(tmp_path, monkeypatch, not_evaluated=("ready_checks", "settle", "reconciliation"))
    side = json.loads((tmp_path / "items" / "E__A__M__s1__python__a.accounting.json").read_text())
    assert ph.sealed_ok(side) and side["not_evaluated"] == ["ready_checks", "settle", "reconciliation"]
    assert (tmp_path / "b.item0.continue").exists()


# ------------------------------------------------------------------------------------------------ X14: no silent defaults on the Chain
def test_x14_a_chain_built_without_its_state_has_no_defaulted_attributes():
    """(b) X14: a misspelt or missing attribute raises (candidate 1's `__getattr__` read an empty default in production)."""
    c = core.Chain.__new__(core.Chain)
    for name in ("p426_harness_dnf", "p426_holds", "p426_hold", "p426_acounting"):
        with pytest.raises(AttributeError):
            getattr(c, name)


# ------------------------------------------------------------------------------------------------ X8 / X11 / X13 / X15: the guard
def test_x8_a_foreign_record_carries_identity_never_the_arguments(leader):
    """(a) X8, the data boundary (the rows are public): executable basename and argument count, no argument, path or token."""
    leader.add(Proc(70200, sid=FOREIGN_SID, argv=["/usr/libexec/some-daemon", "--token=SECRET-123", "/private/path/x"]))
    leader.cleanup()
    status = leader.guard.status()
    entry = foreign_entry(status, 70200)
    assert entry is not None
    assert "SECRET" not in json.dumps(status) and "/private" not in json.dumps(status) and "--token" not in json.dumps(status)
    assert entry["argv"] == ["some-daemon"] and entry["argc"] == 3


@pytest.fixture
def leader(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch, leader=True)


def test_x11_a_process_the_scan_cannot_read_that_is_a_member_of_the_probe_session_is_never_silently_dropped(leader):
    """(a) X11 / 'an owned process is never left alive unrecorded': its same-uid read is denied, its session is ours: it stays
    an obligation, so the cleanup is uncertain while it is there (candidate 1 listed nothing: by inspection)."""
    leader.add(Proc(70210, sid=leader.probe_sid, deny=["uids"]))
    status, exc = leader.cleanup()
    assert isinstance(exc, TransportAbort) and status["uncertain"] is True


def test_x11_a_process_the_scan_cannot_read_that_belongs_to_nobody_we_know_is_counted_not_killed_not_refused(leader):
    """(a) X11: not ours, unreadable: counted (record only); never a refusal, never killed."""
    other = leader.add(Proc(70211, sid=FOREIGN_SID, deny=["uids"]))
    status, exc = leader.cleanup()
    assert exc is None and status["uncertain"] is False and status["unreadable_count"] >= 1 and not other.dead


def test_x11_such_a_process_that_exits_discharges_the_obligation(leader):
    """(b) gone is discharged, as every other claimed obligation."""
    member = leader.add(Proc(70212, sid=leader.probe_sid, deny=["uids"]))
    leader.processes.remove(member)                                     # it exited before the scan looked again
    status, exc = leader.cleanup()
    assert exc is None and status["uncertain"] is False


@pytest.mark.parametrize("denied", ["cwd", "cmdline", "environ"])
def test_x15_a_provably_older_process_with_a_denied_read_is_counted(leader, denied):
    """(a) X15 / spec 3.4: 'the rest are counted (unreadable_count), not listed' (candidate 1 counted only a denied liveness)."""
    old = leader.add(Proc(70220, sid=FOREIGN_SID, deny=[denied]))
    old.start_order = lambda: 5
    leader.guard.started_order = 1000
    status, exc = leader.cleanup()
    assert exc is None and status["uncertain"] is False and not old.dead
    assert foreign_entry(status, 70220) is None and status["unreadable_count"] >= 1


class _LaggingExit(Proc):
    """A killed process that the liveness read still reports alive for a while (the fork storm that is cleaned, but not instantly)."""

    def __init__(self, *a, lag=8, **kw):
        super().__init__(*a, **kw)
        self.lag, self.reads = lag, 0

    def status(self):
        if self.dead:
            self.reads += 1
            return "running" if self.reads <= self.lag else "zombie"
        return "running"


def test_x13_a_tracked_process_that_was_killed_and_is_verified_gone_is_not_a_survivor(tmp_path, monkeypatch):
    """(a) X13: 'survivors = alive or not verified gone'. Candidate 1 kept every pid the last audit round killed as a survivor,
    so a cleaned fork storm raised CleanupUncertain (by inspection of the fix diff)."""
    w = World(tmp_path, monkeypatch, leader=False)
    w.guard.kill_role = pg.ProcessGuard.kill_role.__get__(w.guard)
    proc = w.add(_LaggingExit(70230, ppid=os.getpid(), sid=61000, created=10))
    w.guard.register(proc, "client")
    status, exc = w.cleanup()
    assert exc is None, exc
    assert proc.dead and status["uncertain"] is False and status["survivors"] == []


def test_x13_a_process_that_is_really_still_alive_stays_a_survivor_and_uncertain(tmp_path, monkeypatch):
    """(b) the verification is not weakened."""
    w = World(tmp_path, monkeypatch, leader=False)
    w.guard.kill_role = pg.ProcessGuard.kill_role.__get__(w.guard)
    proc = w.add(Proc(70231, ppid=os.getpid(), sid=61000, created=10))
    w.guard.register(proc, "client")
    proc.kill = lambda: None
    status, exc = w.cleanup()
    assert isinstance(exc, TransportAbort) and status["uncertain"] is True and 70231 in status["survivors"]


# ------------------------------------------------------------------------------------------------ X10 / X8: the chain's scan, real processes
def _scan(**kw):
    ops = co.ChainOps.__new__(co.ChainOps)
    return ops.owned_scan(deadline_s=20.0, **kw)


@pytest.fixture
def spawned():
    procs = []

    def spawn(*args, **kw):
        # a user-space interpreter, not /bin/sleep: macOS denies the environment of hardened platform binaries
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        procs.append(p)
        return p
    yield spawn
    for p in procs:
        if p.poll() is None:
            p.kill()
        p.wait(timeout=10)


def test_x10_the_scan_kills_a_process_that_carries_the_runs_home_and_leaves_a_bystander_and_a_path_only_match(tmp_path, spawned):
    """(a) X10: one ownership rule. An environment match is ours (killed, verified); a process that merely works under the root
    is recorded by identity only (basename + argc, X8) and never killed; a bystander is untouched."""
    run = tmp_path / "run"
    (run / "home").mkdir(parents=True)
    ours = spawned(env={"HOME": str(run / "home"), "PATH": os.environ.get("PATH", "")})
    path_only = spawned(cwd=run, env={"PATH": os.environ.get("PATH", "")})
    bystander = spawned(env={"PATH": os.environ.get("PATH", "")})
    time.sleep(0.3)
    result = _scan(roots=[run])
    assert ours.poll() is not None, "the environment-matched process is ours and must be gone"
    assert path_only.poll() is None and bystander.poll() is None
    assert any(k["pid"] == ours.pid for k in result["killed"])
    listed = [e for e in result["path_only"] if e["pid"] == path_only.pid]
    assert listed and listed[0]["argv"] == [Path(sys.executable).name] and listed[0]["argc"] == 3
    assert "time.sleep" not in json.dumps(listed[0])


def test_x10_a_session_member_older_than_the_probe_is_not_ours(spawned):
    """(a) X10 / X22: the probe's recorded start bounds its session; a member that started before it is another holder of a
    reused session id. Nothing killed."""
    leader = spawned(start_new_session=True)
    time.sleep(0.3)
    started_at = pg.start_time(psutil.Process(leader.pid))
    _scan(sid=leader.pid, not_before=started_at + 10 ** 6)
    assert leader.poll() is None


SESSION_PROBE = ("import subprocess, sys, time\n"
                 "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], stdin=subprocess.DEVNULL,\n"
                 "                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                 "print(c.pid, flush=True)\n"
                 "%s\n")


def _alive(pid):
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def _gone(pid, timeout=10.0):
    end = time.monotonic() + timeout
    while _alive(pid) and time.monotonic() < end:
        time.sleep(0.05)
    return not _alive(pid)


def _probe_with_member(tail):
    """A stand-in probe: a session LEADER (`start_new_session`) that starts a non-leader member of its own session; `tail` is what
    the probe then does (stay alive, or exit while its member lives on)."""
    probe = subprocess.Popen([sys.executable, "-c", SESSION_PROBE % tail], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
                             text=True, start_new_session=True)
    member = int(probe.stdout.readline())
    return probe, member


def _cleanup(probe, member):
    for pid in (member, probe.pid):
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    probe.wait(timeout=10)


def test_x10_a_non_leader_member_of_the_probes_session_started_after_it_is_ours_and_is_killed():
    """(b) v4 (Y3: re-staged): the recorded probe leads the session; a member of that session, started after the probe's
    recorded start, is ours: killed and verified gone, whether the probe is still alive or already gone."""
    probe, member = _probe_with_member("time.sleep(120)")
    try:
        time.sleep(0.3)
        recorded = pg.start_time(psutil.Process(probe.pid))                    # what the probe recorded of itself
        result = _scan(sid=probe.pid, not_before=recorded)
        assert result["session_reused"] is None
        assert any(k["pid"] == member for k in result["killed"]) and _gone(member)
    finally:
        _cleanup(probe, member)


def test_x10_a_member_of_the_probes_session_is_still_ours_when_the_probe_has_already_exited():
    """(b) v4: the session outlives its leader (the kernel keeps its id from reuse while a member lives): bounded by the
    probe's recorded start, the member is ours."""
    probe, member = _probe_with_member("time.sleep(1.5)")
    try:
        recorded = pg.start_time(psutil.Process(probe.pid))
        probe.wait(timeout=20)                                                 # the probe exits; its member lives on
        assert _alive(member)
        result = _scan(sid=probe.pid, not_before=recorded)
        assert result["session_reused"] is None
        assert any(k["pid"] == member for k in result["killed"]) and _gone(member)
    finally:
        _cleanup(probe, member)


def test_x10_a_live_session_leader_that_is_not_the_recorded_probe_is_a_reused_session_and_nothing_is_killed():
    """(a) v4 (Y3): the leader of `sid` is alive but its start is not the recorded probe's (the session died and its pid was
    reused by an unrelated new session leader): no session claim, recorded as `session_reused`, neither the leader nor its
    member is touched. Candidate 2 claimed and killed them (by inspection of fix-2.patch)."""
    stranger, member = _probe_with_member("time.sleep(120)")
    try:
        time.sleep(0.3)
        real_start = pg.start_time(psutil.Process(stranger.pid))
        result = _scan(sid=stranger.pid, not_before=real_start - 10 ** 6)       # the probe recorded another start
        assert result["session_reused"] and result["session_reused"]["pid"] == stranger.pid
        assert result["killed"] == []
        assert _alive(stranger.pid) and _alive(member)
    finally:
        _cleanup(stranger, member)


def test_x10_without_the_probes_recorded_start_a_session_proves_nothing(spawned):
    """(a) fail closed: no start recorded -> the session is not trusted (not killed) and the scan is not certain."""
    leader = spawned(start_new_session=True)
    time.sleep(0.3)
    result = _scan(sid=leader.pid, not_before=None)
    assert leader.poll() is None and result["certain"] is False


# ------------------------------------------------------------------------------------------------ X7: the watcher's idea of "ours"
def test_x7_the_driver_s_own_shell_session_is_never_ours_but_a_probe_session_it_leads_is(tmp_path, spawned):
    """(a) X7: the sequencer launches the chain in the ambient (shell) session; its other members are not ours, the sessions LED by
    a descendant (the probes) are."""
    sys.path.insert(0, str(TESTS.parents[1] / "m1"))
    import bench_watch as bw
    code = ("import subprocess,sys,time\n"
            "c=subprocess.Popen(['sleep','60'],start_new_session=True)\n"
            "print(c.pid,flush=True)\n"
            "time.sleep(60)\n")
    driver = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
    try:
        child = int(driver.stdout.readline())
        bystander = spawned()                                    # same (ambient) session as the driver, not its descendant
        pids, sids = bw.BoxSampler(driver.pid, tmp_path / "probe")._ours(psutil)
        assert child in pids and child in sids
        assert os.getsid(driver.pid) not in sids, "the driver's own session must not be claimed"
        assert bystander.pid not in pids
    finally:
        for pid in (locals().get("child"),):
            if pid:
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass
        driver.kill()
        driver.wait(timeout=10)


# ------------------------------------------------------------------------------------------------ X12: the interrupt's evidence in v8
def _tg2_record(tmp_path, monkeypatch, **ops_kw):
    from bench.tests.s26_frozen import s26_support as X
    world = X.HostWorld(tmp_path / "host")
    ops = X.PosOps(tmp_path, world, **ops_kw)
    rc, out = X.positives(tmp_path, monkeypatch, ops)
    return rc, X.record(out)


def _v8(doc):
    from bench import p426_freeze as fz
    from bench.tests.s26_frozen import s26_support as X
    return fz.positives_problems(doc, arm="n16", commit=X.COMMIT, identity=dict(X.IDENT), frozen_prompt_date=X.DATE,
                                 image_id=doc["image_id"], cancel_path_sha256=fz.CANCEL_PATH_SHA256)


@pytest.mark.parametrize("what, edit", [
    ("no row digest", lambda e: e.pop("row_sha256")),
    ("a malformed row digest", lambda e: e.update(row_sha256="abc")),
    ("a nonzero probe exit", lambda e: e.update(probe_rc=1)),
    ("no probe exit recorded", lambda e: e.pop("probe_rc")),
    ("the verifier did not say PASS", lambda e: e.update(verify_verdict="PASS_NO_INFLIGHT")),
    ("no verifier verdict", lambda e: e.pop("verify_verdict")),
])
def test_x12_v8_refuses_an_interrupt_entry_without_its_evidence(tmp_path, monkeypatch, what, edit):
    """(a) X12: the interrupt is the record's one cancellation proof, so its PASS needs the in-flight verdict of the verifier, a
    clean probe exit and its row's digest, not the verdict string alone (candidate 1 accepted the string: by inspection)."""
    rc, doc = _tg2_record(tmp_path, monkeypatch)
    assert rc == 0 and _v8(doc) == []
    body = {k: v for k, v in doc.items() if k != "sha256"}
    body["injects"] = [dict(e) for e in body["injects"]]
    entry = next(e for e in body["injects"] if e["kind"] == "interrupt")
    edit(entry)
    problems = _v8(ph.seal(body))
    assert problems and any("interrupt" in p for p in problems), what


def test_x12_the_writer_fails_an_interrupt_whose_row_differs_from_the_one_the_probe_reported(tmp_path, monkeypatch):
    """(a) X12: the sha of the row on disk is checked for every PASS (kind-independent)."""
    from bench.tests.s26_frozen import s26_support as X
    rc, doc = _tg2_record(tmp_path, monkeypatch, bad_row_sha={(X.LANGS[0], "interrupt")})
    assert rc == 1 and doc["verdict"] == "FAIL"
    assert any("interrupt" in p for p in doc["problems"])


def test_x12_the_writer_fails_an_interrupt_the_probe_exited_nonzero_for(tmp_path, monkeypatch):
    """(b) a probe failure is never a PASS."""
    from bench.tests.s26_frozen import s26_support as X
    rc, doc = _tg2_record(tmp_path, monkeypatch, probe_rc={(X.LANGS[0], "interrupt"): 1})
    assert rc == 1 and doc["verdict"] == "FAIL"


# ------------------------------------------------------------------------------------------------ X19: the leak guard
def test_x19_no_test_module_wraps_the_guards_init_beside_the_hermetic_scan():
    """(a) X19: the conftest's hermetic scan already replaces `ProcessGuard.__init__` per test and restores it; a second wrapper
    installed through `monkeypatch` is undone AFTER that restore, so it re-installed the hermetic wrapper for the rest of the run
    (every later real-process test then used the family scan: the two broad-run-only failures). Candidate 1's C157 fixture did it
    (by inspection of the fix diff)."""
    offenders = []
    pattern = re.compile(r"""(setattr\(\s*[\w.]*ProcessGuard\s*,\s*["']__init__["']|setattr\(\s*[\w.]*proc_guard\.ProcessGuard\s*,\s*["']__init__["']|ProcessGuard\.__init__\s*=)""")
    for path in TESTS.rglob("*.py"):
        if path.name in ("conftest.py", "hermetic_scan.py", Path(__file__).name):
            continue
        if pattern.search(path.read_text(errors="replace")):
            offenders.append(path.relative_to(TESTS).as_posix())
    assert offenders == [], offenders


def test_x19_the_guards_init_is_not_left_replaced_by_a_test_helper():
    """(b) whatever installed it, one test's wrapper never survives into the next: this test sees the guard's `__init__` exactly
    as the conftest's hermetic wrapper (one level), not a wrapper of a wrapper."""
    init = pg.ProcessGuard.__init__
    inner = getattr(init, "__wrapped__", None)
    assert inner is None or getattr(inner, "__wrapped__", None) is None
    assert "install" in getattr(init, "__qualname__", "") or init.__qualname__.endswith("ProcessGuard.__init__")
