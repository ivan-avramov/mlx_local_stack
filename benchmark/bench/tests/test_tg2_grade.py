"""M65 tg2 grader (`bench/tg2_grade.py`, version m65-tg2-v1): parsers, phase-typed grading, outcome classes, tamper
checks, skip-form refusal. Unit tests use a fake `run` (no docker); docker-marked integration tests grade real
reference / stub trees inside the built `tg2-grader` image and are skipped (with the reason) when docker, the image or
the polyglot corpus is absent."""

import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess

import pytest

from bench import structured_grade as sg
from bench import tg2_grade as tg
from bench.token_turn_gate import TransportAbort

IMG = "sha256:" + "ab" * 32


# P361: OrbStack bind mounts under $TMPDIR serve stale file sizes, and the grader refuses such sources, so every test
# tree lives under a non-TMPDIR root.
def _test_root():
    base = os.environ.get("STACK_WORKDIR")
    root = Path(base) / "m65/test-tmp" if base else Path(__file__).resolve().parents[3] / ".tg2-test-tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root


TEST_ROOT = _test_root()


@pytest.fixture
def tmp_path():
    import uuid
    path = TEST_ROOT / ("t-" + uuid.uuid4().hex[:10])
    path.mkdir()
    yield path
    shutil.rmtree(path, ignore_errors=True)


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
    if cmd[:2] == ["docker", "volume"]:
        return "volume"
    if cmd[:3] == ["docker", "run", "-d"]:
        return "holder"
    if cmd[:2] == ["docker", "ps"]:
        return "ps"
    if cmd[:3] == ["docker", "rm", "-f"]:
        return "rm"
    if "TG2_COLLECT_START" in cmd[-1]:
        return "collect"
    if "TG2_STAGE" in cmd[-1]:
        return "launch"
    if cmd[:2] == ["docker", "inspect"]:
        return "inspect"
    script = cmd[-1] if cmd[-2:-1] == ["-c"] else " ".join(cmd[-3:])
    if "TG2_PREFLIGHT" in script:
        return "preflight"
    if "TG2_COMPILE_START" in script:
        return "compile"
    return "execute"


def mounts(cmd):
    """dst -> src (bind path or volume name) from `--mount type=...,src=...,dst=...[,readonly]` arguments."""
    out = {}
    for i, a in enumerate(cmd):
        if a == "--mount":
            kv = dict(x.split("=", 1) for x in cmd[i + 1].split(",") if "=" in x)
            out[kv["dst"]] = kv["src"]
    return out


def make_tar(members):
    """members: [(name, kind, payload)] with kind file/dir/symlink/fifo/chr; payload = bytes or link target."""
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, kind, payload in members:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(payload)
                tf.addfile(info, io.BytesIO(payload))
                continue
            info.type = {"dir": tarfile.DIRTYPE, "symlink": tarfile.SYMTYPE, "fifo": tarfile.FIFOTYPE,
                         "chr": tarfile.CHRTYPE}[kind]
            if kind == "symlink":
                info.linkname = payload
            tf.addfile(info)
    return buf.getvalue()


class FakeGuard:
    grader_mem_kill = False

    def __init__(self, plan, mem_kill_step=None):
        self.plan, self.names, self.registered, self.removed, self.calls = plan, {}, [], [], []
        self.n = 0
        self.mem_kill_step = mem_kill_step
        self.step_by_name = {}
        self.volumes, self.volume_ops, self.holders = {}, [], []
        self.volume_names = set()
        self.volume_labels, self.holder_names = {}, {}
        self.vroot = Path(__import__("tempfile").mkdtemp(prefix="fakevol-", dir=TEST_ROOT))

    def container_name(self):
        self.n += 1
        return f"fake-{self.n}"

    def register_container(self, name):
        self.registered.append(name)

    def remove_container(self, name):
        if self.plan.get("holder_rm").get("raise") and name == "fake-1":
            raise TransportAbort("container cleanup uncertain (fake)")
        self.removed.append(name)
        self.holder_names.pop(name, None)

    def vol(self, src):
        return self.volumes[src] if src in self.volumes else Path(src)

    def run_grader(self, cmd, **kw):
        step = step_of(cmd)
        if step == "volume":
            self.volume_ops.append(cmd)
            if cmd[2] == "create":
                path = self.vroot / cmd[-1]
                path.mkdir()
                self.volumes[cmd[-1]] = path
                self.volume_names.add(cmd[-1])
                self.volume_labels[cmd[-1]] = dict(x.split("=", 1) for i, x in enumerate(cmd) if cmd[i - 1] == "--label")
            elif cmd[2] == "rm":
                rm = self.plan.get("volume_rm")
                if rm.get("timeout"):
                    raise subprocess.TimeoutExpired(cmd, 1)
                if not rm.get("rc"):
                    shutil.rmtree(self.volumes.pop(cmd[-1], self.vroot / "none"), ignore_errors=True)
                return subprocess.CompletedProcess(cmd, rm.get("rc", 0), None, None)
            elif cmd[2] == "ls":
                flt = cmd[cmd.index("--filter") + 1]
                if flt.startswith("label="):
                    key, _, val = flt[len("label="):].partition("=")
                    kw["stdout"].write("".join("%s %s\n" % (n, self.volume_labels.get(n, {}).get("mlxbench.tg2.created", ""))
                                               for n in self.volumes if self.volume_labels.get(n, {}).get(key) == val))
                else:
                    want = flt.split("name=^", 1)[1].rstrip("$")
                    kw["stdout"].write("".join(n + "\n" for n in self.volumes if n == want))
            return subprocess.CompletedProcess(cmd, 0, None, None)
        if step == "ps":
            flt = cmd[cmd.index("--filter") + 1]
            if flt.startswith("label="):
                key, _, val = flt[len("label="):].partition("=")
                kw["stdout"].write("".join("%s %s\n" % (n, l.get("mlxbench.tg2.created", ""))
                                           for n, l in self.holder_names.items() if l.get(key) == val))
            else:
                want = flt.split("name=^/", 1)[1].rstrip("$")
                kw["stdout"].write("".join(n + "\n" for n in self.holder_names if n == want))
            return subprocess.CompletedProcess(cmd, 0, None, None)
        if step == "rm":
            self.holder_names.pop(cmd[-1], None)
            return subprocess.CompletedProcess(cmd, 0, None, None)
        if step == "holder":
            self.holders.append(cmd)
            self.holder_names[cmd[cmd.index("--name") + 1]] = dict(
                x.split("=", 1) for i, x in enumerate(cmd) if cmd[i - 1] == "--label")
            kw["stdout"].write("holder-id\n")
            return subprocess.CompletedProcess(cmd, self.plan.get("holder").get("rc", 0), None, None)
        if step == "inspect" and any("Config.Labels" in x for x in cmd):
            kw["stdout"].write(self.holder_names.get(cmd[-1], {}).get("mlxbench.tg2", "") + "\n")
            return subprocess.CompletedProcess(cmd, 0, None, None)
        if step == "inspect":
            spec = self.plan.get(self.step_by_name.get(cmd[-1], "?"))
            if spec.get("inspect_rc"):
                return subprocess.CompletedProcess(cmd, spec["inspect_rc"], None, None)
            kw["stdout"].write(spec.get("inspect_out", "true" if spec.get("oom") else "false") + "\n")
            return subprocess.CompletedProcess(cmd, 0, None, None)
        if "--name" in cmd:
            self.step_by_name[cmd[cmd.index("--name") + 1]] = step
        self.calls.append((step, cmd))
        spec = self.plan.get(step)
        if step in ("compile", "execute", "collect") and spec.get("mem_kill"):
            self.grader_mem_kill = True
        if step in ("compile", "execute"):
            tag = "TG2_RUNNER_START" if step == "execute" else "TG2_COMPILE_START"
            nonce = re.search(tag + r" (\w+)", cmd[-1]).group(1)
            if spec.get("fake_marker"):
                kw["stdout"].write(tag + " deadbeef\n")
            if not spec.get("no_marker"):
                kw["stdout"].write("%s %s\n" % (tag, nonce))
        if step == "collect" and not spec.get("no_marker"):
            kw["stderr"].write("TG2_COLLECT_START %s\n" % re.search(r"TG2_COLLECT_START (\w+)", cmd[-1]).group(1))
        if spec.get("timeout"):
            kw["stdout"].write(spec.get("stdout", ""))
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 1)
        if spec.get("big_stdout"):
            kw["stdout"].write("x" * spec["big_stdout"])
        kw["stdout"].write(spec.get("stdout", ""))
        kw["stderr"].write(spec.get("stderr", ""))
        m = mounts(cmd)
        wdst = next((d for d in m if d.startswith("/work/")), None)
        if wdst and wdst != "/work/slug":
            m["/work/slug"] = m[wdst]
        if step == "launch":
            shutil.copytree(self.vol(m["/src"]), self.vol(m["/work/slug"]), dirs_exist_ok=True)
        for rel, data in spec.get("report", {}).items():
            (self.vol(m["/report"]) / rel).write_bytes(data if isinstance(data, bytes) else data.encode())
        for rel, data in spec.get("work", {}).items():
            p = self.vol(m["/work/slug"]) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else data.encode())
        if step == "collect":
            if "tar" in spec:
                data = spec["tar"]
            elif "test-results" in cmd[-1]:
                root = self.vol(m["/work/slug"]) / "build/test-results/test"
                data = make_tar([("test", "dir", None)] + [("test/" + f.name, "file", f.read_bytes())
                                                           for f in sorted(root.glob("*.xml"))]) if root.is_dir() else b""
            else:
                name = "jest.json" if "jest.json" in cmd[-1] else "cpp.xml"
                f = self.vol(m["/report"]) / name
                data = make_tar([(name, "file", f.read_bytes())]) if f.is_file() else b""
            kw["stdout"].buffer.write(data)
            kw["stdout"].flush()
            return subprocess.CompletedProcess(cmd, spec.get("rc", 0 if data else 2), None, None)
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
    assert steps == ["image", "launch", "preflight", "compile", "execute"] + ([] if lang == "rust" else ["collect"])
    for step, cmd in guard.calls[1:]:
        text = " ".join(cmd)
        for flag in ("--pull=never", "--network none", "--memory 4g", "--memory-swap 4g", "--name"):
            assert flag in text, (step, flag)
        assert cmd[:2] == ["docker", "run"] and "--rm" not in cmd          # kept for OOM inspection
        assert IMG in cmd                                                    # run by the verified image id
        m = mounts(cmd)
        if step == "launch":                                                 # only the stage step sees the host tree
            assert set(m) == {"/src", "/work/slug", "/report"} and m["/src"] == str(tree[0].resolve())
            assert "readonly" in [x for x in cmd if x.endswith("dst=/src,readonly")][0]
        else:
            assert set(m) == {"/work/slug", "/report"}                       # volumes only: no host bind at all
            assert m["/work/slug"] in guard.volume_names and m["/report"] in guard.volume_names
        assert "/work/slug" in cmd                                           # -w
    compile_cmd, execute_cmd = (guard.calls[3][1][-1], guard.calls[4][1][-1])
    for part in EXPECTED[lang][0]:
        assert part in compile_cmd
    for part in EXPECTED[lang][1]:
        assert part in execute_cmd
    # every launched container was registered with the guard and removed
    assert sorted(guard.removed) == sorted(guard.registered)
    assert guard.calls[0][1][:3] == ["docker", "image", "inspect"]


def test_rust_execute_merges_stderr_so_binary_headers_stay_with_their_tests(tree):
    _, guard = do_grade("rust", tree, basic_plan("rust"))
    assert "2>&1" in guard.calls[4][1][-1]


# ----------------------------------------------------------------------------------------------- outcome classes
@pytest.mark.parametrize("lang", sorted(EXPECTED))
def test_compile_failure_fails_every_leaf_and_skips_execute(tree, lang):
    plan = basic_plan(lang, compile=dict(rc=101, stderr="error[E0425]: cannot find value\nerror: aborting"))
    result, guard = do_grade(lang, tree, plan)
    assert result.outcome == "compile_failure" and result.all_failed
    assert result.passing == set() and result.failing({"a", "b"}) == 2
    assert [s for s, _ in guard.calls] == ["image", "launch", "preflight", "compile"]


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
                                      ("cpp", 3), ("cpp", 139), ("javascript", 134), ("java", 137)])
def test_missing_report_after_runner_start_is_a_model_outcome(tree, lang, rc):
    result, _ = do_grade(lang, tree, basic_plan(lang, execute=dict(rc=rc)))
    assert result.outcome == "crash" and result.all_failed and result.passing == set()
    assert result.reason == "runner_crash_after_start"


def test_malformed_report_after_runner_start_is_a_model_outcome(tree):
    plan = basic_plan("javascript", execute=dict(rc=1, report={"jest.json": "{broken"}))
    result, _ = do_grade("javascript", tree, plan)
    assert result.outcome == "crash" and result.reason == "runner_crash_after_start"


def test_rust_without_any_test_lines_after_start_is_a_model_outcome(tree):
    result, _ = do_grade("rust", tree, basic_plan("rust", execute=dict(rc=0, stdout="nothing here\n")))
    assert result.outcome == "crash" and result.all_failed


def test_javascript_process_exit_style_crash_after_start_is_a_model_failure(tree):
    plan = basic_plan("javascript", execute=dict(rc=1, stderr="process.exit called with \"1\"\n"))
    result, _ = do_grade("javascript", tree, plan)
    assert result.outcome == "crash" and result.all_failed and result.reason == "runner_crash_after_start"


@pytest.mark.parametrize("lang", sorted(EXPECTED))
def test_marker_absent_is_infrastructure_even_with_a_report_present(tree, lang):
    plan = basic_plan(lang)
    plan.steps["execute"]["no_marker"] = True
    with pytest.raises(TransportAbort, match="marker"):
        do_grade(lang, tree, plan)


def test_forged_marker_without_the_nonce_does_not_change_classification(tree):
    plan = basic_plan("javascript")
    plan.steps["execute"].update(no_marker=True, fake_marker=True)
    with pytest.raises(TransportAbort, match="marker"):                       # still absent: forged nonce
        do_grade("javascript", tree, plan)
    plan = basic_plan("javascript")
    plan.steps["execute"]["fake_marker"] = True
    result, _ = do_grade("javascript", tree, plan)                           # real marker present: unchanged
    assert result.outcome == "parsed" and len(result.passing) == 2


def test_execute_script_prints_the_marker_right_before_the_runner_with_a_fresh_nonce(tree):
    _, g1 = do_grade("java", tree, basic_plan("java"))
    _, g2 = do_grade("java", tree, basic_plan("java"))
    s1, s2 = g1.calls[4][1][-1], g2.calls[4][1][-1]
    assert re.search(r'echo "TG2_RUNNER_START [0-9a-f]{16}"; bash \./gradlew', s1)
    assert s1 != s2


@pytest.mark.parametrize("step,over", [
    ("image", dict(rc=1, stderr="No such image")),
    ("image", dict(image_id="sha256:" + "cd" * 32)),
    ("launch", dict(rc=125, stderr="docker: Error response from daemon")),
    ("launch", dict(timeout=True)),
    ("compile", dict(rc=125, stderr="docker: Error response from daemon: pull access denied", no_marker=True)),
    ("compile", dict(rc=127, stderr="bash: cargo: command not found", no_marker=True)),
    ("preflight", dict(rc=1, stderr="cargo: command not found")),
    ("preflight", dict(timeout=True)),
    ("execute", dict(rc=126, stderr="permission denied", no_marker=True)),
])
def test_setup_and_docker_level_failures_are_infrastructure(tree, step, over):
    with pytest.raises(TransportAbort):
        do_grade("rust", tree, basic_plan("rust", **{step: over}))


@pytest.mark.parametrize("lang,text", [
    ("rust", "error: failed to get `time` as a dependency of package `x`\nattempting to make an HTTP request, but --offline"),
    ("java", "Could not resolve org.assertj:assertj-core:3.25.1.\nNo cached version available for offline mode"),
])
def test_dependency_looking_compile_text_is_a_model_outcome_after_preflight(tree, lang, text):
    plan = basic_plan(lang, compile=dict(rc=101 if lang == "rust" else 1, stderr=text))
    result, _ = do_grade(lang, tree, plan)
    assert result.outcome == "compile_failure" and result.all_failed


PREFLIGHT_NEEDLES = {"rust": ("cargo", "cargo-vendor"), "java": ("java", "GRADLE_RO_DEP_CACHE", "gradle-8.7"),
                     "javascript": ("jest", "@babel/core"), "cpp": ("cmake", "boost")}


@pytest.mark.parametrize("lang", sorted(PREFLIGHT_NEEDLES))
def test_preflight_checks_runners_and_dependency_closure_before_the_compile_marker(tree, lang):
    _, guard = do_grade(lang, tree, basic_plan(lang))
    script = guard.calls[2][1][-1]
    assert "TG2_PREFLIGHT" in script and "TG2_COMPILE_START" not in script
    for needle in PREFLIGHT_NEEDLES[lang]:
        assert needle in script, needle
    assert "TG2_COMPILE_START" in guard.calls[3][1][-1]


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
    assert names == ["setup-image", "setup-launch", "preflight", "compile", "execute", "collect"]
    compile_phase = phases["phases"][3]
    assert compile_phase["rc"] == 0 and compile_phase["seconds"] >= 0
    assert compile_phase["stdout_sha256"] == hashlib.sha256((d / "compile.stdout").read_bytes()).hexdigest()
    assert (d / "compile.stdout").read_text().endswith("listed\n")
    assert result.artifacts == index["artifacts"]


def test_retained_report_directory_exists_on_infrastructure_abort_too(tree, tmp_path):
    keep = tmp_path / "keep"
    with pytest.raises(TransportAbort):
        do_grade("java", tree, basic_plan("java", execute=dict(rc=1, no_marker=True)), keep=keep, seq=0, boundary=1)
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


# --------------------------------------------------------------------------------- agent-created build outputs
def test_strip_removes_absent_top_level_build_outputs_and_tamper_then_passes(tmp_path):
    work, prepared, protected = prep(tmp_path, RUST, ["src/lib.rs"])
    write(work, "target/debug/x.rs")
    write(work, "build/y")
    write(work, "node_modules/jest/index.js")
    write(work, ".gradle/z")
    assert tg.tamper_reasons(work, protected, prepared, "rust", solutions=["src/lib.rs"])   # default-deny unstripped
    assert tg.strip_build_outputs(work, prepared) == ["build", "target", "node_modules", ".gradle"]
    assert tg.tamper_reasons(work, protected, prepared, "rust", solutions=["src/lib.rs"]) == []
    assert not (work / "target").exists() and not (work / "node_modules").exists()


def test_strip_removes_a_symlinked_build_dir_without_following_it(tmp_path):
    work, prepared, _ = prep(tmp_path, RUST, ["src/lib.rs"])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("1")
    os.symlink(outside, work / "target")
    assert tg.strip_build_outputs(work, prepared) == ["target"]
    assert (outside / "keep").exists() and not (work / "target").is_symlink()


def test_prepared_build_dir_is_protected_not_stripped(tmp_path):
    files = dict(RUST, **{"build/fixture.txt": "data\n"})
    work, prepared, protected = prep(tmp_path, files, ["src/lib.rs"])
    assert tg.strip_build_outputs(work, prepared) == []
    write(work, "build/fixture.txt", "changed\n")
    assert tg.tamper_reasons(work, protected, prepared, "rust", solutions=["src/lib.rs"])


def test_nested_build_dir_is_not_stripped_and_stays_default_denied(tmp_path):
    work, prepared, protected = prep(tmp_path, RUST, ["src/lib.rs"])
    write(work, "src/build/x.rs")
    assert tg.strip_build_outputs(work, prepared) == []
    assert (work / "src/build/x.rs").exists()
    # a rust src/*.rs helper is allowlisted even in a dir called build; non-allowlisted nested files are denied
    write(work, "tests/build/y.rs")
    reasons = tg.tamper_reasons(work, protected, prepared, "rust", solutions=["src/lib.rs"])
    assert any("tests/build/y.rs" in r for r in reasons)


def test_grade_strips_planted_artifacts_before_any_container_and_records_them(tree):
    work, private = tree
    write(work, "node_modules/jest/index.js", "evil")
    write(work, "target/debug/stale", "stale")
    prepared = sg.manifest(work)
    prepared = {k: v for k, v in prepared.items() if not k.startswith(("node_modules/", "target/"))}
    seen = {}
    guard = FakeGuard(basic_plan("javascript"))
    inner = guard.run_grader

    def run(cmd, **kw):
        seen.setdefault("present", []).append((work / "node_modules").exists() or (work / "target").exists())
        return inner(cmd, **kw)

    result = tg.grade("javascript", work, "slug", private, prepared=prepared, image_id=IMG, guard=guard, run=run)
    assert result.stripped == ["target", "node_modules"] and not any(seen["present"])


# ------------------------------------------------------------------------------------------- Rust lockfile helper
def test_generate_cargo_locks_runs_offline_in_the_image_and_returns_created_locks(tmp_path):
    work = build_tree(tmp_path / "w", {"Cargo.toml": "x", "nested/Cargo.toml": "y"})
    seen = []

    def run(cmd, **kw):
        if cmd[:2] == ["docker", "inspect"]:
            kw["stdout"].write("false\n")
            return subprocess.CompletedProcess(cmd, 0, None, None)
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


# ============================================================================================ round-2 (G1-G17)
# G1 -------------------------------------------------------------------------------------------------------------
def test_g1_failing_counts_failed_leaves_outside_the_universe_and_missing_expected():
    g = tg.Tg2Grade(leaves={"a": True, "b": True, "teardown": False, "c": False})
    assert g.failing({"a", "b"}) == 2                # teardown, c: collected failures outside the universe
    assert g.failing({"a", "b", "m"}) == 3           # + missing expected leaf m
    g.optional = frozenset({"c"})
    assert g.failing({"a", "b"}) == 1                # frozen optional ids excluded only
    assert tg.Tg2Grade(leaves={"a": True}, all_failed=True).failing({"a", "b"}) == 2


# G2 / G3 --------------------------------------------------------------------------------------------------------
def test_g2_suite_status_failure_with_passing_assertions_is_a_counted_failure():
    doc = jest_doc([{"name": "/work/s/a.spec.js", "status": "failed", "message": "afterAll boom",
                     "assertionResults": [{"fullName": "x", "status": "passed"}]}])
    leaves = tg.parse_jest(doc, "/work/s")
    assert leaves["a.spec.js::x"] is True and leaves["a.spec.js::<suite failed>"] is False


def test_g2_top_level_success_false_without_any_failed_leaf_is_a_counted_failure():
    doc = json.dumps({"success": False, "testResults": [{"name": "/work/s/a.spec.js", "status": "passed",
                      "assertionResults": [{"fullName": "x", "status": "passed"}]}]})
    leaves = tg.parse_jest(doc, "/work/s")
    assert leaves["<run failed>"] is False


@pytest.mark.parametrize("doc", [
    {"success": True, "testResults": [{"name": "/w/a.js", "status": "passed", "assertionResults": ["x"]}]},
    {"success": True, "testResults": [{"name": "/w/a.js", "status": "passed", "assertionResults": [{"status": "passed"}]}]},
    {"success": True, "testResults": [{"name": "/w/a.js", "status": "passed", "assertionResults": [{"fullName": 1, "status": "passed"}]}]},
    {"success": True, "testResults": [{"name": "/w/a.js", "assertionResults": []}]},
    {"success": True, "testResults": [{"name": "/w/a.js", "status": 3, "assertionResults": []}]},
    {"success": True, "testResults": [{"name": "/w/a.js", "status": "passed", "assertionResults": "x"}]},
    {"success": True, "testResults": ["x"]},
    {"testResults": [{"name": "/w/a.js", "status": "passed", "assertionResults": []}]},
    {"success": "yes", "testResults": [{"name": "/w/a.js", "status": "passed", "assertionResults": []}]},
])
def test_g3_every_report_shape_error_is_a_report_error(doc):
    with pytest.raises(tg.ReportError):
        tg.parse_jest(json.dumps(doc), "/w")


def test_g3_valid_json_wrong_shape_after_start_is_a_model_outcome_not_an_exception(tree):
    plan = basic_plan("javascript", execute=dict(rc=1, report={"jest.json": json.dumps(
        {"success": True, "testResults": [{"name": "/w/a.js", "status": "passed", "assertionResults": ["x"]}]})}))
    result, _ = do_grade("javascript", tree, plan)
    assert result.outcome == "crash" and result.reason == "runner_crash_after_start"


# G4 -------------------------------------------------------------------------------------------------------------
def test_g4_test_skip_is_not_refused_and_its_two_optional_leaves_are_frozen():
    assert tg.OPTIONAL_LEAVES[("javascript", "palindrome-products")] == frozenset(
        {"palindrome-products.spec.js::Palindromes largest palindrome from four digit factors"})
    assert tg.OPTIONAL_LEAVES[("javascript", "robot-name")] == frozenset(
        {"robot-name.spec.js::Robot all the names can be generated"})
    assert len(tg.OPTIONAL_LEAVES) == 2


def test_g4_tree_with_test_skip_is_graded_and_optional_leaf_is_excluded_from_scoring(tree):
    work, private = tree
    (work / "palindrome-products.spec.js").write_text("test.skip('x', () => {});")
    assert tg.skip_form_violations(work, "javascript") == []
    doc = jest_doc([{"name": "/work/palindrome-products/palindrome-products.spec.js", "status": "passed",
                     "assertionResults": [
                         {"fullName": "Palindromes ok", "status": "passed"},
                         {"fullName": "Palindromes largest palindrome from four digit factors", "status": "pending"}]}])
    guard = FakeGuard(basic_plan("javascript", execute=dict(report={"jest.json": doc})))
    result = tg.grade("javascript", work, "palindrome-products", private, image_id=IMG, guard=guard, run=guard.run_grader)
    assert result.outcome == "parsed"
    assert result.failing({"palindrome-products.spec.js::Palindromes ok"}) == 0
    assert result.leaves["palindrome-products.spec.js::Palindromes largest palindrome from four digit factors"] is False


# G5 -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang,rel", [
    ("javascript", "Jest.config.js"), ("javascript", "BABEL.CONFIG.JS"), ("javascript", ".BabelRC"),
    ("javascript", "Node_Modules/x.js"), ("javascript", "JEST/index.js"), ("javascript", "__Mocks__/fs.js"),
    ("rust", "Build.rs"), ("rust", ".Cargo/config.toml"), ("rust", "Target/x.rs"),
    ("java", "Settings.Gradle"), ("java", "GRADLE.PROPERTIES"), ("java", "BUILD/x.java"),
    ("cpp", "cmakelists.txt"), ("cpp", "Tool.CMAKE"), ("cpp", "CATCH.HPP"), ("cpp", "Catch2/x.hpp"), ("cpp", "BOOST/x.hpp")])
def test_g5_case_variants_of_denied_names_are_tampering(tmp_path, lang, rel):
    assert reasons_for(tmp_path, lang, lambda w: write(w, rel))


def test_g5_helper_allowlist_is_case_folded_too(tmp_path):
    # `Jest.config.js` must never be accepted as a plain helper
    assert reasons_for(tmp_path, "javascript", lambda w: write(w, "Jest.config.js"))
    assert reasons_for(tmp_path / "b", "javascript", lambda w: write(w, "X.SPEC.JS"))


def test_g5_case_collisions_are_detected():
    assert tg.case_collisions(["a/Cargo.toml", "a/cargo.TOML", "b"]) == [("a/Cargo.toml", "a/cargo.TOML")]
    assert tg.case_collisions(["a", "b"]) == []


def test_g5_strip_matches_case_variant_directories(tmp_path):
    work, prepared, _ = prep(tmp_path, RUST, ["src/lib.rs"])
    write(work, "Target/debug/x")
    write(work, "NODE_MODULES/a")
    assert sorted(tg.strip_build_outputs(work, prepared)) == ["NODE_MODULES", "Target"]
    assert not (work / "Target").exists()


# G6 -------------------------------------------------------------------------------------------------------------
def test_g6_grade_item_strips_then_tampers_then_grades(tmp_path):
    work, prepared, protected = prep(tmp_path, JS, ["x.js"])
    write(work, "node_modules/jest/index.js", "evil")
    write(work, "x.js", "edited")
    guard = FakeGuard(basic_plan("javascript"))
    result = tg.grade_item("javascript", work, "slug", tmp_path / "private", prepared=prepared, solutions=["x.js"],
                           image_id=IMG, guard=guard, run=guard.run_grader)
    assert result.outcome == "parsed" and result.stripped == ["node_modules"]


def test_g6_grade_item_returns_a_tampered_outcome_without_any_container(tmp_path):
    work, prepared, protected = prep(tmp_path, JS, ["x.js"])
    write(work, "x.spec.js", "changed")
    write(work, "target/y")
    guard = FakeGuard(basic_plan("javascript"))
    keep = tmp_path / "keep"
    result = tg.grade_item("javascript", work, "slug", tmp_path / "private", prepared=prepared, solutions=["x.js"],
                           image_id=IMG, guard=guard, run=guard.run_grader, keep=keep, seq=0, boundary=2, final=True)
    assert result.outcome == "tampered" and result.all_failed and result.stripped == ["target"]
    assert any("x.spec.js" in r for r in result.tamper_reasons) and guard.calls == []
    index = json.loads((keep / "seq-0000/index.json").read_text())
    assert index["outcome"] == "tampered" and index["artifacts"] == {}


def test_g6_grade_item_refuses_missing_prepared_manifest(tmp_path):
    with pytest.raises(TypeError):
        tg.grade_item("javascript", tmp_path, "slug", tmp_path / "p", solutions=["x.js"])


# G13 ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("step,over", [
    ("compile", dict(timeout=True, no_marker=True)),
    ("compile", dict(oom=True, rc=137, no_marker=True)),
    ("compile", dict(rc=1, no_marker=True)),
    ("compile", dict(rc=0, fake_marker=True, no_marker=True)),
    ("execute", dict(timeout=True, no_marker=True)),
    ("execute", dict(oom=True, rc=137, no_marker=True)),
])
def test_g13_resource_outcomes_require_the_nonce_marker_first(tree, step, over):
    with pytest.raises(TransportAbort, match="marker"):
        do_grade("rust", tree, basic_plan("rust", **{step: over}))


def test_g13_compile_script_prints_its_own_marker_right_before_the_compiler(tree):
    _, guard = do_grade("rust", tree, basic_plan("rust"))
    compile_script = guard.calls[3][1][-1]
    assert re.search(r'echo "TG2_COMPILE_START [0-9a-f]{16}"; cargo test --frozen --offline --no-run', compile_script)
    assert "TG2_RUNNER_START" not in compile_script


# G14 ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("body", [
    "/* package org.junit; */\npackage org.assertj.core.api;\npublic class Shadow {}",
    "// x\npackage org . assertj . core;\npublic class Shadow {}",
    "\\u0070ackage org.assertj.core.api;\npublic class Shadow {}",
    "\\uuu0070ackage org.assertj;\npublic class Shadow {}",
    "package org.assertj\\u002ecore;\npublic class Shadow {}",
    "package\n  org.junit.jupiter;\nclass Shadow {}",
    "package  /* hidden */ org.json ;\nclass Shadow {}",
])
def test_g14_hidden_or_escaped_package_declarations_are_still_denied(tmp_path, body):
    assert reasons_for(tmp_path, "java", lambda w: write(w, "src/main/java/Shadow.java", body))


def test_g14_package_must_agree_with_path(tmp_path):
    files = dict(JAVA, **{"src/main/java/pkg/Foo.java": "package pkg;\npublic class Foo {}\n"})
    sols = ["src/main/java/pkg/Foo.java"]
    assert reasons_for(tmp_path, "java", lambda w: write(w, "src/main/java/pkg/H.java", "package other;\nclass H {}\n"),
                       files=files, solutions=sols)
    assert reasons_for(tmp_path / "b", "java", lambda w: write(w, "src/main/java/pkg/H.java", "class H {}\n"),
                       files=files, solutions=sols)
    assert reasons_for(tmp_path / "c", "java", lambda w: write(w, "src/main/java/pkg/H.java", "package pkg;\nclass H {}\n"),
                       files=files, solutions=sols) == []


def test_g14_comment_and_string_lookalikes_do_not_create_false_denials(tmp_path):
    body = '// package org.junit;\nclass Helper { String s = "package org.assertj;"; /* package x; */ }\n'
    assert reasons_for(tmp_path, "java", lambda w: write(w, "src/main/java/Helper.java", body)) == []


def test_g14_secondary_top_level_type_duplicating_a_test_class_is_denied(tmp_path):
    body = "class Helper {}\nclass FooTest {}\n"
    assert reasons_for(tmp_path, "java", lambda w: write(w, "src/main/java/Helper.java", body))


# G15 ------------------------------------------------------------------------------------------------------------
def test_g15_containers_are_pid_file_and_output_bounded(tree):
    _, guard = do_grade("rust", tree, basic_plan("rust"))
    for step, cmd in guard.calls[1:]:
        text = " ".join(cmd)
        assert "--pids-limit" in text and "--ulimit nofile=" in text and "--ulimit fsize=" in text, step
    for step, cmd in guard.calls[3:]:
        assert "head -c" in cmd[-1] and "PIPESTATUS" in cmd[-1], step


def test_g15_output_over_the_cap_after_start_is_a_model_outcome(tree, monkeypatch):
    monkeypatch.setattr(tg, "OUTPUT_CAP", 1000)
    result, _ = do_grade("rust", tree, basic_plan("rust", execute=dict(big_stdout=5000)))
    assert result.outcome == "output_cap" and result.all_failed


def test_g15_oversized_or_excessive_reports_are_report_errors(tree, monkeypatch):
    monkeypatch.setattr(tg, "REPORT_CAP", 50)
    result, _ = do_grade("javascript", tree, basic_plan("javascript"))
    assert result.outcome == "crash" and result.reason == "runner_crash_after_start"
    assert "cap" in result.reason_detail


# G16 ------------------------------------------------------------------------------------------------------------
def test_g16_private_and_keep_must_be_disjoint_from_the_mounted_tree(tree, tmp_path):
    work, private = tree
    guard = FakeGuard(basic_plan("rust"))
    for kw in (dict(private=work / "p"), dict(keep=work / "k"), dict(private=tmp_path), dict(keep=tmp_path)):
        args = dict(private=private, keep=None, seq=0, boundary=0)
        args.update(kw)
        with pytest.raises(TransportAbort, match="disjoint"):
            tg.grade("rust", work, "slug", args.pop("private"), image_id=IMG, guard=guard, run=guard.run_grader, **args)
    assert guard.calls == []
    with pytest.raises(TransportAbort, match="disjoint"):
        tg.generate_cargo_locks(work, "slug", work / "p", image_id=IMG, run=guard.run_grader)


# G17 ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("over", [dict(inspect_rc=1), dict(inspect_out="garbage"), dict(inspect_out="")])
def test_g17_unverifiable_container_state_aborts(tree, over):
    with pytest.raises(TransportAbort, match="container state"):
        do_grade("rust", tree, basic_plan("rust", execute=dict(over)))


# ============================================================================================ round-3 (G18-G20, P361)
# G18: reports reach the host only as a tar stream emitted by a collect step; model-created symlinks, FIFOs and device
# entries inside the report area become tar members that are refused, never opened on the host.
J = b'{"success": true, "testResults": []}'


@pytest.mark.parametrize("members", [
    [("jest.json", "symlink", "/etc/passwd")],
    [("jest.json", "fifo", None)],
    [("jest.json", "chr", None)],
    [("sub", "symlink", "/etc"), ("sub/jest.json", "file", J)],
    [("../jest.json", "file", J)],
    [("/abs/jest.json", "file", J)],
    [("other.json", "file", J)],
    [],
])
def test_g18_unsafe_or_unexpected_tar_members_are_report_errors_for_jest(members):
    with pytest.raises(tg.ReportError):
        tg.parse_collect("javascript", make_tar(members))


@pytest.mark.parametrize("members", [
    [("test", "dir", None), ("test/a.xml", "symlink", "/etc/passwd")],
    [("test", "dir", None), ("test/a.xml", "fifo", None)],
    [("test", "dir", None), ("test/a.xml", "chr", None)],
    [("test", "symlink", "/etc"), ("test/a.xml", "file", b"<x/>")],
    [("test", "dir", None), ("test/../../b.xml", "file", b"<x/>")],
])
def test_g18_unsafe_java_tar_members_are_report_errors(members):
    with pytest.raises(tg.ReportError):
        tg.parse_collect("java", make_tar(members))


def test_g18_valid_java_and_single_file_tars_are_returned_by_member_name():
    got = tg.parse_collect("java", make_tar([("test", "dir", None), ("test/A.xml", "file", b"<a/>"),
                                             ("test/note.txt", "file", b"ignored")]))
    assert got == {"A.xml": b"<a/>"}
    assert tg.parse_collect("cpp", make_tar([("cpp.xml", "file", b"<c/>")])) == {"cpp.xml": b"<c/>"}


def test_g18_hostile_tar_after_start_is_a_model_outcome_and_nothing_is_read_from_the_host_tree(tree):
    plan = basic_plan("javascript", collect=dict(tar=make_tar([("jest.json", "symlink", "/etc/passwd")])))
    result, _ = do_grade("javascript", tree, plan)
    assert result.outcome == "crash" and result.reason == "runner_crash_after_start"


def test_g18_collect_marker_absent_is_infrastructure(tree):
    with pytest.raises(TransportAbort, match="marker"):
        do_grade("javascript", tree, basic_plan("javascript", collect=dict(no_marker=True)))


# G19: aggregate storage bound -> per-grade size-limited tmpfs volumes; the host tree is only a read-only stage source.
def test_g19_work_and_report_live_on_size_limited_volumes_held_open_and_removed(tree):
    _, guard = do_grade("java", tree, basic_plan("java"))
    creates = [c for c in guard.volume_ops if c[2] == "create"]
    assert len(creates) == 2 and all("type=tmpfs" in " ".join(c) and "size=" in " ".join(c) for c in creates)
    assert guard.holders and "sleep" in guard.holders[0] and "7200" not in guard.holders[0]
    assert guard.volumes == {} and any(c[2] == "rm" for c in guard.volume_ops)       # removed again
    assert guard.removed.count(guard.registered[0]) >= 1


def test_g19_volumes_and_holder_are_removed_on_infrastructure_abort_too(tree):
    guard = FakeGuard(basic_plan("rust", execute=dict(no_marker=True)))
    with pytest.raises(TransportAbort):
        tg.grade("rust", tree[0], "slug", tree[1], image_id=IMG, guard=guard, run=guard.run_grader)
    assert guard.volumes == {} and set(guard.removed) == set(guard.registered)


def test_g19_oversized_input_tree_is_a_model_outcome_without_any_container(tree, monkeypatch):
    monkeypatch.setattr(tg, "TREE_CAP", 10)
    (tree[0] / "big.bin").write_bytes(b"x" * 100)
    guard = FakeGuard(basic_plan("rust"))
    result = tg.grade("rust", tree[0], "slug", tree[1], image_id=IMG, guard=guard, run=guard.run_grader)
    assert result.outcome == "storage_cap" and result.all_failed and guard.calls == []


def test_g19_cumulative_report_size_is_capped_during_parsing(monkeypatch):
    monkeypatch.setattr(tg, "REPORT_CAP", 100)
    members = [("test", "dir", None)] + [("test/%d.xml" % i, "file", b"x" * 60) for i in range(3)]
    with pytest.raises(tg.ReportError, match="cap"):
        tg.parse_collect("java", make_tar(members))
    monkeypatch.setattr(tg, "MAX_JUNIT_FILES", 2)
    monkeypatch.setattr(tg, "REPORT_CAP", 10_000)
    with pytest.raises(tg.ReportError, match="cap"):
        tg.parse_collect("java", make_tar(members))


# P361: bind-mount sources under $TMPDIR or /var/folders serve stale file sizes on OrbStack.
def test_p361_mount_source_under_tmpdir_is_refused(tmp_path):
    import tempfile
    bad = Path(tempfile.mkdtemp())
    try:
        (bad / "f").write_text("x")
        guard = FakeGuard(basic_plan("rust"))
        with pytest.raises(TransportAbort, match="TMPDIR"):
            tg.grade("rust", bad, "slug", tmp_path / "p", image_id=IMG, guard=guard, run=guard.run_grader)
        with pytest.raises(TransportAbort, match="TMPDIR"):
            tg.generate_cargo_locks(bad, "slug", tmp_path / "p", image_id=IMG, run=guard.run_grader)
        assert guard.calls == []
    finally:
        shutil.rmtree(bad, ignore_errors=True)


@pytest.mark.parametrize("path", ["/var/folders/zz/x/T/tree", "/private/var/folders/zz/x/T/tree"])
def test_p361_var_folders_prefixes_are_refused_by_name(path):
    with pytest.raises(TransportAbort, match="TMPDIR"):
        tg.refuse_tmp_source(Path(path))


# ============================================================================================ round-4 (G21-G24)
def labels_of(cmd):
    return dict(x.split("=", 1) for i, x in enumerate(cmd) if cmd[i - 1] == "--label")


# G21 ------------------------------------------------------------------------------------------------------------
def test_g21_volumes_and_holder_carry_ownership_labels_and_the_holder_self_expires(tree):
    _, guard = do_grade("java", tree, basic_plan("java"), timeout=100)
    for c in (c for c in guard.volume_ops if c[2] == "create"):
        assert labels_of(c)["mlxbench.tg2"] == "1" and labels_of(c)["mlxbench.tg2.created"].isdigit()
    holder = guard.holders[0]
    assert labels_of(holder)["mlxbench.tg2"] == "1"
    assert holder[-2] == "sleep" and int(holder[-1]) == 5 * 100 + 300           # bounded by the grade timeout


def test_g21_cleanup_continues_past_every_failure_and_surfaces_uncertainty_on_success(tree, tmp_path):
    guard = FakeGuard(basic_plan("rust", holder_rm=dict(raise_=1), volume_rm=dict(rc=1)))
    guard.plan.steps["holder_rm"] = {"raise": True}
    with pytest.raises(TransportAbort, match="cleanup uncertain") as exc:
        tg.grade("rust", tree[0], "slug", tree[1], image_id=IMG, guard=guard, run=guard.run_grader)
    assert "volume" in str(exc.value) and "holder" in str(exc.value).lower() or "container" in str(exc.value)
    rms = [c for c in guard.volume_ops if c[2] == "rm"]
    assert len(rms) == 2                                                    # both volumes attempted despite failures


def test_g21_original_exception_is_preserved_with_cleanup_notes(tree):
    guard = FakeGuard(basic_plan("rust", execute=dict(no_marker=True), volume_rm=dict(timeout=True)))
    with pytest.raises(TransportAbort, match="marker") as exc:
        tg.grade("rust", tree[0], "slug", tree[1], image_id=IMG, guard=guard, run=guard.run_grader)
    assert any("cleanup" in n for n in getattr(exc.value, "__notes__", []))
    assert len([c for c in guard.volume_ops if c[2] == "rm"]) == 2


def test_g21_registry_entry_exists_during_the_grade_and_is_removed_after_verified_cleanup(tree):
    work, private = tree
    guard = FakeGuard(basic_plan("rust"))
    seen = []
    inner = guard.run_grader

    def run(cmd, **kw):
        if step_of(cmd) == "preflight":
            seen.append(sorted(p.name for p in (private / ".tg2-registry").glob("*.json")))
        return inner(cmd, **kw)

    tg.grade("rust", work, "slug", private, image_id=IMG, guard=guard, run=run)
    assert len(seen[0]) == 1 and not list((private / ".tg2-registry").glob("*.json"))


def test_g21_registry_entry_survives_uncertain_cleanup(tree):
    work, private = tree
    guard = FakeGuard(basic_plan("rust", volume_rm=dict(rc=1)))
    with pytest.raises(TransportAbort):
        tg.grade("rust", work, "slug", private, image_id=IMG, guard=guard, run=guard.run_grader)
    assert len(list((private / ".tg2-registry").glob("*.json"))) == 1


def _leftover(guard, vol="mlxbench-tg2-aaaaaaaaaaaa-w", holder="old-holder", registry=None):
    (guard.vroot / vol).mkdir(exist_ok=True)
    guard.volumes[vol] = guard.vroot / vol
    guard.volume_labels[vol] = {"mlxbench.tg2": "1", "mlxbench.tg2.created": "1"}
    guard.holder_names[holder] = {"mlxbench.tg2": "1", "mlxbench.tg2.created": "1"}
    return vol, holder


def test_p363_list_leftovers_lists_labelled_objects_only_and_deletes_nothing(tree):
    guard = FakeGuard(basic_plan("rust"))
    vol, holder = _leftover(guard)
    guard.volumes["unlabelled-tg2-volume"] = guard.vroot
    guard.volume_labels["unlabelled-tg2-volume"] = {}
    guard.holder_names["foreign"] = {}
    out = tg.list_leftovers(guard.run_grader, tree[1])
    assert out == dict(containers=[holder], volumes=[vol])
    assert vol in guard.volumes and holder in guard.holder_names             # nothing was removed
    assert not hasattr(tg, "sweep_leftovers")


def test_p363_grade_refuses_to_start_while_a_labelled_leftover_exists(tree):
    guard = FakeGuard(basic_plan("rust"))
    vol, holder = _leftover(guard)
    with pytest.raises(TransportAbort, match="leftover") as exc:
        tg.grade("rust", tree[0], "slug", tree[1], image_id=IMG, guard=guard, run=guard.run_grader)
    assert vol in str(exc.value) and holder in str(exc.value) and "tg2_cleanup.py" in str(exc.value)
    assert guard.calls == [("image", guard.calls[0][1])] and not guard.holders      # nothing was started
    assert vol in guard.volumes                                                     # and nothing was deleted


def test_p363_a_clean_box_starts_and_the_grades_own_objects_never_count_as_leftovers(tree):
    guard = FakeGuard(basic_plan("rust"))
    result = tg.grade("rust", tree[0], "slug", tree[1], image_id=IMG, guard=guard, run=guard.run_grader)
    assert result.outcome == "parsed" and tg.list_leftovers(guard.run_grader, tree[1]) == dict(containers=[], volumes=[])


def _registry(private, vol, holder, extra=None):
    d = private / ".tg2-registry"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "mlxbench-tg2-aaaaaaaaaaaa.json"
    path.write_text(json.dumps(dict(base="mlxbench-tg2-aaaaaaaaaaaa", volumes=[vol, vol[:-1] + "r"], holder=holder,
                                    created=1, **(extra or {}))))
    return path


def test_p363_remove_registered_removes_exactly_the_recorded_names_and_verifies(tree):
    work, private = tree
    guard = FakeGuard(basic_plan("rust"))
    vol, holder = _leftover(guard)
    other_vol, other_holder = _leftover(guard, vol="mlxbench-tg2-bbbbbbbbbbbb-w", holder="other-holder")
    guard.volumes["mlxbench-tg2-aaaaaaaaaaaa-r"] = guard.vroot
    guard.volume_labels["mlxbench-tg2-aaaaaaaaaaaa-r"] = {"mlxbench.tg2": "1", "mlxbench.tg2.created": "1"}
    reg = _registry(private, vol, holder)
    out = tg.remove_registered(guard.run_grader, reg, private)
    assert sorted(out["volumes"]) == sorted([vol, "mlxbench-tg2-aaaaaaaaaaaa-r"]) and out["containers"] == [holder]
    assert other_vol in guard.volumes and other_holder in guard.holder_names          # not recorded: untouched
    assert not reg.exists()                                                           # registry retired after verification


@pytest.mark.parametrize("doc", [
    dict(volumes=["../../etc"], holder="h"), dict(volumes=["someone-elses-volume"], holder="h"),
    dict(volumes="x", holder="h"), dict(volumes=[], holder=""), "not-an-object",
])
def test_p363_remove_registered_refuses_malformed_or_foreign_names(tree, doc):
    work, private = tree
    guard = FakeGuard(basic_plan("rust"))
    reg = private / "reg.json"
    reg.write_text(json.dumps(doc))
    with pytest.raises(TransportAbort, match="registry"):
        tg.remove_registered(guard.run_grader, reg, private)


def test_p363_remove_registered_refuses_a_holder_without_the_ownership_label(tree):
    work, private = tree
    guard = FakeGuard(basic_plan("rust"))
    vol, _ = _leftover(guard)
    guard.holder_names["h-unlabelled"] = {}
    reg = _registry(private, vol, "h-unlabelled")
    with pytest.raises(TransportAbort, match="label"):
        tg.remove_registered(guard.run_grader, reg, private)
    assert "h-unlabelled" in guard.holder_names and vol in guard.volumes


def test_p363_remove_registered_fails_loudly_when_removal_cannot_be_verified(tree):
    work, private = tree
    guard = FakeGuard(basic_plan("rust", volume_rm=dict(rc=1)))
    vol, holder = _leftover(guard)
    reg = _registry(private, vol, holder)
    with pytest.raises(TransportAbort, match="verif"):
        tg.remove_registered(guard.run_grader, reg, private)
    assert reg.exists()


# G22 ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("over,outcome", [(dict(timeout=True), "timeout"), (dict(oom=True, rc=137), "oom"),
                                          (dict(mem_kill=True, rc=137), "mem_kill")])
def test_g22_collect_resource_exhaustion_after_its_marker_is_a_resource_outcome(tree, over, outcome):
    result, _ = do_grade("javascript", tree, basic_plan("javascript", collect=over))
    assert result.outcome == outcome and result.all_failed


# G24 ------------------------------------------------------------------------------------------------------------
def test_g24_duplicate_tar_member_keys_are_rejected():
    dup = make_tar([("test", "dir", None), ("test/A.xml", "file", b"<a/>"), ("test/A.xml", "file", b"<b/>")])
    with pytest.raises(tg.ReportError, match="duplicate"):
        tg.parse_collect("java", dup)
    with pytest.raises(tg.ReportError, match="duplicate"):
        tg.parse_collect("javascript", make_tar([("jest.json", "file", J), ("jest.json", "file", J)]))


def test_g24_extracted_length_must_equal_the_declared_size(monkeypatch):
    import tarfile as tf

    class Short:
        def read(self, n):
            return b"x"

    real = tf.TarFile.extractfile
    monkeypatch.setattr(tf.TarFile, "extractfile", lambda self, m: Short())
    with pytest.raises(tg.ReportError, match="size"):
        tg.parse_collect("cpp", make_tar([("cpp.xml", "file", b"<c/>")]))
    monkeypatch.setattr(tf.TarFile, "extractfile", real)


# G23 ------------------------------------------------------------------------------------------------------------
def test_g23_test_trees_are_rooted_outside_tmpdir(tmp_path):
    with pytest.raises(TransportAbort):
        tg.refuse_tmp_source(Path(__import__("tempfile").gettempdir()) / "x")
    tg.refuse_tmp_source(tmp_path)          # the overriding fixture lives under $STACK_WORKDIR, never TMPDIR


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


def _docker_env():
    docker_bin = shutil.which("docker") or str(Path.home() / ".orbstack/bin/docker")
    os.environ["PATH"] = str(Path(docker_bin).parent) + os.pathsep + os.environ["PATH"]


def _prepared(stub):
    return sg.manifest(stub)


def _item(tmp_path, lang, slug, guard):
    """(prepared stub tree, its manifest, solutions) with Rust lockfiles generated offline at preparation."""
    from bench.tests import tg2_trees
    stub = tg2_trees.stub_tree(POLYGLOT, lang, slug, tmp_path / "stub")
    if lang == "rust":
        tg.generate_cargo_locks(stub, slug, tmp_path / "private", guard=guard)
    return stub, _prepared(stub), tg2_trees.solutions(POLYGLOT, lang, slug)


def _ref_of(tmp_path, stub, lang, slug):
    from bench.tests import tg2_trees
    ref = tmp_path / "ref"
    shutil.copytree(stub, ref)
    return tg2_trees.apply_reference(POLYGLOT, lang, slug, ref)


@pytest.mark.docker
@pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")
def test_javascript_solution_calling_process_exit_is_a_model_failure_not_infrastructure(tmp_path):
    _docker_env()
    guard = tg.LocalDocker()
    stub, prepared, sols = _item(tmp_path, "javascript", "affine-cipher", guard)
    ref = _ref_of(tmp_path, stub, "javascript", "affine-cipher")
    (ref / "affine-cipher.js").write_text("process.exit(1);\n")
    (ref / "node_modules").mkdir()                                   # planted artefact: stripped before grading
    (ref / "node_modules/jest").mkdir()
    result = tg.grade_item("javascript", ref, "affine-cipher", tmp_path / "private", prepared=prepared,
                           solutions=sols, guard=guard, timeout=300)
    assert result.stripped == ["node_modules"]
    assert result.outcome in ("crash", "parsed") and result.passing == set()
    assert result.failing({"x"}) >= 1


@pytest.mark.docker
@pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")
def test_suite_level_afterall_failure_is_a_counted_failure_in_the_real_runner(tmp_path):
    _docker_env()
    guard = tg.LocalDocker()
    stub, prepared, sols = _item(tmp_path, "javascript", "affine-cipher", guard)
    ref = _ref_of(tmp_path, stub, "javascript", "affine-cipher")
    clean = tg.grade_item("javascript", ref, "affine-cipher", tmp_path / "private", prepared=prepared, solutions=sols,
                          guard=guard, timeout=300)
    universe = set(clean.collected)
    assert clean.failing(universe) == 0
    body = (ref / "affine-cipher.js").read_text()
    (ref / "affine-cipher.js").write_text("afterAll(() => { throw new Error('teardown boom'); });\n" + body)
    bad = tg.grade_item("javascript", ref, "affine-cipher", tmp_path / "private", prepared=prepared, solutions=sols,
                        guard=guard, timeout=300)
    assert bad.outcome == "parsed" and bad.failing(universe) >= 1, (bad.outcome, bad.leaves)


HOSTILE = {                                            # shell run by a detached child AFTER jest wrote its report
    "symlink": "ln -s /etc/passwd /report/jest.json",
    "fifo": "mkfifo /report/jest.json",
    "oversize": "head -c 34000000 /dev/zero > /report/jest.json",
}


@pytest.mark.docker
@pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")
@pytest.mark.parametrize("kind", sorted(HOSTILE))
def test_g23_hostile_report_replaced_by_the_solution_is_a_model_failure_in_the_real_runner(tmp_path, kind):
    _docker_env()
    guard = tg.LocalDocker()
    stub, prepared, sols = _item(tmp_path, "javascript", "affine-cipher", guard)
    ref = _ref_of(tmp_path, stub, "javascript", "affine-cipher")
    # Deterministic: the detached child polls until /report/jest.json parses as complete JSON (jest has finished writing
    # it), then replaces it. It inherits stdout, so the bounded-output pipe (and the container) stays up until then.
    wait = ("for i in $(seq 1 600); do python3 -c \"import json;json.load(open('/report/jest.json'))\" 2>/dev/null "
            "&& break; sleep 0.2; done")
    hook = ("require('child_process').spawn('sh', ['-c', %r], "
            "{detached: true, stdio: ['ignore', 'inherit', 'inherit']}).unref();\n"
            % ("%s; rm -f /report/jest.json; %s" % (wait, HOSTILE[kind])))
    (ref / "affine-cipher.js").write_text(hook + (ref / "affine-cipher.js").read_text())
    result = tg.grade_item("javascript", ref, "affine-cipher", tmp_path / "private", prepared=prepared,
                           solutions=sols, guard=guard, timeout=300)
    assert result.outcome == "crash" and result.reason == "runner_crash_after_start", (result.outcome, result.reason_detail)
    assert result.all_failed and not guard.leftover() and not guard.leftover_volumes()


@pytest.mark.docker
@pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")
def test_p363_a_killed_grader_leaves_listed_leftovers_that_block_grading_until_explicitly_removed(tmp_path):
    import signal
    import sys
    import textwrap
    _docker_env()
    guard = tg.LocalDocker()
    stub, prepared, sols = _item(tmp_path, "javascript", "affine-cipher", guard)
    bench_root = Path(__file__).resolve().parents[2]
    script = textwrap.dedent("""
        import os, signal, sys
        sys.path.insert(0, %r)
        from bench import tg2_grade as tg
        tg._grade_steps = lambda *a, **k: os.kill(os.getpid(), signal.SIGKILL)
        tg.grade("javascript", %r, "affine-cipher", %r)
    """) % (str(bench_root), str(stub), str(tmp_path / "private"))
    proc = subprocess.run([sys.executable, "-c", script], env=dict(os.environ, PYTHONPATH=str(bench_root)), timeout=120)
    assert proc.returncode == -signal.SIGKILL
    leftovers = tg.list_leftovers(guard.run_grader, tmp_path / "private")
    assert leftovers["volumes"] and leftovers["containers"]                          # real orphaned state, listed
    with pytest.raises(TransportAbort, match="leftover"):                             # and it blocks the next grade
        tg.grade("javascript", stub, "affine-cipher", tmp_path / "private", guard=guard)
    foreign = "mlxbench-tg2-foreign-" + __import__("uuid").uuid4().hex[:6]
    subprocess.run(["docker", "volume", "create", foreign], check=True, capture_output=True)
    try:
        registry = next((tmp_path / "private/.tg2-registry").glob("*.json"))
        cli = subprocess.run([sys.executable, str(bench_root / "m65/tg2_cleanup.py"), "--remove", str(registry),
                              "--private", str(tmp_path / "private")], capture_output=True, text=True, timeout=120)
        assert cli.returncode == 0, cli.stderr
        assert tg.list_leftovers(guard.run_grader, tmp_path / "private") == dict(containers=[], volumes=[])
        listed = subprocess.run(["docker", "volume", "ls", "-q"], capture_output=True, text=True).stdout.split()
        assert foreign in listed                                                     # never touched
    finally:
        subprocess.run(["docker", "volume", "rm", "-f", foreign], capture_output=True)


@pytest.mark.docker
@pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")
def test_tamper_is_caught_through_the_production_entry_point(tmp_path):
    _docker_env()
    guard = tg.LocalDocker()
    stub, prepared, sols = _item(tmp_path, "javascript", "affine-cipher", guard)
    ref = _ref_of(tmp_path, stub, "javascript", "affine-cipher")
    (ref / "Jest.Config.js").write_text("module.exports = { testEnvironment: 'node' };\n")
    result = tg.grade_item("javascript", ref, "affine-cipher", tmp_path / "private", prepared=prepared, solutions=sols,
                           guard=guard, timeout=300)
    assert result.outcome == "tampered" and result.all_failed and not guard.leftover()


@pytest.mark.docker
@pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")
@pytest.mark.parametrize("lang,slug", ITEMS)
def test_reference_all_pass_and_untouched_stub_fails_in_the_built_image(tmp_path, lang, slug):
    _docker_env()
    guard = tg.LocalDocker()
    stub, prepared, sols = _item(tmp_path, lang, slug, guard)
    ref = _ref_of(tmp_path, stub, lang, slug)
    stub_copy = tmp_path / "stub_copy"
    shutil.copytree(stub, stub_copy)
    good = tg.grade_item(lang, ref, slug, tmp_path / "private", prepared=prepared, solutions=sols, guard=guard,
                         timeout=900, keep=tmp_path / "keep", seq=0, boundary=0, final=True)
    assert good.outcome == "parsed", good.phases
    assert good.collected and good.passing == good.collected, sorted(good.collected - good.passing)
    base = tg.grade_item(lang, stub_copy, slug, tmp_path / "private", prepared=prepared, solutions=sols, guard=guard,
                         timeout=900)
    assert base.failing(good.collected) > 0, (base.outcome, base.passing)
    assert not guard.leftover()
