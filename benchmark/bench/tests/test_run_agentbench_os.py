"""M54: bench.run_agentbench_os CLI -- M50/C106 discipline, graceful degrade, resume, pilot draw,
prepare-artifact gating. Docker, the router and the model are all mocked; no network, no docker,
no model calls."""
import json
import sys

import pytest

import bench.provenance as P
import bench.run_agentbench_os as R
from bench import paths


def _passing(monkeypatch, tmp_path, pid=999):
    monkeypatch.setattr(P, "router_owner", lambda port: {
        "pid": pid, "cmdline": "mlx-serve start", "cwd": str(tmp_path),
        "env": {"MLX_SERVE_CONFIG": str(paths.registry_path())}})


def _refusing(monkeypatch):
    monkeypatch.setattr(P, "router_owner", lambda port: None)


def _args(tmp_path, **over):
    base = ["--model", "m", "--out", str(tmp_path / "rows.jsonl"),
           "--corpus", str(tmp_path / "corpus.jsonl"),
           "--scripts-root", str(tmp_path / "scripts")]
    for k, v in over.items():
        flag = f"--{k.replace('_', '-')}"
        if v == "":              # store_true style flag (--prepare, --resume): no value
            base.append(flag)
        else:
            base += [flag, str(v)]
    return base


def _write_corpus(tmp_path, tasks):
    p = tmp_path / "corpus.jsonl"
    p.write_text("\n".join(json.dumps(t) for t in tasks) + "\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------- M50
def test_generate_refuses_before_docker_or_corpus_checks(tmp_path, monkeypatch):
    _refusing(monkeypatch)
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: pytest.fail("docker checked before M50"))
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert not (tmp_path / "rows.jsonl").exists()


def test_generate_records_router_block_once_past_m50(tmp_path, monkeypatch):
    _passing(monkeypatch, tmp_path, pid=4242)
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: False)
    rc = R.main(_args(tmp_path))
    assert rc == 0        # docker-missing degrade, not a refusal
    doc = json.loads((tmp_path / "rows.jsonl").read_text())
    assert doc["skipped"] is True


# --------------------------------------------------------------------------- graceful degrade (AC7)
def test_skipped_when_docker_unavailable(tmp_path, monkeypatch):
    _passing(monkeypatch, tmp_path)
    _write_corpus(tmp_path, [{"id": "t1"}])
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: False)
    rc = R.main(_args(tmp_path))
    assert rc == 0
    assert json.loads((tmp_path / "rows.jsonl").read_text())["skipped"] is True


def test_skipped_when_images_missing(tmp_path, monkeypatch):
    _passing(monkeypatch, tmp_path)
    _write_corpus(tmp_path, [{"id": "t1"}])
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(AB, "images_available", lambda **k: {"default": False, "packages": True, "ubuntu": True})
    rc = R.main(_args(tmp_path))
    assert rc == 0
    note = json.loads((tmp_path / "rows.jsonl").read_text())["note"]
    assert "default" in note


def test_skipped_when_corpus_missing(tmp_path, monkeypatch):
    _passing(monkeypatch, tmp_path)
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: pytest.fail("docker checked before corpus"))
    rc = R.main(_args(tmp_path))   # corpus path was never written
    assert rc == 0
    assert json.loads((tmp_path / "rows.jsonl").read_text())["skipped"] is True


def test_prepare_mode_also_degrades_on_no_docker(tmp_path, monkeypatch):
    _write_corpus(tmp_path, [{"id": "t1"}])
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: False)
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    assert json.loads((tmp_path / "rows.jsonl").read_text())["skipped"] is True


# --------------------------------------------------------------------------- prepare artifact gate
def test_generate_refuses_without_prepare_artifact(tmp_path, monkeypatch, capsys):
    _passing(monkeypatch, tmp_path)
    _write_corpus(tmp_path, [{"id": "t1"}])
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(AB, "images_available", lambda **k: {"default": True, "packages": True, "ubuntu": True})
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert "prepare" in capsys.readouterr().err
    assert not (tmp_path / "rows.jsonl").exists()


def test_prepare_writes_exclusions_and_gold_cache(tmp_path, monkeypatch):
    import bench.agentbench_adapter as AB
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "workdir"))
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(AB, "images_available", lambda **k: {"default": True, "packages": True, "ubuntu": True})
    match_task = {"id": "m1", "group": 1, "evaluation": {"match": "yes"}, "description": "d"}
    _write_corpus(tmp_path, [match_task])
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    excl = json.loads((tmp_path / "rows.exclusions.json").read_text())
    assert excl == []   # the only task is `match`, never examined/excluded
    cache_files = list((tmp_path / "workdir" / "agentbench_os_golds").glob("*.json"))
    assert len(cache_files) == 1


# --------------------------------------------------------------------------- full generate happy path
def _ready(tmp_path, monkeypatch):
    import bench.agentbench_adapter as AB
    _passing(monkeypatch, tmp_path)
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(AB, "images_available", lambda **k: {"default": True, "packages": True, "ubuntu": True})
    monkeypatch.setattr(AB, "sweep_stale_containers", lambda *a, **k: [])
    return AB


def _stub_registry(monkeypatch, tmp_path):
    reg = tmp_path / "reg.yaml"
    reg.write_text("models:\n  - name: m\n    generation_defaults:\n      temperature: 0.4\n"
                   "      max_tokens: 100\n      thinking_budget: 50\n", encoding="utf-8")
    monkeypatch.setattr(paths, "registry_path", lambda: reg)


def test_full_generate_writes_rows_manifest_and_summary(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [{"id": "m1", "group": 1, "labels": [], "evaluation": {"match": "yes"}, "description": "d"}]
    _write_corpus(tmp_path, tasks)
    (tmp_path / "rows.exclusions.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        return {"id": task["id"], "group": task["group"], "labels": [], "image": "default",
               "passed": True, "outcome": "solved", "turns": 1, "submitted_via": "answer",
               "answer": "yes", "gold": None, "per_turn_completion_tokens": [5],
               "completion_tokens_total": 5, "finish_reasons": ["stop"], "converged": True,
               "wall_s": 0.1, "tool_calls": 0, "tool_timeouts": 0, "error": None}
    monkeypatch.setattr(AB, "run_task", fake_run_task)

    rc = R.main(_args(tmp_path))
    assert rc == 0
    rows = [json.loads(l) for l in (tmp_path / "rows.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["passed"] is True
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["router"]["pid"] == 999
    summary = json.loads((tmp_path / "rows.summary.json").read_text())
    assert summary["n"] == 1 and summary["passed"] == 1 and summary["acc"] == 1.0


def test_resume_skips_already_done_ids(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [{"id": f"m{i}", "group": 1, "labels": [], "evaluation": {"match": "yes"}, "description": "d"}
            for i in range(2)]
    _write_corpus(tmp_path, tasks)
    (tmp_path / "rows.exclusions.json").write_text("[]", encoding="utf-8")
    (tmp_path / "rows.jsonl").write_text(json.dumps({"id": "m0", "passed": True, "outcome": "solved",
                                                     "wall_s": 0.1, "completion_tokens_total": 1,
                                                     "labels": []}) + "\n", encoding="utf-8")
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    seen = []

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        seen.append(task["id"])
        return {"id": task["id"], "group": 1, "labels": [], "image": "default", "passed": True,
               "outcome": "solved", "turns": 1, "submitted_via": "answer", "answer": "yes",
               "gold": None, "per_turn_completion_tokens": [1], "completion_tokens_total": 1,
               "finish_reasons": ["stop"], "converged": True, "wall_s": 0.1, "tool_calls": 0,
               "tool_timeouts": 0, "error": None}
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 0
    assert seen == ["m1"]           # m0 was already done; only m1 ran


def test_without_resume_refuses_on_nonempty_out(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _write_corpus(tmp_path, [{"id": "m0", "group": 1, "evaluation": {"match": "x"}, "description": "d"}])
    (tmp_path / "rows.exclusions.json").write_text("[]", encoding="utf-8")
    (tmp_path / "rows.jsonl").write_text(json.dumps({"id": "m0"}) + "\n", encoding="utf-8")
    rc = R.main(_args(tmp_path))
    assert rc == 2


def test_pilot_draw_is_recorded_in_manifest_and_limits_the_run(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [{"id": f"m{i}", "group": 1, "labels": [], "evaluation": {"match": "yes"}, "description": "d"}
            for i in range(20)]
    _write_corpus(tmp_path, tasks)
    (tmp_path / "rows.exclusions.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    seen = []

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        seen.append(task["id"])
        return {"id": task["id"], "group": 1, "labels": [], "image": "default", "passed": True,
               "outcome": "solved", "turns": 1, "submitted_via": "answer", "answer": "yes",
               "gold": None, "per_turn_completion_tokens": [1], "completion_tokens_total": 1,
               "finish_reasons": ["stop"], "converged": True, "wall_s": 0.1, "tool_calls": 0,
               "tool_timeouts": 0, "error": None}
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path, pilot_seed=7, pilot_n=5))
    assert rc == 0
    assert len(seen) == 5
    assert seen != [f"m{i}" for i in range(5)]   # not the first 5
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert sorted(man["runtime"]["pilot_ids"]) == sorted(seen)


def test_limit_caps_number_of_tasks_run(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [{"id": f"m{i}", "group": 1, "labels": [], "evaluation": {"match": "yes"}, "description": "d"}
            for i in range(10)]
    _write_corpus(tmp_path, tasks)
    (tmp_path / "rows.exclusions.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    seen = []

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        seen.append(task["id"])
        return {"id": task["id"], "group": 1, "labels": [], "image": "default", "passed": True,
               "outcome": "solved", "turns": 1, "submitted_via": "answer", "answer": "yes",
               "gold": None, "per_turn_completion_tokens": [1], "completion_tokens_total": 1,
               "finish_reasons": ["stop"], "converged": True, "wall_s": 0.1, "tool_calls": 0,
               "tool_timeouts": 0, "error": None}
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path, limit=3))
    assert rc == 0 and len(seen) == 3


def test_exclusions_are_never_run(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [{"id": "m0", "group": 1, "labels": [], "evaluation": {"match": "yes"}, "description": "d"},
            {"id": "m1", "group": 1, "labels": [], "evaluation": {"check": [{"code": "x"}]}, "description": "d"}]
    _write_corpus(tmp_path, tasks)
    (tmp_path / "rows.exclusions.json").write_text(json.dumps([{"id": "m1", "reason": "no_gold"}]),
                                                    encoding="utf-8")
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    seen = []

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        seen.append(task["id"])
        return {"id": task["id"], "group": 1, "labels": [], "image": "default", "passed": True,
               "outcome": "solved", "turns": 1, "submitted_via": "answer", "answer": "yes",
               "gold": None, "per_turn_completion_tokens": [1], "completion_tokens_total": 1,
               "finish_reasons": ["stop"], "converged": True, "wall_s": 0.1, "tool_calls": 0,
               "tool_timeouts": 0, "error": None}
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path))
    assert rc == 0 and seen == ["m0"]


# --------------------------------------------------------------------------- C106 exit check
def test_generate_refuses_to_complete_when_served_file_changes_mid_run(tmp_path, monkeypatch, capsys):
    import shutil
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    reg = paths.registry_path()
    tasks = [{"id": "m0", "group": 1, "labels": [], "evaluation": {"match": "yes"}, "description": "d"}]
    _write_corpus(tmp_path, tasks)
    (tmp_path / "rows.exclusions.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        reg.write_text(reg.read_text() + "\n# edited mid-run\n")
        return {"id": task["id"], "group": 1, "labels": [], "image": "default", "passed": True,
               "outcome": "solved", "turns": 1, "submitted_via": "answer", "answer": "yes",
               "gold": None, "per_turn_completion_tokens": [1], "completion_tokens_total": 1,
               "finish_reasons": ["stop"], "converged": True, "wall_s": 0.1, "tool_calls": 0,
               "tool_timeouts": 0, "error": None}
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert "C106" in capsys.readouterr().err
    assert not (tmp_path / "rows.summary.json").exists()
