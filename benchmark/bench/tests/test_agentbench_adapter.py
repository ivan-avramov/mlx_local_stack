"""M54: bench.agentbench_adapter -- corpus/eval semantics, container lifecycle (docker fully
mocked via FakeRunner), dual-submit shim, and per-task run outcomes. No docker, no network, no
model calls."""
import json

import pytest

import bench.agent_loop as agent_loop
import bench.agent_outcomes as AO
import bench.agentbench_adapter as AB
from bench.tests.conftest import FakeDriver, FakeRunner, complete_result, tool_call

CORPUS = "corpora/agentbench_os_v1.jsonl"
SCRIPTS_ROOT = "corpora/agentbench_os_v1/scripts"


# --------------------------------------------------------------------------- corpus / id scheme
def test_load_corpus_yields_all_144_tasks_with_unique_ids():
    tasks = AB.load_corpus(CORPUS)
    assert len(tasks) == 144
    ids = [t["id"] for t in tasks]
    assert len(set(ids)) == 144
    assert all(t["id"].startswith(f"std-{t['group']:03d}-") for t in tasks)


def test_load_corpus_respects_limit():
    assert len(AB.load_corpus(CORPUS, limit=3)) == 3


def test_load_corpus_rows_carry_index_in_file():
    """index_in_file is the 0-based position within the task's OWN upstream source file --
    distinct from the std-00n-<k> id's k, which is 0-based within the whole GROUP (several files
    concatenated for group 4)."""
    tasks = AB.load_corpus(CORPUS)
    by_file = {}
    for t in tasks:
        key = (t["group"], t["source_file"])
        by_file.setdefault(key, []).append(t["index_in_file"])
    for key, idxs in by_file.items():
        assert idxs == list(range(len(idxs))), key


def test_load_corpus_group_counts_match_upstream_os_yaml():
    tasks = AB.load_corpus(CORPUS)
    counts = {}
    for t in tasks:
        counts[t["group"]] = counts.get(t["group"], 0) + 1
    assert counts == {1: 7, 2: 5, 3: 6, 4: 19, 5: 10, 6: 9, 7: 88}


def test_apply_exclusions_drops_only_listed_ids():
    tasks = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    out = AB.apply_exclusions(tasks, [{"id": "b", "reason": "no_gold"}])
    assert [t["id"] for t in out] == ["a", "c"]


# --------------------------------------------------------------------------- task_config
def test_task_config_match_string_wraps_to_answer_strip_true():
    task = {"group": 4, "evaluation": {"match": "love"}}
    cfg = AB.task_config(task, SCRIPTS_ROOT)
    assert cfg["match"] == {"answer": "love", "strip": True}
    assert cfg["check"] is None


def test_task_config_check_single_dict_wraps_to_list():
    task = {"group": 5, "evaluation": {"check": {"file": "checking/0.sh"}, "example": {"file": "example/0.sh"}}}
    cfg = AB.task_config(task, SCRIPTS_ROOT)
    assert isinstance(cfg["check"], list) and len(cfg["check"]) == 1
    assert cfg["check"][0][0] == "bash"
    assert cfg["example"][0] == "bash"


def test_task_config_check_null_entry_stays_none_until_evaluation():
    task = {"group": 1, "evaluation": {
        "check": [None, {"language": "python", "file": "check/integer-match.py"}],
        "example": {"code": "echo 3"}}}
    cfg = AB.task_config(task, SCRIPTS_ROOT)
    assert cfg["check"][0] is None
    assert cfg["check"][1][0] == "python"
    assert cfg["example"] == ("bash", "echo 3")


def test_task_config_init_as_list_of_scripts():
    task = {"group": 1, "create": {"local": "default",
           "init": [{"code": "echo a"}, {"code": "echo b"}]}}
    cfg = AB.task_config(task, SCRIPTS_ROOT)
    assert cfg["init_scripts"] == [("bash", "echo a"), ("bash", "echo b")]


def test_task_config_mirrors_upstream_malformed_create_list_quirk():
    """data/os_interaction/data/5/new.json #7 (vendored as std-005-7) has a LIST `create` field.
    Upstream task.py only ever tests `"local" in item["create"]` / `"init" in item["create"]`,
    which on a list is always False -> image defaults to "default", no init script. This is a
    real upstream data quirk the adapter must reproduce, not silently fix."""
    tasks = {t["id"]: t for t in AB.load_corpus(CORPUS)}
    task = tasks["std-005-7"]
    assert isinstance(task["create"], list)
    cfg = AB.task_config(task, SCRIPTS_ROOT)
    assert cfg["image"] == "default"
    assert cfg["init_scripts"] == []


def test_task_config_real_corpus_rows_all_load_without_error():
    """Every one of the 144 vendored rows must normalize cleanly (file refs resolve, etc)."""
    for task in AB.load_corpus(CORPUS):
        cfg = AB.task_config(task, SCRIPTS_ROOT)
        assert cfg["image"] in ("default", "packages", "ubuntu")
        assert (cfg["match"] is not None) != (cfg["check"] is not None)  # exactly one evaluation kind


# --------------------------------------------------------------------------- evaluate_match
def test_evaluate_match_strips_before_comparing():
    assert AB.evaluate_match(" love \n", {"answer": "love", "strip": True}) is True


def test_evaluate_match_no_strip_requires_exact():
    assert AB.evaluate_match(" love", {"answer": "love", "strip": False}) is False


def test_evaluate_match_regex():
    assert AB.evaluate_match("abc123", {"regex": r"\d+"}) is True
    assert AB.evaluate_match("abc", {"regex": r"\d+"}) is False


# --------------------------------------------------------------------------- check chain
def test_run_check_chain_null_entry_runs_example_and_chains_stdout():
    runner = FakeRunner(results=[
        FakeRunner.Proc(0, "7\n", ""),      # position 0 (None -> example) with params=[answer]
        FakeRunner.Proc(0, "", ""),         # position 1 (integer-match.py) with params=[answer, "7\n"]
    ])
    ok = AB.run_check_chain("c1", [None, ("python", "check")], ("bash", "example"), "7", runner)
    assert ok is True
    assert len(runner.calls) == 2
    # second call's argv must include BOTH the original answer and the gold stdout from call 1
    second_cmd = runner.calls[1]["cmd"]
    assert second_cmd[-2:] == ["7", "7\n"]


def test_run_check_chain_nonzero_exit_fails():
    runner = FakeRunner(default=FakeRunner.Proc(1, "", "boom"))
    assert AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner) is False


def test_run_check_chain_timeout_fails():
    import subprocess
    runner = FakeRunner(results=[subprocess.TimeoutExpired(cmd="x", timeout=1)])
    assert AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner, timeout=1) is False


def test_run_check_chain_null_with_no_example_fails_without_raising():
    runner = FakeRunner()
    assert AB.run_check_chain("c1", [None], None, "ans", runner) is False
    assert runner.calls == []


# --------------------------------------------------------------------------- D2 exclusion
def _check_task(tid="t1"):
    return {"id": tid, "group": 1, "evaluation": {
        "check": [None, {"code": "x"}], "example": {"code": "echo gold"}}}


def _match_task(tid="m1"):
    return {"id": tid, "group": 1, "evaluation": {"match": "yes"}}


def test_prepare_exclusions_match_tasks_never_excluded_or_examined():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", "diagnostic-should-not-be-called"))
    golds, exclusions = AB.prepare_exclusions([_match_task()], SCRIPTS_ROOT, runner)
    assert exclusions == [] and golds == {}
    assert runner.calls == []    # no docker calls at all for a match task


def _exec_sequenced_runner(exec_results):
    """A fake `subprocess.run`-shaped callable: `docker exec` calls consume `exec_results` in
    order; every other docker call (run/rm) always succeeds. Avoids depending on the exact
    rm/run bookkeeping call count around each `docker exec`."""
    exec_results = list(exec_results)

    def _runner(cmd, **kw):
        if len(cmd) >= 2 and cmd[1] == "exec":
            code, out, err = exec_results.pop(0)
            return FakeRunner.Proc(code, out, err)
        return FakeRunner.Proc(0, "", "")
    return _runner


def test_prepare_exclusions_agreeing_golds_cached_not_excluded():
    runner = _exec_sequenced_runner([(0, "3\n", ""), (0, "3\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert exclusions == []
    assert golds["t1"] == "3\n"


def test_prepare_exclusions_disagreeing_golds_excluded_with_reason():
    runner = _exec_sequenced_runner([(0, "3\n", ""), (0, "4\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t1", "reason": "gold_mismatch", "gold_1": "3\n", "gold_2": "4\n"}]


def test_prepare_exclusions_no_gold_when_example_fails():
    runner = _exec_sequenced_runner([(1, "", "boom"), (0, "3\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t1", "reason": "no_gold"}]


# --------------------------------------------------------------------------- docker primitives
def test_docker_exec_bash_builds_exec_bash_c_with_extra_params():
    runner = FakeRunner()
    AB.docker_exec("c1", ("bash", "echo hi"), 10, runner, extra_params=["a", "b"])
    assert runner.last_cmd == ["docker", "exec", "c1", "bash", "-c", "echo hi", "--", "a", "b"]


def test_docker_exec_python_builds_python3_c_with_argv():
    runner = FakeRunner()
    AB.docker_exec("c1", ("python", "print(1)"), 10, runner, extra_params=["a"])
    assert runner.last_cmd == ["docker", "exec", "c1", "python3", "-c", "print(1)", "a"]


def test_docker_exec_timeout_returns_timed_out_without_raising():
    import subprocess
    runner = FakeRunner(results=[subprocess.TimeoutExpired(cmd="x", timeout=1)])
    res = AB.docker_exec("c1", ("bash", "sleep 99"), 1, runner)
    assert res["timed_out"] is True and res["exit_code"] is None


def test_docker_exec_rejects_unsupported_language():
    with pytest.raises(ValueError):
        AB.docker_exec("c1", ("c++", "int main(){}"), 10, FakeRunner())


def test_truncate_output_caps_and_flags():
    text, truncated = AB.truncate_output("x" * 10, limit=5)
    assert truncated is True and text == "xxxxx"
    text, truncated = AB.truncate_output("short", limit=100)
    assert truncated is False and text == "short"


def test_container_name_sanitizes_unsafe_characters():
    name = AB.container_name("agentbench-os", "std/weird id!")
    assert name == "agentbench-os-std-weird-id-"


def test_sweep_stale_containers_removes_each_match():
    runner = FakeRunner(results=[FakeRunner.Proc(0, "agentbench-os-a\nagentbench-os-b\n", "")])
    removed = AB.sweep_stale_containers("agentbench-os", runner)
    assert removed == ["agentbench-os-a", "agentbench-os-b"]
    rm_calls = [c["cmd"] for c in runner.calls if c["cmd"][:2] == ["docker", "rm"]]
    assert rm_calls == [["docker", "rm", "-f", "agentbench-os-a"], ["docker", "rm", "-f", "agentbench-os-b"]]


def test_remove_container_never_raises_on_runner_error():
    def boom(*a, **k):
        raise OSError("docker daemon gone")
    AB.remove_container("c1", boom)   # must not raise


def test_docker_available_false_on_nonzero_and_on_exception():
    assert AB.docker_available(FakeRunner(default=FakeRunner.Proc(1, "", ""))) is False
    assert AB.docker_available(lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())) is False


def test_images_available_reports_each_image():
    calls = {"n": 0}

    def runner(cmd, **kw):
        calls["n"] += 1
        return FakeRunner.Proc(0 if "default" in cmd[-1] else 1, "", "")
    out = AB.images_available(runner=runner)
    assert out["default"] is True and out["packages"] is False and out["ubuntu"] is False


# --------------------------------------------------------------------------- pilot draw
def test_pilot_draw_is_seeded_and_deterministic():
    ids = [f"std-007-{i}" for i in range(88)]
    a = AB.pilot_draw(ids, seed=42, n=5)
    b = AB.pilot_draw(ids, seed=42, n=5)
    assert a == b and len(a) == 5


def test_pilot_draw_is_not_the_first_items():
    ids = [f"std-007-{i}" for i in range(88)]
    drawn = AB.pilot_draw(ids, seed=42, n=5)
    assert drawn != ids[:5]


# --------------------------------------------------------------------------- dual-submit driver
def test_dualsubmit_driver_passes_through_answer_action_unrenamed():
    inner = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "42"})])])
    d = AB.DualSubmitDriver(inner, timeout=5)
    out = d.complete("m", [], {})
    assert out["tool_calls"][0]["function"]["name"] == "answer_action"
    assert out["tool_calls"][0]["function"]["arguments"] == json.dumps({"answer": "42"})
    assert d.submitted_via == "answer"


def test_dualsubmit_driver_renames_finish_action_to_answer_action_and_folds_thought():
    inner = FakeDriver(script=[complete_result(tool_calls=[tool_call("finish_action", {"thought": "done, no answer"})])])
    d = AB.DualSubmitDriver(inner, timeout=5)
    out = d.complete("m", [], {})
    fn = out["tool_calls"][0]["function"]
    assert fn["name"] == "answer_action"
    assert json.loads(fn["arguments"]) == {"answer": "done, no answer"}
    assert d.submitted_via == "finish"


def test_dualsubmit_driver_records_per_turn_telemetry():
    inner = FakeDriver(script=[
        complete_result(completion_tokens=11, finish_reason="tool_calls", prompt_tokens=5,
                        tool_calls=[tool_call("bash_action", {"script": "ls"})]),
        complete_result(completion_tokens=22, finish_reason="stop", prompt_tokens=9,
                        tool_calls=[tool_call("answer_action", {"answer": "x"})]),
    ])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    d.complete("m", [], {})
    assert [t["completion_tokens"] for t in d.per_turn] == [11, 22]
    assert d.submitted_via == "answer"


# --------------------------------------------------------------------------- build_tools (bash_action)
def test_bash_tool_executes_via_docker_exec_and_truncates():
    runner = FakeRunner(default=FakeRunner.Proc(0, "x" * 9000, ""))
    counters = {}
    tools = AB.build_tools("c1", runner, timeout=10, counters=counters)
    bash = {t.name: t for t in tools}["bash_action"]
    out = bash.fn({"script": "cat big"})
    assert out.endswith("[truncated because the output is too long]")
    assert len(out) < 9000


def test_bash_tool_timeout_increments_counter_and_returns_error_text():
    import subprocess
    runner = FakeRunner(results=[subprocess.TimeoutExpired(cmd="x", timeout=1)])
    counters = {}
    tools = AB.build_tools("c1", runner, timeout=1, counters=counters)
    bash = {t.name: t for t in tools}["bash_action"]
    out = bash.fn({"script": "sleep 999"})
    assert "timed out" in out
    assert counters["tool_timeouts"] == 1


def test_build_tools_schemas_are_upstream_verbatim():
    tools = {t.name: t for t in AB.build_tools("c1", FakeRunner())}
    assert set(tools) == {"bash_action", "finish_action", "answer_action"}
    assert tools["bash_action"].parameters == AB.BASH_TOOL_SCHEMA
    assert tools["finish_action"].parameters == AB.FINISH_TOOL_SCHEMA
    assert tools["answer_action"].parameters == AB.ANSWER_TOOL_SCHEMA


# --------------------------------------------------------------------------- outcome mapping
def test_finalize_outcome_solved_and_passing():
    result = {"outcome": AO.SOLVED, "submitted": {"answer": "7"}}
    outcome, passed, answer = AB.finalize_outcome(result, lambda a: a == "7")
    assert (outcome, passed, answer) == (AO.SOLVED, True, "7")


def test_finalize_outcome_solved_but_failing_grade():
    result = {"outcome": AO.SOLVED, "submitted": {"answer": "wrong"}}
    outcome, passed, answer = AB.finalize_outcome(result, lambda a: a == "7")
    assert (outcome, passed, answer) == (AO.FAILED_TESTS, False, "wrong")


@pytest.mark.parametrize("outcome", [AO.NO_SUBMIT, AO.TURN_CAP, AO.DEADLINE, AO.TOOL_ERROR_LOOP, AO.SERVER_ERROR])
def test_finalize_outcome_non_solved_is_always_a_scored_fail(outcome):
    result = {"outcome": outcome, "submitted": None}
    o, passed, answer = AB.finalize_outcome(result, lambda a: pytest.fail("must not grade a non-submission"))
    assert o == outcome and passed is False and answer is None


def test_episode_converged_uses_last_turn():
    per_turn = [{"completion_tokens": 5, "finish_reason": "tool_calls", "prompt_tokens": 1},
               {"completion_tokens": 9, "finish_reason": "stop", "prompt_tokens": 1}]
    assert AB.episode_converged(per_turn, thinking_budget=100, context_limit=None, max_tokens=None) is True


def test_episode_converged_none_when_no_turns():
    assert AB.episode_converged([], 100, None, None) is None


# --------------------------------------------------------------------------- run_task (per-item)
def _match_cfg_task():
    return {"id": "std-004-0", "group": 4, "labels": ["l1"],
           "evaluation": {"match": "love"}, "description": "say love"}


def test_run_task_cleans_up_container_on_setup_failure():
    runner = FakeRunner(results=[
        FakeRunner.Proc(0, "", ""),   # docker run OK
        FakeRunner.Proc(1, "", "init failed"),  # init script fails -- task has none here though
    ])
    task = {"id": "t1", "group": 1, "labels": [],
           "create": {"local": "default", "init": {"code": "false"}},
           "evaluation": {"match": "x"}, "description": "d"}
    row = AB.run_task("m", task, SCRIPTS_ROOT, FakeDriver(), {}, runner=runner)
    assert row["outcome"] == AO.SERVER_ERROR and row["passed"] is False
    rm_calls = [c for c in runner.calls if c["cmd"][:2] == ["docker", "rm"]]
    assert len(rm_calls) >= 1   # cleanup ran even though setup failed


def test_run_task_cleans_up_container_on_keyboard_interrupt_and_reraises():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))

    class _BoomDriver:
        def complete(self, *a, **k):
            raise KeyboardInterrupt()

    task = _match_cfg_task()
    with pytest.raises(KeyboardInterrupt):
        AB.run_task("m", task, SCRIPTS_ROOT, _BoomDriver(), {}, runner=runner)
    rm_calls = [c for c in runner.calls if c["cmd"][:2] == ["docker", "rm"]]
    assert len(rm_calls) >= 1


def test_run_task_turn_cap_is_a_scored_fail_row_never_dropped():
    runner = FakeRunner(default=FakeRunner.Proc(0, "ok", ""))
    # Always calls bash_action with a DIFFERENT command, never submits -> exhausts max_turns ->
    # TURN_CAP (not the loop_guard's TOOL_ERROR_LOOP, which trips on identical repeats).
    script = [complete_result(tool_calls=[tool_call("bash_action", {"script": f"ls {i}"}, call_id=f"c{i}")])
             for i in range(3)]
    driver = FakeDriver(script=script)
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, max_turns=3, runner=runner)
    assert row["outcome"] == AO.TURN_CAP
    assert row["passed"] is False
    assert row["turns"] == 3


def test_run_task_solved_and_passing_match_task():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner)
    assert row["outcome"] == AO.SOLVED and row["passed"] is True
    assert row["submitted_via"] == "answer" and row["answer"] == "love"


def test_run_task_solved_via_finish_action_is_recorded():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("finish_action", {"thought": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner)
    assert row["outcome"] == AO.SOLVED and row["passed"] is True
    assert row["submitted_via"] == "finish"


def test_run_task_only_one_container_touched_per_task():
    """Every docker invocation in a run_task call must reference the SAME container name."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("bash_action", {"script": "ls"})]),
                                complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, max_turns=5, runner=runner)
    names = {c["cmd"][5] for c in runner.calls if c["cmd"][:2] == ["docker", "run"]}
    assert len(names) == 1
