import json

import bench.agent_loop as AL
import bench.agent_outcomes as AO


def _toolcall(name, args):
    return {"id": "x", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


class ScriptedDriver:
    """Returns a scripted sequence of (tool_calls, content) per complete() call."""
    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def complete(self, model, messages, params, timeout=3600, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        tcs, content = self._script.pop(0)
        return {"content": content, "tool_calls": tcs, "prompt_tokens": 1,
                "completion_tokens": 1, "decode_tps": 1.0, "peak_mem_gb": 1.0,
                "prefill_s": 0.1, "prefill_tps": 1, "wall_s": 0.1, "finish_reason": "stop"}


def _tools(log):
    return [
        AL.Tool("read_file", "read a file", {"type": "object", "properties": {"path": {"type": "string"}}},
                lambda a: log.append(("read", a.get("path"))) or f"contents of {a.get('path')}"),
        AL.Tool("submit", "submit the patch", {"type": "object", "properties": {"patch": {"type": "string"}}},
                lambda a: "submitted"),
    ]


def test_agent_runs_tool_then_submits():
    log = []
    driver = ScriptedDriver([
        ([_toolcall("read_file", {"path": "a.py"})], ""),         # turn 1: read
        ([_toolcall("submit", {"patch": "DIFF"})], ""),           # turn 2: submit -> stop
    ])
    out = AL.run_agent(driver, "m", "sys", "fix it", _tools(log), {"max_tokens": 16}, max_turns=5)
    assert ("read", "a.py") in log
    assert out["submitted"] == {"patch": "DIFF"}
    assert out["turns"] == 2


def test_agent_stops_on_no_tool_calls():
    driver = ScriptedDriver([([], "here is my final answer")])
    out = AL.run_agent(driver, "m", "sys", "t", _tools([]), {}, max_turns=5)
    assert out["final"] == "here is my final answer"
    assert out["submitted"] is None


def test_agent_respects_max_turns():
    # Always asks to read; never submits -> bounded by max_turns.
    driver = ScriptedDriver([([_toolcall("read_file", {"path": "a"})], "")] * 10)
    out = AL.run_agent(driver, "m", "sys", "t", _tools([]), {}, max_turns=3)
    assert out["turns"] == 3 and out["submitted"] is None


def test_agent_handles_bad_tool_args():
    # arguments is not valid JSON -> treated as {}; unknown tool name -> error result, loop continues.
    driver = ScriptedDriver([
        ([{"id": "x", "type": "function", "function": {"name": "read_file", "arguments": "not json"}}], ""),
        ([_toolcall("submit", {"patch": "D"})], ""),
    ])
    log = []
    out = AL.run_agent(driver, "m", "sys", "t", _tools(log), {}, max_turns=5)
    assert ("read", None) in log               # bad args -> {} -> path None, no crash
    assert out["submitted"] == {"patch": "D"}


# --------------------------------------------------------------------------- M54 cold-review: opt-in extensions
def test_default_behaviour_unchanged_when_new_params_omitted():
    """Sanity pin: the new opt-in params default to off, so every pre-existing call shape (none of
    which pass them) keeps behaving exactly as before -- a no-tool-call turn still ends the episode
    immediately as NO_SUBMIT, not after reprompting."""
    driver = ScriptedDriver([([], "done")])
    out = AL.run_agent(driver, "m", "sys", "t", _tools([]), {}, max_turns=5)
    assert out["outcome"] == AO.NO_SUBMIT and out["turns"] == 1


def test_no_tool_call_reprompt_continues_the_loop_instead_of_ending_it():
    driver = ScriptedDriver([([], "")] * 3)
    out = AL.run_agent(driver, "m", "sys", "t", _tools([]), {}, max_turns=3,
                       no_tool_call_reprompt="REPROMPT TEXT")
    assert out["turns"] == 3                            # ran the FULL budget, didn't stop at turn 1
    assert out["outcome"] == AO.NO_SUBMIT                # never any tool call at all -> NO_SUBMIT
    # the reprompt text was actually fed back as a message, not silently dropped
    assert driver.calls[1]["messages"][-1] == {"role": "user", "content": "REPROMPT TEXT"}
    assert driver.calls[2]["messages"][-1] == {"role": "user", "content": "REPROMPT TEXT"}


def test_no_tool_call_reprompt_then_a_real_tool_call_is_turn_cap_not_no_submit():
    """Upstream: no_submit is reserved for an episode that NEVER called a tool. One that used
    tools but still ran out of rounds without submitting is turn_cap."""
    log = []
    driver = ScriptedDriver([([], ""), ([_toolcall("read_file", {"path": "a"})], "")])
    out = AL.run_agent(driver, "m", "sys", "t", _tools(log), {}, max_turns=2,
                       no_tool_call_reprompt="REPROMPT")
    assert out["turns"] == 2
    assert out["outcome"] == AO.TURN_CAP
    assert ("read", "a") in log


def test_single_tool_call_per_turn_ignores_the_rest_and_does_not_stop_on_a_trailing_submit():
    log = []
    tcs = [_toolcall("read_file", {"path": "a"}), _toolcall("submit", {"patch": "SHOULD NOT SUBMIT"})]
    driver = ScriptedDriver([(tcs, ""), ([_toolcall("submit", {"patch": "REAL"})], "")])
    out = AL.run_agent(driver, "m", "sys", "t", _tools(log), {}, max_turns=5,
                       single_tool_call_per_turn=True)
    assert log == [("read", "a")]                       # the submit in turn 1 was never dispatched
    assert out["submitted"] == {"patch": "REAL"}         # only turn 2's submit counted
    assert out["turns"] == 2


def test_deadline_is_reachable_on_the_no_tool_call_reprompt_path():
    """cold-review N12: a deadline check only after tool-call processing can never fire for an
    episode that keeps getting re-prompted (no tool calls at all) -- it would only ever bound on
    max_turns."""
    from bench.tests.conftest import FrozenClock
    clock = FrozenClock()
    driver = ScriptedDriver([([], "")] * 100)   # far more turns than the deadline should allow
    out = AL.run_agent(driver, "m", "sys", "t", _tools([]), {}, max_turns=100,
                       no_tool_call_reprompt="REPROMPT", deadline_s=5,
                       clock=clock.ticking(2))   # +2s per clock() read
    assert out["outcome"] == AO.DEADLINE
    assert out["turns"] < 100


def test_abort_episode_from_a_tool_ends_the_loop_immediately_with_the_given_outcome():
    log = []

    def _boom(a):
        log.append("boom-called")
        raise AL.AbortEpisode(AO.FAILED_TESTS, "command timed out")

    tools = [AL.Tool("boom", "d", {"type": "object", "properties": {}}, _boom),
            AL.Tool("other", "d", {"type": "object", "properties": {}}, lambda a: log.append("other") or "ok"),
            AL.Tool("submit", "d", {"type": "object", "properties": {}}, lambda a: "submitted")]
    tcs = [_toolcall("boom", {}), _toolcall("other", {}), _toolcall("submit", {})]
    driver = ScriptedDriver([(tcs, ""), ([_toolcall("submit", {})], "")])   # a 2nd turn must never run
    out = AL.run_agent(driver, "m", "sys", "t", tools, {}, max_turns=5)
    assert log == ["boom-called"]                        # "other" and "submit" in the SAME turn never ran
    assert out["outcome"] == AO.FAILED_TESTS
    assert out["turns"] == 1
    assert len(driver.calls) == 1                        # the loop did not continue to a 2nd turn
    assert out["submitted"] is None
