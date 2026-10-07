"""Shared opencode mechanics: retained unit tests from the frozen 1.18 probe."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from bench import opencode_common as P
from bench import paths as _paths
from bench import rowschema
from bench.opencode_common import _scratch_dir



@pytest.fixture
def resume_case(tmp_path):
    """Shared resume checks without the frozen main() or a binary fixture."""
    identity = {key: f"original-{key}" for key in P.RESUME_IDENTITY_KEYS}
    identity["seed_base"] = 1
    doc = {"runtime": dict(identity), "model": "m",
           "git": {"serving_path": {"mlx-vlm": "original"}},
           "router": {"config_sha256": "original"}}
    return doc, identity, tmp_path / "rows.jsonl"


@pytest.mark.parametrize("key", P.RESUME_IDENTITY_KEYS)
def test_resume_helper_refuses_each_changed_identity_field(resume_case, key):
    doc, identity, out = resume_case
    P._check_resume(doc, identity, out)
    doc["runtime"][key] = "changed"
    with pytest.raises(SystemExit, match=key):
        P._check_resume(doc, identity, out)
    del doc["runtime"][key]
    with pytest.raises(SystemExit, match="pre-C121"):
        P._check_resume(doc, identity, out)


@pytest.mark.parametrize("flag", ["served_config_drift", "cache_bin_inventory_drift"])
def test_resume_helper_refuses_prior_drift(resume_case, flag):
    doc, identity, out = resume_case
    doc[flag] = {"error": "drift"}
    with pytest.raises(SystemExit, match=flag):
        P._check_resume(doc, identity, out)


def test_resume_helper_checks_model_serving_code_and_router(resume_case):
    doc, identity, out = resume_case
    P._check_resume(doc, identity, out, doc["router"], model="m", git_now=doc["git"])
    with pytest.raises(SystemExit, match="model differs"):
        P._check_resume(doc, identity, out, model="other")
    with pytest.raises(SystemExit, match="serving-code identity"):
        P._check_resume(doc, identity, out, git_now={"serving_path": {"mlx-vlm": "changed"}})
    with pytest.raises(SystemExit, match="router.config_sha256"):
        P._check_resume(doc, identity, out, {"config_sha256": "changed"})
    with pytest.raises(SystemExit, match="no manifest"):
        P._check_resume(None, identity, out)


def test_load_rows_returns_recorded_keys(tmp_path):
    out = tmp_path / "rows.jsonl"
    assert P._load_rows(out) == set()
    out.write_text('{"id":"python/x","sample":0}\n{"id":"python/y"}\n')
    assert P._load_rows(out) == {("python/x", 0), ("python/y", 0)}


@pytest.mark.parametrize("tail,needle", [
    ('{"id": "python/x", "sam', "line 2"),
    ('{"id": "python/x", "sample": 0}', "unterminated"),
    ('not json\n', "line 2"),
])
def test_load_rows_refuses_corrupt_tail(tmp_path, tail, needle):
    out = tmp_path / "rows.jsonl"
    out.write_text('{"id":"python/x","sample":0}\n' + tail)
    with pytest.raises(SystemExit, match=needle):
        P._load_rows(out)


def test_item_seed_is_distinct_per_item_reproducible_and_base_dependent():
    s = {i: P._item_seed(i, 1) for i in ("python/a", "python/b", "go/c")}
    assert len(set(s.values())) == 3
    assert s["python/a"] == P._item_seed("python/a", 1) == rowschema.sample_seed("python/a", 0, base=1)
    assert P._item_seed("python/a", 2) != s["python/a"]


def test_row_seed_fields():
    f = P._seed_row_fields("python/a", 7, "abc")
    assert f == {"sampler_seed": rowschema.sample_seed("python/a", 0, base=7), "seed_base": 7,
                 "overlay_sha256": "abc"}


def test_cache_bin_inventory_hash_tracks_files_under_the_shared_cache(tmp_path):
    cache = tmp_path / "cache"; (cache / "opencode" / "bin").mkdir(parents=True)
    (cache / "opencode" / "bin" / "rg").write_text("ripgrep-1")
    h1 = P._cache_bin_inventory_sha256(cache)
    assert h1 == P._cache_bin_inventory_sha256(cache)
    (cache / "opencode" / "bin" / "lsp-server").write_text("x")          # a new tool appears
    h2 = P._cache_bin_inventory_sha256(cache)
    assert h2 != h1
    (cache / "opencode" / "bin" / "rg").write_text("ripgrep-2")           # same size, different content
    assert P._cache_bin_inventory_sha256(cache) != h2
    (cache / "opencode" / "models.json").write_text("{}")                 # the catalogue is NOT inventoried
    h3 = P._cache_bin_inventory_sha256(cache)
    (cache / "opencode" / "models.json").write_text('{"a": 1}')
    assert P._cache_bin_inventory_sha256(cache) == h3
    assert P._cache_bin_inventory_sha256(tmp_path / "absent") == P._cache_bin_inventory_sha256(tmp_path / "absent2")


def test_error_strings_are_pii_scrubbed_before_truncation(monkeypatch, tmp_path):
    home = str(Path.home())
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    monkeypatch.setattr(P, "_login_name", lambda: "someoperator")
    msg = "x" * 5 + f" failed in {home}/ws/scratch/oc-1/ex as someoperator ({home}/.cache/opencode)"
    out = P._scrub_error(msg, limit=40)
    assert home not in out and "someoperator" not in out
    # a cut through the home prefix cannot leave a partial prefix: scrub the whole text first, then cut
    cut = P._scrub_error("a" * 20 + home + "/deep/path", limit=len("a" * 20) + 6)
    assert home not in cut and "$HOME" in cut[:30]


def test_tick_snapshots_are_confined_to_the_run_temp_dir(tmp_path):
    work = tmp_path / "work"; work.mkdir()
    sol = work / "sol.py"; test = work / "t.py"
    sol.write_text("before"); test.write_text("x"); log = work / "log.txt"; log.write_text("")
    runtmp = tmp_path / "runtmp"; runtmp.mkdir()
    seen = []

    def grade(w, t):
        seen.append(Path(w)); return True, ""
    snap = P._tick_snapshot_fn(work, sol, test, "before", grade, log, tmp_dir=runtmp)
    sol.write_text("after")
    snap(1.0)
    assert seen and str(seen[0]).startswith(str(runtmp)), seen


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


def test_transcript_path_is_under_workdir_with_placeholder(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    p, rel = P._transcript_target("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "python", "beer-song", tag="m46")
    assert p == tmp_path / "opencode_transcripts" / "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed" / "m46" / "python__beer-song.json"
    assert rel == "$STACK_WORKDIR/opencode_transcripts/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/m46/python__beer-song.json"


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
    from bench import opencode_common as p
    monkeypatch.setattr(p, "_stack_workdir", lambda required=False: None)
    monkeypatch.setattr(p.os.path, "expanduser", lambda s: "/Users/zed" if s == "~" else s)  # allow-pii-pattern (synthetic)
    monkeypatch.setattr(p, "_login_name", lambda: "zed")
    out = p._scrub_pii("drwxr-xr-x@ 7 zed  staff   224 Oct  4 .\n/Users/zed/x zedx dazed")  # allow-pii-pattern (synthetic)
    assert out == "drwxr-xr-x@ 7 $USER  staff   224 Oct  4 .\n$HOME/x zedx dazed"


def _mkfiles(tmp_path, sol_text="before", test_text="def test_x(): pass\n"):
    work = tmp_path / "work"
    work.mkdir()
    sol = work / "sol.py"
    test = work / "sol_test.py"
    sol.write_text(sol_text)
    test.write_text(test_text)
    log = work / ".opencode_probe_log.txt"
    log.write_text("")
    return work, sol, test, log


def test_first_tick_unchanged_file_is_flat_and_never_grades(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)

    def grade(w, t):
        raise AssertionError("grade must not run when the solution file has not changed")

    snap = P._tick_snapshot_fn(work, sol, test, "before", grade, log)
    tick = snap(300.0)
    assert tick.file_changed is False
    assert tick.n_failing is None
    assert tick.elapsed_s == 300.0


def test_changed_file_triggers_a_grade_call_and_records_the_result(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)
    calls = []

    def grade(w, t):
        calls.append((w, t))
        return True, "1 passed"

    snap = P._tick_snapshot_fn(work, sol, test, "before", grade, log)
    sol.write_text("after")   # the model "edits" the file between ticks
    tick = snap(300.0)
    assert tick.file_changed is True
    assert tick.n_failing == 0
    assert len(calls) == 1
    # grade was called on a SNAPSHOT COPY, never the live work dir -- the whole point of the design
    # ("never race a live write" / never corrupt an in-progress session).
    w_arg, t_arg = calls[0]
    assert w_arg != work and t_arg != test


def test_grade_failure_records_n_failing_one(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)

    def grade(w, t):
        return False, "1 failed"

    snap = P._tick_snapshot_fn(work, sol, test, "before", grade, log)
    sol.write_text("after")
    tick = snap(300.0)
    assert tick.n_failing == 1


def test_second_tick_with_no_further_change_does_not_re_grade(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)
    calls = []

    def grade(w, t):
        calls.append(1)
        return True, "ok"

    snap = P._tick_snapshot_fn(work, sol, test, "before", grade, log)
    sol.write_text("after")
    t1 = snap(300.0)
    assert t1.file_changed is True and len(calls) == 1
    t2 = snap(600.0)   # nothing edited since t1
    assert t2.file_changed is False
    assert t2.n_failing is None       # neutral -- the gate carries the last known count forward
    assert len(calls) == 1            # NOT re-graded


def test_signature_reflects_the_captured_log_tail(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)
    snap = P._tick_snapshot_fn(work, sol, test, "before", lambda w, t: (True, ""), log)
    t1 = snap(300.0)
    log.write_text("some new tool-call output\n")
    t2 = snap(600.0)
    assert t1.signature != t2.signature


def test_scratch_dir_is_fully_resolved(tmp_path, monkeypatch):
    # The scratch root may be reached through a symlink (an alias, or /var -> /private/var);
    # the yielded path must be the canonical form or opencode's project-boundary check
    # auto-rejects every absolute tool path. Since 2026-10-04 the root comes from
    # OPENCODE_PROBE_SCRATCH / <workdir>/scratch/octmp.noindex, not TMPDIR.
    link = tmp_path / "alias"
    real = tmp_path / "real"
    real.mkdir()
    link.symlink_to(real)
    monkeypatch.setenv("OPENCODE_PROBE_SCRATCH", str(link))
    with _scratch_dir("beer-song") as work_root:
        p = Path(work_root)
        assert p.exists()
        assert str(p) == os.path.realpath(p), (
            f"scratch dir {p} contains symlinked components; opencode's "
            "project-boundary check breaks on the alias"
        )
        assert str(p).startswith(str(real)), "OPENCODE_PROBE_SCRATCH redirection was not honored"


def test_scratch_dir_resolved_under_default_tmp(monkeypatch):
    # No override and no resolvable workdir -> tempfile's default (TMPDIR), which on macOS
    # lives under /var -> /private/var; the returned scratch dir must already be canonical.
    from bench import opencode_common as p
    monkeypatch.delenv("OPENCODE_PROBE_SCRATCH", raising=False)
    monkeypatch.setattr(p, "_stack_workdir", lambda required=False: None)
    with _scratch_dir("x") as work_root:
        assert str(work_root) == os.path.realpath(work_root)


def test_scratch_dir_defaults_under_workdir_noindex(tmp_path, monkeypatch):
    """2026-10-04 (M55): Spotlight indexed the per-item node_modules trees under the scratch dir
    (load 12 storms). macOS skips directories whose name ends in `.noindex`, so the probe's scratch
    root defaults to `<STACK_WORKDIR>/scratch/octmp.noindex` (created on demand) and no longer
    depends on the launcher exporting TMPDIR. `OPENCODE_PROBE_SCRATCH` overrides it explicitly."""
    from bench import opencode_common as p
    wd = tmp_path / "wd"; wd.mkdir()
    monkeypatch.setattr(p, "_stack_workdir", lambda required=False: wd)
    monkeypatch.delenv("OPENCODE_PROBE_SCRATCH", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "elsewhere"))
    with p._scratch_dir("beer-song") as root:
        assert str(root).startswith(str((wd / "scratch" / "octmp.noindex").resolve()))
        assert root.name.startswith("oc-beer-song-")
    override = tmp_path / "ovr.noindex"; override.mkdir()
    monkeypatch.setenv("OPENCODE_PROBE_SCRATCH", str(override))
    with p._scratch_dir("beer-song") as root:
        assert str(root).startswith(str(override.resolve()))
