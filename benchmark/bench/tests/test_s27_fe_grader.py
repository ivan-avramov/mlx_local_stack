"""S27 (spec v1.4, sections 5.1, 5.8, 6, acceptance 10.1) -- blind test-writer, delivery 1: grader infrastructure faults and the
abort path, driven through the real `p.main()` / `run_item` of the tg1 entry with a fake client and a scripted grade
(`test_s27_fe_support.ScriptedGrader`, assumption G1: an infrastructure fault is `GradeOutcome(outcome="infrastructure")`).

Class of each test: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) exercises new behaviour.

Interface assumptions:
  G1  see `test_s27_fe_support`;
  G2  a final-grade fault budget of three grades in all (the first, plus up to 2 retries); the third fault ends the probe with
      `SystemExit` and a manifest `transport_abort` whose `cause` is `"grader_infra"` (spec 5.8), carrying the gate report and
      the item's evidence files; no row is written (the chain turns that stamp into the `grade_fault` DNF);
  G3  an interim grade infrastructure fault ends the probe the same way (`cause: "grader_infra"`), before any outcome exists;
  G4  C365: the abort path records `grade_cancelled` somewhere in the stamp's `termination` (text search, the key is
      `grade_cancelled` per spec 6), and the join is bounded by `arm_runner.GRACEFUL_CLIENT_S` read at call time (else by a
      value not above 15 s: the test allows 20 s);
  G5  one generation == one line of the fake client's `calls` file.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from bench import arm_runner as runner
from bench import proc_guard as pg
from bench.tests.test_opencode_v2_probe import tg1_probe as probe          # noqa: F401  (fixture)
from bench.tests.test_s27_fe_support import ScriptedGrader, infra, model
from bench.tests.test_tg1_integration import tg_fixture
from bench.tests.test_token_turn_gate import event, usage


def run_ok(f, **kw):
    assert f["run"]("one", **kw) == 0
    return [json.loads(x) for x in f["out"].read_text().splitlines()]


def generations(f):
    return len(f["calls"].read_text().splitlines())


def stamp_of(f):
    return json.loads(f["mp"].read_text())["transport_abort"]


# ------------------------------------------------------------------------------------------------ the final grade (5.1)
def test_two_final_infrastructure_faults_then_a_pass_is_accepted_with_one_generation_and_one_snapshot(probe, monkeypatch, tmp_path):
    """(a) The baseline scores the first infrastructure result as a model outcome (a strict fail from a grade that never
    measured the tree); the spec regrades inside the probe, on the same snapshot, never regenerating."""
    grader = ScriptedGrader(final_script=[infra(), infra(), model(0)]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    (row,) = run_ok(f)
    assert row["passed"] is True and row["nonconv_kind"] is None
    assert len(grader.finals) == 3, grader.calls
    assert generations(f) == 1                                           # no regeneration
    snaps = grader.final_snaps
    assert snaps[0] is snaps[1] is snaps[2], "the final snapshot is taken once and kept for the whole item"
    assert "transport_abort" not in json.loads(f["mp"].read_text())


def test_one_final_infrastructure_fault_then_a_fail_is_the_models_scored_fail(probe, monkeypatch, tmp_path):
    """(c) A regraded model outcome is the outcome, whatever it is."""
    grader = ScriptedGrader(final_script=[infra(), model(2)]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    (row,) = run_ok(f)
    assert row["passed"] is False and len(grader.finals) == 2 and generations(f) == 1


def test_three_final_infrastructure_faults_end_the_item_with_the_grader_infra_stamp_and_the_generation_evidence(probe, monkeypatch, tmp_path):
    """(a) Only the third fault writes the stamp; no row; the generation evidence (gate report, evidence files) persists."""
    grader = ScriptedGrader(final_script=[infra(), infra(), infra()]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        f["run"]("one")
    assert len(grader.finals) == 3 and generations(f) == 1
    assert not f["out"].exists() or f["out"].read_text() == ""            # a DNF, not a row
    stamp = stamp_of(f)
    assert stamp["cause"] == "grader_infra"
    # (the gate report is a P426-mode stamp field: this flat tg1 entry carries the item's evidence files instead; the probe's
    # abort stamp keeps them with their sha256 so that the generation is not lost)
    files = stamp["evidence"]["files"]
    assert {"events", "export"} <= set(files) and all(files[k]["sha256"] for k in ("events", "export"))
    assert stamp["cleanup_status"]["uncertain"] is False


@pytest.mark.parametrize("what, final", [
    ("a grader timeout", model(3, outcome="timeout")),
    ("a grader memory kill", model(3, mem_kill=True, outcome="mem_kill")),
    ("an out-of-memory kill", model(3, oom=True, outcome="oom")),
])
def test_a_grader_timeout_or_resource_kill_is_the_items_outcome_and_is_never_regraded(probe, monkeypatch, tmp_path, what, final):
    """(b) A model outcome (timeout / mem_kill / oom) is never a fault: exactly one final grade, the row is scored."""
    grader = ScriptedGrader(final_script=[final]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    (row,) = run_ok(f)
    assert len(grader.finals) == 1, what
    assert row["passed"] is False
    assert row["grader_mem_kill"] is final.resources["grader_mem_kill"]
    assert row["grader_oom"] is final.resources["grader_oom"]


def test_a_tampered_final_tree_is_the_outcome_and_is_never_regraded(probe, monkeypatch, tmp_path):
    """(b)"""
    from bench.corpus import GradeOutcome
    tampered = GradeOutcome(failing=None, leaves=(), tampered=True, outcome="model", resources=dict(grader_mem_kill=False, grader_oom=False),
                            phases=(dict(seq=0, boundary=0, final=True, outcome="tampered"),), reports={})
    grader = ScriptedGrader(final_script=[tampered]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    (row,) = run_ok(f)
    assert len(grader.finals) == 1 and row["test_modified"] is True and row["passed"] is False


# ------------------------------------------------------------------------------------------------ the interim grade (5.1, 5.2)
def test_an_interim_grader_infrastructure_fault_while_the_client_generates_ends_the_probe_with_the_typed_stamp(probe, monkeypatch, tmp_path):
    """(a) v3 (X3): the fault lands WHILE THE CLIENT IS STILL GENERATING (a lingering fake client): a pre-outcome fault: no row; the
    stamp is typed so that the chain reruns the SAME item once (5.2 / 5.8). The baseline takes it as a model grade."""
    from bench.tests.test_c147_cancel import linger_events
    grader = ScriptedGrader(script=[infra()], final_script=[model(0)]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    linger_events(f, tmp_path)                                  # one finished request, one open: the client lingers 30 s
    started = time.monotonic()
    with pytest.raises(SystemExit):
        f["run"]("one")
    assert time.monotonic() - started < 25, "the fault must end the item without waiting for the lingering client"
    assert grader.interims, "the concurrent grader must have run for this test to mean anything"
    assert grader.finals == [], "no outcome: the final grade never ran"
    assert stamp_of(f)["cause"] == "grader_infra"
    assert not f["out"].exists() or f["out"].read_text() == ""


def test_an_interim_grader_fault_first_seen_after_the_client_exited_never_costs_the_finished_generation(probe, monkeypatch, tmp_path):
    """(a) v3 (X3): the interim grade is still running when the client exits and only then fails with an infrastructure fault:
    the generation is finished, so nothing reruns: the final grade decides, the interim fault is recorded. Candidate 1 aborted
    here and the chain would regenerate (checked by inspection of the fix diff)."""
    finishing = threading.Event()
    real_finish = runner.GradeWorker.finish

    def finish(self):                                           # the client has exited and the drain is done: only now fail
        finishing.set()
        return real_finish(self)
    monkeypatch.setattr(runner.GradeWorker, "finish", finish)

    def late_fault(final):
        assert finishing.wait(20), "the probe never reached the terminal grading phase"
        raise infra()
    grader = ScriptedGrader(script=[late_fault], final_script=[model(0)]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    (row,) = run_ok(f)
    assert row["passed"] is True and len(grader.finals) == 1 and generations(f) == 1
    assert row["termination"].get("interim_grade_fault"), "the interim fault is recorded"
    assert "transport_abort" not in json.loads(f["mp"].read_text())


def test_agent_controlled_output_that_looks_like_an_infrastructure_fault_is_never_one(probe, monkeypatch, tmp_path):
    """(b) v3 (X6): a grade that fails with a plain transport abort whose text embeds an agent program's output ("Connection
    refused", "Cannot connect to the Docker daemon") is not a grader infrastructure fault: one grade, no regrade, no
    `grader_infra` stamp (the substring matching of candidate 1 would have regraded x3 and turned a real failure into a DNF)."""
    from bench.token_turn_gate import TransportAbort
    embedded = TransportAbort("tg1 go: test output: dial tcp 127.0.0.1:1: Connection refused; Cannot connect to the Docker daemon; "
                              "docker command failed")
    grader = ScriptedGrader(final_script=[embedded, model(0)]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        f["run"]("one")
    assert len(grader.finals) == 1, "agent output must never be regraded as infrastructure"
    assert stamp_of(f).get("cause") != "grader_infra"
    assert generations(f) == 1


def test_a_grade_that_returns_a_model_outcome_whose_report_names_a_docker_fault_is_just_the_outcome(probe, monkeypatch, tmp_path):
    """(b) v3 (X6): a returned graded result is never inspected for fault text."""
    grader = ScriptedGrader(final_script=[model(2, outcome="Cannot connect to the Docker daemon")]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    (row,) = run_ok(f)
    assert len(grader.finals) == 1 and row["passed"] is False


# ------------------------------------------------------------------------------------------------ C365: abort vs an in-flight grade (6)
def slow_grade_world(monkeypatch, tmp_path, probe, *, block_s, release_on_kill=True):
    """An interim grade that blocks (the slow grader); a malformed complete event line is the primary exception, so the abort
    path runs while the grade is in flight."""
    released = threading.Event()
    ended = []

    def slow(final):
        released.wait(block_s)
        ended.append(time.monotonic())
        raise RuntimeError("the killed grader's transport failed")        # what a grade killed mid-run looks like
    grader = ScriptedGrader(script=[slow]).install(monkeypatch)
    real_kill_role = pg.ProcessGuard.kill_role
    kills = []

    def kill_role(self, role=None):
        if role == "grader":
            kills.append(time.monotonic())
            if release_on_kill:
                released.set()                                             # killing the grader frees the blocked grade
        return real_kill_role(self, role)
    monkeypatch.setattr(pg.ProcessGuard, "kill_role", kill_role)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    lines = [event("step_start", "m1"), event("step_finish", "m1", tokens=usage(10, 100)), event("step_start", "m2")]
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in lines) + "{ not json }\n")
    return f, grader, released, kills, ended


def test_c365_a_grade_that_fails_after_the_abort_began_never_replaces_the_original_exception(probe, monkeypatch, tmp_path):
    """(a) The primary exception (the malformed event line) propagates with its cleanup record; the grade killed by the abort
    is recorded `grade_cancelled`, never raised as `grading worker failed`."""
    f, grader, released, kills, ended = slow_grade_world(monkeypatch, tmp_path, probe, block_s=20)
    try:
        started = time.monotonic()
        with pytest.raises(SystemExit) as exc:
            f["run"]("one")
        assert time.monotonic() - started < 18
    finally:
        released.set()
    assert grader.entered.is_set(), "the grade must have been in flight when the abort began"
    assert kills, "the abort path must kill the grader role"
    stamp = stamp_of(f)
    assert "malformed complete event line" in stamp["error"], stamp["error"]
    assert "grading worker failed" not in stamp["error"] and "grading worker failed" not in str(exc.value)
    assert "grade_cancelled" in json.dumps(stamp.get("termination")), stamp.get("termination")
    assert stamp["cleanup_status"]["completed"] is True


def test_c365_the_abort_joins_a_grader_that_ignores_the_kill_only_for_a_bounded_time(probe, monkeypatch, tmp_path):
    """(a) A grade that is not freed by the kill (a wedged grader): the abort path's join is bounded (GRACEFUL_CLIENT_S scale),
    not the grader's own multi-minute timeout."""
    monkeypatch.setattr(runner, "GRACEFUL_CLIENT_S", 1)
    if hasattr(runner, "ABORT_GRADE_JOIN_S"):                  # v2: the candidate's bound, computed at import
        monkeypatch.setattr(runner, "ABORT_GRADE_JOIN_S", 1)
    f, grader, released, kills, ended = slow_grade_world(monkeypatch, tmp_path, probe, block_s=25, release_on_kill=False)
    started = time.monotonic()
    try:
        with pytest.raises(SystemExit):
            f["run"]("one")
        elapsed = time.monotonic() - started
    finally:
        released.set()
    assert elapsed < 20, f"the abort path waited {elapsed:.0f} s for a grader that the kill did not free"
    assert "malformed complete event line" in stamp_of(f)["error"]


def test_a_grade_failure_stored_before_any_abort_is_still_a_fault(probe, monkeypatch, tmp_path):
    """(b) 'a failure stored before the mark stays a fault': with no primary exception in flight, a grader that raises is
    the abort it always was (the unchanged `test_harness_grade_failure_aborts` rule for the concurrent grader)."""
    def boom(final):
        raise RuntimeError("grader crashed")
    ScriptedGrader(script=[boom]).install(monkeypatch)
    f = tg_fixture(probe, monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        f["run"]("one")
    assert "grading worker failed" in stamp_of(f)["error"] or "grader crashed" in stamp_of(f)["error"]
