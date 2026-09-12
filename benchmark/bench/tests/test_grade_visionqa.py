"""Grading rules for visionqa (M39, docs/vision-smoke-m39.md), per source:
    ChartQA   relaxed: numeric within +-5% (after stripping %,$,commas), else normalized exact
    ScreenQA  normalized exact match OR token-F1 >= 0.5
    AI2D      option letter (accepts "B", "B)", or the option text)
    TextVQA   VQA accuracy: min(matches/3, 1) over the 10 references
Plus one end-to-end grade_visionqa() test wired through the shared convergence postprocessor.
"""
import bench.grade as GR


# --------------------------------------------------------------------------- extraction
def test_extract_prefers_boxed_over_last_line():
    assert GR._visionqa_extract("blah\n\\boxed{42}\nmore text") == "42"


def test_extract_falls_back_to_last_nonempty_line():
    assert GR._visionqa_extract("reasoning...\n\nThe answer is Blue\n\n") == "The answer is Blue"


def test_extract_returns_none_for_empty_content():
    assert GR._visionqa_extract("") is None
    assert GR._visionqa_extract(None) is None


# --------------------------------------------------------------------------- ChartQA relaxed
def test_chartqa_numeric_within_5_percent_matches():
    assert GR._visionqa_chartqa_ok("12.4", "12") is True     # 3.3% off
    assert GR._visionqa_chartqa_ok("12.7", "12") is False    # 5.8% off


def test_chartqa_strips_percent_dollar_commas_before_numeric_compare():
    assert GR._visionqa_chartqa_ok("$1,200", "1200") is True
    assert GR._visionqa_chartqa_ok("45%", "45") is True


def test_chartqa_percent_vs_fraction_convention_is_a_mismatch():
    """"42%" and "0.42" mean the same real-world value in different unit conventions, but the
    spec's rule only strips symbols (%,$,commas) -- it does NOT do a percent<->fraction unit
    conversion. So these are the same numeric value under the letter of the rule (42 vs 0.42):
    a deliberate MISMATCH, not a bug."""
    assert GR._visionqa_chartqa_ok("42%", "0.42") is False


def test_chartqa_falls_back_to_normalized_exact_match_for_non_numeric_answers():
    assert GR._visionqa_chartqa_ok("The Blue line", "blue line") is True
    assert GR._visionqa_chartqa_ok("Red", "Blue") is False


def test_chartqa_zero_gold_requires_exact_zero():
    assert GR._visionqa_chartqa_ok("0", "0") is True
    assert GR._visionqa_chartqa_ok("0.5", "0") is False


def test_chartqa_none_prediction_never_matches():
    assert GR._visionqa_chartqa_ok(None, "12") is False


# --------------------------------------------------------------------------- ScreenQA
def test_screenqa_normalized_exact_match():
    assert GR._visionqa_screenqa_ok("12 exercises", ["12 exercises", "a total of 12 exercises"])
    assert GR._visionqa_screenqa_ok("THE 12 Exercises!", ["12 exercises"])  # case/article/punct


def test_screenqa_token_f1_partial_credit_over_threshold():
    # pred="12 total exercises" vs gold="a total of 12 exercises": common {total,12,exercises}=3
    # over normalized pred len 3, gold len 4 -> P=1.0 R=0.75 F1=0.857 >= 0.5
    assert GR._visionqa_screenqa_ok("12 total exercises", ["a total of 12 exercises"]) is True


def test_screenqa_below_f1_threshold_and_no_exact_match_fails():
    assert GR._visionqa_screenqa_ok("banana", ["12 exercises"]) is False


def test_screenqa_empty_prediction_never_matches():
    assert GR._visionqa_screenqa_ok("", ["12"]) is False
    assert GR._visionqa_screenqa_ok(None, ["12"]) is False


# --------------------------------------------------------------------------- AI2D
def test_ai2d_bare_letter_matches_case_insensitively():
    assert GR._visionqa_ai2d_ok("B", "b", ["w", "x", "y", "z"]) is True


def test_ai2d_letter_with_paren_matches():
    assert GR._visionqa_ai2d_ok("B)", "B", ["w", "x", "y", "z"]) is True
    assert GR._visionqa_ai2d_ok("(B)", "B", ["w", "x", "y", "z"]) is True


def test_ai2d_wrong_letter_fails():
    assert GR._visionqa_ai2d_ok("A", "B", ["w", "x", "y", "z"]) is False


def test_ai2d_option_text_matches_when_letter_is_absent():
    assert GR._visionqa_ai2d_ok("the oblong one", "C", ["egg", "elliptic", "The Oblong one", "top"]) is True


def test_ai2d_wrong_option_text_fails():
    assert GR._visionqa_ai2d_ok("egg", "C", ["egg", "elliptic", "oblong", "top"]) is False


def test_ai2d_empty_prediction_never_matches():
    assert GR._visionqa_ai2d_ok("", "B", ["w", "x", "y", "z"]) is False


# --------------------------------------------------------------------------- TextVQA
def test_textvqa_partial_credit_two_of_ten():
    refs = ["dakota"] * 2 + ["nope"] * 8
    assert round(GR._visionqa_textvqa_score("Dakota", refs), 3) == 0.667


def test_textvqa_three_or_more_saturates_at_one():
    refs = ["dakota"] * 3 + ["nope"] * 7
    assert GR._visionqa_textvqa_score("dakota", refs) == 1.0
    refs_more = ["dakota"] * 7 + ["nope"] * 3
    assert GR._visionqa_textvqa_score("dakota", refs_more) == 1.0


def test_textvqa_zero_matches_scores_zero():
    refs = ["nope"] * 10
    assert GR._visionqa_textvqa_score("dakota", refs) == 0.0


def test_textvqa_empty_prediction_or_refs_scores_zero():
    assert GR._visionqa_textvqa_score("", ["dakota"] * 10) == 0.0
    assert GR._visionqa_textvqa_score("dakota", []) == 0.0


# --------------------------------------------------------------------------- grade_visionqa (e2e)
def _meta_item(id_, source_kind, answer, options=None):
    return {"id": id_, "prompt": "q", "answer": answer, "options": options,
            "meta": {"source_kind": source_kind}}


def test_grade_visionqa_end_to_end(monkeypatch):
    rows = [
        {"id": "chartqa-000", "content": "\\boxed{12}", "completion_tokens": 10,
         "thinking_budget": 1000, "finish_reason": "stop"},
        {"id": "ai2d-000", "content": "\\boxed{B}", "completion_tokens": 10,
         "thinking_budget": 1000, "finish_reason": "stop"},
        {"id": "textvqa-000", "content": "\\boxed{dakota}", "completion_tokens": 10,
         "thinking_budget": 1000, "finish_reason": "stop"},
        # a non-converged row (budget hit): acc_strict must charge this as 0 regardless of content
        {"id": "screenqa-000", "content": "\\boxed{12 exercises}", "completion_tokens": 1000,
         "thinking_budget": 1000, "finish_reason": "stop"},
    ]
    monkeypatch.setattr(GR, "_rows", lambda m, n, **kw: rows)
    meta = [
        _meta_item("chartqa-000", "chartqa", "12"),
        _meta_item("ai2d-000", "ai2d", "B", options=["w", "x", "y", "z"]),
        _meta_item("textvqa-000", "textvqa", ["dakota"] * 10),
        _meta_item("screenqa-000", "screenqa", ["12 exercises"]),
    ]
    monkeypatch.setattr(GR.benchmarks, "load", lambda name, limit, seed: meta)

    out = GR.grade_visionqa("visionqa", "m")
    assert out["n"] == 4
    assert out["correct"] == 4                 # all four raw predictions are individually correct
    assert out["per_source"] == {"chartqa": 1.0, "ai2d": 1.0, "textvqa": 1.0, "screenqa": 1.0}

    full = GR.grade("visionqa", "m")           # runs through _finalize's convergence vector
    assert full["acc"] == 1.0                  # raw correctness, convergence-blind
    # the screenqa row hit its thinking_budget (completion_tokens >= thinking_budget) -> not
    # converged -> acc_strict charges it as 0 even though its raw answer was right
    assert full["acc_strict"] == 0.75
