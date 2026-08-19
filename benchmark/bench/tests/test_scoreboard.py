"""D7 part 1: `opencode` is the primary agentic harness for the "coding" role; `aider` (retired as a
harness 2026-08-16 -- see AGENTS.md client integrations table) is demoted to a diagnostic column and
must not be counted toward, or mistaken for, the "coding" role's headline verdict.
"""
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "scoreboard", Path(__file__).resolve().parents[2] / "m1" / "scoreboard.py")
SB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SB)


def _write_rows(root: Path, model: str, bench: str, rows: list[dict], score: dict | None = None):
    d = root / model
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{bench}.jsonl"
    with p.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    if score is not None:
        p.with_suffix(".score.json").write_text(json.dumps(score))
    return p


def _humaneval_rows(n=12):
    return [{"id": i, "wall_s": 1.0, "finish_reason": "stop", "completion_tokens": 10,
              "thinking_budget": 8192} for i in range(n)]


# --------------------------------------------------------------------------- ROLES / DIAGNOSTIC_ROLES
def test_opencode_is_in_the_coding_role():
    assert "opencode" in SB.ROLES["coding"]


def test_aider_is_not_in_the_coding_role():
    """aider must not publish under the coding role headline any more -- it moved to DIAGNOSTIC_ROLES."""
    assert "aider" not in SB.ROLES["coding"]


def test_aider_is_a_diagnostic_for_coding():
    assert "aider" in SB.DIAGNOSTIC_ROLES.get("coding", [])


def test_other_coding_benches_unaffected():
    for b in ("humanevalplus", "mbppplus", "livecodebench"):
        assert b in SB.ROLES["coding"]


# --------------------------------------------------------------------------- verdict()
def test_verdict_ignores_aider_for_coverage_math(monkeypatch, tmp_path):
    """A model with ONLY aider rows (no opencode/humanevalplus/mbppplus/livecodebench) must read as
    NOT MEASURED on the coding role -- aider no longer counts toward "have"."""
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "aider", _humaneval_rows(110),
                score={"acc": 0.5, "acc_strict": 0.5})
    data = SB.collect()
    assert SB.verdict(data["modelX"], "coding") == "NOT MEASURED"


def test_verdict_counts_opencode_toward_coding_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "opencode", _humaneval_rows(22),
                score={"acc": 0.7, "acc_strict": 0.7})
    data = SB.collect()
    v = SB.verdict(data["modelX"], "coding")
    assert "1/4 axes" in v
    assert "missing" in v and "aider" not in v.split("missing")[1]


# --------------------------------------------------------------------------- rendering (main --md)
def test_diagnostic_bench_marked_in_main_table(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "aider", _humaneval_rows(110),
                score={"acc": 0.5, "acc_strict": 0.5})
    _write_rows(tmp_path, "modelX", "opencode", _humaneval_rows(22),
                score={"acc": 0.7, "acc_strict": 0.7})
    SB.main(["--md"])
    out = capsys.readouterr().out
    assert "aider [diag]" in out
    assert "opencode" in out and "opencode [diag]" not in out


def test_role_coverage_section_shows_diagnostic_separately(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "aider", _humaneval_rows(110),
                score={"acc": 0.5, "acc_strict": 0.5})
    SB.main([])
    out = capsys.readouterr().out
    assert "coding" in out and "NOT MEASURED" in out
    assert "coding [diag]" in out
    assert "aider" in out.split("coding [diag]")[1].split("\n")[0]
