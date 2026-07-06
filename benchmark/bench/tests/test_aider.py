"""Tests for the Aider polyglot adapter (pass-rate parse, subprocess driving, degrade)."""
import json
import os
import types

import bench.aider_adapter as A
import bench.run_aider as RA


def test_parse_pass_rate_extracts_both():
    stdout = "...\npass_rate_1: 42.5\npass_rate_2: 61.0\nsome other line\n"
    out = A.parse_pass_rate(stdout)
    assert out["pass_rate_1"] == 42.5
    assert out["pass_rate_2"] == 61.0


def test_parse_pass_rate_missing_is_none():
    out = A.parse_pass_rate("no rates printed here")
    assert out["pass_rate_1"] is None and out["pass_rate_2"] is None


def test_aider_available_checks_harness(tmp_path):
    assert A.aider_available(str(tmp_path)) is False
    bdir = tmp_path / "benchmark"
    bdir.mkdir()
    (bdir / "benchmark.py").write_text("# harness")
    assert A.aider_available(str(tmp_path)) is True


def test_run_aider_skips_when_harness_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: False)
    out = A.run_aider("m", exercises_dir=str(tmp_path), aider_repo=str(tmp_path))
    assert out["skipped"] is True and out["acc"] is None and "note" in out
    assert out["axis"] == "agentic_coding" and out["tool"] == "aider_polyglot"


def test_run_aider_success_parses_and_normalizes(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    captured = {}

    def fake_runner(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env", {})
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_1: 40.0\npass_rate_2: 55.0\n", stderr="")

    out = A.run_aider("Qwen3.6-27B-UD-MLX-6bit", exercises_dir="/ex", aider_repo="/aider",
                      num_tests=3, runner=fake_runner)
    assert out["pass_rate_2"] == 55.0
    assert out["acc"] == 0.55                      # pass_rate_2 normalized
    assert out["skipped"] is False
    assert "openai/Qwen3.6-27B-UD-MLX-6bit" in captured["cmd"]
    assert "--num-tests" in captured["cmd"] and "3" in captured["cmd"]
    assert captured["env"]["OPENAI_API_BASE"].endswith("/v1")


def test_run_aider_falls_back_to_rate1(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_1: 30.0\n", stderr="")

    out = A.run_aider("m", "/ex", "/aider", runner=fake_runner)
    assert out["acc"] == 0.30                      # pass_rate_2 absent -> rate_1


def test_run_aider_nonzero_exit_degrades(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="boom")

    out = A.run_aider("m", "/ex", "/aider", runner=fake_runner)
    assert out["acc"] is None and "note" in out and out["skipped"] is False


def test_run_aider_runner_raises_degrades(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def boom(cmd, **kw):
        raise FileNotFoundError("python gone")

    out = A.run_aider("m", "/ex", "/aider", runner=boom)
    assert out["acc"] is None and "raised" in out["note"]


def test_run_aider_success_but_no_rate_parsed_notes(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout="benchmark finished, no rates here", stderr="")

    out = A.run_aider("m", "/ex", "/aider", runner=fake_runner)
    assert out["acc"] is None and out["skipped"] is False and "note" in out


def test_run_aider_cli_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(RA, "RESULTS", str(tmp_path))
    monkeypatch.setattr(RA, "run_aider", lambda **kw: {
        "model": kw["model"], "axis": "agentic_coding", "tool": "aider_polyglot",
        "edit_format": "whole", "pass_rate_1": 40.0, "pass_rate_2": 55.0, "acc": 0.55,
        "skipped": False})
    rc = RA.main(["--model", "mymodel", "--exercises-dir", "/ex", "--aider-repo", "/aider"])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "aider.json")))
    assert out["model"] == "mymodel" and out["acc"] == 0.55 and out["tool"] == "aider_polyglot"


def test_run_aider_sets_aider_docker_to_bypass_host_guard(tmp_path, monkeypatch):
    # aider's benchmark.py returns immediately (prints a docker warning, runs nothing) unless
    # AIDER_DOCKER is set. We run on the host (toolchains present), so the adapter MUST set it —
    # otherwise every run yields "NO SCORE" (no pass_rate parsed).
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    captured = {}

    def fake_runner(cmd, **kw):
        captured["env"] = kw.get("env", {})
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_2: 55.0\n", stderr="")

    A.run_aider("m", exercises_dir="/ex", aider_repo="/aider", runner=fake_runner)
    assert captured["env"].get("AIDER_DOCKER") == "1"
