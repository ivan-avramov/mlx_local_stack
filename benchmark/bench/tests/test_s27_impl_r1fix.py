"""S27 change review r1 (ledger X1–X19): one red test (or more) per adopted finding."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from bench import chain_core as core
from bench import chain_hooks as ch
from bench import p426_hooks as ph
from bench.tests.test_b2_s3_core import BASE, barrier, bare

SLOT_A = f"{BASE}|a"
ROW = {"id": "python/a", "gate": {}}


class InfraAtDone(ch.ChainHooks):
    def __init__(self, cause="record_write_failed", not_evaluated=()):
        self.cause, self.not_evaluated = cause, not_evaluated

    def after_attempt(self, slot, done, context=None):
        raise ch.HookInfrastructureError(self.cause, not_evaluated=self.not_evaluated)


def to_done(c, tmp_path, monkeypatch, bar, row=ROW):
    (tmp_path / "b.item0.ready").write_text("{}")
    hooks, c.hooks = c.hooks, ch.ChainHooks()
    c.pump_barrier(bar)
    c.hooks = hooks
    (tmp_path / "b.item0.done").write_text(json.dumps({"id": row["id"]}))
    monkeypatch.setattr(core.cr, "read_rows", lambda p: [dict(row)])
    c.web_record, c.web_rules = (lambda *a, **k: {}), (lambda arm: None)


def paused(c, tmp_path):
    stop = tmp_path / "b.item0.stop"
    return (not (tmp_path / "b.item0.continue").exists() and stop.exists()
            and json.loads(stop.read_text()) == {"disposition": "hold"})


# ------------------------------------------------------------------------------------------------------------------ X4
def _done_infra(tmp_path, monkeypatch, prepare):
    c = bare(tmp_path)
    bar = barrier(tmp_path, c)
    to_done(c, tmp_path, monkeypatch, bar)
    prepare(tmp_path)
    c.hooks = InfraAtDone()
    c.pump_barrier(bar)
    return c


def test_x4_an_existing_sidecar_of_another_row_is_not_already_sealed_the_leg_pauses(tmp_path, monkeypatch):
    def prepare(root):
        ph.write_accounting(root, SLOT_A, 0, {"id": "python/a", "gate": {"other": 1}}, None, ["x"])
    c = _done_infra(tmp_path, monkeypatch, prepare)
    assert paused(c, tmp_path) and c.p426_invalid == []


def test_x4_an_existing_sidecar_of_another_attempt_is_not_already_sealed(tmp_path, monkeypatch):
    def prepare(root):
        doc = json.loads(json.dumps(ph.seal(dict(slot=SLOT_A, rerun_index=1, row_sha256=ph.row_sha256(ROW),
                                                  item_record_sha256=None, failed_checks=["x"],
                                                  disposition="accounting_fault"))))
        p = ph.accounting_path(root, SLOT_A, 0)
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps(doc))
    c = _done_infra(tmp_path, monkeypatch, prepare)
    assert paused(c, tmp_path)


def test_x4_a_symlinked_or_directory_sidecar_is_not_already_sealed(tmp_path, monkeypatch):
    def prepare(root):
        real = root / "elsewhere.json"
        ph.write_exclusive(real, dict(slot=SLOT_A, rerun_index=0, row_sha256=ph.row_sha256(ROW), item_record_sha256=None,
                                      failed_checks=["x"], disposition="accounting_fault"))
        p = ph.accounting_path(root, SLOT_A, 0)
        p.parent.mkdir(parents=True)
        os.symlink(real, p)
    c = _done_infra(tmp_path, monkeypatch, prepare)
    assert paused(c, tmp_path)
    d = tmp_path / "d"
    d.mkdir()

    def prepare_dir(root):
        ph.accounting_path(root, SLOT_A, 0).mkdir(parents=True)
    c = _done_infra(d, monkeypatch, prepare_dir)
    assert paused(c, d)


def test_x4_this_attempts_own_sealed_sidecar_counts_as_written_and_the_leg_continues(tmp_path, monkeypatch):
    def prepare(root):
        ph.write_accounting(root, SLOT_A, 0, ROW, None, ["boundary_count"])
    c = _done_infra(tmp_path, monkeypatch, prepare)
    assert (tmp_path / "b.item0.continue").exists() and not (tmp_path / "b.item0.stop").exists()


# ----------------------------------------------------------------------------------------------------------------- X16
def test_x16_a_failed_ready_check_at_done_names_the_checks_never_evaluated(tmp_path):
    hooks = ph.P426Hooks(ops=SimpleNamespace(), out_root=tmp_path, arm="A", settle_bound_s=1)

    def broken():
        raise RuntimeError("git unavailable")
    hooks.bind_ready_checks(broken)
    with pytest.raises(ch.HookInfrastructureError) as ei:
        hooks.after_attempt(SLOT_A, {"id": "python/a"}, context={"rerun_index": 0, "row": dict(ROW)})
    assert "ready_checks" in ei.value.not_evaluated and "reconciliation" in ei.value.not_evaluated
    assert "preconditions" not in ei.value.not_evaluated


def test_x16_the_done_infra_sidecar_records_the_checks_not_evaluated(tmp_path, monkeypatch):
    c = bare(tmp_path)
    bar = barrier(tmp_path, c)
    to_done(c, tmp_path, monkeypatch, bar)
    c.hooks = InfraAtDone("a ready check could not run", not_evaluated=("ready_checks", "reconciliation"))
    c.pump_barrier(bar)
    side = json.loads(ph.accounting_path(tmp_path, SLOT_A, 0).read_text())
    assert ph.sealed_ok(side) and side["not_evaluated"] == ["ready_checks", "reconciliation"]
    assert "not evaluated" in side["failed_checks"][0]
    assert (tmp_path / "b.item0.continue").exists()


# ----------------------------------------------------------------------------------------------------------------- X14
@pytest.mark.parametrize("name", ["p426_harness_dnf", "p426_faults", "p426_accounting", "p426_holds",
                                  "p426_pending_hold", "pause_path", "p426_misspelt"])
def test_x14_a_chain_has_no_silent_defaults_for_unset_s27_state(name, tmp_path):
    c = core.Chain.__new__(core.Chain)
    c.out_root = tmp_path
    with pytest.raises(AttributeError):
        getattr(c, name)
    assert c.paused_path == tmp_path / "PAUSED"          # derived from out_root, never a default


# ------------------------------------------------------------------------------------------------------------------ X5
def test_x5_a_ready_barrier_fault_on_item_two_is_stamped_at_ready_without_an_outcome(monkeypatch, tmp_path):
    """The abort stamp names the stage of the item actually running (item 2, before its generation), never item 1's `done`."""
    import importlib
    from bench import item_barrier as ib
    from bench.tests.test_tg1_integration import tg_fixture
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    real = ib.ItemBarrier.ready

    def ready(self, k):
        if k == 1:
            raise ib.BarrierTimeout("the chain did not answer item 2's ready barrier")
        return real(self, k)
    monkeypatch.setattr(ib.ItemBarrier, "ready", ready)
    f = tg_fixture(importlib.import_module("run_tg1_probe"), monkeypatch, tmp_path)
    with pytest.raises(BaseException):
        f["run"]("one,two")
    man = json.loads(f["out"].with_suffix(".manifest.json").read_text())
    stamp = man["transport_abort"]
    assert stamp["cause"] == "hook_infra"
    assert stamp["stage"] == "ready" and stamp["outcome_present"] is False
    assert [json.loads(x)["id"] for x in f["out"].read_text().splitlines()] == ["python/one"]


# ------------------------------------------------------------------------------------------------------------------ X3
def typed_infra():
    """X6: a grader infrastructure fault as the harness raises it (typed at the source)."""
    from bench import token_turn_gate as tg
    return tg.GraderInfraError("docker command failed (run): Cannot connect to the Docker daemon", kind="transport")


def _interim_worker(exc):
    from bench.tests.test_s27_impl_runner import worker
    import time as _t

    def grade(snap):
        raise exc
    w = worker(grade)
    w.notify(1)
    deadline = _t.monotonic() + 5
    while w.failure is None and _t.monotonic() < deadline:
        _t.sleep(0.01)
    return w


def test_x3_an_interim_infra_fault_first_seen_after_the_client_exited_is_recorded_not_a_rerun():
    """After the client exits the final grade decides: `finish()` hands the interim infrastructure fault back (recorded by
    the caller), never `GraderInfraAbort(stage="generation")`."""
    w = _interim_worker(typed_infra())
    fault = w.finish()
    assert fault is not None and "Docker daemon" in str(fault)


def test_x3_a_non_infra_interim_failure_still_aborts_at_finish():
    from bench import token_turn_gate as tg
    w = _interim_worker(tg.TransportAbort("malformed Go report"))
    with pytest.raises(tg.TransportAbort) as err:
        w.finish()
    assert not isinstance(err.value, tg.GraderInfraAbort)


def test_x3_while_the_client_still_generates_the_interim_infra_fault_stays_pre_outcome():
    from bench import arm_runner as ar
    from bench import token_turn_gate as tg
    w = _interim_worker(typed_infra())
    with pytest.raises(tg.GraderInfraAbort) as err:
        w.check()
    assert ar.harness_fault_cause(err.value) == ("grader_infra", "generation")
    w.finish()


def test_x3_run_item_records_the_interim_fault_and_the_final_grade_decides(monkeypatch, tmp_path):
    """The recorded case: the interim grade's infrastructure fault surfaces only at `finish()` (the fake client has exited);
    the row is written with the final grade's outcome and the fault in `termination` — one generation, no typed abort."""
    import importlib
    from bench.tests.test_s27_fe_support import ScriptedGrader, model
    from bench.tests.test_tg1_integration import tg_fixture
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    grader = ScriptedGrader(script=[typed_infra()], final_script=[model(0)]).install(monkeypatch)
    f = tg_fixture(importlib.import_module("run_tg1_probe"), monkeypatch, tmp_path)
    assert f["run"]("one") == 0
    assert grader.interims
    (row,) = [json.loads(x) for x in f["out"].read_text().splitlines()]
    assert row["passed"] is True and "interim_grade_fault" in row["termination"]


# ------------------------------------------------------------------------------------------------------------------ X6
@pytest.mark.parametrize("agent_text", [
    "tg2 preflight failed (rc=1): Error: connect ECONNREFUSED 127.0.0.1:5432 Connection refused",
    "tg2 stage failed (rc=1 timeout=False): cp: ./Cannot connect to the Docker daemon.txt: Broken pipe",
    "malformed Go report: panic: dial tcp: connection reset by peer; No such image",
    "Docker infrastructure failure: --- FAIL: TestDB (0.00s) Cannot connect to the Docker daemon",
])
def test_x6_agent_output_naming_a_fault_is_never_a_grader_infrastructure_fault(agent_text):
    from bench import token_turn_gate as tg
    assert not tg.grader_infra_fault(tg.TransportAbort(agent_text))


def test_x6_the_harness_own_docker_failures_are_typed_at_the_source(tmp_path):
    import subprocess
    from bench import tg2_grade as g
    from bench import token_turn_gate as tg

    def lost(*a, **k):
        raise ConnectionRefusedError("docker.sock")
    with pytest.raises(tg.TransportAbort) as err:
        g._plain(lost, ["docker", "volume", "ls"], tmp_path, "t")
    assert tg.grader_infra_fault(err.value) and err.value.kind == "transport"

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("docker", 30)
    with pytest.raises(tg.TransportAbort) as err:
        g._container_oom(slow, "c", tmp_path, "s")
    assert tg.grader_infra_fault(err.value)

    def listing_fails(cmd, stdout=None, **k):
        return SimpleNamespace(returncode=1)
    with pytest.raises(tg.TransportAbort) as err:
        g._exists(listing_fails, "volume", "v", tmp_path, "x")
    assert tg.grader_infra_fault(err.value)


def test_x6_a_stage_container_that_docker_could_not_start_is_spawn_infra_any_other_stage_failure_is_not(tmp_path):
    from bench import tg2_grade as g
    from bench import token_turn_gate as tg
    for rc, infra in ((125, True), (1, False)):
        out = tmp_path / str(rc)
        out.mkdir()
        (out / "s.stdout").write_text("Cannot connect to the Docker daemon")
        (out / "s.stderr").write_text("")
        launch = dict(rc=rc, timed_out=False, stdout=out / "s.stdout", stderr=out / "s.stderr")
        err = g.stage_failure(launch)
        assert isinstance(err, tg.TransportAbort) and tg.grader_infra_fault(err) is infra


@pytest.mark.parametrize("name", [
    "test_two_final_infrastructure_faults_then_a_pass_is_accepted_with_one_generation_and_one_snapshot",
    "test_one_final_infrastructure_fault_then_a_fail_is_the_models_scored_fail",
    "test_three_final_infrastructure_faults_end_the_item_with_the_grader_infra_stamp_and_the_generation_evidence",
])
def test_x6_the_frozen_final_grade_scenarios_hold_with_a_typed_infrastructure_fault(name, monkeypatch, tmp_path):
    """The frozen fixture `test_s27_fe_support.infra()` is an untyped `TransportAbort` classified by its text (G1 v2): under X6
    it is no longer a grader fault. With ONLY that fixture typed, the frozen scenarios hold unchanged (evidence for the report;
    the frozen files are not edited)."""
    import importlib
    from bench.tests import test_s27_fe_grader as fg
    monkeypatch.setattr(fg, "infra", typed_infra)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    getattr(fg, name)(importlib.import_module("run_tg1_probe"), monkeypatch, tmp_path)


# ------------------------------------------------------------------------------------------------------------------ X2
def _x2_case(**over):
    """A kill whose `/metrics` sample read 0 in flight (the client was between requests) while the client then opened the
    next request before the SIGTERM landed; the worker failed it (one trailing STREAM_CLOSED line)."""
    from bench import p426_reconcile as pr
    from bench.tests import b2_frozen_support as S
    from bench.tests.test_b2_frozen_s4_reconcile import BEFORE, after, lines_of
    r = S.golden_row("item_stall_kill")
    u = r["request_usage"]
    n = len(u)
    signal_at = 1793524600.0
    ends = [100 * (k + 1) for k in range(n)]
    term = dict(r["termination"], in_flight_at_kill=0, signal_offset=ends[-1] + 80, signal_at=signal_at,
                step_end_offsets=ends, step_start_offsets=[e - 60 for e in ends] + [ends[-1] + 40])
    term.update(over.pop("term", {}))
    r["termination"] = term
    lines = S.item_window(r["session_id"], u) + [S.started_line(), S.failed_line()]
    aft = after(u, failed=1)
    aft["last_error"] = dict(error=pr.STREAM_CLOSED, timestamp_unix=over.pop("failed_at", signal_at + 0.4))
    for k, v in over.items():
        aft[k] = v
    return pr.reconcile_item(r, lines_of(lines), BEFORE, aft)


def test_x2_a_failed_request_the_client_opened_before_the_signal_is_accepted_on_recorded_evidence():
    rep = _x2_case()
    assert rep.ok is True and rep.case == "kill_inflight_failed", rep.problems
    assert rep.late_record and rep.late_record["shape"] == "open_step_at_signal"


@pytest.mark.parametrize("term,extra", [
    (dict(signal_offset=None, signal_at=None), {}),                        # no signal was delivered
    (dict(step_start_offsets=None), {}),                                   # the stream's starts are not recorded
    (dict(step_start_offsets="short"), {}),                                # no open step: starts == finishes
    (dict(signal_offset=520), {}),                                         # the open step started AFTER the signal
    ({}, dict(failed_at=1793524600.0 - 1.0)),                              # the worker failed it BEFORE the SIGTERM
])
def test_x2_without_every_anchor_the_trailing_failed_line_stays_off_table(term, extra):
    from bench.tests import b2_frozen_support as S
    if term.get("step_start_offsets") == "short":
        n = len(S.golden_row("item_stall_kill")["request_usage"])
        term = dict(step_start_offsets=[100 * (k + 1) - 60 for k in range(n)])
    rep = _x2_case(term=term, **extra)
    assert rep.ok is False and "inflight_evidence" in rep.checks and not rep.checks["inflight_evidence"]["ok"]


# ------------------------------------------------------------------------------------------------------------------ X9
@pytest.mark.parametrize("last", ["absent", None])
def test_x9_the_unpublished_shape_needs_the_streams_last_step_start_id(last):
    """§4.2 / C375: the recovered message is bound to the open step by its id; a row without that id is not this case."""
    from bench import p426_reconcile as pr
    from bench.tests import test_s27_impl_reconcile as T
    doc = T.d1()
    row = T.row_of(doc)
    if last == "absent":
        row["termination"].pop("last_step_start", None)
    else:
        row["termination"]["last_step_start"] = None
    report = pr.reconcile_item(row, T.log_lines(doc), doc["worker_before"], doc["worker_after"])
    assert report.case != pr.LATE_RECORD and not report.ok


@pytest.mark.parametrize("module,name", [
    ("test_s27_fe_reconcile", "test_d1_the_recorded_numbers_are_a_late_record_of_the_unpublished_order"),
    ("test_s27_fe_reconcile", "test_d1_the_offsets_are_recorded_but_not_required_for_the_unpublished_shape"),
    ("test_s27_fe_done_hook", "test_the_recorded_d1_item_is_reconciled_by_the_hook_and_the_item_record_carries_the_late_record"),
])
def test_x9_the_frozen_d1_cases_hold_once_the_row_carries_the_open_steps_id(module, name, tmp_path, monkeypatch):
    """The frozen D1 fixture row predates `termination.last_step_start` (the field is new in S27); under X9 it is not the
    unpublished shape. With ONLY that id added (the 26th step's message, `msg_26` in the tests' usage naming), the frozen
    cases hold unchanged (evidence for the report; the frozen files are not edited)."""
    import importlib
    import inspect
    m = importlib.import_module(f"bench.tests.{module}")
    real = m.d1

    def d1_with_id():
        fx = real()
        fx["row"]["termination"] = dict(fx["row"].get("termination") or {}, last_step_start="msg_26")
        return fx
    monkeypatch.setattr(m, "d1", d1_with_id)
    fn = getattr(m, name)
    kwargs = {"tmp_path": tmp_path} if "tmp_path" in inspect.signature(fn).parameters else {}
    fn(**kwargs)


# ------------------------------------------------------------------------------------------------------------------ X1
@pytest.mark.parametrize("module,flag", [("run_tg1_probe", "--tg1-inject"), ("run_tg2_probe", "--tg2-inject"),
                                         ("run_oc_probe", "--tg1-inject")])
def test_x1_the_probe_clis_accept_every_shared_inject_kind_through_the_real_parser(module, flag, monkeypatch, tmp_path):
    import importlib
    from bench import run_config as rc
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    probe = importlib.import_module(module)
    base = ["--model", "M", "--items", "one", "--seed-base", "1"]
    for kind in rc.ALL_INJECT_KINDS:
        a, _ = probe._parser().parse_known_args(base + [flag, kind])
        assert a.tg1_inject == kind
    with pytest.raises(SystemExit):
        probe._parser().parse_known_args(base + [flag, "bogus"])


def test_x1_the_inject_kind_lists_are_the_one_shared_list():
    import importlib
    from bench import run_config as rc
    assert importlib.import_module("m62.inject_verify").KINDS == rc.ALL_INJECT_KINDS
    assert importlib.import_module("chains.c147.run_inject").KINDS == rc.ALL_INJECT_KINDS


# ----------------------------------------------------------------------------------------------------------------- X12
def _interrupt(**over):
    e = dict(language="rust", kind="interrupt", item="x", verdict="PASS", verify_verdict="PASS", probe_rc=0,
             row_sha256="a" * 64)
    e.update(over)
    return e


def test_x12_the_interrupt_is_the_cancellation_proof_v8_requires_its_rc_verdict_and_row_sha():
    from bench import p426_freeze as fz
    assert fz.interrupt_ok(_interrupt())
    for over in (dict(probe_rc=None), dict(probe_rc=1), dict(probe_rc=True), dict(verify_verdict="PASS_NO_INFLIGHT"),
                 dict(verify_verdict=None), dict(row_sha256=None), dict(row_sha256="zz"), dict(verdict="PASS_NO_INFLIGHT")):
        assert not fz.interrupt_ok(_interrupt(**over)), over


def test_x12_v8_refuses_a_record_whose_interrupt_pass_lacks_its_evidence():
    from bench import p426_freeze as fz
    from bench.tests import test_s27_impl_positives as P
    doc, _ = P.record()
    assert P.problems_of(doc) == []
    for over in (dict(probe_rc=None), dict(verify_verdict=None), dict(row_sha256=None)):
        injects = [dict(e, **over) if e["kind"] == "interrupt" else e for e in doc["injects"]]
        bad, _ = P.record(injects=injects)
        assert [p for p in P.problems_of(bad) if "interrupt" in p], over


@pytest.mark.parametrize("kind,verdict", [("interrupt", "PASS"), ("stall", "PASS"), ("stall", "PASS_NO_INFLIGHT"),
                                          ("loop", "PASS")])
def test_x12_the_writer_fails_a_pass_whose_row_is_missing(kind, verdict, tmp_path):
    from bench import p426_wave2 as w2
    ops = SimpleNamespace(positive_inject=lambda lang, item, kind, seed, attempt: dict(run=str(tmp_path), rc=0,
                                                                                       row_sha256="a" * 64),
                          inject_verify=lambda run, kind: verdict)
    entry, _ = w2.positive_entry(ops, tmp_path, "rust", "x", kind)
    assert entry["verdict"].startswith("FAIL"), entry


# ----------------------------------------------------------------------------------------------------------------- X13
def test_x13_a_process_killed_in_the_third_round_and_verified_gone_is_no_survivor(tmp_path):
    """A forked-storm survivor that dies on the third kill: killed and verified gone -> certain, not CleanupUncertain."""
    from bench import chain_incident as ci
    from bench.tests.test_proc_guard import Process
    from bench.tests.test_s27_impl_guard import PROBE_SID, make

    class Slow(Process):
        kills = 0

        def kill(self):
            Slow.kills += 1
            if Slow.kills >= 3:
                self.dead = True
    child = Slow(95, 1, created=11, argv=["node"])
    g, mp = make(tmp_path, [child], sessions={95: PROBE_SID})
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert child.dead and s["survivors"] == [] and s["uncertain"] is False and ci.cleanup_problems(s) == []


def test_x13_a_tracked_process_killed_in_the_last_audit_round_and_verified_gone_is_no_survivor(tmp_path):
    from bench.tests.test_proc_guard import Process
    from bench.tests.test_s27_impl_guard import make

    class Slow(Process):
        kills = 0

        def kill(self):
            Slow.kills += 1
            if Slow.kills >= 3:
                self.dead = True
    child = Slow(96, 1, created=11)
    g, mp = make(tmp_path, [child], sessions={96: 777})
    g.tracked[(96, 11)] = "client"
    g._processes = lambda: []                     # only the tracked audit sees it (its uids() read was denied)
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert child.dead and s["survivors"] == [] and s["uncertain"] is False


# ------------------------------------------------------------------------------------------------------------------ X8
def test_x8_foreign_new_records_identity_never_the_command_line_content(tmp_path):
    from bench.tests.test_proc_guard import Process
    from bench.tests.test_s27_impl_guard import FOREIGN_SID, make
    p = Process(81, 1, created=11, argv=["/opt/tool/bin/python3.12", "--token=s3cr3t", "/somewhere/private/project"])
    g, mp = make(tmp_path, [p], sessions={81: FOREIGN_SID})
    try:
        g.cleanup()
    finally:
        mp.undo()
    (e,) = g.status()["foreign_new"]
    assert e["argv"] == ["python3.12"] and e["argc"] == 3
    assert "s3cr3t" not in json.dumps(e) and "/somewhere" not in json.dumps(e)
    assert set(e) == {"pid", "create_time", "sid", "path_match", "unreadable", "argv", "argc"}


# ----------------------------------------------------------------------------------------------------------------- X15
@pytest.mark.parametrize("deny", ["cwd", "environ"])
def test_x15_a_provably_older_unclaimed_process_with_a_denied_read_is_counted(tmp_path, deny):
    """§3.4: an unclaimed unreadable process provably older than the guard is counted (`unreadable_count`), not listed."""
    from bench.tests.test_s27_impl_guard import FOREIGN_SID, Denied, make

    class OldDenied(Denied):
        def start_order(self):
            return 1                                  # readable and proven older than the guard (order 10)
    old = OldDenied(71, 1, created=11, deny=(deny,))
    g, mp = make(tmp_path, [old], sessions={71: FOREIGN_SID}, markers={"HOME": str(tmp_path / "home")},
                 roots=[tmp_path, tmp_path / "home"])
    g.started_order = 10
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert s["unreadable_count"] == 1 and s["foreign_new"] == [] and s["uncertain"] is False and not old.dead


def test_x15_a_provably_older_readable_process_is_neither_counted_nor_listed(tmp_path):
    from bench.tests.test_s27_impl_guard import FOREIGN_SID, Denied, make

    class Old(Denied):
        def start_order(self):
            return 1
    old = Old(72, 1, created=11, deny=())
    g, mp = make(tmp_path, [old], sessions={72: FOREIGN_SID}, markers={"HOME": str(tmp_path / "home")},
                 roots=[tmp_path, tmp_path / "home"])
    g.started_order = 10
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert s["unreadable_count"] == 0 and s["foreign_new"] == []


# ----------------------------------------------------------------------------------------------------------------- X11
class UidDenied:
    """A listed process whose uids() read is denied (mid-exec / mid-exit): same-uid cannot even be established."""

    def __init__(self, pid):
        self.pid = pid

    def uids(self):
        import psutil
        raise psutil.AccessDenied(self.pid)

    def __getattr__(self, name):
        import psutil

        def denied(*a, **k):
            raise psutil.AccessDenied(self.pid)
        return denied


def test_x11_a_uid_denied_member_of_the_probe_session_is_a_claimed_obligation_never_dropped(tmp_path):
    from bench import proc_guard as pg
    from bench.tests.test_s27_impl_guard import PROBE_SID, make
    member = UidDenied(73)
    g, mp = make(tmp_path, [member], sessions={73: PROBE_SID})
    g.reconcile_deadline_s = 0.5
    try:
        with pytest.raises(pg.CleanupUncertain):
            g.cleanup()
    finally:
        mp.undo()
    assert 73 in [r["pid"] for r in g.status()["uncertain_records"]]


def test_x11_a_uid_denied_unclaimed_process_is_counted_and_the_cleanup_stays_certain(tmp_path):
    from bench.tests.test_s27_impl_guard import FOREIGN_SID, make
    stranger = UidDenied(74)
    g, mp = make(tmp_path, [stranger], sessions={74: FOREIGN_SID})
    try:
        g.cleanup()
    finally:
        mp.undo()
    s = g.status()
    assert s["uncertain"] is False and s["unreadable_count"] == 1


def test_x11_the_scan_reports_a_pid_it_cannot_construct_instead_of_dropping_it():
    from bench import proc_guard as pg

    class FakePsutil:
        NoSuchProcess, AccessDenied = type("NSP", (Exception,), {}), type("AD", (Exception,), {})

        @staticmethod
        def pids():
            return [5, 6]

        @classmethod
        def Process(cls, pid):
            if pid == 6:
                raise cls.AccessDenied()
            return SimpleNamespace(pid=pid)
    denied = set()
    out = pg._scan(FakePsutil, {}, denied)
    assert [p.pid for p in out] == [5] and denied == {6}


def test_x11_a_tracked_pid_the_scan_cannot_construct_is_a_claimed_obligation(tmp_path):
    from bench import proc_guard as pg
    from bench.tests.test_s27_impl_guard import make
    g, mp = make(tmp_path, [], sessions={75: 777})
    g.tracked[(75, 11)] = "model"
    real = g.scan

    def scan():
        g._scan_denied.add(75)
        return real()
    g.scan = scan

    def get(pid):
        import psutil
        raise psutil.AccessDenied(pid)               # still present, still unreadable: never "gone"
    g.get = get
    g.reconcile_deadline_s = 0.5
    try:
        with pytest.raises(pg.CleanupUncertain):
            g.cleanup()
    finally:
        mp.undo()
    assert 75 in [r["pid"] for r in g.status()["uncertain_records"]]


# ----------------------------------------------------------------------------------------------------------------- X10
def _ops(tmp_path):
    import time as _t
    from bench import chain_ops as co
    return co.ChainOps(tmp_path, tmp_path, tmp_path / "overlay.yaml", lambda m: None, sleep=_t.sleep)


def _leader():
    import subprocess
    import sys
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_x10_a_session_member_older_than_the_probe_is_not_ours_and_is_never_killed(tmp_path):
    """Session members are bounded by the probe's start (a reused session id after a long pause names another process)."""
    import psutil
    from bench import proc_guard as pg
    old = _leader()
    try:
        started = pg.start_time(psutil.Process(old.pid))
        scan = _ops(tmp_path).owned_scan(sid=os.getsid(old.pid), not_before=started + 5.0, roots=[],
                                         container_prefixes=(), deadline_s=5.0)
        assert old.poll() is None and scan["killed"] == [] and scan["certain"] is True
    finally:
        old.kill()
        old.wait(timeout=10)


def test_x10_without_the_probes_recorded_start_a_session_scan_proves_nothing(tmp_path):
    scan = _ops(tmp_path).owned_scan(sid=2 ** 30 + 7, roots=[], container_prefixes=(), deadline_s=5.0)
    assert scan["certain"] is False and any("start" in p for p in scan["problems"])


def _fake_table(monkeypatch, *, member):
    import psutil
    from bench import chain_ops as co
    real_process = psutil.Process

    def Process(pid=None):
        if pid == 88001:
            raise psutil.AccessDenied(pid)
        if pid == 5150:                              # Y3: the probe session's leader has exited (no reuse to rule out)
            raise psutil.NoSuchProcess(pid)
        return real_process(pid) if pid is not None else real_process()
    monkeypatch.setattr(psutil, "pids", lambda: [88001])
    monkeypatch.setattr(psutil, "Process", Process)
    monkeypatch.setattr(co.os, "getsid", lambda pid: 5150 if (member or pid == 0) else 777)


def test_x10_an_unreadable_unclaimed_process_is_listed_never_silently_skipped(tmp_path, monkeypatch):
    _fake_table(monkeypatch, member=False)
    scan = _ops(tmp_path).owned_scan(sid=5150, not_before=0.0, roots=[], container_prefixes=(), deadline_s=2.0)
    assert scan["certain"] is True and [u["pid"] for u in scan["unreadable"]] == [88001]


def test_x10_an_unreadable_member_of_the_probe_session_leaves_the_scan_uncertain(tmp_path, monkeypatch):
    _fake_table(monkeypatch, member=True)
    scan = _ops(tmp_path).owned_scan(sid=5150, not_before=0.0, roots=[], container_prefixes=(), deadline_s=2.0)
    assert scan["certain"] is False and [u["pid"] for u in scan["unreadable"]] == [88001]


def test_x7_the_watcher_never_claims_the_drivers_ambient_shell_session(monkeypatch):
    """The sequencer launches the chain in the operator's shell session: that session is not ours. Ours = the driver and its
    descendants, plus the sessions LED by a descendant (the probes, `start_new_session=True`)."""
    import importlib
    bw = importlib.import_module("m1.bench_watch")
    SHELL, DRIVER, PROBE, CLIENT = 500, 600, 700, 701

    class P:
        def __init__(self, pid):
            self.pid = pid

        def children(self, recursive=False):
            return [P(PROBE), P(CLIENT)] if self.pid == DRIVER else []
    fake = SimpleNamespace(Process=P, Error=Exception)
    sids = {DRIVER: SHELL, PROBE: PROBE, CLIENT: PROBE}
    monkeypatch.setattr(bw.os, "getsid", lambda pid: sids[pid])
    pids, sessions = bw.BoxSampler(DRIVER, "/nonexistent", scrub=str)._ours(fake)
    assert pids == {DRIVER, PROBE, CLIENT}
    assert sessions == {PROBE}                       # never SHELL: an unrelated same-session process stays `foreign`


def test_x19_no_test_module_patches_the_guards_init_beside_the_hermetic_scan():
    """X19 (the cause of the broad-run failures): the conftest's hermetic scan replaces `ProcessGuard.__init__` with its own
    setattr / undo; a test that ALSO patches `__init__` through `monkeypatch` is undone after it and re-installs the hermetic
    wrapper for the rest of the run, so every later `real_process_scan` test silently runs on the family scan
    (`test_p585_...cannot_construct...`: `process_iter`'s cached objects never re-read the patched create_time;
    `test_real_rapid_fork...`: the family scan's documented blind spot for a setsid'd leak). Candidate 1's C157 fixture did
    exactly that; nothing but the conftest may patch it."""
    import re
    from pathlib import Path
    here = Path(__file__).parent
    offenders = []
    for f in sorted(here.rglob("*.py")):
        if f.name in ("conftest.py", "hermetic_scan.py", "p371_hermetic_scan.py") or f == Path(__file__):
            continue
        text = f.read_text(errors="replace")
        if re.search(r"ProcessGuard\s*,\s*[\"']__init__[\"']|ProcessGuard\.__init__\s*=", text):
            offenders.append(f.relative_to(here).as_posix())
    assert offenders == []


def test_x10_the_shared_environment_rule_matches_either_spelling_of_a_hermetic_root(tmp_path):
    """macOS: `/var/...` resolves to `/private/var/...`; the environment carries the spelling it was given."""
    from bench import proc_guard as pg
    real = tmp_path / "real-run"
    (real / "home").mkdir(parents=True)
    link = tmp_path / "link-run"
    link.symlink_to(real)
    by_link = SimpleNamespace(pid=1, environ=lambda: {"HOME": str(link / "home")})
    by_real = SimpleNamespace(pid=2, environ=lambda: {"HOME": str(real / "home")})
    other = SimpleNamespace(pid=3, environ=lambda: {"HOME": str(tmp_path / "elsewhere")})
    for root in (link, real):
        homes = pg.hermetic_homes([str(root)])
        assert pg.env_claim(by_link, homes) and pg.env_claim(by_real, homes) and not pg.env_claim(other, homes)


def test_x10_the_guard_and_the_chain_scan_share_one_ownership_rule():
    import inspect
    from bench import chain_ops as co
    from bench import proc_guard as pg
    src = inspect.getsource(co.ChainOps.owned_scan)
    for helper in ("session_claim", "env_claim", "path_claim"):
        assert f"pg.{helper}(" in src and helper in inspect.getsource(pg.ProcessGuard)


# ------------------------------------------------------------------------------------------------- X6 (tg1 Go, scope +)
@pytest.mark.parametrize("rc,kind", [(125, "spawn"), (126, "image"), (127, "image")])
def test_x6_tg1_go_dockers_own_failure_status_is_a_typed_grader_infrastructure_fault(rc, kind):
    """`docker run`'s own statuses (125: the daemon could not create / start the container; 126 / 127: the pinned image's
    command cannot run) are the harness's failure -> typed, regraded like tg2's."""
    from bench import structured_grade as sg
    from bench import token_turn_gate as tg
    with pytest.raises(tg.TransportAbort) as err:
        sg.parse_go("", rc, stderr="docker: Error response from daemon: x")
    assert tg.grader_infra_fault(err.value) and err.value.kind == kind


@pytest.mark.parametrize("stderr", ["Cannot connect to the Docker daemon", "Unable to find image",
                                    "--- FAIL: TestDB\n    db_test.go:9: Error response from daemon: pull access denied"])
def test_x6_tg1_go_test_output_naming_a_docker_fault_still_aborts_but_is_never_typed(stderr):
    """The container's stderr carries the agent's test output: a pattern there may abort (unchanged), never a regrade."""
    from bench import structured_grade as sg
    from bench import token_turn_gate as tg
    with pytest.raises(tg.TransportAbort, match="Docker infrastructure") as err:
        sg.parse_go("", 1, stderr=stderr)
    assert not tg.grader_infra_fault(err.value)
