"""Tests for the code-quality judge panel (rubric/prompt/parser, backends, aggregation)."""
import json

import bench.judge as J


def test_rubric_has_ten_axes():
    assert len(J.RUBRIC_AXES) == 10
    assert "security" in J.RUBRIC_AXES and "readability" in J.RUBRIC_AXES


def test_build_judge_prompt_is_blind_and_asks_for_json():
    system, user = J.build_judge_prompt("Write a function that adds two ints.",
                                        "def add(a,b): return a+b", reference=None)
    assert "JSON" in system or "JSON" in user
    # blind: the prompt must NOT name the model under test
    assert "Qwen" not in (system + user) and "gemma" not in (system + user)
    assert "def add(a,b)" in user


def test_parse_scores_extracts_and_clamps():
    text = ('Here is my evaluation.\n{"scores": {"readability": 4, "security": 7, '
            '"design": 0, "robustness": 3}, "rationale": "ok"}\nThanks!')
    out = J.parse_scores(text)
    assert out["readability"] == 4
    assert out["security"] == 5      # clamped from 7
    assert out["design"] == 1        # clamped from 0
    assert out["robustness"] == 3


def test_parse_scores_ignores_unknown_axes():
    out = J.parse_scores('{"scores": {"readability": 5, "made_up_axis": 3}}')
    assert out == {"readability": 5}


def test_parse_scores_none_on_garbage():
    assert J.parse_scores("no json here") is None
    assert J.parse_scores('{"scores": {}}') is None      # no recognized axes
    assert J.parse_scores("") is None
