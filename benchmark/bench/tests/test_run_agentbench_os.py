"""M54: bench.run_agentbench_os CLI -- M50/C106 discipline, graceful degrade, resume, pilot draw,
the corpus-level prepare-artifact gate, transport-failure escalation, and SIGTERM cleanup. Docker,
the router and the model are all mocked; no network, no docker, no model calls."""
import json
import signal
import sys
from pathlib import Path

import pytest

import bench.provenance as P
import bench.run_agentbench_os as R
from bench import paths


@pytest.fixture(autouse=True)
def _stack_workdir_is_tmp_path(monkeypatch, tmp_path):
    """5th cold review P19 confines --out/--transcripts-dir/the exclusions artifact to the repo or
    STACK_WORKDIR. Every test in this file writes under pytest's own `tmp_path`, which is neither
    -- treat it as this test's STACK_WORKDIR so the existing fixtures keep working unmodified."""
    monkeypatch.setattr(paths, "stack_workdir", lambda required=True: tmp_path)


def _passing(monkeypatch, tmp_path, pid=999):
    monkeypatch.setattr(P, "router_owner", lambda port: {
        "pid": pid, "cmdline": "mlx-serve start", "cwd": str(tmp_path),
        "env": {"MLX_SERVE_CONFIG": str(paths.registry_path())}})


def _refusing(monkeypatch):
    monkeypatch.setattr(P, "router_owner", lambda port: None)


def _args(tmp_path, *, llm_timeout="60", **over):
    """`llm_timeout="60"` by default (5th cold review P14: a per-turn timeout that cannot be SIZED
    now REFUSES the run) -- most tests here don't care about the exact derived value. The small
    number of tests that specifically exercise DERIVATION (no explicit override) pass
    `llm_timeout=None` to omit the flag."""
    base = ["--model", "m", "--out", str(tmp_path / "rows.jsonl"),
           "--corpus", str(tmp_path / "corpus.jsonl"),
           "--scripts-root", str(tmp_path / "scripts")]
    if llm_timeout is not None:
        base += ["--llm-timeout", str(llm_timeout)]
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


def _check_task(tid):
    """A non-match task -- P10: a manual exclusion must not pre-empt the match exemption, so a
    manually-excluded task in these tests must be a CHECK task (match tasks are never examined by
    anything, manual included)."""
    return {"id": tid, "group": 1, "labels": [],
           "evaluation": {"check": [{"code": "true"}], "example": {"code": "echo x"}},
           "description": "d"}


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
    """P10: stamps a scripts_sha256 matching the SAME (possibly nonexistent) scripts root every
    test's generate-mode call uses (`_args`'s `--scripts-root <tmp_path>/scripts`), plus a full
    disposition map over the corpus, so run_generate's P10 checks see a match by default."""
    exclusions = exclusions or []
    scripts_root = tmp_path / "scripts"
    tasks = AB.load_corpus(corpus_path)
    disposition = AB.build_disposition_map(tasks, scripts_root, {}, exclusions)
    AB.write_exclusions_artifact(
        AB.exclusions_artifact_path(corpus_path), corpus_sha256=R._sha256_file(corpus_path),
        image_ids=dict(IMAGE_IDS), golds={}, exclusions=exclusions, complete=True,
        scripts_root=str(scripts_root), scripts_sha256=AB.scripts_root_sha256(scripts_root),
        disposition=disposition)


def _fake_run_task_factory(seen=None, **overrides):
    seen = seen if seen is not None else []

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        seen.append(task["id"])
        row = {"id": task["id"], "group": 1, "labels": [], "image": "default", "passed": True,
              "outcome": "solved", "turns": 1, "submitted_via": "answer", "answer": "yes",
              "gold_prepare": None, "gold_live": None, "per_turn_completion_tokens": [1], "completion_tokens_total": 1,
              "per_turn_finish_reasons": ["stop"], "converged": True, "budget_hits": 0,
              "wall_s": 0.1, "tool_calls": 0, "tool_timeouts": 0, "repeat_calls": 0,
              "exec_timeout": False, "setup_error": False, "decode_tps": 10.0,
              "per_turn_decode_tps": [10.0], "error": None,
              "_transcript_turns": [{"turn": 1, "assistant_content": "ok", "tool_call": None,
                                     "tool_result": None, "raw_output_len": None,
                                     "finish_reason": "stop", "completion_tokens": 1,
                                     "decode_tps": 10.0, "wall_s": 0.1}]}
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


def test_prepare_refuses_when_corpus_sibling_artifact_is_outside_confined_roots_P31(tmp_path, monkeypatch, capsys):
    """6th cold review round 6 P31: `--prepare --corpus /outside/tasks.jsonl` would write a
    sibling .exclusions.json artifact outside the repo/STACK_WORKDIR, unchecked by main()'s
    generic --out confinement (which never looks at --corpus's own directory). --out itself
    stays confined (the default, under tmp_path, which this file's autouse fixture treats as
    STACK_WORKDIR) -- only --corpus points outside, isolating which check fires."""
    import tempfile
    AB = _ready(tmp_path, monkeypatch)
    outside_dir = Path(tempfile.mkdtemp(prefix="agentbench_os_p31_outside_"))
    try:
        outside = outside_dir / "tasks.jsonl"
        outside.write_text(json.dumps(_match_task("t1")) + "\n", encoding="utf-8")
        rc = R.main(_args(tmp_path, prepare="", corpus=str(outside)))
        assert rc == 2
        assert "D2 exclusions artifact" in capsys.readouterr().err
        assert not (outside_dir / "tasks.exclusions.json").exists()
    finally:
        import shutil
        shutil.rmtree(outside_dir, ignore_errors=True)


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


# --------------------------------------------------------------------------- manual exclusions
def test_prepare_merges_manual_exclusions_into_the_artifact(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_check_task("m0"), _match_task("m1")])
    manual_path = AB.manual_exclusions_path(corpus)
    manual_path.write_text(json.dumps({"m0": "known blind spot"}), encoding="utf-8")
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    doc = AB.read_exclusions_artifact(AB.exclusions_artifact_path(corpus))
    assert doc["exclusions"] == [{"id": "m0", "reason": "manual", "note": "known blind spot"}]
    assert doc["manual_exclusions_sha256"] == R._sha256_file(manual_path)


def test_prepare_with_no_manual_file_records_none_sha(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    doc = AB.read_exclusions_artifact(AB.exclusions_artifact_path(corpus))
    assert doc["manual_exclusions_sha256"] is None


def test_generate_refuses_when_manual_exclusions_file_changed_since_prepare(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    manual_path = AB.manual_exclusions_path(corpus)
    manual_path.write_text(json.dumps({"m0": "x"}), encoding="utf-8")
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    manual_path.write_text(json.dumps({"m0": "x", "m1": "y"}), encoding="utf-8")   # changed AFTER prepare
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert "manual" in capsys.readouterr().err.lower()


def test_generate_accepts_when_manual_exclusions_file_unchanged_since_prepare(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_check_task("m0"), _match_task("m1")])
    manual_path = AB.manual_exclusions_path(corpus)
    manual_path.write_text(json.dumps({"m0": "x"}), encoding="utf-8")
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path))
    assert rc == 0 and seen == ["m1"]   # m0 excluded via manual, never run


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


def test_generate_refuses_when_scripts_changed_since_prepare_P10(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_match_task("t1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(AB, "scripts_root_sha256", lambda root: "CHANGED")
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert "scripts" in capsys.readouterr().err.lower()


def test_generate_refuses_when_disposition_missing_a_corpus_id_P10(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    corpus = _write_corpus(tmp_path, [_match_task("t1"), _match_task("t2")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    doc = AB.read_exclusions_artifact(AB.exclusions_artifact_path(corpus))
    doc["disposition"].pop("t2", None)
    AB.write_exclusions_artifact(AB.exclusions_artifact_path(corpus), corpus_sha256=doc["corpus_sha256"],
                                 image_ids=doc["image_ids"], golds=doc["golds"],
                                 exclusions=doc["exclusions"], complete=True,
                                 scripts_root=doc["scripts_root"], scripts_sha256=doc["scripts_sha256"],
                                 disposition=doc["disposition"])
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert "t2" in capsys.readouterr().err


# --------------------------------------------------------------------------- full generate happy path
def test_full_generate_writes_rows_manifest_and_summary(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
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
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    monkeypatch.setattr(R.model_params, "params_for",
                       lambda model, profile: {"temperature": 1.0, "max_tokens": 10, "thinking_budget": 5})
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, **{"sampling-profile": "official", "allow-profile": ""}))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["sampling_profile"] == "official"


# --------------------------------------------------------------------------- P11 summary
def _row(id_, *, passed, converged, setup_error=False, nonconv_kinds=None):
    return {"id": id_, "passed": passed, "converged": converged, "setup_error": setup_error,
           "nonconv_kinds": nonconv_kinds or [], "outcome": "solved" if passed else "failed_tests",
           "labels": []}


def test_summarize_acc_strict_requires_passed_and_converged_P11():
    rows = [_row("a", passed=True, converged=True),
           _row("b", passed=True, converged=False, nonconv_kinds=["budget_hit"]),
           _row("c", passed=False, converged=True)]
    summary = R.summarize(rows)
    assert summary["passed"] == 2             # a and b both passed
    assert summary["acc"] == round(2 / 3, 3)
    assert summary["acc_strict"] == round(1 / 3, 3)   # only "a" is passed AND converged


def test_summarize_conv_rate_and_nonconv_kind_counts_P11():
    """summarize()'s aggregation is a generic string counter over whatever each row's
    `nonconv_kinds` list contains -- `missing_usage` was retired as a PRODUCED kind by P24 (it now
    escalates at the client boundary instead), but the counting mechanism itself is agnostic to
    the specific label strings."""
    rows = [_row("a", passed=True, converged=True),
           _row("b", passed=False, converged=False, nonconv_kinds=["budget_hit"]),
           _row("c", passed=False, converged=False, nonconv_kinds=["bad_finish_reason", "budget_hit"])]
    summary = R.summarize(rows)
    assert summary["conv_rate"] == round(1 / 3, 3)
    assert summary["nonconv_kind_counts"] == {"budget_hit": 2, "bad_finish_reason": 1}


def test_summarize_acc_strict_denominator_excludes_setup_errors_P11():
    rows = [_row("a", passed=True, converged=True),
           _row("b", passed=False, converged=False, setup_error=True)]
    summary = R.summarize(rows)
    assert summary["graded_n"] == 1
    assert summary["acc_strict"] == 1.0


def test_summarize_graded_ids_excludes_setup_error_rows_P23():
    """P23: graded_ids is the exact set actually in the denominator -- two arms must intersect it
    before their accuracies are compared."""
    rows = [_row("a", passed=True, converged=True),
           _row("b", passed=False, converged=False, setup_error=True)]
    summary = R.summarize(rows)
    assert summary["graded_ids"] == ["a"]


def test_summarize_wall_total_s_mean_and_max_P32():
    rows = [{**_row("a", passed=True, converged=True), "wall_total_s": 10.0},
           {**_row("b", passed=True, converged=True), "wall_total_s": 30.0}]
    summary = R.summarize(rows)
    assert summary["wall_total_s_mean"] == 20.0
    assert summary["wall_total_s_max"] == 30.0


def test_summarize_wall_total_s_falls_back_to_wall_s_for_older_rows_P32():
    row = _row("a", passed=True, converged=True)
    row["wall_s"] = 5.0
    assert "wall_total_s" not in row
    summary = R.summarize([row])
    assert summary["wall_total_s_mean"] == 5.0


def test_setup_error_rows_excluded_from_acc_denominator_F1(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task("m0"), _match_task("m1")]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        if task["id"] == "m0":
            return {"id": "m0", "group": 1, "labels": [], "image": "default", "passed": False,
                    "outcome": "server_error", "turns": 0, "submitted_via": None, "answer": None,
                    "gold_prepare": None, "gold_live": None, "per_turn_completion_tokens": [], "completion_tokens_total": 0,
                    "per_turn_finish_reasons": [], "converged": None, "budget_hits": 0, "wall_s": 0.1,
                    "tool_calls": 0, "tool_timeouts": 0, "repeat_calls": 0, "exec_timeout": False,
                    "setup_error": True, "decode_tps": None, "per_turn_decode_tps": [],
                    "error": "docker run failed"}
        return {"id": "m1", "group": 1, "labels": [], "image": "default", "passed": True,
               "outcome": "solved", "turns": 1, "submitted_via": "answer", "answer": "yes",
               "gold_prepare": None, "gold_live": None, "per_turn_completion_tokens": [1], "completion_tokens_total": 1,
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
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
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
    """P39 (round 7): a resume requires a REAL, readable manifest describing the existing rows --
    produce it via a genuine first invocation (limit=1), never by hand-writing a bare rows file."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1))
    assert rc == 0 and seen == ["m0"]

    seen.clear()
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 0
    assert seen == ["m1"]


# --------------------------------------------------------------------------- G3/P7 resume identity
def test_resume_refuses_when_round_limit_changed_G3(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, round_limit=4))
    assert rc == 0 and seen == ["m0", "m1"]

    seen.clear()
    rc = R.main(_args(tmp_path, resume="", round_limit=8))   # changed since the first run
    assert rc == 2
    assert seen == []   # refused before touching a single task
    err = capsys.readouterr().err
    assert "round_limit" in err


def test_resume_accepts_when_nothing_changed_G3(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1))
    assert rc == 0 and seen == ["m0"]

    seen.clear()
    rc = R.main(_args(tmp_path, resume="", limit=1))   # identical runtime identity
    assert rc == 0


def test_resume_refuses_when_rows_exist_but_manifest_is_missing_P39(tmp_path, monkeypatch, capsys):
    """7th cold review round 7 P39 (HIGH), reproduced -- and directly exercised by a PASSING test
    at the reviewed HEAD (provenance laundering): rows existing with NO manifest at all must
    refuse resume, never silently accept with nothing to verify identity against."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0"), _match_task("m1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    (tmp_path / "rows.jsonl").write_text(json.dumps({"id": "m0", "passed": True, "outcome": "solved",
                                                     "wall_s": 0.1, "completion_tokens_total": 1,
                                                     "labels": [], "setup_error": False}) + "\n",
                                         encoding="utf-8")
    assert not (tmp_path / "rows.manifest.json").exists()
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 2
    assert seen == []
    assert "does not exist" in capsys.readouterr().err


def test_resume_refuses_when_manifest_is_unreadable_P39(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0"), _match_task("m1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    (tmp_path / "rows.jsonl").write_text(json.dumps({"id": "m0", "passed": True, "outcome": "solved",
                                                     "wall_s": 0.1, "completion_tokens_total": 1,
                                                     "labels": [], "setup_error": False}) + "\n",
                                         encoding="utf-8")
    (tmp_path / "rows.manifest.json").write_text("{not valid json", encoding="utf-8")
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 2
    assert seen == []
    assert "unreadable" in capsys.readouterr().err


def test_resume_refuses_when_git_identity_changed_P39(tmp_path, monkeypatch, capsys):
    """P39: the harness/serving-fork implementation identity (repo HEAD sha + fork submodule
    shas) is part of resume identity -- changing it while everything else stays the same must
    still refuse."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0"), _match_task("m1")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1))
    assert rc == 0

    man_path = tmp_path / "rows.manifest.json"
    man = json.loads(man_path.read_text())
    man["git"]["stack_head"] = "deadbeef" * 5
    man_path.write_text(json.dumps(man))

    seen.clear()
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 2
    assert seen == []
    assert "git" in capsys.readouterr().err


def test_resume_segments_carry_git_identity_P39(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert "git" in man["segments"][0]["identity"]
    assert "stack_head" in man["segments"][0]["identity"]["git"]


def test_resume_refuses_when_manifest_lacks_nested_identity_P21(tmp_path, monkeypatch, capsys):
    """6th cold review round 6 P21 (HIGH): a manifest missing the nested identity blocks
    entirely (router.config_sha256 / sampling / kv.*) -- e.g. a legacy manifest predating this
    check -- must refuse rather than silently treat absence as 'no constraint'."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    (tmp_path / "rows.jsonl").write_text(json.dumps({"id": "m0", "passed": True, "outcome": "solved",
                                                     "wall_s": 0.1, "completion_tokens_total": 1,
                                                     "labels": [], "setup_error": False}) + "\n",
                                         encoding="utf-8")
    (tmp_path / "rows.manifest.json").write_text(json.dumps({
        "runtime": {"model": "m", "round_limit": AB.ROUND_LIMIT}, "router": {"pid": 999}}) + "\n",
        encoding="utf-8")
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 2
    assert seen == []
    assert "missing" in capsys.readouterr().err


def test_resume_refuses_when_router_config_sha_changed_P21(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1))
    assert rc == 0

    # mutate the recorded router config sha, simulating a served-file change between runs
    man_path = tmp_path / "rows.manifest.json"
    man = json.loads(man_path.read_text())
    man["router"]["config_sha256"] = "DIFFERENT-SHA"
    man_path.write_text(json.dumps(man))

    seen.clear()
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 2
    assert seen == []
    assert "router_config_sha256" in capsys.readouterr().err


def test_resume_refuses_when_effective_sampling_changed_P21(tmp_path, monkeypatch, capsys):
    """Addendum B/P21: identity compares the EFFECTIVE sampling (temperature/top_p/etc) actually
    used -- changing the registry's generation_defaults between the first run and a resume must
    refuse, even though --sampling-profile itself didn't change."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1))
    assert rc == 0

    reg = tmp_path / "reg.yaml"
    reg.write_text("models:\n  - name: m\n    generation_defaults:\n      temperature: 0.9\n"
                   "      max_tokens: 100\n      thinking_budget: 50\n", encoding="utf-8")

    seen.clear()
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 2
    assert seen == []
    # in this mock harness the registry file IS the served-config file, so editing it also
    # changes router_config_sha256 -- either refusal reason is correct evidence of the change.
    err = capsys.readouterr().err
    assert "sampling" in err or "router_config_sha256" in err


def test_resume_reuses_llm_timeout_and_deadline_from_previous_manifest_addendum_B(tmp_path, monkeypatch):
    """Addendum B: a resume must REUSE the pilot's derived llm_timeout_s/deadline_s rather than
    re-deriving (and refusing on a changed NUMBER) once this axis has gathered more rows of its
    own between the pilot and the resume."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    # pilot: derive from a measured rate (no explicit --llm-timeout)
    monkeypatch.setattr(R, "_rate_rows_matching_identity",
                       lambda model, bench, draft_kind: ([{"per_turn_decode_tps": [10.0]}] * 10, ["f1"]) if bench == "agentbench_os" else ([], []))
    rc = R.main(_args(tmp_path, limit=1, llm_timeout=None))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    pilot_timeout = man["runtime"]["llm_timeout_s"]
    pilot_deadline = man["runtime"]["deadline_s"]

    # resume: the axis now has MORE rows with a DIFFERENT measured rate -- would derive a
    # DIFFERENT number if re-derived, but must REUSE the pilot's instead.
    seen.clear()
    monkeypatch.setattr(R, "_rate_rows_matching_identity",
                       lambda model, bench, draft_kind: ([{"decode_tps": 999.0}] * 50, ["f2"]) if bench == "agentbench_os" else ([], []))
    rc = R.main(_args(tmp_path, resume="", llm_timeout=None))
    assert rc == 0
    man2 = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man2["runtime"]["llm_timeout_s"] == pilot_timeout
    assert man2["runtime"]["deadline_s"] == pilot_deadline


def test_resume_refuses_when_explicit_llm_timeout_differs_from_the_manifest_R6(tmp_path, monkeypatch, capsys):
    """7th cold review round 7 addendum R6: an explicit --llm-timeout on a resume that DIFFERS
    from the manifest's recorded value must REFUSE, not silently ignore it in favor of reuse."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1, llm_timeout="60"))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["runtime"]["llm_timeout_s"] == 60.0

    seen.clear()
    rc = R.main(_args(tmp_path, resume="", llm_timeout="99"))
    assert rc == 2 and seen == []
    assert "REFUSED" in capsys.readouterr().err


def test_resume_accepts_an_explicit_llm_timeout_matching_the_manifest_R6(tmp_path, monkeypatch):
    """The SAME explicit value re-given on resume is NOT a conflict -- only a DIFFERING value
    refuses."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1, llm_timeout="60"))
    assert rc == 0
    seen.clear()
    rc = R.main(_args(tmp_path, resume="", llm_timeout="60"))
    assert rc == 0 and seen == ["m1"]


def test_resume_refuses_when_explicit_deadline_s_differs_from_the_manifest_R6(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1, llm_timeout="60", deadline_s="600"))
    assert rc == 0
    seen.clear()
    rc = R.main(_args(tmp_path, resume="", llm_timeout="60", deadline_s="9999"))
    assert rc == 2 and seen == []
    assert "REFUSED" in capsys.readouterr().err


def test_resume_refuses_when_previous_manifest_has_served_config_drift_P7(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    (tmp_path / "rows.jsonl").write_text(json.dumps({"id": "m0", "passed": True, "outcome": "solved",
                                                     "wall_s": 0.1, "completion_tokens_total": 1,
                                                     "labels": [], "setup_error": False}) + "\n",
                                         encoding="utf-8")
    (tmp_path / "rows.manifest.json").write_text(json.dumps({
        "runtime": {"round_limit": R.AB.ROUND_LIMIT}, "router": {"pid": 999},
        "served_config_drift": {"error": "config changed mid-run"}}) + "\n", encoding="utf-8")
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 2
    assert seen == []
    assert "served_config_drift" in capsys.readouterr().err


def test_resume_segments_accumulate_across_runs_P7(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert len(man["segments"]) == 1
    assert man["segments"][0]["rows_before"] == 0

    rc = R.main(_args(tmp_path, resume=""))   # no --limit this time: m1 is new work
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert len(man["segments"]) == 2
    assert man["segments"][1]["rows_before"] == 1


# --------------------------------------------------------------------------- P16 container cleanup CLI
def test_generate_stops_the_run_when_container_removal_is_unverified_P16(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(3)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory(container_removed_verified=False)
    monkeypatch.setattr(AB, "run_task", fake)
    with pytest.raises(AB.ContainerCleanupError):
        R.main(_args(tmp_path))
    # the row for the FIRST task was still durably written before the run stopped
    rows = (tmp_path / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert seen == ["m0"]   # stopped after the first task, never reached m1/m2


def test_generate_continues_when_container_removal_is_verified_P16(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory(container_removed_verified=True)
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path))
    assert rc == 0 and seen == ["m0", "m1"]


def test_resume_tolerates_a_torn_final_line(tmp_path, monkeypatch):
    """P39 (round 7): the torn row must be simulated on top of a REAL manifest (produced by a
    genuine first run), not a hand-written rows file with no manifest at all."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path))
    assert rc == 0 and seen == ["m0", "m1"]

    # simulate an interrupted write: tear off the last row's tail (the manifest from the real run
    # above stays intact).
    rows_path = tmp_path / "rows.jsonl"
    lines = rows_path.read_text(encoding="utf-8").splitlines()
    torn_last = lines[-1][:len(lines[-1]) // 2]
    rows_path.write_text("\n".join(lines[:-1]) + "\n" + torn_last, encoding="utf-8")

    seen.clear()
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
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, pilot_seed=7, pilot_n=5))
    assert rc == 0
    assert len(seen) == 5
    assert seen != [f"m{i}" for i in range(5)]
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert sorted(man["runtime"]["pilot_ids"]) == sorted(seen)


def test_generate_refuses_limit_and_pilot_seed_together_addendum_J(tmp_path, monkeypatch, capsys):
    """Addendum J (round 6): mutation-sensitive coverage for G4's --limit/--pilot-seed refusal via
    the real CLI (main/run_generate), not just by inspection of the source."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task(f"m{i}") for i in range(10)])
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=3, pilot_seed=1, pilot_n=3))
    assert rc == 2
    assert seen == []
    assert "mutually exclusive" in capsys.readouterr().err


def test_main_refuses_out_outside_confined_roots_addendum_J(tmp_path, monkeypatch, capsys):
    """Addendum J (round 6): mutation-sensitive coverage for P19's --out confinement wiring in
    main() itself (not just the underlying confine_path unit tests) -- a genuinely out-of-bounds
    --out must refuse before any docker/corpus work happens."""
    import tempfile
    # the file's own autouse fixture pins STACK_WORKDIR to `tmp_path`; a dir minted OUTSIDE
    # tmp_path (and outside the repo) is therefore genuinely unconfined for this test.
    outside_dir = Path(tempfile.mkdtemp(prefix="agentbench_os_j_outside_"))
    try:
        rc = R.main(["--model", "m", "--out", str(outside_dir / "rows.jsonl"),
                    "--corpus", str(tmp_path / "corpus.jsonl"),
                    "--scripts-root", str(tmp_path / "scripts"), "--llm-timeout", "60"])
        assert rc == 2
        assert "--out" in capsys.readouterr().err
        assert not (outside_dir / "rows.jsonl").exists()
    finally:
        import shutil
        shutil.rmtree(outside_dir, ignore_errors=True)


def test_pilot_executes_in_the_sampled_order_not_resorted_P17(tmp_path, monkeypatch):
    """6th cold review round 6, P17 remainder: the pilot must run in the SAMPLED order
    (AB.pilot_draw's own output order), never re-sorted back to the corpus's easy-first order --
    a re-sort silently discards the whole point of drawing a representative random sample."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(20)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, pilot_seed=7, pilot_n=5))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert seen == man["runtime"]["pilot_ids"]   # EXACT order, not just the same set


def test_limit_caps_number_of_tasks_run(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(10)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
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
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
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
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    swept = []
    monkeypatch.setattr(AB, "sweep_stale_containers", lambda prefix, runner: swept.append(prefix))
    R.main(_args(tmp_path))
    assert swept == [AB.GENERATE_CONTAINER_PREFIX]


def test_prepare_sweeps_the_prepare_prefix_at_startup_P40(tmp_path, monkeypatch):
    """7th cold review round 7 P40 (HIGH): prepare gets the SAME initial startup sweep as
    generate -- a prior interrupted --prepare's leftover containers must be cleared before
    probing begins."""
    AB = _ready(tmp_path, monkeypatch)
    _write_corpus(tmp_path, [{"id": "c0", "group": 1, "evaluation": {"check": [{"code": "x"}],
                                                                     "example": {"code": "y"}},
                             "description": "d"}])
    swept = []
    monkeypatch.setattr(AB, "sweep_stale_containers", lambda prefix, runner: swept.append(prefix))
    monkeypatch.setattr(AB, "prepare_exclusions", lambda *a, **k: ({}, []))
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    assert swept == [AB.PREPARE_CONTAINER_PREFIX]


def test_generate_aborts_before_any_container_when_startup_discovery_fails_P40(tmp_path, monkeypatch, capsys):
    """7th cold review round 7 P40 (HIGH): deliberately does NOT use `_ready()` (which stubs
    sweep_stale_containers to a no-op) -- this test needs the REAL startup-sweep discovery path."""
    import bench.agentbench_adapter as AB
    _passing(monkeypatch, tmp_path)
    monkeypatch.setattr(AB, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(AB, "images_available", lambda **k: {"default": True, "packages": True, "ubuntu": True})
    monkeypatch.setattr(AB, "current_image_ids", lambda **k: dict(IMAGE_IDS))
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)

    class _Proc:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

    def failing_runner(cmd, **kw):
        if cmd[:3] == ["docker", "ps", "-a"]:
            return _Proc(1, "", "Cannot connect to the Docker daemon")
        raise AssertionError(f"no container work should happen after a failed startup sweep: {cmd}")
    seen = []

    def fake_run_task(*a, **k):
        seen.append(a[1]["id"])
        raise AssertionError("run_task must never be called after a failed startup sweep")
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    import subprocess
    monkeypatch.setattr(subprocess, "run", failing_runner)
    with pytest.raises(AB.ContainerDiscoveryError):
        R.main(_args(tmp_path))
    assert seen == []


def test_prepare_uses_the_prepare_container_prefix(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _write_corpus(tmp_path, [{"id": "c0", "group": 1, "evaluation": {"check": [{"code": "x"}],
                                                                     "example": {"code": "y"}},
                             "description": "d"}])
    used_prefix = {}

    def fake_prepare(tasks, scripts_root, runner, timeout, prefix, manual=None):
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
        def _fake(name, runner, verify=False):
            calls.append((name, runner, verify))
            return True
        AB.remove_container = _fake
        current = {"container": "agentbench-os-run-t1"}
        handler = R._make_sigterm_handler(current, monkeypatch_runner)
        with pytest.raises(SystemExit) as ei:
            handler(signal.SIGTERM, None)
        assert ei.value.code == 143
        assert calls == [("agentbench-os-run-t1", monkeypatch_runner, True)]
    finally:
        AB.remove_container = orig_remove


def test_sigterm_handler_warns_on_unverified_removal_P16(capsys):
    import bench.agentbench_adapter as AB
    orig_remove = AB.remove_container
    try:
        AB.remove_container = lambda name, runner, verify=False: False
        current = {"container": "agentbench-os-run-t1"}
        handler = R._make_sigterm_handler(current, object())
        with pytest.raises(SystemExit):
            handler(signal.SIGTERM, None)
        assert "UNVERIFIED" in capsys.readouterr().err
    finally:
        AB.remove_container = orig_remove


def test_sigterm_handler_noop_when_no_container_live():
    import bench.agentbench_adapter as AB
    calls = []
    orig_remove = AB.remove_container
    try:
        AB.remove_container = lambda name, runner, verify=False: calls.append(name)
        handler = R._make_sigterm_handler({"container": None}, object())
        with pytest.raises(SystemExit) as ei:
            handler(signal.SIGTERM, None)
        assert ei.value.code == 143
        assert calls == []
    finally:
        AB.remove_container = orig_remove


# --------------------------------------------------------------------------- N6 append_row torn-tail
def test_append_row_truncates_a_torn_tail_before_appending(tmp_path):
    out = tmp_path / "rows.jsonl"
    good = json.dumps({"id": "m0", "passed": True})
    torn = '{"id": "m1", "passed": tr'   # cut off mid-write, no trailing \n
    out.write_text(good + "\n" + torn, encoding="utf-8")
    R.append_row(out, {"id": "m2", "passed": True})
    lines = out.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"id": "m0", "passed": True}
    assert json.loads(lines[1]) == {"id": "m2", "passed": True}
    assert len(lines) == 2   # the torn row is gone, not concatenated onto


def test_append_row_preserves_a_complete_row_missing_only_its_newline_P13(tmp_path):
    """5th cold review P13: a final line that IS a complete, valid JSON object (just missing its
    trailing newline -- e.g. the write landed but the process died before the `\\n` byte) must be
    PRESERVED, not deleted as if it were an actually-torn fragment."""
    out = tmp_path / "rows.jsonl"
    good = json.dumps({"id": "m0", "passed": True})
    complete_no_newline = json.dumps({"id": "m1", "passed": False, "outcome": "failed_tests"})
    out.write_text(good + "\n" + complete_no_newline, encoding="utf-8")
    R.append_row(out, {"id": "m2", "passed": True})
    lines = out.read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["id"] for l in lines] == ["m0", "m1", "m2"]
    assert json.loads(lines[1]) == {"id": "m1", "passed": False, "outcome": "failed_tests"}


def test_append_row_leaves_a_clean_file_untouched(tmp_path):
    out = tmp_path / "rows.jsonl"
    out.write_text(json.dumps({"id": "m0"}) + "\n", encoding="utf-8")
    R.append_row(out, {"id": "m1"})
    lines = out.read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["id"] for l in lines] == ["m0", "m1"]


def test_resume_after_a_torn_tail_real_file_both_old_and_new_rows_readable_then_second_resume_works(tmp_path, monkeypatch):
    """N6 end-to-end: a real torn-tail file, resumed via the full CLI, produces a clean file a
    SECOND resume can also build on. P39 (round 7): the torn tail is simulated on top of a REAL
    manifest (a genuine first run covering only m0), not a hand-written rows file alone."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(3)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1))
    assert rc == 0 and seen == ["m0"]

    torn = '{"id": "m1", "passed": tr'
    with open(tmp_path / "rows.jsonl", "a", encoding="utf-8") as f:
        f.write(torn)

    seen.clear()
    rc = R.main(_args(tmp_path, resume=""))
    assert rc == 0
    assert seen == ["m1", "m2"]      # m1's torn row discarded -> reran; m2 never ran before
    rows = R.read_rows(tmp_path / "rows.jsonl")
    assert sorted(r["id"] for r in rows) == ["m0", "m1", "m2"]

    # a SECOND resume with nothing left to do must not error and must not duplicate rows
    seen.clear()
    rc2 = R.main(_args(tmp_path, resume=""))
    assert rc2 == 0 and seen == []
    rows2 = R.read_rows(tmp_path / "rows.jsonl")
    assert sorted(r["id"] for r in rows2) == ["m0", "m1", "m2"]


# --------------------------------------------------------------------------- P30/R6 timeout formula
def test_floor_tps_r6_native_falls_back_to_true_minimum_under_5_qualifying_turns():
    """6th cold review round 6 P30 + 7th round addendum R6: with FEWER than 5 turns at
    completion_tokens>=256 (here: none carry completion_tokens at all), the floor falls back to
    the TRUE minimum across all turns -- never an episode-averaged `decode_tps`."""
    rows = [{"per_turn_decode_tps": [50.0, 30.0, 5.0]}, {"per_turn_decode_tps": [40.0]}]
    assert R._floor_tps_R6(rows, native=True) == 5.0


def test_floor_tps_r6_native_ignores_error_rows_and_non_numeric_turns():
    rows = [{"per_turn_decode_tps": [50.0, None, 2.0], "error": None},
           {"per_turn_decode_tps": [1.0], "error": "boom"}]   # excluded: errored row
    assert R._floor_tps_R6(rows, native=True) == 2.0


def test_floor_tps_r6_fallback_uses_per_row_decode_tps():
    rows = [{"decode_tps": 20.0}, {"decode_tps": 5.0}, {"decode_tps": 50.0}]
    assert R._floor_tps_R6(rows, native=False) == 5.0


def test_floor_tps_r6_none_when_no_evidence():
    assert R._floor_tps_R6([], native=True) is None
    assert R._floor_tps_R6([{"per_turn_decode_tps": []}], native=True) is None


def test_floor_tps_r6_uses_10th_percentile_over_turns_with_at_least_256_tokens():
    """7th cold review round 7 addendum R6: with >=5 turns at completion_tokens>=256, the floor
    is the 10th PERCENTILE over THOSE turns, not the bare minimum -- a turn generating only a
    handful of tokens (fixed per-request overhead, not sustained decode) must not set the floor."""
    rows = [{"per_turn_decode_tps": [100.0, 90.0, 80.0, 70.0, 60.0, 1.0],
            "per_turn_completion_tokens": [300, 300, 300, 300, 300, 10]}]   # last turn: 10 tok, excluded
    tps = R._floor_tps_R6(rows, native=True)
    assert tps == 60.0   # 10th pct over [60,70,80,90,100] (sorted) == the lowest of the 5
    assert tps != 1.0   # the tiny-token turn must NOT set the floor


def test_floor_tps_r6_fallback_to_minimum_with_fewer_than_5_qualifying_turns():
    """Only 4 turns qualify (>=256 tokens) -- too little evidence for a percentile, so fall back
    to the true minimum across ALL turns (including the small ones)."""
    rows = [{"per_turn_decode_tps": [100.0, 90.0, 80.0, 70.0, 1.0],
            "per_turn_completion_tokens": [300, 300, 300, 300, 10]}]
    assert R._floor_tps_R6(rows, native=True) == 1.0


_SAMPLE_IDENTITY = {"draft_kind": "mtp", "kv_bits": 4, "max_kv_cache_size": 262144,
                    "thinking_budget": 1000, "max_tokens": 2000, "box": "testbox"}


def _write_rate_row_file(tmp_path, model: str, bench: str, tune: str, row: dict, *,
                         man_model: str | None = None, identity: dict | None = None,
                         served_config_drift: bool = False, config_sha256: str | None = None):
    """8th cold review round 8 P48: the manifest now carries the FULL identity (kv/sampling/box),
    not just draft_kind -- `identity` defaults to `_SAMPLE_IDENTITY` (override individual fields
    via `{**_SAMPLE_IDENTITY, "kv_bits": 8}` to test a single-field mismatch)."""
    man_model = model if man_model is None else man_model
    identity = dict(_SAMPLE_IDENTITY) if identity is None else identity
    root = tmp_path / model
    root.mkdir(parents=True, exist_ok=True)
    stem = f"{bench}.{tune}" if tune else bench
    rows_path = root / f"{stem}.jsonl"
    rows_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    man = {"model": man_model,
          "runtime": {"draft_kind": identity.get("draft_kind")},
          "kv": {"kv_bits": identity.get("kv_bits"), "max_kv_cache_size": identity.get("max_kv_cache_size")},
          "sampling": {"thinking_budget": identity.get("thinking_budget"), "max_tokens": identity.get("max_tokens")},
          "box": identity.get("box"), "router": {"config_sha256": config_sha256}}
    if served_config_drift:
        man["served_config_drift"] = {"entry_sha256": "x", "exit_sha256": "y"}
    man_path = root / f"{stem}.manifest.json"
    man_path.write_text(json.dumps(man), encoding="utf-8")
    return rows_path


def test_rate_rows_matching_identity_includes_a_file_whose_manifest_matches_P43b(tmp_path, monkeypatch):
    monkeypatch.setattr(R.generate, "RESULTS", tmp_path)
    _write_rate_row_file(tmp_path, "m1", R.BENCH_NAME, "v1", row={"per_turn_decode_tps": [42.0]},
                         config_sha256="abc123")
    rows, sources = R._rate_rows_matching_identity("m1", R.BENCH_NAME, _SAMPLE_IDENTITY)
    assert len(rows) == 1 and rows[0]["per_turn_decode_tps"] == [42.0]
    assert len(sources) == 1 and sources[0]["file"].endswith(f"{R.BENCH_NAME}.v1.jsonl")
    assert sources[0]["config_sha256"] == "abc123"   # P48: each source's served-config hash


def test_rate_rows_matching_identity_excludes_a_file_with_a_different_draft_kind_P43b(tmp_path, monkeypatch):
    """7th cold review round 7 P43(b): rate evidence from an INCOMPATIBLE serving identity
    (different draft_kind) must never silently inform the derivation."""
    monkeypatch.setattr(R.generate, "RESULTS", tmp_path)
    _write_rate_row_file(tmp_path, "m1", R.BENCH_NAME, "v1", row={"per_turn_decode_tps": [999.0]},
                         identity={**_SAMPLE_IDENTITY, "draft_kind": "off"})
    rows, sources = R._rate_rows_matching_identity("m1", R.BENCH_NAME, _SAMPLE_IDENTITY)
    assert rows == [] and sources == []


def test_rate_rows_matching_identity_excludes_a_file_with_no_manifest_P43b(tmp_path, monkeypatch):
    monkeypatch.setattr(R.generate, "RESULTS", tmp_path)
    root = tmp_path / "m1"
    root.mkdir(parents=True)
    (root / f"{R.BENCH_NAME}.v1.jsonl").write_text(json.dumps({"per_turn_decode_tps": [999.0]}) + "\n",
                                                    encoding="utf-8")
    rows, sources = R._rate_rows_matching_identity("m1", R.BENCH_NAME, _SAMPLE_IDENTITY)
    assert rows == [] and sources == []


# --------------------------------------------------------------------------- P48 full-identity matching
@pytest.mark.parametrize("field,other_value", [
    ("kv_bits", 8), ("max_kv_cache_size", 131072), ("thinking_budget", 500), ("max_tokens", 4000),
    ("box", "a-different-box"),
])
def test_rate_rows_matching_identity_excludes_a_mismatch_on_each_P48_field(tmp_path, monkeypatch, field, other_value):
    """8th cold review round 8 P48: P43(b) filtered on model+draft_kind ALONE -- a row from a
    different kv_bits, max_kv_cache_size, thinking_budget, max_tokens, or BOX could still silently
    size the wrong timeout. Every one of these fields must independently exclude a mismatched
    row."""
    monkeypatch.setattr(R.generate, "RESULTS", tmp_path)
    _write_rate_row_file(tmp_path, "m1", R.BENCH_NAME, "v1", row={"per_turn_decode_tps": [999.0]},
                         identity={**_SAMPLE_IDENTITY, field: other_value})
    rows, sources = R._rate_rows_matching_identity("m1", R.BENCH_NAME, _SAMPLE_IDENTITY)
    assert rows == [] and sources == []


def test_rate_rows_matching_identity_excludes_a_file_with_served_config_drift_P48(tmp_path, monkeypatch):
    """P48: a manifest that itself recorded a served_config_drift from a prior exit is suspect --
    its rate evidence must be excluded even when every OTHER identity field matches exactly."""
    monkeypatch.setattr(R.generate, "RESULTS", tmp_path)
    _write_rate_row_file(tmp_path, "m1", R.BENCH_NAME, "v1", row={"per_turn_decode_tps": [999.0]},
                         served_config_drift=True)
    rows, sources = R._rate_rows_matching_identity("m1", R.BENCH_NAME, _SAMPLE_IDENTITY)
    assert rows == [] and sources == []


def test_rate_rows_matching_identity_excludes_a_file_from_a_different_model_despite_matching_identity_P48(tmp_path, monkeypatch):
    monkeypatch.setattr(R.generate, "RESULTS", tmp_path)
    _write_rate_row_file(tmp_path, "m1", R.BENCH_NAME, "v1", row={"per_turn_decode_tps": [999.0]},
                         man_model="a-different-model")
    rows, sources = R._rate_rows_matching_identity("m1", R.BENCH_NAME, _SAMPLE_IDENTITY)
    assert rows == [] and sources == []


def test_derive_llm_timeout_end_to_end_filters_by_draft_kind_real_files_P43b(tmp_path, monkeypatch):
    """End-to-end (no _rate_rows_matching_identity mock): a compatible-draft_kind file sizes the
    timeout; an incompatible-draft_kind file for the SAME model is silently excluded."""
    monkeypatch.setattr(R.generate, "RESULTS", tmp_path)
    monkeypatch.setattr(R.provenance, "registry_draft", lambda model, **k: {"draft_kind": "mtp"})
    _write_rate_row_file(tmp_path, "m1", R.BENCH_NAME, "v1", row={"per_turn_decode_tps": [999.0]},
                         identity={**_SAMPLE_IDENTITY, "draft_kind": "off"})   # incompatible
    timeout_s, source, msg, d = R._derive_llm_timeout("m1", 1000, 2000, None)
    assert d["observable"] is False   # no COMPATIBLE evidence found anywhere
    assert d["identity"]["draft_kind"] == "mtp"
    assert d["sources"] == []


def test_derive_llm_timeout_formula_uses_max_generation_tokens_over_floor_tps_plus_headroom(monkeypatch):
    """P30: timeout = max_generation_tokens / floor_tps + 300s headroom (no multiplicative safety
    factor); max_generation_tokens is the LARGER of max_tokens and thinking_budget+4096."""
    monkeypatch.setattr(R, "_rate_rows_matching_identity",
                       lambda model, bench, draft_kind: ([{"per_turn_decode_tps": [10.0]}], ["f"]) if bench == "agentbench_os" else ([], []))
    timeout_s, source, msg, d = R._derive_llm_timeout("m", 1000, 2000, None)
    # thinking_budget+4096=5096 < max_tokens=2000? no, 5096 > 2000, so max_generation_tokens=5096
    assert d["max_generation_tokens"] == 5096
    assert timeout_s == pytest.approx(5096 / 10.0 + 300.0, abs=0.1)


def test_derive_llm_timeout_max_tokens_wins_when_larger_than_budget_plus_headroom(monkeypatch):
    monkeypatch.setattr(R, "_rate_rows_matching_identity",
                       lambda model, bench, draft_kind: ([{"per_turn_decode_tps": [10.0]}], ["f"]) if bench == "agentbench_os" else ([], []))
    _, _, _, d = R._derive_llm_timeout("m", 100, 50000, None)
    assert d["max_generation_tokens"] == 50000


def test_derive_llm_timeout_explicit_override_is_recorded_as_unvalidated_P30():
    """P30: an explicit --llm-timeout is NOT thereby validated -- observable must be the literal
    string 'override', distinct from True (an independently sized, measured derivation)."""
    timeout_s, source, msg, d = R._derive_llm_timeout("m", 1000, 2000, 45.0)
    assert timeout_s == 45.0
    assert d["observable"] == "override"
    assert d["observable"] is not True


# --------------------------------------------------------------------------- N11 timeout source / deadline cap
def test_timeout_source_names_only_contributing_fallback_benches(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)

    def _rate_rows(model, bench, draft_kind):
        if bench == "agentbench_os":
            return [], []
        if bench == "math500":
            return [{"decode_tps": v} for v in range(10, 30)], ["f_math500"]
        return [], []   # convergence contributes NOTHING
    monkeypatch.setattr(R, "_rate_rows_matching_identity", _rate_rows)
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, llm_timeout=None))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["runtime"]["timeout_source"] == "fallback:math500"   # NOT "fallback:math500+convergence"


def test_generate_refuses_when_llm_timeout_cannot_be_sized_P14(tmp_path, monkeypatch, capsys):
    """5th cold review P14: with no rows anywhere (this axis AND every fallback bench) and no
    explicit --llm-timeout, the per-turn timeout cannot be SIZED at all -- refuse rather than
    silently running on the shared ceiling, whose only honest meaning here is 'uninterpretable'."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, llm_timeout=None))
    assert rc == 2
    assert seen == []   # refused before touching a single task
    assert "cannot derive a per-turn LLM timeout" in capsys.readouterr().err


def test_generate_explicit_llm_timeout_overrides_an_unobservable_derivation_P14(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, llm_timeout=45))
    assert rc == 0 and seen == ["m0"]
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["runtime"]["llm_timeout_s"] == 45.0
    assert man["runtime"]["timeout_derivation"]["observable"] == "override"
    assert man["runtime"]["timeout_derivation"]["source"] == "explicit"


def test_manifest_records_timeout_derivation_block_P14(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity",
                       lambda model, bench, draft_kind: ([{"per_turn_decode_tps": [10.0]}] * 10, ["f"]) if bench == "agentbench_os" else ([], []))
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, llm_timeout=None))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    d = man["runtime"]["timeout_derivation"]
    assert d["observable"] is True
    assert d["floor_decode_tps"] == 10.0
    assert d["source"] == "agentbench_os"
    assert d["sources"] == ["f"]   # P43(b)/P48: the contributing sources are recorded


def test_deadline_defaults_to_eight_times_the_per_turn_timeout(tmp_path, monkeypatch):
    """R3 (architect ruling, AGENTS.md "the thinking budget is external truncation, never
    tuned"): there is NO hard cap -- a slow model's deadline can legitimately be very large."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    # a very slow decode rate -> a large per-turn timeout -> the deadline must scale with it,
    # uncapped (this would have been clamped to 3600s before R3).
    monkeypatch.setattr(R, "_rate_rows_matching_identity",
                       lambda model, bench, draft_kind: ([{"per_turn_decode_tps": [0.01]}] * 10, ["f"]) if bench == "agentbench_os" else ([], []))
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, llm_timeout=None))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["runtime"]["deadline_s"] == man["runtime"]["llm_timeout_s"] * R.DEADLINE_MULTIPLIER
    assert man["runtime"]["deadline_s"] > 3600   # proves there is no cap any more
    # addendum J (round 6): explicit proof the per-turn timeout ITSELF can exceed the shared
    # budget_timeout.CEILING_S (7200s) -- that ceiling exists for a DIFFERENT axis and must never
    # silently cap this one.
    assert man["runtime"]["llm_timeout_s"] > R.budget_timeout.CEILING_S
    assert not hasattr(R, "DEADLINE_CAP_S")


def test_deadline_explicit_flag_overrides_the_default(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, **{"deadline-s": 9999}))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["runtime"]["deadline_s"] == 9999.0


# --------------------------------------------------------------------------- N12
def test_summary_counts_exec_timeout_and_shell_died_rows(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task("m0"), _match_task("m1")]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        base, _ = _fake_run_task_factory()
        row = base(model, task, scripts_root, driver, params, **kw)
        if task["id"] == "m0":
            row["exec_timeout"] = True
        else:
            row["shell_died"] = True
            row["setup_error"] = True
        return row
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path))
    assert rc == 0
    summary = json.loads((tmp_path / "rows.summary.json").read_text())
    assert summary["exec_timeout_count"] == 1
    assert summary["shell_died_count"] == 1


def test_summary_counts_gold_prepare_differs_rows_R5(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task("m0"), _match_task("m1")]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        base, _ = _fake_run_task_factory()
        row = base(model, task, scripts_root, driver, params, **kw)
        if task["id"] == "m0":
            row["gold_prepare"], row["gold_live"] = "3\n", "4\n"   # drifted
        else:
            row["gold_prepare"], row["gold_live"] = "3\n", "3\n"   # agrees
        return row
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path))
    assert rc == 0
    summary = json.loads((tmp_path / "rows.summary.json").read_text())
    assert summary["gold_prepare_differs_count"] == 1
    assert summary["gold_prepare_differs_ids"] == ["m0"]


def test_summary_gold_prepare_differs_ignores_rows_missing_either_gold(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, _ = _fake_run_task_factory()   # gold_prepare/gold_live both None by default
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path))
    assert rc == 0
    summary = json.loads((tmp_path / "rows.summary.json").read_text())
    assert summary["gold_prepare_differs_count"] == 0


def test_stale_skipped_marker_is_cleared_after_a_successful_run(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    (tmp_path / "rows.skipped.json").write_text(json.dumps({"skipped": True, "note": "stale"}),
                                                encoding="utf-8")
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path))
    assert rc == 0
    assert not (tmp_path / "rows.skipped.json").exists()


def test_prepare_installs_a_sigterm_sweep_handler(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _write_corpus(tmp_path, [_match_task("m0")])
    installed = {}
    real_signal = signal.signal

    def fake_signal(sig, handler):
        if sig == signal.SIGTERM:
            installed["handler"] = handler
        return real_signal(sig, handler) if sig != signal.SIGTERM else None
    monkeypatch.setattr(signal, "signal", fake_signal)
    monkeypatch.setattr(AB, "prepare_exclusions", lambda *a, **k: ({}, []))
    rc = R.main(_args(tmp_path, prepare=""))
    assert rc == 0
    assert "handler" in installed


def test_generate_populates_gold_prepare_onto_every_row_from_the_artifact_AC5(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    scripts_root = tmp_path / "scripts"
    AB.write_exclusions_artifact(AB.exclusions_artifact_path(corpus),
                                 corpus_sha256=R._sha256_file(corpus), image_ids=dict(IMAGE_IDS),
                                 golds={"m0": "3\n"}, exclusions=[], complete=True,
                                 scripts_root=str(scripts_root),
                                 scripts_sha256=AB.scripts_root_sha256(scripts_root),
                                 disposition={"m0": "match"})
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    seen_golds = []

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        seen_golds.append(kw.get("gold_prepare"))
        fake, _ = _fake_run_task_factory()
        row = fake(model, task, scripts_root, driver, params, **kw)
        row["gold_prepare"] = kw.get("gold_prepare")
        return row
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path))
    assert rc == 0
    assert seen_golds == ["3\n"]
    rows = R.read_rows(tmp_path / "rows.jsonl")
    assert rows[0]["gold_prepare"] == "3\n"


# --------------------------------------------------------------------------- C106 exit check
def test_generate_refuses_to_complete_when_served_file_changes_mid_run(tmp_path, monkeypatch, capsys):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    reg = paths.registry_path()
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        reg.write_text(reg.read_text() + "\n# edited mid-run\n")
        fake, _ = _fake_run_task_factory()
        return fake(model, task, scripts_root, driver, params, **kw)
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    rc = R.main(_args(tmp_path))
    assert rc == 2
    assert "C106" in capsys.readouterr().err
    assert not (tmp_path / "rows.summary.json").exists()


# --------------------------------------------------------------------------- transcripts
def test_transcript_written_after_the_row_with_expected_fields(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    tdir = tmp_path / "transcripts"
    rc = R.main(_args(tmp_path, **{"transcripts-dir": str(tdir)}))
    assert rc == 0
    doc = json.loads((tdir / "m0.json").read_text())
    assert doc["id"] == "m0" and doc["model"] == "m"
    assert doc["system"] == AB.SYSTEM_PROMPT
    assert doc["task_description"] == "d"
    assert doc["turns"][0]["assistant_content"] == "ok"
    assert doc["submitted_via"] == "answer" and doc["answer"] == "yes"
    assert doc["gold_prepare"] is None and doc["gold_live"] is None
    assert doc["passed"] is True and doc["outcome"] == "solved"
    rows = R.read_rows(tmp_path / "rows.jsonl")
    assert rows[0]["transcript_path"] == str(tdir / "m0.json")


def test_transcript_not_written_when_no_row_is_appended(tmp_path, monkeypatch):
    """Transport-failure tasks write no row -- and therefore no transcript either."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))

    def fake_run_task(model, task, scripts_root, driver, params, **kw):
        raise AB.TransportFailure(f"task {task['id']}: boom")
    monkeypatch.setattr(AB, "run_task", fake_run_task)
    tdir = tmp_path / "transcripts"
    with pytest.raises(AB.TransportFailure):
        R.main(_args(tmp_path, **{"transcripts-dir": str(tdir)}))
    assert not tdir.exists() or list(tdir.glob("*.json")) == []


def test_resume_reuses_the_same_run_id_transcripts_dir_P29(tmp_path, monkeypatch):
    """6th cold review round 6 P29: a resume must land its LATER tasks' transcripts in the SAME
    run-id directory as the earlier ones, not mint a fresh (different-timestamp) subdirectory."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task(f"m{i}") for i in range(2)]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.setattr(R.paths, "stack_workdir", lambda required=True: workdir)
    rc = R.main(_args(tmp_path, out=str(workdir / "rows.jsonl"), limit=1))
    assert rc == 0
    man1 = json.loads((workdir / "rows.manifest.json").read_text())
    first_dir = man1["runtime"]["transcripts_dir"]

    seen.clear()
    rc = R.main(_args(tmp_path, out=str(workdir / "rows.jsonl"), resume=""))
    assert rc == 0
    man2 = json.loads((workdir / "rows.manifest.json").read_text())
    assert man2["runtime"]["transcripts_dir"] == first_dir
    assert (Path(first_dir) / "m1.json").exists()


def test_two_fresh_runs_use_different_run_id_transcript_dirs_P29(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.setattr(R.paths, "stack_workdir", lambda required=True: workdir)
    rc = R.main(_args(tmp_path, out=str(workdir / "a" / "rows.jsonl")))
    assert rc == 0
    man1 = json.loads((workdir / "a" / "rows.manifest.json").read_text())

    import time as _time
    _time.sleep(1.01)   # run_id has second granularity -- ensure a different timestamp
    rc = R.main(_args(tmp_path, out=str(workdir / "b" / "rows.jsonl")))
    assert rc == 0
    man2 = json.loads((workdir / "b" / "rows.manifest.json").read_text())
    assert man1["runtime"]["transcripts_dir"] != man2["runtime"]["transcripts_dir"]


def test_resume_does_not_rewrite_an_existing_transcript(tmp_path, monkeypatch):
    """P39 (round 7): the pre-existing-transcript scenario is simulated on top of a REAL manifest
    (a genuine first run for m0 with the SAME --transcripts-dir), not a hand-written rows file."""
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    tasks = [_match_task("m0"), _match_task("m1")]
    corpus = _write_corpus(tmp_path, tasks)
    _write_complete_exclusions(tmp_path, AB, corpus)
    tdir = tmp_path / "transcripts"
    fake, seen = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    rc = R.main(_args(tmp_path, limit=1, **{"transcripts-dir": str(tdir)}))
    assert rc == 0 and seen == ["m0"]

    # overwrite m0's REAL transcript with a sentinel, simulating a pre-existing file a resume
    # must never touch again.
    sentinel_doc = {"id": "m0", "note": "PRE-EXISTING, must not be overwritten"}
    (tdir / "m0.json").write_text(json.dumps(sentinel_doc), encoding="utf-8")

    seen.clear()
    rc = R.main(_args(tmp_path, resume="", **{"transcripts-dir": str(tdir)}))
    assert rc == 0
    assert seen == ["m1"]
    assert json.loads((tdir / "m0.json").read_text()) == sentinel_doc   # untouched
    assert (tdir / "m1.json").exists()                                 # the newly-run task got one


def test_manifest_records_transcripts_dir(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    tdir = tmp_path / "transcripts"
    rc = R.main(_args(tmp_path, **{"transcripts-dir": str(tdir)}))
    assert rc == 0
    man = json.loads((tmp_path / "rows.manifest.json").read_text())
    assert man["runtime"]["transcripts_dir"] == str(tdir)


def test_transcripts_dir_defaults_to_stack_workdir_m54_transcripts_model(tmp_path, monkeypatch):
    AB = _ready(tmp_path, monkeypatch)
    _stub_registry(monkeypatch, tmp_path)
    corpus = _write_corpus(tmp_path, [_match_task("m0")])
    _write_complete_exclusions(tmp_path, AB, corpus)
    monkeypatch.setattr(R, "_rate_rows_matching_identity", lambda model, bench, draft_kind: ([], []))
    fake, _ = _fake_run_task_factory()
    monkeypatch.setattr(AB, "run_task", fake)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.setattr(R.paths, "stack_workdir", lambda required=True: workdir)
    args = _args(tmp_path, out=str(workdir / "rows.jsonl"))   # no --transcripts-dir
    rc = R.main(args)
    assert rc == 0
    base = workdir / "m54" / "transcripts" / "m"
    # P29: transcripts now live under a run-id subdirectory of the base (two different runs of
    # the same model must never share <model>/<task>.json and overwrite each other's evidence).
    matches = list(base.glob("*/m0.json"))
    assert len(matches) == 1, f"expected exactly one run-id subdir under {base}, found {matches}"
    man = json.loads((workdir / "rows.manifest.json").read_text())
    assert man["runtime"]["transcripts_dir"] == str(matches[0].parent)
