"""M62 V1: passive accounting and terminal contracts, without inference."""

import json
import pytest
from bench import token_turn_gate as tg


def usage(output=1, input=10, read=0, write=0):
    return dict(output=output, reasoning=0, input=input, cache=dict(read=read, write=write))


def event(kind, mid="m1", **kw):
    return dict(
        type=kind,
        sessionID="s1",
        part=dict(id=kw.get("partID", kind + mid), messageID=mid, **kw),
    )


def tool_state(inputs=None, status="completed"):
    return dict(status=status, input={} if inputs is None else inputs,
                metadata={}, time=dict(start=1, end=2),
                **(dict(output="", title="shell") if status == "completed" else dict(error="failed")))


def request(stream, mid="m1", output=1, calls=()):
    stream.accept(event("step_start", mid))
    for i, call in enumerate(calls):
        stream.accept(
            event(
                "tool_use",
                mid,
                partID=f"{mid}-{i}",
                tool="shell",
                state=tool_state(call),
            )
        )
    stream.accept(event("step_finish", mid, tokens=usage(output)))


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("output", 81920, "stalled"),
        ("requests", 40, "stalled"),
        ("calls", 8, "looping"),
        ("total_output", 327680, "hard_ceiling"),
        ("total_requests", 150, "hard_ceiling"),
    ],
)
def test_exact_thresholds(field, value, reason):
    gate = tg.TokenTurnGate(10)
    if field.startswith("total"):
        gate.pending.add(1000)
    if field in ("output", "total_output"):
        gate.complete("a", usage(value - 1))
        assert gate.stop_reason is None
        gate.complete("b", usage(1))
    elif field in ("requests", "total_requests"):
        for i in range(value - 1):
            gate.complete(str(i), usage(0))
        assert gate.stop_reason is None
        gate.complete("last", usage(0))
    else:
        for i in range(value - 1):
            gate.tool("shell", {"command": "same"})
        gate.complete("a", usage(0))
        assert gate.stop_reason is None
        gate.tool("shell", {"command": "same"})
        gate.complete("b", usage(0))
    assert gate.stop_reason == reason


def test_precedence_sticky_boundary_reset_and_backlog():
    g = tg.TokenTurnGate(10)
    g.pending.add(1)
    g.complete("a", usage(81920))
    g.complete("b", usage(30))
    assert g.stop_reason is None
    g.grade(1, 9)
    assert (g.no_progress_tokens, g.no_progress_requests) == (30, 1)
    g.pending.add(3)
    g.complete("c", usage(81920))
    g.complete("d", usage(40))
    g.grade(3, 9)
    assert g.stop_reason == "stalled"
    g.grade(4, 0)
    assert g.stop_reason == "stalled"
    assert g.report()["decision_backlog_max"] >= 1
    for _ in range(8):
        g.tool("shell", {})
    g.complete("e", usage(327680))
    assert g.primary == "looping"
    assert {"looping", "hard_ceiling", "stalled", "budget_hit"} <= g.flags


@pytest.mark.parametrize(
    "failing,tampered", [(10, False), (11, False), (0, True), (None, False)]
)
def test_equal_count_alternating_tampered_ungradeable_never_progress(failing, tampered):
    g = tg.TokenTurnGate(10)
    g.pending.add(1)
    g.complete("a", usage(81920))
    g.grade(1, failing, tampered)
    assert g.stop_reason == "stalled" and g.best == 10


def test_fragmented_utf8_json_terminal_drain():
    g = tg.TokenTurnGate(2)
    s = tg.EventStream(g)
    data = "".join(
        json.dumps(e, ensure_ascii=False) + "\n"
        for e in [
            event("step_start"),
            event("text", text="π😀"),
            event("step_finish", tokens=usage()),
        ]
    ).encode()
    for b in data[:-1]:
        s.feed(bytes([b]))
    assert len(g.request_usage) == 0
    s.feed(data[-1:])
    s.finish()
    assert len(g.request_usage) == 1


@pytest.mark.parametrize(
    "kind", ["duplicate", "malformed", "retry", "id_mismatch", "partial"]
)
def test_ingestion_refuses(kind):
    s = tg.EventStream(tg.TokenTurnGate(1))
    s.accept(event("step_start"))
    with pytest.raises(tg.TransportAbort):
        if kind == "duplicate":
            s.accept(event("step_start"))
        elif kind == "malformed":
            s.feed(b"{broken}\n")
        elif kind == "unknown":
            s.accept(event("new_step_event"))
        elif kind == "retry":
            s.accept(event("step_start", "m2"))
        elif kind == "id_mismatch":
            s.accept(event("step_finish", "m2", tokens=usage()))
        else:
            s.feed(b"{")
            s.finish()


def test_parallel_tools_completion_order_and_tool_free_request():
    a = tg.TokenTurnGate(1)
    b = tg.TokenTurnGate(1)
    for call in [1, 2, 2]:
        a.tool("shell", call)
    for call in [2, 1, 2]:
        b.tool("shell", call)
    a.complete("x", usage())
    b.complete("x", usage())
    assert a.max_identical_run_live == 2 and b.max_identical_run_live == 1
    a.complete("y", usage())
    a.tool("shell", 2)
    assert a.max_identical_run_live == 3


def test_cache_budget_boundary():
    g = tg.TokenTurnGate(1, context_limit=1000)
    g.complete("x", usage(480, 100, 200, 100))
    assert g.request_usage == [("x", 480, 400, 480)]
    assert g.primary == "budget_hit" and g.stop_reason is None


@pytest.mark.parametrize(
    "path,value",
    [
        ("output", True),
        ("output", -1),
        ("input", None),
        ("read", True),
        ("write", -1),
        ("write", None),
    ],
)
def test_missing_bool_negative_usage(path, value):
    u = usage()
    target = u["cache"] if path in ("read", "write") else u
    if value is None:
        del target[path]
    else:
        target[path] = value
    with pytest.raises(tg.TransportAbort):
        tg.TokenTurnGate(1).complete("x", u)


def assistant(mid="m1", output=1, **kw):
    return dict(id=mid, type="assistant", tokens=usage(output), content=[], finish="stop", **kw)


def test_terminal_normal_final_usage_charged_once_and_final_ceiling():
    g = tg.TokenTurnGate(1)
    s = tg.EventStream(g)
    request(s, "m1")
    s.accept(event("step_start", "m2"))
    tg.reconcile(s, dict(messages=[assistant(), assistant("m2", 327680)]), 0)
    assert len(g.request_usage) == 2 and g.primary == "hard_ceiling"


def test_final_request_k_crossing():
    g = tg.TokenTurnGate(1)
    s = tg.EventStream(g)
    request(s, calls=[{}] * 7)
    s.accept(event("step_start", "m2"))
    s.accept(event("tool_use", "m2", partID="last", tool="shell", state=tool_state()))
    tg.reconcile(s, dict(messages=[assistant(), assistant("m2")]), 0)
    assert g.primary == "looping"


@pytest.mark.parametrize(
    "state", ["stalled", "looping", "hard_ceiling", "exec_timeout", "client_resource"]
)
def test_terminal_kill_backlog_and_interrupted_last(state):
    g = tg.TokenTurnGate(1)
    s = tg.EventStream(g)
    request(s)
    g.stop(state)
    tg.reconcile(
        s,
        dict(
            messages=[
                assistant(),
                assistant("m2"),
                dict(type="assistant", id="m3", error=dict(type="aborted")),
            ]
        ),
        -9,
        state,
    )
    assert len(g.request_usage) == 2 and state in g.flags


def test_terminal_context_overflow():
    g = tg.TokenTurnGate(1)
    s = tg.EventStream(g)
    err = dict(
        type="provider.invalid-request",
        status=400,
        message="maximum context length is 100 tokens; messages resulted in 200 tokens",
    )
    s.accept(dict(type="error", sessionID="s1", error=err))
    tg.reconcile(s, dict(messages=[dict(type="assistant", id="m1", error=err)]), 1)
    assert g.primary == "context_overflow"


@pytest.mark.parametrize(
    "case", ["mismatch", "missing", "extra", "retry", "step_failed", "exit", "aborted"]
)
def test_terminal_other_states_abort(case):
    g = tg.TokenTurnGate(1)
    s = tg.EventStream(g)
    request(s)
    messages = [assistant()]
    rc = 0
    if case == "mismatch":
        messages[0]["tokens"] = usage(2)
    if case == "missing":
        messages = []
    if case == "extra":
        messages += [assistant("m2"), assistant("m3")]
    if case == "retry":
        messages[0]["retry"] = {"attempt": 1}
    if case == "step_failed":
        s.accept(dict(type="error", sessionID="s1", error=dict(type="Step.Failed")))
    if case == "exit":
        rc = 1
    if case == "aborted":
        messages[0]["error"] = {"type": "aborted"}
    with pytest.raises(tg.TransportAbort):
        tg.reconcile(s, dict(messages=messages), rc)


def test_duplicate_tool_call_id_different_projection_rejected():
    s = tg.EventStream(tg.TokenTurnGate(1))
    s.accept(event("step_start"))
    first = event("tool_use", partID="projection-a", tool="read", state=tool_state())
    s.accept(first)
    second = {**first, "part": {**first["part"], "partID": "projection-b"}}
    with pytest.raises(tg.TransportAbort, match="duplicate"):
        s.accept(second)
