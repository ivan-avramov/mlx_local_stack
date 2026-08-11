"""Tests for bench.traces — the module that says HOW a generation failed to converge, and
that compresses the thinking trace so the answer is recoverable from the results jsonl instead
of requiring a bespoke live re-probe (the harness gap recorded in the campaign's
"Qwen3.6-27B-MLX-8bit light — DNF" entry).

The two fixtures below reproduce the two REAL signatures documented in docs/campaign-results.md,
because the whole value of this module is separating them: repetition is a sampling/quant defect,
meander is a temperature knee (the temperature-ladder recipe).
  - gemma at temp 1.0        -> one line repeated 34-78x, unique-line ratio ~44%
  - Qwen3.6-27B-MLX-8bit     -> 8-gram/20-gram uniqueness ~1.00, "wait"x7 / "actually"x3
"""
import inspect

import bench.convergence as C
import bench.traces as T


# --------------------------------------------------------------------------- real signatures
def repetition_trace():
    """gemma temp-1.0 shape: 40 copies of one line among 30 distinct ones -> unique ratio ~0.44."""
    stuck = "So the answer must be the maximum of the two remaining candidate windows."
    distinct = [f"Considering candidate window number {i} with left bound {i * 3} and right bound {i * 7} now."
                for i in range(30)]
    return "\n".join(distinct + [stuck] * 40)


def meander_trace():
    """Qwen shape: coherent, genuinely novel step-by-step reasoning that never concludes.

    Every line carries per-line-unique numbers so no 8-gram recurs (uniqueness ~1.0), exactly as
    the capped-budget probe of aime24-72 measured, plus the backtracking markers it showed."""
    lines = [f"So the coefficient of x^{i} in that expansion works out to {i * 3 + 7} over {i + 2}, "
             f"and simplifying leaves {i * 11 + 5} in the numerator."
             for i in range(25)]
    lines += [
        "Wait, that contradicts the parity argument I set up several steps earlier above.",
        "wait, let me recount the boundary cases before committing to any closed form here.",
        "Actually the substitution u = 1 - t is cleaner and avoids the awkward branch entirely.",
        "Hmm, but then the endpoints disagree, so let me reconsider the whole normalisation.",
        "Actually, re-deriving from scratch: suppose instead the sequence alternates in sign.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- trace_stats
def test_stats_of_none_and_empty_are_zeros_with_none_ratios():
    for empty in (None, "", "   \n\n"):
        s = T.trace_stats(empty)
        assert s["chars"] == len(empty or "")
        assert s["lines"] == 0
        assert s["unique_line_ratio"] is None
        assert s["max_line_repeat"] == 0
        assert s["ngram8_unique"] is None
        assert s["ngram20_unique"] is None
        assert s["backtrack_markers"] == {"wait": 0, "actually": 0, "hmm": 0, "let me reconsider": 0}


def test_stats_reproduce_the_gemma_repetition_signature():
    s = T.trace_stats(repetition_trace())
    assert s["lines"] == 70
    assert s["max_line_repeat"] == 40                      # campaign range 34-78
    assert 0.40 <= s["unique_line_ratio"] <= 0.48          # campaign ~44%
    assert s["ngram8_unique"] < 0.6                        # verbatim repeats collapse the n-grams


def test_stats_reproduce_the_qwen_meander_signature():
    s = T.trace_stats(meander_trace())
    assert s["max_line_repeat"] == 1                        # no verbatim looping at all
    assert s["ngram8_unique"] > 0.95                        # campaign ~1.00
    assert s["ngram20_unique"] > 0.95                        # campaign ~1.00
    assert s["backtrack_markers"]["wait"] == 2
    assert s["backtrack_markers"]["actually"] == 2
    assert s["backtrack_markers"]["hmm"] == 1
    assert s["backtrack_markers"]["let me reconsider"] == 1


def test_markers_are_whole_words_and_case_insensitive():
    s = T.trace_stats("Waiting for the awaited result; WAIT. wait! hmmm Hmm, actually_not actually.")
    assert s["backtrack_markers"]["wait"] == 2              # not "Waiting"/"awaited"
    assert s["backtrack_markers"]["hmm"] == 1               # not "hmmm"
    assert s["backtrack_markers"]["actually"] == 1          # not "actually_not"


def test_only_nontrivial_lines_count_matching_convergence_convention():
    # >20 stripped chars, same rule as convergence.looks_like_loop, so the two modules agree.
    text = "short\ntiny line\n" + "\n".join(["a genuinely long enough reasoning line here"] * 3)
    s = T.trace_stats(text)
    assert s["lines"] == 3
    assert s["max_line_repeat"] == 3


def test_ngram_ratio_is_none_when_there_are_too_few_words():
    s = T.trace_stats("only five words here now")             # 5 words
    assert s["ngram8_unique"] is None                         # "no data" must not read as 1.0
    assert s["ngram20_unique"] is None
    s2 = T.trace_stats(" ".join(f"w{i}" for i in range(10)))   # 10 words
    assert s2["ngram8_unique"] == 1.0                         # 3 windows, all distinct
    assert s2["ngram20_unique"] is None


def test_ngram_ratio_counts_repeated_windows():
    # 16 words = 9 8-grams, of which windows 0 and 8 are identical -> 8 distinct / 9.
    s = T.trace_stats(" ".join(["a b c d e f g h"] * 2))
    assert abs(s["ngram8_unique"] - 8 / 9) < 1e-9


# --------------------------------------------------------------------------- compress_trace
def test_compress_keeps_whole_text_in_both_halves_when_it_fits():
    # A naive text[:head] / text[-tail:] pair returns overlapping fragments here (or, at
    # tail == 0, an empty tail) — the point of the no-truncation branch.
    text = "line one\nline two\nline three"
    c = T.compress_trace(text, head=4096, tail=4096)
    assert c["truncated"] is False
    assert c["reasoning_head"] == text
    assert c["reasoning_tail"] == text
    assert c["reasoning_chars"] == len(text)


def test_compress_truncates_a_budget_saturating_trace():
    text = "".join(str(i % 10) for i in range(40000))
    c = T.compress_trace(text, head=100, tail=50)
    assert c["truncated"] is True
    assert c["reasoning_chars"] == 40000                     # the FULL length is still recorded
    assert c["reasoning_head"] == text[:100]                 # how it set the problem up
    assert c["reasoning_tail"] == text[-50:]                 # what it was doing when it ran out


def test_compress_boundary_is_exactly_head_plus_tail():
    text = "x" * 150
    assert T.compress_trace(text, head=100, tail=50)["truncated"] is False
    assert T.compress_trace("x" * 151, head=100, tail=50)["truncated"] is True


def test_compress_of_none_does_not_raise():
    c = T.compress_trace(None)
    assert c == {"reasoning_chars": 0, "reasoning_head": "", "reasoning_tail": "", "truncated": False}


# --------------------------------------------------------------------------- classify
CONV = {"id": "ok", "finish_reason": "stop", "completion_tokens": 3000, "thinking_budget": 81920}
BUDGET = {"id": "b", "finish_reason": "stop", "completion_tokens": 82763, "thinking_budget": 81920}
LENGTH = {"id": "l", "finish_reason": "length", "completion_tokens": 102400, "thinking_budget": 81920}


def test_error_row_has_no_class():
    assert T.classify({"id": "e", "error": "connection reset"}) is None
    # even with a trace attached, an errored row is not a usable generation
    assert T.classify({"id": "e", "error": "boom"}, trace_text=repetition_trace()) is None


def test_converged_row_has_no_class():
    assert T.classify(CONV) is None
    assert T.classify(CONV, trace_text=meander_trace()) is None


def test_unusable_row_without_completion_tokens_has_no_class():
    assert T.classify({"id": "u", "finish_reason": "stop", "completion_tokens": None,
                       "thinking_budget": 81920}) is None


def test_repetition_is_detected_on_a_budget_hit():
    assert T.classify(BUDGET, trace_text=repetition_trace()) == "degenerate_repetition"


def test_repetition_wins_over_length_because_we_act_on_the_mechanism():
    # A repetition loop that ALSO hit max_tokens is still a repetition loop; reporting
    # "max_tokens" would hide the sampling/quant defect.
    assert T.classify(LENGTH, trace_text=repetition_trace()) == "degenerate_repetition"


def test_length_without_repetition_is_max_tokens():
    assert T.classify(LENGTH, trace_text=meander_trace()) == "max_tokens"
    assert T.classify(LENGTH) == "max_tokens"


def test_budget_hit_without_a_trace_is_an_honest_unknown():
    assert T.classify(BUDGET) == "budget_hit"
    assert T.classify(BUDGET, trace_text="") == "budget_hit"


def test_budget_hit_with_a_high_novelty_trace_is_meander():
    assert T.classify(BUDGET, trace_text=meander_trace()) == "meander"


def test_classify_separates_the_two_documented_signatures():
    assert T.classify(BUDGET, trace_text=meander_trace()) != \
        T.classify(BUDGET, trace_text=repetition_trace())


def test_persisted_reasoning_stats_are_used_and_win_over_trace_text():
    row = dict(BUDGET, reasoning_stats=T.trace_stats(repetition_trace()))
    assert T.classify(row, trace_text=meander_trace()) == "degenerate_repetition"
    row2 = dict(BUDGET, reasoning_stats=T.trace_stats(meander_trace()))
    assert T.classify(row2) == "meander"


def test_short_traces_are_not_misclassified():
    # Fewer than 20 lines: too little evidence to call a loop, and too little novelty
    # evidence to call a meander -> the honest unknown.
    short_repeat = "\n".join(["the same line over and over again here"] * 5)
    assert T.classify(BUDGET, trace_text=short_repeat) == "budget_hit"
    # Fewer than 8 words: the n-gram ratio is None, which must not pass the novelty test.
    assert T.classify(BUDGET, trace_text="far too short to judge") == "budget_hit"


def test_meander_needs_low_line_repetition_too():
    # High n-gram novelty but a heavily repeated line is not a meander (belt-and-braces:
    # both signals must agree before we send an operator to the temperature ladder).
    stats = {"lines": 40, "unique_line_ratio": 0.9, "max_line_repeat": 25,
             "ngram8_unique": 0.99, "ngram20_unique": 1.0, "chars": 1,
             "backtrack_markers": {}}
    assert T.classify(dict(BUDGET, reasoning_stats=stats)) == "budget_hit"


def test_repetition_thresholds_match_convergence_so_the_modules_cannot_drift():
    defaults = inspect.signature(C.looks_like_loop).parameters
    assert T.REPEAT_MIN_LINES == defaults["min_lines"].default
    assert T.REPEAT_MAX_REPEAT == defaults["max_repeat"].default
    assert T.REPEAT_MIN_UNIQUE_RATIO == defaults["min_unique_ratio"].default


def test_repetition_detection_agrees_with_looks_like_loop_on_both_fixtures():
    for text, expected in ((repetition_trace(), True), (meander_trace(), False)):
        assert C.looks_like_loop(text) is expected
        assert (T.classify(BUDGET, trace_text=text) == "degenerate_repetition") is expected


# --------------------------------------------------------------------------- summarize
def test_summarize_counts_kinds_and_skips_converged_and_error_rows():
    rows = [
        CONV,
        dict(BUDGET, id="b1"),
        dict(BUDGET, id="b2", reasoning_stats=T.trace_stats(meander_trace())),
        dict(LENGTH, id="l1"),
        dict(LENGTH, id="r1", reasoning_stats=T.trace_stats(repetition_trace())),
        {"id": "e1", "error": "net"},
    ]
    s = T.summarize(rows)
    assert s["n"] == 4                                    # converged + error rows skipped
    assert s["kinds"] == {"budget_hit": 1, "meander": 1, "max_tokens": 1,
                          "degenerate_repetition": 1}
    assert s["ids_by_kind"]["meander"] == ["b2"]
    assert s["ids_by_kind"]["degenerate_repetition"] == ["r1"]


def test_summarize_of_an_empty_or_all_converged_run():
    assert T.summarize([]) == {"n": 0, "kinds": {}, "ids_by_kind": {}}
    assert T.summarize([CONV, CONV]) == {"n": 0, "kinds": {}, "ids_by_kind": {}}
