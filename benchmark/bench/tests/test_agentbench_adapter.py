"""M54: bench.agentbench_adapter -- corpus/eval semantics, container lifecycle (docker fully
mocked via FakeRunner / a fake Popen), dual-submit shim, and per-task run outcomes. No docker, no
network, no model calls."""
import functools
import json
import os
import re
import signal
import subprocess
import time
import uuid

import pytest

import bench.agent_loop as agent_loop
import bench.agent_outcomes as AO
import bench.agentbench_adapter as AB
from bench.tests.conftest import FakeDriver, FakeRunner, complete_result, tool_call

CORPUS = "corpora/agentbench_os_v1.jsonl"
SCRIPTS_ROOT = "corpora/agentbench_os_v1/scripts"


class _TestHang(Exception):
    pass


def _timeout(seconds):
    """3rd cold review: guards every REAL-bash test against a hang caused by a regression in
    PersistentShell's OWN Python-side timeout -- this is a backstop so a broken timeout fails the
    ONE test loudly instead of hanging the whole suite, never a substitute for the real fix.
    `pytest-timeout` is not installed in .venv-bench; this is a signal.alarm-based guard (Unix
    only, fine on macOS/Linux CI)."""
    def _decorator(fn):
        @functools.wraps(fn)
        def _wrapped(*a, **kw):
            def _handler(signum, frame):
                raise _TestHang(f"{fn.__name__} exceeded its {seconds}s guard -- "
                               "PersistentShell's own timeout likely regressed")
            old = signal.signal(signal.SIGALRM, _handler)
            signal.setitimer(signal.ITIMER_REAL, seconds)
            try:
                return fn(*a, **kw)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old)
        return _wrapped
    return _decorator


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
    ok, gold_live = AB.run_check_chain("c1", [None, ("python", "check")], ("bash", "example"), "7", runner)
    assert ok is True
    assert gold_live == "7\n"   # R5: the null-slot stdout, captured live
    assert len(runner.calls) == 2
    second_cmd = runner.calls[1]["cmd"]
    assert second_cmd[-2:] == ["7", "7\n"]


def test_run_check_chain_nonzero_exit_fails():
    runner = FakeRunner(default=FakeRunner.Proc(1, "", "boom"))
    ok, gold_live = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is False and gold_live is None


def test_run_check_chain_timeout_fails():
    runner = FakeRunner(results=[subprocess.TimeoutExpired(cmd="x", timeout=1)])
    ok, gold_live = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner, timeout=1)
    assert ok is False and gold_live is None


def test_run_check_chain_null_with_no_example_fails_without_raising():
    runner = FakeRunner()
    ok, gold_live = AB.run_check_chain("c1", [None], None, "ans", runner)
    assert ok is False and gold_live is None
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


def test_prepare_exclusions_two_placeholder_runs_are_genuinely_different_R6():
    """R6(2), mutation-resistant: the previous test's `in` checks pass even if both calls used the
    SAME placeholder (membership doesn't prove distinctness). Capture the actual two values IN
    ORDER and assert they differ -- a mutation that made both calls pass "1" must fail this."""
    seen = []

    def runner(cmd, **kw):
        if len(cmd) >= 2 and cmd[1] == "exec" and "echo gold" in cmd:
            seen.append(cmd[-1])
        return FakeRunner.Proc(0, "x\n", "")
    AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert len(seen) == 2
    assert seen[0] != seen[1]


def test_answer_placeholder_constants_are_distinct():
    assert AB.ANSWER_PLACEHOLDER_PRIMARY != AB.ANSWER_PLACEHOLDER_PROBE


def test_prepare_exclusions_disagreeing_golds_excluded_as_gold_mismatch():
    runner = _exec_sequenced_runner([(0, "3\n", ""), (0, "4\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t1", "reason": "gold_mismatch",
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


def _local_bash_shim(cwd):
    """A `runner` that routes `docker run`/`rm` to no-ops and `docker exec <c> bash -c <code>
    [-- params...]` to a REAL local `/bin/bash` with `cwd=cwd` standing in for the container's
    filesystem (2nd cold review N3/N4: "running them under real local bash with a tmp-root
    substitution"). This executes the ACTUAL vendored init/example scripts, not a re-implementation
    of their logic."""
    def runner(cmd, **kw):
        if cmd[:2] in (["docker", "run"], ["docker", "rm"]):
            return FakeRunner.Proc(0, "", "")
        if cmd[:2] == ["docker", "exec"]:
            tail = cmd[3:]   # ["bash", "-c", code, ...maybe "--", *params]
            proc = subprocess.run(tail, cwd=str(cwd), capture_output=True, text=True, timeout=10)
            return FakeRunner.Proc(proc.returncode, proc.stdout, proc.stderr)
        return FakeRunner.Proc(0, "", "")
    return runner


@_timeout(10)
def test_std_007_84_example_script_genuinely_reads_its_answer_argument(tmp_path):
    """A REAL corpus task (std-007-84): its `example` script is
    `grep "error" system_logs.log | grep " $USER_ID " | wc -l` -- genuinely data-dependent on its
    argument (the log's real user ids are 15/28/01). Proven here with REAL local bash (the real
    vendored init script writes the real log fixture, the real vendored example script runs the
    real grep pipeline) and DISCRIMINATING placeholders ("15" vs "28", values that actually appear
    in the fixture log) -- not a hand-simulated count, which was blind to whether this was really
    true of the vendored script text."""
    tasks = {t["id"]: t for t in AB.load_corpus(CORPUS)}
    task = tasks["std-007-84"]
    cfg = AB.task_config(task, SCRIPTS_ROOT)
    assert cfg["example"][0] == "bash" and "$1" in cfg["example"][1]
    assert AB._check_list_has_gold_slot(cfg["check"])

    runner = _local_bash_shim(tmp_path)
    ok1, g1 = AB.run_reference(cfg["image"], cfg["init_scripts"], cfg["start"], cfg["example"],
                               "c1", runner, 10, "15")
    ok2, g2 = AB.run_reference(cfg["image"], cfg["init_scripts"], cfg["start"], cfg["example"],
                               "c2", runner, 10, "28")
    assert ok1 and ok2
    assert g1.strip() == "2" and g2.strip() == "1"   # genuinely different -- the script DOES read $1
    assert g1 != g2


@_timeout(10)
def test_std_007_84_with_production_placeholders_is_a_known_miss(tmp_path):
    """HONEST LIMITATION, found by running the REAL script rather than assuming: the production
    placeholders "1"/"2" (N4: "plausible-looking answers") do NOT happen to appear anywhere in
    std-007-84's specific fixture log (whose real user ids are 15/28/01), so BOTH placeholders grep
    to the same count (0) and this task is NOT excluded under the real probe -- even though the
    script provably reads its argument (see the test above with discriminating placeholders "15"/
    "28"). This is a genuine gap in a GENERIC two-placeholder heuristic, not a bug in the
    disagreement-detection mechanism itself; flagged for the operator rather than silently
    asserting a false "it works" with placeholders chosen to make this one task pass."""
    tasks = {t["id"]: t for t in AB.load_corpus(CORPUS)}
    task = tasks["std-007-84"]
    golds, exclusions = AB.prepare_exclusions([task], SCRIPTS_ROOT, _local_bash_shim(tmp_path))
    assert exclusions == []                              # NOT caught by the generic probe
    assert golds["std-007-84"].strip() == "0"             # both placeholders agree, wrongly


@_timeout(10)
def test_std_004_47_pure_state_check_requires_only_one_reference_run_no_placeholder_probe():
    """A REAL corpus task with NO gold slot in its check list (Q47's vendored task): every check
    position is a literal checker script, so the live grading chain never runs `example` with the
    model's answer -- probing with two placeholders would test nothing. Only the reference
    (init+start+example) needs to run, once, successfully, and no gold is ever cached."""
    tasks = {t["id"]: t for t in AB.load_corpus(CORPUS)}
    task = next(t for t in tasks.values() if t["source_file"] == "Q47.json")
    cfg = AB.task_config(task, SCRIPTS_ROOT)
    assert not AB._check_list_has_gold_slot(cfg["check"])

    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return FakeRunner.Proc(0, "", "")
    golds, exclusions = AB.prepare_exclusions([task], SCRIPTS_ROOT, runner)
    assert exclusions == [] and golds == {}
    run_calls = [c for c in calls if c[:2] == ["docker", "run"]]
    assert len(run_calls) == 1          # ONE fresh container -- not the two-placeholder probe


def test_reference_failed_reason_when_no_gold_slot_and_example_fails():
    task = {"id": "t2", "group": 1, "evaluation": {
        "check": [{"code": "exit 0"}, {"code": "exit 0"}], "example": {"code": "exit 1"}}}

    def runner(cmd, **kw):
        if cmd[:2] == ["docker", "exec"]:
            return FakeRunner.Proc(1, "", "example failed")   # only the example script fails
        return FakeRunner.Proc(0, "", "")
    golds, exclusions = AB.prepare_exclusions([task], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t2", "reason": "reference_failed"}]


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


# --------------------------------------------------------------------------- manual exclusions
def test_manual_exclusions_path_is_corpus_sibling():
    p = AB.manual_exclusions_path("corpora/agentbench_os_v1.jsonl")
    assert str(p) == "corpora/agentbench_os_v1.manual_exclusions.json"


def test_load_manual_exclusions_missing_file_returns_empty_dict(tmp_path):
    assert AB.load_manual_exclusions(tmp_path / "nope.json") == {}


def test_load_manual_exclusions_reads_the_real_vendored_file():
    manual = AB.load_manual_exclusions("corpora/agentbench_os_v1.manual_exclusions.json")
    assert "std-007-84" in manual
    assert "placeholder probe" in manual["std-007-84"]


def test_prepare_exclusions_manual_entry_excludes_without_any_probing():
    task = _check_task("std-007-84")
    runner = FakeRunner(default=FakeRunner.Proc(0, "", "should not be called"))
    golds, exclusions = AB.prepare_exclusions([task], SCRIPTS_ROOT, runner,
                                              manual={"std-007-84": "known numeric-id blind spot"})
    assert exclusions == [{"id": "std-007-84", "reason": "manual",
                           "note": "known numeric-id blind spot"}]
    assert golds == {}
    assert runner.calls == []    # never probed, never even touched docker


def test_prepare_exclusions_manual_does_not_affect_other_tasks():
    tasks = [_check_task("std-007-84"), _match_task("m1")]
    golds, exclusions = AB.prepare_exclusions(tasks, SCRIPTS_ROOT, FakeRunner(),
                                              manual={"std-007-84": "x"})
    assert [e["id"] for e in exclusions] == ["std-007-84"]   # m1 (match) still never examined


def test_write_exclusions_artifact_records_manual_exclusions_sha(tmp_path):
    path = tmp_path / "x.exclusions.json"
    AB.write_exclusions_artifact(path, corpus_sha256="abc", image_ids={}, golds={}, exclusions=[],
                                 complete=True, manual_exclusions_sha256="deadbeef")
    doc = AB.read_exclusions_artifact(path)
    assert doc["manual_exclusions_sha256"] == "deadbeef"


def test_validate_exclusions_artifact_refuses_manual_exclusions_drift():
    doc = {"corpus_sha256": "abc", "image_ids": {}, "complete": True,
          "manual_exclusions_sha256": "old"}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={},
                                             manual_exclusions_sha256="new")
    assert reason and "manual" in reason


def test_validate_exclusions_artifact_accepts_matching_manual_exclusions_sha():
    doc = {"corpus_sha256": "abc", "image_ids": {}, "complete": True,
          "manual_exclusions_sha256": "same"}
    assert AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={},
                                           manual_exclusions_sha256="same") is None


def test_validate_exclusions_artifact_accepts_both_none_when_no_manual_file_either_time():
    doc = {"corpus_sha256": "abc", "image_ids": {}, "complete": True,
          "manual_exclusions_sha256": None}
    assert AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={},
                                           manual_exclusions_sha256=None) is None


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
def _real_bash_popen_factory(home_dir=None):
    """Swaps the `docker exec -i <container> /bin/bash --login` argv `PersistentShell.start()`
    builds for a REAL local `/bin/bash --login` (2nd cold review N1: "spawn bash directly in
    tests with the docker argv swapped out"). `home_dir`, when given, becomes $HOME for the
    spawned shell -- used to control exactly what a login shell sources (N8)."""
    def _popen(cmd, **kwargs):
        env = dict(os.environ)
        if home_dir is not None:
            env["HOME"] = str(home_dir)
        return subprocess.Popen(["/bin/bash", "--login"], env=env, **kwargs)
    return _popen


def _real_shell(tmp_path, banner=None):
    """A PersistentShell over a REAL bash, with its own empty $HOME (optionally seeded with a
    `.bash_profile` banner line) so login-shell sourcing is controlled and reproducible."""
    home = tmp_path / f"home-{uuid.uuid4().hex}"
    home.mkdir()
    if banner:
        (home / ".bash_profile").write_text(f"echo '{banner}'\n")
    shell = AB.PersistentShell("unused-container", popen=_real_bash_popen_factory(home),
                               runner=lambda *a, **k: FakeRunner.Proc(0, "", ""))
    shell.start()
    return shell


# --------------------------------------------------------------------------- PersistentShell (real bash)
@_timeout(10)
def test_persistent_shell_real_bash_runs_a_command_and_returns_exit_code(tmp_path):
    shell = _real_shell(tmp_path)
    try:
        res = shell.run("pwd")
        assert res["exit_code"] == 0 and res["timed_out"] is False and res["shell_died"] is False
        assert res["output"].strip()
    finally:
        shell.close()


@_timeout(10)
def test_persistent_shell_real_bash_eats_login_banner_N8(tmp_path):
    shell = _real_shell(tmp_path, banner="BANNER_NOISE_XYZ")
    try:
        res = shell.run("echo hi")
        assert "BANNER_NOISE_XYZ" not in res["output"]
        assert res["output"] == "hi\n"
    finally:
        shell.close()


@_timeout(10)
def test_persistent_shell_real_bash_start_cd_persists_into_later_commands(tmp_path):
    """start=`cd /usr`, then `pwd` -> `/usr` (upstream-faithful: start and bash_action share ONE
    shell session)."""
    shell = _real_shell(tmp_path)
    try:
        shell.run("cd /usr")
        res = shell.run("pwd")
        assert res["output"] == "/usr\n" and res["exit_code"] == 0
    finally:
        shell.close()


@_timeout(10)
def test_persistent_shell_real_bash_start_var_persists_into_later_commands(tmp_path):
    shell = _real_shell(tmp_path)
    try:
        shell.run("var=10")
        res = shell.run("echo $var")
        assert res["output"] == "10\n" and res["exit_code"] == 0
    finally:
        shell.close()


@_timeout(10)
def test_persistent_shell_real_bash_printf_no_trailing_newline(tmp_path):
    """N2: the command's own output has NO trailing newline; the sentinel protocol's injected `\\n`
    (from `printf '\\n%s%d\\n' ...`) must be the ONLY newline consumed -- the real output text
    comes back exactly as `printf` wrote it, with no extra/missing characters."""
    shell = _real_shell(tmp_path)
    try:
        res = shell.run("printf abc")
        assert res["output"] == "abc" and res["exit_code"] == 0
    finally:
        shell.close()


@_timeout(10)
def test_persistent_shell_real_bash_cat_file_without_final_newline(tmp_path):
    f = tmp_path / "nofinalnewline.txt"
    f.write_bytes(b"line1")        # deliberately no trailing \n
    shell = _real_shell(tmp_path)
    try:
        res = shell.run(f"cat {f}")
        assert res["output"] == "line1" and res["exit_code"] == 0
    finally:
        shell.close()


@_timeout(10)
def test_persistent_shell_real_bash_false_reports_nonzero(tmp_path):
    shell = _real_shell(tmp_path)
    try:
        res = shell.run("false")
        assert res["exit_code"] == 1
    finally:
        shell.close()


@_timeout(10)
def test_persistent_shell_real_bash_exit_ends_the_shell_N9(tmp_path):
    """Upstream: `exit` ends the session. bash never reaches the sentinel printf (it terminates on
    the `exit` line itself), so THIS SAME run() call must report shell_died, not hang/time out."""
    shell = _real_shell(tmp_path)
    try:
        res = shell.run("exit 3")
        assert res["shell_died"] is True
    finally:
        shell.close()


@_timeout(10)
def test_persistent_shell_real_bash_run_after_shell_died_reports_immediately(tmp_path):
    shell = _real_shell(tmp_path)
    try:
        shell.run("exit 0")
        import time as _time
        t0 = _time.monotonic()
        res = shell.run("echo should not run", timeout_s=5)
        elapsed = _time.monotonic() - t0
        assert res["shell_died"] is True
        assert elapsed < 1.0, "shell_died must be reported immediately, not after the full timeout"
    finally:
        shell.close()


def test_persistent_shell_run_before_start_raises():
    shell = AB.PersistentShell("c1")
    with pytest.raises(RuntimeError):
        shell.run("pwd")


@_timeout(10)
def test_persistent_shell_close_terminates_a_live_process_N7(tmp_path):
    shell = _real_shell(tmp_path)
    assert shell.proc.poll() is None, "sanity: the real shell process is alive before close()"
    shell.close()
    assert shell.proc.poll() is not None, "close() must leave no live process behind"


@_timeout(10)
def test_persistent_shell_without_close_the_process_is_left_running_N7(tmp_path):
    """Demonstrates why `finally: shell.close()` is mandatory: the real process is a resource that
    outlives the Python object if nothing terminates it. (The real cleanup path is exercised,
    end-to-end through run_task, by test_run_task_cleans_up_container_AFTER_docker_run_on_init_failure
    and friends; this isolates PersistentChain's OWN contribution to that cleanup.)"""
    shell = _real_shell(tmp_path)
    try:
        assert shell.proc.poll() is None   # still alive -- close() was never called
    finally:
        shell.close()       # the test's own cleanup; NOT part of what is being demonstrated


# --------------------------------------------------------------------------- PersistentShell timeout
# (2nd cold review: "a fake Popen may remain only for timeout paths" -- a real bash process that
# never responds cannot be simulated without actually blocking, so this one path keeps a minimal
# fake that just never produces the sentinel line.)
class _HangingFakeProc:
    def __init__(self):
        self.stdin = self
        self.stdout = self
        self.killed = False

    def write(self, s):
        pass

    def flush(self):
        pass

    def read(self, n):
        time.sleep(2)   # "hangs" -- long enough to exceed any test's tiny timeout
        return b""

    def poll(self):
        return None if not self.killed else -9

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        if not self.killed:
            raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)


def test_persistent_shell_timeout_kills_process_and_reports_timed_out():
    proc_holder = {}

    def make_proc(*a, **k):
        p = _HangingFakeProc()
        proc_holder["proc"] = p
        return p
    runner_calls = []
    shell = AB.PersistentShell("c1", popen=make_proc,
                              runner=lambda cmd, **kw: runner_calls.append(cmd) or FakeRunner.Proc(0, "", ""))
    shell.proc = make_proc()    # bypass start()'s own no-op sentinel round (it would also hang)
    res = shell.run("sleep 999", timeout_s=0.02)
    assert res["timed_out"] is True
    assert proc_holder["proc"].killed is True
    # R7: the best-effort in-container kill is the SIMPLE, bounded form -- pkill -KILL -f, not a
    # process-group kill via pgrep substitution (unverified semantics on an arbitrary image).
    assert runner_calls == [["docker", "exec", "c1", "pkill", "-KILL", "-f", "bash --login"]]


def test_persistent_shell_exit_code_137_is_treated_as_timed_out():
    """N5 (moot as a live trigger now, kept as a safety net): a sentinel that DOES arrive, but with
    exit code 137 (SIGKILL), still marks timed_out=True."""
    class _Proc137:
        def __init__(self):
            self.stdin = self
            self.stdout = self
            self._pending = None   # None = nothing written yet; the reader must wait, not EOF

        def write(self, s):
            m = re.search(rb"printf '\\n%s%d\\n' (\S+) \$\?", s)
            self._pending = b"\n" + m.group(1) + b"137\n"

        def flush(self):
            pass

        def read(self, n):
            while self._pending is None:
                time.sleep(0.01)
            data, self._pending = self._pending, b""
            return data

        def poll(self):
            return None

    import threading as _threading
    shell = AB.PersistentShell("c1", popen=lambda *a, **k: _Proc137())
    shell.proc = _Proc137()
    _threading.Thread(target=shell._reader_loop, daemon=True).start()
    res = shell.run("kill -KILL $$", timeout_s=5)
    assert res["exit_code"] == 137 and res["timed_out"] is True


def test_persistent_shell_sentinel_tail_split_across_two_reads_parses_137_and_leaks_nothing():
    """3rd cold review R1/R4: a chunk boundary landing INSIDE the exit-code digits+newline
    (`...137` | `\\n...`) must not be misread as a shorter code, and nothing from that split must
    leak into the following run() call's output."""
    class _SplitProc:
        def __init__(self):
            self.stdin = self
            self.stdout = self
            self._sentinel = None
            self._stage = 0   # 0=not written, 1=first half sent, 2=second half sent

        def write(self, s):
            m = re.search(rb"printf '\\n%s%d\\n' (\S+) \$\?", s)
            self._sentinel = m.group(1)
            self._stage = 1

        def flush(self):
            pass

        def read(self, n):
            while self._stage == 0:       # the reader thread starts before write() is called
                time.sleep(0.01)
            if self._stage == 1:
                self._stage = 2
                return b"\n" + self._sentinel + b"13"      # digits split mid-number
            if self._stage == 2:
                self._stage = 3
                return b"7\n"                              # the rest, in a SEPARATE read()
            while True:
                time.sleep(0.05)   # next run() call hasn't written yet; just block harmlessly

        def poll(self):
            return None

    import threading as _threading
    proc = _SplitProc()
    shell = AB.PersistentShell("c1", popen=lambda *a, **k: proc)
    shell.proc = proc
    _threading.Thread(target=shell._reader_loop, daemon=True).start()
    res = shell.run("whatever", timeout_s=5)
    assert res["exit_code"] == 137 and res["output"] == ""
    assert shell._carry == b""   # nothing leaked past the sentinel+newline


@_timeout(15)
def test_persistent_shell_real_bash_1mb_output_fast_and_correct(tmp_path):
    """3rd cold review R1: the old O(n^2) `re.search` over the whole buffer measured 20KB->9.4s,
    50KB->116s, >=100KB effectively hangs. The incremental bytearray.find() scan must handle 1MB
    in well under 2s."""
    shell = _real_shell(tmp_path)
    try:
        t0 = time.monotonic()
        res = shell.run("head -c 1048576 /dev/zero | tr '\\0' x", timeout_s=10)
        elapsed = time.monotonic() - t0
        assert res["exit_code"] == 0 and res["timed_out"] is False
        assert len(res["output"]) == 1048576
        assert elapsed < 2.0, f"1MB took {elapsed:.2f}s -- should be well under 2s"
    finally:
        shell.close()


@_timeout(15)
def test_persistent_shell_real_bash_4mb_output_fast_and_correct(tmp_path):
    shell = _real_shell(tmp_path)
    try:
        t0 = time.monotonic()
        res = shell.run("head -c 4194304 /dev/zero | tr '\\0' x", timeout_s=10)
        elapsed = time.monotonic() - t0
        assert res["exit_code"] == 0 and res["timed_out"] is False
        assert len(res["output"]) == 4194304
        assert elapsed < 2.0, f"4MB took {elapsed:.2f}s -- should be well under 2s"
    finally:
        shell.close()


# --------------------------------------------------------------------------- dual-submit driver
def test_dualsubmit_driver_submitted_via_only_from_the_DISPATCHED_first_call_N10():
    """run_agent (single_tool_call_per_turn=True) only ever dispatches tool_calls[0]; a
    finish_action/answer_action riding in position 1+ never actually runs and must NOT be recorded
    as the submission."""
    inner = FakeDriver(script=[complete_result(tool_calls=[
        tool_call("bash_action", {"script": "ls"}, call_id="c0"),
        tool_call("answer_action", {"answer": "ignored"}, call_id="c1"),
    ])])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    assert d.submitted_via is None


def test_dualsubmit_driver_submitted_via_set_when_the_submit_IS_first_N10():
    inner = FakeDriver(script=[complete_result(tool_calls=[
        tool_call("finish_action", {"thought": "done"}, call_id="c0"),
        tool_call("bash_action", {"script": "ls"}, call_id="c1"),
    ])])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    assert d.submitted_via == "finish"


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
@_timeout(10)
def test_bash_tool_executes_via_persistent_shell_and_wraps_output(tmp_path):
    shell = _real_shell(tmp_path)
    try:
        counters = {}
        tools = AB.build_tools(shell, timeout=10, counters=counters)
        bash = {t.name: t for t in tools}["bash_action"]
        out = bash.fn({"script": "echo hello"})
        assert out == "The output of the OS:\n\nhello\n"
    finally:
        shell.close()


@_timeout(10)
def test_bash_tool_empty_output_uses_upstream_sentence(tmp_path):
    shell = _real_shell(tmp_path)
    try:
        tools = AB.build_tools(shell, timeout=10, counters={})
        bash = {t.name: t for t in tools}["bash_action"]
        assert bash.fn({"script": "true"}) == "The output of the OS is empty."
    finally:
        shell.close()


@_timeout(10)
def test_bash_tool_truncates_at_800_keeping_780(tmp_path):
    shell = _real_shell(tmp_path)
    try:
        tools = AB.build_tools(shell, timeout=10, counters={})
        bash = {t.name: t for t in tools}["bash_action"]
        out = bash.fn({"script": "printf 'x%.0s' {1..2000}"})
        assert out.endswith("[truncated because the output is too long]")
        body = out[len("The output of the OS:\n\n"):]
        assert body == "x" * 780 + "\n[truncated because the output is too long]"
    finally:
        shell.close()


def test_bash_tool_timeout_kills_shell_sets_flag_and_aborts_episode():
    def make_proc(*a, **k):
        return _HangingFakeProc()
    shell = AB.PersistentShell("c1", popen=make_proc)
    shell.proc = make_proc()   # bypass the no-op start() round, which would also hang
    counters, flag = {}, {}
    tools = AB.build_tools(shell, timeout=0.02, counters=counters, exec_timeout_flag=flag)
    bash = {t.name: t for t in tools}["bash_action"]
    with pytest.raises(agent_loop.AbortEpisode) as ei:
        bash.fn({"script": "sleep 999"})
    assert ei.value.outcome == AO.FAILED_TESTS
    assert counters["tool_timeouts"] == 1
    assert flag["hit"] is True


@_timeout(10)
def test_bash_tool_shell_died_sets_flag_and_aborts_as_scored_fail_R2(tmp_path):
    """R2: a shell death triggered by the MODEL's own bash_action is a SCORED FAIL
    (outcome=failed_tests), not an infra failure -- only a death during start() is setup_error."""
    shell = _real_shell(tmp_path)
    try:
        counters, exec_flag, died_flag = {}, {}, {}
        tools = AB.build_tools(shell, timeout=10, counters=counters, exec_timeout_flag=exec_flag,
                               shell_died_flag=died_flag)
        bash = {t.name: t for t in tools}["bash_action"]
        with pytest.raises(agent_loop.AbortEpisode) as ei:
            bash.fn({"script": "exit 1"})
        assert ei.value.outcome == AO.FAILED_TESTS
        assert died_flag["hit"] is True
    finally:
        shell.close()


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
    """A REAL local bash backs every run_task test's PersistentShell (2nd cold review: "a fake
    Popen may remain only for timeout paths") -- run_task's own docker lifecycle (create/init/rm)
    stays on the FakeRunner; only the persistent-shell PROCESS is real."""
    return _real_bash_popen_factory()


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


@_timeout(10)
def test_run_task_calls_shell_close_and_the_real_process_has_exited_R6(monkeypatch, tmp_path):
    """R6(1): spy on PersistentShell.close (must be called exactly once) AND, with a REAL bash
    process, confirm it has actually exited by the time run_task returns -- a close() that's
    called but doesn't really terminate the process would pass a pure spy check."""
    calls = []
    orig_close = AB.PersistentShell.close

    def spy_close(self):
        calls.append(self)
        return orig_close(self)
    monkeypatch.setattr(AB.PersistentShell, "close", spy_close)

    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert len(calls) == 1
    assert calls[0].proc.poll() is not None, "the real shell process must have exited"


def test_run_task_cleans_up_container_on_keyboard_interrupt_and_reraises():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))

    class _BoomDriver:
        def complete(self, *a, **k):
            raise KeyboardInterrupt()

    task = _match_cfg_task()
    with pytest.raises(KeyboardInterrupt):
        AB.run_task("m", task, SCRIPTS_ROOT, _BoomDriver(), {}, runner=runner, popen=_shell_popen_ok())
    # F11 leftover: not just "an rm happened somewhere" (the pre-clean rm exists even with the
    # `finally` deleted) -- an rm AFTER the `docker run` that actually created this container.
    run_idx = next(i for i, c in enumerate(runner.calls) if c["cmd"][:2] == ["docker", "run"])
    rm_after = [c for c in runner.calls[run_idx + 1:] if c["cmd"][:2] == ["docker", "rm"]]
    assert rm_after, "no `docker rm` after `docker run` -- cleanup did not run post-creation"


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
    # F11 leftover: an rm AFTER the `docker run` that created this container, not just any rm.
    run_idx = next(i for i, c in enumerate(runner.calls) if c["cmd"][:2] == ["docker", "run"])
    rm_after = [c for c in runner.calls[run_idx + 1:] if c["cmd"][:2] == ["docker", "rm"]]
    assert rm_after, "no `docker rm` after `docker run` -- cleanup did not run post-creation"


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


def test_run_task_captures_gold_live_from_the_check_chain_R5():
    """R5: the check chain already executes the gold-slot script live at grading time; capture
    its stdout as `gold_live` rather than trusting the D2-prepare-time `gold_prepare` is still
    valid."""
    runner = _exec_sequenced_runner([(0, "3\n", ""), (0, "", "")])   # null slot, then the checker
    task = {"id": "std-001-0", "group": 1, "labels": [],
           "evaluation": {"check": [None, {"code": "x"}], "example": {"code": "echo gold"}},
           "description": "d"}
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "3"})])])
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok(),
                      gold_prepare="3\n")
    assert row["gold_live"] == "3\n"
    assert row["gold_prepare"] == "3\n"


def test_run_task_gold_drift_when_prepare_and_live_golds_disagree_R5():
    runner = _exec_sequenced_runner([(0, "4\n", ""), (0, "", "")])   # environment now answers differently
    task = {"id": "std-001-0", "group": 1, "labels": [],
           "evaluation": {"check": [None, {"code": "x"}], "example": {"code": "echo gold"}},
           "description": "d"}
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "4"})])])
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok(),
                      gold_prepare="3\n")
    assert row["gold_prepare"] == "3\n" and row["gold_live"] == "4\n"
    assert row["gold_prepare"] != row["gold_live"]


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
    """Real bash: `sleep 999` genuinely never reaches the sentinel printf within our tiny
    Python-side exec_timeout, so the timeout fires on OUR schedule, not the sleep's."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("bash_action", {"script": "sleep 999"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, exec_timeout=0.05,
                      popen=_shell_popen_ok())
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


@_timeout(10)
def test_run_task_model_caused_shell_death_is_a_scored_fail_R2(tmp_path):
    """R2: a model-caused shell death (bash_action runs `exit`) is a SCORED FAIL --
    outcome=failed_tests, shell_died=true, setup_error=FALSE, IN the acc denominator -- using a
    REAL bash process so the shell genuinely exits rather than us pretending it did. Only a death
    during the `start` script (before any model action) is setup_error; see the sibling test
    `test_run_task_start_script_shell_death_is_also_setup_error`."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("bash_action", {"script": "exit 0"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["shell_died"] is True
    assert row["setup_error"] is False
    assert row["outcome"] == AO.FAILED_TESTS and row["passed"] is False


@_timeout(10)
def test_run_task_start_script_shell_death_is_also_setup_error(tmp_path):
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    task = {"id": "t1", "group": 1, "labels": [], "create": {"local": "default"}, "start": "exit 0",
           "evaluation": {"match": "x"}, "description": "d"}
    row = AB.run_task("m", task, SCRIPTS_ROOT, FakeDriver(), {}, runner=runner, popen=_shell_popen_ok())
    assert row["shell_died"] is True and row["setup_error"] is True


def test_run_task_populates_gold_prepare_from_the_artifact_AC5():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok(),
                      gold_prepare="3\n")
    assert row["gold_prepare"] == "3\n"
    assert row["gold_live"] is None   # a match task never runs the check chain


def test_run_task_gold_prepare_defaults_to_none_when_not_provided():
    runner = FakeRunner(default=FakeRunner.Proc(1, "", "boom"))
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, FakeDriver(), {}, runner=runner, popen=_shell_popen_ok())
    assert row["gold_prepare"] is None and row["gold_live"] is None
