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

from bench import workqueue


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
