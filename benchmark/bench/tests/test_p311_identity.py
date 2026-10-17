"""P311-lite (iii): probe_code_sha256 is the closure digest; toolchain identity; the generation composite (spec 3, 4)."""
import json
import subprocess
from pathlib import Path

import pytest

from bench import identity_closure as ic
from bench import tg1_runner as runner
from bench import toolchain
from bench.token_turn_gate import TransportAbort

REPO = Path(__file__).resolve().parents[3]
ENTRY = "benchmark/run_tg1_probe.py"


@pytest.fixture
def p(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    import importlib
    return importlib.import_module("run_tg1_probe")


def selection(p):
    return p._carrier_selection(runner.SCAFFOLD, None, source=runner.CARRIER)


def ident(p, **kw):
    return runner.identity(p, selection(p), "u" * 64, "2.0.20", Path(p.__file__), **kw)


def test_generation_data_lists_the_non_python_inputs():
    assert set(runner.GENERATION_DATA) == {"benchmark/opencode_plugins/toolbounds.js",
                                           "benchmark/opencode_plugins/noretry.js",
                                           "benchmark/opencode_bench_v2_web_tg1.json"}
    assert all((REPO / rel).is_file() for rel in runner.GENERATION_DATA)


def test_probe_code_sha_is_the_closure_digest_of_the_entry(p):
    assert ident(p)["probe_code_sha256"] == ic.closure_sha256(ENTRY, REPO, data=runner.GENERATION_DATA)


def test_inject_mode_has_the_same_code_identity(p):
    assert ident(p)["probe_code_sha256"] == ident(p, inject="stall")["probe_code_sha256"]


# ---- toolchain (spec 3, P23 / test 4)
def test_toolchain_current_reports_lock_interpreter_and_grader_image():
    got = toolchain.current()
    assert set(got) == {"lock_sha256", "interpreter", "grader_image_id"}
    assert got["lock_sha256"] == ic.hashlib.sha256((REPO / "benchmark/requirements-bench.lock").read_bytes()).hexdigest()


@pytest.mark.parametrize("field,patch", [
    ("lock_sha256", ("lock_sha256", lambda: "0" * 64)),
    ("interpreter", ("interpreter_version", lambda: "CPython 9.9.9")),
    ("grader_image_id", ("grader_image_id", lambda: "sha256:" + "9" * 64)),
])
def test_toolchain_change_changes_the_scaffold_policy_sha(p, monkeypatch, field, patch):
    base = ident(p)
    assert base["policy"]["toolchain"]["grader_image_id"].startswith("sha256:")
    monkeypatch.setattr(toolchain, patch[0], patch[1])
    changed = ident(p)
    assert changed["policy"]["toolchain"][field] != base["policy"]["toolchain"][field]
    assert changed["scaffold_policy_sha256"] != base["scaffold_policy_sha256"]
    assert changed["probe_code_sha256"] == base["probe_code_sha256"]


def test_missing_grader_image_refuses(p, monkeypatch):
    def gone():
        raise toolchain.ToolchainError("grader image aider-benchmark is missing")
    monkeypatch.setattr(toolchain, "grader_image_id", gone)
    with pytest.raises(toolchain.ToolchainError):
        ident(p)


def test_grader_image_probe_is_fail_closed():
    calls = []

    def fake(rc, out):
        def run(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, rc, out, "")
        return run
    good = "sha256:" + "a" * 64
    assert toolchain.docker_image_id(run=fake(0, good + "\n")) == good
    assert calls[0][:3] == ["docker", "image", "inspect"] and "aider-benchmark" in calls[0]
    for rc, out in ((1, ""), (0, ""), (0, "not-an-id")):
        with pytest.raises(toolchain.ToolchainError):
            toolchain.docker_image_id(run=fake(rc, out))

    def missing(cmd, **kw):
        raise FileNotFoundError("docker")
    with pytest.raises(toolchain.ToolchainError):
        toolchain.docker_image_id(run=missing)


def test_verify_refuses_drift(monkeypatch):
    expected = toolchain.current()
    toolchain.verify(expected)
    monkeypatch.setattr(toolchain, "grader_image_id", lambda: "sha256:" + "8" * 64)
    with pytest.raises(toolchain.ToolchainError, match="grader_image_id"):
        toolchain.verify(expected)
