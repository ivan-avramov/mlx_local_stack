"""M54: bench.run_agentbench_os CLI -- M50/C106 discipline, graceful degrade, resume, pilot draw,
the corpus-level prepare-artifact gate, transport-failure escalation, and SIGTERM cleanup. Docker,
the router and the model are all mocked; no network, no docker, no model calls."""
import json
import signal
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


def _match_task(tid):
    return {"id": tid, "group": 1, "labels": [], "evaluation": {"match": "yes"}, "description": "d"}


IMAGE_IDS = {"default": "sha256:d", "packages": "sha256:p", "ubuntu": "sha256:u"}


def _ready(tmp_path, monkeypatch):
    import bench.agentbench_adapter as AB
    _passing(monkeypatch, tmp_path)
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(AB, "images_available", lambda **k: {"default": True, "packages": True, "ubuntu": True})
    monkeypatch.setattr(AB, "current_image_ids", lambda **k: dict(IMAGE_IDS))
    monkeypatch.setattr(AB, "sweep_stale_containers", lambda *a, **k: [])
    return AB


def _stub_registry(monkeypatch, tmp_path):
    reg = tmp_path / "reg.yaml"
    reg.write_text("models:\n  - name: m\n    generation_defaults:\n      temperature: 0.4\n"
                   "      max_tokens: 100\n      thinking_budget: 50\n", encoding="utf-8")
    monkeypatch.setattr(paths, "registry_path", lambda: reg)


def _write_complete_exclusions(tmp_path, AB, corpus_path, exclusions=None):
    AB.write_exclusions_artifact(
        AB.exclusions_artifact_path(corpus_path), corpus_sha256=R._sha256_file(corpus_path),
        image_ids=dict(IMAGE_IDS), golds={}, exclusions=exclusions or [], complete=True)


def _fake_run_task_factory(seen=None, **overrides):
    seen = seen if seen is not None else []

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        seen.append(task["id"])
        row = {"id": task["id"], "group": 1, "labels": [], "image": "default", "passed": True,
              "outcome": "solved", "turns": 1, "submitted_via": "answer", "answer": "yes",
              "gold": None, "per_turn_completion_tokens": [1], "completion_tokens_total": 1,
              "per_turn_finish_reasons": ["stop"], "converged": True, "budget_hits": 0,
              "wall_s": 0.1, "tool_calls": 0, "tool_timeouts": 0, "repeat_calls": 0,
              "exec_timeout": False, "setup_error": False, "decode_tps": 10.0,
              "per_turn_decode_tps": [10.0], "error": None}
        row.update(overrides)
        return row
    return fake_run_task, seen


# --------------------------------------------------------------------------- M50
def test_generate_refuses_before_docker_or_corpus_checks(tmp_path, monkeypatch):
    _refusing(monkeypatch)
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: pytest.fail("docker checked before M50"))
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert not (tmp_path / "rows.jsonl").exists()


# --------------------------------------------------------------------------- graceful degrade (AC7/F3)
def test_skipped_writes_a_SEPARATE_file_never_the_rows_file(tmp_path, monkeypatch):
    """cold-review F3: `_write_skipped` must never touch the rows file at all."""
    _passing(monkeypatch, tmp_path)
    _write_corpus(tmp_path, [_match_task("t1")])
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: False)
    rc = R.main(_args(tmp_path))
    assert rc == 0
    assert not (tmp_path / "rows.jsonl").exists()
    assert json.loads((tmp_path / "rows.skipped.json").read_text())["skipped"] is True


def test_skipped_marker_creates_its_parent_directory_F10(tmp_path, monkeypatch):
    _passing(monkeypatch, tmp_path)
    _write_corpus(tmp_path, [_match_task("t1")])
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: False)
    out = tmp_path / "new" / "deep" / "rows.jsonl"
    args = _args(tmp_path); args[args.index("--out") + 1] = str(out)
    rc = R.main(args)
    assert rc == 0
    assert (out.parent / "rows.skipped.json").exists()


def test_skipped_when_docker_unavailable(tmp_path, monkeypatch):
    _passing(monkeypatch, tmp_path)
    _write_corpus(tmp_path, [_match_task("t1")])
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: False)
    rc = R.main(_args(tmp_path))
    assert rc == 0


def test_skipped_when_images_missing(tmp_path, monkeypatch):
    _passing(monkeypatch, tmp_path)
    _write_corpus(tmp_path, [_match_task("t1")])
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(AB, "images_available", lambda **k: {"default": False, "packages": True, "ubuntu": True})
    rc = R.main(_args(tmp_path))
    assert rc == 0
    note = json.loads((tmp_path / "rows.skipped.json").read_text())["note"]
    assert "default" in note


def test_skipped_when_corpus_missing(tmp_path, monkeypatch):
    _passing(monkeypatch, tmp_path)
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: pytest.fail("docker checked before corpus"))
    rc = R.main(_args(tmp_path))
    assert rc == 0
    assert json.loads((tmp_path / "rows.skipped.json").read_text())["skipped"] is True


def test_prepare_mode_also_degrades_on_no_docker(tmp_path, monkeypatch):
    _write_corpus(tmp_path, [_match_task("t1")])
    import bench.agentbench_adapter as AB
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: False)
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    assert json.loads((tmp_path / "rows.skipped.json").read_text())["skipped"] is True


# --------------------------------------------------------------------------- prepare artifact (F6/F7)
def test_prepare_refuses_limit(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _write_corpus(tmp_path, [_match_task("t1")])
    rc = R.main(_args(tmp_path, prepare="", limit=1))
    assert rc == 2
    assert "--limit" in capsys.readouterr().err
    assert not AB.exclusions_artifact_path(tmp_path / "corpus.jsonl").exists()


def test_prepare_writes_corpus_level_artifact_with_image_ids_and_complete_true(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_match_task("m1")])
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    doc = AB.read_exclusions_artifact(AB.exclusions_artifact_path(corpus))
    assert doc["complete"] is True
    assert doc["image_ids"] == IMAGE_IDS
    assert doc["corpus_sha256"] == R._sha256_file(corpus)
    assert doc["exclusions"] == []          # the only task is `match`, never examined/excluded


def test_prepare_artifact_is_independent_of_out_path(tmp_path, monkeypatch):
    """The artifact lives beside the CORPUS, not under --out (cold-review F6: exclusions are a
    corpus property, not a per-model/per-run one)."""
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_match_task("m1")])
    R.main(_args(tmp_path, prepare="", out=str(tmp_path / "totally" / "different" / "rows.jsonl")))
    assert AB.exclusions_artifact_path(corpus).exists()


# --------------------------------------------------------------------------- generate refuses without/with a stale artifact
def test_generate_refuses_without_prepare_artifact(tmp_path, monkeypatch, capsys):
    _ready(tmp_path, monkeypatch)
    _write_corpus(tmp_path, [_match_task("t1")])
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert "prepare" in capsys.readouterr().err
    assert not (tmp_path / "rows.jsonl").exists()


def test_generate_refuses_when_artifact_incomplete(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_match_task("t1")])
    AB.write_exclusions_artifact(AB.exclusions_artifact_path(corpus),
                                 corpus_sha256=R._sha256_file(corpus), image_ids=dict(IMAGE_IDS),
                                 golds={}, exclusions=[], complete=False)
    rc = R.main(_args(tmp_path))
    assert rc == 2 and "complete" in capsys.readouterr().err


def test_generate_refuses_when_corpus_changed_since_prepare(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_match_task("t1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    corpus.write_text(corpus.read_text() + "\n")   # mutate AFTER prepare
    rc = R.main(_args(tmp_path))
    assert rc == 2 and "corpus" in capsys.readouterr().err.lower()


def test_generate_refuses_when_images_changed_since_prepare(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_match_task("t1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(AB, "current_image_ids", lambda **k: {"default": "CHANGED", "packages": "p", "ubuntu": "u"})
    rc = R.main(_args(tmp_path))
    assert rc == 2 and "image" in capsys.readouterr().err.lower()


# --------------------------------------------------------------------------- full generate happy path
def test_full_generate_writes_rows_manifest_and_summary(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)

    rc = R.main(_args(tmp_path))
    assert rc == 0
    rows = [json.loads(l) for l in (tmp_path / "rows.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["passed"] is True
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["router"]["pid"] == 999
    assert man["sampling_profile"] == "deployed"                      # F15
    assert man["runtime"]["image_ids"] == IMAGE_IDS                   # F9
    assert man["runtime"]["exclusions_sha256"]
    assert man["runtime"]["timeout_source"]                           # F8
    assert man["runtime"]["deadline_s"] > 0
    summary = json.loads((tmp_path / "rows.summary.json").read_text())
    assert summary["n"] == 1 and summary["passed"] == 1 and summary["acc"] == 1.0
    assert summary["setup_error_count"] == 0 and summary["graded_n"] == 1


def test_manifest_records_the_actual_overridden_profile_F15(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    monkeypatch.setattr(R.model_params, "params_for",
                       lambda model, profile: {"temperature": 1.0, "max_tokens": 10, "thinking_budget": 5})
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, **{"sampling-profile": "official", "allow-profile": ""}))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["sampling_profile"] == "official"


def test_setup_error_rows_excluded_from_acc_denominator_F1(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task("m0"), _match_task("m1")]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        if task["id"] == "m0":
            return {"id": "m0", "group": 1, "labels": [], "image": "default", "passed": False,
                    "outcome": "server_error", "turns": 0, "submitted_via": None, "answer": None,
                    "gold": None, "per_turn_completion_tokens": [], "completion_tokens_total": 0,
                    "per_turn_finish_reasons": [], "converged": None, "budget_hits": 0, "wall_s": 0.1,
                    "tool_calls": 0, "tool_timeouts": 0, "repeat_calls": 0, "exec_timeout": False,
                    "setup_error": True, "decode_tps": None, "per_turn_decode_tps": [],
                    "error": "docker run failed"}
        return {"id": "m1", "group": 1, "labels": [], "image": "default", "passed": True,
               "outcome": "solved", "turns": 1, "submitted_via": "answer", "answer": "yes",
               "gold": None, "per_turn_completion_tokens": [1], "completion_tokens_total": 1,
               "per_turn_finish_reasons": ["stop"], "converged": True, "budget_hits": 0,
               "wall_s": 0.1, "tool_calls": 0, "tool_timeouts": 0, "repeat_calls": 0,
               "exec_timeout": False, "setup_error": False, "decode_tps": 10.0,
               "per_turn_decode_tps": [10.0], "error": None}
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path))
    assert rc == 0
    summary = json.loads((tmp_path / "rows.summary.json").read_text())
    assert summary["n"] == 2 and summary["setup_error_count"] == 1
    assert summary["graded_n"] == 1 and summary["acc"] == 1.0   # the setup_error row never enters the denominator
    assert summary["setup_error_ids"] == ["m0"]


def test_transport_failure_escalates_and_writes_no_row_F1(tmp_path, monkeypatch):
    """cold-review F1: a TransportFailure from run_task must propagate OUT of main() uncaught --
    the CLI never swallows it into a graded row."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0"), _match_task("m1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    seen = []

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        seen.append(task["id"])
        raise AB.TransportFailure(f"task {task['id']}: ConnectionError: HTTP 500")
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    with pytest.raises(AB.TransportFailure, match="m0"):
        R.main(_args(tmp_path))
    assert seen == ["m0"]                         # aborted on the FIRST task; m1 never even started
    assert not (tmp_path / "rows.jsonl").exists()  # zero rows written


# --------------------------------------------------------------------------- resume + torn rows (F3)
def test_resume_skips_already_done_ids(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    (tmp_path / "rows.jsonl").write_text(json.dumps({"id": "m0", "passed": True, "outcome": "solved",
                                                     "wall_s": 0.1, "completion_tokens_total": 1,
                                                     "labels": [], "setup_error": False}) + "\n", encoding="utf-8")
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 0
    assert seen == ["m1"]


def test_resume_tolerates_a_torn_final_line(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    good = json.dumps({"id": "m0", "passed": True, "outcome": "solved", "wall_s": 0.1,
                       "completion_tokens_total": 1, "labels": [], "setup_error": False})
    torn = '{"id": "m1", "passed": true, "outc'   # cut off mid-write
    (tmp_path / "rows.jsonl").write_text(good + "\n" + torn, encoding="utf-8")
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 0
    assert seen == ["m1"]      # the torn row for m1 was discarded, so m1 reran


def test_malformed_row_NOT_on_the_last_line_escalates(tmp_path):
    out = tmp_path / "rows.jsonl"
    out.write_text('{"id": "m0", "broken\n{"id": "m1", "passed": true}\n', encoding="utf-8")
    with pytest.raises(R.TornRowError):
        R.read_rows(out)


def test_rows_lacking_id_are_skipped(tmp_path):
    out = tmp_path / "rows.jsonl"
    out.write_text(json.dumps({"passed": True}) + "\n" + json.dumps({"id": "m1", "passed": True}) + "\n",
                   encoding="utf-8")
    rows = R.read_rows(out)
    assert [r["id"] for r in rows] == ["m1"]


def test_without_resume_refuses_on_nonempty_out(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    (tmp_path / "rows.jsonl").write_text(json.dumps({"id": "m0"}) + "\n", encoding="utf-8")
    rc = R.main(_args(tmp_path))
    assert rc == 2


# --------------------------------------------------------------------------- pilot / limit / exclusions
def test_pilot_draw_is_recorded_in_manifest_and_limits_the_run(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(20)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, pilot_seed=7, pilot_n=5))
    assert rc == 0
    assert len(seen) == 5
    assert seen != [f"m{i}" for i in range(5)]
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert sorted(man["runtime"]["pilot_ids"]) == sorted(seen)


def test_limit_caps_number_of_tasks_run(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(10)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=3))
    assert rc == 0 and len(seen) == 3


def test_exclusions_are_never_run(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task("m0"), {"id": "m1", "group": 1, "labels": [],
            "evaluation": {"check": [{"code": "x"}]}, "description": "d"}]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus, exclusions=[{"id": "m1", "reason": "no_gold"}])
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path))
    assert rc == 0 and seen == ["m0"]


# --------------------------------------------------------------------------- F16 distinct sweep prefixes
def test_generate_sweeps_only_the_generate_prefix(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    swept = []
    monkeypatch.setattr(AB, "sweep_stale_containers", lambda prefix, runner: swept.append(prefix))
    R.main(_args(tmp_path))
    assert swept == [AB.GENERATE_CONTAINER_PREFIX]


def test_prepare_uses_the_prepare_container_prefix(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _write_corpus(tmp_path, [{"id": "c0", "group": 1, "evaluation": {"check": [{"code": "x"}],
                                                                     "example": {"code": "y"}},
                             "description": "d"}])
    used_prefix = {}

    def fake_prepare(tasks, scripts_root, runner, timeout, prefix):
        used_prefix["prefix"] = prefix
        return {}, []
    monkeypatch.setattr(AB, "prepare_exclusions", fake_prepare)
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    assert used_prefix["prefix"] == AB.PREPARE_CONTAINER_PREFIX


# --------------------------------------------------------------------------- F12 SIGTERM cleanup
def test_sigterm_handler_removes_the_live_container_and_exits_143():
    import bench.agentbench_adapter as AB
    calls = []
    monkeypatch_runner = object()
    orig_remove = AB.remove_container
    try:
        AB.remove_container = lambda name, runner: calls.append((name, runner))
        current = {"container": "agentbench-os-run-t1"}
        handler = R._make_sigterm_handler(current, monkeypatch_runner)
        with pytest.raises(SystemExit) as ei:
            handler(signal.SIGTERM, None)
        assert ei.value.code == 143
        assert calls == [("agentbench-os-run-t1", monkeypatch_runner)]
    finally:
        AB.remove_container = orig_remove


def test_sigterm_handler_noop_when_no_container_live():
    import bench.agentbench_adapter as AB
    calls = []
    orig_remove = AB.remove_container
    try:
        AB.remove_container = lambda name, runner: calls.append(name)
        handler = R._make_sigterm_handler({"container": None}, object())
        with pytest.raises(SystemExit) as ei:
            handler(signal.SIGTERM, None)
        assert ei.value.code == 143
        assert calls == []
    finally:
        AB.remove_container = orig_remove


# --------------------------------------------------------------------------- C106 exit check
def test_generate_refuses_to_complete_when_served_file_changes_mid_run(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    reg = paths.registry_path()
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R.generate, "rows_for_rate", lambda model, bench: [])

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        reg.write_text(reg.read_text() + "\n# edited mid-run\n")
        fake, _ = _fake_run_task_factory()
        return fake(model, task, scripts_root, driver, params, **kw)
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert "C106" in capsys.readouterr().err
    assert not (tmp_path / "rows.summary.json").exists()
