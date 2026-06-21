"""Tests for the code-quality judge panel (rubric/prompt/parser, backends, aggregation)."""
import json
import types

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


class _FakeBlock:
    def __init__(self, type, text=""):
        self.type = type
        self.text = text


class _FakeAnthropic:
    """Stand-in anthropic.Anthropic client returning a scripted JSON text block."""
    def __init__(self, text):
        self._text = text
        self.messages = types.SimpleNamespace(create=self._create)
        self.captured = {}

    def _create(self, **kw):
        self.captured = kw
        return types.SimpleNamespace(content=[_FakeBlock("thinking", ""),
                                              _FakeBlock("text", self._text)])


def test_anthropic_judge_extracts_text_and_passes_params():
    client = _FakeAnthropic('{"scores": {"readability": 4}}')
    out = J.anthropic_judge("claude-opus-4-8", "sys", "usr", client=client)
    assert out == '{"scores": {"readability": 4}}'
    assert client.captured["model"] == "claude-opus-4-8"
    assert client.captured["system"] == "sys"
    assert client.captured["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in client.captured and "temperature" not in client.captured


def test_anthropic_judge_degrades_on_error():
    class Boom:
        def __init__(self):
            self.messages = types.SimpleNamespace(create=self._c)
        def _c(self, **kw):
            raise RuntimeError("401 no key")
    assert J.anthropic_judge("claude-opus-4-8", "s", "u", client=Boom()) is None


def test_codex_judge_runs_and_returns_stdout():
    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout='{"scores": {"design": 5}}', stderr="")
    assert J.codex_judge("sys", "usr", runner=fake_runner) == '{"scores": {"design": 5}}'


def test_codex_judge_degrades_on_nonzero_and_raise():
    assert J.codex_judge("s", "u", runner=lambda c, **k: types.SimpleNamespace(
        returncode=1, stdout="", stderr="boom")) is None

    def boom(c, **k):
        raise FileNotFoundError("codex not found")
    assert J.codex_judge("s", "u", runner=boom) is None
