"""M65 tg2 grader (`bench/tg2_grade.py`, version m65-tg2-v1): parsers, phase-typed grading, outcome classes, tamper
checks, skip-form refusal. Unit tests use a fake `run` (no docker); docker-marked integration tests grade real
reference / stub trees inside the built `tg2-grader` image and are skipped (with the reason) when docker, the image or
the polyglot corpus is absent."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from bench import structured_grade as sg
from bench import tg2_grade as tg
from bench.token_turn_gate import TransportAbort

IMG = "sha256:" + "ab" * 32


# --------------------------------------------------------------------------------------------------------- parsers
RUST_TWO_BINARIES = """\
   Compiling x v0.1.0
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.4s
     Running unittests src/lib.rs (target/debug/deps/forth-aaa)

running 2 tests
test tests::basic ... ok
test tests::shared ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/forth.rs (target/debug/deps/forth-bbb)

running 3 tests
test shared ... ok
test tests::shared ... FAILED
test alloc ... ignored, slow

failures:

---- tests::shared stdout ----
test fake_leaf ... ok
thread 'tests::shared' panicked at src/lib.rs:3:5

test result: FAILED. 1 passed; 1 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.00s

   Doc-tests forth

running 1 test
test src/lib.rs - Foo (line 5) ... ok
"""


def test_rust_leaf_ids_are_binary_qualified_and_collisions_do_not_merge():
    leaves = tg.parse_rust(RUST_TWO_BINARIES)
    assert leaves["unittests src/lib.rs::tests::shared"] is True
    assert leaves["tests/forth.rs::tests::shared"] is False
    assert leaves["tests/forth.rs::shared"] is True
    assert leaves["tests/forth.rs::alloc"] is False   # ignored under --include-ignored means it did not run: failed
    assert leaves["doc-tests forth::src/lib.rs - Foo (line 5)"] is True
    assert "tests/forth.rs::fake_leaf" not in leaves and "fake_leaf" not in leaves  # indented/captured output only


def test_rust_duplicate_name_in_one_binary_failure_wins():
    text = "     Running tests/a.rs (x)\nrunning 2 tests\ntest dup ... ok\ntest dup ... FAILED\n"
    assert tg.parse_rust(text) == {"tests/a.rs::dup": False}


def test_rust_no_test_activity_is_a_report_error():
    with pytest.raises(tg.ReportError):
        tg.parse_rust("warning: nothing\n")


JUNIT = """<?xml version="1.0"?>
<testsuites><testsuite name="S" tests="5">
<testcase classname="com.A" name="ok()" time="0.1"/>
<testcase classname="com.A" name="bad()"><failure message="m">x</failure></testcase>
<testcase classname="com.A" name="err()"><error message="m">x</error></testcase>
<testcase classname="com.A" name="skip()"><skipped/></testcase>
<testcase classname="com.A" name="dup()"/>
<testcase classname="com.A" name="dup()"><failure message="m"/></testcase>
</testsuite></testsuites>"""


def test_junit_failure_error_skipped_and_duplicates():
    leaves = tg.parse_junit(JUNIT)
    assert leaves == {"com.A#ok()": True, "com.A#bad()": False, "com.A#err()": False, "com.A#skip()": False,
                      "com.A#dup()": False}


def test_junit_bare_testsuite_root_and_merge_across_files():
    one = '<testsuite name="a"><testcase classname="A" name="t"/></testsuite>'
    two = '<testsuite name="b"><testcase classname="A" name="t"><failure/></testcase></testsuite>'
    merged = tg.merge_leaves(tg.parse_junit(one), tg.parse_junit(two))
    assert merged == {"A#t": False}


@pytest.mark.parametrize("bad", ["", "<testsuite", "not xml", "<testsuites/>"])
def test_junit_malformed_or_empty_is_a_report_error(bad):
    with pytest.raises(tg.ReportError):
        tg.parse_junit(bad)


def jest_doc(results):
    return json.dumps({"success": True, "testResults": results})


def test_jest_leaf_ids_relative_duplicates_and_statuses():
    doc = jest_doc([
        {"name": "/work/affine/a.spec.js", "status": "failed", "message": "", "assertionResults": [
            {"fullName": "x encode", "status": "passed"},
            {"fullName": "x encode", "status": "failed"},          # duplicate event: failure wins
            {"fullName": "x dup ok", "status": "passed"},
            {"fullName": "x dup ok", "status": "passed"},
            {"fullName": "x pending", "status": "pending"},
            {"fullName": "x todo", "status": "todo"},
            {"fullName": "x skipped", "status": "skipped"},
        ]},
        {"name": "/work/affine/b.spec.js", "status": "passed", "assertionResults": [
            {"fullName": "x encode", "status": "passed"}]},
    ])
    leaves = tg.parse_jest(doc, "/work/affine")
    assert leaves == {"a.spec.js::x encode": False, "a.spec.js::x dup ok": True, "a.spec.js::x pending": False,
                      "a.spec.js::x todo": False, "a.spec.js::x skipped": False, "b.spec.js::x encode": True}


def test_jest_suite_that_failed_to_run_is_a_failed_leaf():
    doc = jest_doc([{"name": "/work/affine/a.spec.js", "status": "failed", "message": "SyntaxError",
                     "assertionResults": []}])
    assert tg.parse_jest(doc, "/work/affine") == {"a.spec.js::<suite failed to run>": False}


@pytest.mark.parametrize("bad", ["", "{", "[]", json.dumps({"testResults": "x"}), json.dumps({"testResults": []})])
def test_jest_malformed_is_a_report_error(bad):
    with pytest.raises(tg.ReportError):
        tg.parse_jest(bad, "/work/x")


def test_cpp_junit_uses_classname_hash_name():
    xml = ('<testsuites><testsuite name="g"><testcase classname="g.global" name="a" status="run"/>'
           '<testcase classname="g.global" name="b"><failure message="m"/></testcase></testsuite></testsuites>')
    assert tg.parse_junit(xml) == {"g.global#a": True, "g.global#b": False}


# --------------------------------------------------------------------------------------------- fake docker harness
class Plan:
    """Per-step scripted behaviour: rc, stdout/stderr text, files written into the report dir or the work tree."""

    def __init__(self, **steps):
        self.steps = steps

    def get(self, step):
        return self.steps.get(step, {})


def step_of(cmd):
    if cmd[:3] == ["docker", "image", "inspect"]:
        return "image"
    script = cmd[-1] if cmd[-2:-1] == ["-c"] else " ".join(cmd[-3:])
    if cmd[-1] == "true":
        return "launch"
    if any(k in script for k in ("--no-run", "compileTestJava", "--listTests", "cmake -S")):
        return "compile"
    return "execute"


def mounts(cmd):
    out = {}
    for i, a in enumerate(cmd):
        if a == "-v":
            host, _, target = cmd[i + 1].rpartition(":")
            out[target] = host
    return out


class FakeGuard:
    grader_mem_kill = False

    def __init__(self, plan, mem_kill_step=None):
        self.plan, self.names, self.registered, self.removed, self.calls = plan, {}, [], [], []
        self.n = 0
        self.mem_kill_step = mem_kill_step
        self.step_by_name = {}

    def container_name(self):
        self.n += 1
        return f"fake-{self.n}"

    def register_container(self, name):
        self.registered.append(name)

    def container_oom(self, name):
        return bool(self.plan.get(self.step_by_name.get(name, "?")).get("oom"))

    def remove_container(self, name):
        self.removed.append(name)

    def run_grader(self, cmd, **kw):
        step = step_of(cmd)
        if "--name" in cmd:
            self.step_by_name[cmd[cmd.index("--name") + 1]] = step
        self.calls.append((step, cmd))
        spec = self.plan.get(step)
        if step in ("compile", "execute") and spec.get("mem_kill"):
            self.grader_mem_kill = True
        if spec.get("timeout"):
            kw["stdout"].write(spec.get("stdout", ""))
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 1)
        kw["stdout"].write(spec.get("stdout", ""))
        kw["stderr"].write(spec.get("stderr", ""))
        m = mounts(cmd)
        for rel, data in spec.get("report", {}).items():
            (Path(m["/report"]) / rel).write_bytes(data if isinstance(data, bytes) else data.encode())
        for rel, data in spec.get("work", {}).items():
            p = next(Path(h) for t, h in m.items() if t.startswith("/work/")) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else data.encode())
        if step == "image":
            kw["stdout"].write(spec.get("image_id", IMG) + "\n")
        return subprocess.CompletedProcess(cmd, spec.get("rc", 0), None, None)


def basic_plan(lang, *, exec_rc=0, **over):
    ok = {
        "rust": dict(stdout="     Running tests/t.rs (x)\nrunning 2 tests\ntest a ... ok\ntest b ... ok\n"),
        "java": dict(work={"build/test-results/test/TEST-T.xml":
                           '<testsuite><testcase classname="T" name="a()"/><testcase classname="T" name="b()"/></testsuite>'}),
        "javascript": dict(report={"jest.json": jest_doc([{"name": "/work/slug/t.spec.js", "status": "passed",
                                                            "assertionResults": [{"fullName": "a", "status": "passed"},
                                                                                 {"fullName": "b", "status": "passed"}]}])}),
        "cpp": dict(report={"cpp.xml": '<testsuites><testsuite name="s"><testcase classname="s.global" name="a"/>'
                                       '<testcase classname="s.global" name="b"/></testsuite></testsuites>'}),
    }[lang]
    steps = {"execute": dict(ok, rc=exec_rc)}
    steps.update(over)
    return Plan(**steps)


@pytest.fixture
def tree(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "stub.txt").write_text("x")
    (tmp_path / "private").mkdir()
    return work, tmp_path / "private"


def do_grade(lang, tree, plan, **kw):
    work, private = tree
    guard = kw.pop("guard", None) or FakeGuard(plan)
    result = tg.grade(lang, work, "slug", private, image_id=IMG, guard=guard, run=kw.pop("run", guard.run_grader),
                      **kw)
    return result, guard


# ----------------------------------------------------------------------------------------- commands and containers
EXPECTED = {
    "rust": (["cargo test --frozen --offline --no-run"],
             ["cargo test --frozen --offline --no-fail-fast -- --include-ignored"]),
    "java": (["bash ./gradlew --offline --no-daemon compileTestJava"],
             ["bash ./gradlew --offline --no-daemon --rerun-tasks test"]),
    "javascript": (["/opt/tg2/js/node_modules/.bin/jest --ci --listTests"],
                   ["/opt/tg2/js/node_modules/.bin/jest --ci --json --outputFile=/report/jest.json"]),
    "cpp": (["cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON", "cmake --build build --target slug"],
            ["./build/slug -r junit -o /report/cpp.xml"]),
}


@pytest.mark.parametrize("lang", sorted(EXPECTED))
def test_phase_commands_flags_and_mounts_per_language(tree, lang):
    result, guard = do_grade(lang, tree, basic_plan(lang))
    assert result.outcome == "parsed" and not result.all_failed
    assert result.passing == result.collected and len(result.collected) == 2
    steps = [s for s, _ in guard.calls]
    assert steps == ["image", "launch", "compile", "execute"]
    for step, cmd in guard.calls[1:]:
        text = " ".join(cmd)
        for flag in ("--pull=never", "--network none", "--memory 4g", "--memory-swap 4g", "--name"):
            assert flag in text, (step, flag)
        assert cmd[:2] == ["docker", "run"] and "--rm" not in cmd          # kept for OOM inspection
        assert IMG in cmd                                                    # run by the verified image id
        m = mounts(cmd)
        assert set(m) == {"/work/slug", "/report"}                           # nothing else mounted
        assert m["/work/slug"] == str(tree[0].resolve()) and m["/report"] != m["/work/slug"]
        assert "/work/slug" in cmd                                           # -w
    compile_cmd, execute_cmd = (guard.calls[2][1][-1], guard.calls[3][1][-1])
    for part in EXPECTED[lang][0]:
        assert part in compile_cmd
    for part in EXPECTED[lang][1]:
        assert part in execute_cmd
    # every launched container was registered with the guard and removed
    assert len(guard.registered) == 3 and sorted(guard.removed) == sorted(guard.registered)
    assert guard.calls[0][1][:3] == ["docker", "image", "inspect"]


def test_rust_execute_merges_stderr_so_binary_headers_stay_with_their_tests(tree):
    _, guard = do_grade("rust", tree, basic_plan("rust"))
    assert "2>&1" in guard.calls[3][1][-1]


# ----------------------------------------------------------------------------------------------- outcome classes
@pytest.mark.parametrize("lang", sorted(EXPECTED))
def test_compile_failure_fails_every_leaf_and_skips_execute(tree, lang):
    plan = basic_plan(lang, compile=dict(rc=101, stderr="error[E0425]: cannot find value\nerror: aborting"))
    result, guard = do_grade(lang, tree, plan)
    assert result.outcome == "compile_failure" and result.all_failed
    assert result.passing == set() and result.failing({"a", "b"}) == 2
    assert [s for s, _ in guard.calls] == ["image", "launch", "compile"]


@pytest.mark.parametrize("step", ["compile", "execute"])
def test_timeout_after_launch_is_a_model_outcome(tree, step):
    result, guard = do_grade("rust", tree, basic_plan("rust", **{step: dict(timeout=True)}))
    assert result.outcome == "timeout" and result.all_failed and result.passing == set()
    assert guard.removed          # killed container removed


@pytest.mark.parametrize("step", ["compile", "execute"])
def test_container_oom_is_a_model_outcome(tree, step):
    result, _ = do_grade("java", tree, basic_plan("java", **{step: dict(oom=True, rc=137)}))
    assert result.outcome == "oom" and result.all_failed


def test_memory_kill_by_the_guard_is_a_model_outcome(tree):
    plan = basic_plan("cpp", execute=dict(mem_kill=True, rc=137))
    result, _ = do_grade("cpp", tree, plan)
    assert result.outcome == "mem_kill" and result.all_failed


def test_failure_wins_and_missing_expected_leaf_fails(tree):
    plan = basic_plan("rust", execute=dict(rc=101, stdout=(
        "     Running tests/t.rs (x)\nrunning 3 tests\ntest a ... ok\ntest a ... FAILED\ntest b ... ok\n")))
    result, _ = do_grade("rust", tree, plan)
    assert result.outcome == "parsed"
    assert result.passing == {"tests/t.rs::b"}
    assert result.failing({"tests/t.rs::a", "tests/t.rs::b", "tests/t.rs::never_ran"}) == 2


@pytest.mark.parametrize("lang,rc", [("javascript", 0), ("javascript", 1), ("java", 0), ("java", 1), ("cpp", 0),
                                      ("cpp", 3)])
def test_missing_report_after_clean_execute_is_infrastructure(tree, lang, rc):
    plan = basic_plan(lang, execute=dict(rc=rc))
    with pytest.raises(TransportAbort):
        do_grade(lang, tree, plan)


def test_malformed_report_after_clean_execute_is_infrastructure(tree):
    plan = basic_plan("javascript", execute=dict(rc=1, report={"jest.json": "{broken"}))
    with pytest.raises(TransportAbort):
        do_grade("javascript", tree, plan)


def test_rust_without_any_test_lines_after_clean_exit_is_infrastructure(tree):
    with pytest.raises(TransportAbort):
        do_grade("rust", tree, basic_plan("rust", execute=dict(rc=0, stdout="nothing here\n")))


@pytest.mark.parametrize("lang,rc", [("cpp", 139), ("javascript", 134), ("java", 137)])
def test_crash_without_report_is_a_model_outcome(tree, lang, rc):
    result, _ = do_grade(lang, tree, basic_plan(lang, execute=dict(rc=rc)))
    assert result.outcome == "crash" and result.all_failed


def test_java_test_executor_crash_is_a_model_outcome(tree):
    plan = basic_plan("java", execute=dict(rc=1, stdout="Process 'Gradle Test Executor 1' finished with non-zero exit value 1"))
    result, _ = do_grade("java", tree, plan)
    assert result.outcome == "crash" and result.all_failed


def test_rust_binary_killed_mid_run_is_a_model_outcome(tree):
    plan = basic_plan("rust", execute=dict(rc=101, stdout=(
        "     Running tests/t.rs (x)\nerror: test failed\nprocess didn't exit successfully: `x` (signal: 11, SIGSEGV)\n")))
    result, _ = do_grade("rust", tree, plan)
    assert result.outcome == "crash" and result.all_failed


@pytest.mark.parametrize("step,over", [
    ("image", dict(rc=1, stderr="No such image")),
    ("image", dict(image_id="sha256:" + "cd" * 32)),
    ("launch", dict(rc=125, stderr="docker: Error response from daemon")),
    ("launch", dict(timeout=True)),
    ("compile", dict(rc=125, stderr="docker: Error response from daemon: pull access denied")),
    ("compile", dict(rc=127, stderr="bash: cargo: command not found")),
    ("execute", dict(rc=126, stderr="permission denied")),
])
def test_setup_and_docker_level_failures_are_infrastructure(tree, step, over):
    with pytest.raises(TransportAbort):
        do_grade("rust", tree, basic_plan("rust", **{step: over}))


@pytest.mark.parametrize("lang,text", [
    ("rust", "error: failed to get `time` as a dependency of package `x`\nattempting to make an HTTP request, but --offline was specified"),
    ("java", "Could not resolve org.assertj:assertj-core:3.25.1.\nNo cached version available for offline mode"),
])
def test_unresolvable_offline_dependency_is_infrastructure_not_model(tree, lang, text):
    with pytest.raises(TransportAbort):
        do_grade(lang, tree, basic_plan(lang, compile=dict(rc=101 if lang == "rust" else 1, stderr=text)))


# ------------------------------------------------------------------------------------------------- skip-form refusal
@pytest.mark.parametrize("lang,rel,body", [
    ("javascript", "a.spec.js", "xtest('x', () => {});"),
    ("javascript", "a.spec.js", "  xit('x', () => {});"),
    ("javascript", "a.spec.js", "xdescribe('x', () => {});"),
    ("java", "src/test/java/ATest.java", "    @Disabled\n    void t() {}"),
    ("java", "src/test/java/ATest.java", '    @Disabled("Remove to run test")\n    void t() {}'),
])
def test_tree_with_rewritten_skip_form_is_refused_before_any_container(tree, lang, rel, body):
    work, _ = tree
    (work / rel).parent.mkdir(parents=True, exist_ok=True)
    (work / rel).write_text(body)
    guard = FakeGuard(basic_plan(lang))
    with pytest.raises(TransportAbort, match="skip"):
        tg.grade(lang, work, "slug", tree[1], image_id=IMG, guard=guard, run=guard.run_grader)
    assert guard.calls == []
    assert tg.skip_form_violations(work, lang) == [rel]


def test_clean_test_files_have_no_skip_forms(tree):
    work, _ = tree
    (work / "a.spec.js").write_text("test('x', () => {}); describe('y', () => { it('z', () => {}); });")
    assert tg.skip_form_violations(work, "javascript") == []
    (work / "src/test/java").mkdir(parents=True)
    (work / "src/test/java/ATest.java").write_text("import org.junit.jupiter.api.Test; class ATest { @Test void t() {} }")
    assert tg.skip_form_violations(work, "java") == []


# ------------------------------------------------------------------------------------------------------- retention
def test_raw_outputs_retained_by_sha256_with_phase_records(tree, tmp_path):
    keep = tmp_path / "keep"
    plan = basic_plan("javascript", compile=dict(stdout="listed\n", stderr="warn\n"))
    result, _ = do_grade("javascript", tree, plan, keep=keep, seq=3, boundary=7, final=True)
    d = keep / "seq-0003"
    index = json.loads((d / "index.json").read_text())
    assert index["boundary"] == 7 and index["final"] is True and index["outcome"] == "parsed"
    assert {"phases.json", "compile.stdout", "compile.stderr", "execute.stdout", "execute.stderr",
            "report.json"} <= set(index["artifacts"])
    for name, meta in index["artifacts"].items():
        assert hashlib.sha256((keep / meta["path"]).read_bytes()).hexdigest() == meta["sha256"]
    phases = json.loads((d / "phases.json").read_text())
    assert phases["version"] == tg.VERSION == "m65-tg2-v1" and phases["image_id"] == IMG
    names = [p["step"] for p in phases["phases"]]
    assert names == ["setup-image", "setup-launch", "compile", "execute"]
    compile_phase = phases["phases"][2]
    assert compile_phase["rc"] == 0 and compile_phase["seconds"] >= 0
    assert compile_phase["stdout_sha256"] == hashlib.sha256(b"listed\n").hexdigest()
    assert result.artifacts == index["artifacts"]


def test_retained_report_directory_exists_on_infrastructure_abort_too(tree, tmp_path):
    keep = tmp_path / "keep"
    with pytest.raises(TransportAbort):
        do_grade("java", tree, basic_plan("java", execute=dict(rc=1)), keep=keep, seq=0, boundary=1)
    index = json.loads((keep / "seq-0000/index.json").read_text())
    assert index["outcome"] == "infrastructure" and "execute.stdout" in index["artifacts"]


def test_existing_grade_report_path_is_immutable(tree, tmp_path):
    keep = tmp_path / "keep"
    (keep / "seq-0001").mkdir(parents=True)
    with pytest.raises(TransportAbort, match="immutable"):
        do_grade("rust", tree, basic_plan("rust"), keep=keep, seq=1, boundary=0)


def test_image_digest_is_pinned_and_checked_before_grading(tree):
    work, private = tree
    guard = FakeGuard(basic_plan("rust", image=dict(image_id="sha256:" + "ee" * 32)))
    with pytest.raises(TransportAbort, match="image"):
        tg.grade("rust", work, "slug", private, image_id=IMG, guard=guard, run=guard.run_grader)
    assert [s for s, _ in guard.calls] == ["image"]
    pinned = tg.pinned_image_id()
    assert pinned.startswith("sha256:") and len(pinned) == 71


def test_unsupported_language_is_refused(tree):
    with pytest.raises(TransportAbort):
        tg.grade("go", *tree[:1], "slug", tree[1], image_id=IMG)


# ------------------------------------------------------------------------------------------------------- tamper
def build_tree(root, files):
    root = Path(root)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def prep(tmp_path, files, solutions):
    work = build_tree(tmp_path / "w", files)
    prepared = sg.manifest(work)
    return work, prepared, sg.protected_manifest(prepared, solutions)


RUST = {"Cargo.toml": "[package]\nname='x'\n", "Cargo.lock": "# lock\n", "src/lib.rs": "pub fn f() {}\n",
        "tests/x.rs": "#[test] fn t() {}\n"}
JAVA = {"build.gradle": "plugins {}\n", "gradlew": "#!/bin/sh\n", "gradle/wrapper/gradle-wrapper.properties": "x=1\n",
        "src/main/java/Foo.java": "public class Foo {}\n", "src/main/java/Bar.java": "public class Bar {}\n",
        "src/test/java/FooTest.java": "public class FooTest {}\n"}
JS = {"package.json": "{}", "babel.config.js": "module.exports = {};\n", "x.js": "export {};\n",
      "x.spec.js": "test('a', () => {});\n"}
CPP = {"CMakeLists.txt": "project(x)\n", "x.cpp": "\n", "x.h": "\n", "x_test.cpp": "#include \"x.h\"\n",
       "test/catch.hpp": "// catch\n", "test/tests-main.cpp": "#define CATCH_CONFIG_MAIN\n"}
CASES = {"rust": (RUST, ["src/lib.rs"]), "java": (JAVA, ["src/main/java/Foo.java"]), "javascript": (JS, ["x.js"]),
         "cpp": (CPP, ["x.cpp", "x.h"])}


def reasons_for(tmp_path, lang, mutate, *, files=None, solutions=None):
    base, sols = CASES[lang]
    work, prepared, protected = prep(tmp_path, files or base, solutions or sols)
    mutate(work)
    return tg.tamper_reasons(work, protected, prepared, lang, solutions=solutions or sols)


def write(work, rel, text="x\n"):
    p = Path(work) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.mark.parametrize("lang", sorted(CASES))
def test_editing_only_declared_solution_files_is_not_tampering(tmp_path, lang):
    base, sols = CASES[lang]
    assert reasons_for(tmp_path, lang, lambda w: [write(w, s, "// edited\n") for s in sols]) == []


@pytest.mark.parametrize("lang,rel", [
    ("rust", "tests/x.rs"), ("rust", "Cargo.lock"), ("java", "src/test/java/FooTest.java"),
    ("java", "build.gradle"), ("java", "gradlew"), ("javascript", "x.spec.js"), ("javascript", "package.json"),
    ("cpp", "x_test.cpp"), ("cpp", "test/catch.hpp"), ("cpp", "CMakeLists.txt")])
def test_modifying_a_protected_file_is_tampering(tmp_path, lang, rel):
    assert reasons_for(tmp_path, lang, lambda w: write(w, rel, "changed\n"))


@pytest.mark.parametrize("lang,rel", [("rust", "tests/x.rs"), ("java", "src/test/java/FooTest.java"),
                                       ("javascript", "x.spec.js"), ("cpp", "x_test.cpp")])
def test_deleting_a_protected_file_is_tampering(tmp_path, lang, rel):
    assert reasons_for(tmp_path, lang, lambda w: (Path(w) / rel).unlink())


def test_rust_cargo_toml_edit_is_tampering_even_when_metadata_lists_it_as_a_solution(tmp_path):
    reasons = reasons_for(tmp_path, "rust", lambda w: write(w, "Cargo.toml", "[package]\nname='y'\n"),
                          solutions=["src/lib.rs", "Cargo.toml"])
    assert any("Cargo.toml" in r for r in reasons)
    assert any("Cargo.lock" in r for r in reasons_for(tmp_path / "b", "rust",
                                                      lambda w: write(w, "Cargo.lock", "# other\n")))


@pytest.mark.parametrize("rel", ["build.rs", "src/build.rs", ".cargo/config.toml", "target/debug/x.rs", "tests/extra.rs",
                                  "Cargo.toml.bak", "src/main.rs", "src/bin/x.rs", "sub/Cargo.toml",
                                  "rust-toolchain.toml", "benches/b.rs", "notes.txt"])
def test_rust_new_file_vectors_are_tampering(tmp_path, rel):
    assert reasons_for(tmp_path, "rust", lambda w: write(w, rel))


def test_rust_allows_new_src_helper_modules(tmp_path):
    assert reasons_for(tmp_path, "rust", lambda w: (write(w, "src/helper.rs"), write(w, "src/sub/mod.rs"))) == []


@pytest.mark.parametrize("rel", ["src/test/java/ExtraTest.java", "settings.gradle", "settings.gradle.kts",
                                  "gradle.properties", "build/classes/x.class", ".gradle/x", "src/main/resources/junit-platform.properties",
                                  "src/main/java/module-info.java", "init.gradle", "notes.md", "buildSrc/x.java"])
def test_java_new_file_vectors_are_tampering(tmp_path, rel):
    assert reasons_for(tmp_path, "java", lambda w: write(w, rel))


@pytest.mark.parametrize("rel,body", [
    ("src/main/java/org/assertj/core/api/Assertions.java", "package org.assertj.core.api; public class Assertions {}"),
    ("src/main/java/Shadow.java", "package org.assertj.core.api;\npublic class Shadow {}"),          # path != package
    ("src/main/java/org/junit/jupiter/api/Assertions.java", "package org.junit.jupiter.api; public class Assertions {}"),
    ("src/main/java/org/json/JSONObject.java", "package org.json; public class JSONObject {}"),
    ("src/main/java/io/reactivex/Observable.java", "package io.reactivex; public class Observable {}"),
    ("src/main/java/java/lang/Thing.java", "package java.lang; public class Thing {}"),
    ("src/main/java/javax/x/Thing.java", "package javax.x; public class Thing {}"),
    ("src/main/java/FooTest.java", "public class FooTest {}"),            # duplicate of a test-visible class
])
def test_java_namespace_and_duplicate_guard_vectors(tmp_path, rel, body):
    assert reasons_for(tmp_path, "java", lambda w: write(w, rel, body))


def test_java_allows_helper_classes_under_the_solution_package_root(tmp_path):
    files = dict(JAVA, **{"src/main/java/pkg/Foo.java": "package pkg;\npublic class Foo {}\n"})
    sols = ["src/main/java/pkg/Foo.java"]
    reasons = reasons_for(tmp_path, "java", lambda w: (write(w, "src/main/java/pkg/Helper.java",
                                                            "package pkg;\nclass Helper {}\n"),
                                                      write(w, "src/main/java/pkg/sub/Deep.java",
                                                            "package pkg.sub;\nclass Deep {}\n")),
                          files=files, solutions=sols)
    assert reasons == []
    # outside the declared package root:
    assert reasons_for(tmp_path / "b", "java", lambda w: write(w, "src/main/java/other/Helper.java",
                                                               "package other;\nclass Helper {}\n"),
                       files=files, solutions=sols)


@pytest.mark.parametrize("rel", ["jest.config.js", "jest.config.json", "jest.config.ts", "babel.config.json",
                                  "babel.config.cjs", ".babelrc", ".babelrc.js", "node_modules/x/index.js",
                                  "jest/index.js", "__mocks__/fs.js", "extra.spec.js", "extra.test.js", "sub/helper.js",
                                  "package-lock.json", "build/x.js", "setup.mjs", ".npmrc"])
def test_javascript_new_file_vectors_are_tampering(tmp_path, rel):
    assert reasons_for(tmp_path, "javascript", lambda w: write(w, rel))


def test_javascript_allows_non_test_helper_beside_the_solution(tmp_path):
    assert reasons_for(tmp_path, "javascript", lambda w: write(w, "helper.js")) == []


@pytest.mark.parametrize("rel", ["catch.hpp", "catch2/catch.hpp", "test/extra.cpp", "extra_test.cpp", "tests-main.cpp",
                                  "CMakeLists.txt.new", "toolchain.cmake", "build/x.o", "sub/x.h", "notes.txt",
                                  "boost/date_time.hpp", "Catch.hpp"])
def test_cpp_new_file_vectors_are_tampering(tmp_path, rel):
    assert reasons_for(tmp_path, "cpp", lambda w: write(w, rel))


def test_cpp_allows_new_helper_headers_and_sources_beside_the_solution(tmp_path):
    assert reasons_for(tmp_path, "cpp", lambda w: (write(w, "helper.h"), write(w, "helper.cpp"))) == []


def test_symlinks_are_tampering(tmp_path):
    def mutate(w):
        os.symlink("/etc/passwd", Path(w) / "src" / "evil.rs")
    assert reasons_for(tmp_path, "rust", mutate)


def test_tampered_bool_wrapper_matches_reasons(tmp_path):
    work, prepared, protected = prep(tmp_path, RUST, ["src/lib.rs"])
    assert tg.tampered(work, protected, prepared, "rust", solutions=["src/lib.rs"]) is False
    write(work, "build.rs")
    assert tg.tampered(work, protected, prepared, "rust", solutions=["src/lib.rs"]) is True


# ------------------------------------------------------------------------------------------- Rust lockfile helper
def test_generate_cargo_locks_runs_offline_in_the_image_and_returns_created_locks(tmp_path):
    work = build_tree(tmp_path / "w", {"Cargo.toml": "x", "nested/Cargo.toml": "y"})
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        m = mounts(cmd)
        host = Path(next(h for t, h in m.items() if t.startswith("/work/")))
        (host / "Cargo.lock").write_text("a")
        (host / "nested/Cargo.lock").write_text("b")
        return subprocess.CompletedProcess(cmd, 0, None, None)

    locks = tg.generate_cargo_locks(work, "slug", tmp_path / "p", image_id=IMG, run=run)
    assert locks == ["Cargo.lock", "nested/Cargo.lock"]
    text = " ".join(seen[0])
    assert "--network none" in text and "--pull=never" in text and "generate-lockfile --offline" in text
    assert "--frozen" not in text


# ----------------------------------------------------------------------------------------- docker integration
POLYGLOT = Path(os.environ.get("POLYGLOT_DIR") or Path(os.environ.get("STACK_WORKDIR", "")) / "polyglot-benchmark")


def _docker_skip_reason():
    docker = shutil.which("docker") or str(Path.home() / ".orbstack/bin/docker")
    if not Path(docker).exists():
        return "docker CLI not available"
    try:
        pinned = tg.pinned_image_id()
        out = subprocess.run([docker, "image", "inspect", "--format", "{{.Id}}", pinned], capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired, TransportAbort) as exc:
        return "docker unavailable: %s" % exc
    if out.returncode:
        return "tg2-grader image %s is not built locally (run benchmark/m65/tg2_image/build.sh)" % tg.IMAGE_TAG
    if not (POLYGLOT / "rust/exercises/practice").is_dir():
        return "polyglot corpus not found (set POLYGLOT_DIR / STACK_WORKDIR)"
    return None


DOCKER_SKIP = _docker_skip_reason()
ITEMS = [("rust", "gigasecond"), ("rust", "macros"), ("java", "affine-cipher"), ("java", "connect"),
         ("javascript", "affine-cipher"), ("javascript", "alphametics"), ("cpp", "gigasecond"),
         ("cpp", "binary-search-tree")]


@pytest.mark.docker
@pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")
@pytest.mark.parametrize("lang,slug", ITEMS)
def test_reference_all_pass_and_untouched_stub_fails_in_the_built_image(tmp_path, lang, slug):
    from bench.tests import tg2_trees
    docker_bin = shutil.which("docker") or str(Path.home() / ".orbstack/bin/docker")
    os.environ["PATH"] = str(Path(docker_bin).parent) + os.pathsep + os.environ["PATH"]
    ref = tg2_trees.reference_tree(POLYGLOT, lang, slug, tmp_path / "ref")
    stub = tg2_trees.stub_tree(POLYGLOT, lang, slug, tmp_path / "stub")
    guard = tg.LocalDocker()
    (tmp_path / "private").mkdir()
    if lang == "rust":
        tg.generate_cargo_locks(ref, slug, tmp_path / "private", guard=guard)
        tg.generate_cargo_locks(stub, slug, tmp_path / "private", guard=guard)
    good = tg.grade(lang, ref, slug, tmp_path / "private", guard=guard, timeout=900,
                    keep=tmp_path / "keep", seq=0, boundary=0, final=True)
    assert good.outcome == "parsed", good.phases
    assert good.collected and good.passing == good.collected, sorted(good.collected - good.passing)
    base = tg.grade(lang, stub, slug, tmp_path / "private", guard=guard, timeout=900)
    assert base.failing(good.collected) > 0, (base.outcome, base.passing)
    assert not guard.leftover()
