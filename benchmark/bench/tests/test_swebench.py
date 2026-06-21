import json
import types

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


def test_run_swebench_degrades_when_swebench_absent(monkeypatch):
    monkeypatch.setattr(SW, "swebench_available", lambda: False)
    out = SW.run_swebench("m", n=2, instances=[{"instance_id": "i1", "repo": "r"}])
    assert out["skipped"] is True and out["acc"] is None and out["axis"] == "agentic_coding"


def test_run_swebench_orchestrates(monkeypatch, tmp_path):
    monkeypatch.setattr(SW, "swebench_available", lambda: True)
    insts = [{"instance_id": "i1", "repo": "r"}, {"instance_id": "i2", "repo": "r"}]

    def fake_agent(driver, model, instance, repo_dir, params, max_turns=12):
        return f"PATCH for {instance['instance_id']}"

    report_file = tmp_path / "report.json"

    def fake_harness(cmd, **kw):
        # emulate swebench writing its report; the fake closes over the path the test passes in
        report_file.write_text(json.dumps({"resolved_instances": ["i1"], "total_instances": 2}))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    out = SW.run_swebench("m", n=2, seed=0, instances=insts, driver=object(), params={},
                          agent_fn=fake_agent, harness_runner=fake_harness,
                          predictions_path=str(tmp_path / "preds.jsonl"),
                          report_path=str(report_file))
    assert out["resolved"] == 1 and out["total"] == 2
    assert out["resolve_rate"] == 0.5 and out["acc"] == 0.5
    assert out["n"] == 2 and out["skipped"] is False
    # predictions were written
    assert (tmp_path / "preds.jsonl").exists()


def test_solve_instance_returns_submitted_patch(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    import bench.agent_loop as AL

    def fake_run_agent(driver, model, system, task, tools, params, max_turns=12, submit_tool="submit"):
        # exercise a read tool, then return a submitted patch
        names = {t.name for t in tools}
        assert {"list_dir", "read_file", "submit"} <= names
        return {"final": None, "submitted": {"patch": "THE DIFF"}, "turns": 2, "transcript": []}

    monkeypatch.setattr(AL, "run_agent", fake_run_agent)
    patch = SW.solve_instance(object(), "m", {"instance_id": "i1", "problem_statement": "fix"},
                              str(tmp_path), {})
    assert patch == "THE DIFF"
