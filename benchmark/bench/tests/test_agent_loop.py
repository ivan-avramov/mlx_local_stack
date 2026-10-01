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
    """6th cold review round 6 P27: malformed arguments are NEVER silently substituted with `{}`
    and dispatched as if valid -- the tool's `fn` must NOT be called at all; a parse-error tool
    response is fed back instead, and the loop continues (never crashes, never ends the episode)."""
    driver = ScriptedDriver([
        ([{"id": "x", "type": "function", "function": {"name": "read_file", "arguments": "not json"}}], ""),
        ([_toolcall("submit", {"patch": "D"})], ""),
    ])
    log = []
    out = AL.run_agent(driver, "m", "sys", "t", _tools(log), {}, max_turns=5)
    assert ("read", None) not in log            # the tool's fn was NEVER called with bad args
    assert log == []
    assert out["submitted"] == {"patch": "D"}


def test_agent_malformed_submit_args_are_never_treated_as_a_submission_P27():
    """6th cold review round 6 P27 (HIGH), reproduction: malformed JSON in the SUBMIT tool's
    arguments must not be silently turned into a valid (if empty/null) submission -- the episode
    must continue, feeding back the parse error, until a WELL-FORMED submit arrives."""
    driver = ScriptedDriver([
        ([{"id": "x", "type": "function", "function": {"name": "submit", "arguments": "{bad json"}}], ""),
        ([_toolcall("submit", {"patch": "D"})], ""),
    ])
    log = []
    out = AL.run_agent(driver, "m", "sys", "t", _tools(log), {}, max_turns=5)
    assert out["submitted"] == {"patch": "D"}   # only the SECOND, well-formed submit counts
    assert out["turns"] == 2


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


# --------------------------------------------------------------------------- P49 unknown_tool_text
def test_unknown_tool_text_default_preserves_the_diagnostic_message():
    log = []
    tools = _tools(log)
    driver = ScriptedDriver([([_toolcall("nope", {})], ""), ([_toolcall("submit", {"patch": "D"})], "")])
    out = AL.run_agent(driver, "m", "sys", "t", tools, {}, max_turns=5)
    tool_msgs = [m for m in driver.calls[1]["messages"] if m.get("role") == "tool"]
    assert "ERROR: unknown tool" in tool_msgs[-1]["content"]
    assert out["outcome"] == AO.SOLVED


def test_unknown_tool_text_when_set_feeds_back_the_exact_text_verbatim_P49():
    """8th cold review round 8 P49: an opt-in unknown_tool_text, when set, replaces our own
    diagnostic message with the caller-supplied text verbatim -- default behaviour (every
    pre-existing, non-AgentBench caller) is unchanged."""
    log = []
    tools = _tools(log)
    driver = ScriptedDriver([([_toolcall("nope", {})], ""), ([_toolcall("submit", {"patch": "D"})], "")])
    out = AL.run_agent(driver, "m", "sys", "t", tools, {}, max_turns=5,
                       unknown_tool_text="Invalid function call. Please call a tool instead")
    tool_msgs = [m for m in driver.calls[1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs[-1]["content"] == "Invalid function call. Please call a tool instead"
    assert out["outcome"] == AO.SOLVED   # the episode continued to a real submit next turn


# --------------------------------------------------------------------------- P53(b) on_feedback
def test_on_feedback_captures_every_feedback_kind_at_its_real_source():
    """8th cold review round 8 P53(b): on_feedback fires with the EXACT text fed back, for every
    kind -- parse-error, unknown-tool, a tool's own result, and the no-tool-call reprompt --
    eliminating the need for a caller to independently reconstruct any of it."""
    captured = []

    def _on_feedback(tool_call_id, text):
        captured.append((tool_call_id, text))

    log = []
    tools = _tools(log)
    driver = ScriptedDriver([
        ([], ""),                                                     # no tool call -> reprompt
        ([{"id": "c1", "type": "function",
           "function": {"name": "read_file", "arguments": "{not json"}}], ""),   # parse error
        ([_toolcall("nope", {})], ""),                                # unknown tool
        ([_toolcall("read_file", {"path": "a.py"})], ""),             # real tool success
        ([_toolcall("submit", {"patch": "D"})], ""),                  # submit
    ])
    out = AL.run_agent(driver, "m", "sys", "t", tools, {}, max_turns=10,
                       no_tool_call_reprompt="No executable tool calls found. Please call a tool instead",
                       on_feedback=_on_feedback)
    assert out["outcome"] == AO.SOLVED
    assert len(captured) == 5
    assert captured[0] == (None, "No executable tool calls found. Please call a tool instead")
    assert captured[1][0] == "c1" and "Expecting" in captured[1][1]   # the JSON decode error text
    assert "ERROR: unknown tool" in captured[2][1]
    assert captured[3][1] == "contents of a.py"                      # the tool's own real result
    assert captured[4][1] == "submitted"


def test_on_feedback_abort_episode_captures_the_abort_message():
    captured = []

    def _boom(a):
        raise AL.AbortEpisode(AO.FAILED_TESTS, "command timed out")
    tools = [AL.Tool("boom", "d", {"type": "object", "properties": {}}, _boom)]
    driver = ScriptedDriver([([_toolcall("boom", {})], "")])
    out = AL.run_agent(driver, "m", "sys", "t", tools, {}, max_turns=5,
                       on_feedback=lambda tcid, text: captured.append((tcid, text)))
    assert out["outcome"] == AO.FAILED_TESTS
    assert captured == [("x", "command timed out")]


def test_on_feedback_default_none_is_a_pure_noop():
    """Every pre-existing caller (on_feedback not passed at all) must see IDENTICAL behaviour."""
    tools = _tools([])
    driver = ScriptedDriver([([_toolcall("read_file", {"path": "a.py"})], ""),
                             ([_toolcall("submit", {"patch": "D"})], "")])
    out = AL.run_agent(driver, "m", "sys", "t", tools, {}, max_turns=5)
    assert out["outcome"] == AO.SOLVED
