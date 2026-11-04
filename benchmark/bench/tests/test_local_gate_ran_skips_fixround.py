"""P624 fix round (`.p624-material/dispositions.md`): fix 1 (skip lists compare as multisets), fix 2 (an id ran and passed only if
EVERY testcase with that id is clean), fix 3 (a junit absent after a successful pytest step is its own problem), plus the test
gaps of the first delivery. Hermetic: the runner is the fake of test_local_gate_ran_skips; the real gate is never run."""

import json
from pathlib import Path

from bench import local_gate as G
from bench.tests.test_local_gate_ran_skips import A, B, C, JunitRunner, _gate, _id, _problems, env  # noqa: F401  (env: fixture)

P1 = ("tests.test_p", "test_p[x-1]")
P2 = ("tests.test_p", "test_p[x-2]")


class NoJunitRunner(JunitRunner):
    """pytest 'succeeds' (rc 0) but writes no junit file."""

    def __call__(self, argv, cwd, env):
        junit = [a for a in argv if a.startswith("--junitxml=")]
        if junit:
            return 0, ""
        return super().__call__(argv, cwd, env)


def _gate_with(env, baseline_text, runner):
    (env["baselines"] / "mlx-serve.skips.txt").write_text(baseline_text)
    path = G.run("mlx-serve", env["sha"], live=env["live"], gate_dir=env["gate"], baselines=env["baselines"], runner=runner,
                 busy=lambda: [], dirty=runner.dirty, artifacts=lambda d: True)
    return json.loads(Path(path).read_text())


# ------------------------------------------------------------------ fix 1: multisets
# reproduces-failure: candidate (sets) gives PASS
def test_fix1_a_duplicated_baseline_line_is_a_problem(env):
    doc = _gate_with(env, f"{_id(A)}\n{_id(A)}\n", JunitRunner(skipped=[A]))
    assert doc["verdict"] == "FAIL"
    assert "skip baseline lists an entry more than once" in _problems(doc)


# reproduces-failure: candidate (sets) gives PASS
def test_fix1_a_duplicated_baseline_line_is_a_problem_even_when_the_entry_ran(env):
    doc = _gate_with(env, f"{_id(A)}\n{_id(A)}\n", JunitRunner(passed=[A]))
    assert doc["verdict"] == "FAIL"
    assert "skip baseline lists an entry more than once" in _problems(doc)


# reproduces-failure: candidate (sets) gives PASS
def test_fix1_a_skipped_id_twice_against_the_baseline_once_fails_with_the_skip_list_problem(env):
    doc = _gate(env, [A], skipped=[A, A])
    assert doc["verdict"] == "FAIL"
    assert "skip list != baseline" in _problems(doc)


# invariant: the same id twice in S and twice in W is (still) not a pass either way; one each passes
def test_fix1_one_skip_one_baseline_line_still_passes(env):
    doc = _gate(env, [A], skipped=[A])
    assert doc["verdict"] == "PASS" and doc["problems"] == []


# ------------------------------------------------------------------ fix 2: every testcase with the id must be clean
# reproduces-failure: candidate lists the id as ran-and-passed because one testcase is clean
def test_fix2_a_clean_and_a_failing_testcase_with_one_id_is_not_ran_and_passed(env):
    doc = _gate(env, [A], skipped=[], passed=[A], failed=[A])
    assert doc["verdict"] == "FAIL"
    assert "baseline skip neither skipped nor passed" in _problems(doc)
    assert doc["baseline_skips_ran"] == []


# reproduces-failure
def test_fix2_a_clean_and_an_errored_testcase_with_one_id_is_not_ran_and_passed(env):
    doc = _gate(env, [A], skipped=[], passed=[A], errored=[A])
    assert doc["verdict"] == "FAIL"
    assert "baseline skip neither skipped nor passed" in _problems(doc)
    assert doc["baseline_skips_ran"] == []


# reproduces-failure
def test_fix2_the_helper_omits_an_id_with_any_unclean_testcase(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text('<testsuites><testsuite>'
                 f'<testcase classname="{A[0]}" name="{A[1]}"/>'
                 f'<testcase classname="{A[0]}" name="{A[1]}"><failure message="x"/></testcase>'
                 f'<testcase classname="{B[0]}" name="{B[1]}"/>'
                 f'<testcase classname="{B[0]}" name="{B[1]}"/>'
                 '</testsuite></testsuites>')
    got = G.ran_and_passed_from_junit(p)
    assert _id(A) not in got and _id(B) in got  # B twice clean: listed once or twice is not pinned (spec: ids)


# ------------------------------------------------------------------ fix 3: junit absent after rc 0
# reproduces-failure: candidate reports "neither skipped nor passed" instead
def test_fix3_a_junit_absent_after_a_successful_pytest_step_is_its_own_problem(env):
    doc = _gate_with(env, f"{_id(A)}\n", NoJunitRunner())
    assert doc["verdict"] == "FAIL"
    assert "pytest junit not written" in _problems(doc)
    assert "neither skipped nor passed" not in _problems(doc)


# reproduces-failure: the skip checks do not run, so no skip-list message either
def test_fix3_a_junit_absent_runs_no_skip_checks(env):
    doc = _gate_with(env, f"{_id(A)}\n{_id(B)}\n", NoJunitRunner())
    assert doc["verdict"] == "FAIL"
    assert "skip list != baseline" not in _problems(doc) and "neither skipped nor passed" not in _problems(doc)


# ------------------------------------------------------------------ test gaps
# invariant: both problems at once, exact messages, today's message first
def test_both_problems_at_once_have_the_exact_messages_in_order(env):
    doc = _gate(env, [B], skipped=[A])
    assert doc["problems"] == [f"skip list != baseline: +['{_id(A)}'] -['{_id(B)}']",
                               f"baseline skip neither skipped nor passed: ['{_id(B)}']"]


# invariant: the -[...] tail lists all of W - S, including the entry that ran and passed
def test_the_minus_tail_includes_a_ran_and_passed_entry(env):
    doc = _gate(env, [A, B], skipped=[C], passed=[A])
    assert doc["verdict"] == "FAIL"
    assert doc["problems"] == [f"skip list != baseline: +['{_id(C)}'] -['{_id(A)}', '{_id(B)}']",
                               f"baseline skip neither skipped nor passed: ['{_id(B)}']"]
    assert doc["baseline_skips_ran"] == [_id(A)]


# invariant: a FAIL receipt after the pytest step still carries baseline_skips_ran with the entries that ran
def test_a_fail_receipt_after_the_pytest_step_carries_baseline_skips_ran(env):
    doc = _gate(env, [A, B], skipped=[], passed=[A])
    assert doc["verdict"] == "FAIL"
    assert doc["baseline_skips_ran"] == [_id(A)]


# invariant: multi-child testcases in both helpers
def test_a_multi_child_testcase_is_skipped_for_one_helper_and_never_passed_for_the_other(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text('<testsuites><testsuite>'
                 f'<testcase classname="{A[0]}" name="{A[1]}"><skipped/><failure message="x"/></testcase>'
                 f'<testcase classname="{B[0]}" name="{B[1]}"><failure message="x"/><error message="y"/></testcase>'
                 f'<testcase classname="{C[0]}" name="{C[1]}"><system-out>hi</system-out></testcase>'
                 '</testsuite></testsuites>')
    assert G.skipped_from_junit(p) == [_id(A)]  # the existing helper: any <skipped> child
    assert G.ran_and_passed_from_junit(p) == [_id(C)]  # <system-out> is not a failure kind; B and A are not passed


# invariant: a parametrised id in W, S and P (brackets and dashes survive every step)
def test_a_parametrised_id_in_baseline_skipped_and_passed(env):
    doc = _gate(env, [P1, P2], skipped=[P1], passed=[P2])
    assert doc["verdict"] == "PASS" and doc["problems"] == []
    assert doc["skipped_tests"] == [_id(P1)]
    assert doc["baseline_skips_ran"] == [_id(P2)]


# invariant
def test_a_parametrised_id_in_the_helpers(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text('<testsuites><testsuite>'
                 f'<testcase classname="{P1[0]}" name="{P1[1]}"><skipped/></testcase>'
                 f'<testcase classname="{P2[0]}" name="{P2[1]}"/>'
                 '</testsuite></testsuites>')
    assert G.skipped_from_junit(p) == [_id(P1)]
    assert G.ran_and_passed_from_junit(p) == [_id(P2)]
