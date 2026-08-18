"""`run.py generate`/`grade` grow `--tune <label>` (D3 spec item 2): the label is validated
against the grammar at the CLI layer (a malformed label must fail loudly, not silently generate
against the wrong file) and threaded down to `generate.run`/`grade.grade_all`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # benchmark/ (holds run.py)
import run as RUN  # noqa: E402


def _parse(*argv):
    return RUN.build_parser().parse_args(list(argv))


def test_generate_accepts_a_well_formed_tune():
    args = _parse("generate", "--tune", "kv4")
    assert args.tune == "kv4"


def test_generate_tune_defaults_to_none():
    args = _parse("generate")
    assert args.tune is None


def test_grade_accepts_a_well_formed_tune():
    args = _parse("grade", "--tune", "suffixon")
    assert args.tune == "suffixon"


@pytest.mark.parametrize("bad", ["Bad_Label", "KV4", "kv4."])
def test_generate_rejects_a_malformed_tune_at_the_cli_layer(bad, capsys):
    with pytest.raises(SystemExit):
        _parse("generate", "--tune", bad)
    assert "invalid" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("bad", ["Bad_Label", ".kv4"])
def test_grade_rejects_a_malformed_tune_at_the_cli_layer(bad, capsys):
    with pytest.raises(SystemExit):
        _parse("grade", "--tune", bad)
    assert "invalid" in capsys.readouterr().err.lower()


def test_cmd_generate_threads_tune_to_generate_run(monkeypatch):
    captured = {}
    monkeypatch.setattr(RUN.client, "roster", lambda: ["m"])
    monkeypatch.setattr(RUN.generate, "run", lambda *a, **kw: captured.update(kw))
    args = _parse("generate", "--tune", "kv4", "--benches", "aime")
    RUN.cmd_generate(args)
    assert captured.get("tune") == "kv4"


def test_cmd_generate_tune_omitted_passes_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(RUN.client, "roster", lambda: ["m"])
    monkeypatch.setattr(RUN.generate, "run", lambda *a, **kw: captured.update(kw))
    args = _parse("generate", "--benches", "aime")
    RUN.cmd_generate(args)
    assert captured.get("tune") is None


def test_cmd_grade_threads_tune_to_grade_all(monkeypatch):
    captured = {}
    monkeypatch.setattr(RUN.client, "roster", lambda: ["m"])
    monkeypatch.setattr(RUN.grade, "grade_all", lambda models, benches, **kw: (
        captured.update(kw) or []))
    args = _parse("grade", "--tune", "suffixon", "--benches", "aime")
    RUN.cmd_grade(args)
    assert captured.get("tune") == "suffixon"
