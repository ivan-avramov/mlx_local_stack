"""S27 (spec v1.4, section 4.1) -- blind test-writer, delivery 1: the byte positions the kill path records.

`terminate_client` records, under the lock that reads `requests_at_kill`, the ingested byte position of the events stream
(`ingested_offset_at_count`) and the file size (`events_size_at_count`); it keeps `signal_offset`; the gate records each step's
END offset; all persist in `termination` / the row.

Class of each test: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) exercises new behaviour.

Interface assumptions:
  F1  the gate's per-step END offsets are `gate.report()["step_end_offsets"]` (list of ints, the byte just past each
      `step_finish` line, in completion order) and so `row["gate"]["step_end_offsets"]`;
  F2  the count-time fields are keys of `termination` (spec 4.1 names them; the dict is what the row and an abort stamp carry);
  F3  no event line is a step end unless it is a `step_finish` that completed a request.
"""
from __future__ import annotations

import json
import time

import pytest

from bench import token_turn_gate as tg
from bench.tests.test_s27_fe_support import ScriptedGrader
from bench.tests.test_c147_cancel import linger_events, manifest, when
from bench.tests.test_opencode_v2_probe import tg1_probe as probe          # noqa: F401  (the fixture, as the tg1 modules import it)
from bench.tests.test_tg1_integration import tg_fixture
from bench.tests.test_token_turn_gate import event, usage


def feed_lines(events):
    gate = tg.TokenTurnGate(1)
    stream = tg.EventStream(gate)
    blob = b"".join(json.dumps(e).encode() + b"\n" for e in events)
    stream.feed(blob)
    ends, pos = [], 0
    for e in events:
        pos += len(json.dumps(e).encode()) + 1
        if e["type"] == "step_finish":
            ends.append(pos)
    return gate, stream, ends


def test_the_gate_records_each_steps_end_offset():
    """(c) one END offset per completed request: the position just past its `step_finish` line."""
    events = [event("step_start", "m1"), event("step_finish", "m1", tokens=usage(5, 100)),
              event("step_start", "m2"), event("tool_use", "m2", partID="t", tool="shell",
                                               state=dict(status="completed", input={"command": "ls"}, metadata={},
                                                          output="", title="shell", time=dict(start=1, end=2))),
              event("step_finish", "m2", tokens=usage(7, 200)), event("step_start", "m3")]
    gate, stream, ends = feed_lines(events)
    assert stream.step_end_offsets == ends and len(ends) == 2           # v2: the stream records them (persisted in `termination`)
    assert stream.offset > ends[-1]                      # the open third step is ingested but is not a step end


def test_an_open_step_has_no_end_offset_yet():
    """(b) a `step_start` without its `step_finish` is not a step end, so the count and the offsets agree."""
    gate, stream, ends = feed_lines([event("step_start", "m1"), event("step_finish", "m1", tokens=usage(5, 100)), event("step_start", "m2")])
    assert stream.step_end_offsets == ends and len(ends) == 1
    assert gate.report()["requests_completed"] == 1


def test_a_gate_with_no_completed_request_reports_no_offsets():
    gate, stream, _ = feed_lines([event("step_start", "m1")])
    assert stream.step_end_offsets == []


def test_the_kill_records_the_ingested_and_file_positions_under_the_same_count(probe, monkeypatch, tmp_path):
    """(a) Composed, the real runner and a lingering fake client, killed through the cooperative cancel (the same
    `terminate_client`): the record carries the count and, with it, where the stream was and how big the file was; the signal
    position follows. The baseline records the count and the signal position only."""
    ScriptedGrader().install(monkeypatch)                   # the clone has no grader interpreter: the grade is scripted
    f = tg_fixture(probe, monkeypatch, tmp_path)
    marker = linger_events(f, tmp_path)
    cancel = tmp_path / "leg.CANCEL"
    watcher = when(marker, lambda: cancel.write_text(""))
    started = time.time()
    with pytest.raises(SystemExit, match="cancelled by runner"):
        f["run"]("one", extra=["--cancel-file", str(cancel)])
    watcher.join(5)
    assert time.time() - started < 25
    term = manifest(f)["cancelled_item"]["termination"]
    assert term["requests_at_kill"] in (0, 1)               # the ingester's poll is asynchronous: both are legitimate
    for key in ("ingested_offset_at_count", "events_size_at_count", "signal_offset"):
        assert type(term.get(key)) is int, f"termination.{key} = {term.get(key)!r}"
    final_size = (tmp_path / "events.jsonl").stat().st_size
    # the stream only ever ingests what the file holds; the file only grows; the signal comes after the count was read
    assert 0 <= term["ingested_offset_at_count"] <= term["events_size_at_count"] <= term["signal_offset"] <= final_size
    if term["requests_at_kill"] == 1:                      # a counted request means the stream had consumed its lines
        assert term["ingested_offset_at_count"] > 0


def test_the_kill_record_marks_the_signal_as_never_delivered_when_none_was(probe, monkeypatch, tmp_path):
    """(c) `signal_offset` is None when no signal was delivered. A client that already exited needs no signal: the gate stops
    on its own, but the cancel path is the only one that always sends one, so this case is covered at the unit level of
    the baseline (`stream.signal_offset is None` => no tolerated abort errors) and checked here on the stream itself."""
    gate = tg.TokenTurnGate(1)
    stream = tg.EventStream(gate)
    assert stream.signal_offset is None
    assert tg.tolerated_abort_errors(stream) == set()
