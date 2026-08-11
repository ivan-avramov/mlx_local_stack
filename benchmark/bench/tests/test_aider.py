"""Tests for the Aider polyglot adapter (pass-rate parse, subprocess driving, degrade).

The structured-results tests below assert against a fixture run directory whose LAYOUT AND FIELD
NAMES were transcribed from aider's own `benchmark/benchmark.py` (v0.86.2 == the version installed
on this box, verified byte-identical to `main` for both the per-case `results = dict(...)` block and
`summarize_results()`). That matters: no aider stdout/results artifact exists in this repo, so a
guessed field name would make the parser return all-`None` while every test still passed.
"""
import json
import os
import types

import bench.aider_adapter as A
import bench.run_aider as RA
import bench.stats as S

FIXTURE_RUN = os.path.join(os.path.dirname(__file__), "fixtures", "aider_run")
FIXTURE_RUN_DIR = os.path.join(FIXTURE_RUN, "2026-08-11-09-00-00--fixture-run")


def _case(name, lang="python"):
    return os.path.join(FIXTURE_RUN_DIR, lang, "exercises", "practice", name,
                        ".aider.results.json")


def test_parse_pass_rate_extracts_both():
    stdout = "...\npass_rate_1: 42.5\npass_rate_2: 61.0\nsome other line\n"
    out = A.parse_pass_rate(stdout)
    assert out["pass_rate_1"] == 42.5
    assert out["pass_rate_2"] == 61.0


def test_parse_pass_rate_missing_is_none():
    out = A.parse_pass_rate("no rates printed here")
    assert out["pass_rate_1"] is None and out["pass_rate_2"] is None


def test_aider_available_checks_harness(tmp_path):
    assert A.aider_available(str(tmp_path)) is False
    bdir = tmp_path / "benchmark"
    bdir.mkdir()
    (bdir / "benchmark.py").write_text("# harness")
    assert A.aider_available(str(tmp_path)) is True


def test_run_aider_skips_when_harness_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: False)
    out = A.run_aider("m", exercises_dir=str(tmp_path), aider_repo=str(tmp_path))
    assert out["skipped"] is True and out["acc"] is None and "note" in out
    assert out["axis"] == "agentic_coding" and out["tool"] == "aider_polyglot"


def test_run_aider_success_parses_and_normalizes(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    captured = {}

    def fake_runner(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env", {})
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_1: 40.0\npass_rate_2: 55.0\n", stderr="")

    out = A.run_aider("Qwen3.6-27B-UD-MLX-6bit", exercises_dir="/ex", aider_repo="/aider",
                      num_tests=3, runner=fake_runner)
    assert out["pass_rate_2"] == 55.0
    assert out["acc"] == 0.55                      # pass_rate_2 normalized
    assert out["skipped"] is False
    assert "openai/Qwen3.6-27B-UD-MLX-6bit" in captured["cmd"]
    assert "--num-tests" in captured["cmd"] and "3" in captured["cmd"]
    assert captured["env"]["OPENAI_API_BASE"].endswith("/v1")


def test_run_aider_falls_back_to_rate1(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_1: 30.0\n", stderr="")

    out = A.run_aider("m", "/ex", "/aider", runner=fake_runner)
    assert out["acc"] == 0.30                      # pass_rate_2 absent -> rate_1


def test_run_aider_nonzero_exit_degrades(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="boom")

    out = A.run_aider("m", "/ex", "/aider", runner=fake_runner)
    assert out["acc"] is None and "note" in out and out["skipped"] is False


def test_run_aider_runner_raises_degrades(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def boom(cmd, **kw):
        raise FileNotFoundError("python gone")

    out = A.run_aider("m", "/ex", "/aider", runner=boom)
    assert out["acc"] is None and "raised" in out["note"]


def test_run_aider_success_but_no_rate_parsed_notes(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout="benchmark finished, no rates here", stderr="")

    out = A.run_aider("m", "/ex", "/aider", runner=fake_runner)
    assert out["acc"] is None and out["skipped"] is False and "note" in out


def test_run_aider_cli_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(RA, "RESULTS", str(tmp_path))
    monkeypatch.setattr(RA, "run_aider", lambda **kw: {
        "model": kw["model"], "axis": "agentic_coding", "tool": "aider_polyglot",
        "edit_format": "whole", "pass_rate_1": 40.0, "pass_rate_2": 55.0, "acc": 0.55,
        "skipped": False})
    rc = RA.main(["--model", "mymodel", "--exercises-dir", "/ex", "--aider-repo", "/aider"])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "aider.json")))
    assert out["model"] == "mymodel" and out["acc"] == 0.55 and out["tool"] == "aider_polyglot"


def test_run_aider_sets_aider_docker_to_bypass_host_guard(tmp_path, monkeypatch):
    # aider's benchmark.py returns immediately (prints a docker warning, runs nothing) unless
    # AIDER_DOCKER is set. We run on the host (toolchains present), so the adapter MUST set it —
    # otherwise every run yields "NO SCORE" (no pass_rate parsed).
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    captured = {}

    def fake_runner(cmd, **kw):
        captured["env"] = kw.get("env", {})
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_2: 55.0\n", stderr="")

    A.run_aider("m", exercises_dir="/ex", aider_repo="/aider", runner=fake_runner)
    assert captured["env"].get("AIDER_DOCKER") == "1"


def test_run_aider_prepends_python_bindir_to_path_for_test_tools(monkeypatch):
    # polyglot python exercises run `pytest` via subprocess (TEST_COMMANDS[".py"]=["pytest"]);
    # pytest lives in the aider venv (== the python running benchmark.py), so the adapter must
    # prepend that bindir to PATH or the test-runner FileNotFoundErrors on `pytest`.
    import os, sys
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    captured = {}

    def fake_runner(cmd, **kw):
        captured["env"] = kw.get("env", {})
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_2: 55.0\n", stderr="")

    A.run_aider("m", exercises_dir="/ex", aider_repo="/aider", runner=fake_runner)
    assert os.path.dirname(sys.executable) in captured["env"]["PATH"].split(os.pathsep)


def test_run_aider_sets_absolute_benchmark_dir(monkeypatch, tmp_path):
    # benchmark.py asserts BENCHMARK_DNAME (default relative "tmp.benchmarks") exists; the adapter
    # runs from an arbitrary CWD, so it must point AIDER_BENCHMARK_DIR at an absolute, existing dir.
    import os
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    captured = {}

    def fake_runner(cmd, **kw):
        captured["env"] = kw.get("env", {})
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_2: 55.0\n", stderr="")

    repo = str(tmp_path / "aider")
    A.run_aider("m", exercises_dir="/ex", aider_repo=repo, runner=fake_runner)
    bd = captured["env"].get("AIDER_BENCHMARK_DIR")
    assert bd == os.path.join(repo, "benchmark", "tmp.benchmarks")
    assert os.path.isabs(bd) and os.path.isdir(bd)   # adapter created it


# ---------------------------------------------------------------- parse_aider_results (schema)
def _raw(outcomes, **kw):
    """A minimal RAW aider per-case results dict (aider's own key spellings)."""
    d = {"testcase": "synthetic", "model": "openai/m", "edit_format": "diff",
         "tests_outcomes": list(outcomes), "duration": 100.0, "cost": 0.0}
    d.update(kw)
    return d


def test_parse_aider_results_reads_per_case_file():
    out = A.parse_aider_results(_case("bowling"))
    assert out["note"] is None and out["parsed"] is True
    assert out["testcase"] == "bowling"
    assert out["model"] == "openai/Ornith-1.0-35B-mlx-uniform-4bit"
    assert out["edit_format"] == "diff" and out["commit_hash"] == "abc1234"
    assert out["tests_outcomes"] == [False, True]
    assert out["n_attempts"] == 2 and out["passed"] is True and out["passed_on_attempt"] == 2
    assert out["duration"] == 640.25 and out["cost"] == 0.0
    # aider's key is num_exhausted_context_windows / num_error_outputs; ours normalises the names
    assert out["num_malformed_responses"] == 1 and out["num_with_malformed_responses"] == 1
    assert out["indentation_errors"] == 1 and out["lazy_comments"] == 2
    assert out["syntax_errors"] == 0 and out["test_timeouts"] == 0
    assert out["num_error_outputs"] == 1 and out["num_user_asks"] == 2
    assert out["exhausted_context_windows"] == 0
    assert out["prompt_tokens"] == 5901 and out["completion_tokens"] == 9044


def test_parse_aider_results_accepts_a_dict():
    out = A.parse_aider_results(_raw([True], num_malformed_responses=0))
    assert out["parsed"] is True and out["passed"] is True and out["n_attempts"] == 1
    assert out["passed_on_attempt"] == 1


def test_parse_aider_results_missing_file_notes_never_raises(tmp_path):
    out = A.parse_aider_results(str(tmp_path / "nope" / ".aider.results.json"))
    assert out["parsed"] is False and out["note"] and "not found" in out["note"].lower()
    assert out["tests_outcomes"] is None and out["duration"] is None
    assert out["num_malformed_responses"] is None


def test_parse_aider_results_corrupt_json_notes_never_raises(tmp_path):
    p = tmp_path / ".aider.results.json"
    p.write_text('{"testcase": "anagram", "tests_outcomes": [tru')   # killed mid-write
    out = A.parse_aider_results(str(p))
    assert out["parsed"] is False and out["note"] and "json" in out["note"].lower()
    assert out["tests_outcomes"] is None


def test_parse_aider_results_unknown_keys_ignored_missing_keys_none():
    out = A.parse_aider_results({"tests_outcomes": [True], "brand_new_aider_field": 7,
                                 "chat_hashes": [["a", "b"]]})
    assert out["passed"] is True
    assert "brand_new_aider_field" not in out
    for k in ("duration", "cost", "model", "edit_format", "commit_hash", "test_timeouts",
              "syntax_errors", "lazy_comments", "num_error_outputs"):
        assert out[k] is None, k


def test_parse_aider_results_exception_shaped_case_is_parsed_but_scoreless():
    # benchmark.py:675 writes {"exception": traceback} when a case crashes. It is a real,
    # non-empty results file: aider counts it in completed_tests, so it must parse (not degrade)
    # while carrying no outcome.
    out = A.parse_aider_results(_case("two-fer", lang="go"))
    assert out["parsed"] is True
    assert out["tests_outcomes"] is None and out["passed"] is None
    assert out["note"] and "exception" in out["note"].lower()


def test_parse_aider_results_accepts_aggregate_string_pass_rates():
    # summarize_results stores pass_rate_N as a FORMATTED STRING (f"{pass_rate:.1f}") and spells
    # cost `total_cost`; a summary dict must not come back as None.
    out = A.parse_aider_results({"pass_rate_1": "20.0", "pass_rate_2": "40.0",
                                 "total_cost": 0.0, "exhausted_context_windows": 2})
    assert out["pass_rate_1"] == 20.0 and out["pass_rate_2"] == 40.0
    assert out["cost"] == 0.0 and out["exhausted_context_windows"] == 2


# -------------------------------------------------------------------- the output-limit mislabel
def test_output_limit_hits_mirrors_exhausted_windows_and_annotates_the_mislabel():
    # 2026-07-06: gemma-4-26B-A4B-it-OptiQ-4bit was recorded "20% pass_rate_2" while 5/5 cases hit
    # the OUTPUT cap after long thinking (input ~2,283 of 98,304 — fine). aider's counter is named
    # num_exhausted_context_windows, which reads as an input-context problem. The parsed dict must
    # say otherwise, in the dict, where a future reader will see it.
    out = A.parse_aider_results(_case("grep", lang="rust"))
    assert out["exhausted_context_windows"] == 2
    assert out["output_limit_hits"] == 2
    note = out["output_limit_note"].lower()
    assert "output" in note and "input" in note
    assert "mislabel" in note or "misnomer" in note


def test_aggregate_carries_the_output_limit_annotation():
    agg = A.aggregate_cases([_raw([False, False], num_exhausted_context_windows=2),
                             _raw([True])])
    assert agg["exhausted_context_windows"] == 2 and agg["output_limit_hits"] == 2
    note = agg["output_limit_note"].lower()
    assert "output" in note and "input" in note


# ------------------------------------------------------------------------------ aggregate_cases
def test_aggregate_pass_rate_1_vs_2_semantics():
    # aider: a case counts as passed only if its LAST attempt passed, and it is credited from
    # try len(tests_outcomes) onward. So [False, True] is a pass_rate_2 success but NOT pass_rate_1,
    # and [] is neither (it still sits in the denominator).
    agg = A.aggregate_cases([_raw([True]), _raw([False, True]), _raw([])])
    assert agg["n_cases"] == 3 and agg["tries"] == 2
    assert agg["pass_num_1"] == 1 and agg["pass_num_2"] == 2
    assert agg["pass_rate_1"] == 100 * 1 / 3
    assert agg["pass_rate_2"] == 100 * 2 / 3
    assert agg["pass_rate_final"] == agg["pass_rate_2"]


def test_aggregate_last_attempt_false_is_not_a_pass():
    # a naive any(outcomes) would score this a pass; aider looks at tests_outcomes[-1] only.
    agg = A.aggregate_cases([_raw([True, False])])
    assert agg["pass_num_1"] == 0 and agg["pass_num_2"] == 0 and agg["pass_rate_2"] == 0.0


def test_aggregate_empty_case_list_degrades():
    agg = A.aggregate_cases([])
    assert agg["n_cases"] == 0
    assert agg["pass_rate_1"] is None and agg["pass_rate_2"] is None
    assert agg["percent_cases_well_formed"] is None
    assert agg["durations"] == [] and agg["note"]


def test_aggregate_all_fail():
    agg = A.aggregate_cases([_raw([False, False]), _raw([False, False])])
    assert agg["pass_rate_1"] == 0.0 and agg["pass_rate_2"] == 0.0
    assert agg["pass_rate_final"] == 0.0
    assert agg["durations_success"] == [] and len(agg["durations_fail"]) == 2


def test_aggregate_all_pass():
    agg = A.aggregate_cases([_raw([True]), _raw([True])])
    assert agg["pass_rate_1"] == 100.0 and agg["pass_rate_2"] == 100.0
    assert agg["percent_cases_well_formed"] == 100.0
    assert agg["durations_fail"] == [] and len(agg["durations_success"]) == 2


def test_aggregate_ragged_and_missing_keys_do_not_crash():
    cases = [{"tests_outcomes": [True]},                      # no duration, no counters
             {"tests_outcomes": [False, False], "duration": 5.0},
             {},                                              # empty-ish, but a real file
             {"exception": "boom"}]
    agg = A.aggregate_cases(cases)
    assert agg["n_cases"] == 4
    assert agg["n_scored"] == 2 and agg["n_crashed"] == 2   # {} and {"exception": ...} never ran
    assert agg["pass_num_1"] == 1
    assert agg["pass_rate_1"] == 25.0       # denominator is ALL cases (aider semantics)
    assert agg["durations"] == [5.0]        # cases without a duration are OMITTED, not zeroed
    assert agg["test_timeouts"] == 0 and agg["num_malformed_responses"] == 0


def test_aggregate_sums_counters_and_durations_and_well_formed():
    cases = [_raw([True], num_malformed_responses=0, test_timeouts=0, duration=10.0),
             _raw([False, True], num_malformed_responses=3, lazy_comments=2, duration=20.0),
             _raw([False, False], test_timeouts=1, syntax_errors=4, num_error_outputs=2,
                  indentation_errors=1, num_user_asks=2, duration=30.0,
                  num_exhausted_context_windows=1, cost=0.5)]
    agg = A.aggregate_cases(cases)
    assert agg["num_malformed_responses"] == 3
    assert agg["num_with_malformed_responses"] == 1      # cases, not responses
    assert agg["percent_cases_well_formed"] == 100 * (1 - 1 / 3)
    assert agg["lazy_comments"] == 2 and agg["syntax_errors"] == 4
    assert agg["indentation_errors"] == 1 and agg["test_timeouts"] == 1
    assert agg["num_error_outputs"] == 2 and agg["num_user_asks"] == 2
    assert agg["durations"] == [10.0, 20.0, 30.0]
    assert agg["durations_success"] == [10.0, 20.0] and agg["durations_fail"] == [30.0]
    assert agg["total_duration"] == 60.0 and agg["avg_duration"] == 20.0
    assert agg["total_cost"] == 0.5


def test_aggregate_skips_unparsable_cases_but_counts_them(tmp_path):
    bad = tmp_path / ".aider.results.json"
    bad.write_text("{not json")
    agg = A.aggregate_cases([_raw([True]), str(bad)])
    assert agg["n_cases"] == 1 and agg["n_unparsed"] == 1   # aider's load_results skips these too
    assert agg["pass_rate_1"] == 100.0


def test_aggregate_reports_unanimous_model_and_edit_format():
    agg = A.aggregate_cases([_raw([True]), _raw([True])])
    assert agg["model"] == "openai/m" and agg["edit_format"] == "diff"
    mixed = A.aggregate_cases([_raw([True]), _raw([True], edit_format="whole")])
    assert mixed["edit_format"] is None      # mixed formats are NOT comparable; refuse to pick one


# ------------------------------------------------------------------ realistic multi-case fixture
def test_collect_case_results_globs_aiders_real_layout():
    cases = A.collect_case_results(FIXTURE_RUN)
    assert len(cases) == 5                      # python x2, rust x2, go x1 (the exception case)
    assert {c["testcase"] for c in cases if c["testcase"]} == {"anagram", "bowling", "clock",
                                                               "grep"}


def test_collect_case_results_filters_by_run_name():
    assert A.collect_case_results(FIXTURE_RUN, run_name="fixture-run")
    assert A.collect_case_results(FIXTURE_RUN, run_name="some-other-run") == []
    assert A.collect_case_results("/no/such/benchmark/dir") == []


def test_aggregate_over_the_fixture_run():
    agg = A.aggregate_cases(A.collect_case_results(FIXTURE_RUN))
    assert agg["n_cases"] == 5 and agg["tries"] == 2
    assert agg["n_scored"] == 4 and agg["n_crashed"] == 1
    assert agg["pass_num_1"] == 1 and agg["pass_num_2"] == 2
    assert agg["pass_rate_1"] == 20.0 and agg["pass_rate_2"] == 40.0
    assert agg["percent_cases_well_formed"] == 80.0        # 1 of 5 cases had a malformed response
    assert agg["output_limit_hits"] == 2                   # the grep case, output budget not input
    assert agg["test_timeouts"] == 1
    assert sorted(agg["durations"]) == [180.5, 640.25, 905.0, 1520.75]
    assert agg["durations_success"] == [180.5, 640.25]


# --------------------------------------------------------------------------- reliability_summary
def test_reliability_summary_matches_stats_time_to_success():
    cases = ([_raw([True], duration=d) for d in (100.0, 200.0, 300.0)]
             + [_raw([False, False], duration=d) for d in (400.0, 500.0)])
    rel = A.reliability_summary(A.aggregate_cases(cases))
    assert rel["n_success"] == 3 and rel["n_fail"] == 2
    assert rel["p"] == 0.6
    want = S.time_to_success([100.0, 200.0, 300.0], [400.0, 500.0], 0.6)
    assert rel["expected_s"] == want["expected_s"]
    assert rel["successes_per_hour"] == want["successes_per_hour"]
    assert rel["mean_success_s"] == 200.0 and rel["mean_fail_s"] == 450.0
    # 3 successes / 2 failures is below stats.time_to_success's stated ~5-of-each floor, and the
    # summary must say so rather than present the ratio bare.
    assert rel["thin_evidence"] is True and "thin evidence" in rel["note"]


def test_reliability_summary_all_pass_charges_no_retries():
    rel = A.reliability_summary(A.aggregate_cases([_raw([True], duration=60.0),
                                                   _raw([True], duration=120.0)]))
    assert rel["p"] == 1.0 and rel["expected_s"] == 90.0
    assert rel["successes_per_hour"] == 40.0


def test_reliability_summary_all_fail_degrades_without_raising():
    rel = A.reliability_summary(A.aggregate_cases([_raw([False, False], duration=400.0)]))
    assert rel["p"] == 0.0
    assert rel["expected_s"] is None and rel["successes_per_hour"] == 0.0
    assert rel["note"] and "success" in rel["note"].lower()


def test_reliability_summary_empty_aggregate_degrades():
    rel = A.reliability_summary(A.aggregate_cases([]))
    assert rel["expected_s"] is None and rel["p"] is None and rel["note"]


def test_reliability_summary_carries_the_reliability_counters():
    agg = A.aggregate_cases([_raw([True], duration=10.0, num_malformed_responses=2),
                             _raw([False, False], duration=20.0,
                                  num_exhausted_context_windows=1, test_timeouts=1)])
    rel = A.reliability_summary(agg)
    assert rel["percent_cases_well_formed"] == 50.0
    assert rel["num_malformed_responses"] == 2
    assert rel["output_limit_hits"] == 1 and "output" in rel["output_limit_note"].lower()
    assert rel["test_timeouts"] == 1


def test_reliability_summary_flags_thin_evidence():
    # stats.time_to_success needs ~5 successes and ~5 failures before its two means mean anything.
    rel = A.reliability_summary(A.aggregate_cases([_raw([True], duration=10.0),
                                                   _raw([False, False], duration=20.0)]))
    assert rel["expected_s"] == 10.0 + (0.5 / 0.5) * 20.0
    assert rel["thin_evidence"] is True
    big = ([_raw([True], duration=10.0)] * 5) + ([_raw([False, False], duration=20.0)] * 5)
    assert A.reliability_summary(A.aggregate_cases(big))["thin_evidence"] is False


def test_reliability_summary_no_observed_failures_is_optimistic_and_says_so():
    # p<1 with an empty t_fail happens when failing cases errored out (unparsable). stats charges
    # zero for the retries; the caller must be told the number is an optimistic bound.
    agg = A.aggregate_cases([_raw([True], duration=10.0), _raw([], duration=None)])
    rel = A.reliability_summary(agg)
    assert rel["p"] == 0.5 and rel["n_fail"] == 0
    assert rel["expected_s"] == 10.0        # no failure durations observed -> retries cost 0
    assert rel["note"] and "optimistic" in rel["note"].lower()


# ---------------------------------------------------------------------- run_aider JSON wiring
def _fixture_into(repo_dir):
    """Copy the fixture run into <repo>/benchmark/tmp.benchmarks (where run_aider looks)."""
    import shutil
    dst = os.path.join(repo_dir, "benchmark", "tmp.benchmarks")
    shutil.copytree(FIXTURE_RUN, dst, dirs_exist_ok=True)
    return dst


def test_run_aider_prefers_results_json_over_stdout(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    repo = str(tmp_path / "aider")
    _fixture_into(repo)

    def fake_runner(cmd, **kw):
        # stdout says 99/99; the structured results say 20/40. The JSON wins.
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_1: 99.0\npass_rate_2: 99.0\n",
                                     stderr="")

    out = A.run_aider("m", "/ex", repo, run_name="fixture-run", runner=fake_runner)
    assert out["source"] == "results_json"
    assert out["pass_rate_1"] == 20.0 and out["pass_rate_2"] == 40.0
    assert out["acc"] == 0.40 and out["skipped"] is False
    assert out["n_cases"] == 5 and out["percent_cases_well_formed"] == 80.0
    assert out["output_limit_hits"] == 2 and "output" in out["output_limit_note"].lower()
    assert out["reliability"]["successes_per_hour"] > 0
    assert out["aider_results"]["test_timeouts"] == 1


def test_run_aider_falls_back_to_stdout_when_no_json(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    repo = str(tmp_path / "aider")     # no tmp.benchmarks content -> nothing to parse

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_1: 40.0\npass_rate_2: 55.0\n",
                                     stderr="")

    out = A.run_aider("m", "/ex", repo, runner=fake_runner)
    assert out["source"] == "stdout" and out["acc"] == 0.55
    assert out["pass_rate_2"] == 55.0
    assert out["reliability"] is None and out["aider_results"] is None


def test_run_aider_json_present_but_every_case_crashed_is_not_a_zero(tmp_path, monkeypatch):
    # A run where NO case reached its tests is not "0% pass" — aider's own denominator would
    # happily print 0.0 and the campaign would file it as a capability result. It must degrade.
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    repo = tmp_path / "aider"
    d = repo / "benchmark" / "tmp.benchmarks" / "2026-01-01-00-00-00--r" / "go" / "exercises" \
        / "practice" / "two-fer"
    d.mkdir(parents=True)
    (d / ".aider.results.json").write_text(json.dumps({"exception": "boom"}))

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_2: 0.0\n", stderr="")

    out = A.run_aider("m", "/ex", str(repo), run_name="r", runner=fake_runner)
    assert out["source"] == "results_json"
    assert out["acc"] is None and out["skipped"] is False and out["note"]
    assert out["pass_rate_1"] is None and out["pass_rate_2"] is None
    assert out["aider_results"]["n_crashed"] == 1 and out["aider_results"]["n_scored"] == 0


def test_parse_aider_report_is_the_stdout_parser_alias():
    assert A.parse_aider_report is A.parse_pass_rate
