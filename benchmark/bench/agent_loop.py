"""A bounded tool-calling agent loop over a Driver. The model is given a task + tool schemas;
each turn it either calls tools (we execute them and feed results back) or returns a final
answer. Bounded by max_turns (a hard cap). Used by the SWE-bench patch-gen agent; generic."""
import json
from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON schema for the arguments
    fn: Callable[[dict], str]  # executes the tool, returns a string result

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters}}


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def run_agent(driver, model, system, task, tools, params, max_turns: int = 12,
              submit_tool: str = "submit") -> dict:
    """Run the loop. Returns {final, submitted, turns, transcript}. `submitted` is the args
    dict of the first call to `submit_tool` (or None if never submitted)."""
    by_name = {t.name: t for t in tools}
    schemas = [t.schema() for t in tools]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    transcript, submitted, final, turns = [], None, None, 0
    for _ in range(max_turns):
        turns += 1
        out = driver.complete(model, messages, params, tools=schemas)
        tcs = out.get("tool_calls") or []
        transcript.append({"assistant": out.get("content", ""), "tool_calls": tcs})
        if not tcs:
            final = out.get("content", "")
            break
        messages.append({"role": "assistant", "content": out.get("content", ""), "tool_calls": tcs})
        stop = False
        for tc in tcs:
            fn = (tc.get("function") or {})
            name = fn.get("name")
            args = _parse_args(fn.get("arguments"))
            if name == submit_tool:
                submitted = args
                stop = True
                result = "submitted"
            elif name in by_name:
                try:
                    result = by_name[name].fn(args)
                except Exception as e:  # noqa: BLE001 — tool failure is fed back, not fatal
                    result = f"ERROR: {type(e).__name__}: {str(e)[:200]}"
            else:
                result = f"ERROR: unknown tool {name!r}"
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": str(result)})
        if stop:
            break
    return {"final": final, "submitted": submitted, "turns": turns, "transcript": transcript}
