"""M54: bench.agentbench_adapter -- corpus/eval semantics, container lifecycle (docker fully
mocked via FakeRunner / a fake Popen), dual-submit shim, and per-task run outcomes. No docker, no
network, no model calls."""
import errno
import functools
import json
import os
import queue
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


def _marked(rc: int, stdout: str = "") -> str:
    """11th cold review round 11 P7-residual: FakeRunner fixtures simulate a REAL docker_exec
    invocation, which now wraps every checker/init/example script with a trailing rc marker (see
    bench.agentbench_adapter._RC_MARKER / docker_exec) -- a test that wants to simulate "the
    script genuinely ran to completion with rc=<rc>" must embed that marker in the configured
    Proc's stdout, exactly as the real wrapped bash -c invocation would produce it."""
    return f"{stdout}\n{AB._RC_MARKER}{rc}\n"


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
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [None, ("python", "check")], ("bash", "example"), "7", runner)
    assert infra_error is None
    assert ok is True
    assert gold_live == "7\n"   # R5: the null-slot stdout, captured live
    assert len(runner.calls) == 2
    second_cmd = runner.calls[1]["cmd"]
    assert second_cmd[-2:] == ["7", "7\n"]


def test_run_check_chain_nonzero_exit_fails():
    """8th cold review round 8 P47 (11th round P7-residual: the checker's rc marker is now
    authoritative on its own -- no `docker inspect` probe is even needed once the marker is
    observed): a nonzero exit that genuinely completed (the trailing rc marker was observed) is
    the checker's own verdict, so this stays failed_tests."""
    runner = FakeRunner(results=[FakeRunner.Proc(0, _marked(1, ""), "boom")])
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is False and gold_live is None and infra_error is None


def test_run_check_chain_timeout_with_unhealthy_docker_is_infra_error():
    """6th cold review round 6, addendum C refinement of P9(a), re-grounded on P47's
    `docker inspect` probe: a check-script TIMEOUT is infra ONLY when the daemon-level health
    probe run immediately afterward ALSO fails/times out -- proving docker itself, not just the
    checker script, is unresponsive."""
    runner = FakeRunner(results=[subprocess.TimeoutExpired(cmd="x", timeout=1),
                                 subprocess.TimeoutExpired(cmd="docker inspect", timeout=3)])
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner, timeout=1)
    assert ok is False and gold_live is None and infra_error is not None
    assert infra_error["timed_out"] is True


def test_run_check_chain_timeout_with_start_marker_observed_is_failed_tests_addendum_C():
    """Addendum C (12th round addendum P6: resolved via the START marker now, never `docker
    inspect`): std-005-0/1/2 run the MODEL's OWN installed binaries, which can hang -- that is a
    real `failed_tests` (IN the denominator), not an infra failure, when the START marker was
    observed in the partial output before the timeout (DIRECT evidence the checker genuinely
    began running)."""
    timeout_with_start = subprocess.TimeoutExpired(
        cmd="x", timeout=1, output=f"\n{AB._START_MARKER}\n".encode())
    runner = FakeRunner(results=[timeout_with_start])   # no docker inspect call needed/made
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner, timeout=1)
    assert ok is False and gold_live is None and infra_error is None
    assert exec_started is True


def test_run_check_chain_null_with_no_example_fails_without_raising():
    runner = FakeRunner()
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [None], None, "ans", runner)
    assert ok is False and gold_live is None and infra_error is None
    assert runner.calls == []


def test_run_check_chain_none_answer_becomes_the_literal_string_None_cold_review_F14():
    """Upstream `params = [str(answer)]`, unconditionally. A finish_action with no `thought`
    submits Python None; str(None) == "None" is what the check script actually receives -- not
    an empty string. This is a MUTATION-SENSITIVE assertion on the literal argv value."""
    runner = FakeRunner()
    AB.run_check_chain("c1", [("bash", "x")], None, None, runner)
    assert runner.last_cmd[-1] == "None"


# --------------------------------------------------------------------------- P47 daemon-level health-probe matrix
# 8th cold review round 8 P47 (HIGH), superseding P37's `docker exec <c> true` design entirely:
# that probe ran INSIDE the container, so a model that deleted /bin/true (or bash itself, e.g.
# `rm -rf /bin`) made a container that was still genuinely Running look infra-dead; and the P37
# stderr-prefix shortcut meant a model that merely PRINTED docker-CLI-looking text into its own
# stderr (e.g. "OCI runtime ...") could short-circuit straight to a free setup_error instead of a
# scored failure. The fix is DAEMON-level: `docker inspect <c> --format '{{.State.Running}}'`,
# answered by the daemon directly, independent of anything inside the container. The stderr-prefix
# shortcut is REMOVED -- docker-CLI-looking stderr text is still RECORDED in infra_evidence for
# diagnostics, but never again used to decide the classification on its own.
def test_run_check_chain_P47_case_a_healthy_app_prints_docker_like_text_is_still_failed_tests():
    """(a) Daemon reachable, container Running -- even though the checker's OWN stderr happens to
    read like a docker-CLI error ("OCI runtime ...") -- must NOT short-circuit to infra; it is the
    model's/checker's own failure."""
    runner = FakeRunner(results=[FakeRunner.Proc(0, _marked(1, ""),
                                                 "OCI runtime exec failed: my own app broke")])
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is False and infra_error is None


def test_run_check_chain_P47_case_b_model_deleted_bin_true_inspect_still_confirms_running():
    """(b) The model ran `rm` on `/bin/true` (or similar) inside the container, but bash ITSELF
    (what we invoke -- see docker_exec's wrapping) is still intact, so our exec still reaches the
    trailing rc marker -- the SCRIPT's own attempt to use the now-missing /bin/true just produces
    bash's own "127: command not found" as ITS exit code. The marker's presence alone proves this
    is the model's own doing, no `docker inspect` probe even needed."""
    runner = FakeRunner(results=[FakeRunner.Proc(0, _marked(127, ""),
                                                 "bash: true: No such file or directory")])
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is False and infra_error is None


def test_run_check_chain_P47_case_c_container_exited_is_infra():
    """(c) `docker inspect` answers successfully but reports the container is NOT Running
    (exited) -> setup_error/infra_evidence."""
    runner = FakeRunner(results=[FakeRunner.Proc(1, "", "some checker error"),
                                 FakeRunner.Proc(0, "false\n", "")])   # inspect: exited
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is False and infra_error is not None
    assert infra_error["health_probe_ok"] is False
    assert infra_error["inspect"]["running"] is False


def test_run_check_chain_P47_case_d_daemon_down_is_infra():
    """(d) `docker inspect` itself cannot even complete (daemon unreachable) -> setup_error/
    infra_evidence -- the docker-CLI stderr is recorded as evidence, never used to decide on its
    own (the shortcut is gone; this case reaches the same verdict via the ACTUAL probe failing)."""
    runner = FakeRunner(results=[FakeRunner.Proc(1, "", "some checker error"),
                                 FakeRunner.Proc(125, "", "Cannot connect to the Docker daemon at...")])
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is False and infra_error is not None
    assert infra_error["health_probe_ok"] is False
    assert infra_error["inspect"]["ok"] is False
    assert "Cannot connect to the Docker daemon" in infra_error["message"]


def test_run_check_chain_P47_daemon_itself_times_out_is_infra():
    runner = FakeRunner(results=[FakeRunner.Proc(1, "", "some checker error"),
                                 subprocess.TimeoutExpired(cmd="docker inspect", timeout=3)])
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is False and infra_error is not None
    assert infra_error["inspect"]["timed_out"] is True
    assert exec_started is None   # daemon unreachable -- truly unknown, not a guessed False


# --------------------------------------------------------------------------- P7 (residual, 11th round): authoritative execution evidence via rc marker
# 11th cold review round 11 P7 (supersedes 10th round P7's bare rc-125 rule): rc 125 from `docker
# exec` and rc 125 from the SCRIPT ITSELF (its own `exit 125`) share the same channel -- the bare
# rc can never tell them apart. `docker_exec` now wraps every invocation with a trailing rc
# marker (see `_RC_MARKER`); `_classify_check_result` reads `res["marker_observed"]` as the
# PRIMARY signal instead.
def test_classify_check_result_marker_observed_rc_125_is_not_infra_P7():
    """The marker's PRESENCE is authoritative on its own, no probe needed -- even rc 125 (the
    docker CLI's own code) is then just the SCRIPT's own exit code, since the script genuinely
    ran to completion (proven by reaching the trailing printf)."""
    res = {"exit_code": 125, "marker_observed": True, "timed_out": False,
          "stderr": "some checker-internal message, exit 125"}

    def fail_if_probed(cmd, **kw):
        raise AssertionError("the daemon-level probe must not run -- the marker alone is "
                            "already unambiguous evidence")
    infra_evidence, exec_started = AB._classify_check_result("c1", res, fail_if_probed)
    assert infra_evidence is None
    assert exec_started is True


def test_classify_check_result_marker_absent_despite_running_is_now_infra_P7():
    """11th round's STRENGTHENED rule (vs the 10th round's P47 inspect-based fallback): a
    COMPLETED nonzero exit with NO marker observed is STILL ambiguous even when `docker inspect`
    confirms the container is Running -- we have no proof the real command ever ran at all."""
    res = {"exit_code": 1, "marker_observed": False, "timed_out": False, "stderr": "boom"}
    runner = FakeRunner(default=FakeRunner.Proc(0, "true\n", ""))   # inspect: Running
    infra_evidence, exec_started = AB._classify_check_result("c1", res, runner)
    assert infra_evidence is not None and exec_started is False
    assert infra_evidence["exec_started"] is False


def test_classify_check_result_marker_absent_and_not_running_is_infra_P7():
    res = {"exit_code": 1, "marker_observed": False, "timed_out": False, "stderr": ""}
    runner = FakeRunner(default=FakeRunner.Proc(0, "false\n", ""))   # inspect: exited
    infra_evidence, exec_started = AB._classify_check_result("c1", res, runner)
    assert infra_evidence is not None and exec_started is False


def test_classify_check_result_marker_absent_daemon_down_is_infra_P7():
    res = {"exit_code": None, "marker_observed": False, "timed_out": False, "stderr": ""}
    runner = FakeRunner(default=FakeRunner.Proc(125, "", "Cannot connect to the Docker daemon"))
    infra_evidence, exec_started = AB._classify_check_result("c1", res, runner)
    assert infra_evidence is not None and exec_started is None   # daemon unreachable -- unknown


def test_classify_check_result_timeout_start_observed_is_addendum_C_P6():
    """12th round addendum P6 (supersedes addendum C's docker-inspect-based timeout resolution):
    a check-script TIMEOUT (the RC marker is NEVER observed for a timeout -- the process was
    killed before reaching it) with the START marker observed is DIRECT evidence the model's own
    hang, not infra -- no probe needed, `docker inspect` must not even be called."""
    res = {"exit_code": None, "marker_observed": False, "start_observed": True,
          "timed_out": True, "stderr": ""}

    def fail_if_probed(cmd, **kw):
        raise AssertionError("docker inspect must not be called -- the START marker is already "
                            "direct, unambiguous evidence")
    infra_evidence, exec_started = AB._classify_check_result("c1", res, fail_if_probed)
    assert infra_evidence is None
    assert exec_started is True


def test_classify_check_result_timeout_start_absent_is_infra_even_if_running_P6():
    """12th round addendum P6: a TIMEOUT with NO start marker observed is setup_error -- NEVER
    asserted as "it ran" on the weaker basis of `docker inspect` showing the container Running
    (which only proves the CONTAINER is alive, not that THIS exec ever reached the real command).
    `docker inspect` is not even consulted for a timeout any more."""
    res = {"exit_code": None, "marker_observed": False, "start_observed": False,
          "timed_out": True, "stderr": "some stderr"}

    def fail_if_probed(cmd, **kw):
        raise AssertionError("docker inspect must not be called for a timeout")
    infra_evidence, exec_started = AB._classify_check_result("c1", res, fail_if_probed)
    assert infra_evidence is not None and exec_started is False
    assert infra_evidence["exec_started"] is False


def test_run_check_chain_records_exec_started_true_on_a_full_pass_P7():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is True and exec_started is True


def test_run_check_chain_records_exec_started_false_on_exec_creation_failure_P7():
    """No marker in the (empty) stdout -> falls to the daemon-level probe, which here ALSO fails
    (no more queued results, default Proc() has empty "" stdout -> not Running) -> infra."""
    runner = FakeRunner(results=[FakeRunner.Proc(125, "", "Cannot connect to the Docker daemon")])
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is False and exec_started is False
    assert infra_error["exec_started"] is False


@_timeout(10)
def test_docker_exec_real_bash_checker_exit_125_is_authoritative_via_marker_P7():
    """11th cold review round 11 P7: a REAL local bash checker doing `exit 125` proves the marker
    mechanism end-to-end -- rc 125 from the SCRIPT itself (not docker exec) is observed via the
    marker and is authoritative, never misread as an exec-creation failure. `runner` substitutes a
    REAL local bash for "docker exec <container>", keeping the EXACT wrapped script/argv
    docker_exec built, so the generated script text and marker-parsing round-trip through genuine
    bash (no actual Docker container needed to prove the mechanism)."""
    def runner(cmd, **kw):
        assert cmd[:3] == ["docker", "exec", "c1"]
        real_cmd = ["bash"] + cmd[4:]   # drop "docker exec c1", keep "bash -c <script> [-- ...]"
        return subprocess.run(real_cmd, capture_output=True, timeout=kw.get("timeout", 5))
    res = AB.docker_exec("c1", ("bash", "exit 125"), 5.0, runner)
    assert res["marker_observed"] is True
    assert res["exit_code"] == 125
    infra_evidence, exec_started = AB._classify_check_result("c1", res, runner)
    assert infra_evidence is None   # authoritative: the model's/checker's own exit 125, not infra
    assert exec_started is True


@_timeout(10)
def test_docker_exec_real_bash_checker_normal_output_is_preserved_P7():
    """The marker is correctly stripped and the script's OWN stdout is preserved byte-for-byte --
    proves _extract_rc_marker's splitting is exact against genuine bash output, not just a
    FakeRunner-simulated one."""
    def runner(cmd, **kw):
        assert cmd[:3] == ["docker", "exec", "c1"]
        real_cmd = ["bash"] + cmd[4:]
        return subprocess.run(real_cmd, capture_output=True, timeout=kw.get("timeout", 5))
    res = AB.docker_exec("c1", ("bash", "echo hello"), 5.0, runner)
    assert res["marker_observed"] is True
    assert res["exit_code"] == 0
    assert res["stdout"] == "hello\n"
    assert AB._RC_MARKER not in res["stdout"]
    assert res["start_observed"] is True            # 12th round P6
    assert AB._START_MARKER not in res["stdout"]


# --------------------------------------------------------------------------- P6 (12th round addendum): START marker on timeout
@_timeout(10)
def test_docker_exec_real_bash_timeout_with_start_marker_sets_start_observed_P6():
    """12th cold review round 12 addendum P6: a checker that genuinely begins running (prints the
    START marker) and then hangs must have `start_observed=True` on timeout -- DIRECT evidence,
    captured from subprocess.TimeoutExpired's own partial stdout."""
    def runner(cmd, **kw):
        assert cmd[:3] == ["docker", "exec", "c1"]
        real_cmd = ["bash"] + cmd[4:]
        return subprocess.run(real_cmd, capture_output=True, timeout=kw.get("timeout", 5))
    res = AB.docker_exec("c1", ("bash", "sleep 999"), 0.3, runner)
    assert res["timed_out"] is True
    assert res["start_observed"] is True


def test_docker_exec_timeout_without_any_output_has_start_observed_false_P6():
    """A timeout where NOTHING was ever captured (the exec never even reached the point of
    printing the START marker) must report start_observed=False, never crash on a None partial
    stdout."""
    runner = FakeRunner(results=[subprocess.TimeoutExpired(cmd="x", timeout=1)])   # no `output=`
    res = AB.docker_exec("c1", ("bash", "x"), 1.0, runner)
    assert res["timed_out"] is True
    assert res["start_observed"] is False


def test_docker_exec_timeout_with_start_marker_in_partial_output_sets_start_observed_true_P6():
    timeout_with_start = subprocess.TimeoutExpired(
        cmd="x", timeout=1, output=f"some partial output\n{AB._START_MARKER}\n".encode())
    runner = FakeRunner(results=[timeout_with_start])
    res = AB.docker_exec("c1", ("bash", "x"), 1.0, runner)
    assert res["timed_out"] is True
    assert res["start_observed"] is True


# --------------------------------------------------------------------------- P7 (12th round addendum): oversized/unlaunchable argv
def test_docker_exec_oversized_param_raises_UnrepresentableArgvError_without_attempting_exec_P7():
    """12th cold review round 12 addendum P7: an answer/param over 32 KiB is rejected
    PROACTIVELY, before even attempting the exec -- the runner must never be called."""
    def fail_if_called(cmd, **kw):
        raise AssertionError("must not attempt the exec for an oversized param")
    oversized = "x" * (32 * 1024 + 1)
    with pytest.raises(AB.UnrepresentableArgvError, match="oversized answer"):
        AB.docker_exec("c1", ("bash", "x"), 5.0, fail_if_called, extra_params=[oversized])


def test_docker_exec_param_at_exactly_the_cap_is_allowed_P7():
    """Boundary: exactly 32 KiB must NOT be rejected -- only strictly OVER the cap is."""
    runner = FakeRunner(default=FakeRunner.Proc(0, _marked(0, ""), ""))
    at_cap = "x" * (32 * 1024)
    res = AB.docker_exec("c1", ("bash", "x"), 5.0, runner, extra_params=[at_cap])
    assert res["marker_observed"] is True


def test_docker_exec_e2big_oserror_from_the_runner_is_UnrepresentableArgvError_P7():
    """A safety net for whatever the proactive per-param cap didn't catch -- the OS itself
    rejecting the launch with E2BIG (argument list too long) is the SAME scored failure."""
    def runner(cmd, **kw):
        raise OSError(errno.E2BIG, "Argument list too long")
    with pytest.raises(AB.UnrepresentableArgvError):
        AB.docker_exec("c1", ("bash", "x"), 5.0, runner)


def test_docker_exec_einval_oserror_from_the_runner_is_UnrepresentableArgvError_P7():
    def runner(cmd, **kw):
        raise OSError(errno.EINVAL, "Invalid argument")
    with pytest.raises(AB.UnrepresentableArgvError):
        AB.docker_exec("c1", ("bash", "x"), 5.0, runner)


def test_docker_exec_enoent_oserror_is_NOT_caught_stays_a_genuine_infra_failure_P7():
    """ENOENT (the docker binary itself missing) is a genuine launch/infra failure -- it must
    propagate UNCAUGHT, never mistaken for the model's doing."""
    def runner(cmd, **kw):
        raise FileNotFoundError(errno.ENOENT, "No such file or directory", "docker")
    with pytest.raises(FileNotFoundError):
        AB.docker_exec("c1", ("bash", "x"), 5.0, runner)


def test_docker_exec_eacces_oserror_is_NOT_caught_stays_a_genuine_infra_failure_P7():
    """EACCES (permission denied) is a genuine launch/infra failure -- it must propagate
    UNCAUGHT, never mistaken for the model's doing."""
    def runner(cmd, **kw):
        raise PermissionError(errno.EACCES, "Permission denied")
    with pytest.raises(PermissionError):
        AB.docker_exec("c1", ("bash", "x"), 5.0, runner)


def test_run_task_oversized_answer_is_scored_failed_tests_not_setup_error_P7():
    """End-to-end: a model answer over the 32 KiB cap must be a SCORED failed_tests row with
    "oversized answer (N bytes)" in the error, never setup_error."""
    def runner(cmd, **kw):
        return FakeRunner.Proc(0, "", "")
    oversized_answer = "y" * (32 * 1024 + 500)
    driver = FakeDriver(script=[
        complete_result(tool_calls=[tool_call("answer_action", {"answer": oversized_answer})]),
    ])
    task = _check_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["outcome"] == AO.FAILED_TESTS
    assert row["passed"] is False
    assert row["setup_error"] is False
    assert "oversized answer" in row["error"]


def _all_vendored_bash_scripts():
    """Every (task_id, field, code) for a bash-language init/start/check/example script actually
    vendored in the corpus -- feeds both the bash -n sweep and documents which field each came
    from on a failure."""
    tasks = AB.load_corpus(CORPUS)
    out = []
    for task in tasks:
        cfg = AB.task_config(task, SCRIPTS_ROOT)
        for i, s in enumerate(cfg["init_scripts"]):
            if s is not None and s[0] == "bash":
                out.append((task["id"], f"init_scripts[{i}]", s[1]))
        if cfg["start"] is not None and cfg["start"][0] == "bash":
            out.append((task["id"], "start", cfg["start"][1]))
        for i, s in enumerate(cfg["check"] or []):
            if s is not None and s[0] == "bash":
                out.append((task["id"], f"check[{i}]", s[1]))
        if cfg["example"] is not None and cfg["example"][0] == "bash":
            out.append((task["id"], "example", cfg["example"][1]))
    return out


def test_every_vendored_bash_script_wraps_to_syntactically_valid_bash_P12():
    """12th cold review round 12 (HIGH regression in 0c4d469, external cold-review finding): the `( ... )`
    subshell wrapping must stay syntactically valid bash for EVERY vendored init/start/check/
    example script in the corpus, not just the ones exercised by other unit tests -- a
    comment-only (or otherwise all-whitespace) script previously made the subshell body EMPTY,
    which bash rejects as a syntax error. `bash -n` (parse/syntax-check only, never executes)
    against the EXACT wrapping docker_exec applies (`_wrap_bash_script`, not a re-implementation
    that could drift) catches this class of regression across the WHOLE corpus at once."""
    scripts = _all_vendored_bash_scripts()
    assert len(scripts) > 50   # sanity: the sweep is actually seeing the real corpus, not a stub
    failures = []
    for task_id, field, code in scripts:
        wrapped = AB._wrap_bash_script(code)
        proc = subprocess.run(["bash", "-n", "-c", wrapped], capture_output=True, text=True, timeout=5)
        if proc.returncode != 0:
            failures.append(f"{task_id} ({field}): rc={proc.returncode} stderr={proc.stderr!r}")
    assert not failures, "bash -n rejected the wrapped form of:\n" + "\n".join(failures)


@_timeout(10)
def test_docker_exec_comment_only_script_runs_with_rc_0_and_marker_present_P12():
    """12th round, end-to-end reproduction of the Opus-found regression: a comment-only init
    script (the EXACT shape of the 7 affected upstream tasks, e.g. std-007-18's
    "#!/bin/bash\\n# No initial setup required...") must run with rc 0 and the marker observed --
    before the `:` fix this was a bash syntax error (rc 2, no marker) via a REAL local bash."""
    def runner(cmd, **kw):
        assert cmd[:3] == ["docker", "exec", "c1"]
        real_cmd = ["bash"] + cmd[4:]
        return subprocess.run(real_cmd, capture_output=True, timeout=kw.get("timeout", 5))
    code = "\n#!/bin/bash\n# No initial setup required for this problem, as it uses default system tools."
    res = AB.docker_exec("c1", ("bash", code), 5.0, runner)
    assert res["marker_observed"] is True
    assert res["exit_code"] == 0
    assert res["timed_out"] is False


# --------------------------------------------------------------------------- P8(b) binary/undecodable output
def test_docker_exec_decodes_invalid_utf8_bytes_with_replace_never_raises_P8b():
    """A checker emitting raw 0xff on stderr must never raise UnicodeDecodeError -- it decodes
    with errors="replace" and the row stays a SCORED failed_tests, not a setup_error."""
    class _BytesProc:
        def __init__(self, returncode, stdout, stderr):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def runner(cmd, **kw):
        return _BytesProc(1, b"", b"\xff binary garbage on stderr")
    res = AB.docker_exec("c1", ("bash", "x"), 5.0, runner)
    assert res["exit_code"] == 1
    assert "�" in res["stderr"]   # the replacement character, not a raised exception


def test_run_task_checker_stderr_with_invalid_utf8_is_failed_tests_not_setup_error_P8b():
    """9th cold review round 9 P8(b), end-to-end: a checker emitting \\xff on stderr with a
    nonzero exit, while the container is confirmed healthy/Running, must be a SCORED
    failed_tests -- the decode itself must never be what crashes or misclassifies the row."""
    class _BytesProc:
        def __init__(self, returncode, stdout, stderr):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def runner(cmd, **kw):
        if cmd[:2] == ["docker", "run"]:
            return FakeRunner.Proc(0, "", "")
        if cmd[:2] == ["docker", "inspect"]:
            return FakeRunner.Proc(0, "true\n", "")
        if cmd[:2] == ["docker", "exec"] and not any(isinstance(c, str) and "echo gold" in c for c in cmd):
            marker = f"\n{AB._RC_MARKER}1\n".encode()
            return _BytesProc(0, marker, b"assertion failed \xff binary")
        return FakeRunner.Proc(0, "", "")
    task = {"id": "t1", "group": 1, "labels": [],
           "evaluation": {"check": [{"code": "x"}], "example": {"code": "echo gold"}},
           "description": "d"}
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "x"})])])
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["setup_error"] is False
    assert row["passed"] is False
    assert row["harness_error"] is False


def test_run_check_chain_legitimate_checker_failure_has_no_infra_error():
    """A checker script failing on its OWN merits (not a docker/transport problem) must NOT be
    mistaken for an infra error -- P9(a) distinguishes the MECHANISM, not just "nonzero"."""
    runner = FakeRunner(results=[FakeRunner.Proc(0, _marked(1, ""), "assertion failed: file missing")])
    ok, gold_live, infra_error, exec_started = AB.run_check_chain("c1", [("bash", "x")], None, "ans", runner)
    assert ok is False and infra_error is None


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
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(0, "", "")   # P26: verification requires an EMPTY stdout
        if len(cmd) >= 2 and cmd[1] == "exec" and any(isinstance(c, str) and "echo gold" in c for c in cmd):
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
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(0, "", "")   # P26: verification requires an EMPTY stdout
        if len(cmd) >= 2 and cmd[1] == "exec" and any(isinstance(c, str) and "echo gold" in c for c in cmd):
            seen.append(cmd[-1])
        return FakeRunner.Proc(0, "x\n", "")
    AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert len(seen) == 2
    assert seen[0] != seen[1]


def test_answer_placeholder_constants_are_distinct():
    assert AB.ANSWER_PLACEHOLDER_PRIMARY != AB.ANSWER_PLACEHOLDER_PROBE


def test_prepare_exclusions_disagreeing_golds_excluded_as_gold_mismatch():
    """D2 rule v2: this is now EXPECTED (not necessarily an error) for a randomized-init task --
    two runs INSIDE the same container legitimately producing different example stdout."""
    runner = _exec_sequenced_runner([(0, "3\n", ""), (0, "4\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t1", "reason": "gold_mismatch", "failed_step": None,
                           "exit_codes": [0, 0], "stdout": ["3\n", "4\n"], "stderr": ["", ""],
                           "timed_out": False}]


def test_prepare_exclusions_no_gold_when_example_fails():
    runner = _exec_sequenced_runner([(1, "", "boom"), (0, "3\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t1", "reason": "no_gold", "failed_step": "example",
                           "exit_codes": [1, 0], "stdout": ["", "3\n"], "stderr": ["boom", ""],
                           "timed_out": False}]


def test_prepare_exclusions_no_gold_when_stdout_empty():
    """cold-review F7: an empty stdout at a gold slot is `no_gold`, not a cached empty string."""
    runner = _exec_sequenced_runner([(0, "", ""), (0, "3\n", "")])
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert exclusions == [{"id": "t1", "reason": "no_gold", "failed_step": "example",
                           "exit_codes": [0, 0], "stdout": ["", "3\n"], "stderr": ["", ""],
                           "timed_out": False}]


def test_prepare_exclusions_gold_slot_uses_exactly_one_container_D2_v2():
    """D2 rule v2 (operator 2026-09-30): the old two-SEPARATE-fresh-containers probe caused 11/13
    real exclusions to be false positives on randomized-init ($RANDOM/shuf) tasks, because two
    DIFFERENT containers legitimately produce different random state. The fix: ONE fresh container
    (one `docker run`), `example` run TWICE inside it. Count `docker run` calls, not just exec."""
    runner_calls = []

    def runner(cmd, **kw):
        runner_calls.append(list(cmd))
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(0, "", "")   # P26: verification requires an EMPTY stdout
        return FakeRunner.Proc(0, "same\n", "")
    AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    run_calls = [c for c in runner_calls if c[:2] == ["docker", "run"]]
    assert len(run_calls) == 1


def test_prepare_exclusions_match_exemption_wins_over_manual_P10():
    """P10: a manual exclusion must NOT pre-empt the match exemption -- a match-config task is
    skipped before `manual` is even consulted, so a (mistaken or stale) manual entry naming a
    match task has no effect and the task is never probed."""
    task = _match_task("m1")
    runner = FakeRunner(default=FakeRunner.Proc(0, "", "should-not-run"))
    golds, exclusions = AB.prepare_exclusions([task], SCRIPTS_ROOT, runner,
                                              manual={"m1": "stale manual entry"})
    assert exclusions == [] and golds == {}
    assert runner.calls == []


def test_prepare_exclusions_setup_failure_records_failed_step():
    """D2 rule v2 diagnostic requirement: a setup (create/init/start) failure for a gold-slot task
    is `no_gold` with the failing step recorded, not a silent/unexplained exclusion (operator's
    std-004-8 complaint: 'came back no_gold with no explanation')."""
    def runner(cmd, **kw):
        if cmd[:2] == ["docker", "run"]:
            return FakeRunner.Proc(1, "", "create failed: no such image")
        return FakeRunner.Proc(0, "", "")
    golds, exclusions = AB.prepare_exclusions([_check_task("t1")], SCRIPTS_ROOT, runner)
    assert golds == {}
    assert len(exclusions) == 1
    assert exclusions[0]["id"] == "t1" and exclusions[0]["reason"] == "no_gold"
    assert exclusions[0]["failed_step"] == "create"


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
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "abc",
          "image_ids": {"default": "id1"}, "complete": True}
    assert AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={"default": "id1"}) is None


def test_validate_exclusions_artifact_refuses_missing():
    assert "run --prepare" in AB.validate_exclusions_artifact(None, corpus_sha256="x", image_ids={})


def test_validate_exclusions_artifact_refuses_incomplete():
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "abc", "image_ids": {},
          "complete": False}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={})
    assert reason and "complete" in reason


def test_validate_exclusions_artifact_refuses_corpus_drift():
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "OLD", "image_ids": {},
          "complete": True}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="NEW", image_ids={})
    assert reason and "corpus" in reason


def test_validate_exclusions_artifact_refuses_image_drift():
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "abc",
          "image_ids": {"default": "old"}, "complete": True}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={"default": "new"})
    assert reason and "image" in reason


def test_validate_exclusions_artifact_refuses_old_rule_version():
    """D2 rule-v2 (operator 2026-09-30): an artifact produced under the OLD (two-separate-
    containers) rule must be refused outright, never silently reused -- its exclusions are known
    to contain false positives for randomized-init tasks."""
    doc = {"rule_version": 1, "corpus_sha256": "abc", "image_ids": {}, "complete": True}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={})
    assert reason and "rule_version" in reason


def test_validate_exclusions_artifact_refuses_scripts_drift_P10():
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "abc", "image_ids": {},
          "complete": True, "scripts_sha256": "old"}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={},
                                             scripts_sha256="new")
    assert reason and "scripts" in reason


def test_validate_exclusions_artifact_refuses_missing_disposition_entries_P10():
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "abc", "image_ids": {},
          "complete": True, "disposition": {"t1": "kept"}}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={},
                                             all_task_ids=["t1", "t2"])
    assert reason and "t2" in reason


def test_validate_exclusions_artifact_accepts_complete_disposition_P10():
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "abc", "image_ids": {},
          "complete": True, "disposition": {"t1": "kept", "t2": "match"}}
    assert AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={},
                                           all_task_ids=["t1", "t2"]) is None


def test_scripts_root_sha256_changes_when_a_script_file_changes(tmp_path):
    (tmp_path / "a.sh").write_text("echo 1\n")
    h1 = AB.scripts_root_sha256(tmp_path)
    (tmp_path / "a.sh").write_text("echo 2\n")
    h2 = AB.scripts_root_sha256(tmp_path)
    assert h1 != h2


def test_scripts_root_sha256_stable_for_unchanged_tree(tmp_path):
    (tmp_path / "a.sh").write_text("echo 1\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.sh").write_text("echo 2\n")
    assert AB.scripts_root_sha256(tmp_path) == AB.scripts_root_sha256(tmp_path)


def test_build_disposition_map_covers_match_kept_and_excluded():
    tasks = [_match_task("m1"), _check_task("t1"), _check_task("t2")]
    golds = {"t1": "3\n"}
    exclusions = [{"id": "t2", "reason": "gold_mismatch"}]
    disposition = AB.build_disposition_map(tasks, SCRIPTS_ROOT, golds, exclusions)
    assert disposition == {"m1": "match", "t1": "kept", "t2": "excluded:gold_mismatch"}


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
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "abc", "image_ids": {},
          "complete": True, "manual_exclusions_sha256": "old"}
    reason = AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={},
                                             manual_exclusions_sha256="new")
    assert reason and "manual" in reason


def test_validate_exclusions_artifact_accepts_matching_manual_exclusions_sha():
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "abc", "image_ids": {},
          "complete": True, "manual_exclusions_sha256": "same"}
    assert AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={},
                                           manual_exclusions_sha256="same") is None


def test_validate_exclusions_artifact_accepts_both_none_when_no_manual_file_either_time():
    doc = {"rule_version": AB.EXCLUSIONS_RULE_VERSION, "corpus_sha256": "abc", "image_ids": {},
          "complete": True, "manual_exclusions_sha256": None}
    assert AB.validate_exclusions_artifact(doc, corpus_sha256="abc", image_ids={},
                                           manual_exclusions_sha256=None) is None


# --------------------------------------------------------------------------- docker primitives
def test_docker_exec_bash_builds_exec_bash_c_with_extra_params():
    """11th cold review round 11 P7-residual: the code is now WRAPPED (code + a trailing rc-
    marker printf, see _RC_MARKER) inside the SAME bash -c script element -- the original code
    text and the marker constant must both be present, and the positional params still follow
    `--`, unaffected."""
    runner = FakeRunner()
    AB.docker_exec("c1", ("bash", "echo hi"), 10, runner, extra_params=["a", "b"])
    cmd = runner.last_cmd
    assert cmd[:5] == ["docker", "exec", "c1", "bash", "-c"]
    assert "echo hi" in cmd[5]   # wrapped in a subshell -- see docker_exec's bash branch
    assert AB._RC_MARKER in cmd[5]
    assert cmd[6:] == ["--", "a", "b"]


def test_docker_exec_python_builds_python3_c_with_argv():
    """11th round P7-residual: python code is now passed as ITS OWN argv element ($1 inside a
    bash -c wrapper, see docker_exec), never interpolated into the bash script text -- avoiding
    any shell-quoting hazard -- with the rc-marker printf appended the same way as bash."""
    runner = FakeRunner()
    AB.docker_exec("c1", ("python", "print(1)"), 10, runner, extra_params=["a"])
    cmd = runner.last_cmd
    assert cmd[:5] == ["docker", "exec", "c1", "bash", "-c"]
    assert AB._RC_MARKER in cmd[5]
    assert "python3" in cmd[5]
    assert cmd[6:] == ["--", "print(1)", "a"]   # code and params passed as bash's OWN positional argv


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
            assert cmd[4] == f"name=^{AB.GENERATE_CONTAINER_PREFIX}-"
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


# ----------------------------------------------------------- PersistentShell (scripted fake proc, P51)
class _FakeStdin:
    """Swallows writes -- P51's test cares only about SCRIPTED stdout bytes, never about re-running
    a real command."""
    def __init__(self):
        self.written = bytearray()

    def write(self, data):
        self.written += data

    def flush(self):
        pass

    def close(self):
        pass


class _ScriptedStdout:
    """`.read()` blocks (polling, cancellable) until the test `.push()`es a chunk -- mirrors a real
    pipe's blocking read without needing a real subprocess, so the exact byte layout around the
    sentinel is fully under the test's control."""
    def __init__(self):
        self._q: "queue.Queue" = queue.Queue()
        self._closed = False

    def push(self, chunk: bytes):
        self._q.put(chunk)

    def read(self, n):
        while not self._closed:
            try:
                return self._q.get(timeout=0.1)
            except queue.Empty:
                continue
        return b""

    def close(self):
        self._closed = True


class _FakeProc:
    def __init__(self):
        self.stdin = _FakeStdin()
        self.stdout = _ScriptedStdout()
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9

    def terminate(self):
        self.returncode = -15


@_timeout(10)
def test_persistent_shell_leftover_bytes_past_sentinel_carried_raw_not_decoded_P51(monkeypatch):
    """8th cold review round 8 P51 (MEDIUM): 'ABCD' + sentinel + an UNEXPECTED multibyte leftover
    ('€', 3 raw UTF-8 bytes) arriving in the SAME read chunk as the sentinel match must
    produce output == 'ABCD' and carry the leftover bytes RAW (never decoded, never folded into
    `output` via a byte-count trim) to the next run() call. The OLD code trimmed `decoded_text` by
    `len(raw) - idx` (a BYTE count) assuming the trailer was pure ASCII -- a multibyte leftover
    breaks that assumption and can corrupt real output."""
    fixed = uuid.UUID(int=0)
    monkeypatch.setattr(AB.uuid, "uuid4", lambda: fixed)
    sentinel = f"__M54_SENTINEL_{fixed.hex}__"
    marker = ("\n" + sentinel).encode("ascii")

    proc = _FakeProc()
    shell = AB.PersistentShell("c", popen=lambda *a, **k: proc,
                               runner=lambda *a, **k: FakeRunner.Proc(0, "", ""))
    # the handshake run("true", ...) inside start() -- a clean, empty-output, exit-0 round.
    proc.stdout.push(marker + b"0\n")
    shell.start()
    try:
        # the real round: "ABCD" + marker + exit 0 + newline + an unexpected leftover '€',
        # ALL in a single chunk (the exact scenario the byte-count trim got wrong).
        proc.stdout.push(b"ABCD" + marker + b"0\n" + "€".encode("utf-8"))
        res = shell.run("printf ABCD", timeout_s=5)
        assert res["output"] == "ABCD"
        assert res["exit_code"] == 0
        assert shell._carry == "€".encode("utf-8")   # carried RAW, never decoded here
    finally:
        proc.stdout.push(b"")   # EOF, so the reader thread can terminate cleanly
        shell.close()


@pytest.mark.parametrize("trailer,trailer_name", [
    ("€".encode("utf-8"), "complete_euro_sign"),
    ("€".encode("utf-8")[:1], "partial_first_byte_of_euro_sign"),
    (b"\xff", "raw_invalid_byte"),
])
def test_persistent_shell_trailer_never_influences_preceding_output_P11(monkeypatch, trailer, trailer_name):
    """9th cold review round 9 P11 (refines P51): the raw bytes are split at the sentinel BEFORE
    any decoding, and the command-output incremental decoder is finalized on the command bytes
    ONLY -- the trailer (complete, partial, or outright invalid UTF-8) must NEVER influence the
    preceding output. All three trailer shapes must produce output == "ABCD" and carry the
    trailer bytes forward raw, unmodified."""
    fixed = uuid.UUID(int=0)
    monkeypatch.setattr(AB.uuid, "uuid4", lambda: fixed)
    sentinel = f"__M54_SENTINEL_{fixed.hex}__"
    marker = ("\n" + sentinel).encode("ascii")

    proc = _FakeProc()
    shell = AB.PersistentShell("c", popen=lambda *a, **k: proc,
                               runner=lambda *a, **k: FakeRunner.Proc(0, "", ""))
    proc.stdout.push(marker + b"0\n")
    shell.start()
    try:
        proc.stdout.push(b"ABCD" + marker + b"0\n" + trailer)
        res = shell.run("printf ABCD", timeout_s=5)
        assert res["output"] == "ABCD", f"trailer={trailer_name}"
        assert res["exit_code"] == 0
        assert shell._carry == trailer   # carried RAW, byte-for-byte, regardless of validity
    finally:
        proc.stdout.push(b"")
        shell.close()


def test_persistent_shell_command_outputs_own_trailing_partial_lead_byte_is_decode_error_P12(monkeypatch):
    """10th cold review round 10 P12: a trailing PARTIAL lead byte in the COMMAND's OWN real
    output (e.g. the literal stdout of `printf 'ABCD\\342'`) is genuinely incomplete -- upstream's
    own strict WHOLE-output decode treats this as an ERROR, not something silently invisible.
    DISTINCT from P11's trailer tests: here the incomplete byte is BEFORE the sentinel (part of
    the command's real output), not an unexpected byte AFTER it."""
    fixed = uuid.UUID(int=0)
    monkeypatch.setattr(AB.uuid, "uuid4", lambda: fixed)
    sentinel = f"__M54_SENTINEL_{fixed.hex}__"
    marker = ("\n" + sentinel).encode("ascii")

    proc = _FakeProc()
    shell = AB.PersistentShell("c", popen=lambda *a, **k: proc,
                               runner=lambda *a, **k: FakeRunner.Proc(0, "", ""))
    proc.stdout.push(marker + b"0\n")
    shell.start()
    try:
        # "ABCD" + a LONE lead byte of a 3-byte UTF-8 sequence (e.g. printf's own real stdout),
        # immediately followed by the clean sentinel -- no unexpected trailer at all.
        proc.stdout.push(b"ABCD\xe2" + marker + b"0\n")
        res = shell.run("printf 'ABCD\\342'", timeout_s=5)
        assert res["output"] == AB.PersistentShell.UPSTREAM_DECODE_ERROR_TEXT
        assert res["exit_code"] == 0
        assert shell._carry == b""   # nothing unexpected past the sentinel this time
    finally:
        proc.stdout.push(b"")
        shell.close()


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


def test_persistent_shell_exit_code_137_is_NOT_treated_as_timed_out_G1():
    """4th cold review G1: there is no in-container `timeout` wrapper any more, so a sentinel that
    arrives WITH exit code 137 (SIGKILL) is most likely the container's own 1 GiB memory-cap OOM
    killer, not our Python-side deadline -- mis-scoring it as `exec_timeout` would hide a real
    memory failure behind the wrong label. Only OUR OWN deadline firing sets timed_out."""
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
    assert res["exit_code"] == 137 and res["timed_out"] is False


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


def test_persistent_shell_leftover_bytes_carry_forward_G5():
    """G5, mutation-sensitive: if a round's sentinel match leaves unexpected trailing bytes (e.g. a
    background job's output racing the sentinel), those bytes MUST be carried into and PREFIXED
    onto the next round's raw buffer -- deleting the carry-forward (`self._carry = b""`
    unconditionally, discarding whatever was captured) must fail this test."""
    class _LeftoverProc:
        def __init__(self):
            self.stdin = self
            self.stdout = self
            self._pending = None
            self._round = 0

        def write(self, s):
            m = re.search(rb"printf '\\n%s%d\\n' (\S+) \$\?", s)
            sentinel = m.group(1)
            if self._round == 0:
                self._pending = b"\n" + sentinel + b"0\nEXTRA-LEFTOVER-BYTES"
            else:
                self._pending = b"second-output\n" + sentinel + b"0\n"
            self._round += 1

        def flush(self):
            pass

        def read(self, n):
            while self._pending is None:
                time.sleep(0.01)
            data, self._pending = self._pending, None
            return data

        def poll(self):
            return None

    import threading as _threading
    proc = _LeftoverProc()
    shell = AB.PersistentShell("c1", popen=lambda *a, **k: proc)
    shell.proc = proc
    _threading.Thread(target=shell._reader_loop, daemon=True).start()
    res1 = shell.run("first", timeout_s=5)
    assert res1["exit_code"] == 0
    assert shell._carry == b"EXTRA-LEFTOVER-BYTES"
    res2 = shell.run("second", timeout_s=5)
    # the protocol's own leading "\n" (from `printf '\n%s%d\n' ...`) is indistinguishable from the
    # command's own trailing newline and is consumed as part of the sentinel match either way.
    assert res2["output"] == "EXTRA-LEFTOVER-BYTESsecond-output"


def test_persistent_shell_invalid_utf8_reproduces_upstream_message_P15b():
    """5th cold review P15b: upstream (`task.py` `_execute_bash_command`, confirmed at the pinned
    commit) strict-decodes with `.decode('utf-8')` and on failure the WHOLE result text becomes the
    literal string 'OS Environment output cannot be decoded as UTF-8' -- not per-byte mojibake."""
    class _BadUtf8Proc:
        def __init__(self):
            self.stdin = self
            self.stdout = self
            self._pending = None

        def write(self, s):
            m = re.search(rb"printf '\\n%s%d\\n' (\S+) \$\?", s)
            self._pending = b"\xff\xfe" + b"\n" + m.group(1) + b"0\n"

        def flush(self):
            pass

        def read(self, n):
            while self._pending is None:
                time.sleep(0.01)
            data, self._pending = self._pending, None
            return data

        def poll(self):
            return None

    import threading as _threading
    proc = _BadUtf8Proc()
    shell = AB.PersistentShell("c1", popen=lambda *a, **k: proc)
    shell.proc = proc
    _threading.Thread(target=shell._reader_loop, daemon=True).start()
    res = shell.run("whatever", timeout_s=5)
    assert res["output"] == AB.PersistentShell.UPSTREAM_DECODE_ERROR_TEXT
    assert res["exit_code"] == 0


@_timeout(10)
def test_persistent_shell_write_deadline_fires_before_a_blocking_write_completes_P8(tmp_path):
    """5th cold review P8: the deadline covers the WRITE itself, not just the subsequent read --
    a shell busy running a long foreground command (not yet reading stdin) can fill the OS pipe's
    write buffer; a blocked write past the deadline must itself report timed_out=True, well before
    bash's own sleep would otherwise finish."""
    shell = _real_shell(tmp_path)
    try:
        huge = "x" * (300 * 1024)
        script = f"sleep 2\necho {huge}"
        t0 = time.monotonic()
        res = shell.run(script, timeout_s=0.5)
        elapsed = time.monotonic() - t0
        assert res["timed_out"] is True
        assert elapsed < 1.5, f"write-deadline timeout took {elapsed:.2f}s -- should fire near 0.5s"
    finally:
        shell.close()


def test_persistent_shell_reader_queue_is_actually_bounded_G2_J():
    """6th cold review round 6, addendum J: mutation-sensitive -- an UNBOUNDED `queue.Queue()`
    (the pre-G2 state) would never raise `Full` here. Proves `queue_maxsize` is actually wired
    into the real `queue.Queue(maxsize=...)` the reader thread writes to, not just accepted and
    ignored."""
    import queue as _queue
    shell = AB.PersistentShell("c1", queue_maxsize=2)
    assert shell._q.maxsize == 2
    shell._q.put_nowait(b"a")
    shell._q.put_nowait(b"b")
    with pytest.raises(_queue.Full):
        shell._q.put_nowait(b"c")


@_timeout(10)
def test_persistent_shell_read_write_do_not_deadlock_P22(tmp_path):
    """6th cold review (round 6) P22, HIGH, real-bash reproduction: `head -c 20971520 /dev/zero`
    completes in ~0.03s alone; the SAME command followed by a 300 KiB comment on one stdin write
    used to wedge solid (>1s, effectively forever) -- bash starts executing the first line and
    floods its own stdout; the reader thread fills the bounded queue (G2, maxsize=256) and blocks
    on put(); the OLD `run()` was still parked awaiting the full write before it ever drained that
    queue. The fix services reads and the (now backgrounded) write concurrently against one
    deadline."""
    shell = _real_shell(tmp_path)
    try:
        comment = "x" * (300 * 1024)
        script = f"head -c 20971520 /dev/zero\n# {comment}"
        t0 = time.monotonic()
        res = shell.run(script, timeout_s=10)
        elapsed = time.monotonic() - t0
        assert res["exit_code"] == 0 and res["timed_out"] is False
        # 20MB is well past the G2 1MiB retention cap, so the DISPLAY text is capped -- the point
        # of this test is that it completes at all (no deadlock), not the exact capped length.
        assert res["raw_output_len"] == 20971520
        assert elapsed < 2.0, f"took {elapsed:.2f}s -- should complete in well under 2s, not deadlock"
    finally:
        shell.close()


@_timeout(10)
def test_persistent_shell_close_bounded_even_with_a_pipe_holding_descendant_P22(tmp_path):
    """P22: close() must return promptly even when a backgrounded descendant (`sleep 30 &`) still
    holds a reference to the shell's stdout pipe -- the OLD close() could wedge on its own
    unbounded `self.proc.stdin.write(b"exit\\n")` call if the shell was busy; this proves the
    bounded write + bounded wait/kill + bounded thread joins keep close() itself fast regardless."""
    shell = _real_shell(tmp_path)
    shell.run("sleep 30 & disown", timeout_s=5)
    t0 = time.monotonic()
    shell.close()
    elapsed = time.monotonic() - t0
    assert elapsed < 3.0, f"close() took {elapsed:.2f}s -- should return within 3s"
    assert shell.proc.poll() is not None


@_timeout(15)
def test_persistent_shell_reader_thread_terminates_after_close_P41(tmp_path):
    """7th cold review round 7 P41 (MEDIUM), reproduced: after a background writer filled the
    queue, close() itself returned in ~0.3s (bounded, as designed) -- but after killing every
    process, the READER THREAD remained alive, still parked in a blocking Queue.put() with 256
    queued chunks nobody would ever drain; a timed Thread.join() alone cannot cancel a thread
    stuck in a blocking call. This test proves the thread is ACTUALLY GONE after close(), not just
    that close() itself returned quickly -- a background flooder (`while :; do echo tick; done &`)
    keeps producing output AFTER the triggering run() call has already returned (nobody draining
    the queue any more), and a `sleep 30 &` holds the shell's pipe open too."""
    shell = _real_shell(tmp_path)
    shell.run("(while :; do echo tick; done &) ; sleep 30 & disown", timeout_s=3)
    # give the flooder time to actually fill the 256-chunk queue with nobody draining it.
    time.sleep(1.5)
    t0 = time.monotonic()
    shell.close()
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0, f"close() took {elapsed:.2f}s"
    assert shell._reader_thread is not None
    assert not shell._reader_thread.is_alive(), "reader thread leaked past close()"


def test_persistent_shell_start_returns_the_handshake_result_P9b(tmp_path):
    """P9(b): start() must return the handshake ("true") round's result so the caller (run_task)
    can validate it BEFORE ever making a model call, rather than discarding it."""
    home = tmp_path / f"home-{uuid.uuid4().hex}"
    home.mkdir()
    shell = AB.PersistentShell("unused-container", popen=_real_bash_popen_factory(home),
                              runner=lambda *a, **k: FakeRunner.Proc(0, "", ""))
    handshake = shell.start()
    try:
        assert handshake["exit_code"] == 0
        assert handshake["shell_died"] is False and handshake["timed_out"] is False
    finally:
        shell.close()


@_timeout(15)
def test_persistent_shell_real_bash_600kb_output_fast_and_uncapped(tmp_path):
    """3rd cold review R1: the old O(n^2) `re.search` over the whole buffer measured 20KB->9.4s,
    50KB->116s, >=100KB effectively hangs. The incremental bytearray.find() scan must handle a
    sizeable output in well under 2s. 600 KiB is comfortably UNDER the G2 1 MiB retention cap
    (sentinel + exit-code overhead on top of a round 1 MiB input would tip exactly-1MiB over the
    cap), so this also proves a legitimate large-but-not-huge output is NOT truncated."""
    shell = _real_shell(tmp_path)
    try:
        t0 = time.monotonic()
        res = shell.run("head -c 614400 /dev/zero | tr '\\0' x", timeout_s=10)
        elapsed = time.monotonic() - t0
        assert res["exit_code"] == 0 and res["timed_out"] is False
        assert len(res["output"]) == 614400
        assert res["raw_output_len"] == 614400
        assert elapsed < 2.0, f"600KB took {elapsed:.2f}s -- should be well under 2s"
    finally:
        shell.close()


@_timeout(15)
@_timeout(10)
def test_persistent_shell_real_bash_timeout_finalizes_a_trailing_partial_byte_P12(tmp_path):
    """10th cold review round 10 P12: the decoder must be finalized (final=True) on a TIMEOUT
    exit too, not just the sentinel-found success path -- real bash never reaches the sentinel
    (the command itself hangs), so `output` is built from whatever arrived before the deadline;
    a trailing partial lead byte in THAT must still produce the decode-error text."""
    shell = _real_shell(tmp_path)
    try:
        res = shell.run("printf 'ABCD\\342'; sleep 999", timeout_s=0.3)
        assert res["timed_out"] is True
        assert res["output"] == AB.PersistentShell.UPSTREAM_DECODE_ERROR_TEXT
    finally:
        shell.close()


def test_persistent_shell_real_bash_4mb_output_fast_and_capped_G2(tmp_path):
    """4th cold review G2: an output well past the 1 MiB retention cap is held/returned capped
    (head 512 KiB + tail 512 KiB + a drop marker) -- NOT buffered in full -- while
    `raw_output_len` still reports the TRUE total so a huge/degenerate output stays visible in the
    data."""
    shell = _real_shell(tmp_path)
    try:
        t0 = time.monotonic()
        res = shell.run("head -c 4194304 /dev/zero | tr '\\0' x", timeout_s=10)
        elapsed = time.monotonic() - t0
        assert res["exit_code"] == 0 and res["timed_out"] is False
        assert res["raw_output_len"] == 4194304
        assert len(res["output"]) < 4194304
        assert len(res["output"]) <= AB.PersistentShell.MAX_RETAINED_BYTES + 64
        # P28: the DISPLAY TEXT is now capped by CHARACTER count (never a byte-offset cut, which
        # could split a multibyte codepoint), so its drop marker says "chars dropped".
        assert "chars dropped" in res["output"]
        assert elapsed < 2.0, f"4MB took {elapsed:.2f}s -- should be well under 2s"
    finally:
        shell.close()


@_timeout(15)
def test_persistent_shell_real_bash_1_2mb_of_euro_signs_roundtrips_P28(tmp_path):
    """6th cold review round 6 P28, MEDIUM, reproduction: 1.2MB of valid multi-byte UTF-8 (`€`,
    3 bytes each) is well past the 1 MiB retention cap, so compaction WILL trigger -- a naive
    fixed BYTE-offset head/tail cut can land mid-character and corrupt the WHOLE output into the
    upstream decode-error message, even though every byte the process produced was genuinely valid
    UTF-8. Decoding incrementally per ORIGINAL chunk (never re-decoding a post-hoc byte slice)
    must round-trip real `€` characters instead."""
    shell = _real_shell(tmp_path)
    try:
        res = shell.run("python3 -c \"import sys; sys.stdout.write(chr(0x20AC) * 400000)\"",
                        timeout_s=10)
        assert res["exit_code"] == 0 and res["timed_out"] is False
        assert res["raw_output_len"] == 400000 * 3
        assert res["output"] != AB.PersistentShell.UPSTREAM_DECODE_ERROR_TEXT
        assert "€" in res["output"]
        assert res["output"].count("€") > 100000   # most of it survived despite compaction
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


# --------------------------------------------------------------------------- transcripts
def test_dualsubmit_driver_per_turn_captures_transcript_fields():
    inner = FakeDriver(script=[complete_result(
        content="let me look", reasoning="thinking...", finish_reason="tool_calls",
        completion_tokens=10, wall_s=1.5, tool_calls=[tool_call("bash_action", {"script": "ls"})])])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    t = d.per_turn[0]
    assert t["turn"] == 1
    assert t["assistant_content"] == "let me look"
    assert t["reasoning_content"] == "thinking..."
    assert t["wall_s"] == 1.5
    assert t["tool_call"] == {"name": "bash_action", "args": {"script": "ls"}}
    assert t["tool_result"] is None and t["raw_output_len"] is None   # filled by build_tools, not here


def test_dualsubmit_driver_per_turn_omits_reasoning_when_absent():
    inner = FakeDriver(script=[complete_result(reasoning="")])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    assert "reasoning_content" not in d.per_turn[0]


def test_dualsubmit_driver_per_turn_tool_call_none_when_no_tool_calls():
    inner = FakeDriver(script=[complete_result(tool_calls=[], content="final answer prose")])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    assert d.per_turn[0]["tool_call"] is None


def test_dualsubmit_driver_per_turn_tool_result_submitted_on_answer_action():
    inner = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "x"})])])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    assert d.per_turn[0]["tool_result"] == "submitted"


def test_dualsubmit_driver_per_turn_tool_result_submitted_on_finish_action():
    inner = FakeDriver(script=[complete_result(tool_calls=[tool_call("finish_action", {"thought": "done"})])])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    assert d.per_turn[0]["tool_result"] == "submitted"
    assert d.per_turn[0]["tool_call"] == {"name": "finish_action", "args": {"thought": "done"}}


def test_dualsubmit_driver_turn_numbers_increment():
    inner = FakeDriver(script=[complete_result(tool_calls=[tool_call("bash_action", {"script": "a"})]),
                               complete_result(tool_calls=[tool_call("bash_action", {"script": "b"})])])
    d = AB.DualSubmitDriver(inner, timeout=5)
    d.complete("m", [], {})
    d.complete("m", [], {})
    assert [t["turn"] for t in d.per_turn] == [1, 2]


def test_build_tools_patches_the_current_turn_with_tool_result_and_raw_output_len(tmp_path):
    shell = _real_shell(tmp_path)
    try:
        transcript_turns = [{"turn": 1, "tool_call": {"name": "bash_action", "args": {"script": "echo hi"}},
                             "tool_result": None, "raw_output_len": None}]
        tools = AB.build_tools(shell, timeout=10, counters={}, transcript_turns=transcript_turns)
        bash = {t.name: t for t in tools}["bash_action"]
        out = bash.fn({"script": "echo hi"})
        assert transcript_turns[0]["tool_result"] == out
        assert transcript_turns[0]["raw_output_len"] == len("hi\n")   # pre-truncation, pre-wrap
    finally:
        shell.close()


def test_build_tools_without_transcript_turns_is_a_noop():
    """transcript_turns is optional -- omitting it must not break anything."""
    shell = AB.PersistentShell("c1")
    tools = AB.build_tools(shell)   # should not raise
    assert {t.name for t in tools} == {"bash_action", "finish_action", "answer_action"}


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


def test_evaluate_convergence_missing_completion_tokens_is_defensive_not_a_crash_P24():
    """6th cold review round 6 P24: the P11 `missing_usage` nonconv_kind is REMOVED -- a response
    missing `completion_tokens` now ESCALATES at the client boundary
    (bench.client.probe -> MalformedResponseError -> TransportFailure, see test_driver.py) and
    never reaches this function on a live run. This only proves the DEFENSIVE fallback (malformed/
    historical data) does not crash and does not force non-convergence on its own."""
    per_turn = [{"completion_tokens": None, "finish_reason": "stop", "prompt_tokens": 1}]
    out = AB.evaluate_convergence(per_turn, thinking_budget=100, context_limit=None, max_tokens=None)
    assert out["converged"] is True
    assert "missing_usage" not in out["nonconv_kinds"]


def test_evaluate_convergence_nonconv_kinds_empty_when_converged():
    per_turn = [{"completion_tokens": 5, "finish_reason": "stop", "prompt_tokens": 1}]
    out = AB.evaluate_convergence(per_turn, thinking_budget=100, context_limit=None, max_tokens=None)
    assert out["converged"] is True
    assert out["nonconv_kinds"] == []


def test_evaluate_convergence_reports_per_turn_resolved_budget():
    per_turn = [{"completion_tokens": 5, "finish_reason": "stop", "prompt_tokens": 1}]
    out = AB.evaluate_convergence(per_turn, thinking_budget=100, context_limit=None, max_tokens=None)
    assert out["per_turn_resolved_budget"] == [100]


def test_evaluate_convergence_bad_finish_reason_is_tagged():
    per_turn = [{"completion_tokens": 5, "finish_reason": "content_filter", "prompt_tokens": 1}]
    out = AB.evaluate_convergence(per_turn, thinking_budget=100, context_limit=None, max_tokens=None)
    assert out["converged"] is False
    assert "bad_finish_reason" in out["nonconv_kinds"]


def test_evaluate_convergence_length_finish_reason_is_budget_hit_not_bad_finish_P36():
    """7th cold review round 7 P36: finish_reason=="length" (a max_tokens hit) is itself a
    budget/length exhaustion event -- classified as `budget_hit`, never the generic
    `bad_finish_reason` bucket, even when this turn's own completion_tokens stayed under the
    thinking_budget (a SMALLER max_tokens cap can be hit first)."""
    per_turn = [{"completion_tokens": 5, "finish_reason": "length", "prompt_tokens": 1}]
    out = AB.evaluate_convergence(per_turn, thinking_budget=100, context_limit=None, max_tokens=None)
    assert out["converged"] is False
    assert "budget_hit" in out["nonconv_kinds"]
    assert "bad_finish_reason" not in out["nonconv_kinds"]


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


def test_run_task_failed_docker_run_cleanup_does_not_raise_addendum_G():
    """Addendum G (round 6): when `docker run` itself fails (container never created), the
    FINAL-cleanup `remove_container(verify=True)` naturally sees `docker rm -f` report nonzero
    (no such container) -- that must NOT be treated as an unverified removal / raise
    ContainerCleanupError, since `docker ps -a` correctly proves the container is absent
    regardless (addendum G: the verdict depends solely on verification, not on rm's own rc)."""
    def runner(cmd, **kw):
        if cmd[:2] == ["docker", "run"]:
            return FakeRunner.Proc(1, "", "no such image")
        if cmd[:3] == ["docker", "rm", "-f"]:
            return FakeRunner.Proc(1, "", "no such container")
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(0, "", "")
        return FakeRunner.Proc(0, "", "")
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, FakeDriver(), {}, runner=runner,
                      popen=_shell_popen_ok())
    assert row["setup_error"] is True
    assert row["container_removed_verified"] is True


def test_sweep_stale_containers_raises_on_nonzero_discovery_rc_P40():
    """7th cold review round 7 P40 (HIGH): a mocked FAILED discovery command used to return []
    (indistinguishable from proven absence) -- it must abort BEFORE any container is created."""
    def runner(cmd, **kw):
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(1, "", "Cannot connect to the Docker daemon")
        return FakeRunner.Proc(0, "", "")
    with pytest.raises(AB.ContainerDiscoveryError):
        AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner)


def test_sweep_stale_containers_raises_on_discovery_launch_exception_P40():
    def runner(cmd, **kw):
        if cmd[:3] == ["docker", "ps", "-a"]:
            raise OSError("docker: command not found")
        return FakeRunner.Proc(0, "", "")
    with pytest.raises(AB.ContainerDiscoveryError):
        AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner)


def test_sweep_stale_containers_succeeds_when_discovery_rc_is_zero_and_empty_P40():
    def runner(cmd, **kw):
        return FakeRunner.Proc(0, "", "")
    assert AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner) == []


def test_sweep_stale_containers_raises_on_unverified_removal_P26():
    def runner(cmd, **kw):
        if cmd[:3] == ["docker", "rm", "-f"]:
            return FakeRunner.Proc(0, "", "")
        if cmd[:3] == ["docker", "ps", "-a"]:
            filter_arg = cmd[4] if len(cmd) > 4 else ""
            if filter_arg.endswith("-"):   # sweep's own discovery query (prefix match)
                return FakeRunner.Proc(0, "agentbench-os-run-stale\n", "")
            return FakeRunner.Proc(0, "agentbench-os-run-stale\n", "")   # verify: still present!
        return FakeRunner.Proc(0, "", "")
    with pytest.raises(AB.ContainerCleanupError):
        AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner)


def test_sweep_stale_containers_succeeds_when_removal_is_verified_P26():
    def runner(cmd, **kw):
        if cmd[:3] == ["docker", "rm", "-f"]:
            return FakeRunner.Proc(0, "", "")
        if cmd[:3] == ["docker", "ps", "-a"]:
            filter_arg = cmd[4] if len(cmd) > 4 else ""
            if filter_arg.endswith("-"):
                return FakeRunner.Proc(0, "agentbench-os-run-stale\n", "")
            return FakeRunner.Proc(0, "", "")   # verify: confirmed absent
        return FakeRunner.Proc(0, "", "")
    names = AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner)
    assert names == ["agentbench-os-run-stale"]


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


def test_run_task_malformed_finish_action_does_not_produce_a_passing_one_turn_episode_P27():
    """6th cold review round 6 P27 (HIGH), the literal reproduction: malformed JSON in
    finish_action used to become answer_action({"answer": null}) -- a FALSE submission that could
    pass a state-check/match task on turn 1. The malformed call must be rejected (parse-error
    tool response, episode continues); only the SECOND, well-formed answer_action submits."""
    driver = FakeDriver(script=[
        complete_result(tool_calls=[
            {"id": "c1", "type": "function",
             "function": {"name": "finish_action", "arguments": "{not valid json"}}]),
        complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})]),
    ])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=FakeRunner(default=FakeRunner.Proc(0, "", "")),
                      popen=_shell_popen_ok())
    assert row["passed"] is True
    assert row["turns"] == 2   # NOT a one-turn pass via the malformed call
    assert row["submitted_via"] == "answer"


def test_run_task_grading_infra_failure_preserves_completed_turns_and_transcript_addendum_I():
    """6th cold review round 6, addendum I: a grading-time infra failure (P23) must NOT reset an
    already-executed episode back to zero turns/tokens/transcript -- the row still carries the
    episode's actual completed turns and the transcript turns the model actually produced."""
    def runner(cmd, **kw):
        if cmd[:2] == ["docker", "run"]:
            return FakeRunner.Proc(0, "", "")
        if cmd[:2] == ["docker", "exec"] and any(isinstance(c, str) and "echo gold" in c for c in cmd):
            return FakeRunner.Proc(127, "", "Error response from daemon: No such container: abc")
        return FakeRunner.Proc(0, "", "")
    task = {"id": "t1", "group": 1, "labels": [],
           "evaluation": {"check": [None], "example": {"code": "echo gold"}}, "description": "d"}
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "x"})])])
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["setup_error"] is True
    assert row["infra_evidence"] is not None and row["infra_evidence"]["exit_code"] == 127
    assert row["turns"] == 1   # the episode actually ran one turn -- not reset to 0
    assert len(row["_transcript_turns"]) == 1
    assert row["submitted_via"] == "answer"


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


def test_run_task_row_carries_wall_total_s_covering_full_lifecycle_P32():
    """6th cold review round 6 P32: wall_total_s covers container create -> verified removal,
    not just the agent loop's own wall_s -- it must be >= wall_s (cleanup/setup time is on top)."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert isinstance(row["wall_total_s"], (int, float))
    assert row["wall_total_s"] >= row["wall_s"]


def test_run_task_setup_error_row_also_carries_wall_total_s_P32():
    runner = FakeRunner(default=FakeRunner.Proc(1, "", "init failed"))
    task = {"id": "t1", "group": 1, "labels": [],
           "create": {"local": "default", "init": {"code": "false"}},
           "evaluation": {"match": "x"}, "description": "d"}
    row = AB.run_task("m", task, SCRIPTS_ROOT, FakeDriver(), {}, runner=runner, popen=_shell_popen_ok())
    assert row["setup_error"] is True
    assert isinstance(row["wall_total_s"], (int, float))


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
    # P43(a): the fed-back timeout message is saved in the transcript before raising.
    turns = row["_transcript_turns"]
    assert len(turns) == 1
    assert "timed out after" in turns[-1]["tool_result"]


def test_run_task_malformed_submit_args_save_fed_back_parse_error_in_transcript_P43a():
    """7th cold review round 7 P43(a): a malformed finish_action/answer_action call's transcript
    turn must carry the ACTUAL fed-back parse-error text in tool_result, not None."""
    driver = FakeDriver(script=[
        complete_result(tool_calls=[
            {"id": "c1", "type": "function",
             "function": {"name": "finish_action", "arguments": "{not valid json"}}]),
        complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})]),
    ])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=FakeRunner(default=FakeRunner.Proc(0, "", "")),
                      popen=_shell_popen_ok())
    assert row["passed"] is True
    turns = row["_transcript_turns"]
    assert len(turns) == 2
    assert turns[0]["tool_result"] is not None
    # R5: bare str(e), no "Error parsing arguments: " prefix -- upstream task.py:575-592.
    assert "Expecting property name" in turns[0]["tool_result"]
    assert not turns[0]["tool_result"].startswith("Error parsing arguments")
    assert turns[0]["tool_call"]["parse_error"] == turns[0]["tool_result"]


def test_run_task_unexpected_grading_exception_preserves_completed_turns_P43a():
    """P43(a): an UNEXPECTED exception during grading (not a known infra/parse condition) must not
    reset an already-executed episode's transcript to empty."""
    def boom_match(*a, **k):
        raise RuntimeError("boom during grading")
    task = _match_cfg_task()
    task["evaluation"] = {"match": {"_boom": True}}   # triggers evaluate_match to raise via bad cfg

    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    orig_evaluate_match = AB.evaluate_match
    try:
        AB.evaluate_match = boom_match
        row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {},
                          runner=FakeRunner(default=FakeRunner.Proc(0, "", "")), popen=_shell_popen_ok())
    finally:
        AB.evaluate_match = orig_evaluate_match
    assert row["setup_error"] is True
    assert row["error"] is not None and "boom during grading" in row["error"]
    assert len(row["_transcript_turns"]) == 1   # the episode's real turn survives


def test_run_task_unexpected_grading_exception_preserves_real_turn_and_token_counters_P53a():
    """8th cold review round 8 P53(a): an unexpected grading exception must keep the loop's REAL
    turns/token counters on the row, not just the transcript -- _fail_row's defaults (turns=0,
    completion_tokens_total=0, ...) must be overridden with the actual values from a MULTI-turn
    episode."""
    def boom_match(*a, **k):
        raise RuntimeError("boom during grading")
    task = _match_cfg_task()
    task["evaluation"] = {"match": {"_boom": True}}

    driver = FakeDriver(script=[
        complete_result(tool_calls=[tool_call("bash_action", {"script": "echo hi"})], completion_tokens=7),
        complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})], completion_tokens=3),
    ])
    orig_evaluate_match = AB.evaluate_match
    try:
        AB.evaluate_match = boom_match
        row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {},
                          runner=FakeRunner(default=FakeRunner.Proc(0, "", "")), popen=_shell_popen_ok())
    finally:
        AB.evaluate_match = orig_evaluate_match
    assert row["setup_error"] is True
    assert row["turns"] == 2   # NOT the _fail_row default of 0
    assert row["completion_tokens_total"] == 10   # NOT 0
    assert row["per_turn_completion_tokens"] == [7, 3]
    assert len(row["per_turn_finish_reasons"]) == 2
    assert row["submitted_via"] == "answer"


def test_run_task_unicode_error_reaching_the_catch_all_is_flagged_harness_error_P8b():
    """9th cold review round 9 P8(b): after docker_exec's errors="replace" fix, no LEGITIMATE
    grading path should ever raise a UnicodeDecodeError -- one reaching the final catch-all is, by
    construction, a HARNESS bug (our own decoding missed a spot somewhere), flagged distinctly so
    it surfaces for a fix rather than reading as routine infra flakiness."""
    def boom_match(*a, **k):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "simulated harness decode bug")
    task = _match_cfg_task()
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    orig_evaluate_match = AB.evaluate_match
    try:
        AB.evaluate_match = boom_match
        row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {},
                          runner=FakeRunner(default=FakeRunner.Proc(0, "", "")), popen=_shell_popen_ok())
    finally:
        AB.evaluate_match = orig_evaluate_match
    assert row["setup_error"] is True
    assert row["harness_error"] is True
    assert "simulated harness decode bug" in row["error"]


def test_run_task_ordinary_value_error_is_not_flagged_harness_error_P8b():
    """A ValueError that is NOT a UnicodeError (e.g. an ordinary bug elsewhere in grading) must
    NOT be misclassified as a harness decoding bug."""
    def boom_match(*a, **k):
        raise ValueError("unrelated bug")
    task = _match_cfg_task()
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    orig_evaluate_match = AB.evaluate_match
    try:
        AB.evaluate_match = boom_match
        row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {},
                          runner=FakeRunner(default=FakeRunner.Proc(0, "", "")), popen=_shell_popen_ok())
    finally:
        AB.evaluate_match = orig_evaluate_match
    assert row["setup_error"] is True
    assert row["harness_error"] is False


# --------------------------------------------------------------------------- R2/P49 upstream-fidelity arg extraction
def test_extract_tool_arg_is_purely_positional_ignores_the_documented_key_P49():
    """8th cold review round 8 P49 (supersedes R2's "prefer the expected key" compromise):
    upstream is PURELY positional -- even when the documented key ("script") IS present, if it is
    not FIRST in the dict, upstream still takes the first value by position."""
    assert AB._extract_tool_arg({"extra": "junk", "script": "ls"}) == "junk"


def test_extract_tool_arg_takes_the_first_value_regardless_of_key_name():
    """R2's original reproduction, still valid under P49: a model emitting `command` instead of
    `script` must still have its argument used, not silently dropped."""
    assert AB._extract_tool_arg({"command": "echo hi"}) == "echo hi"


def test_extract_tool_arg_raises_index_error_on_empty_args_P49():
    """P49: mirrors upstream's `list({}.values())[0]` -> IndexError("list index out of range")."""
    with pytest.raises(IndexError, match="list index out of range"):
        AB._extract_tool_arg({})


def test_run_task_bash_action_with_wrong_key_name_still_runs_the_script_R2():
    """R2's literal reproduction: `bash_action({"command":"echo hi"})` must actually run
    `echo hi`, not silently execute an empty script because `args.get("script")` found nothing."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[
        complete_result(tool_calls=[tool_call("bash_action", {"command": "echo R2_MARKER_919"})]),
        complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})]),
    ])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["passed"] is True
    turns = row["_transcript_turns"]
    assert "R2_MARKER_919" in turns[0]["tool_result"]


def test_run_task_empty_bash_action_ends_the_episode_as_a_scored_fail_P10():
    """9th cold review round 9 P10 (supersedes the P53(b) reproduction, which encoded the
    OLD P49-era "continue the episode" behavior): verified against the pinned upstream source --
    bash_action's empty-args IndexError is UNCAUGHT upstream, terminating the whole sample via its
    task-error path. This is functionally a SCORED FAIL that ENDS the episode immediately, not a
    recoverable tool error the episode continues past."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[
        complete_result(tool_calls=[tool_call("bash_action", {})]),
        complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})]),   # never reached
    ])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["turns"] == 1   # ended on the FIRST (empty) call -- the 2nd script entry never ran
    assert row["outcome"] == AO.FAILED_TESTS
    assert row["passed"] is False
    assert row["setup_error"] is False   # a SCORED fail, not infra
    turns = row["_transcript_turns"]
    assert turns[0]["tool_result"] == "empty tool arguments"


def test_run_task_answer_action_with_wrong_key_name_still_submits_the_answer_R2():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"response": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["answer"] == "love"
    assert row["passed"] is True


def test_run_task_finish_action_with_wrong_key_name_still_submits_the_thought_as_answer_R2():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("finish_action", {"reason": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["answer"] == "love"
    assert row["passed"] is True


def test_run_task_submit_args_with_multiple_keys_take_the_FIRST_value_not_the_documented_key_P49():
    """8th cold review round 8 P49 (supersedes R2): upstream is PURELY positional -- even with
    the documented key ("answer") present, if a DIFFERENT key comes first in the dict, upstream
    still takes that first value. This distinguishes P49 from R2's superseded "prefer the
    expected key" behavior."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[
        tool_call("answer_action", {"confidence": "high", "answer": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["answer"] == "high"   # the FIRST value, not the "answer"-keyed one
    assert row["passed"] is False    # "high" != "love" -- a real, scored miss


def test_run_task_empty_finish_action_submits_a_null_answer_not_a_parse_error_P49():
    """P49: upstream's finish_action tolerates an EMPTY call (arguments[0] if arguments else
    None) -- an empty finish_action is still a valid (if hopeless) submission, not fed back as a
    malformed-arguments error."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("finish_action", {})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["answer"] is None
    assert row["passed"] is False   # None != "love", but it IS a real scored submission
    assert row["turns"] == 1


def test_run_task_empty_answer_action_ends_the_episode_as_a_scored_fail_P10():
    """9th cold review round 9 P10 (supersedes the P49 reproduction, which recovered into an
    unknown-tool turn and let the episode continue -- the coordinator's ruling explicitly removes
    that recovery for this case): verified against the pinned upstream source -- answer_action's
    empty-args IndexError is UNCAUGHT upstream, terminating the whole sample via its task-error
    path. SCORED FAIL, episode ends immediately; submitted_via records "none" (a STRING, distinct
    from the Python None used for "never attempted a submission at all")."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[
        complete_result(tool_calls=[tool_call("answer_action", {})]),
        complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})]),   # never reached
    ])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["turns"] == 1   # ended on the FIRST (empty) call
    assert row["outcome"] == AO.FAILED_TESTS
    assert row["passed"] is False
    assert row["setup_error"] is False
    assert row["submitted_via"] == "none"
    assert row["answer"] is None
    turns = row["_transcript_turns"]
    assert turns[0]["tool_result"] == "empty tool arguments"


def test_run_task_empty_answer_action_abort_still_carries_that_turns_telemetry_P11():
    """10th cold review round 10 P11 (MEDIUM): an abort raised from WITHIN driver.complete()
    (empty answer_action) must still carry that response's telemetry into the row --
    completion_tokens_total and tool_calls must be consistent with the per-turn lists, which DO
    include the aborted turn (via DualSubmitDriver's own transcript append before it raises)."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[
        complete_result(tool_calls=[tool_call("answer_action", {})], completion_tokens=17),
    ])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["outcome"] == AO.FAILED_TESTS
    assert row["turns"] == 1
    assert len(row["per_turn_completion_tokens"]) == 1   # the aborted turn IS in the per-turn list
    assert row["per_turn_completion_tokens"] == [17]
    assert row["completion_tokens_total"] == 17          # must match, not silently 0
    assert row["tool_calls"] == 1                         # the one (aborting) call IS counted


def _check_cfg_task():
    """A non-match task (a real check chain, inline code -- no scripts_root file dependency) so
    the model's answer actually flows into a subprocess argv via docker_exec/run_check_chain."""
    return {"id": "std-004-0", "group": 4, "labels": ["l1"],
           "evaluation": {"check": [{"code": "exit 0", "language": "bash"}]},
           "description": "say something"}


def test_run_task_unrepresentable_answer_embedded_nul_is_scored_failed_tests_not_setup_error_P2():
    """11th cold review round 11 P2 (HIGH): a model answer that cannot be passed as a subprocess
    argv element (embedded NUL byte is the concrete case; any ValueError/TypeError raised while
    BUILDING the argv counts the same way) must be a SCORED failed_tests row with
    error="unrepresentable answer: ...", never setup_error -- the generic catch-all (which would
    otherwise wrongly mark it setup_error=True, outcome=SERVER_ERROR) must never see this
    exception. The runner here simulates exactly what a real subprocess.Popen raises for an
    argv element containing an embedded NUL byte."""
    def runner(cmd, **kw):
        if any(isinstance(c, str) and "\x00" in c for c in cmd):
            raise ValueError("embedded null byte")
        return FakeRunner.Proc(0, "", "")
    driver = FakeDriver(script=[
        complete_result(tool_calls=[tool_call("answer_action", {"answer": "bad\x00answer"})]),
    ])
    task = _check_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["outcome"] == AO.FAILED_TESTS
    assert row["passed"] is False
    assert row["setup_error"] is False
    assert "unrepresentable answer" in row["error"]


def test_run_task_harness_valueerror_unrelated_to_argv_is_NOT_labelled_unrepresentable_answer_Rb():
    """12th cold review round 12 R-b (minor severity, narrows the P2 catch): a ValueError/TypeError raised
    SOMEWHERE ELSE in the check-chain's broader logic (here: `docker inspect`'s own runner call,
    reached via _classify_check_result after a nonzero exit -- nothing to do with the model's
    answer at all) must NOT be mislabeled "unrepresentable answer" -- that would hide a genuine
    HARNESS bug behind a model-blaming message. It must propagate to the generic catch-all like
    any other unexpected exception: setup_error=True, outcome=SERVER_ERROR."""
    def runner(cmd, **kw):
        if cmd[:2] == ["docker", "run"]:
            return FakeRunner.Proc(0, "", "")
        if cmd[:2] == ["docker", "inspect"]:
            raise ValueError("some unrelated harness bug, nothing to do with the model's answer")
        if cmd[:2] == ["docker", "exec"]:
            return FakeRunner.Proc(1, "", "checker failed, no marker")   # triggers the inspect probe
        return FakeRunner.Proc(0, "", "")
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "x"})])])
    task = _check_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["setup_error"] is True
    assert row["outcome"] == AO.SERVER_ERROR
    assert row.get("error") is None or "unrepresentable answer" not in row["error"]


def test_run_task_a_valid_submit_followed_by_a_stray_empty_call_in_the_SAME_turn_still_solves_P10():
    """10th cold review round 10 P10 (MEDIUM, scoring -- fixes a round-9 regression): a complete,
    valid answer_action({"answer":"42"}) followed in the SAME turn by a stray empty
    answer_action({}) must still solve the episode -- agent_loop.run_agent (single_tool_call_
    per_turn=True) only ever dispatches position 0; DualSubmitDriver.complete() must apply
    semantics to position 0 ONLY and drop the rest, never let a never-dispatched position-1 call
    abort an otherwise-valid submission."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[
        tool_call("answer_action", {"answer": "42"}, call_id="c1"),
        tool_call("answer_action", {}, call_id="c2"),
    ])])
    task = {"id": "t1", "group": 1, "labels": [], "evaluation": {"match": "42"}, "description": "d"}
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["outcome"] == AO.SOLVED
    assert row["passed"] is True
    assert row["answer"] == "42"
    assert row["submitted_via"] == "answer"
    turns = row["_transcript_turns"]
    assert len(turns) == 1
    assert turns[0]["n_tool_calls"] == 2   # the raw count, even though only position 0 ran
    assert row["multi_call_turns"] == 1


def test_run_task_multi_call_turns_is_zero_when_every_turn_has_one_call_P10():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["multi_call_turns"] == 0
    assert row["_transcript_turns"][0]["n_tool_calls"] == 1


def test_run_task_unknown_tool_name_feeds_back_upstream_verbatim_text_P49():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[
        complete_result(tool_calls=[tool_call("not_a_real_tool", {"x": 1})]),
        complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})]),
    ])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    # the unknown-tool turn did not end the episode -- it continued to the 2nd (real) turn.
    assert row["turns"] == 2
    assert row["passed"] is True
    assert AB.UNKNOWN_TOOL_TEXT == "Invalid function call. Please call a tool instead"
    # 8th cold review round 8 P53(b): on_feedback now captures the REAL fed-back text at its one
    # true source, closing a gap where an unknown-tool turn's tool_result stayed None.
    turns = row["_transcript_turns"]
    assert turns[0]["tool_result"] == AB.UNKNOWN_TOOL_TEXT


def test_run_task_only_one_container_touched_per_task():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("bash_action", {"script": "ls"})]),
                                complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, max_turns=5, runner=runner, popen=_shell_popen_ok())
    names = {c["cmd"][5] for c in runner.calls if c["cmd"][:2] == ["docker", "run"]}
    assert len(names) == 1


def test_run_task_returns_transcript_turns_for_a_solved_episode():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(content="submitting now",
                                               tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    turns = row["_transcript_turns"]
    assert len(turns) == 1
    assert turns[0]["assistant_content"] == "submitting now"
    assert turns[0]["tool_result"] == "submitted"


def test_run_task_returns_empty_transcript_turns_for_a_setup_error():
    runner = FakeRunner(default=FakeRunner.Proc(1, "", "boom"))
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, FakeDriver(), {}, runner=runner, popen=_shell_popen_ok())
    assert row["_transcript_turns"] == []


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
    # 7th cold review round 7 P43(a): the fed-back abort message is saved in the transcript
    # BEFORE AbortEpisode is raised -- a shell-death episode used to retain tool_result=None even
    # though the model genuinely received this text back.
    turns = row["_transcript_turns"]
    assert len(turns) == 1
    assert turns[-1]["tool_result"] == "the persistent shell exited (e.g. the command ran `exit`)"


@_timeout(10)
def test_run_task_start_script_shell_death_is_also_setup_error(tmp_path):
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    task = {"id": "t1", "group": 1, "labels": [], "create": {"local": "default"}, "start": "exit 0",
           "evaluation": {"match": "x"}, "description": "d"}
    row = AB.run_task("m", task, SCRIPTS_ROOT, FakeDriver(), {}, runner=runner, popen=_shell_popen_ok())
    assert row["shell_died"] is True and row["setup_error"] is True


def test_run_task_handshake_failure_is_setup_error_with_no_model_call_P9b():
    """P9(b): a shell whose handshake ("true") round itself fails must never reach the agent
    loop -- the row is setup_error and the model driver is NEVER invoked."""
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))

    class _FailHandshakeProc:
        def __init__(self):
            self.stdin = self
            self.stdout = self
            self._pending = None

        def write(self, s):
            m = re.search(rb"printf '\\n%s%d\\n' (\S+) \$\?", s)
            self._pending = b"\n" + m.group(1) + b"1\n"

        def flush(self):
            pass

        def read(self, n):
            while self._pending is None:
                time.sleep(0.01)
            data, self._pending = self._pending, None
            return data

        def poll(self):
            return None

    class _BoomIfCalledDriver:
        def complete(self, *a, **k):
            pytest.fail("model must never be called when the shell handshake failed")

    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, _BoomIfCalledDriver(), {}, runner=runner,
                      popen=lambda *a, **k: _FailHandshakeProc())
    assert row["outcome"] == AO.SERVER_ERROR and row["setup_error"] is True
    assert "handshake" in row["error"]


# --------------------------------------------------------------------------- P16 container cleanup
def test_remove_container_verify_true_returns_true_when_rm_succeeds_and_absent():
    def runner(cmd, **kw):
        if cmd[:3] == ["docker", "rm", "-f"]:
            return FakeRunner.Proc(0, "", "")
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(0, "", "")
        return FakeRunner.Proc(0, "", "")
    assert AB.remove_container("c1", runner, verify=True) is True


def test_remove_container_verify_true_returns_false_when_still_present():
    def runner(cmd, **kw):
        if cmd[:3] == ["docker", "rm", "-f"]:
            return FakeRunner.Proc(0, "", "")
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(0, "c1\n", "")
        return FakeRunner.Proc(0, "", "")
    assert AB.remove_container("c1", runner, verify=True) is False


def test_remove_container_verify_true_ignores_rm_rc_when_verification_proves_absence_addendum_G():
    """Addendum G (round 6): `rm -f` can legitimately report nonzero for a container that was
    NEVER CREATED (a prior `docker run` failed) -- that is NOT a cleanup failure. The verdict
    depends SOLELY on the verification step (`docker ps -a` rc 0 + empty stdout), independent of
    `rm -f`'s own rc."""
    def runner(cmd, **kw):
        if cmd[:3] == ["docker", "rm", "-f"]:
            return FakeRunner.Proc(1, "", "no such container")
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(0, "", "")
        return FakeRunner.Proc(0, "", "")
    assert AB.remove_container("c1", runner, verify=True) is True


def test_remove_container_verify_true_returns_false_when_verification_command_itself_fails_P26():
    """6th cold review round 6 P26 (HIGH), reproduction: `docker rm -f` reports rc 0, but the
    VERIFICATION command (`docker ps -a`) itself fails (rc 1) while happening to produce empty
    stdout (e.g. an error went to stderr) -- the OLD check only looked at stdout, so this falsely
    verified. The check command's OWN rc must be required too."""
    def runner(cmd, **kw):
        if cmd[:3] == ["docker", "rm", "-f"]:
            return FakeRunner.Proc(0, "", "")
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(1, "", "docker: daemon hiccup")   # rc 1, empty stdout
        return FakeRunner.Proc(0, "", "")
    assert AB.remove_container("c1", runner, verify=True) is False


def test_remove_container_default_verify_false_is_best_effort_never_raises():
    runner = FakeRunner(default=FakeRunner.Proc(1, "", "boom"))
    assert AB.remove_container("c1", runner) is None


def test_run_task_row_carries_container_removed_verified_true_on_clean_removal():
    runner = FakeRunner(default=FakeRunner.Proc(0, "", ""))
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["container_removed_verified"] is True


def test_run_task_row_carries_container_removed_verified_false_when_rm_unverified():
    """P16: when final cleanup cannot be verified, the row still comes back (so the caller can
    append it) but flagged -- the caller decides whether to stop the run. Addendum G: the verdict
    is unverified here because the VERIFICATION step itself fails (rc 1), not because `rm -f`'s
    own rc is nonzero (that alone is no longer sufficient per P26)."""
    def runner(cmd, **kw):
        if cmd[:3] == ["docker", "ps", "-a"]:
            return FakeRunner.Proc(1, "", "docker: daemon hiccup")
        return FakeRunner.Proc(0, "", "")
    driver = FakeDriver(script=[complete_result(tool_calls=[tool_call("answer_action", {"answer": "love"})])])
    task = _match_cfg_task()
    row = AB.run_task("m", task, SCRIPTS_ROOT, driver, {}, runner=runner, popen=_shell_popen_ok())
    assert row["container_removed_verified"] is False


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
