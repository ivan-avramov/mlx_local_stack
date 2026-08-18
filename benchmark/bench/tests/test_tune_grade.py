"""D3: grade.py's per-pair artifacts (rows, manifest, score.json, and the evalplus sidecar
`_samples.jsonl` / `_samples_eval_results.json`) all thread an optional `tune` through to
`generate.result_path`, so grading a tuned run reads/writes at `<bench>.<tune>.*` and never
touches (or is shadowed by) the deployed baseline's files.
"""
import json

import bench.generate as G
import bench.grade as GR


def test_write_pair_score_writes_to_the_tuned_path(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    GR._write_pair_score("m", "aime", {"benchmark": "aime", "model": "m", "acc": 0.5}, tune="kv4")
    p = tmp_path / "m" / "aime.kv4.score.json"
    assert p.exists()
    assert json.loads(p.read_text())["acc"] == 0.5
    assert not (tmp_path / "m" / "aime.score.json").exists()


def test_grade_all_with_tune_reads_and_writes_the_tuned_pair(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    seen = {}

    def fake_grade(name, model, tune=None):
        seen["args"] = (name, model, tune)
        return {"benchmark": name, "model": model, "acc": 1.0, "items": []}

    monkeypatch.setattr(GR, "grade", fake_grade)
    scores = GR.grade_all(["m"], ["aime"], tune="kv4")
    assert seen["args"] == ("aime", "m", "kv4")
    assert scores[0]["acc"] == 1.0
    assert (tmp_path / "m" / "aime.kv4.score.json").exists()


def test_grade_evalplus_tuned_sidecars_use_the_tune_infixed_stem(tmp_path, monkeypatch):
    """The evalplus grader writes its docker-mount sidecars (`<stem>_samples.jsonl`,
    `<stem>_samples_eval_results.json`) beside the rows — under a tune, `<stem>` must be
    `<bench>.<tune>`, matching the already-shipped `.suffixon_samples_eval_results.json`
    convention exactly."""
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    p = G.result_path("m", "humanevalplus", tune="kv4")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"id": "HumanEval/0",
                             "content": "```python\ndef f():\n    return 1\n```"}) + "\n")
    captured = {}

    def fake_runner(cmd, **kw):
        sdir = tmp_path / "m"
        spath = sdir / "humanevalplus.kv4_samples.jsonl"
        captured["exists"] = spath.exists()
        (sdir / "humanevalplus.kv4_samples_eval_results.json").write_text(json.dumps(
            {"eval": {"HumanEval/0": [{"base_status": "pass", "plus_status": "pass"}]}}))
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    s = GR.grade_evalplus("humanevalplus", "m", runner=fake_runner,
                          all_ids=["HumanEval/0"], tune="kv4")
    assert captured["exists"] is True
    assert s["acc"] == 1.0
    # nothing was written under the untuned (deployed) name
    assert not (tmp_path / "m" / "humanevalplus_samples.jsonl").exists()
