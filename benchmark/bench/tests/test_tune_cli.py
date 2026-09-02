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
    args = _parse("generate", "--sampling-profile", "deployed", "--tune", "kv4")
    assert args.tune == "kv4"


def test_generate_tune_defaults_to_none():
    args = _parse("generate", "--sampling-profile", "deployed")
    assert args.tune is None


def test_grade_accepts_a_well_formed_tune():
    args = _parse("grade", "--tune", "suffixon")
    assert args.tune == "suffixon"


@pytest.mark.parametrize("bad", ["Bad_Label", "KV4", "kv4."])
def test_generate_rejects_a_malformed_tune_at_the_cli_layer(bad, capsys):
    with pytest.raises(SystemExit):
        _parse("generate", "--sampling-profile", "deployed", "--tune", bad)
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
    args = _parse("generate", "--sampling-profile", "deployed", "--tune", "kv4", "--benches", "aime")
    RUN.cmd_generate(args)
    assert captured.get("tune") == "kv4"


def test_cmd_generate_tune_omitted_passes_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(RUN.client, "roster", lambda: ["m"])
    monkeypatch.setattr(RUN.generate, "run", lambda *a, **kw: captured.update(kw))
    args = _parse("generate", "--sampling-profile", "deployed", "--benches", "aime")
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


def test_samples_above_1_is_ACCEPTED_after_the_O30_seed_fix(monkeypatch):
    """O30 guard LIFTED 2026-09-02. The fork fix (ab5273f, per-request seeds on the batched decode
    path; C26 ab5708a5 for the cached path) is an ancestor of the deployed submodule (57177a21), and
    the ruling's exit condition passed on the live router: same prompt, seeds 11 vs 22 -> different
    text; seed 11 twice -> byte-identical (2-seed byte-difference probe, lab notebook 2026-09-02).
    `--samples k` must therefore proceed to resolution instead of refusing."""
    import run as R
    class Reached(Exception):
        pass
    def _stop(args):
        raise Reached
    monkeypatch.setattr(R, "_resolve", _stop)
    parser = R.build_parser()
    args = parser.parse_args(["generate", "--sampling-profile", "deployed",
                              "--models", "m", "--benches", "humanevalplus",
                              "--samples", "3"])
    try:
        R.cmd_generate(args)
    except Reached:
        pass                                   # the guard did not fire; resolution was reached
    except SystemExit as e:
        raise AssertionError(f"--samples 3 was refused (exit {e.code}) after the O30 lift")
