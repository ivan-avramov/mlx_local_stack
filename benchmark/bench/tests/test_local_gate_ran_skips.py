"""P624 (`docs/specs/p624-gate-ran-skips.md` v1): a baseline-listed test that ran and passed in the gated tree does not fail the
gate and is recorded in the receipt (`baseline_skips_ran`); every other skip difference fails as before. The runner is mocked
(the fake of test_local_gate, extended to write passed / failed / errored testcases); the real gate is never run."""

import json
from pathlib import Path

import pytest

from bench import local_gate as G
from bench.tests.test_local_gate import Runner, _repo

LIVE_ORIGIN = "git@github.com:ivan-avramov/mlx-serve"
A = ("tests.test_a", "test_one")
B = ("tests.test_b", "test_two")
C = ("tests.test_c", "test_three")
D = ("tests.test_d", "test_four")


def _id(case):
    return f"{case[0]}::{case[1]}"


def _junit_xml(skipped=(), passed=(), failed=(), errored=()):
    cases = [f'<testcase classname="{c}" name="{n}"><skipped/></testcase>' for c, n in skipped]
    cases += [f'<testcase classname="{c}" name="{n}"/>' for c, n in passed]
    cases += [f'<testcase classname="{c}" name="{n}"><failure message="boom"/></testcase>' for c, n in failed]
    cases += [f'<testcase classname="{c}" name="{n}"><error message="boom"/></testcase>' for c, n in errored]
    return f'<testsuites><testsuite>{"".join(cases)}</testsuite></testsuites>'


class JunitRunner(Runner):
    """The Runner fake, writing passed / failed / errored testcases next to the skipped ones (the pytest step still rc 0)."""

    def __init__(self, skipped=(), passed=(), failed=(), errored=(), **kw):
        super().__init__(skipped=skipped, **kw)
        self.passed, self.failed, self.errored = passed, failed, errored

    def __call__(self, argv, cwd, env):
        rc, out = super().__call__(argv, cwd, env)
        if rc == 0 and any(a.startswith("--junitxml=") for a in argv):
            xml = next(a.split("=", 1)[1] for a in argv if a.startswith("--junitxml="))
            Path(xml).write_text(_junit_xml(self.skipped, self.passed, self.failed, self.errored))
        return rc, out


@pytest.fixture
def env(tmp_path):
    live = tmp_path / "live" / "mlx-serve"
    sha = _repo(live, {"pyproject.toml": "[project]\nname='x'\n", "uv.lock": "x\n"}, origin=LIVE_ORIGIN)
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    return dict(tmp=tmp_path, live=live, sha=sha, gate=tmp_path / "gate", baselines=baselines)


def _gate(env, baseline, **runner_kw):
    """Write the baseline (list of cases, or None for no file), run the gate on the fake, return the receipt document."""
    path = env["baselines"] / "mlx-serve.skips.txt"
    if baseline is not None:
        path.write_text("".join(f"{_id(c)}\n" for c in baseline))
    r = JunitRunner(**runner_kw)
    receipt = G.run("mlx-serve", env["sha"], live=env["live"], gate_dir=env["gate"], baselines=env["baselines"], runner=r,
                    busy=lambda: [], dirty=r.dirty, artifacts=lambda d: True)
    return json.loads(Path(receipt).read_text())


def _problems(doc):
    return " | ".join(doc["problems"])


# ------------------------------------------------------------------ helper ran_and_passed_from_junit
# new-behaviour
def test_helper_returns_none_for_an_absent_junit(tmp_path):
    assert G.ran_and_passed_from_junit(tmp_path / "missing.xml") is None


# new-behaviour
def test_helper_lists_only_testcases_with_no_skipped_failure_or_error_sorted(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(_junit_xml(skipped=[A], passed=[D, B], failed=[C], errored=[("tests.test_e", "test_five")]))
    assert G.ran_and_passed_from_junit(p) == [_id(B), _id(D)]


# new-behaviour
def test_helper_on_a_junit_without_passed_testcases_is_an_empty_list(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(_junit_xml(skipped=[A], failed=[B]))
    assert G.ran_and_passed_from_junit(p) == []
    p.write_text("<testsuites><testsuite/></testsuites>")
    assert G.ran_and_passed_from_junit(p) == []


# new-behaviour
def test_helper_ids_are_classname_double_colon_name_like_the_skipped_helper(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(_junit_xml(skipped=[A], passed=[B]))
    assert G.skipped_from_junit(p) == [_id(A)]
    assert G.ran_and_passed_from_junit(p) == [_id(B)]


# invariant
def test_skipped_helper_ignores_passed_failed_and_errored_testcases(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(_junit_xml(skipped=[A], passed=[B], failed=[C], errored=[D]))
    assert G.skipped_from_junit(p) == [_id(A)]
    assert G.skipped_from_junit(tmp_path / "missing.xml") is None


# ------------------------------------------------------------------ run: S == W
# new-behaviour (the key is absent at the baseline)
def test_equal_skip_list_and_baseline_passes_with_an_empty_baseline_skips_ran(env):
    doc = _gate(env, [A, B], skipped=[A, B])
    assert doc["verdict"] == "PASS" and doc["problems"] == []
    assert doc["skipped_tests"] == [_id(A), _id(B)]
    assert doc["baseline_skips_ran"] == []


# new-behaviour
def test_empty_baseline_and_no_skips_passes_with_an_empty_baseline_skips_ran(env):
    doc = _gate(env, [], skipped=[], passed=[A])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_ran"] == []


# new-behaviour: an unrelated passed test (not in the baseline) is never recorded
def test_a_passed_test_outside_the_baseline_is_not_recorded(env):
    doc = _gate(env, [A], skipped=[A], passed=[B, C])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_ran"] == []


# ------------------------------------------------------------------ run: W - S ran and passed
# reproduces-failure: at the baseline this is a FAIL ("skip list != baseline"); after the change it is a PASS
def test_a_baseline_skip_that_ran_and_passed_no_longer_fails_the_gate(env):
    doc = _gate(env, [A, B], skipped=[], passed=[A, B])
    assert doc["verdict"] == "PASS" and doc["problems"] == []


# new-behaviour
def test_a_baseline_skip_that_ran_and_passed_is_recorded_sorted(env):
    doc = _gate(env, [B, A], skipped=[], passed=[B, A, C])
    assert doc["verdict"] == "PASS"
    assert doc["baseline_skips_ran"] == [_id(A), _id(B)]
    assert doc["skipped_tests"] == []  # skipped_tests unchanged: only what the junit skipped


# new-behaviour
def test_a_partial_overlap_records_only_the_baseline_entries_that_ran(env):
    doc = _gate(env, [A, B, C], skipped=[B], passed=[A, C])
    assert doc["verdict"] == "PASS"
    assert doc["skipped_tests"] == [_id(B)]
    assert doc["baseline_skips_ran"] == [_id(A), _id(C)]


# new-behaviour
def test_baseline_blank_lines_are_ignored(env):
    (env["baselines"] / "mlx-serve.skips.txt").write_text(f"\n{_id(A)}\n   \n\n")
    r = JunitRunner(skipped=[], passed=[A])
    doc = json.loads(Path(G.run("mlx-serve", env["sha"], live=env["live"], gate_dir=env["gate"], baselines=env["baselines"],
                                runner=r, busy=lambda: [], dirty=r.dirty, artifacts=lambda d: True)).read_text())
    assert doc["verdict"] == "PASS" and doc["baseline_skips_ran"] == [_id(A)]


# new-behaviour: the id is classname AND name; a same-named test in another class is not the baseline entry
def test_a_passed_test_with_the_same_name_in_another_class_does_not_count(env):
    other = ("tests.test_other", A[1])
    doc = _gate(env, [A], skipped=[], passed=[other])
    assert doc["verdict"] == "FAIL"
    assert f"baseline skip neither skipped nor passed: ['{_id(A)}']" in _problems(doc)


# ------------------------------------------------------------------ run: W - S neither skipped nor passed
# new-behaviour
def test_a_baseline_entry_absent_from_the_junit_fails_with_the_new_problem(env):
    doc = _gate(env, [A, B], skipped=[], passed=[A])
    assert doc["verdict"] == "FAIL"
    assert f"baseline skip neither skipped nor passed: ['{_id(B)}']" in _problems(doc)


# new-behaviour
def test_the_new_problem_lists_every_such_entry_sorted(env):
    doc = _gate(env, [D, C, A], skipped=[], passed=[A])
    assert doc["verdict"] == "FAIL"
    assert f"baseline skip neither skipped nor passed: ['{_id(C)}', '{_id(D)}']" in _problems(doc)


# new-behaviour
def test_a_baseline_entry_that_failed_fails_the_gate_even_with_pytest_rc_0(env):
    doc = _gate(env, [A], skipped=[], failed=[A])
    assert doc["verdict"] == "FAIL"
    assert f"baseline skip neither skipped nor passed: ['{_id(A)}']" in _problems(doc)


# new-behaviour
def test_a_baseline_entry_that_errored_fails_the_gate_even_with_pytest_rc_0(env):
    doc = _gate(env, [A], skipped=[], errored=[A])
    assert doc["verdict"] == "FAIL"
    assert f"baseline skip neither skipped nor passed: ['{_id(A)}']" in _problems(doc)


# new-behaviour: one failing entry among passing ones still fails, naming only the failing one
def test_one_failed_entry_among_ran_and_passed_ones_fails_naming_only_it(env):
    doc = _gate(env, [A, B], skipped=[], passed=[A], failed=[B])
    assert doc["verdict"] == "FAIL"
    assert f"baseline skip neither skipped nor passed: ['{_id(B)}']" in _problems(doc)
    assert _id(A) not in _problems(doc).split("neither skipped nor passed:")[1]


# invariant: today's behaviour for a baseline entry that is simply gone (renamed / not collected) is a FAIL
def test_a_baseline_entry_missing_from_the_junit_fails(env):
    doc = _gate(env, [A], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL" and doc["problems"]


# ------------------------------------------------------------------ run: S - W
# invariant (the existing test_a_skip_list_unequal_to_the_baseline_fails stays green)
def test_an_unbaselined_skip_fails_with_todays_message(env):
    doc = _gate(env, [], skipped=[A])
    assert doc["verdict"] == "FAIL"
    assert f"skip list != baseline: +['{_id(A)}'] -[]" in _problems(doc)
    assert doc["skipped_tests"] == [_id(A)]


# invariant: an extra skip fails even when another baseline entry ran and passed
def test_an_unbaselined_skip_fails_even_if_a_baseline_entry_ran_and_passed(env):
    doc = _gate(env, [B], skipped=[A], passed=[B])
    assert doc["verdict"] == "FAIL"
    assert f"skip list != baseline: +['{_id(A)}']" in _problems(doc)


# invariant: an extra skip fails even when the baseline entry it replaces is absent
def test_an_unbaselined_skip_with_an_absent_baseline_entry_fails_with_the_skip_list_message(env):
    doc = _gate(env, [B], skipped=[A])
    assert doc["verdict"] == "FAIL"
    assert f"skip list != baseline: +['{_id(A)}']" in _problems(doc)


# ------------------------------------------------------------------ run: unchanged around the rule
# invariant: no baseline file keeps today's problem
def test_no_baseline_file_keeps_todays_problem(env):
    doc = _gate(env, None, skipped=[], passed=[A])
    assert doc["verdict"] == "FAIL"
    assert "no skip baseline" in _problems(doc)
    assert "neither skipped nor passed" not in _problems(doc)


# invariant: a failed earlier step stops the run before any skip rule is applied
def test_a_failing_pytest_step_fails_without_the_skip_rule(env):
    doc = _gate(env, [A], rcs={"junitxml": 1}, skipped=[], passed=[A])
    assert doc["verdict"] == "FAIL"
    assert any("pytest" in p for p in doc["problems"])
    assert "neither skipped nor passed" not in _problems(doc)


# invariant: the receipt of a PASS still has the full step list
def test_a_pass_with_ran_skips_keeps_the_six_steps_and_the_scratch_is_removed(env):
    doc = _gate(env, [A], skipped=[], passed=[A])
    assert [s["name"] for s in doc["steps"]] == ["clone", "sync", "ruff-check", "ruff-format", "pytest", "build"]
    assert not list((env["gate"] / "scratch").glob("*"))


# invariant: policy digest is a function of its inputs only, not of the junit content
def test_the_policy_digest_does_not_depend_on_what_ran(env):
    d1 = _gate(env, [A], skipped=[A])["policy_digest"]
    d2 = _gate(env, [A], skipped=[], passed=[A])["policy_digest"]
    assert d1 == d2
