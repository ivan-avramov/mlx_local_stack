"""grade_evalplus runs the OFFICIAL evalplus evaluator IN DOCKER (Linux — the macOS
reliability_guard setrlimit crashes; the container also isolates execution). evalplus asserts
ALL problems are present, so we pad the subset to the full problem set with failing dummies,
run the evaluator, then read pass@1 for ONLY our generated subset from the per-problem
*_eval_results.json. The docker runner is injectable for tests.
"""
import json

import bench.generate as G
import bench.grade as GR


def _write_rows(tmp_path, model, bench, rows):
    p = tmp_path / model / f"{bench}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_grade_evalplus_pads_and_reads_subset(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    # two real completions (with code) + the harness pads the rest of the problem set
    _write_rows(tmp_path, "m", "humanevalplus", [
        {"id": "HumanEval/0", "content": "```python\ndef f():\n    return 1\n```"},
        {"id": "HumanEval/1", "content": "```python\ndef g():\n    return 2\n```"},
    ])
    all_ids = ["HumanEval/0", "HumanEval/1", "HumanEval/2"]   # /2 is padded

    captured = {}

    def fake_runner(cmd, **kw):
        captured["cmd"] = cmd
        # the samples file the harness wrote (find it in the mount spec)
        sdir = tmp_path / "m"
        spath = sdir / "humanevalplus_samples.jsonl"
        captured["samples"] = [json.loads(l) for l in spath.read_text().splitlines()]
        # evalplus writes <stem>_eval_results.json: /0 base+plus pass, /1 base pass plus fail,
        # /2 (the pad) fails — must be IGNORED.
        (sdir / "humanevalplus_samples_eval_results.json").write_text(json.dumps({"eval": {
            "HumanEval/0": [{"base_status": "pass", "plus_status": "pass"}],
            "HumanEval/1": [{"base_status": "pass", "plus_status": "fail"}],
            "HumanEval/2": [{"base_status": "fail", "plus_status": "fail"}],
        }}))
        return type("P", (), {"returncode": 0, "stdout": "pass@1:\t0.667", "stderr": ""})()

    s = GR.grade_evalplus("humanevalplus", "m", runner=fake_runner, all_ids=all_ids)
    # padded to the FULL set so evalplus's all-problems assertion passes
    assert {x["task_id"] for x in captured["samples"]} == set(all_ids)
    assert "docker" in captured["cmd"][0] or "docker" in captured["cmd"]
    # the -v host mount MUST be absolute (docker treats a relative path as a named volume)
    import os
    vmount = captured["cmd"][captured["cmd"].index("-v") + 1]
    assert os.path.isabs(vmount.split(":")[0])
    # pass@1 over OUR subset (2 items), padding ignored
    assert s["n"] == 2
    assert s["pass@1_base"] == 1.0          # both base-pass
    assert s["pass@1_plus"] == 0.5          # one plus-pass
    assert s["acc"] == 0.5                   # headline acc = the stricter +tests rate


def test_grade_evalplus_no_completions(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_rows(tmp_path, "m", "humanevalplus", [{"id": "HumanEval/0", "error": "boom"}])
    s = GR.grade_evalplus("humanevalplus", "m", runner=lambda *a, **k: None, all_ids=["HumanEval/0"])
    assert s["acc"] is None and "no completions" in s["note"]


def test_grade_evalplus_degrades_when_no_results_file(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_rows(tmp_path, "m", "humanevalplus",
                [{"id": "HumanEval/0", "content": "```python\ndef f():\n    return 1\n```"}])

    def runner_no_output(cmd, **kw):
        return type("P", (), {"returncode": 1, "stdout": "", "stderr": "docker: boom"})()

    s = GR.grade_evalplus("humanevalplus", "m", runner=runner_no_output, all_ids=["HumanEval/0"])
    assert s["acc"] is None and s["note"]      # graceful: no crash, a note explaining it


def test_a_timed_out_run_RECOVERS_results_that_evalplus_already_wrote(tmp_path, monkeypatch):
    """evalplus hangs in two ways that BOTH leave a complete results file: it prints results and
    never exits, or one sample's worker dies (a rosetta mmap fault on Mbpp/255) and it waits forever
    for that one. The old code returned acc=None on TimeoutExpired, DISCARDING a computed result and
    burning 3600s to do it."""
    import subprocess
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_rows(tmp_path, "m", "humanevalplus", [
        {"id": "HumanEval/0", "content": "```python\ndef f():\n    return 1\n```"},
    ])
    killed = []

    def runner(cmd, **kw):
        if cmd[:2] == ["docker", "kill"]:
            killed.append(cmd[2])
            return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        # evalplus wrote its results, then hung instead of exiting
        (tmp_path / "m" / "humanevalplus_samples_eval_results.json").write_text(json.dumps({"eval": {
            "HumanEval/0": [{"base_status": "pass", "plus_status": "pass"}],
        }}))
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))

    s = GR.grade_evalplus("humanevalplus", "m", runner=runner, all_ids=["HumanEval/0"])
    assert s["acc"] == 1.0, "a result evalplus already wrote must not be thrown away"
    assert s["n"] == 1
    assert s.get("timed_out") is True
    assert "RECOVERED" in s["note"]
    assert killed and killed[0].startswith("evalplus-"), "the wedged container must be killed"


def test_a_timeout_with_NO_results_still_degrades_and_kills_the_container(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_rows(tmp_path, "m", "humanevalplus", [
        {"id": "HumanEval/0", "content": "```python\ndef f():\n    return 1\n```"},
    ])
    killed = []

    def runner(cmd, **kw):
        if cmd[:2] == ["docker", "kill"]:
            killed.append(cmd[2]); return type("P", (), {"returncode": 0})()
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))

    s = GR.grade_evalplus("humanevalplus", "m", runner=runner, all_ids=["HumanEval/0"])
    assert s["acc"] is None
    assert "timed out with no results" in s["note"]
    assert killed, "container must still be killed when there is nothing to recover"


def test_the_timeout_is_bounded_well_below_the_old_3600s(tmp_path, monkeypatch):
    """A wedged container previously held the batch for a full hour; 900s is above a healthy run."""
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_rows(tmp_path, "m", "humanevalplus", [
        {"id": "HumanEval/0", "content": "```python\ndef f():\n    return 1\n```"},
    ])
    seen = {}

    def runner(cmd, **kw):
        seen["timeout"] = kw.get("timeout")
        (tmp_path / "m" / "humanevalplus_samples_eval_results.json").write_text(json.dumps({"eval": {
            "HumanEval/0": [{"base_status": "pass", "plus_status": "pass"}]}}))
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    GR.grade_evalplus("humanevalplus", "m", runner=runner, all_ids=["HumanEval/0"])
    assert seen["timeout"] == GR.EVALPLUS_TIMEOUT_S <= 900
