"""A bounded tool-calling agent loop over a Driver. The model is given a task + tool schemas;
each turn it either calls tools (we execute them and feed results back) or returns a final
answer. Used by the SWE-bench patch-gen agent; generic.

Termination is a LABELLED outcome (see agent_outcomes), not just "did it submit". Three bounds,
each catching a different failure:

  * `loop_guard`  — the model is STUCK (repeating an invalid call, or inventing tool names). This,
    not the turn cap, is the runaway protection: a model was observed calling a nonexistent tool
    400+ times while the harness kept replying with the correct tool list, and under a bare turn
    cap that is indistinguishable from productive work that ran long.
  * `deadline_s`  — the model is too SLOW to be useful, which is a scored outcome rather than an
    excluded run. Tokens per second is a vanity metric; time-to-outcome is the deployment property.
  * `max_turns`   — the last-resort bound. Raised 12 -> 30: twelve turns cannot cover
    list -> read several files -> patch, and with the guard in place it no longer has to be tight.
"""
import json
import time
from dataclasses import dataclass
from typing import Callable

from . import agent_outcomes as AO


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


_JSON_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
               "array": list, "object": dict}


def _counter_schema(tools, submit_tool: str) -> dict:
    """{name: {required, types}} for the counters, derived from each Tool's JSON schema.

    `submit_tool` is included even though the loop handles it itself: it is a legitimate call, and
    omitting it would count every successful run's submit as an unknown-tool error.
    """
    out = {submit_tool: {"required": [], "types": {}}}
    for t in tools:
        params = t.parameters or {}
        props = params.get("properties") or {}
        types = {k: _JSON_TYPES[v["type"]] for k, v in props.items()
                 if isinstance(v, dict) and v.get("type") in _JSON_TYPES}
        out[t.name] = {"required": list(params.get("required") or []), "types": types}
    return out


def run_agent(driver, model, system, task, tools, params, max_turns: int = 30,
              submit_tool: str = "submit", deadline_s: float | None = None,
              loop_guard: AO.LoopGuard | None = None, clock=time.perf_counter) -> dict:
    """Run the loop. Returns {final, submitted, turns, transcript, outcome, counters}.

    `submitted` is the args dict of the first call to `submit_tool` (or None if never submitted).
    `clock` is injectable so deadline behaviour is testable without real elapsed time.
    """
    guard = loop_guard if loop_guard is not None else AO.LoopGuard()
    by_name = {t.name: t for t in tools}
    schemas = [t.schema() for t in tools]
    cschema = _counter_schema(tools, submit_tool)
    counters = AO.Counters()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    transcript, submitted, final, turns = [], None, None, 0
    outcome, error = None, None
    t0 = clock()

    while turns < max_turns:
        turns += 1
        try:
            out = driver.complete(model, messages, params, tools=schemas)
        except Exception as e:  # noqa: BLE001 — transport/router failure is an OUTCOME, not a crash
            outcome, error = AO.SERVER_ERROR, f"{type(e).__name__}: {str(e)[:200]}"
            break
        counters.turns = turns
        counters.completion_tokens += int(out.get("completion_tokens") or 0)
        tcs = out.get("tool_calls") or []
        transcript.append({"assistant": out.get("content", ""), "tool_calls": tcs})

        if not tcs:
            final = out.get("content", "")
            outcome = AO.NO_SUBMIT          # ended its turn with prose and never submitted
            break

        messages.append({"role": "assistant", "content": out.get("content", ""), "tool_calls": tcs})
        stop = False
        for tc in tcs:
            fn = (tc.get("function") or {})
            name = fn.get("name")
            args = _parse_args(fn.get("arguments"))
            counters.observe({"name": name, "args": args}, cschema, turn=turns)
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
                # The corrective feedback whose EFFECT is now measured: naming the available
                # tools makes a repeat of the same invalid call unambiguously the model's doing.
                result = (f"ERROR: unknown tool {name!r}. Available tools: "
                          f"{sorted(list(by_name) + [submit_tool])}")
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": str(result)})
        if stop:
            outcome = AO.SOLVED            # submitted; whether it PASSES is the grader's call
            break

        aborted = guard.should_abort(counters)
        if aborted:
            outcome = aborted
            break
        if deadline_s is not None and (clock() - t0) >= deadline_s:
            outcome = AO.DEADLINE
            break

    counters.wall_s = round(clock() - t0, 2)
    if outcome is None:
        outcome = AO.TURN_CAP              # still working when the turn budget ran out
    result = {"final": final, "submitted": submitted, "turns": turns, "transcript": transcript,
              "outcome": AO.validate_outcome(outcome), "counters": counters.as_dict()}
    if error:
        result["error"] = error
    return result
