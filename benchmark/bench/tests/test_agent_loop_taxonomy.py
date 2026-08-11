"""`run_agent` must end in a LABELLED outcome, with counters, a deadline, and a loop guard.

The scenario that motivates all of it, observed in the wild: a model called a tool that does not
exist, the harness replied with the error and the correct tool list, and the model repeated the
identical invalid call 400+ times until a human killed it. Under the old loop that is
`turns=12, submitted=None` — the same shape as a model that was working productively and ran out
of turns. Now it aborts on the third identical call with `outcome="tool_error_loop"`.

`max_turns` also rises 12 -> 30 here. Twelve turns is far too few for real agentic work (the
SWE-bench explore-and-patch agent has to list, read several files, then patch), and with a loop
guard in place the turn cap is no longer the runaway protection — the guard is.
"""
import pytest

import bench.agent_loop as AL
import bench.agent_outcomes as AO

from .conftest import FakeDriver, FrozenClock, complete_result, tool_call


def _tools():
    """A read-only tool plus submit, as the SWE-bench agent uses."""
    reads = []

    def read(args):
        reads.append(args.get("path"))
        return f"contents of {args.get('path')}"

    return [AL.Tool(name="read_file", description="read a file",
                    parameters={"type": "object", "properties": {"path": {"type": "string"}},
                                "required": ["path"]},
                    fn=read)], reads


def _submit_tool():
    return AL.Tool(name="submit", description="submit the patch",
                   parameters={"type": "object", "properties": {"patch": {"type": "string"}},
                               "required": ["patch"]},
                   fn=lambda args: "submitted")


def _run(script, **kw):
    tools, _ = _tools()
    tools.append(_submit_tool())
    driver = FakeDriver(script)
    return AL.run_agent(driver, "m", "sys", "task", tools, {"temperature": 0.4}, **kw), driver


# --------------------------------------------------------------------- the wild scenario
def test_infinite_identical_invalid_call_aborts_in_three_turns():
    """Would previously have burned every available turn and reported no_submit."""
    forever = [complete_result(tool_calls=[tool_call("serch_repo", {"q": "bug"})])
               for _ in range(30)]
    out, driver = _run(forever)
    assert out["outcome"] == AO.TOOL_ERROR_LOOP
    assert out["turns"] == 3, "the guard must stop it, not the turn cap"
    assert driver.n_calls == 3, "and it must stop CALLING the model, not just label the result"
    assert out["counters"]["unknown_tool_calls"] == 3
    assert out["counters"]["max_identical_repeat"] == 3


def test_a_model_inventing_a_new_fake_tool_each_turn_also_aborts():
    script = [complete_result(tool_calls=[tool_call(f"ghost{i}", {})]) for i in range(10)]
    out, driver = _run(script)
    assert out["outcome"] == AO.TOOL_ERROR_LOOP
    assert out["counters"]["unknown_tool_calls"] == 5      # max_unknown default
    assert out["counters"]["max_identical_repeat"] == 1     # never repeated itself


def test_recovering_from_one_bad_call_is_not_penalised_and_is_measured():
    script = [
        complete_result(tool_calls=[tool_call("serch_repo", {"q": "bug"})]),
        complete_result(tool_calls=[tool_call("read_file", {"path": "a.py"})]),
        complete_result(tool_calls=[tool_call("submit", {"patch": "diff"})]),
    ]
    out, _ = _run(script)
    assert out["outcome"] == AO.SOLVED
    assert out["submitted"] == {"patch": "diff"}
    assert out["counters"]["recovered_after_error"] is True
    assert out["counters"]["turns_to_recovery"] == 1


# --------------------------------------------------------------------- deadline
def test_deadline_aborts_and_keeps_the_partial_transcript():
    clock = FrozenClock()
    script = [complete_result(tool_calls=[tool_call("read_file", {"path": f"{i}.py"})])
              for i in range(10)]
    tools, _ = _tools()
    tools.append(_submit_tool())
    out = AL.run_agent(FakeDriver(script), "m", "sys", "task", tools, {},
                       deadline_s=10, clock=clock.ticking(6))
    assert out["outcome"] == AO.DEADLINE
    assert out["turns"] == 2, "6s, then 12s > 10s deadline"
    assert len(out["transcript"]) == 2, "partial work is retained for diagnosis"
    assert out["counters"]["wall_s"] >= 10


def test_no_deadline_means_no_deadline_abort():
    script = [complete_result(tool_calls=[tool_call("read_file", {"path": "a.py"})]),
              complete_result(tool_calls=[tool_call("submit", {"patch": "p"})])]
    out, _ = _run(script, deadline_s=None)
    assert out["outcome"] == AO.SOLVED


# --------------------------------------------------------------------- other outcomes
def test_turn_cap_is_distinct_from_no_submit():
    """turn_cap = still working when the budget ran out. no_submit = ended its turn with prose."""
    script = [complete_result(tool_calls=[tool_call("read_file", {"path": f"{i}.py"})])
              for i in range(4)]
    out, _ = _run(script, max_turns=4)
    assert out["outcome"] == AO.TURN_CAP

    out2, _ = _run([complete_result(content="I think the bug is in foo.py.", tool_calls=[])])
    assert out2["outcome"] == AO.NO_SUBMIT
    assert out2["final"].startswith("I think")


def test_default_max_turns_is_thirty():
    """12 was too few for real agentic work; the loop guard is now the runaway protection."""
    import inspect
    assert inspect.signature(AL.run_agent).parameters["max_turns"].default == 30


def test_driver_exception_is_a_server_error_not_a_crash():
    class Boom:
        def complete(self, *a, **k):
            raise ConnectionResetError("router died")

    tools, _ = _tools()
    out = AL.run_agent(Boom(), "m", "sys", "task", tools, {})
    assert out["outcome"] == AO.SERVER_ERROR
    assert "ConnectionResetError" in (out.get("error") or "")


def test_tool_raising_is_fed_back_not_fatal():
    """A tool blowing up is information for the model, not the end of the session."""
    def boom(args):
        raise RuntimeError("disk on fire")

    tools = [AL.Tool(name="read_file", description="d", parameters={}, fn=boom), _submit_tool()]
    script = [complete_result(tool_calls=[tool_call("read_file", {"path": "a.py"})]),
              complete_result(tool_calls=[tool_call("submit", {"patch": "p"})])]
    out = AL.run_agent(FakeDriver(script), "m", "sys", "task", tools, {})
    assert out["outcome"] == AO.SOLVED


def test_counters_are_json_serialisable_for_the_results_row():
    import json
    out, _ = _run([complete_result(tool_calls=[tool_call("submit", {"patch": "p"})])])
    json.dumps(out["counters"])


def test_outcome_is_always_a_member_of_the_closed_set():
    out, _ = _run([complete_result(tool_calls=[tool_call("submit", {"patch": "p"})])])
    AO.validate_outcome(out["outcome"])


def test_guard_thresholds_are_configurable():
    forever = [complete_result(tool_calls=[tool_call("nope", {})]) for _ in range(30)]
    out, _ = _run(forever, loop_guard=AO.LoopGuard(max_identical=2, max_unknown=99))
    assert out["turns"] == 2


def test_submit_tool_absent_from_schema_still_counts_as_known():
    """`submit` is handled by the loop itself, not by the tool table — it must not be counted as
    an unknown-tool call (which would make every successful run look like one error)."""
    out, _ = _run([complete_result(tool_calls=[tool_call("submit", {"patch": "p"})])])
    assert out["counters"]["unknown_tool_calls"] == 0
    assert out["counters"]["recovered_after_error"] is None
