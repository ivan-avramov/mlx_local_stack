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


def _parse_args_with_error(raw) -> tuple:
    """6th cold review round 6 P27 (HIGH): malformed tool-call arguments must NEVER be silently
    substituted with `{}` -- that let a garbled `finish_action`/submit call through as a VALID
    (if empty) submission, reproduced as a passing one-turn episode on a state-check task.
    Mirrors upstream AgentBench task.py's own parse-failure handling (`except Exception as e: ...
    content=str(e)`, feeding the exception text back as a tool response and continuing the
    episode, never ending it).

    7th cold review round 7 addendum R5: the fed-back text is the BARE `str(e)`, with NO
    "Error parsing arguments: " prefix -- upstream task.py:575-592 feeds back the raw exception
    text verbatim, and our added prefix is foreign to a model that has seen upstream's exact
    phrasing during training/eval on the real benchmark.

    8th cold review round 8 P49: an EMPTY dict (`{}`) is deliberately NOT rejected HERE -- it is
    a structurally VALID tool call with zero arguments, legitimate for any tool whose JSON schema
    requires nothing (confirmed by a PRE-EXISTING generic test: a zero-arg tool dispatched with
    `{}` must actually run). Upstream AgentBench's own POSITIONAL extraction
    (`list(json.loads(args).values())[0]`, which raises IndexError on an empty values list) is
    specific to AgentBench OS's 3 single-argument tools, not a property of tool-call parsing in
    general -- handled at the EXTRACTION point (`agentbench_adapter._extract_tool_arg` and its
    call sites), not genericaly here. This parser stays tool-agnostic (it also backs non-
    AgentBench callers). Returns (args: dict, error: str|None)."""
    if isinstance(raw, dict):
        return raw, None
    try:
        v = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        return {}, str(e)
    if not isinstance(v, dict):
        return {}, f"expected a JSON object, got {type(v).__name__}"
    return v, None


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


class AbortEpisode(Exception):
    """A tool can raise this (M54 cold review F5/F4a) to end the episode IMMEDIATELY with a given
    outcome, instead of having the exception fed back as an "ERROR: ..." tool message and the loop
    continuing (the default for every other exception a tool raises). Opt-in by construction: no
    pre-existing tool raises it, so default behaviour is unchanged. Use case: an exec timeout that
    must end the task, not just report a failed command."""

    def __init__(self, outcome: str, message: str = ""):
        super().__init__(message)
        self.outcome = outcome
        self.message = message


def run_agent(driver, model, system, task, tools, params, max_turns: int = 30,
              submit_tool: str = "submit", deadline_s: float | None = None,
              loop_guard: AO.LoopGuard | None = None, clock=time.perf_counter,
              no_tool_call_reprompt: str | None = None,
              single_tool_call_per_turn: bool = False,
              unknown_tool_text: str | None = None,
              on_feedback=None) -> dict:
    """Run the loop. Returns {final, submitted, turns, transcript, outcome, counters}.

    `submitted` is the args dict of the first call to `submit_tool` (or None if never submitted).
    `clock` is injectable so deadline behaviour is testable without real elapsed time.

    Opt-in parameters added for M54 (AgentBench os-std), default off so every pre-existing caller
    keeps its exact prior behaviour:
      * `no_tool_call_reprompt` — when set, a turn with no tool call feeds this text back as a user
        message and CONTINUES the loop (consuming a turn) instead of ending the episode as
        NO_SUBMIT on the spot. `NO_SUBMIT` is then reserved for an episode that reaches `max_turns`
        having NEVER made a single tool call; one that used tools but still never submitted is
        `TURN_CAP` (upstream os-std semantics: a no-tool-call turn is a corrective re-prompt, not
        a terminal state).
      * `single_tool_call_per_turn` — when True, only the FIRST tool call of a turn is dispatched;
        the rest are silently ignored (upstream `tool_calls[0]`), so a submit riding alongside a
        bash call in the same turn is never processed.
      * `unknown_tool_text` (8th cold review round 8 P49) — when set, an unknown-tool-name call
        feeds back this EXACT text instead of our own diagnostic "ERROR: unknown tool ...
        Available tools: [...]" message. Upstream AgentBench os_interaction task.py's equivalent
        check (`action_data["action"] not in ["bash", "commit"]`) feeds back the fixed string
        "Invalid function call. Please call a tool instead" -- no tool name, no tool list, since
        upstream's extraction silently maps any OTHER func_name to action=None rather than
        naming what was wrong. Default `None` preserves the diagnostic text for every
        pre-existing (non-AgentBench) caller.
      * `on_feedback` (8th cold review round 8 P53(b)) — when set, called as
        `on_feedback(tool_call_id, text)` at the EXACT point this loop appends a `{"role":
        "tool", ...}` message (or `on_feedback(None, text)` for the no-tool-call reprompt's user
        message) -- i.e. the ACTUAL text fed back to the model, captured at its one true source,
        rather than a caller having to independently RECONSTRUCT what this loop will produce
        (parse-error text, unknown-tool text, a tool's own result/abort message) and risk it
        drifting out of lockstep. Exceptions from `on_feedback` itself propagate (a caller's own
        bug in its callback is not this loop's problem to swallow). Default `None` is a pure
        no-op for every pre-existing caller.
    """
    guard = loop_guard if loop_guard is not None else AO.LoopGuard()
    by_name = {t.name: t for t in tools}
    schemas = [t.schema() for t in tools]
    cschema = _counter_schema(tools, submit_tool)
    counters = AO.Counters()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    transcript, submitted, final, turns = [], None, None, 0
    outcome, error = None, None
    any_tool_call_ever = False
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
            if no_tool_call_reprompt is not None:
                messages.append({"role": "assistant", "content": out.get("content", "")})
                messages.append({"role": "user", "content": no_tool_call_reprompt})
                if on_feedback is not None:
                    on_feedback(None, no_tool_call_reprompt)
                # cold-review N12: the deadline must be reachable on this path too -- without it,
                # an episode stuck re-prompting forever only ever bounds on max_turns.
                if deadline_s is not None and (clock() - t0) >= deadline_s:
                    outcome = AO.DEADLINE
                    break
                continue
            final = out.get("content", "")
            outcome = AO.NO_SUBMIT          # ended its turn with prose and never submitted
            break

        any_tool_call_ever = True
        messages.append({"role": "assistant", "content": out.get("content", ""), "tool_calls": tcs})
        stop = False
        aborted_episode = None
        calls_this_turn = tcs[:1] if single_tool_call_per_turn else tcs
        for tc in calls_this_turn:
            fn = (tc.get("function") or {})
            name = fn.get("name")
            args, parse_error = _parse_args_with_error(fn.get("arguments"))
            counters.observe({"name": name, "args": args}, cschema, turn=turns)
            if parse_error is not None:
                # P27: a malformed-arguments call is NEVER a submission, regardless of which tool
                # name it claims (including submit_tool) -- feed back the parse error (upstream's
                # own mechanism) and let the episode continue, never silently substitute {}.
                messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": parse_error})
                if on_feedback is not None:
                    on_feedback(tc.get("id"), parse_error)
                continue
            if name == submit_tool:
                submitted = args
                stop = True
                result = "submitted"
            elif name in by_name:
                try:
                    result = by_name[name].fn(args)
                except AbortEpisode as e:
                    result = e.message or str(e)
                    messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": str(result)})
                    if on_feedback is not None:
                        on_feedback(tc.get("id"), str(result))
                    aborted_episode = e.outcome
                    break
                except Exception as e:  # noqa: BLE001 — tool failure is fed back, not fatal
                    result = f"ERROR: {type(e).__name__}: {str(e)[:200]}"
            elif unknown_tool_text is not None:
                # P49: upstream's own corrective text, verbatim.
                result = unknown_tool_text
            else:
                # The corrective feedback whose EFFECT is now measured: naming the available
                # tools makes a repeat of the same invalid call unambiguously the model's doing.
                result = (f"ERROR: unknown tool {name!r}. Available tools: "
                          f"{sorted(list(by_name) + [submit_tool])}")
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": str(result)})
            if on_feedback is not None:
                on_feedback(tc.get("id"), str(result))
        if aborted_episode is not None:
            outcome = aborted_episode
            break
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
        # TURN_CAP unless this episode never made a single tool call under the reprompt protocol,
        # in which case it is NO_SUBMIT even though it ran the full budget (see docstring).
        outcome = AO.NO_SUBMIT if (no_tool_call_reprompt is not None and not any_tool_call_ever) \
            else AO.TURN_CAP
    result = {"final": final, "submitted": submitted, "turns": turns, "transcript": transcript,
              "outcome": AO.validate_outcome(outcome), "counters": counters.as_dict()}
    if error:
        result["error"] = error
    return result
