"""Preflight probes: the edit-format decision, and the canary's sampling profile.

WHY THESE TESTS EXIST — both cases cost real campaign time.

1. EDIT FORMAT. `docs/campaign-results.md:434` records `gemma-4-31b-it-6bit` running the
   agentic Aider axis at `edit_format: diff` and getting STUCK: 0 exercises done in 2h on
   exercise 1, repeated identical 8126-token generations, because its SEARCH/REPLACE blocks
   did not apply (aider's "misapplies edits" retry loop). The fix was `edit_format: whole`.
   Two hours of a scarce 64GB box to learn something a 5-minute probe answers. It matters
   again right now: the three M1 candidates run two formats (qwen-arch pair on `diff`, gemma
   on `whole`), which CONFOUNDS the cross-family agentic comparison
   (`docs/campaign-queue.md:64-65`), so the probe must decide each model's format on evidence
   BEFORE the head-to-head.

   The failure mode to distinguish is specifically `search_not_found`: a well-formed block
   whose SEARCH text does not literally occur in the file. A boolean cannot tell that apart
   from "emitted no block at all", and the two have different fixes.

2. CANARY PROFILE. `run_canary` called `params_for(model)` with no profile, so it always used
   the `production` table. It did not hardcode a temperature — it IGNORED the run's profile,
   which is why an Ornith canary ran at production temp 0.7 and MEANDERED (ct=49221 > 49152
   budget = non-converged) while the same trivial prompt converged in 1369 tokens at temp 0.6
   (`docs/campaign-queue.md:232-240`). A false-failed canary blocks a run that would have been
   fine.

Everything here runs against `FakeDriver` — a preflight probe that needed a live router to test
would never be tested.
"""
import pytest

import bench.model_params as MP
import bench.preflight as P

from .conftest import FakeDriver, complete_result

# The one literal line the probe asks the model to edit. Taken from the fixture itself so the
# test cannot drift from the module the model is actually shown.
TARGET_LINE = "TAX_RATE = 0.08"


# --------------------------------------------------------------------------- block builders
def sr_block(search, replace, *, filename="pricing.py", fence="python", pad="", eol="\n"):
    """An aider-style SEARCH/REPLACE response: filename line, then a fenced marker triple.

    `pad` pads the marker lines with leading/trailing whitespace (real models do this);
    `eol` lets a test feed CRLF.
    """
    lines = []
    if filename:
        lines.append(filename)
    lines.append(f"```{fence}" if fence else "```")
    lines += [f"{pad}<<<<<<< SEARCH{pad}", search, f"{pad}======={pad}", replace,
              f"{pad}>>>>>>> REPLACE{pad}", "```"]
    return eol.join(lines) + eol


def whole_file(src, *, fence="python"):
    return f"Here is the updated file.\n\n```{fence}\n{src}\n```\n"


def good_diff_response():
    return sr_block(TARGET_LINE, "TAX_RATE = 0.09")


def responses(diff_text, whole_text=None):
    """A FakeDriver script for one check_edit_format call: the diff probe, then the whole probe."""
    return [complete_result(content=diff_text),
            complete_result(content=whole_file(P.FIXTURE_SRC) if whole_text is None
                            else whole_text)]


# --------------------------------------------------------------------------- the fixture
def test_fixture_is_a_real_python_module():
    """The probe's ground truth. If the fixture does not parse, `whole` can never be judged and
    every SEARCH is matched against nonsense."""
    import ast
    ast.parse(P.FIXTURE_SRC)
    assert TARGET_LINE in P.FIXTURE_SRC
    assert P.FIXTURE_SRC.count(TARGET_LINE) == 1      # a unique anchor: no ambiguous match
    assert 10 <= len(P.FIXTURE_SRC.splitlines()) <= 40


def test_diff_prompt_shows_the_file_and_asks_for_one_block():
    prompt = P.diff_prompt()
    assert P.FIXTURE_SRC in prompt and P.FIXTURE_NAME in prompt
    assert "SEARCH" in prompt and "REPLACE" in prompt
    assert P.EDIT_INSTRUCTION in prompt


# --------------------------------------------------------------------------- parser / applier
def test_applies_a_correct_single_block():
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, good_diff_response())
    assert reason == "applied"
    assert "TAX_RATE = 0.09" in out and TARGET_LINE not in out


def test_search_text_absent_reports_search_not_found():
    """The gemma case: the block is perfectly well-formed, but its SEARCH text is not in the
    file (invented indentation / paraphrased line), so aider's applier rejects it and retries
    forever."""
    resp = sr_block("TAX_RATE=0.08   # sales tax", "TAX_RATE=0.09")
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, resp)
    assert reason == "search_not_found" and out is None


def test_no_marker_at_all_reports_no_block():
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, "Sure! Just change the tax rate to 0.09.")
    assert reason == "no_block" and out is None


def test_mangled_markers_report_malformed_markers():
    """Markers are clearly INTENDED but the triple is broken (here: no `=======` divider).
    Distinct from no_block: the model knows the format and fumbled it, which a prompt/template
    fix addresses — whereas no_block means it ignored the format entirely."""
    resp = ("```python\n<<<<<<< SEARCH\nTAX_RATE = 0.08\nTAX_RATE = 0.09\n"
            ">>>>>>> REPLACE\n```\n")
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, resp)
    assert reason == "malformed_markers" and out is None


def test_multiple_blocks_all_apply():
    resp = (sr_block(TARGET_LINE, "TAX_RATE = 0.09")
            + "\nand also:\n\n"
            + sr_block("def subtotal(items):", "def subtotal(items):  # noqa: D103"))
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, resp)
    assert reason == "applied"
    assert "TAX_RATE = 0.09" in out and "# noqa: D103" in out


def test_crlf_response_applies_against_an_lf_file():
    """Models served through HTTP proxies do emit CRLF. Unnormalised, every SEARCH would end
    with a stray \\r and report search_not_found — a fake gemma-style failure."""
    resp = sr_block(TARGET_LINE, "TAX_RATE = 0.09", eol="\r\n")
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, resp)
    assert reason == "applied" and "TAX_RATE = 0.09" in out


def test_whitespace_padded_markers_are_tolerated():
    resp = sr_block(TARGET_LINE, "TAX_RATE = 0.09", pad="  ")
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, resp)
    assert reason == "applied"


def test_prose_and_thinking_around_the_block_are_tolerated():
    """Thinking is ON for every test in this campaign (AGENTS.md) — never disabled to make a
    benchmark work — so the parser must survive reasoning text on both sides of the block."""
    resp = ("<think>The tax rate lives at module scope. I will emit one block.</think>\n"
            "I'll update the constant.\n\n" + good_diff_response()
            + "\nThat should do it. Let me know if you want the discount changed too.\n")
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, resp)
    assert reason == "applied" and "TAX_RATE = 0.09" in out


def test_last_block_wins_when_the_same_search_is_drafted_then_finalised():
    """With thinking on, a model often drafts a block, criticises it, then emits the real one.
    Applying both would fail the second (its SEARCH is already gone) and report a bogus
    search_not_found, so duplicate SEARCH texts collapse to the LAST occurrence."""
    draft = sr_block(TARGET_LINE, "TAX_RATE = 0.99")
    final = sr_block(TARGET_LINE, "TAX_RATE = 0.09")
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, f"<think>{draft}</think>\n{final}")
    assert reason == "applied"
    assert "TAX_RATE = 0.09" in out and "0.99" not in out


def test_a_malformed_draft_followed_by_a_good_block_still_applies():
    mangled = "```\n<<<<<<< SEARCH\nTAX_RATE = 0.08\n>>>>>>> REPLACE\n```\n"
    out, reason = P.apply_search_replace(P.FIXTURE_SRC, mangled + good_diff_response())
    assert reason == "applied"


def test_parse_captures_the_filename_line_before_the_fence():
    blocks = P.parse_search_replace(good_diff_response())
    assert len(blocks) == 1
    assert blocks[0]["filename"] == "pricing.py"
    assert blocks[0]["search"] == TARGET_LINE


def test_parse_without_a_filename_line_still_yields_the_block():
    resp = sr_block(TARGET_LINE, "TAX_RATE = 0.09", filename=None)
    blocks = P.parse_search_replace(resp)
    assert len(blocks) == 1 and blocks[0]["filename"] is None


# --------------------------------------------------------------------------- whole format
def test_whole_probe_accepts_a_complete_parsing_file():
    d = FakeDriver(responses(good_diff_response()))
    res = P.check_edit_format(d, "m", {"temperature": 0.4})
    assert res["whole"] is True and res["whole_failure"] is None


def test_whole_probe_rejects_a_file_that_does_not_parse():
    bad = "```python\ndef total(items)\n    return 1\n```"
    d = FakeDriver(responses(good_diff_response(), whole_text=bad))
    res = P.check_edit_format(d, "m", {})
    assert res["whole"] is False and res["whole_failure"] == "syntax_error"


def test_whole_probe_rejects_a_response_with_no_fenced_code():
    d = FakeDriver(responses(good_diff_response(), whole_text="I would change the tax rate."))
    res = P.check_edit_format(d, "m", {})
    assert res["whole"] is False and res["whole_failure"] == "no_code_block"


# --------------------------------------------------------------------------- check_edit_format
def test_check_edit_format_happy_path():
    d = FakeDriver(responses(good_diff_response()))
    res = P.check_edit_format(d, "Ornith-1.0-35B-mlx-uniform-4bit", {"temperature": 0.4})
    assert res["diff"] is True and res["whole"] is True
    assert res["diff_failure"] is None
    assert res["recommended_format"] == "diff"
    assert res["note"] is None
    assert d.n_calls == 2                                  # diff probe, then whole probe
    assert d.calls[0]["params"]["temperature"] == 0.4       # production params reach the probe


def test_check_edit_format_captures_raw_on_search_not_found():
    """The raw block is the whole point of a failure: without it the operator cannot see WHY
    the diff did not apply, which is what made the gemma episode a two-hour mystery."""
    resp = sr_block("TAX_RATE = 0.080", "TAX_RATE = 0.09")
    d = FakeDriver(responses(resp))
    res = P.check_edit_format(d, "gemma-4-31b-it-6bit", {})
    assert res["diff"] is False
    assert res["diff_failure"] == "search_not_found"
    assert "TAX_RATE = 0.080" in res["raw"]
    assert res["recommended_format"] == "whole"            # the fix that unstuck gemma


def test_check_edit_format_reports_no_block():
    d = FakeDriver(responses("Change the tax rate to 0.09 and you're done."))
    res = P.check_edit_format(d, "m", {})
    assert res["diff"] is False and res["diff_failure"] == "no_block"


def test_check_edit_format_reports_malformed_markers():
    d = FakeDriver(responses("```python\n<<<<<<< SEARCH\nTAX_RATE = 0.08\n### REPLACE\n```"))
    res = P.check_edit_format(d, "m", {})
    assert res["diff"] is False and res["diff_failure"] == "malformed_markers"


def test_raw_capture_is_truncated():
    huge = sr_block("nope " * 4000, "x")
    d = FakeDriver(responses(huge))
    res = P.check_edit_format(d, "m", {})
    assert res["diff_failure"] == "search_not_found"
    assert len(res["raw"]) <= P.RAW_MAX_CHARS + 120        # + the truncation marker
    assert "truncated" in res["raw"]


def test_custom_fixture_source_is_used():
    src = "VALUE = 1\n"
    d = FakeDriver([complete_result(content=sr_block("VALUE = 1", "VALUE = 2")),
                    complete_result(content=whole_file(src))])
    res = P.check_edit_format(d, "m", {}, fixture=src)
    assert res["diff"] is True and res["whole"] is True
    assert src in d.calls[0]["messages"][0]["content"]


def test_driver_exception_degrades_to_a_dict_with_a_note():
    """Graceful degrade: a 500 from a half-dead router must not crash the preflight — it should
    report an unknown format so the operator restarts the router, not edit a config."""
    def boom(model, messages, params):
        raise RuntimeError("HTTP 500 from router")

    d = FakeDriver([boom, boom])
    res = P.check_edit_format(d, "m", {})
    assert res["diff"] is False and res["whole"] is False
    assert res["recommended_format"] is None
    assert "HTTP 500" in res["note"]
    assert res["diff_failure"] == "probe_error"


def test_partial_driver_failure_still_reports_the_other_format():
    d = FakeDriver([complete_result(content=good_diff_response()),
                    lambda *a: (_ for _ in ()).throw(RuntimeError("whole probe died"))])
    res = P.check_edit_format(d, "m", {})
    assert res["diff"] is True and res["whole"] is False
    assert res["recommended_format"] == "diff"
    assert "whole probe died" in res["note"]


# --------------------------------------------------------------------------- run_canary profile
CANARY_OK = complete_result(content="```python\ndef is_palindrome(s):\n    return True\n```",
                            completion_tokens=1200, finish_reason="stop")


def test_run_canary_default_profile_is_unchanged_production():
    """Default behaviour must not move: existing preflight invocations (preflight.sh passes no
    profile) keep canarying at the production table."""
    d = FakeDriver([CANARY_OK])
    res = P.run_canary("Ornith-1.0-35B-mlx-uniform-4bit", driver=d)
    assert res["profile"] == "production"
    assert res["ok"] is True and res["converged"] is True and res["has_code"] is True
    assert d.calls[0]["params"] == MP.params_for("Ornith-1.0-35B-mlx-uniform-4bit", "production")
    assert d.preloaded == ["Ornith-1.0-35B-mlx-uniform-4bit"]


def test_run_canary_explicit_profile_is_actually_sent():
    """The bug: run_canary IGNORED the run's profile, so an Ornith canary ran at production
    temp 0.7 and meandered past its 49152 budget, while temp 0.6 converged in 1369 tokens."""
    d = FakeDriver([CANARY_OK])
    res = P.run_canary("Ornith-1.0-35B-mlx-uniform-4bit", profile="official", driver=d)
    assert res["profile"] == "official"
    sent = d.calls[0]["params"]
    assert sent["temperature"] == 0.6                 # NOT the production 0.7
    assert sent["thinking_budget"] == 81920
    assert sent == MP.params_for("Ornith-1.0-35B-mlx-uniform-4bit", "official")


def test_run_canary_uses_the_profiles_budget_for_the_convergence_verdict():
    """A profile change moves the convergence bar with it: 20000 tokens is a budget-hit under
    production (49152 clamp aside, ct must be < budget) only if the budget is small. Here the
    same response converges under `official` (81920) and not under a tiny stub budget."""
    d = FakeDriver([complete_result(content="```python\nx=1\n```", completion_tokens=60000,
                                   finish_reason="stop")])
    res = P.run_canary("Ornith-1.0-35B-mlx-uniform-4bit", profile="official", driver=d)
    assert res["thinking_budget"] == 81920 and res["converged"] is True
    d2 = FakeDriver([complete_result(content="```python\nx=1\n```", completion_tokens=60000,
                                     finish_reason="stop")])
    res2 = P.run_canary("Ornith-1.0-35B-mlx-uniform-4bit", profile="production", driver=d2)
    assert res2["thinking_budget"] == 49152
    assert res2["converged"] is False and res2["ok"] is False


def test_run_canary_deployed_profile_reads_the_registry(tmp_path):
    """`deployed` = main_models.yaml generation_defaults, the config mlx-serve actually
    forwards. Canarying at anything else re-opens the drift this profile closed."""
    import yaml
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.safe_dump({"models": [
        {"name": "m", "generation_defaults": {"temperature": 0.3, "thinking_budget": 81920,
                                              "max_tokens": 102400}}]}))
    d = FakeDriver([CANARY_OK])
    res = P.run_canary("m", profile="deployed", driver=d, registry_path=str(reg))
    assert res["profile"] == "deployed" and res["ok"] is True
    assert d.calls[0]["params"]["temperature"] == 0.3


def test_run_canary_deployed_against_the_real_registry():
    from pathlib import Path
    reg = str(Path(P.__file__).resolve().parents[2] / "main_models.yaml")
    d = FakeDriver([CANARY_OK])
    res = P.run_canary("Qwen3.6-27B-Opus-Distill-OptiQ-4bit", profile="deployed", driver=d,
                       registry_path=reg)
    assert res["ok"] is True
    assert d.calls[0]["params"]["temperature"] == 0.3      # deployed op-temp, not production 0.7


def test_run_canary_unknown_profile_degrades_without_raising():
    d = FakeDriver([CANARY_OK])
    res = P.run_canary("Ornith-1.0-35B-mlx-uniform-4bit", profile="nonsense", driver=d)
    assert res["ok"] is False
    assert "nonsense" in res["note"] and "production" in res["note"]
    assert d.calls == [] and d.preloaded == []            # no box time spent on a typo


def test_run_canary_deployed_for_an_unregistered_model_degrades(tmp_path):
    import yaml
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.safe_dump({"models": [{"name": "other", "generation_defaults": {}}]}))
    d = FakeDriver([CANARY_OK])
    res = P.run_canary("ghost", profile="deployed", driver=d, registry_path=str(reg))
    assert res["ok"] is False and "ghost" in res["note"]
    assert d.calls == []


def test_run_canary_driver_exception_degrades():
    d = FakeDriver([lambda *a: (_ for _ in ()).throw(RuntimeError("router down"))])
    res = P.run_canary("Ornith-1.0-35B-mlx-uniform-4bit", driver=d)
    assert res["ok"] is False and "router down" in res["note"]


def test_run_canary_no_code_fails_even_when_converged():
    d = FakeDriver([complete_result(content="I'd be happy to help!", completion_tokens=12)])
    res = P.run_canary("Ornith-1.0-35B-mlx-uniform-4bit", driver=d)
    assert res["converged"] is True and res["has_code"] is False and res["ok"] is False


# --------------------------------------------------------------------------- CLI plumbing
def test_cli_parses_model_and_profile():
    args = P.parse_args(["Ornith-1.0-35B-mlx-uniform-4bit", "--profile", "deployed"])
    assert args["model"] == "Ornith-1.0-35B-mlx-uniform-4bit"
    assert args["profile"] == "deployed"
    assert args["edit_format"] is False


def test_cli_defaults_to_production_and_no_edit_format_probe():
    args = P.parse_args(["m"])
    assert args["profile"] == "production" and args["edit_format"] is False


def test_cli_edit_format_flag():
    args = P.parse_args(["m", "--edit-format"])
    assert args["edit_format"] is True


def test_cli_rejects_a_missing_model():
    with pytest.raises(SystemExit):
        P.parse_args([])
