"""Tests for the BFCL tool-calling adapter (score parsing, subprocess driving, degrade)."""
import json
import os
import types

import bench.bfcl_adapter as A
import bench.run_bfcl as RB


def _write_score(score_dir, model, cat, summary_obj, extra_lines=()):
    d = os.path.join(score_dir, model)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"BFCL_v3_{cat}_score.json")
    lines = [json.dumps(summary_obj)] + [json.dumps(x) for x in extra_lines]
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def test_parse_scores_weighted_overall(tmp_path):
    sd = str(tmp_path)
    _write_score(sd, "m", "simple", {"accuracy": 1.0, "correct_count": 100, "total_count": 100})
    _write_score(sd, "m", "multiple", {"accuracy": 0.5, "correct_count": 50, "total_count": 100},
                 extra_lines=[{"id": "x", "error": "wrong"}])
    _write_score(sd, "m", "parallel", {"accuracy": 0.8, "correct_count": 80, "total_count": 100})
    _write_score(sd, "m", "parallel_multiple", {"accuracy": 0.7, "correct_count": 70, "total_count": 100})
    out = A.parse_scores(sd, "m")
    assert out["n"] == 400
    # weighted overall = (100+50+80+70)/400 = 300/400 = 0.75
    assert out["acc"] == 0.75
    assert out["per_category"]["simple"]["accuracy"] == 1.0
    assert out["per_category"]["multiple"]["correct"] == 50


def test_parse_scores_missing_category_excluded(tmp_path):
    sd = str(tmp_path)
    _write_score(sd, "m", "simple", {"accuracy": 1.0, "correct_count": 10, "total_count": 10})
    # other 3 categories absent
    out = A.parse_scores(sd, "m")
    assert out["per_category"]["simple"]["accuracy"] == 1.0
    assert out["per_category"]["multiple"] is None
    assert out["n"] == 10            # only the present category counts
    assert out["acc"] == 1.0


def test_parse_scores_all_missing_gives_none(tmp_path):
    out = A.parse_scores(str(tmp_path), "m")
    assert out["acc"] is None and out["n"] == 0


def test_run_bfcl_degrades_when_cli_absent(monkeypatch):
    monkeypatch.setattr(A, "bfcl_available", lambda: False)
    out = A.run_bfcl("m", categories=("simple",))
    assert out["skipped"] is True and out["acc"] is None and "note" in out
    assert out["axis"] == "tool_calling"


def test_run_bfcl_invokes_generate_then_evaluate_then_parses(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "bfcl_available", lambda: True)
    calls = []

    def fake_runner(cmd, **kw):
        calls.append(cmd)
        # On the evaluate call, drop a score file so parse_scores finds it.
        if "evaluate" in cmd:
            _write_score(str(tmp_path / "score"), "m", "simple",
                         {"accuracy": 0.9, "correct_count": 9, "total_count": 10})
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    out = A.run_bfcl("m", categories=("simple",),
                     result_dir=str(tmp_path / "result"), score_dir=str(tmp_path / "score"),
                     runner=fake_runner)
    assert any("generate" in c for c in calls)
    assert any("evaluate" in c for c in calls)
    # generate precedes evaluate
    assert next(i for i, c in enumerate(calls) if "generate" in c) < \
           next(i for i, c in enumerate(calls) if "evaluate" in c)
    assert out["acc"] == 0.9 and out["n"] == 10 and out["skipped"] is False


def test_run_bfcl_nonzero_exit_degrades(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "bfcl_available", lambda: True)

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=2, stdout="", stderr="boom")

    out = A.run_bfcl("m", categories=("simple",),
                     result_dir=str(tmp_path / "result"), score_dir=str(tmp_path / "score"),
                     runner=fake_runner)
    assert out["acc"] is None and "note" in out
    assert out["skipped"] is False


def test_run_bfcl_runner_exception_degrades(monkeypatch):
    monkeypatch.setattr(A, "bfcl_available", lambda: True)

    def boom_runner(cmd, **kw):
        raise FileNotFoundError("bfcl vanished")

    out = A.run_bfcl("m", categories=("simple",), runner=boom_runner)
    assert out["acc"] is None and out["skipped"] is False and "raised" in out["note"]


def test_run_bfcl_cli_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(RB, "RESULTS", str(tmp_path))
    monkeypatch.setattr(RB, "run_bfcl", lambda **kw: {
        "model": kw["model"], "axis": "tool_calling", "categories": list(kw["categories"]),
        "per_category": {"simple": {"accuracy": 0.9, "correct": 9, "total": 10}},
        "acc": 0.9, "n": 10, "skipped": False})
    rc = RB.main(["--model", "mymodel", "--categories", "simple"])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "bfcl.json")))
    assert out["model"] == "mymodel" and out["axis"] == "tool_calling" and out["acc"] == 0.9
