"""Tests for the Aider polyglot adapter (pass-rate parse, subprocess driving, degrade)."""
import os

import bench.aider_adapter as A


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
