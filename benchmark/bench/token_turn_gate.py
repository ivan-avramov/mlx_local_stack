"""M62 passive request accounting. No model, process or grading dependencies."""

from __future__ import annotations
import json
import re
import time
from .convergence import resolved_thinking_budget

POLICY = dict(
    no_progress_tokens=81920,
    no_progress_requests=40,
    identical_calls=8,
    output_tokens=327680,
    requests=150,
    thinking_budget=81920,
    max_tokens=102400,
)
PRECEDENCE = (
    "looping",
    "hard_ceiling",
    "stalled",
    "exec_timeout",
    "client_resource",
    "context_overflow",
    "budget_hit",
)


class TransportAbort(RuntimeError):
    """Evidence or infrastructure cannot support a scored row."""


def usage_tuple(tokens):
    try:
        values = (
            tokens["output"],
            tokens["reasoning"],
            tokens["input"],
            tokens["cache"]["read"],
            tokens["cache"]["write"],
        )
    except (KeyError, TypeError):
        raise TransportAbort("missing request usage") from None
    if any(type(n) is not int or n < 0 for n in values):
        raise TransportAbort("usage must contain non-negative integers, not bools")
    return values


class TokenTurnGate:
    def __init__(
        self, baseline_failing, *, context_limit=262144, universe_size=None, policy=None
    ):
        self.policy = dict(POLICY if policy is None else policy)
        self.context_limit = context_limit
        self.baseline = self.best = baseline_failing
        self.universe_size = universe_size
        self.last_progress_boundary = 0
        self.request_usage = []
        self.usage = {}
        self.pending = set()
        self.stall_wait = None
        self.flags = set()
        self.stop_reason = None
        self.trajectory = []
        self.previous_tool = None
        self.identical_run = self.max_identical_run_live = 0
        self.first_crossing_request = None
        self.output_at_crossing = None
        self.decision_backlog_max = 0
        self.inflight_s_at_stop = None
        self.requests_at_kill = None

    @property
    def no_progress_tokens(self):
        return sum(r[1] for r in self.request_usage[self.last_progress_boundary :])

    @property
    def no_progress_requests(self):
        return len(self.request_usage) - self.last_progress_boundary

    @property
    def output_tokens(self):
        return sum(r[1] for r in self.request_usage)

    @property
    def primary(self):
        return next((k for k in PRECEDENCE if k in self.flags), None)

    def tool(self, name, inputs):
        sig = (name, json.dumps(inputs, sort_keys=True, allow_nan=False))
        return self.on_tool_call(sig)

    def on_tool_call(self, sig):
        self.identical_run = self.identical_run + 1 if sig == self.previous_tool else 1
        self.previous_tool = sig
        self.max_identical_run_live = max(
            self.max_identical_run_live, self.identical_run
        )
        return self.check(tool_request=len(self.request_usage) + 1)

    def complete(self, message_id, tokens, *, check=True):
        if (
            not isinstance(message_id, str)
            or not message_id
            or message_id in self.usage
        ):
            raise TransportAbort("missing or duplicate message id")
        values = usage_tuple(tokens)
        visible, reasoning, *inputs = values
        output = visible + reasoning
        prompt = sum(inputs)
        budget = resolved_thinking_budget(
            dict(thinking_budget=81920, prompt_tokens=prompt),
            context_limit=self.context_limit,
            max_tokens=102400,
        )
        if budget is None:
            raise TransportAbort("cannot resolve completed request budget")
        self.usage[message_id] = values
        self.on_request(len(self.request_usage) + 1, output, prompt, budget)
        self.request_usage[-1] = (message_id, output, prompt, budget)
        return self.check() if check else None

    def on_request(self, j, output_j, prompt_j, b_j):
        if j != len(self.request_usage) + 1:
            raise TransportAbort("non-sequential completed request")
        self.request_usage.append((str(j), output_j, prompt_j, b_j))
        if output_j >= b_j:
            self.flags.add("budget_hit")

    def on_capture(self, boundary):
        self.pending.add(boundary)

    def on_grade(self, boundary, failing, gradeable, tampered):
        return self.grade(boundary, failing if gradeable else None, tampered)

    def decision(self):
        return self.check()

    def terminal(self, final_request, final_grade):
        if final_request is not None:
            self.on_request(*final_request)
        if final_grade is not None:
            self.on_grade(*final_grade)
        return self.decision()

    def grade(self, boundary, failing, tampered=False):
        self.pending.discard(boundary)
        self.trajectory.append((boundary, failing, tampered))
        if failing is not None and not tampered and failing < self.best:
            self.best = failing
            self.last_progress_boundary = max(self.last_progress_boundary, boundary)
        return self.check()

    def stop(self, reason):
        self.flags.add(reason)
        if self.stop_reason is None:
            self.stop_reason = reason
        return self.stop_reason

    def check(self, *, tool_request=None):
        p = self.policy
        conditions = []
        if self.max_identical_run_live >= p["identical_calls"]:
            conditions.append("looping")
        if (
            self.output_tokens >= p["output_tokens"]
            or len(self.request_usage) >= p["requests"]
        ):
            conditions.append("hard_ceiling")
        stalled = (
            self.no_progress_tokens >= p["no_progress_tokens"]
            or self.no_progress_requests >= p["no_progress_requests"]
        )
        if conditions or stalled:
            if self.first_crossing_request is None:
                self.first_crossing_request = tool_request or len(self.request_usage)
                self.output_at_crossing = self.output_tokens
            self.decision_backlog_max = max(
                self.decision_backlog_max,
                len(self.request_usage) - self.first_crossing_request,
            )
        if not stalled:
            self.stall_wait = None
        else:
            if self.stall_wait is None:
                # Freeze the capture cohort at the crossing. Later edits cannot extend it.
                self.stall_wait = {b for b in self.pending if b > self.last_progress_boundary}
            self.stall_wait &= {b for b in self.pending if b > self.last_progress_boundary}
            if not self.stall_wait:
                conditions.append("stalled")
        self.flags.update(conditions)
        if conditions:
            self.stop(conditions[0])
        return self.stop_reason

    def report(self):
        first = self.first_crossing_request
        return dict(
            stop_reason=self.stop_reason,
            first_crossing_request=first,
            requests_completed=len(self.request_usage),
            output_tokens_completed=self.output_tokens,
            requests_completed_at_kill=self.requests_at_kill,
            no_progress_tokens=self.no_progress_tokens,
            no_progress_requests=self.no_progress_requests,
            max_identical_run_live=self.max_identical_run_live,
            universe_size=self.universe_size,
            baseline_failing=self.baseline,
            best_failing=self.best,
            failing_trajectory=self.trajectory,
            decision_backlog_max=self.decision_backlog_max,
            post_threshold_tokens_known=(
                self.output_tokens - self.output_at_crossing if first else 0
            ),
            inflight_s_at_stop=self.inflight_s_at_stop,
            inflight_tokens="unknown",
        )


class EventStream:
    """Incremental bytes parser. Consumers must serialize accept/grade on their gate."""

    def __init__(self, gate, on_complete=None):
        self.gate = gate
        self.on_complete = on_complete
        self.buffer = b""
        self.seen = set()
        self.session_id = None
        self.active = None
        self.started_at = None
        self.starts = []
        self.errors = []
        self.last_event = time.monotonic()
        self.event_types_seen = {}
        self.torn_tail = False

    def feed(self, data):
        self.buffer += data
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                value = json.loads(
                    line.decode("utf-8"),
                    parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),
                )
            except (ValueError, UnicodeError) as exc:
                raise TransportAbort("malformed complete event line") from exc
            self.accept(value)

    def finish(self, *, killed=False):
        if self.buffer:
            if not killed:
                raise TransportAbort("partial event at terminal drain")
            self.torn_tail = True
            self.buffer = b""

    def accept(self, e):
        if not isinstance(e, dict):
            raise TransportAbort("event is not an object")
        kind = e.get("type")
        if not isinstance(kind, str) or not kind:
            raise TransportAbort("missing event type")
        self.event_types_seen[kind] = self.event_types_seen.get(kind, 0) + 1
        self.last_event = time.monotonic()
        if kind not in ("step_start", "step_finish", "tool_use", "error"):
            return
        session = e.get("sessionID")
        if (
            not isinstance(session, str)
            or not session
            or (self.session_id and session != self.session_id)
        ):
            raise TransportAbort("missing/mismatched session id")
        self.session_id = session
        part = e.get("part")
        if kind == "error":
            if not isinstance(e.get("error"), dict) or not isinstance(e["error"].get("type"), str):
                raise TransportAbort("malformed error event")
            # Native error events have no part. Their projection is validated above.
            if part is None:
                self.errors.append(e["error"])
                return
        if not isinstance(part, dict) or not isinstance(part.get("id"), str) or not part["id"]:
            raise TransportAbort("missing event part id")
        key = (kind, part["id"])
        if key in self.seen:
            raise TransportAbort("duplicate event")
        self.seen.add(key)
        if kind == "error":
            self.errors.append(e["error"])
            return
        mid = part.get("messageID")
        if not isinstance(mid, str) or not mid:
            raise TransportAbort("missing message id")
        if kind == "step_start":
            if self.active is not None:
                raise TransportAbort("second step_start: retry")
            if mid in self.starts:
                raise TransportAbort("reused message id")
            self.active = mid
            self.starts.append(mid)
            self.started_at = time.monotonic()
            return
        if mid != self.active:
            raise TransportAbort("event message id mismatch")
        if kind == "tool_use":
            try:
                if not isinstance(part["tool"], str) or not part["tool"]:
                    raise TransportAbort("malformed tool name")
                self.gate.tool(part["tool"], part["state"]["input"])
            except (KeyError, TypeError, ValueError):
                raise TransportAbort("malformed tool completion") from None
        if kind == "step_finish":
            usage_tuple(part.get("tokens"))
            self.gate.complete(mid, part.get("tokens"), check=False)
            if self.on_complete:
                self.on_complete(len(self.gate.request_usage))
            self.gate.check()
            self.active = None
            self.started_at = None


def context_overflow(error):
    return (
        isinstance(error, dict)
        and error.get("type") == "provider.invalid-request"
        and error.get("status") == 400
        and bool(
            re.search(
                r"maximum context length is \d+ tokens.*messages resulted in \d+ tokens",
                json.dumps(error),
                re.I | re.S,
            )
        )
    )


def reconcile(stream, export, rc, outcome=None):
    """Match native IDs before normalization, then charge permitted missing completions."""
    stream.finish(killed=outcome in PRECEDENCE[:5] or outcome == "client_exit_hang")
    gate = stream.gate
    exit_hang = outcome == "client_exit_hang"
    if exit_hang:
        outcome = None
        rc = 0
    if stream.errors:
        if rc == 1 and len(stream.errors) == 1 and context_overflow(stream.errors[0]):
            outcome = "context_overflow"
        else:
            raise TransportAbort("error event / Step.Failed")
    killed = outcome in PRECEDENCE[:5]
    if outcome is not None and not killed and outcome != "context_overflow":
        raise TransportAbort("unknown terminal outcome")
    if not killed and not outcome and rc != 0:
        raise TransportAbort("unexpected exit")
    if outcome:
        gate.flags.add(outcome)
    try:
        messages = [m for m in export["messages"] if m.get("type") == "assistant"]
    except (KeyError, TypeError, AttributeError):
        raise TransportAbort("bad export") from None
    seen = set()
    extras = []
    for i, m in enumerate(messages):
        mid = m.get("id")
        if not isinstance(mid, str) or not mid or mid in seen:
            raise TransportAbort("export message id missing/duplicate")
        seen.add(mid)
        if m.get("retry"):
            raise TransportAbort("export retry")
        error = m.get("error")
        if mid in gate.usage:
            if error or usage_tuple(m.get("tokens")) != gate.usage[mid]:
                raise TransportAbort("export usage/error mismatch")
            continue
        if error:
            allowed = i == len(messages) - 1 and (
                (killed and error.get("type") == "aborted")
                or (outcome == "context_overflow" and context_overflow(error))
            )
            if not allowed:
                raise TransportAbort("unexpected assistant error")
            if m.get("tokens") is not None:
                raise TransportAbort("interrupted/rejected assistant carries usage")
            continue
        if not m.get("finish"):
            raise TransportAbort("unpublished assistant has no finish")
        extras.append(m)
        if not killed and (outcome or i != len(messages) - 1 or mid != stream.active):
            raise TransportAbort("unmatched export assistant")
    if not set(gate.usage) <= seen:
        raise TransportAbort("live message missing in export")
    if not messages:
        raise TransportAbort("empty assistant export")
    if exit_hang and messages[-1].get("finish") not in ("stop", "length", "content-filter"):
        raise TransportAbort("client silent, worker idle: session not finished")
    if not killed and not outcome and len(extras) > 1:
        raise TransportAbort("multiple unmatched assistants")
    if not killed and not outcome and stream.active and stream.active not in seen:
        raise TransportAbort("unfinished live message absent from export")
    for m in extras:
        gate.complete(m["id"], m.get("tokens"))
    gate.check()
    return gate.primary
