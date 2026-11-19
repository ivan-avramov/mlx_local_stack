"""S26 frozen tests, `m62/inject_verify.py` alloc rule (spec erratum v1.1a 2: only EXECUTED shell calls carrying `bytearray(` count -
a call with `state.status == "error"` and `state.metadata.providerCall.executed` false was rejected by the tool-bounds plugin and is
excluded - and exactly one executed call must exist, whose part id equals the single kill's `tool_call_id`).

Classes: [FIX] reproduces the failure the erratum fixes (the recorded java alloc row: a rejected `background: true` call, then the
executed retry, one kill linked to the retry -> baseline `FAIL:no_shell_part`); [INV] unchanged rules. The rows are real-shaped
(the real `row_fields`, recorded grade reports, `tool_use` events as opencode 2.0.20 writes them), judged by the real `iv.main`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bench.tests.s26_frozen import s26_support as X

SCAFFOLD = "opencode-v2-web-tg2"
CMD = "python3 -c \"x = bytearray(1 << 40); print(len(x))\""
REJECTED = "M62_TOOL_BOUND: shell background must be false"


def tool_event(call, *, status, inputs, executed=None, error=None):
    state = dict(status=status, input=inputs, metadata={}, time=dict(start=1_000, end=2_000), title="shell")
    if executed is not None:
        state["metadata"] = dict(providerCall=dict(executed=executed))
    if error:
        state["error"] = error
    if status == "completed":
        state["output"] = "x"
    return json.dumps(dict(type="tool_use", sessionID="s1", part=dict(partID="p-" + call, id=call, messageID="m1", type="tool",
                                                                       tool="shell", state=state)))


def rejected(call="c-rej"):
    """The tool-bounds plugin's rejection: never reached the provider."""
    return tool_event(call, status="error", inputs=dict(command=CMD, background=True), executed=False, error=REJECTED)


def executed(call="c-run", *, killed=True):
    """The executed retry; killed by the memory guard (an `error` part whose provider call DID execute)."""
    if killed:
        return tool_event(call, status="error", inputs=dict(command=CMD, background=False), executed=True, error="killed")
    return tool_event(call, status="completed", inputs=dict(command=CMD, background=False), executed=True)


def verdict(tmp_path, events, *, kill_id="c-run", carrying=3, boundary=2, kills=1):
    """`inject_verify.main --kind alloc` over one row: the events file as given, `kills` kills linked to `kill_id`."""
    if str(X.BENCH) not in sys.path:
        sys.path.insert(0, str(X.BENCH))
    from m62 import inject_verify as iv
    wd = Path(tmp_path) / "wd"
    wd.mkdir(exist_ok=True)

    def edit(row, manifest):
        kill = dict(role="model", argv=["python3", "-c", "x = bytearray(1 << 40)"], rss=600 * 1024 ** 2, tool_call_id=kill_id,
                    carrying_request=carrying, completed_boundary_at_kill=boundary)
        row["mem_kills"] = [dict(kill) for _ in range(kills)]
        row["gate"]["requests_completed"] = 4
        manifest["runtime"]["inject"]["policy"]["hygiene"]["per_process"] = 512 * 1024 ** 2
    run = wd / "m65" / "iv-run"
    X.write_inject_run(run, wd, "alloc", 1, events, shape="mem_kill", mutate=edit)
    lines = []
    iv.main(["--run", str(run), "--kind", "alloc", "--workdir", str(wd), "--scaffold", SCAFFOLD], out=lines.append)
    return lines[0].split(": ", 1)[1].split("  [", 1)[0]


def steps(*parts):
    """step 1, then each part preceded by the step that precedes it, then two closing steps (so requests_completed 4 > the kill's)."""
    out = X.ev_step(1)
    for n, part in enumerate(parts, start=2):
        out += [part] + X.ev_step(n)
    return out + X.ev_step(len(parts) + 2)


def test_fix_a_rejected_first_call_then_an_executed_retry_linked_to_the_kill_passes(tmp_path):
    """[FIX] erratum v1.1a 2, the recorded java alloc shape: rejected `background: true` call (request 2), executed retry (request 3),
    one kill carrying request 3 whose `tool_call_id` is the retry's part id -> PASS."""
    assert verdict(tmp_path, steps(rejected(), executed())) == "PASS"


def test_fix_a_kill_linked_to_another_part_than_the_retry_is_tool_call_id(tmp_path):
    """[FIX] ... with the retry's id differing from the kill's -> `FAIL:tool_call_id`."""
    assert verdict(tmp_path, steps(rejected(), executed()), kill_id="c-other") == "FAIL:tool_call_id"


def test_fix_a_kill_linked_to_the_rejected_call_is_tool_call_id(tmp_path):
    """[FIX] the rejected call is excluded from the count, so a kill pointing at it does not match the (single) executed call."""
    assert verdict(tmp_path, steps(rejected("c-rej"), executed("c-run")), kill_id="c-rej") == "FAIL:tool_call_id"


def test_fix_two_executed_marker_calls_are_no_shell_part(tmp_path):
    """[FIX] ... two EXECUTED marker calls -> `FAIL:no_shell_part` (exactly one executed call is required)."""
    assert verdict(tmp_path, steps(rejected(), executed("c-run"), executed("c-run2"))) == "FAIL:no_shell_part"


def test_fix_only_rejected_calls_is_no_shell_part(tmp_path):
    """[FIX] nothing executed carried the marker (the kill cannot be linked to any shell call)."""
    assert verdict(tmp_path, steps(rejected())) == "FAIL:no_shell_part"


def test_inv_a_single_executed_call_without_any_rejection_still_passes(tmp_path):
    """[INV] the rule for rows without a rejection is as before."""
    assert verdict(tmp_path, steps(executed()), carrying=2, boundary=1) == "PASS"       # the only call is request 2


def test_inv_an_executed_error_part_is_counted_not_excluded(tmp_path):
    """[INV] exclusion needs BOTH `status == "error"` AND `executed` false: an error part whose provider call executed counts, so two
    of them are two executed calls."""
    two = steps(executed("c-a"), executed("c-b"))
    assert verdict(tmp_path, two) == "FAIL:no_shell_part"


def test_inv_a_completed_part_is_never_treated_as_rejected(tmp_path):
    """[INV] a `completed` shell part is executed: it is counted (single, linked), so the rule reaches the unchanged killed-part
    shape check, which refuses a completed part with no nonzero exit / signal."""
    assert verdict(tmp_path, steps(executed("c-run", killed=False)), carrying=2, boundary=1) == "FAIL:killed_part_shape"
