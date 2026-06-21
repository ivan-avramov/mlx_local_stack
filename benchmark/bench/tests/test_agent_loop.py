import json

import bench.agent_loop as AL


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
