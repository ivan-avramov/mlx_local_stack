"""A derived timeout must be interpretable, bounded, and honest about what it cannot observe.

The defect being fixed (measured 2026-08-13): a fixed 3600 s client timeout against an 81,920-token
budget means a model decoding at 10-16 tok/s can NEVER be scored as a budget hit — the client always
gives up first and the worker keeps generating, which is what orphaned Tier-0 rev A. The fix must not
become "a much bigger number", or a looping model burns hours unattended.
"""
import bench.budget_timeout as BT


# ---------------------------------------------------------------- the derivation
def test_fast_model_gets_a_timeout_above_its_budget_time():
    """Ornith at ~140 tok/s needs ~10 min for 81,920 tok; the timeout must exceed that."""
    d = BT.derive_timeout(81920, 140.0)
    assert d["budget_time_s"] == round(81920 / 140.0, 1)
    assert d["timeout_s"] > d["budget_time_s"]
    assert d["budget_observable"] is True


def test_slow_model_budget_time_is_recognised_as_LONGER_than_the_old_fixed_timeout():
    """THE regression: at 15 tok/s the budget needs ~91 min, well past the old 3600 s default."""
    d = BT.derive_timeout(81920, 15.0)
    assert d["budget_time_s"] > 3600, "this is exactly the case the fixed timeout could not observe"


def test_a_very_slow_model_is_reported_as_budget_NOT_observable_rather_than_silently_clamped():
    """A timeout we cannot interpret must be flagged, not returned as if it meant budget_hit."""
    d = BT.derive_timeout(81920, 5.0)          # ~273 min -> x1.5 = 410 min, past the ceiling
    assert d["timeout_s"] == BT.CEILING_S
    assert d["budget_observable"] is False
    assert "NOT observable" in d["reason"]


def test_there_is_a_hard_CEILING_so_a_looping_model_cannot_run_unbounded():
    assert BT.derive_timeout(81920, 0.5)["timeout_s"] <= BT.CEILING_S
    assert BT.CEILING_S <= 7200


def test_there_is_a_FLOOR_so_a_cold_model_load_is_not_cut_off():
    d = BT.derive_timeout(64, 200.0)           # a trivially small budget
    assert d["timeout_s"] == BT.FLOOR_S


def test_missing_decode_rate_is_flagged_uninterpretable_not_guessed():
    for tps in (None, 0, -1):
        d = BT.derive_timeout(81920, tps)
        assert d["budget_observable"] is False
        assert d["timeout_s"] == BT.CEILING_S


def test_budget_stays_a_fixed_headroom_and_is_never_adjusted():
    """AGENTS.md forbids using thinking_budget as a knob. Only client patience is derived."""
    a = BT.derive_timeout(81920, 140.0)
    b = BT.derive_timeout(81920, 15.0)
    # same budget in, different timeouts out; the budget itself is never returned as changed
    assert "thinking_budget" not in a and "thinking_budget" not in b
    assert a["timeout_s"] != b["timeout_s"]


# ---------------------------------------------------------------- progress / loop detection
def test_clean_stop_under_budget_is_converged():
    r = BT.classify_stall("stop", 3000, 81920, "some reasoning")
    assert r["converged"] is True and r["nonconv_kind"] is None


def test_budget_hit_is_labelled_even_when_finish_reason_is_stop():
    """A budget hit force-injects </think>, so the model EOSes -- finish_reason alone false-passes."""
    r = BT.classify_stall("stop", 81920, 81920, "x")
    assert r["converged"] is False and r["nonconv_kind"] == "budget_hit"


def test_max_tokens_truncation_is_its_own_kind_when_the_budget_was_NOT_reached():
    """Answer ran long but thinking self-terminated -- a different failure with a different fix."""
    r = BT.classify_stall("length", 40000, 81920, "x")
    assert r["nonconv_kind"] == "max_tokens"


def test_a_compound_failure_reports_the_ROOT_CAUSE_and_keeps_the_downstream_one_as_evidence():
    """ct >= budget AND finish=length: both happened. budget_hit is the root cause (thinking never
    self-terminated) and is what the temperature ladder acts on; the truncation must not be lost."""
    r = BT.classify_stall("length", 102400, 81920, "x")
    assert r["nonconv_kind"] == "budget_hit"
    assert r["evidence"]["also_max_tokens"] is True


def test_a_plain_budget_hit_records_that_max_tokens_was_NOT_also_hit():
    assert BT.classify_stall("stop", 81920, 81920, "x")["evidence"]["also_max_tokens"] is False


def test_degenerate_repetition_is_detected_from_a_cycling_tail():
    """The real 'looping' case -- the gemma temp-1.0 pathology."""
    text = "thinking normally for a while. " + "Let me reconsider the approach again. " * 400
    r = BT.classify_stall(None, 50000, 81920, text)
    assert r["nonconv_kind"] == "degenerate_repetition"
    assert r["evidence"]["repeated_cycle"]


def test_long_but_NON_repeating_reasoning_is_meander_not_looping():
    """The qwen3_5-arch pathology. Distinguishing these matters: they have different fixes."""
    text = " ".join(f"step {i} considers a distinct sub-case" for i in range(2000))
    r = BT.classify_stall(None, 50000, 81920, text)
    assert r["nonconv_kind"] == "meander"


def test_normal_prose_is_not_misread_as_a_loop():
    """A false 'looping' label would send us investigating a healthy model."""
    text = ("First I check the empty list. Then I sort the intervals by start time. "
            "Next I sweep with a counter, incrementing on start and decrementing on end. "
            "Finally I return the running maximum, which is the answer. ") * 3
    assert BT.classify_stall("stop", 3000, 81920, text)["converged"] is True


def test_client_timeout_is_labelled_as_OURS_not_as_a_model_property():
    """rev A's cascade came from conflating 'we gave up' with 'the model failed'."""
    r = BT.classify_stall(None, 40000, 81920, "non-repeating reasoning text here", timed_out=True)
    assert r["nonconv_kind"] == "client_timeout"
    assert r["evidence"]["timed_out"] is True
    assert "not a model property" in r["evidence"]["note"]


def test_a_timeout_WITH_a_cycling_trace_is_still_attributed_to_the_model():
    """If we gave up but the trace was looping, the model is the cause and should be labelled so."""
    text = "prefix. " + "again and again and again. " * 400
    r = BT.classify_stall(None, 40000, 81920, text, timed_out=True)
    assert r["nonconv_kind"] == "degenerate_repetition"


def test_repeated_cycle_evidence_is_truncated_so_a_row_cannot_carry_a_50k_string():
    text = "x. " + "a moderately long repeating clause that cycles forever. " * 300
    r = BT.classify_stall(None, 40000, 81920, text)
    assert len(r["evidence"]["repeated_cycle"]) <= 60


def test_short_reasoning_is_never_classified_as_a_cycle():
    assert BT._longest_repeated_tail_cycle("tiny") is None
