"""Grading rules for visionqa (M39, docs/vision-smoke-m39.md; cold-review fixes 2026-09-12), per
source:
    ChartQA   relaxed: numeric within +-5% (after stripping %,$,commas), else normalized exact
    ScreenQA  normalized exact match; token-F1 >= 0.5 ONLY when gold normalizes to >= 3 tokens
    AI2D      extract.extract_mc_letter first, else the gold option's own text (label-stripped)
    TextVQA   VQA accuracy: min(matches/3, 1) over the 10 references, standard VQA-eval normalization
Plus grade_visionqa() end-to-end tests: it must read the committed corpus directly (never resolve
images / touch the network) and wire correctly into the shared convergence postprocessor.
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


def test_screenqa_token_f1_applies_when_gold_has_3_or_more_tokens():
    # gold "sign in to your account" normalizes to 4 tokens (article "your" is not stripped) ->
    # F1 eligible. pred "sign in to account" shares {sign,in,to,account}: P=1.0 R=0.75 F1=0.857
    assert GR._visionqa_screenqa_ok("sign in to account", ["sign in to your account"]) is True


def test_screenqa_ruling_f1_never_applies_below_3_gold_tokens(monkeypatch=None):
    """Operator ruling (cold review, 2026-09-12): token-F1 is a partial-credit mechanism for
    multi-word answers; below 3 gold tokens it is too easy to satisfy by chance (e.g. any answer
    sharing one of two words), so short gold answers fall back to EXACT match only."""
    # gold "App Crawler" (2 tokens) vs pred "App Store": would share 1/2 tokens (F1=0.5) if F1
    # applied, but must be WRONG under the <3-token exact-only rule.
    assert GR._visionqa_screenqa_ok("App Store", ["App Crawler"]) is False
    # gold "on" (1 token) vs pred "not on": shares the only token, but must be WRONG.
    assert GR._visionqa_screenqa_ok("not on", ["on"]) is False
    # gold "sign in to your account" (4 tokens, >=3) vs pred "sign in to account": CORRECT via F1.
    assert GR._visionqa_screenqa_ok("sign in to account", ["sign in to your account"]) is True


def test_screenqa_below_f1_threshold_and_no_exact_match_fails():
    assert GR._visionqa_screenqa_ok("banana", ["a total of 12 exercises"]) is False


def test_screenqa_empty_prediction_never_matches():
    assert GR._visionqa_screenqa_ok("", ["12"]) is False
    assert GR._visionqa_screenqa_ok(None, ["12"]) is False


# --------------------------------------------------------------------------- AI2D
_LEAF_CHOICES = ["Egg shaped", "Elliptic Leaf", "Oblong", "Top shaped"]


def test_ai2d_bare_letter_matches_case_insensitively():
    assert GR._visionqa_ai2d_ok("B", "b", ["w", "x", "y", "z"]) is True


def test_ai2d_letter_with_closing_paren_and_trailing_text():
    assert GR._visionqa_ai2d_ok("D) Top shaped", "D", _LEAF_CHOICES) is True


def test_ai2d_letter_with_period_and_trailing_text():
    assert GR._visionqa_ai2d_ok("D. Top shaped", "D", _LEAF_CHOICES) is True


def test_ai2d_answer_is_phrasing():
    assert GR._visionqa_ai2d_ok("The answer is D", "D", _LEAF_CHOICES) is True


def test_ai2d_text_only_answer_matches_option_text():
    assert GR._visionqa_ai2d_ok("top shaped", "D", _LEAF_CHOICES) is True


def test_ai2d_bare_wrong_letter_fails():
    assert GR._visionqa_ai2d_ok("A", "D", _LEAF_CHOICES) is False


def test_ai2d_option_text_matches_when_letter_is_absent():
    assert GR._visionqa_ai2d_ok("the oblong one", "C", ["egg", "elliptic", "The Oblong one", "top"]) is True


def test_ai2d_wrong_option_text_fails():
    assert GR._visionqa_ai2d_ok("egg", "C", ["egg", "elliptic", "oblong", "top"]) is False


def test_ai2d_empty_prediction_never_matches():
    assert GR._visionqa_ai2d_ok("", "B", ["w", "x", "y", "z"]) is False


# --------------------------------------------------------------------------- TextVQA normalization
def test_textvqa_norm_number_words_to_digits():
    assert GR._textvqa_norm("two") == GR._textvqa_norm("2") == "2"


def test_textvqa_norm_handles_dotted_acronyms():
    assert GR._textvqa_norm("U.S.A.") == GR._textvqa_norm("usa") == "usa"


def test_textvqa_norm_strips_colon_in_time_like_answers():
    assert GR._textvqa_norm("12:30") == GR._textvqa_norm("1230") == "1230"


def test_textvqa_norm_contractions_map_unifies_apostrophe_forms():
    assert GR._textvqa_norm("don't") == GR._textvqa_norm("dont") == "don't"


def test_textvqa_norm_strips_articles():
    assert GR._textvqa_norm("the dog") == "dog"


# --------------------------------------------------------------------------- TextVQA scoring
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


def test_textvqa_score_uses_the_vqa_normalization_for_matching():
    assert GR._visionqa_textvqa_score("two", ["2"] * 10) == 1.0
    assert GR._visionqa_textvqa_score("dont", ["don't"] * 10) == 1.0


# --------------------------------------------------------------------------- grade_visionqa (e2e)
def _meta_row(id_, source_kind, answer, choices=None):
    """Shape of a raw committed-jsonl row, as `benchmarks.load_visionqa_meta` returns it --
    `source_kind`/`choices` at the TOP level (NOT nested under "meta"/"options" the way the
    generation-time `benchmarks.load` item shape does)."""
    return {"id": id_, "question": "q", "source_kind": source_kind, "answer": answer,
            "choices": choices}


def test_grade_visionqa_never_touches_the_network_or_resolves_images(monkeypatch):
    """Cold-review requirement: grade_visionqa must read the committed jsonl directly. Both the
    image-resolution seam AND the underlying HF-cache seam are wired to explode if called."""
    def boom_resolve(rows):
        raise AssertionError("grade_visionqa must never call _resolve_visionqa_images")
    monkeypatch.setattr(GR.benchmarks, "_resolve_visionqa_images", boom_resolve)

    import datasets
    def boom_ds(*a, **kw):
        raise AssertionError("grade_visionqa must never call datasets.load_dataset")
    monkeypatch.setattr(datasets, "load_dataset", boom_ds)

    rows = [{"id": "chartqa-000", "content": "\\boxed{12}", "completion_tokens": 5,
            "thinking_budget": 100, "finish_reason": "stop"}]
    monkeypatch.setattr(GR, "_rows", lambda m, n, **kw: rows)
    # Uses the REAL committed corpus (benchmarks.load_visionqa_meta reads the jsonl only).
    out = GR.grade_visionqa("visionqa", "m")
    assert out["n"] == 1


def test_grade_visionqa_end_to_end(monkeypatch):
    rows = [
        {"id": "chartqa-000", "content": "\\boxed{12}", "completion_tokens": 10,
         "thinking_budget": 1000, "finish_reason": "stop"},
        {"id": "ai2d-000", "content": "\\boxed{B}", "completion_tokens": 10,
         "thinking_budget": 1000, "finish_reason": "stop"},
        {"id": "textvqa-000", "content": "\\boxed{dakota}", "completion_tokens": 10,
         "thinking_budget": 1000, "finish_reason": "stop"},
        # a non-converged row (budget hit): acc_strict must charge this as 0 regardless of content
        {"id": "screenqa-000", "content": "\\boxed{sign in to your account}", "completion_tokens": 1000,
         "thinking_budget": 1000, "finish_reason": "stop"},
    ]
    monkeypatch.setattr(GR, "_rows", lambda m, n, **kw: rows)
    meta = [
        _meta_row("chartqa-000", "chartqa", "12"),
        _meta_row("ai2d-000", "ai2d", "B", choices=["w", "x", "y", "z"]),
        _meta_row("textvqa-000", "textvqa", ["dakota"] * 10),
        _meta_row("screenqa-000", "screenqa", ["sign in to your account"]),
    ]
    monkeypatch.setattr(GR.benchmarks, "load_visionqa_meta", lambda limit, seed: meta)

    out = GR.grade_visionqa("visionqa", "m")
    assert out["n"] == 4
    assert out["correct"] == 4                 # all four raw predictions are individually correct
    assert out["per_source"] == {"chartqa": 1.0, "ai2d": 1.0, "textvqa": 1.0, "screenqa": 1.0}

    full = GR.grade("visionqa", "m")           # runs through _finalize's convergence vector
    assert full["acc"] == 1.0                  # raw correctness, convergence-blind
    # the screenqa row hit its thinking_budget (completion_tokens >= thinking_budget) -> not
    # converged -> acc_strict charges it as 0 even though its raw answer was right
    assert full["acc_strict"] == 0.75
