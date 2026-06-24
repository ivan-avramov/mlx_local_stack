"""Test the per-difficulty pass@1 grouping for LiveCodeBench. LCB problems carry an
Easy/Medium/Hard difficulty from their source platform; reporting per-difficulty pass@1
(not just overall) is what separates clustered mid-tier / quantized models — the overall
number alone is small + noisy for ~27B 4-bit candidates.
"""
import bench.grade as G


def test_lcb_by_difficulty_groups_and_averages():
    ids = ["a", "b", "c", "d"]
    diff_by_id = {"a": "EASY", "b": "EASY", "c": "HARD", "d": "MEDIUM"}
    # index-aligned per-problem pass@1 (0-1), as in metrics["detail"]["pass@1"]
    detail_pass = {0: 1.0, 1: 0.0, 2: 0.0, 3: 1.0}
    out = G._lcb_by_difficulty(ids, diff_by_id, detail_pass)
    assert out["EASY"] == {"n": 2, "pass@1": 0.5}
    assert out["HARD"] == {"n": 1, "pass@1": 0.0}
    assert out["MEDIUM"] == {"n": 1, "pass@1": 1.0}


def test_lcb_by_difficulty_unknown_bucket():
    ids = ["a", "b"]
    diff_by_id = {"a": "EASY"}             # b missing -> UNKNOWN bucket
    out = G._lcb_by_difficulty(ids, diff_by_id, {0: 1.0, 1: 0.0})
    assert out["EASY"] == {"n": 1, "pass@1": 1.0}
    assert out["UNKNOWN"] == {"n": 1, "pass@1": 0.0}
