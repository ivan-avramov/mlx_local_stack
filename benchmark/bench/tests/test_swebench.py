import json

import bench.swebench_adapter as SW


def test_stratify_is_balanced_and_deterministic():
    insts = [{"instance_id": f"r1-{i}", "repo": "r1"} for i in range(10)] + \
            [{"instance_id": f"r2-{i}", "repo": "r2"} for i in range(10)] + \
            [{"instance_id": f"r3-{i}", "repo": "r3"} for i in range(10)]
    sub = SW.stratify(insts, n=6, seed=0)
    assert len(sub) == 6
    repos = [x["repo"] for x in sub]
    assert repos.count("r1") == 2 and repos.count("r2") == 2 and repos.count("r3") == 2  # balanced
    assert SW.stratify(insts, n=6, seed=0) == sub                                         # deterministic


def test_stratify_caps_at_available():
    insts = [{"instance_id": "a", "repo": "r"}]
    assert len(SW.stratify(insts, n=40, seed=0)) == 1


def test_write_predictions_jsonl(tmp_path):
    p = tmp_path / "preds.jsonl"
    SW.write_predictions(str(p), [{"instance_id": "i1", "model_name_or_path": "m", "model_patch": "D1"},
                                  {"instance_id": "i2", "model_name_or_path": "m", "model_patch": "D2"}])
    lines = p.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["instance_id"] == "i1"


def test_parse_report_resolved_list():
    rep = {"resolved_instances": ["i1", "i3"], "total_instances": 4}
    out = SW.parse_report(rep)
    assert out["resolved"] == 2 and out["total"] == 4 and out["resolve_rate"] == 0.5


def test_parse_report_counts_form():
    rep = {"resolved": 3, "total": 10}
    out = SW.parse_report(rep)
    assert out["resolved"] == 3 and out["total"] == 10 and out["resolve_rate"] == 0.3


def test_parse_report_empty():
    out = SW.parse_report({})
    assert out["resolve_rate"] is None
