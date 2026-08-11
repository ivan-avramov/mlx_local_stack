"""Agentic outcome taxonomy, per-session counters, and the runaway loop guard.

An agentic run ends in exactly one labelled OUTCOME, and carries counters describing HOW it got
there. Before this, `agent_loop` reported only "did it submit", so the two failure modes that
actually end a session were unrepresentable:

  * TOOL_ERROR_LOOP — the model calls a nonexistent tool and ignores the corrective feedback.
    Observed in the wild at 400+ consecutive identical invalid calls while the harness kept
    returning the correct tool list. Under a bare turn cap that reads as "ran out of turns",
    which is the same label a model working productively would get.
  * DEADLINE — a model that is fast per token but slowest to finish, because it loops. Tokens
    per second is a vanity metric; a blown deadline is a scored outcome, not an excluded run.

The guard is deliberately cheap and mechanical: it converts an unbounded burn into a 3-turn
datum. It is NOT a quality judgement — a guarded abort is recorded as its own outcome so it can
never be silently mistaken for a model that merely failed the task.
"""
import json
from dataclasses import dataclass, field

# Terminal states. Closed set: an unrecognised label must fail loudly rather than quietly
# create a new bucket that no report knows how to read.
SOLVED = "solved"
FAILED_TESTS = "failed_tests"
NO_SUBMIT = "no_submit"                 # model ended its turn with prose and never submitted
TURN_CAP = "turn_cap"                   # hit max_turns while still working
DEADLINE = "deadline"                   # blew the wall-clock budget
TOOL_ERROR_LOOP = "tool_error_loop"     # guard tripped: stuck calling invalid tools
MALFORMED_EDIT = "malformed_edit"       # produced an edit/patch that could not be applied
CONTEXT_EXHAUSTED = "context_exhausted"
SERVER_ERROR = "server_error"

OUTCOMES = (SOLVED, FAILED_TESTS, NO_SUBMIT, TURN_CAP, DEADLINE, TOOL_ERROR_LOOP,
            MALFORMED_EDIT, CONTEXT_EXHAUSTED, SERVER_ERROR)


def validate_outcome(outcome: str) -> str:
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}; expected one of {OUTCOMES}")
    return outcome


def _canonical(call: dict) -> str:
    """A call's identity for repeat detection: name + arguments with keys SORTED. A model
    re-emitting the same call with its keys in a different order is still repeating itself, and
    raw-string comparison would miss it."""
    args = call.get("args") or {}
    try:
        blob = json.dumps(args, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = str(sorted(map(str, args.items()))) if hasattr(args, "items") else str(args)
    return f"{call.get('name')}::{blob}"


@dataclass
class Counters:
    """Per-session tool-use statistics. `observe` is called once per tool call, in order."""

    turns: int = 0
    tool_calls: int = 0
    unknown_tool_calls: int = 0
    arg_schema_violations: int = 0
    repeat_identical_calls: int = 0
    max_identical_repeat: int = 1
    wall_s: float = 0.0
    completion_tokens: int = 0
    # None = no error ever occurred, so "did it recover" is N/A rather than False. Reporting a
    # blanket False would make a clean run look like a failure to recover.
    recovered_after_error: bool | None = None
    turns_to_recovery: int | None = None

    _last_key: str | None = field(default=None, repr=False)
    _streak: int = field(default=0, repr=False)
    _first_error_turn: int | None = field(default=None, repr=False)

    def observe(self, call: dict, schema: dict, turn: int | None = None) -> None:
        self.tool_calls += 1
        name = call.get("name")
        spec = schema.get(name)
        bad = False
        if spec is None:
            self.unknown_tool_calls += 1
            bad = True
        else:
            args = call.get("args") or {}
            missing = [a for a in spec.get("required", []) if a not in args]
            wrong = [k for k, t in (spec.get("types") or {}).items()
                     if k in args and not isinstance(args[k], t)]
            if missing or wrong:
                self.arg_schema_violations += 1
                bad = True

        key = _canonical(call)
        if key == self._last_key:
            self._streak += 1
            self.repeat_identical_calls += 1
        else:
            self._streak = 1
            self._last_key = key
        self.max_identical_repeat = max(self.max_identical_repeat, self._streak)

        # Recovery: the FIRST bad call arms the measurement; the first subsequent good call
        # answers it. This is the competence that matters most in an agentic loop — whether the
        # model acts on an error message at all.
        if bad:
            if self._first_error_turn is None:
                self._first_error_turn = turn if turn is not None else self.tool_calls
                self.recovered_after_error = False
        elif self.recovered_after_error is False and self.turns_to_recovery is None:
            self.recovered_after_error = True
            now = turn if turn is not None else self.tool_calls
            self.turns_to_recovery = now - (self._first_error_turn or now)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


@dataclass
class LoopGuard:
    """Aborts a session that is stuck rather than merely slow.

    Two independent triggers, because they catch different pathologies:
      * `max_identical` — a CONSECUTIVE run of byte-identical calls. Consecutive, not cumulative:
        re-reading the same file later in a long session is normal behaviour, and counting that
        would abort healthy runs.
      * `max_unknown` — cumulative calls to tools that do not exist. A model inventing a NEW
        nonexistent name every turn never trips the repeat detector but is just as stuck.

    Either threshold at 0 disables that trigger.
    """

    max_identical: int = 3
    max_unknown: int = 5

    def should_abort(self, counters: Counters) -> str | None:
        if self.max_identical and counters.max_identical_repeat >= self.max_identical:
            return TOOL_ERROR_LOOP
        if self.max_unknown and counters.unknown_tool_calls >= self.max_unknown:
            return TOOL_ERROR_LOOP
        return None
