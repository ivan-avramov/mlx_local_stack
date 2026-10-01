"""M54: bench.agentbench_adapter -- corpus/eval semantics, container lifecycle (docker fully
mocked via FakeRunner / a fake Popen), dual-submit shim, and per-task run outcomes. No docker, no
network, no model calls."""
import json
import subprocess

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


def test_load_corpus_group_counts_match_upstream_os_yaml():
    tasks = AB.load_corpus(CORPUS)
    counts = {}
    for t in tasks:
        counts[t["group"]] = counts.get(t["group"], 0) + 1
    assert counts == {1: 7, 2: 5, 3: 6, 4: 19, 5: 10, 6: 9, 7: 88}


def test_load_corpus_rows_carry_index_in_file():
    tasks = AB.load_corpus(CORPUS)
    by_file = {}
    for t in tasks:
        key = (t["group"], t["source_file"])
        by_file.setdefault(key, []).append(t["index_in_file"])
    for key, idxs in by_file.items():
        assert idxs == list(range(len(idxs))), key


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
    tasks = {t["id"]: t for t in AB.load_corpus(CORPUS)}
    task = tasks["std-005-7"]
    assert isinstance(task["create"], list)
    cfg = AB.task_config(task, SCRIPTS_ROOT)
    assert cfg["image"] == "default"
    assert cfg["init_scripts"] == []


def test_task_config_real_corpus_rows_all_load_without_error():
    for task in AB.load_corpus(CORPUS):
        cfg = AB.task_config(task, SCRIPTS_ROOT)
        assert cfg["image"] in ("default", "packages", "ubuntu")
        assert (cfg["match"] is not None) != (cfg["check"] is not None)


# --------------------------------------------------------------------------- evaluate_match
def test_evaluate_match_strips_before_comparing():
    assert AB.evaluate_match(" love \n", {"answer": "love", "strip": True}) is True


def test_evaluate_match_no_strip_requires_exact():
    assert AB.evaluate_match(" love", {"answer": "love", "strip": False}) is False


def test_evaluate_match_regex():
    assert AB.evaluate_match("abc123", {"regex": r"\d+"}) is True
    assert AB.evaluate_match("abc", {"regex": r"\d+"}) is False


def test_evaluate_match_none_answer_never_crashes():
    """A finish_action with no thought submits Python None; match compares it directly (no
    str() conversion -- that only happens in the CHECK chain, see F14)."""
    assert AB.evaluate_match(None, {"answer": "love", "strip": True}) is False


# --------------------------------------------------------------------------- check chain (incl. F14)
def test_run_check_chain_null_entry_runs_example_and_chains_stdout():
    runner = FakeRunner(results=[
        FakeRunner.Proc(0, "7\n", ""),
        FakeRunner.Proc(0, "", ""),
    ])
    ok = AB.run_check_chain("c1", [None, ("python", "check")], ("bash", "example"), "7", runner)
    assert ok is True
    assert len(runner.calls) == 2
    second_cmd = runner.calls[1]["cmd"]
    assert second_cmd[-2:] == ["7", "7\n"]


def test_run_check_chain_nonzero_exit_fails():
    runner = FakeRunner(default=FakeRunner.Proc(1, "", "boom"))
    assert AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner) is False


def test_run_check_chain_timeout_fails():
    runner = FakeRunner(results=[subprocess.TimeoutExpired(cmd="x", timeout=1)])
    assert AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner, timeout=1) is False


def test_run_check_chain_null_with_no_example_fails_without_raising():
    runner = FakeRunner()
    assert AB.run_check_chain("c1", [None], None, "ans", runner) is False
    assert runner.calls == []


def test_run_check_chain_none_answer_becomes_the_literal_string_None_cold_review_F14():
    """Upstream `params = [str(answer)]`, unconditionally. A finish_action with no `thought`
    submits Python None; str(None) == "None" is what the check script actually receives -- not
    an empty string. This is a MUTATION-SENSITIVE assertion on the literal argv value."""
    runner = FakeRunner()
    AB.run_check_chain("c1", [("bash", "x")], None, None, runner)
    assert runner.last_cmd[-1] == "None"


# --------------------------------------------------------------------------- D2 exclusion (F6/F7)
def _exec_sequenced_runner(exec_results):
    exec_results = list(exec_results)

    def _runner(cmd, **kw):
        if len(cmd) >= 2 and cmd[1] == "exec":
            code, out, err = exec_results.pop(0)
            return FakeRunner.Proc(code, out, err)
        return FakeRunner.Proc(0, "", "")
    return _runner


def _check_task(tid="t1"):
    return {"id": tid, "group": 1, "evaluation": {
        "check": [None, {"code": "x"}], "example": {"code": "echo gold"}}}


def _match_task(tid="m1"):
    return {"id": tid, "group": 1, "evaluation": {"match": "yes"}}


def test_prepare_exclusions_match_tasks_never_excluded_or_examined():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", "diagnostic-should-not-be-called"))
    golds, exclusions = AB.prepare_exclusions([_match_task()], SCRIPTS_ROOT, runner)
    assert exclusions == [] and golds == {}
    assert runner.calls == []


def test_prepare_exclusions_agreeing_golds_cached_not_excluded():
    runner = _exec_sequenced_runner([(0, "3\n", ""), (0, "3\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert exclusions == []
    assert golds["t1"] == "3\n"


def test_prepare_exclusions_two_runs_use_different_placeholders():
    """cold-review F7: the two `compute_gold` calls must pass DIFFERENT answer placeholders, or
    the probe can never detect an example script that reads its answer argument. The example
    script runs via `docker exec <c> bash -c "echo gold" -- <placeholder>` -- the placeholder is
    always the LAST argv element."""
    seen_placeholders = []

    def runner(cmd, **kw):
        if len(cmd) >= 2 and cmd[1] == "exec" and "echo gold" in cmd:
            seen_placeholders.append(cmd[-1])
        return FakeRunner.Proc(0, "x\n", "")
    AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert AB.ANSWER_PLACEHOLDER_PRIMARY in seen_placeholders
    assert AB.ANSWER_PLACEHOLDER_PROBE in seen_placeholders


def test_prepare_exclusions_disagreeing_golds_excluded_as_example_reads_answer():
    runner = _exec_sequenced_runner([(0, "3\n", ""), (0, "4\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t1", "reason": "example_reads_answer",
                           "gold_primary": "3\n", "gold_probe": "4\n"}]


def test_prepare_exclusions_no_gold_when_example_fails():
    runner = _exec_sequenced_runner([(1, "", "boom"), (0, "3\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t1", "reason": "no_gold"}]


def test_prepare_exclusions_no_gold_when_stdout_empty():
    """cold-review F7: an empty stdout at a gold slot is `no_gold`, not a cached empty string."""
    runner = _exec_sequenced_runner([(0, "", ""), (0, "3\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t1", "reason": "no_gold"}]


def test_std_007_84_answer_dependent_example_is_excluded_fixture():
    """A REAL corpus task (std-007-84): its `example` script reads `$1` (the argument) as a user
    id and greps the log for it -- feeding "" vs a sentinel produces different grep match counts,
    exactly the blind spot F7 exists to catch."""
    tasks = {t["id"]: t for t in AB.load_corpus(CORPUS)}
    task = tasks["std-007-84"]
    cfg = AB.task_config(task, SCRIPTS_ROOT)
    assert cfg["example"][0] == "bash" and "$1" in cfg["example"][1]

    # The real script is `grep "error" system_logs.log | grep " $USER_ID " | wc -l`: an empty
    # USER_ID greps for a literal double space (`"  "`), which is a DIFFERENT, data-dependent match
    # count than a sentinel that appears nowhere in the log. Model that data-dependence directly
    # rather than re-simulating grep: the two placeholders must get different counts.
    def runner(cmd, **kw):
        if len(cmd) >= 2 and cmd[1] == "exec":
            placeholder = cmd[-1]
            count = 2 if placeholder == AB.ANSWER_PLACEHOLDER_PRIMARY else 0
            return FakeRunner.Proc(0, f"{count}\n", "")
        return FakeRunner.Proc(0, "", "")

    golds, exclusions = AB.prepare_exclusions([task], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions and exclusions[0]["reason"] == "example_reads_answer"
    assert exclusions[0]["id"] == "std-007-84"


# --------------------------------------------------------------------------- corpus-level exclusions artifact (F6)
def test_exclusions_artifact_path_is_corpus_sibling():
    p = AB.exclusions_artifact_path("corpora/agentbench_os_v1.jsonl")
    assert str(p) == "corpora/agentbench_os_v1.exclusions.json"


def test_write_and_read_exclusions_artifact_roundtrip(tmp_path):
    path = tmp_path / "x.exclusions.json"
    AB.write_exclusions_artifact(path, corpus_sha256="abc", image_ids={"default": "sha256:1"},
                                 golds={"t1": "3"}, exclusions=[{"id": "t2", "reason": "no_gold"}],
                                 complete=True)
    doc = AB.read_exclusions_artifact(path)
    assert doc["corpus_sha256"] == "abc" and doc["complete"] is True
    assert doc["golds"] == {"t1": "3"}


def test_read_exclusions_artifact_missing_returns_none(tmp_path):
    assert AB.read_exclusions_artifact(tmp_path / "nope.json") is None


def test_validate_exclusions_artifact_accepts_matching_state():
    doc = {"corpus_sha256": "abc", "image_ids": {"default": "id1"}, "complete": True}
    assert AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={"default": "id1"}) is None


def test_validate_exclusions_artifact_refuses_missing():
    assert "run --prepare" in AB.validate_exclusions_artifact(None, corpus_sha256="x", image_ids={})


def test_validate_exclusions_artifact_refuses_incomplete():
    doc = {"corpus_sha256": "abc", "image_ids": {}, "complete": False}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={})
    assert reason and "complete" in reason


def test_validate_exclusions_artifact_refuses_corpus_drift():
    doc = {"corpus_sha256": "OLD", "image_ids": {}, "complete": True}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="NEW", image_ids={})
    assert reason and "corpus" in reason


def test_validate_exclusions_artifact_refuses_image_drift():
    doc = {"corpus_sha256": "abc", "image_ids": {"default": "old"}, "complete": True}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={"default": "new"})
    assert reason and "image" in reason


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
    runner = FakeRunner(results=[subprocess.TimeoutExpired(cmd="x", timeout=1)])
    res = AB.docker_exec("c1", ("bash", "sleep 99"), 1, runner)
    assert res["timed_out"] is True and res["exit_code"] is None


def test_docker_exec_rejects_unsupported_language():
    with pytest.raises(ValueError):
        AB.docker_exec("c1", ("c++", "int main(){}"), 10, FakeRunner())


def test_truncate_output_matches_upstream_800_780_mechanism():
    """cold-review F5(b): upstream keeps the first 780 chars (NOT a flat 800-char cap) plus the
    marker, so a truncated result is slightly LONGER than the 800-char trigger."""
    text, truncated = AB.truncate_output("x" * 900)
    assert truncated is True
    assert text == "x" * 780 + "\n[truncated because the output is too long]"


def test_truncate_output_untouched_under_limit():
    text, truncated = AB.truncate_output("short")
    assert truncated is False and text == "short"


def test_truncate_output_boundary_800_is_not_truncated():
    text, truncated = AB.truncate_output("x" * 800)
    assert truncated is False and text == "x" * 800


def test_wrap_os_output_prefixes_nonempty_text_verbatim():
    assert AB.wrap_os_output("hi") == "The output of the OS:\n\nhi"


def test_wrap_os_output_empty_sentence_is_upstream_verbatim():
    assert AB.wrap_os_output("") == "The output of the OS is empty."


def test_container_name_sanitizes_unsafe_characters():
    name = AB.container_name("agentbench-os-run", "std/weird id!")
    assert name == "agentbench-os-run-std-weird-id-"


def test_sweep_stale_containers_removes_each_match():
    runner = FakeRunner(results=[FakeRunner.Proc(0, "agentbench-os-run-a\nagentbench-os-run-b\n", "")])
    removed = AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner)
    assert removed == ["agentbench-os-run-a", "agentbench-os-run-b"]
    rm_calls = [c["cmd"] for c in runner.calls if c["cmd"][:2] == ["docker", "rm"]]
    assert rm_calls == [["docker", "rm", "-f", "agentbench-os-run-a"],
                        ["docker", "rm", "-f", "agentbench-os-run-b"]]


def test_sweep_stale_containers_generate_prefix_never_matches_prepare_containers():
    """cold-review F16: the old scheme's generate prefix was a literal PREFIX of the prepare
    prefix, so a generate-mode sweep killed live prepare containers and vice versa."""
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["docker", "ps"]:
            # a real `docker ps --filter name=^agentbench-os-run-` would never list a
            # `agentbench-os-prep-...` container in the first place; assert the filter used says so
            assert cmd[3] == f"name=^{AB.GENERATE_CONTAINER_PREFIX}-"
            return FakeRunner.Proc(0, "", "")
        return FakeRunner.Proc(0, "", "")
    AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner)
    assert not AB.GENERATE_CONTAINER_PREFIX.startswith(AB.PREPARE_CONTAINER_PREFIX)
    assert not AB.PREPARE_CONTAINER_PREFIX.startswith(AB.GENERATE_CONTAINER_PREFIX)


def test_remove_container_never_raises_on_runner_error():
    def boom(*a, **k):
        raise OSError("docker daemon gone")
    AB.remove_container("c1", boom)


def test_create_container_includes_upstream_resource_flags_F4b():
    runner = FakeRunner()
    AB.create_container("local-os/default", "c1", runner)
    cmd = runner.last_cmd
    assert "-w" in cmd and cmd[cmd.index("-w") + 1] == "/root"
    assert "--memory" in cmd and cmd[cmd.index("--memory") + 1] == "1g"
    assert "--memory-swap" in cmd and cmd[cmd.index("--memory-swap") + 1] == "1g"
    assert "--cpus" in cmd and cmd[cmd.index("--cpus") + 1] == "2"


def test_docker_available_false_on_nonzero_and_on_exception():
    assert AB.docker_available(FakeRunner(default=FakeRunner.Proc(1, "", ""))) is False
    assert AB.docker_available(lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())) is False


def test_images_available_reports_each_image():
    def runner(cmd, **kw):
        return FakeRunner.Proc(0 if "default" in cmd[-1] else 1, "", "")
    out = AB.images_available(runner=runner)
    assert out["default"] is True and out["packages"] is False and out["ubuntu"] is False


def test_current_image_ids_reports_stdout_or_none():
    def runner(cmd, **kw):
        if "default" in cmd[-1]:
            return FakeRunner.Proc(0, "sha256:abc\n", "")
        return FakeRunner.Proc(1, "", "no such image")
    out = AB.current_image_ids(runner=runner)
    assert out["default"] == "sha256:abc" and out["packages"] is None


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


# --------------------------------------------------------------------------- PersistentShell (F4a)
class _FakeShellProc:
    """A fake `subprocess.Popen` standing in for `docker exec -i <c> /bin/bash --login`.
    `responder(written_text) -> (output_lines, exit_code) | None` (None = hang forever, simulating
    a runaway command for the timeout path)."""

    def __init__(self, responder):
        self.responder = responder
        self._pending = []
        self.killed = False
        self.terminated = False
        self.stdin = self
        self.stdout = self

    def write(self, s):
        import re as _re
        m = _re.search(r"echo (\S+)\$\?", s)
        sentinel = m.group(1)
        resp = self.responder(s)
        if resp is None:
            self._pending = None   # readline() will block (simulated via a long sleep)
            return
        out_lines, rc = resp
        self._pending = list(out_lines) + [f"{sentinel}{rc}\n"]

    def flush(self):
        pass

    def close(self):
        pass

    def readline(self):
        if self._pending is None:
            import time as _t
            _t.sleep(2)             # "hangs" -- long enough to exceed any test's tiny timeout
            return ""
        if not self._pending:
            return ""
        return self._pending.pop(0)

    def kill(self):
        self.killed = True

    def terminate(self):
        self.terminated = True


def test_persistent_shell_run_returns_output_and_exit_code():
    def responder(written):
        assert "pwd" in written
        return (["/root\n"], 0)
    shell = AB.PersistentShell("c1", timeout=5, popen=lambda *a, **k: _FakeShellProc(responder))
    shell.start()
    res = shell.run("pwd")
    assert res == {"output": "/root\n", "exit_code": 0, "timed_out": False}


def test_persistent_shell_wraps_command_with_in_container_timeout_kill():
    captured = {}

    def responder(written):
        captured["written"] = written
        return (["ok\n"], 0)
    shell = AB.PersistentShell("c1", timeout=30, popen=lambda *a, **k: _FakeShellProc(responder))
    shell.start()
    shell.run("echo ok")
    assert "timeout -s KILL 30" in captured["written"]
    assert "echo ok" in captured["written"]


def test_persistent_shell_state_persists_across_calls_via_sentinel_protocol():
    """Simulates `cd /tmp` changing the EFFECTIVE state seen by a later `pwd` -- the responder
    tracks cwd itself (as the real persistent bash process would), proving the protocol threads
    state across `run()` calls rather than resetting per call (which a fresh `docker exec` per
    command, the pre-cold-review design, could never do)."""
    state = {"cwd": "/root"}

    def responder(written):
        if "cd /tmp" in written:
            state["cwd"] = "/tmp"
            return ([], 0)
        if "pwd" in written:
            return ([f"{state['cwd']}\n"], 0)
        return ([], 0)
    shell = AB.PersistentShell("c1", timeout=5, popen=lambda *a, **k: _FakeShellProc(responder))
    shell.start()
    shell.run("cd /tmp")
    res = shell.run("pwd")
    assert res["output"] == "/tmp\n"


def test_persistent_shell_timeout_kills_process_and_reports_timed_out():
    proc_holder = {}

    def make_proc(*a, **k):
        p = _FakeShellProc(lambda written: None)   # hangs forever
        proc_holder["proc"] = p
        return p
    shell = AB.PersistentShell("c1", timeout=0.01, popen=make_proc, join_margin=0.01)
    shell.start()
    res = shell.run("sleep 999")
    assert res["timed_out"] is True
    assert proc_holder["proc"].killed is True


def test_persistent_shell_run_before_start_raises():
    shell = AB.PersistentShell("c1")
    with pytest.raises(RuntimeError):
        shell.run("pwd")


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


def test_dualsubmit_driver_finish_action_with_no_thought_answer_is_none_not_empty_string():
    """cold-review F14: must stay Python None (not "") -- str() conversion happens only inside the
    check chain, not here."""
    inner = FakeDriver(script=[complete_result(tool_calls=[tool_call("finish_action", {})])])
    d = AB.DualSubmitDriver(inner, timeout=5)
    out = d.complete("m", [], {})
    fn = out["tool_calls"][0]["function"]
    assert json.loads(fn["arguments"]) == {"answer": None}


def test_dualsubmit_driver_records_per_turn_telemetry_including_decode_tps():
    inner = FakeDriver(script=[
        complete_result(completion_tokens=100, finish_reason="tool_calls", prompt_tokens=5,
                        tool_calls=[tool_call("bash_action", {"script": "ls"})],
                        raw_timings={"predicted_ms": 2000.0}),
        complete_result(completion_tokens=22, finish_reason="stop", prompt_tokens=9,
                        tool_calls=[tool_call("answer_action", {"answer": "x"})]),
    ])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    d.complete("m", [], {})
    assert [t["completion_tokens"] for t in d.per_turn] == [100, 22]
    # 100 completion tokens / 2.0s = 50 tok/s, computed from completion_tokens/generation_ms
    # (cold-review F8), not merely copied from a pre-existing `decode_tps` field.
    assert d.per_turn[0]["decode_tps"] == pytest.approx(50.0)
    assert d.submitted_via == "answer"


def test_dualsubmit_driver_decode_tps_falls_back_to_servers_own_value_without_timings():
    inner = FakeDriver(script=[complete_result(completion_tokens=10, decode_tps=7.5, raw_timings={})])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    assert d.per_turn[0]["decode_tps"] == 7.5


# --------------------------------------------------------------------------- build_tools (bash_action)
def test_bash_tool_executes_via_persistent_shell_and_wraps_output():
    shell = AB.PersistentShell("c1", timeout=10,
                               popen=lambda *a, **k: _FakeShellProc(lambda w: (["hello\n"], 0)))
    shell.start()
    counters = {}
    tools = AB.build_tools(shell, timeout=10, counters=counters)
    bash = {t.name: t for t in tools}["bash_action"]
    out = bash.fn({"script": "echo hello"})
    assert out == "The output of the OS:\n\nhello\n"


def test_bash_tool_empty_output_uses_upstream_sentence():
    shell = AB.PersistentShell("c1", timeout=10, popen=lambda *a, **k: _FakeShellProc(lambda w: ([], 0)))
    shell.start()
    tools = AB.build_tools(shell, timeout=10, counters={})
    bash = {t.name: t for t in tools}["bash_action"]
    assert bash.fn({"script": "true"}) == "The output of the OS is empty."


def test_bash_tool_truncates_at_800_keeping_780():
    big = "x" * 2000 + "\n"

    def responder(w):
        return ([big], 0)
    shell = AB.PersistentShell("c1", timeout=10, popen=lambda *a, **k: _FakeShellProc(responder))
    shell.start()
    tools = AB.build_tools(shell, timeout=10, counters={})
    bash = {t.name: t for t in tools}["bash_action"]
    out = bash.fn({"script": "cat big"})
    assert out.endswith("[truncated because the output is too long]")
    body = out[len("The output of the OS:\n\n"):]
    assert body == "x" * 780 + "\n[truncated because the output is too long]"


def test_bash_tool_timeout_kills_shell_sets_flag_and_aborts_episode():
    shell = AB.PersistentShell("c1", timeout=0.01, join_margin=0.01,
                               popen=lambda *a, **k: _FakeShellProc(lambda w: None))
    shell.start()
    counters, flag = {}, {}
    tools = AB.build_tools(shell, timeout=0.01, counters=counters, exec_timeout_flag=flag)
    bash = {t.name: t for t in tools}["bash_action"]
    with pytest.raises(agent_loop.AbortEpisode) as ei:
        bash.fn({"script": "sleep 999"})
    assert ei.value.outcome == AO.FAILED_TESTS
    assert counters["tool_timeouts"] == 1
    assert flag["hit"] is True


def test_build_tools_schemas_are_upstream_verbatim():
    shell = AB.PersistentShell("c1")
    tools = {t.name: t for t in AB.build_tools(shell)}
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


# --------------------------------------------------------------------------- convergence (F2)
def test_evaluate_convergence_tool_calls_finish_reason_counts_as_converged():
    """cold-review F2: the server returns finish_reason="tool_calls" on every tool-calling turn;
    a rule that only accepted "stop" would mark EVERY multi-turn episode non-converged."""
    per_turn = [{"completion_tokens": 5, "finish_reason": "tool_calls", "prompt_tokens": 1}]
    out = AB.evaluate_convergence(per_turn, thinking_budget=100, context_limit=None, max_tokens=None)
    assert out["converged"] is True
    assert out["per_turn_finish_reasons"] == ["tool_calls"]
    assert out["budget_hits"] == 0


def test_evaluate_convergence_budget_hit_turn_is_not_converged_and_counted():
    per_turn = [{"completion_tokens": 100, "finish_reason": "tool_calls", "prompt_tokens": 1},
               {"completion_tokens": 5, "finish_reason": "stop", "prompt_tokens": 1}]
    out = AB.evaluate_convergence(per_turn, thinking_budget=100, context_limit=None, max_tokens=None)
    assert out["converged"] is False
    assert out["budget_hits"] == 1
    assert out["per_turn_converged"] == [False, True]


def test_evaluate_convergence_unrecognised_finish_reason_not_converged():
    per_turn = [{"completion_tokens": 5, "finish_reason": "length", "prompt_tokens": 1}]
    out = AB.evaluate_convergence(per_turn, thinking_budget=100, context_limit=None, max_tokens=None)
    assert out["converged"] is False


def test_evaluate_convergence_none_for_empty_episode():
    out = AB.evaluate_convergence([], thinking_budget=100, context_limit=None, max_tokens=None)
    assert out["converged"] is None and out["budget_hits"] == 0


def test_evaluate_convergence_uses_resolved_budget_per_turn():
    """As prompt_tokens grows, the resolved budget SHRINKS -- a turn can hit it even though its
    own completion_tokens is well under the DECLARED budget."""
    per_turn = [{"completion_tokens": 50, "finish_reason": "tool_calls", "prompt_tokens": 90}]
    out = AB.evaluate_convergence(per_turn, thinking_budget=1000, context_limit=100, max_tokens=100)
    # resolved = min(1000, int(min(100, 100-90)*0.8)) = min(1000, 8) = 8; 50 >= 8 -> budget hit
    assert out["budget_hits"] == 1
    assert out["converged"] is False


# --------------------------------------------------------------------------- run_task (per-item)
def _match_cfg_task():
    return {"id": "std-004-0", "group": 4, "labels": ["l1"],
           "evaluation": {"match": "love"}, "description": "say love"}


def _shell_popen_ok():
    return lambda *a, **k: _FakeShellProc(lambda w: ([], 0))


def test_run_task_cleans_up_container_AFTER_docker_run_on_init_failure():
    """cold-review F11: the OLD test only proved a pre-clean `rm` happened (which exists even with
    `finally` deleted), and failed at `docker run` rather than `init`. This one fails specifically
    at INIT (docker run succeeds) and asserts an rm call occurs strictly AFTER the `docker run`
    call -- verified by deleting the `finally` clause by hand and watching this go red."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    calls_seen = {"init_failed": False}

    def runner2(cmd, **kw):
        runner.calls.append({"cmd": cmd})
        if len(cmd) >= 2 and cmd[1] == "exec":
            calls_seen["init_failed"] = True
            return FakeRunner.Proc(1, "", "init failed")
        return FakeRunner.Proc(0, "", "")
    task = {"id": "t1", "group": 1, "labels": [],
           "create": {"local": "default", "init": {"code": "false"}},
           "evaluation": {"match": "x"}, "description": "d"}
    row = AB.run_task("m", task, SCRIPTS_ROOT, FakeDriver(), {}, runner=runner2,
                      popen=_shell_popen_ok())
    assert row["outcome"] == AO.SERVER_ERROR and row["passed"] is False and row["setup_error"] is True
    assert calls_seen["init_failed"] is True
    run_idx = next(i for i, c in enumerate(runner.calls) if c["cmd"][:2] == ["docker", "run"])
    rm_after = [c for c in runner.calls[run_idx + 1:] if c["cmd"][:2] == ["docker", "rm"]]
    assert rm_after, "no `docker rm` after `docker run` -- cleanup did not run post-creation"


def test_run_task_cleans_up_container_on_keyboard_interrupt_and_reraises():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))

    class _BoomDriver:
        def complete(self, *a, **k):
            raise KeyboardInterrupt()

    task = _match_cfg_task()
    with pytest.raises(KeyboardInterrupt):
        AB.run_task("m", task, SCRIPTS_ROOT, _BoomDriver(), {}, runner=runner, popen=_shell_popen_ok())
    rm_calls = [c for c in runner.calls if c["cmd"][:2] == ["docker", "rm"]]
    assert len(rm_calls) >= 1


def test_run_task_transport_failure_raises_and_writes_no_row_F1():
    """cold-review F1: driver.complete raising (HTTP 500/timeout/connection error) must ESCALATE,
    never be graded -- run_task raises TransportFailure (container still cleaned up), the CALLER
    is responsible for not appending a row."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))

    class _Http500Driver:
        def complete(self, *a, **k):
            raise ConnectionError("HTTP 500")

    task = _match_cfg_task()
    with pytest.raises(AB.TransportFailure, match="std-004-0"):
        AB.run_task("m", task, SCRIPTS_ROOT, _Http500Driver(), {}, runner=runner, popen=_shell_popen_ok())
    rm_calls = [c for c in runner.calls if c["cmd"][:2] == ["docker", "rm"]]
    assert len(rm_calls) >= 1   # container still cleaned up despite the escalation


def test_run_task_no_submit_only_when_cap_reached_without_any_submit_F5a():
    runner = FakeRunner(default=FakeRunner.Proc(0, "ok", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[])] * 3)   # never calls a tool, ever
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, max_turns=3, runner=runner,
                      popen=_shell_popen_ok())
    assert row["outcome"] == AO.NO_SUBMIT
    assert row["turns"] == 3        # ran the FULL budget (reprompted, didn't stop at turn 1)


def test_run_task_turn_cap_when_tools_were_used_but_never_submitted():
    runner = FakeRunner(default=FakeRunner.Proc(0, "ok", ""))
    script = [complete_result(tool_calls=[tool_call("bash_action", {"script": f"ls {i}"}, call_id=f"c{i}")])
             for i in range(3)]
    driver = FakeDriver(script=script)
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, max_turns=3, runner=runner,
                      popen=_shell_popen_ok())
    assert row["outcome"] == AO.TURN_CAP
    assert row["passed"] is False
    assert row["turns"] == 3


def test_run_task_single_tool_call_per_turn_ignores_a_trailing_submit_F5c():
    runner = FakeRunner(default=FakeRunner.Proc(0, "ok", ""))
    tcs = [tool_call("bash_action", {"script": "ls"}, call_id="c1"),
          tool_call("answer_action", {"answer": "love"}, call_id="c2")]
    driver = FakeDriver(script=[complete_result(tool_calls=tcs),
                                complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"}, call_id="c3")])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, max_turns=5, runner=runner,
                      popen=_shell_popen_ok())
    assert row["turns"] == 2            # turn 1's trailing submit was ignored; turn 2 actually submitted
    assert row["outcome"] == AO.SOLVED and row["passed"] is True


def test_run_task_solved_and_passing_match_task():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["outcome"] == AO.SOLVED and row["passed"] is True
    assert row["submitted_via"] == "answer" and row["answer"] == "love"
    assert row["setup_error"] is False


def test_run_task_solved_via_finish_action_is_recorded():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("finish_action", {"thought": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["outcome"] == AO.SOLVED and row["passed"] is True
    assert row["submitted_via"] == "finish"


def test_run_task_repeat_calls_counted_not_guard_aborted_F5d():
    """The loop guard is disabled for this axis: identical repeats must NOT abort the episode --
    they are reported as a `repeat_calls` counter instead."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "ok", ""))
    script = [complete_result(tool_calls=[tool_call("bash_action", {"script": "ls"}, call_id=f"c{i}")])
             for i in range(5)]   # same identical call 5x -- would trip the default guard at 3
    driver = FakeDriver(script=script)
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, max_turns=5, runner=runner,
                      popen=_shell_popen_ok())
    assert row["outcome"] == AO.TURN_CAP          # not tool_error_loop
    assert row["repeat_calls"] >= 3


def test_run_task_exec_timeout_ends_episode_and_marks_row_F4a():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("bash_action", {"script": "sleep 999"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, exec_timeout=0.01,
                      popen=lambda *a, **k: _FakeShellProc(lambda w: None))
    assert row["exec_timeout"] is True
    assert row["outcome"] == AO.FAILED_TESTS and row["passed"] is False


def test_run_task_only_one_container_touched_per_task():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("bash_action", {"script": "ls"})]),
                                complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, max_turns=5, runner=runner, popen=_shell_popen_ok())
    names = {c["cmd"][5] for c in runner.calls if c["cmd"][:2] == ["docker", "run"]}
    assert len(names) == 1


def test_run_task_setup_error_flagged_rows_carry_decode_tps_none_not_crash():
    runner = FakeRunner(default=FakeRunner.Proc(1, "", "boom"))   # docker run itself fails
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, FakeDriver(), {}, runner=runner, popen=_shell_popen_ok())
    assert row["setup_error"] is True and row["decode_tps"] is None
