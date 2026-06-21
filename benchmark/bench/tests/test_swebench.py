import json
import os
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


def test_run_swebench_cli_writes_json(tmp_path, monkeypatch):
    import bench.run_swebench as RS
    monkeypatch.setattr(RS, "RESULTS", str(tmp_path))
    monkeypatch.setattr(RS, "MlxServeDriver", lambda: object())
    monkeypatch.setattr(RS, "params_for", lambda m: {"temperature": 0.7})
    monkeypatch.setattr(RS, "run_swebench", lambda **kw: {
        "model": kw["model"], "axis": "agentic_coding", "tool": "swebench_verified",
        "n": 2, "resolved": 1, "total": 2, "resolve_rate": 0.5, "acc": 0.5,
        "subset_ids": ["i1", "i2"], "skipped": False})
    rc = RS.main(["--model", "mymodel", "--n", "2", "--no-preload"])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "swebench.json")))
    assert out["acc"] == 0.5 and out["tool"] == "swebench_verified" and out["n"] == 2


def test_safe_path_contains_and_rejects_escape(tmp_path):
    root = str(tmp_path)
    assert SW._safe_path(root, "a/b.py") == os.path.realpath(os.path.join(root, "a/b.py"))
    assert SW._safe_path(root, ".") == os.path.realpath(root)
    assert SW._safe_path(root, "../evil.py") == os.path.realpath(root)   # escape -> root


def test_safe_path_rejects_sibling_prefix(tmp_path):
    root = os.path.join(str(tmp_path), "repo")
    os.makedirs(root, exist_ok=True)
    # /tmp/.../repo-evil must NOT be reachable from repo_dir=/tmp/.../repo
    assert SW._safe_path(root, "../repo-evil/secret") == os.path.realpath(root)


def test_run_swebench_write_predictions_failure_degrades(monkeypatch, tmp_path):
    monkeypatch.setattr(SW, "swebench_available", lambda: True)
    out = SW.run_swebench("m", n=1, instances=[{"instance_id": "i1", "repo": "r"}],
                          driver=object(), params={}, agent_fn=lambda *a, **k: "PATCH",
                          predictions_path=str(tmp_path / "nope" / "preds.jsonl"))  # parent dir missing
    assert out["acc"] is None and out["skipped"] is False and "note" in out
