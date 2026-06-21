"""Tests for the BFCL tool-calling adapter (score parsing, subprocess driving, degrade)."""
import json
import os

import bench.bfcl_adapter as A


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
