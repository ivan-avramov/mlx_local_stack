"""Agentic failure taxonomy: counters, the loop guard, and labelled outcomes.

WHY. `agent_loop.run_agent` feeds an unknown tool call back as `ERROR: unknown tool 'x'` and
counts NOTHING. It has no deadline and no repeat detection, and `max_turns=12` is its only
runaway protection. So the two failure modes that actually end an agentic session are invisible
to this harness:

  * A model that calls a nonexistent tool and IGNORES the corrective feedback, repeating the same
    invalid call indefinitely. Observed in the wild at 400+ consecutive identical invalid calls
    while the harness kept returning the correct tool list. In our data that would appear as
    `turns=12, submitted=None` — indistinguishable from "ran out of turns while working".
  * A model that is fast per token yet slowest to finish, because it loops. Throughput is a vanity
    metric; time-to-outcome is the deployment property, and a blown deadline must be a SCORED
    outcome, not an excluded run.

The loop guard is what converts the first into a 3-turn datum instead of an unbounded burn, and
`recovered_after_error` / `turns_to_recovery` measure the competence that matters most in an
agentic loop: does the model act on an error message?
"""
import pytest

import bench.agent_outcomes as AO


SCHEMA = {"read_file": {"required": ["path"], "types": {"path": str}},
          "run_tests": {"required": [], "types": {}}}


def _call(name, args):
    return {"name": name, "args": args}


# --------------------------------------------------------------------- counters
def test_unknown_tool_is_counted():
    c = AO.Counters()
    c.observe(_call("serch_web", {"q": "x"}), SCHEMA)
    assert c.unknown_tool_calls == 1 and c.tool_calls == 1
    assert c.arg_schema_violations == 0, "an unknown tool cannot also be an arg violation"


def test_known_tool_with_good_args_is_clean():
    c = AO.Counters()
    c.observe(_call("read_file", {"path": "a.py"}), SCHEMA)
    assert (c.unknown_tool_calls, c.arg_schema_violations) == (0, 0)


def test_missing_required_arg_is_a_schema_violation():
    c = AO.Counters()
    c.observe(_call("read_file", {}), SCHEMA)
    assert c.arg_schema_violations == 1


def test_wrong_arg_type_is_a_schema_violation():
    c = AO.Counters()
    c.observe(_call("read_file", {"path": 42}), SCHEMA)
    assert c.arg_schema_violations == 1


def test_identical_repeats_are_tracked_by_name_and_args():
    c = AO.Counters()
    for _ in range(3):
        c.observe(_call("read_file", {"path": "a.py"}), SCHEMA)
    assert c.max_identical_repeat == 3 and c.repeat_identical_calls == 2


def test_arg_order_does_not_defeat_repeat_detection():
    """A model re-emitting the same call with keys in a different order is still repeating."""
    c = AO.Counters()
    c.observe(_call("f", {"a": 1, "b": 2}), {"f": {"required": [], "types": {}}})
    c.observe(_call("f", {"b": 2, "a": 1}), {"f": {"required": [], "types": {}}})
    assert c.max_identical_repeat == 2


def test_different_args_are_not_repeats():
    c = AO.Counters()
    c.observe(_call("read_file", {"path": "a.py"}), SCHEMA)
    c.observe(_call("read_file", {"path": "b.py"}), SCHEMA)
    assert c.max_identical_repeat == 1 and c.repeat_identical_calls == 0


# --------------------------------------------------------------------- recovery
def test_recovery_after_an_invalid_call_is_measured():
    """The corrective-feedback-recovery metric: the model was told the tool does not exist and
    then made a valid call."""
    c = AO.Counters()
    c.observe(_call("nope", {}), SCHEMA, turn=1)
    c.observe(_call("read_file", {"path": "a.py"}), SCHEMA, turn=2)
    assert c.recovered_after_error is True and c.turns_to_recovery == 1


def test_no_recovery_when_the_model_keeps_repeating_the_invalid_call():
    c = AO.Counters()
    for t in (1, 2, 3):
        c.observe(_call("nope", {}), SCHEMA, turn=t)
    assert c.recovered_after_error is False and c.turns_to_recovery is None


def test_recovery_is_not_claimed_when_nothing_went_wrong():
    c = AO.Counters()
    c.observe(_call("read_file", {"path": "a.py"}), SCHEMA, turn=1)
    assert c.recovered_after_error is None, "no error occurred, so recovery is N/A — not False"


# --------------------------------------------------------------------- loop guard
def test_guard_aborts_on_the_third_identical_call():
    g = AO.LoopGuard(max_identical=3, max_unknown=5)
    c = AO.Counters()
    for i in range(2):
        c.observe(_call("nope", {}), SCHEMA)
        assert g.should_abort(c) is None, f"must not abort at {i + 1} repeats"
    c.observe(_call("nope", {}), SCHEMA)
    assert g.should_abort(c) == AO.TOOL_ERROR_LOOP


def test_guard_aborts_on_accumulated_unknown_tools_even_if_all_different():
    """A model inventing a NEW nonexistent tool every turn never trips the repeat detector, but
    it is just as stuck."""
    g = AO.LoopGuard(max_identical=3, max_unknown=5)
    c = AO.Counters()
    for i in range(4):
        c.observe(_call(f"ghost{i}", {}), SCHEMA)
        assert g.should_abort(c) is None
    c.observe(_call("ghost5", {}), SCHEMA)
    assert g.should_abort(c) == AO.TOOL_ERROR_LOOP


def test_guard_ignores_legitimate_repeated_reads():
    """Reading the same file twice in a long session is normal; only the tight identical-repeat
    run is pathological, so the threshold is on the CONSECUTIVE streak."""
    g = AO.LoopGuard(max_identical=3, max_unknown=5)
    c = AO.Counters()
    c.observe(_call("read_file", {"path": "a.py"}), SCHEMA)
    c.observe(_call("read_file", {"path": "b.py"}), SCHEMA)
    c.observe(_call("read_file", {"path": "a.py"}), SCHEMA)
    c.observe(_call("read_file", {"path": "b.py"}), SCHEMA)
    assert g.should_abort(c) is None
    # The streak is CONSECUTIVE, so alternating a/b/a/b never exceeds 1 — which is exactly why
    # re-reading a file later in a long session cannot trip the guard.
    assert c.max_identical_repeat == 1
    assert c.repeat_identical_calls == 0


def test_disabled_guard_never_aborts():
    g = AO.LoopGuard(max_identical=0, max_unknown=0)
    c = AO.Counters()
    for _ in range(50):
        c.observe(_call("nope", {}), SCHEMA)
    assert g.should_abort(c) is None


# --------------------------------------------------------------------- serialisation
def test_counters_round_trip_as_a_dict():
    c = AO.Counters()
    c.observe(_call("nope", {}), SCHEMA, turn=1)
    d = c.as_dict()
    assert d["unknown_tool_calls"] == 1 and d["tool_calls"] == 1
    assert set(d) >= {"turns", "tool_calls", "unknown_tool_calls", "arg_schema_violations",
                      "repeat_identical_calls", "max_identical_repeat",
                      "recovered_after_error", "turns_to_recovery", "wall_s",
                      "completion_tokens"}
    import json
    json.dumps(d)          # must be jsonl-persistable


def test_outcomes_are_a_closed_set():
    assert AO.TOOL_ERROR_LOOP in AO.OUTCOMES
    assert {"solved", "failed_tests", "no_submit", "turn_cap", "deadline", "tool_error_loop",
            "malformed_edit", "context_exhausted", "server_error"} == set(AO.OUTCOMES)


def test_unknown_outcome_is_rejected():
    with pytest.raises(ValueError, match="unknown outcome"):
        AO.validate_outcome("mostly_fine")
