"""M62 fixed-denominator grading and protected inputs."""

import json
import subprocess
from pathlib import Path
import pytest
from bench import structured_grade as sg
from bench.token_turn_gate import TransportAbort


def test_go_leaves_panic_mid_suite_and_build_error():
    def line(action, name=None):
        return (
            json.dumps(
                dict(Action=action, Package="pkg", **({"Test": name} if name else {}))
            )
            + "\n"
        )

    report = (
        line("run", "TestA")
        + line("pass", "TestA/sub")
        + line("pass", "TestA")
        + line("run", "TestB")
    )
    result = sg.parse_go(report, 1)
    assert result.passing == {("pkg", "TestA/sub")}
    assert (
        result.failing({("pkg", "TestA/sub"), ("pkg", "TestB"), ("pkg", "TestC")}) == 2
    )
    result = sg.parse_go(
        "", 1, stderr="# pkg\n./a.go: syntax error\nFAIL pkg [build failed]"
    )
    assert result.failing({("pkg", "TestA")}) == 1


def test_python_collection_error_and_tuple_ids():
    result = sg.parse_python(
        '<testsuites><testsuite><testcase classname="x" name="test_ok"/>'
        '<testcase classname="" name="a_test"><error message="collection"/></testcase>'
        "</testsuite></testsuites>",
        2,
        "a_test.py",
    )
    assert result.passing == {("a_test.py", "x", "test_ok")}
    assert (
        result.failing(
            {("a_test.py", "x", "test_ok"), ("a_test.py", "x", "test_other")}
        )
        == 1
    )


@pytest.mark.parametrize("kind", ["go", "python"])
def test_grader_timeout_counts_unreported(kind):
    result = (
        sg.parse_go("", None, timed_out=True)
        if kind == "go"
        else sg.parse_python("", None, "a_test.py", timed_out=True)
    )
    assert result.failing({("a",), ("b",)}) == 2


@pytest.mark.parametrize(
    "kind,rc,err",
    [
        ("go", 125, ""),
        ("go", 126, ""),
        ("go", 127, ""),
        ("go", 1, "Cannot connect to the Docker daemon"),
        ("go", 1, "Unable to find image"),
        ("go", 1, ""),
        ("python", 1, ""),
    ],
)
def test_infrastructure_failure_aborts(kind, rc, err):
    with pytest.raises(TransportAbort):
        if kind == "go":
            sg.parse_go("", rc, stderr=err)
        else:
            sg.parse_python("", rc, "test.py", stderr=err)


def test_snapshots_consistency_exclusions_and_symlinks(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.py").write_text("a")
    for name in [".git", "__pycache__", ".pytest_cache"]:
        (work / name).mkdir()
        (work / name / "ignored").write_text("noise")
    (work / "a.pyc").write_text("noise")
    assert set(sg.manifest(work)) == {"a.py"}
    with sg.snapshot(work, tmp_path, boundary=3) as snap:
        assert snap.boundary == 3 and snap.manifest == sg.manifest(snap.path)
    (work / "link").symlink_to(work / "a.py")
    with sg.snapshot(work, tmp_path, boundary=4) as snap:
        assert snap is None
    (work / "link").unlink()
    real = sg.manifest
    calls = []

    def race(path):
        calls.append(path)
        return {"a.py": str(len(calls))}

    monkeypatch.setattr(sg, "manifest", race)
    with sg.snapshot(work, tmp_path, boundary=5) as snap:
        assert snap is None
    assert len(calls) <= 9


@pytest.mark.parametrize(
    "name",
    [
        "conftest.py",
        "pytest.ini",
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
        "sitecustomize.py",
        "usercustomize.py",
        "evil.pth",
        "nested/conftest.py",
    ],
)
def test_each_python_forbidden_addition(tmp_path, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    assert sg.tampered(tmp_path, {}, {}, "python")


@pytest.mark.parametrize(
    "name,text",
    [
        ("go.mod", ""),
        ("go.work", ""),
        ("vendor/p/a.go", ""),
        ("helper.go", "package p\nfunc TestMain(m *testing.M) {}"),
    ],
)
def test_each_go_forbidden_addition(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    assert sg.tampered(tmp_path, {}, {}, "go")


def test_empty_vendor_and_testmain_in_existing_solution(tmp_path):
    (tmp_path / "solution.go").write_text("package p")
    prepared = sg.manifest(tmp_path)
    (tmp_path / "vendor").mkdir()
    assert sg.tampered(tmp_path, {}, prepared, "go")
    (tmp_path / "vendor").rmdir()
    (tmp_path / "solution.go").write_text("package p\nfunc TestMain(m *testing.M) {}")
    assert sg.tampered(tmp_path, {}, prepared, "go")


def test_snapshot_retains_forbidden_empty_directory(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "vendor").mkdir()
    with sg.snapshot(work, tmp_path, boundary=1) as snap:
        assert sg.tampered(snap.path, {}, {}, "go")


@pytest.mark.parametrize(
    "name", ["cases_test.go", "interface.go", "common.go", "go.mod"]
)
def test_protected_edit_delete_and_helper_allowed(tmp_path, name):
    path = tmp_path / name
    path.write_text("original")
    prepared = sg.manifest(tmp_path)
    (tmp_path / "helper.go").write_text("package p\nfunc helper() {}")
    assert not sg.tampered(tmp_path, prepared, prepared, "go")
    path.write_text("changed")
    assert sg.tampered(tmp_path, prepared, prepared, "go")
    path.unlink()
    assert sg.tampered(tmp_path, prepared, prepared, "go")


def test_grader_command_trusted_reports_and_missing_interpreter(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        report = Path(
            next(x.split("=", 1)[1] for x in cmd if x.startswith("--junitxml="))
        )
        assert not report.is_relative_to(work)
        report.write_text(
            '<testsuites><testsuite><testcase classname="x" name="ok"/></testsuite></testsuites>'
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    result = sg.grade("python", work, "official_test.py", private, run=run)
    cmd = calls[0][0]
    assert "--rootdir=" + str(work) in cmd and "no:cacheprovider" in cmd
    assert "official_test.py" in cmd and result.passing

    def missing(*a, **kw):
        raise FileNotFoundError("interpreter")

    with pytest.raises(TransportAbort):
        sg.grade("python", work, "official_test.py", private, run=missing)


def test_go_container_limits_registration_and_oom(tmp_path):
    class Guard:
        grader_oom = False
        grader_mem_kill = False

        def register_container(self, name):
            self.name = name

        def container_oom(self, name):
            return True

        def remove_container(self, name):
            self.removed = name

    guard = Guard()

    def run(cmd, **kw):
        assert guard.name in cmd and "--memory" in cmd and "--memory-swap" in cmd
        assert str(tmp_path.resolve()) + ":/work" in cmd
        return subprocess.CompletedProcess(cmd, 137, "", "")

    result = sg.grade("go", tmp_path, "a_test.go", tmp_path, run=run, guard=guard)
    assert result.grader_oom and not result.passing and guard.removed == guard.name


def test_go_full_report_streams_to_file(tmp_path):
    class Guard:
        grader_mem_kill = False

        def register_container(self, name):
            pass

        def container_oom(self, name):
            return False

        def remove_container(self, name):
            pass

    def run(cmd, **kw):
        assert "capture_output" not in kw
        assert (
            hasattr(kw["stdout"], "write")
            and Path(kw["stdout"].name).parent != tmp_path
        )
        kw["stdout"].write(
            json.dumps(dict(Action="pass", Package="p", Test="TestA")) + "\n"
        )
        return subprocess.CompletedProcess(cmd, 0, None, None)

    result = sg.grade("go", tmp_path, "test.go", tmp_path, guard=Guard(), run=run)
    assert result.passing == {("p", "TestA")}


def test_go_real_build_failure_plain_stdout_line():
    """go1.21 (aider-benchmark image) prints `FAIL\t<pkg> [build failed]` as PLAIN TEXT on stdout under -json
    (captured 2026-10-10 on an undefined-symbol stub); errors go to stderr. A build failure counts all failing."""
    from bench import structured_grade as sg
    r = sg.parse_go("FAIL\talphametics [build failed]\n", 1,
                    stderr="# alphametics [alphametics.test]\n./alphametics_test.go:11:14: undefined: Solve\n")
    assert r.passing == set()
    r = sg.parse_go("FAIL\tpkg [setup failed]\n", 1, stderr="")
    assert r.passing == set()
    with pytest.raises(sg.TransportAbort, match="malformed Go report"):
        sg.parse_go("random noise\n", 1, stderr="")
