"""Loop-shape measurement, validated against KNOWN cases including the real ones from the corpus.

The whole `presence_penalty` decision turns on one number — a cycle's period in TOKENS against the
penalty's 20-token window — so this module gets known-positive AND known-negative tests before any
number it produces is quoted. That discipline is not optional here: two false zeros today came from
trusting an instrument (a `truncated` field that meant storage excerpting, and a results path that
existed on the worker but not the driver).
"""
from bench import cycles


def test_finds_the_SHORTEST_period_not_a_multiple():
    """A 2-char cycle also repeats as 4 and 6 chars. The shortest is the one compared to the window."""
    r = cycles.minimal_repeating_suffix("preamble" + ", g" * 50)
    assert r["period_chars"] == 3, r
    assert r["reps"] == 50, r
    assert r["cycle"] == ", g"


def test_the_real_worst_offender_shape_is_detected():
    """`Ornith-1.0-35B-mlx-uniform-4bit` ifeval id 279: a word-list enumeration collapsed to
    comma-space-letter, measured at 1364 repetitions of a 2-token cycle."""
    r = cycles.minimal_repeating_suffix("some reasoning then " + " g," * 1364)
    assert r["period_chars"] == 3 and r["reps"] == 1364, r


def test_a_COUNTER_VARYING_template_has_NO_exact_cycle():
    """The distinction that decides reachability. `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` Mbpp/430 repeats
    a template with an INCREMENTING coefficient, so every iteration is textually novel and NO presence
    penalty can suppress it — the prior tokens differ. Reporting this as 'no cycle' is correct, and it
    must not be conflated with 'converged'."""
    text = "".join(f"a*b*c*{k}\nNot -198.\n" for k in range(14, 58))
    r = cycles.minimal_repeating_suffix(text)
    assert r["period_chars"] is None and r["reps"] == 0, r
    assert cycles.reachable_by_presence_penalty(None) is None, "unknowable, NOT unreachable"


def test_reachability_is_decided_by_TOKENS_and_the_window_is_explicit():
    assert cycles.reachable_by_presence_penalty(2) is True
    assert cycles.reachable_by_presence_penalty(20) is True
    assert cycles.reachable_by_presence_penalty(21) is False       # one token past the window
    assert cycles.reachable_by_presence_penalty(262) is False      # a real coding-loop period
    # the window is a parameter, because widening it is itself a candidate lever
    assert cycles.reachable_by_presence_penalty(40, context_size=64) is True


def test_period_tokens_returns_None_rather_than_guessing_from_CHARACTERS():
    """Characters are not proportional to tokens on repeated punctuation — the reason this function
    exists. With no tokenizer it must decline, not estimate."""
    assert cycles.period_tokens(", g", tokenizer=None) is None


def test_period_tokens_divides_a_CONCATENATION_to_get_the_steady_state_cost():
    class FakeTok:
        def encode(self, s, add_special_tokens=False):
            return list(range(2 * (len(s) // 3)))      # 2 ids per 3-char cycle
    assert cycles.period_tokens(", g", FakeTok(), copies=8) == 2


def test_non_latin_rate_flags_token_salad_and_ignores_a_monolingual_loop():
    """The vendor's documented failure mode for this knob. The corpus contains its end state — a
    multilingual-salad row — produced with NO penalty, so this measures a RATE to compare arms rather
    than proving causation."""
    assert cycles.non_latin_rate("def f(): return 1  # loop loop loop") == 0.0
    # The real `gemma-4-31B-it-qat-6bit` HumanEval/50 tail. Measured rate 0.182 — language MIXING
    # interleaves scripts rather than replacing them, so the signal lives in the TENS of percent, not
    # near 1.0. Asserted against the measurement; an earlier guess of ">0.2" was wrong about the string,
    # not about the function.
    salad = "ม Да Bra fruitsSRPInterface walked لئے"
    assert 0.15 < cycles.non_latin_rate(salad) < 0.25, cycles.non_latin_rate(salad)
    assert cycles.non_latin_rate("") == 0.0
    assert cycles.non_latin_rate("1234 !!! ((( ") == 0.0          # no letters -> 0, not a crash


def test_describe_is_a_complete_per_row_record():
    d = cycles.describe("thinking " + " case," * 681)
    assert d["period_chars"] == 6 and d["reps"] == 681
    assert d["reachable"] is None            # no tokenizer supplied -> unknowable, not False
    assert d["non_latin_rate"] == 0.0 and d["chars"] > 0
