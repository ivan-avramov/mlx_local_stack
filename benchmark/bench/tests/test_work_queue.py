"""A work-queue runner, so a finished job never means an idle worker.

WHY THIS EXISTS. Operator instruction: keep the worker box loaded at all times. That is
structurally impossible with hand-launched jobs, for the same reason AGENTS.md already records for
monitoring — "THE CADENCE MUST LIVE IN A DAEMON, NOT IN THE CONVERSATION". An agent only executes
when the operator sends a message, so every job completion is an idle gap until someone notices.
Measured 2026-08-14: generation finished at 07:43 and the box sat idle for hours with a queued,
unblocked job (the prealloc OFAT) waiting, because completion was treated as a reporting moment
rather than a trigger.

So the queue lives in a FILE, in git, and a runner on the box pulls the next entry the moment the
previous exits. Consequences that shaped the design:

  - **The queue file is the durable state.** It survives a reboot (the runner does not), and the
    operator can reorder or add entries without touching the runner.
  - **Each entry records its own outcome** (started/finished/failed + exit code) IN the queue file,
    so "what has this box actually done?" is answerable from one place — the question the
    scp-drift episode showed is otherwise unanswerable.
  - **A failing job must not stop the queue.** On a single-worker campaign an unattended stop costs
    hours; the runner records the failure and moves on.
  - **Entries are shell commands, not a DSL.** Everything worth queueing is already a committed CLI
    invocation (`run.py generate ...`), and inventing a job schema would just re-encode it.
"""
import json

import pytest

from bench import paths, workqueue


def _q(tmp_path, entries):
    p = tmp_path / "queue.json"
    p.write_text(json.dumps(entries, indent=1))
    return p


def test_runs_entries_in_order(tmp_path):
    ran = []
    q = _q(tmp_path, [{"name": "a", "cmd": "true"}, {"name": "b", "cmd": "true"}])
    workqueue.run(q, runner=lambda cmd: ran.append(cmd) or 0)
    assert ran == ["true", "true"]


def test_records_outcome_per_entry_in_the_queue_file(tmp_path):
    """'What has this box actually done?' must be answerable from the queue file alone."""
    q = _q(tmp_path, [{"name": "a", "cmd": "true"}])
    workqueue.run(q, runner=lambda cmd: 0)
    e = json.loads(q.read_text())[0]
    assert e["state"] == "done"
    assert e["exit_code"] == 0
    assert e["started_at"] and e["finished_at"]


def test_a_failing_job_does_not_stop_the_queue(tmp_path):
    """An unattended stop on a single-worker campaign costs hours."""
    ran = []

    def runner(cmd):
        ran.append(cmd)
        return 1 if cmd == "boom" else 0

    q = _q(tmp_path, [{"name": "a", "cmd": "boom"}, {"name": "b", "cmd": "ok"}])
    workqueue.run(q, runner=runner)
    entries = json.loads(q.read_text())
    assert ran == ["boom", "ok"], "the queue stopped at a failure"
    assert entries[0]["state"] == "failed" and entries[0]["exit_code"] == 1
    assert entries[1]["state"] == "done"


def test_already_done_entries_are_skipped_on_restart(tmp_path):
    """The runner does not survive a reboot; the queue does. Relaunching must resume, not redo —
    a redone generate is hours of worker time."""
    ran = []
    q = _q(tmp_path, [
        {"name": "a", "cmd": "first", "state": "done", "exit_code": 0},
        {"name": "b", "cmd": "second"},
    ])
    workqueue.run(q, runner=lambda cmd: ran.append(cmd) or 0)
    assert ran == ["second"]


def test_a_failed_entry_is_NOT_retried_automatically(tmp_path):
    """A job that failed once will usually fail again, and a retry loop on a single worker is how a
    box spends a night achieving nothing. Re-queueing is an explicit operator act."""
    ran = []
    q = _q(tmp_path, [{"name": "a", "cmd": "x", "state": "failed", "exit_code": 2}])
    workqueue.run(q, runner=lambda cmd: ran.append(cmd) or 0)
    assert ran == []


def test_entries_can_be_added_while_the_runner_is_between_jobs(tmp_path):
    """The queue file is re-read before each entry, so the operator can append work without
    restarting the runner."""
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}])
    calls = []

    def runner(cmd):
        calls.append(cmd)
        if cmd == "a":                     # append a new entry mid-run
            entries = json.loads(q.read_text())
            entries.append({"name": "b", "cmd": "b"})
            q.write_text(json.dumps(entries))
        return 0

    workqueue.run(q, runner=runner)
    assert calls == ["a", "b"], "queue was not re-read between entries"


def test_stops_cleanly_on_an_empty_queue(tmp_path):
    q = _q(tmp_path, [])
    assert workqueue.run(q, runner=lambda cmd: 0) == 0


def test_max_jobs_bounds_a_run(tmp_path):
    """A backstop so a malformed queue cannot spin forever."""
    ran = []
    q = _q(tmp_path, [{"name": str(i), "cmd": f"c{i}"} for i in range(5)])
    workqueue.run(q, runner=lambda cmd: ran.append(cmd) or 0, max_jobs=2)
    assert ran == ["c0", "c1"]


def test_malformed_entry_is_recorded_and_skipped(tmp_path):
    """Never crash the queue on a typo — record it so it is visible, and continue."""
    ran = []
    q = _q(tmp_path, [{"name": "bad"}, {"name": "good", "cmd": "ok"}])
    workqueue.run(q, runner=lambda cmd: ran.append(cmd) or 0)
    entries = json.loads(q.read_text())
    assert entries[0]["state"] == "failed"
    assert "cmd" in (entries[0].get("note") or "")
    assert ran == ["ok"]


def test_each_job_gets_its_own_output_log(tmp_path, monkeypatch):
    """A job's stdout/stderr must be CAPTURED, not discarded.

    Found immediately on first live use: the runner logged only START/DONE and an exit code, so a
    `generate` job's driver output -- per-chunk progress, ETAs, provenance CLEANED/RESTAMPED lines,
    and the reason for any failure -- went to /dev/null. An exit code alone cannot answer "why did
    that fail", and on a single-worker campaign re-running a job to see its output costs hours.
    """
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([{"name": "job one", "cmd": "echo hello; echo oops 1>&2"}]))
    workqueue.run(q, logdir=tmp_path)

    logs = sorted(tmp_path.glob("*.joblog"))
    assert logs, "no per-job log written"
    text = logs[0].read_text()
    assert "hello" in text and "oops" in text, "stdout and stderr must both be captured"
    entry = json.loads(q.read_text())[0]
    assert entry["log"] == logs[0].name, "the queue entry must point at its own log"


def test_job_log_name_is_filesystem_safe(tmp_path):
    """Job names are human-written and contain spaces, slashes and commas."""
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([{"name": "a/b c,d=e n=100", "cmd": "true"}]))
    workqueue.run(q, logdir=tmp_path)
    name = json.loads(q.read_text())[0]["log"]
    assert "/" not in name and " " not in name
    assert (tmp_path / name).exists()


# ---------------------------------------------- plan vs state: the file must not be both

def test_state_is_written_to_a_SEPARATE_file_and_the_plan_is_untouched(tmp_path):
    """The queue file is COMMITTED CONFIG. Writing runtime state into it makes it permanent drift on
    the worker box, means a reordered plan cannot be synced via git without colliding with state,
    and makes the plan un-editable from the driver. Found live 2026-08-14 by editing the driver's
    copy and discovering the runner reads the worker's, which had diverged.
    """
    plan = tmp_path / "plan.json"
    original = json.dumps([{"name": "a", "cmd": "true"}], indent=1)
    plan.write_text(original)
    state = tmp_path / "state.json"

    workqueue.run(plan, state_path=state, runner=lambda cmd: 0)

    assert plan.read_text() == original, "the committed plan was MODIFIED"
    st = json.loads(state.read_text())
    assert st["a"]["state"] == "done" and st["a"]["exit_code"] == 0


def test_state_is_keyed_by_NAME_so_the_plan_can_be_REORDERED(tmp_path):
    """Keying by index would silently mis-attribute state after a reorder — and reordering is the
    operator's main lever for getting data faster."""
    plan = tmp_path / "plan.json"
    state = tmp_path / "state.json"
    plan.write_text(json.dumps([{"name": "first", "cmd": "1"}, {"name": "second", "cmd": "2"}]))
    ran = []
    workqueue.run(plan, state_path=state, runner=lambda c: ran.append(c) or 0, max_jobs=1)
    assert ran == ["1"]

    # operator reorders the plan; 'first' is now last
    plan.write_text(json.dumps([{"name": "second", "cmd": "2"}, {"name": "first", "cmd": "1"}]))
    workqueue.run(plan, state_path=state, runner=lambda c: ran.append(c) or 0)
    assert ran == ["1", "2"], "reordering re-ran a completed job or skipped a pending one"


# ---------------------------------------------- operator control files: STOP / SKIP / PAUSE
#
# Checked BETWEEN queue items (never mid-item) -- a running job is never interrupted; the runner
# only consults these files at the same boundary it already re-reads the queue at. Each file is
# CONSUMED (deleted) once acted on, so the next launch starts fresh. Precedence when several are
# dropped at once: STOP > SKIP > PAUSE.


def test_STOP_stops_the_queue_before_the_next_item_and_is_consumed(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    ran = []

    def runner(cmd):
        ran.append(cmd)
        if cmd == "a":
            (control / "STOP").touch()
        return 0

    q = _q(tmp_path, [{"name": "a", "cmd": "a"}, {"name": "b", "cmd": "b"}])
    workqueue.run(q, runner=runner, control_dir=control)
    assert ran == ["a"], "STOP must take effect only between items, after 'a' finishes"
    assert not (control / "STOP").exists(), "STOP must be consumed so the next launch starts fresh"


def test_STOP_logs_how_many_items_remain(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    (control / "STOP").touch()
    logged = []
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}, {"name": "b", "cmd": "b"}])
    workqueue.run(q, runner=lambda c: 0, control_dir=control, log=logged.append)
    assert any("2" in m and "remain" in m for m in logged), logged


def test_STOP_present_before_the_first_item_prevents_any_item_from_running(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    (control / "STOP").touch()
    ran = []
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}])
    workqueue.run(q, runner=lambda c: ran.append(c) or 0, control_dir=control)
    assert ran == []


def test_SKIP_marks_the_next_pending_item_skipped_with_operator_reason(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    (control / "SKIP").touch()
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}, {"name": "b", "cmd": "b"}])
    ran = []
    workqueue.run(q, runner=lambda c: ran.append(c) or 0, control_dir=control)
    entries = json.loads(q.read_text())
    assert entries[0]["state"] == "skipped"
    assert entries[0]["note"] == "operator SKIP"
    assert ran == ["b"], "one SKIP file must skip exactly one item, then proceed to the next"


def test_SKIP_is_consumed_after_use(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    (control / "SKIP").touch()
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}])
    workqueue.run(q, runner=lambda c: 0, control_dir=control)
    assert not (control / "SKIP").exists()


def test_SKIP_records_into_the_state_file_when_state_path_is_used(tmp_path):
    """SKIP must record the same way the runner records every other outcome: into the SEPARATE
    state file when one is in use, leaving the committed plan untouched."""
    plan = tmp_path / "plan.json"
    original = json.dumps([{"name": "a", "cmd": "a"}, {"name": "b", "cmd": "b"}], indent=1)
    plan.write_text(original)
    state = tmp_path / "state.json"
    control = tmp_path / "control"
    control.mkdir()
    (control / "SKIP").touch()
    ran = []
    workqueue.run(plan, state_path=state, runner=lambda c: ran.append(c) or 0, control_dir=control)
    assert plan.read_text() == original, "the committed plan was modified"
    st = json.loads(state.read_text())
    assert st["a"]["state"] == "skipped" and st["a"]["note"] == "operator SKIP"
    assert ran == ["b"]


def test_SKIP_with_no_pending_items_is_a_no_op_but_still_consumed(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    (control / "SKIP").touch()
    q = _q(tmp_path, [])
    assert workqueue.run(q, runner=lambda c: 0, control_dir=control) == 0
    assert not (control / "SKIP").exists()


def test_PAUSE_blocks_between_items_polling_until_removed_then_resumes(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir()
    (control / "PAUSE").touch()
    calls = []

    def fake_sleep(secs):
        calls.append(secs)
        (control / "PAUSE").unlink()

    monkeypatch.setattr(workqueue.time, "sleep", fake_sleep)
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}])
    ran = []
    workqueue.run(q, runner=lambda c: ran.append(c) or 0, control_dir=control, poll_interval=0.01)
    assert ran == ["a"], "the item must still run once PAUSE is lifted"
    assert calls == [0.01], "poll interval must be injectable, not a hardcoded 30s sleep"


def test_PAUSE_logs_entering_and_leaving_the_paused_state(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir()
    (control / "PAUSE").touch()
    monkeypatch.setattr(workqueue.time, "sleep",
                         lambda secs: (control / "PAUSE").unlink(missing_ok=True))
    logged = []
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}])
    workqueue.run(q, runner=lambda c: 0, control_dir=control, poll_interval=0.01, log=logged.append)
    assert any("PAUSE" in m and "wait" in m.lower() for m in logged), logged
    assert any("PAUSE" in m and ("lift" in m.lower() or "resum" in m.lower()) for m in logged), logged


def test_PAUSE_is_rechecked_after_each_completed_item(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir()
    ran = []

    def runner(cmd):
        ran.append(cmd)
        if cmd == "a":
            (control / "PAUSE").touch()          # dropped mid-run, takes effect after 'a'
        return 0

    monkeypatch.setattr(workqueue.time, "sleep",
                         lambda secs: (control / "PAUSE").unlink(missing_ok=True))
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}, {"name": "b", "cmd": "b"}])
    workqueue.run(q, runner=runner, control_dir=control, poll_interval=0.01)
    assert ran == ["a", "b"]


def test_control_precedence_STOP_beats_SKIP_and_PAUSE(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    (control / "STOP").touch()
    (control / "SKIP").touch()
    (control / "PAUSE").touch()
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}, {"name": "b", "cmd": "b"}])
    ran = []
    workqueue.run(q, runner=lambda c: ran.append(c) or 0, control_dir=control)
    assert ran == []
    assert not (control / "STOP").exists()
    assert (control / "SKIP").exists(), "STOP must win outright; SKIP must not also be consumed"
    assert (control / "PAUSE").exists()


def test_control_precedence_SKIP_beats_PAUSE(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir()
    (control / "SKIP").touch()
    (control / "PAUSE").touch()
    monkeypatch.setattr(workqueue.time, "sleep",
                         lambda secs: (control / "PAUSE").unlink(missing_ok=True))
    q = _q(tmp_path, [{"name": "a", "cmd": "a"}, {"name": "b", "cmd": "b"}])
    ran = []
    workqueue.run(q, runner=lambda c: ran.append(c) or 0, control_dir=control, poll_interval=0.01)
    entries = json.loads(q.read_text())
    assert entries[0]["state"] == "skipped", "SKIP must be actioned before PAUSE is even consulted"
    assert ran == ["b"]


def test_control_dir_defaults_to_repo_benchmark_control(monkeypatch):
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    assert workqueue._control_dir() == paths.repo_root() / "benchmark" / "control"


def test_control_dir_honors_STACK_WORKDIR_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    assert workqueue._control_dir() == tmp_path / "control"


def test_inline_state_in_an_OLD_plan_is_migrated_not_re_run(tmp_path):
    """Backwards compatibility: plans already carry inline state from the first design. Those jobs
    must not be re-run — a redone generate is hours of worker time."""
    plan = tmp_path / "plan.json"
    state = tmp_path / "state.json"
    plan.write_text(json.dumps([
        {"name": "old-done", "cmd": "x", "state": "done", "exit_code": 0},
        {"name": "new", "cmd": "y"},
    ]))
    ran = []
    workqueue.run(plan, state_path=state, runner=lambda c: ran.append(c) or 0)
    assert ran == ["y"]
    assert json.loads(state.read_text())["old-done"]["state"] == "done"
