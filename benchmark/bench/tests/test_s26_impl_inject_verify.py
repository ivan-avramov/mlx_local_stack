"""S26 erratum 2 (implementer tests): `m62/inject_verify.py`'s alloc rule counts only EXECUTED shell calls carrying `bytearray(`
(a call the tool-bounds plugin rejected — `state.status` "error" and `state.metadata.providerCall.executed` false — is excluded)
and requires exactly one, whose part id equals the kill's `tool_call_id`. Fixture: the recorded java alloc row's shape
(`.fe-material/java-alloc-row-shape.md`: a rejected `background: true` call, then the executed retry, one kill linked to the
retry) over the real-shaped tg2 inject row of `test_m76_b4b1_impl_wave2._v2_stall_row`."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2]
TG2 = "opencode-v2-web-tg2"
ALLOC_CMD = "python3 -c \"import time; b = bytearray(1024 * 1024 * 1024); time.sleep(90)\""
RSS = 1087275008
PER_PROCESS = 1 << 30


def _inject_verify():
    spec = importlib.util.spec_from_file_location("s26_impl_inject_verify", BENCH / "m62" / "inject_verify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


IV = _inject_verify()


def ev(kind, mid, **part):
    return dict(type=kind, sessionID="s1", part=dict(messageID=mid, **part))


def rejected_call(part_id="prt_rejected"):
    state = dict(status="error", error="M62_TOOL_BOUND: shell background must be false",
                 input={"background": True, "command": ALLOC_CMD}, time=dict(start=1000, end=1001),
                 metadata=dict(providerCall=dict(executed=False), providerResult=dict(executed=False)))
    return ev("tool_use", "m1", id=part_id, tool="shell", type="tool", state=state)


def executed_call(part_id="prt_retry", mid="m2"):
    state = dict(status="completed", input={"command": ALLOC_CMD}, output="Killed", time=dict(start=2000, end=3000),
                 metadata=dict(exit=137, metadata=dict(exit=137)))
    return ev("tool_use", mid, id=part_id, tool="shell", type="tool", state=state)


def recorded_events(first=None, second=None):
    """step 1 (request 1): the rejected call; step 2 (request 2): the executed retry, killed; steps 3-4 continue."""
    return [ev("step_start", "m1", id="s1"), first or rejected_call(), ev("step_finish", "m1", id="f1"),
            ev("step_start", "m2", id="s2"), second or executed_call(), ev("step_finish", "m2", id="f2"),
            ev("step_start", "m3", id="s3"), ev("step_finish", "m3", id="f3"),
            ev("step_start", "m4", id="s4"), ev("step_finish", "m4", id="f4")]


def alloc_row(tmp_path, events, *, kill_id="prt_retry"):
    from bench.tests.test_m76_b4b1_impl_wave2 import _v2_stall_row
    row, manifest = _v2_stall_row(tmp_path / "arts")
    events_path = Path(row["events_path"])
    events_path.write_text("".join(json.dumps(e) + "\n" for e in events))
    row["evidence_sha256"]["events"] = hashlib.sha256(events_path.read_bytes()).hexdigest()
    label = f"{TG2}-inject:alloc"
    row["scaffold"] = manifest["runtime"]["scaffold"] = label
    manifest["runtime"]["inject"] = dict(kind="alloc", policy=dict(gate={}, hygiene=dict(per_process=PER_PROCESS)))
    row["gate"] = dict(row["gate"], stop_reason=None, requests_completed=4)
    row["termination"] = dict(reason=None, killed=[])
    row["mem_kills"] = [dict(role="model", rss=RSS, argv=["python", "-c", "import time; b = bytearray(1024 * 1024 * 1024); "
                                                                          "time.sleep(90)"],
                             tool_call_id=kill_id, carrying_request=2, completed_boundary_at_kill=1)]
    return row, manifest


def verdict(tmp_path, events, **kw):
    row, manifest = alloc_row(tmp_path, events, **kw)
    return IV.verify_row("alloc", row, manifest, tmp_path, scaffold=TG2)[0]


def test_the_recorded_java_alloc_row_passes(tmp_path):
    """[FIX] red on the baseline (`FAIL:no_shell_part`: it counted the rejected call): the rejected call never ran, the retry
    is the one executed marker call and the kill names it."""
    assert verdict(tmp_path, recorded_events()) == "PASS"


def test_the_retry_not_linked_to_the_kill_is_a_tool_call_id_fail(tmp_path):
    assert verdict(tmp_path, recorded_events(), kill_id="prt_other") == "FAIL:tool_call_id"


def test_the_kill_linked_to_the_rejected_call_is_a_tool_call_id_fail(tmp_path):
    assert verdict(tmp_path, recorded_events(), kill_id="prt_rejected") == "FAIL:tool_call_id"


def test_two_executed_marker_calls_are_no_shell_part(tmp_path):
    assert verdict(tmp_path, recorded_events(first=executed_call("prt_first", mid="m1"))) == "FAIL:no_shell_part"


@pytest.mark.parametrize("edit", ["executed_missing", "executed_true", "status_completed"])
def test_an_error_call_counts_unless_it_provably_never_ran(tmp_path, edit):
    """Only `status: error` AND `providerCall.executed is False` excludes a call; anything less still counts (two calls)."""
    first = rejected_call()
    state = first["part"]["state"]
    if edit == "executed_missing":
        state["metadata"] = {}
    elif edit == "executed_true":
        state["metadata"]["providerCall"]["executed"] = True
    else:
        state["status"] = "completed"
    assert verdict(tmp_path, recorded_events(first=first)) == "FAIL:no_shell_part"


def test_only_the_rejected_call_and_no_executed_one_is_no_shell_part(tmp_path):
    events = [e for e in recorded_events() if e["part"].get("id") != "prt_retry"]
    assert verdict(tmp_path, events) == "FAIL:no_shell_part"


def test_never_executed_reads_the_recorded_fields_only():
    assert IV.never_executed(rejected_call()["part"]["state"]) is True
    assert IV.never_executed(executed_call()["part"]["state"]) is False
    for state in (None, {}, dict(status="error"), dict(status="error", metadata=dict(providerCall=dict(executed=0))),
                  dict(status="error", metadata=dict(providerCall=None))):
        assert IV.never_executed(state) is False


def test_the_other_kinds_are_unchanged(tmp_path):
    """The loop / stall rules do not read the executed flag (every other rule unchanged)."""
    row, manifest = alloc_row(tmp_path, recorded_events())
    for kind in ("loop", "stall"):
        r, m = copy.deepcopy(row), copy.deepcopy(manifest)
        r["scaffold"] = m["runtime"]["scaffold"] = f"{TG2}-inject:{kind}"
        m["runtime"]["inject"]["kind"] = kind
        assert IV.verify_row(kind, r, m, tmp_path, scaffold=TG2)[0] == "not_observed"
