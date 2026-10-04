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
from bench import paths as _paths


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
    # 10th cold review (between-arms fix 2): this FAKE path is pure TEST DATA for the scrubber
    # (never an actual write target) -- replace paths.stack_workdir directly (not just the env
    # var) so the conftest-level real-workdir guard, which wraps the REAL resolver and would
    # otherwise flag this synthetic value as an out-of-bounds write target, is bypassed cleanly.
    monkeypatch.setattr(_paths, "stack_workdir",
                        lambda required=True: Path("/Users/someone/ws/mlx_local_stack_workdir"))  # allow-pii-pattern
    monkeypatch.setenv("STACK_WORKDIR", "/Users/someone/ws/mlx_local_stack_workdir")  # allow-pii-pattern
    monkeypatch.setattr(P.os.path, "expanduser", lambda p: "/Users/someone" if p == "~" else p)  # allow-pii-pattern
    raw = ("Read /Users/someone/ws/mlx_local_stack_workdir/scratch/octmp/oc-x/y failed; "  # allow-pii-pattern
           "also /Users/someone/other/path")  # allow-pii-pattern
    out = P._scrub_pii(raw)
    assert "/Users/someone" not in out
    assert "$STACK_WORKDIR/scratch/octmp/oc-x/y" in out
    assert "$HOME/other/path" in out


def test_scrub_then_tail_scrubs_before_truncating_not_after(monkeypatch):
    """M2 (verifier, 2026-09-05): `_scrub_pii(tail[-300:])` slices BEFORE scrubbing, so a
    `/Users/<name>/...` boundary cut in half leaves a fragment `_scrub_pii` can no longer
    recognize (measured by the verifier: 21 of 399 slice widths leaked the username this way).
    `_scrub_then_tail` must scrub the WHOLE string first, then tail it. This dynamically searches
    for a prefix length that makes the naive (slice-then-scrub) order leak, the same methodology
    the verifier used, so the test doesn't depend on a hand-picked magic width happening to still
    reproduce the bug."""
    # 10th cold review (between-arms fix 2): see test_scrub_pii_replaces_home_and_workdir above --
    # same synthetic-data bypass of the conftest-level real-workdir guard.
    monkeypatch.setattr(_paths, "stack_workdir",
                        lambda required=True: Path("/Users/someone/ws/mlx_local_stack_workdir"))  # allow-pii-pattern
    monkeypatch.setenv("STACK_WORKDIR", "/Users/someone/ws/mlx_local_stack_workdir")  # allow-pii-pattern
    monkeypatch.setattr(P.os.path, "expanduser", lambda p: "/Users/someone" if p == "~" else p)  # allow-pii-pattern
    home_path = "/Users/someone/ws/mlx_local_stack_workdir/scratch/oc-x/y"  # allow-pii-pattern
    # A genuine boundary straddle cuts THROUGH "someone" — the full marker can never survive a
    # straddling slice (that's the whole bug: neither the workdir nor the home replacement can
    # match a partial string), so the leak signal is the bare username fragment, not the full path.
    # The straddle point depends on len(home_path) + len(suffix) relative to `n`, NOT on the
    # prefix length (a longer prefix shifts the cut and the marker forward by the same amount) —
    # so this varies the SUFFIX length to sweep the cut through the marker.
    n = 300
    prefix = "z" * 500  # long enough that the slice never dips into the prefix itself
    leaked_naive = False
    for suffix_len in range(0, 320):
        text = prefix + home_path + ("s" * suffix_len)
        naive = P._scrub_pii(text[-n:])
        if "someone" in naive:  # allow-pii-pattern
            leaked_naive = True
            fixed = P._scrub_then_tail(text, n)
            assert "someone" not in fixed  # allow-pii-pattern
            assert len(fixed) <= n
            break
    assert leaked_naive, "test setup didn't reproduce a boundary straddle — adjust the suffix range"


def test_row_assembly_uses_scrub_then_tail_not_the_broken_slice_then_scrub_order():
    """Regression guard for the M2 call-site bug itself (not just the helper): the row-building
    code in `main()` must call `_scrub_then_tail`, never the old `_scrub_pii(x[-n:])` shape."""
    import inspect
    src = inspect.getsource(P.main)
    assert "_scrub_then_tail(tail, 300)" in src
    assert "_scrub_then_tail(log, 500)" in src
    assert "_scrub_pii(tail[-300:])" not in src
    assert "_scrub_pii(log[-500:])" not in src


# ---------------------------------------------------------------- M46: transcript retention + loop metric
def _tool(name, inp, status="completed", output="ok"):
    return {"type": "tool", "tool": name, "callID": "c", "state": {"status": status, "input": inp, "output": output}}


def _msg(role, parts):
    return {"info": {"role": role}, "parts": parts}


def test_loop_metrics_counts_identical_consecutive_calls_and_repeats_after_error():
    export = {"info": {"id": "ses_x"}, "messages": [
        _msg("user", [{"type": "text", "text": "go"}]),
        _msg("assistant", [_tool("read", {"filePath": "a.py"}), _tool("read", {"filePath": "a.py"}),
                            _tool("read", {"filePath": "a.py"})]),
        _msg("assistant", [_tool("edit", {"filePath": "a.py", "old": "x"}, status="error", output="Error: no match"),
                            _tool("edit", {"filePath": "a.py", "old": "x"}, status="error", output="Error: no match"),
                            _tool("bash", {"command": "pytest"})]),
    ]}
    m = P.loop_metrics(export)
    assert m["tool_calls"] == 6
    assert m["repeat_identical_calls"] == 3          # read×2 extra, edit×1 extra
    assert m["max_identical_run"] == 3
    assert m["calls_repeated_after_error"] == 1      # the second identical failing edit
    assert m["error_calls"] == 2


def test_loop_metrics_handles_empty_or_malformed_export():
    assert P.loop_metrics({})["tool_calls"] == 0
    assert P.loop_metrics({"messages": [{"parts": [{"type": "tool"}]}]})["tool_calls"] == 1


def test_export_latest_session_uses_the_isolated_data_home(monkeypatch, tmp_path):
    calls = []

    def fake_check_output(cmd, **kw):
        calls.append((cmd, kw.get("env", {}).get("XDG_DATA_HOME")))
        if cmd[:3] == ["opencode", "session", "list"]:
            return "Session ID   Title\n────\nses_new111  New session\nses_old222  Older\n"
        if cmd[:2] == ["opencode", "export"]:
            assert cmd[2] == "ses_new111"
            return json.dumps({"info": {"id": "ses_new111"}, "messages": []})
        raise AssertionError(cmd)

    monkeypatch.setattr(P.subprocess, "check_output", fake_check_output)
    data_home = tmp_path / "xdg"
    out = P._export_latest_session(P._opencode_env(data_home), cwd=tmp_path)
    assert out["info"]["id"] == "ses_new111"
    assert all(h == str(data_home) for _, h in calls)


def test_export_latest_session_degrades_to_none_when_no_session(monkeypatch, tmp_path):
    monkeypatch.setattr(P.subprocess, "check_output", lambda cmd, **kw: "Session ID   Title\n")
    assert P._export_latest_session(P._opencode_env(tmp_path), cwd=tmp_path) is None


def test_opencode_env_redirects_only_the_data_home(tmp_path):
    env = P._opencode_env(tmp_path / "xdg")
    assert env["XDG_DATA_HOME"] == str(tmp_path / "xdg")
    assert "XDG_CACHE_HOME" not in env or env["XDG_CACHE_HOME"] == __import__("os").environ.get("XDG_CACHE_HOME")


def test_transcript_path_is_under_workdir_with_placeholder(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    p, rel = P._transcript_target("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "python", "beer-song", tag="m46")
    assert p == tmp_path / "opencode_transcripts" / "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed" / "m46" / "python__beer-song.json"
    assert rel == "$STACK_WORKDIR/opencode_transcripts/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/m46/python__beer-song.json"


# ---------------------------------------------------------------- C103: scaffold independence from the machine's skill trees
def test_opencode_env_disables_external_skill_trees(tmp_path):
    """opencode lists every skill it finds under ~/.claude/skills (incl. synced/ and .trash/) and
    ~/.agents/skills in its system prompt, with file paths. Measured 2026-09-27: 17 skills, half the
    system prompt, paths that change between processes. The probe's scaffold must not depend on what
    Claude Code happens to have synced on this machine."""
    env = P._opencode_env(tmp_path / "xdg")
    assert env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "true"


def test_manifest_runtime_records_the_skill_policy_and_config_hash(monkeypatch, tmp_path):
    cfg = tmp_path / "opencode.json"; cfg.write_text('{"model": "x"}')
    monkeypatch.setattr(P, "SHIPPED_OPENCODE_CONFIG", cfg)
    rt = P._scaffold_runtime()
    assert rt["skill_policy"] == "OPENCODE_DISABLE_EXTERNAL_SKILLS=true"
    import hashlib
    assert rt["opencode_config_sha256"] == hashlib.sha256(cfg.read_bytes()).hexdigest()
    assert rt["opencode_config"] == "opencode_config/opencode.json"


# ------------------------------------------------- M53: STACK_WORKDIR resolved at ENTRY, config.sh fallback
def _config_sh(tmp_path, monkeypatch, body):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    d = tmp_path / "xdg" / "mlx_local_stack"
    d.mkdir(parents=True)
    (d / "config.sh").write_text(body)


def test_stack_workdir_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "env"))
    _config_sh(tmp_path, monkeypatch, 'export STACK_WORKDIR="/nope"\n')
    assert P._stack_workdir() == tmp_path / "env"


def test_stack_workdir_falls_back_to_config_sh_and_expands_home(monkeypatch, tmp_path):
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _config_sh(tmp_path, monkeypatch,
               '# comment\nexport STACK_REPO="$HOME/ws/repo"\nexport STACK_WORKDIR="$HOME/ws/wd"\n')
    assert P._stack_workdir() == tmp_path / "home" / "ws" / "wd"
    t_abs, rel = P._transcript_target("m", "python", "x", tag="t")
    assert t_abs == tmp_path / "home" / "ws" / "wd" / "opencode_transcripts" / "m" / "t" / "python__x.json"
    assert rel == "$STACK_WORKDIR/opencode_transcripts/m/t/python__x.json"


def test_stack_workdir_missing_everywhere_exits_naming_the_variable(monkeypatch, tmp_path):
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    try:
        P._stack_workdir()
        raised = False
    except SystemExit as e:
        raised = True; msg = str(e)
    assert raised and "STACK_WORKDIR" in msg


def test_entry_refuses_missing_workdir_before_m50_and_before_any_request(monkeypatch, tmp_path):
    """Attempt 1 on 2026-09-29 ran a whole item (~1.5 min of worker time) before the transcript
    writer noticed STACK_WORKDIR was unset. The check must fire at entry, before the M50 guard."""
    from bench import provenance
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    monkeypatch.setattr(P, "_opencode_version", lambda: P.PINNED_OPENCODE_VERSION)

    def boom(*a, **k):
        raise AssertionError("reached M50 / the router before the workdir check")
    monkeypatch.setattr(provenance, "opencode_router_base", boom)
    monkeypatch.setattr(provenance, "assert_served_config", boom)
    monkeypatch.setattr(sys, "argv", ["run_opencode_probe.py", "--model", "m", "--items", "x", "--lang", "python"])
    try:
        P.main()
        raised = False
    except SystemExit as e:
        raised = True; msg = str(e)
    assert raised and "STACK_WORKDIR" in msg


# ------------------------------------------------- D12: harness-traffic accounting per row
def _amsg(inp, out, reasoning=0):
    return {"info": {"role": "assistant", "tokens": {"input": inp, "output": out, "reasoning": reasoning,
                                                     "cache": {"read": 0, "write": 0}}}, "parts": []}


def test_traffic_metrics_reports_cumulative_and_incremental_input():
    # opencode's per-message `tokens.input` is the INCREMENTAL prompt (verified 2026-09-29 against the
    # router's session-cache deltas); the router re-reads the whole context each turn, so the
    # cumulative figure is the running-sum total. Both are reported; the gap is the session-cache saving.
    export = {"info": {"id": "ses"}, "messages": [
        {"info": {"role": "user"}, "parts": []}, _amsg(100, 5), _amsg(20, 6), _amsg(30, 7)]}
    t = P.traffic_metrics(export)
    assert t == {"turns": 3, "input_tokens_incremental": 150, "input_tokens_cumulative": 370,
                 "output_tokens": 18, "max_context": 150}


def test_traffic_metrics_handles_empty_or_malformed_export():
    assert P.traffic_metrics({}) == {"turns": 0, "input_tokens_incremental": 0, "input_tokens_cumulative": 0,
                                     "output_tokens": 0, "max_context": 0}
    assert P.traffic_metrics({"messages": [{"info": {"role": "assistant"}}]})["turns"] == 1


def test_scrub_pii_replaces_login_name_in_ls_owner_column(monkeypatch, tmp_path):
    """`ls -l` output captured in log tails carries the login name in the owner column
    ("drwxr-xr-x@ 7 <user>  staff ..."), which the path-only scrub left in 6 landed M55 rows
    (2026-10-04). The whole-word login name must become $USER; substrings inside other words
    must not be touched."""
    import run_opencode_probe as p
    monkeypatch.setattr(p, "_stack_workdir", lambda required=False: None)
    monkeypatch.setattr(p.os.path, "expanduser", lambda s: "/Users/zed" if s == "~" else s)  # allow-pii-pattern (synthetic)
    monkeypatch.setattr(p, "_login_name", lambda: "zed")
    out = p._scrub_pii("drwxr-xr-x@ 7 zed  staff   224 Oct  4 .\n/Users/zed/x zedx dazed")  # allow-pii-pattern (synthetic)
    assert out == "drwxr-xr-x@ 7 $USER  staff   224 Oct  4 .\n$HOME/x zedx dazed"
