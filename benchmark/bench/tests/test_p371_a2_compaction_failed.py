"""P371 phase 2b, plan 4 A2 / P370: `compaction_failed` (the model fails opencode's summary template twice) is a scaffold
OUTCOME, not transport corruption: a registered terminal shape from a pinned real-client fixture -> a scored strict-fail
row with `nonconv_kind: compaction_failed`, the chain continues. The shape is registered only for a configuration that
runs compaction (M64); under tg1 it still aborts. Compaction tokens: from receipts when present, else post hoc from the
export; always in the task totals."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import token_turn_gate as tg
from bench.tests.arm_entry import m64_main
from bench.tests.opencode_v2_mock import MockServer
from bench.tests.test_m64_arm_oc_contract import OcHarness, entry_parser
from bench.tests.test_opencode_v2_probe import MODEL, tg1_probe as probe          # noqa: F401  (fixture)
from bench.tests.test_p371_a3_oc import MockWorker
from bench.tests.test_tg1_integration import FROZEN, pinned_binary, tg_fixture     # noqa: F401  (fixture)

FIXTURE = json.loads((Path(__file__).parent / "fixtures/opencode_2.0.20_compaction_failed.json").read_text())
SCRIPT = {1: {"name": "write", "input": {"path": "solution.py", "content": "answer = 42\n"},
              "usage": {"prompt_tokens": 19500, "completion_tokens": 10, "total_tokens": 19510}},
          2: "badsummary", 3: "badsummary"}


def m64_arm(p):
    return ao.OpencodeArm(p, mode="m64", search=ao.OfflineTestSearchService())


def stream_of(arm, events=None):
    stream = arm.new_stream(tg.TokenTurnGate(3), lambda n: None)
    stream.feed("".join(json.dumps(e) + "\n" for e in (events if events is not None else FIXTURE["events"])).encode())
    return stream


def transcript(export=None):
    doc = copy.deepcopy(export if export is not None else FIXTURE["export"])
    return aa.Transcript(raw=json.dumps(doc), doc=doc)


# ---------------------------------------------------------------- the pinned shape
def test_the_fixture_is_the_real_2_0_20_failed_compaction_shape():
    assert FIXTURE["rc"] == "1" and "2.0.20" in FIXTURE["source"] and "$SCRATCH" in json.dumps(FIXTURE["export"])
    errors = [e for e in FIXTURE["events"] if e["type"] == "error"]
    assert errors and errors[0]["error"] == tg.COMPACTION_FAILED_ERROR == dict(
        type="compaction.failed", message="Compaction summary did not match the required template")
    kinds = [m["type"] for m in FIXTURE["export"]["messages"]]
    assert kinds == ["user", "assistant", "compaction", "idle"]
    comp = FIXTURE["export"]["messages"][2]
    assert comp["status"] == "failed" and comp["error"] == tg.COMPACTION_FAILED_ERROR
    assert comp["tokens"]["input"] == 200 and comp["tokens"]["output"] == 20          # two summary requests, one message
    assert FIXTURE["export"]["messages"][3] == dict(FIXTURE["export"]["messages"][3], outcome="failed")


def test_no_home_path_or_username_is_in_the_fixture():
    text = (Path(__file__).parent / "fixtures/opencode_2.0.20_compaction_failed.json").read_text()
    assert str(Path.home()) not in text and "/private/var" not in text and Path.home().name not in text


def test_compaction_failed_sits_after_the_client_cuts_and_before_budget_hit():
    order = tg.PRECEDENCE
    assert order.index("context_overflow") < order.index("client_inactivity") < order.index("compaction_failed") \
        < order.index("budget_hit")
    assert "compaction_failed" not in tg.KILL_OUTCOMES


def test_reconcile_registers_the_shape_only_when_asked_to():
    gate = tg.TokenTurnGate(3)
    stream = tg.EventStream(gate, lambda n: None)
    stream.feed("".join(json.dumps(e) + "\n" for e in FIXTURE["events"]).encode())
    out = tg.reconcile(stream, FIXTURE["export"], 1, compaction_failed=True)
    assert gate.primary == "compaction_failed" and out["primary"] == "compaction_failed" and out["trailing"] == "none"
    assert out["unmatched_export_messages"] == 0 and len(gate.request_usage) == 1
    again = tg.EventStream(tg.TokenTurnGate(3), lambda n: None)
    again.feed("".join(json.dumps(e) + "\n" for e in FIXTURE["events"]).encode())
    with pytest.raises(tg.TransportAbort, match="error event"):
        tg.reconcile(again, FIXTURE["export"], 1)
    with pytest.raises(tg.TransportAbort, match="error event"):
        tg.reconcile(stream_of(ao.OpencodeArm(None, mode="tg1")), FIXTURE["export"], 1)


def mutate(path, value):
    doc = copy.deepcopy(FIXTURE["export"])
    target = doc
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return doc


@pytest.mark.parametrize("name", [
    "rc0", "other_message", "two_errors", "completed_status", "other_error_type", "no_idle", "idle_outcome",
    "assistant_after", "tokens_missing", "no_compaction_message", "inactivity_too"])
def test_anything_but_the_exact_shape_still_aborts(name):
    export, events, rc = copy.deepcopy(FIXTURE["export"]), copy.deepcopy(FIXTURE["events"]), 1
    if name == "rc0":
        rc = 0
    elif name == "other_message":
        events[-1]["error"]["message"] = "Compaction summary was empty"
    elif name == "two_errors":
        events.append(copy.deepcopy(events[-1]))
    elif name == "completed_status":
        export["messages"][2]["status"] = "completed"
    elif name == "other_error_type":
        export["messages"][2]["error"] = dict(type="compaction.crashed", message="x")
    elif name == "no_idle":
        export["messages"].pop()
    elif name == "idle_outcome":
        export["messages"][3]["outcome"] = "completed"
    elif name == "assistant_after":
        export["messages"].insert(3, copy.deepcopy(export["messages"][1]))
        export["messages"][3]["id"] = "msg_after"
    elif name == "tokens_missing":
        export["messages"][2]["tokens"] = None
    elif name == "no_compaction_message":
        del export["messages"][2]
    elif name == "inactivity_too":
        events[-1]["error"] = tg.INACTIVITY_ERROR
    gate = tg.TokenTurnGate(3)
    stream = tg.EventStream(gate, lambda n: None)
    stream.feed("".join(json.dumps(e) + "\n" for e in events).encode())
    if name == "tokens_missing":                     # a failed compaction whose tokens cannot be counted is not accounted
        arm = m64_arm(None)
        with pytest.raises(tg.TransportAbort, match="compaction usage"):
            arm.reconcile(stream_of(arm), aa.Transcript(raw="", doc=export), None, rc, None)
        return
    with pytest.raises(tg.TransportAbort):
        tg.reconcile(stream, export, rc, compaction_failed=True)


# ---------------------------------------------------------------- the adapter registers it for M64 only
def test_the_adapter_declares_the_scaffold_outcome_for_m64_only():
    assert aa.ArmAdapter.scaffold_outcomes == ()
    assert ao.OpencodeArm(None, mode="m64").scaffold_outcomes == ("compaction_failed",)
    assert ao.OpencodeArm(None, mode="tg1").scaffold_outcomes == ()


def test_m64_reconcile_returns_the_outcome_the_failed_compactions_tokens_and_an_error_terminal():
    arm = m64_arm(None)
    stream = stream_of(arm)
    got = arm.reconcile(stream, transcript(), None, 1, None)
    assert got.outcome == "compaction_failed" and stream.gate.primary == "compaction_failed"
    assert got.compaction_count == 1 and got.compaction_completion_tokens == 20
    assert got.compaction[0]["usage"] == aa.Usage(200, 0, 0, 20, 0).as_dict()
    events = arm.events(stream)
    assert [e.kind for e in events].count("compaction") == 1 and events[-1] == aa.NormalizedEvent.terminal("error")


def test_tg1_reconcile_of_the_same_session_aborts_as_before():
    arm = ao.OpencodeArm(None, mode="tg1")
    with pytest.raises(tg.TransportAbort, match="error event"):
        arm.reconcile(stream_of(arm), transcript(), None, 1, None)


def test_a_failed_compaction_is_not_a_transport_incident():
    arm = m64_arm(None)
    stream = stream_of(arm)
    arm.reconcile(stream, transcript(), None, 1, None)                       # registered: no TransportFailure raised
    stream2 = stream_of(arm, FIXTURE["events"][:-1] + [dict(FIXTURE["events"][-1], error=dict(
        type="compaction.failed", message="something else"))])
    with pytest.raises(tg.TransportAbort) as exc:
        arm.reconcile(stream2, transcript(), None, 1, None)
    assert not isinstance(exc.value, ao.TransportFailure)


# ---------------------------------------------------------------- end to end through the core on the real client
def run_two(probe, pinned_binary, monkeypatch, tmp_path, script, *, items="one", receipts=None):
    (Path(os.environ["STACK_WORKDIR"]) / "m62/inject").mkdir(parents=True, exist_ok=True)
    h = OcHarness(probe, pinned_binary, monkeypatch, tmp_path)
    with MockServer(script) as mock:
        f, sub = h._setup(mock, h.reduced_window)
        out = sub / "rows.jsonl"
        argv = h._argv(sub, out, [])
        argv[argv.index("--items") + 1] = items
        monkeypatch.setattr(sys, "argv", argv)
        a = entry_parser().parse_args(argv[1:])
        adapter = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())
        worker = MockWorker(mock, script) if receipts else None
        abort = None
        try:
            m64_main(probe, adapter, a, receipts_policy="required" if receipts else "absent", receipt_source=worker)
        except SystemExit as exc:
            abort = exc if exc.code not in (0, None) else None
        rows = [json.loads(x) for x in out.read_text().splitlines()] if out.exists() else []
        manifest = json.loads(out.with_suffix(".manifest.json").read_text())
        return dict(rows=rows, abort=abort, mock=mock, manifest=manifest, worker=worker)


def test_a_failed_compaction_is_a_scored_strict_fail_row_and_the_probe_continues(
        probe, pinned_binary, monkeypatch, tmp_path):
    got = run_two(probe, pinned_binary, monkeypatch, tmp_path, SCRIPT, items="one,two")
    assert got["abort"] is None and "transport_abort" not in got["manifest"]
    first, second = got["rows"]
    assert first["id"] == "python/one" and first["nonconv_kind"] == "compaction_failed"
    assert first["converged"] is False and "compaction_failed" in first["nonconv_flags"] and first["opencode_rc"] == 1
    assert first["gate"]["requests_completed"] == 1 and first["stop_reason"] == "completed"
    assert second["id"] == "python/two" and second["nonconv_kind"] is None and second["converged"] is True
    assert len([c for c in got["mock"].chats[:3]]) == 3          # the task request and TWO summary requests


def test_failed_compaction_tokens_are_post_hoc_from_the_export_and_in_the_task_totals(
        probe, pinned_binary, monkeypatch, tmp_path):
    first = run_two(probe, pinned_binary, monkeypatch, tmp_path, SCRIPT)["rows"][0]
    c = first["compaction"]
    assert c["count"] == 1 and c["completion_tokens"] == 20 and c["accounting"] == "post_hoc"
    assert c["receipts"] == 1 and c["accounting_complete"] is True
    t = first["task_tokens"]
    assert t["accounting"] == "client" and t["receipts"] is None
    assert t["gate_completion_tokens"] == 10 and t["compaction_completion_tokens"] == 20 and t["completion_tokens"] == 30
    assert first["token_accounting"] == "client"


def test_failed_compaction_tokens_come_from_the_receipts_when_present(probe, pinned_binary, monkeypatch, tmp_path):
    got = run_two(probe, pinned_binary, monkeypatch, tmp_path, SCRIPT, receipts=True)
    assert got["abort"] is None, got["abort"]
    (row,) = got["rows"]
    assert row["nonconv_kind"] == "compaction_failed" and row["token_accounting"] == "receipts"
    c = row["compaction"]
    assert c["accounting"] == "receipts" and c["completion_tokens"] == 20 and c["export_completion_tokens"] == 20
    receipts = row["task_tokens"]["receipts"]
    assert receipts["by_class"]["compaction"]["requests"] == 2 and receipts["requests"] == 3
    assert row["task_tokens"]["compaction_completion_tokens"] == 20 and row["task_tokens"]["gate_completion_tokens"] == 10


def test_a_receipt_set_that_has_one_summary_request_for_a_failed_compaction_aborts(
        probe, pinned_binary, monkeypatch, tmp_path):
    (Path(os.environ["STACK_WORKDIR"]) / "m62/inject").mkdir(parents=True, exist_ok=True)
    h = OcHarness(probe, pinned_binary, monkeypatch, tmp_path)
    with MockServer(SCRIPT) as mock:
        f, sub = h._setup(mock, h.reduced_window)
        out = sub / "rows.jsonl"
        argv = h._argv(sub, out, [])
        monkeypatch.setattr(sys, "argv", argv)
        a = entry_parser().parse_args(argv[1:])
        worker = MockWorker(mock, SCRIPT, mutate=lambda s: (s._receipts.pop(), setattr(s, "_seq", s._seq - 1)))
        adapter = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())
        with pytest.raises(SystemExit, match="REFUSED.*3 requests but only 2 receipts"):
            m64_main(probe, adapter, a, receipts_policy="required", receipt_source=worker)
        assert not out.exists()


# ---------------------------------------------------------------- tg1 through the core still aborts
def test_tg1_through_the_core_aborts_on_the_failed_compaction_shape(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(dict(e, sessionID="s1", **(
        {"part": dict(e["part"], sessionID="s1")} if "part" in e else {}))) + "\n" for e in FIXTURE["events"]))
    (tmp_path / "rc").write_text("1")
    f["export"].write_text(json.dumps(FIXTURE["export"]))
    with pytest.raises(SystemExit, match="error event"):
        f["run"]()
    assert not f["out"].exists()
