"""Multi-language grading for the opencode agentic probe (`run_opencode_probe.py`).

WHY THIS EXISTS. `_grade_python` was the only wired grader; the M9 blocker is grading the other
four polyglot languages (go, rust, java, javascript), all of which run INSIDE the `aider-benchmark`
docker image — the only place all five toolchains exist at pinned versions. These tests mock
`subprocess.run` throughout (never talk to a real docker daemon or a real model), per the campaign
rule against calling localhost:8000/8091 from a benchmark-tooling test and against relying on a
docker image being present in CI.

Three things get dedicated coverage because they are the actual hazards named in the task, not
incidental: (1) the `-v` mount is always an ABSOLUTE host path — a relative one silently becomes an
empty named volume rather than erroring; (2) `.meta/config.json` resolution correctly handles
nested solution/test paths (java, rust) where the old flat-filename heuristic breaks; (3) a
rewritten test file is scored as a failure and never reaches the docker grader.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # benchmark/ on sys.path
import run_opencode_probe as P


# --------------------------------------------------------------------------- _solution_and_test

def test_meta_config_resolves_nested_java_solution_and_test(tmp_path):
    """java's solution/test live under src/main/java and src/test/java — a flat filename glob
    can't find either; .meta/config.json names them explicitly."""
    src = tmp_path / "src_orig"
    (src / ".meta").mkdir(parents=True)
    (src / ".meta" / "config.json").write_text(json.dumps({
        "files": {
            "solution": ["src/main/java/Series.java"],
            "test": ["src/test/java/SeriesTest.java"],
            "example": [".meta/src/reference/java/Series.java"],
        }
    }))
    staged = tmp_path / "staged"  # .meta already stripped, as _prepare would do
    (staged / "src/main/java").mkdir(parents=True)
    (staged / "src/test/java").mkdir(parents=True)
    (staged / "src/main/java/Series.java").write_text("class Series {}")
    (staged / "src/test/java/SeriesTest.java").write_text("class SeriesTest {}")

    sol, test = P._solution_and_test(staged, src, "java")

    assert sol == staged / "src/main/java/Series.java"
    assert test == staged / "src/test/java/SeriesTest.java"


def test_meta_config_excludes_cargo_toml_from_rust_solution(tmp_path):
    """rust's config.json lists BOTH src/lib.rs and Cargo.toml under "solution" — Cargo.toml is a
    build manifest, not something the model should be told to edit as "the solution"; aider's own
    harness excludes it the same way."""
    src = tmp_path / "src_orig"
    (src / ".meta").mkdir(parents=True)
    (src / ".meta" / "config.json").write_text(json.dumps({
        "files": {"solution": ["src/lib.rs", "Cargo.toml"], "test": ["tests/decimal.rs"]}
    }))
    staged = tmp_path / "staged"
    (staged / "src").mkdir(parents=True)
    (staged / "tests").mkdir(parents=True)
    (staged / "src/lib.rs").write_text("pub struct Decimal;")
    (staged / "Cargo.toml").write_text("[package]\nname='decimal'")
    (staged / "tests/decimal.rs").write_text("#[test] fn it_works() {}")

    sol, test = P._solution_and_test(staged, src, "rust")

    assert sol == staged / "src/lib.rs"
    assert test == staged / "tests/decimal.rs"


def test_falls_back_to_heuristic_when_no_meta_config(tmp_path):
    """python/go exercises with no config.json (or a test harness fixture without one) still
    resolve via the old flat-filename heuristic — the pre-existing, still-correct behavior."""
    src = tmp_path / "src_orig"
    src.mkdir()
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "affine_cipher.py").write_text("def encode(): ...")
    (staged / "affine_cipher_test.py").write_text("def test_encode(): ...")

    sol, test = P._solution_and_test(staged, src, "python")

    assert sol == staged / "affine_cipher.py"
    assert test == staged / "affine_cipher_test.py"


def test_falls_back_when_config_names_files_that_dont_exist_in_staged_copy(tmp_path):
    """Defensive: if config.json is malformed or out of sync with the staged copy, fall through
    to the heuristic rather than returning a Path to a file that isn't there."""
    src = tmp_path / "src_orig"
    (src / ".meta").mkdir(parents=True)
    (src / ".meta" / "config.json").write_text(json.dumps({
        "files": {"solution": ["nope.py"], "test": ["nope_test.py"]}
    }))
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "affine_cipher.py").write_text("def encode(): ...")
    (staged / "affine_cipher_test.py").write_text("def test_encode(): ...")

    sol, test = P._solution_and_test(staged, src, "python")

    assert sol == staged / "affine_cipher.py"
    assert test == staged / "affine_cipher_test.py"


# --------------------------------------------------------------------------- _prepare / .meta exclusion

def test_prepare_excludes_meta_directory(tmp_path):
    """.meta holds the reference solution (example.py etc.) — copying it into the model's
    workspace would let the probe measure nothing, per the module's INTEGRITY section."""
    src = tmp_path / "exercise"
    (src / ".meta").mkdir(parents=True)
    (src / ".meta" / "example.py").write_text("def encode(): return 'the answer'")
    (src / "affine_cipher.py").write_text("def encode(): ...")

    dst = tmp_path / "staged"
    P._prepare(src, dst)

    assert (dst / "affine_cipher.py").exists()
    assert not (dst / ".meta").exists()


# --------------------------------------------------------------------------- _docker_grade

def test_docker_grade_refuses_relative_path_without_touching_subprocess(tmp_path, monkeypatch):
    """The documented trap: a relative -v mount silently becomes an empty named volume instead of
    erroring. Guard against ever reaching subprocess.run with one."""
    def _boom(*a, **kw):
        raise AssertionError("must not shell out for a relative path")
    monkeypatch.setattr(subprocess, "run", _boom)

    passed, tail = P._docker_grade(Path("relative/dir"), ["go", "test"], docker_ok=True)

    assert passed is False
    assert "absolute" in tail


def test_docker_grade_skips_when_docker_unavailable_without_touching_subprocess(tmp_path, monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("must not shell out when docker_ok is False")
    monkeypatch.setattr(subprocess, "run", _boom)

    passed, tail = P._docker_grade(tmp_path, ["go", "test"], docker_ok=False)

    assert passed is False
    assert "docker unavailable" in tail


def test_docker_grade_mounts_absolute_path_and_uses_pinned_image(tmp_path, monkeypatch):
    captured = {}

    def _fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    passed, tail = P._docker_grade(tmp_path, ["go", "test", "./..."], docker_ok=True)

    assert passed is True
    cmd = captured["cmd"]
    assert cmd[0:3] == ["docker", "run", "--rm"]
    assert f"{tmp_path}:/work" in cmd
    assert cmd[cmd.index("-w") + 1] == "/work"
    assert P._AIDER_IMAGE in cmd
    assert cmd[-3:] == ["go", "test", "./..."]


def test_docker_grade_fails_on_nonzero_returncode(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw:
                        subprocess.CompletedProcess(cmd, returncode=1, stdout="FAIL", stderr=""))

    passed, tail = P._docker_grade(tmp_path, ["go", "test"], docker_ok=True)

    assert passed is False
    assert "FAIL" in tail


def test_docker_grade_handles_timeout_gracefully(tmp_path, monkeypatch):
    def _timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout", 300))
    monkeypatch.setattr(subprocess, "run", _timeout)

    passed, tail = P._docker_grade(tmp_path, ["cargo", "test"], docker_ok=True, timeout=600)

    assert passed is False
    assert "timed out" in tail


def test_docker_grade_handles_missing_docker_binary_gracefully(tmp_path, monkeypatch):
    def _missing(cmd, **kw):
        raise FileNotFoundError("docker")
    monkeypatch.setattr(subprocess, "run", _missing)

    passed, tail = P._docker_grade(tmp_path, ["go", "test"], docker_ok=True)

    assert passed is False
    assert "not installed" in tail


# --------------------------------------------------------------------------- per-language commands

def _capturing_run(captured):
    """subprocess.run stand-in that records the invoking cmd and reports success. (Not a bare
    lambda with `dict.setdefault(...) or CompletedProcess(...)`: setdefault returns the cmd list,
    which is truthy, so `or` would short-circuit and hand the caller a list instead of a result.)"""
    def _run(cmd, **kw):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0)
    return _run


def test_grade_go_runs_go_test_ellipsis(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(subprocess, "run", _capturing_run(captured))

    P._grade_go(tmp_path, tmp_path / "x_test.go", docker_ok=True)

    assert captured["cmd"][-3:] == ["go", "test", "./..."]


def test_grade_rust_includes_ignored_cases(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(subprocess, "run", _capturing_run(captured))

    P._grade_rust(tmp_path, tmp_path / "x.rs", docker_ok=True)

    assert captured["cmd"][-4:] == ["cargo", "test", "--", "--include-ignored"]


def test_grade_javascript_uses_the_aider_npm_test_script(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(subprocess, "run", _capturing_run(captured))

    P._grade_javascript(tmp_path, tmp_path / "x.spec.js", docker_ok=True)

    assert captured["cmd"][-2:] == ["bash", "/aider/benchmark/npm-test.sh"]


def test_grade_java_strips_disabled_annotations_before_grading(tmp_path, monkeypatch):
    """Exercism java tests ship every case but the first @Disabled — ungraded, the suite would
    trivially 'pass' on one enabled test. aider's own harness strips this; so must this grader."""
    test_file = tmp_path / "SeriesTest.java"
    test_file.write_text(
        "class SeriesTest {\n"
        "    @Test\n"
        "    void first() {}\n\n"
        "    @Disabled(\"Remove to run test\")\n"
        "    @Test\n"
        "    void second() {}\n"
    )
    captured = {}
    monkeypatch.setattr(subprocess, "run", _capturing_run(captured))

    P._grade_java(tmp_path, test_file, docker_ok=True)

    content = test_file.read_text()
    assert "@Disabled" not in content
    assert "void second" in content  # the test body itself is untouched, only the annotation goes
    assert "gradlew test" in captured["cmd"][-1]


def test_grade_java_command_runs_gradlew_test(tmp_path, monkeypatch):
    test_file = tmp_path / "SeriesTest.java"
    test_file.write_text("class SeriesTest {}")
    captured = {}
    monkeypatch.setattr(subprocess, "run", _capturing_run(captured))

    P._grade_java(tmp_path, test_file, docker_ok=True)

    shell_arg = captured["cmd"][-1]
    assert "gradlew test" in shell_arg
    assert "chmod +x gradlew" in shell_arg


# --------------------------------------------------------------------------- _grade_result (tamper detection)

def test_grade_result_scores_tampered_test_file_as_failure_without_grading(tmp_path):
    """A model that rewrites the test file can make any suite pass by construction — this must be
    caught BEFORE the grader ever runs, and must never call it."""
    test_file = tmp_path / "x_test.py"
    test_file.write_text("def test_x(): assert True  # model replaced this")

    def _grade_must_not_run(work, test):
        raise AssertionError("grader must not be invoked on a tampered test file")

    passed, tail, test_modified = P._grade_result(
        tmp_path, test_file, test_before="def test_x(): assert do_the_real_thing()",
        changed=True, grade=_grade_must_not_run)

    assert passed is False
    assert test_modified is True
    assert "MODIFIED" in tail


def test_grade_result_scores_untouched_solution_as_failure_without_grading(tmp_path):
    test_file = tmp_path / "x_test.py"
    original = "def test_x(): assert True"
    test_file.write_text(original)

    def _grade_must_not_run(work, test):
        raise AssertionError("grader must not be invoked when the solution was never touched")

    passed, tail, test_modified = P._grade_result(
        tmp_path, test_file, test_before=original, changed=False, grade=_grade_must_not_run)

    assert passed is False
    assert test_modified is False
    assert "untouched" in tail


def test_grade_result_grades_when_untampered_and_changed(tmp_path):
    test_file = tmp_path / "x_test.py"
    original = "def test_x(): assert True"
    test_file.write_text(original)
    calls = []

    def _grade(work, test):
        calls.append((work, test))
        return True, "1 passed"

    passed, tail, test_modified = P._grade_result(
        tmp_path, test_file, test_before=original, changed=True, grade=_grade)

    assert passed is True
    assert tail == "1 passed"
    assert test_modified is False
    assert calls == [(tmp_path, test_file)]


# --------------------------------------------------------------------------- CLI language gate

def test_unsupported_lang_exits_with_clear_message(monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["run_opencode_probe.py", "--model", "m", "--items", "x", "--lang", "cobol"])
    try:
        P.main()
        raised = False
    except SystemExit as e:
        raised = True
        msg = str(e)
    assert raised
    assert "cobol" in msg
    assert "unsupported" in msg


def test_scrub_pii_replaces_home_and_workdir(monkeypatch):
    # The repo is PUBLIC: rows must not carry absolute home paths (the pre-commit
    # piicheck rejects them — M3's first commit attempt was blocked by exactly this).
    monkeypatch.setenv("STACK_WORKDIR", "/Users/someone/ws/mlx_local_stack_workdir")  # allow-pii-pattern
    monkeypatch.setattr(P.os.path, "expanduser", lambda p: "/Users/someone" if p == "~" else p)  # allow-pii-pattern
    raw = ("Read /Users/someone/ws/mlx_local_stack_workdir/scratch/octmp/oc-x/y failed; "  # allow-pii-pattern
           "also /Users/someone/other/path")  # allow-pii-pattern
    out = P._scrub_pii(raw)
    assert "/Users/someone" not in out
    assert "$STACK_WORKDIR/scratch/octmp/oc-x/y" in out
    assert "$HOME/other/path" in out
