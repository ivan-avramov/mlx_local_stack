"""Tests for the code-quality judge panel (rubric/prompt/parser, backends, aggregation)."""
import json
import os
import types

import bench.judge as J
import bench.run_judge as RJ


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


def test_judge_one_medians_across_judges():
    panel = [
        ("a", lambda s, u: '{"scores": {"readability": 4, "security": 2}}'),
        ("b", lambda s, u: '{"scores": {"readability": 2, "security": 4}}'),
        ("c", lambda s, u: '{"scores": {"readability": 3, "security": 3}}'),
    ]
    out = J.judge_one("task", "code", judge_fns=panel)
    assert out["n_judges"] == 3 and out["judges_used"] == ["a", "b", "c"]
    assert out["median"]["readability"] == 3      # median(4,2,3)
    assert out["median"]["security"] == 3         # median(2,4,3)
    assert out["per_judge"]["a"]["readability"] == 4


def test_judge_one_skips_failed_judges():
    panel = [
        ("a", lambda s, u: '{"scores": {"design": 5}}'),
        ("b", lambda s, u: None),                       # backend unavailable
        ("c", lambda s, u: "garbage, no json"),         # unparseable
    ]
    out = J.judge_one("t", "o", judge_fns=panel)
    assert out["n_judges"] == 1 and out["judges_used"] == ["a"]
    assert out["per_judge"]["b"] is None
    assert out["median"]["design"] == 5


def test_judge_one_all_fail_empty_median():
    panel = [("a", lambda s, u: None)]
    out = J.judge_one("t", "o", judge_fns=panel)
    assert out["n_judges"] == 0 and out["median"] == {}


def test_aggregate_overall_and_low_confidence():
    records = [
        {"median": {"readability": 4, "security": 4}, "n_judges": 3},
        {"median": {"readability": 2, "security": 2}, "n_judges": 1},   # < 2 judges
    ]
    agg = J.aggregate(records)
    # per-record overall = mean of its axis medians: r1=4.0, r2=2.0 -> overall mean 3.0
    assert agg["overall"] == 3.0
    assert agg["per_axis"]["readability"] == 3.0
    assert agg["n_records"] == 2
    assert agg["low_confidence"] is True            # a record had n_judges < 2


def test_aggregate_empty():
    agg = J.aggregate([])
    assert agg["overall"] is None and agg["n_records"] == 0


def test_judge_one_flags_family_split():
    panel = [
        ("sonnet", lambda s, u: '{"scores": {"readability": 5}}'),
        ("opus", lambda s, u: '{"scores": {"readability": 5}}'),
        ("gpt-5.5", lambda s, u: '{"scores": {"readability": 1}}'),
    ]
    assert J.judge_one("t", "o", judge_fns=panel)["split"] is True


def test_judge_one_no_split_when_families_agree():
    panel = [
        ("sonnet", lambda s, u: '{"scores": {"readability": 4}}'),
        ("gpt-5.5", lambda s, u: '{"scores": {"readability": 4}}'),
    ]
    assert J.judge_one("t", "o", judge_fns=panel)["split"] is False


def test_aggregate_low_confidence_on_split():
    records = [{"median": {"readability": 3}, "n_judges": 3, "split": True}]
    assert J.aggregate(records)["low_confidence"] is True


# ── Finding 2: brace-match parser — trailing prose with brace must not break parse ──
def test_parse_scores_trailing_prose_with_brace():
    """Greedy regex would span to the last } in the prose; brace-match stops at the right one."""
    text = '{"scores": {"design": 4}} Note: use {x} here.'
    out = J.parse_scores(text)
    assert out == {"design": 4}


# ── Finding 3: bool scores must be rejected, not coerced ──
def test_parse_scores_rejects_bool_values():
    """bool ⊂ int in Python; must explicitly reject True/False as numeric scores."""
    # all-bool → empty → None
    assert J.parse_scores('{"scores": {"readability": true, "security": false}}') is None
    # mixed: int survives, bool dropped
    out = J.parse_scores('{"scores": {"design": 3, "readability": true}}')
    assert out == {"design": 3}


# ── Finding 1: CLI per-record resilience ──
def test_run_judge_cli_tolerates_malformed_jsonl(tmp_path, monkeypatch):
    """A bad JSONL line must be skipped+counted; good records still process; main returns 0."""
    recs = tmp_path / "recs.jsonl"
    recs.write_text(
        json.dumps({"task": "T1", "output": "code1"}) + "\n"
        + "NOT JSON {{{\n"
        + json.dumps({"task": "T2", "output": "code2"}) + "\n"
    )
    monkeypatch.setattr(RJ, "RESULTS", str(tmp_path))
    monkeypatch.setattr(RJ, "judge_one", lambda task, output, reference=None: {
        "per_judge": {}, "median": {"readability": 4},
        "judges_used": ["x"], "n_judges": 1, "split": False})
    rc = RJ.main(["--model", "mymodel2", "--records", str(recs)])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel2", "judge.json")))
    assert out["n_records"] == 2        # two good records processed
    assert out["n_skipped"] >= 1        # the bad line was counted


def test_run_judge_cli_missing_file_returns_1(tmp_path, monkeypatch):
    """A missing records file must return 1 without raising."""
    monkeypatch.setattr(RJ, "RESULTS", str(tmp_path))
    rc = RJ.main(["--model", "x", "--records", str(tmp_path / "no_such_file.jsonl")])
    assert rc == 1


def test_run_judge_cli_writes_json(tmp_path, monkeypatch):
    recs = tmp_path / "recs.jsonl"
    recs.write_text(json.dumps({"task": "T1", "output": "code1"}) + "\n" +
                    json.dumps({"task": "T2", "output": "code2"}) + "\n")
    monkeypatch.setattr(RJ, "RESULTS", str(tmp_path))
    monkeypatch.setattr(RJ, "judge_one", lambda task, output, reference=None: {
        "per_judge": {}, "median": {"readability": 4}, "judges_used": ["x"], "n_judges": 1})
    rc = RJ.main(["--model", "mymodel", "--records", str(recs)])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "judge.json")))
    assert out["model"] == "mymodel" and out["axis"] == "code_quality"
    assert out["n_records"] == 2 and len(out["records"]) == 2
    assert out["per_axis"]["readability"] == 4.0
