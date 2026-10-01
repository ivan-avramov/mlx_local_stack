"""M54: bench.agentbench_compare -- the cross-arm comparison report. Rows/manifests are mocked
(synthetic fixtures written to tmp_path); no docker, no router, no model calls."""
import json
import math

import pytest

import bench.agentbench_compare as C
import bench.stats as S

MODEL_A = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
MODEL_B = "Qwen3.8-27B-mlx-uniform-4bit"
MODEL_C = "Ornith-1.0-35B-mlx-uniform-4bit"


def _manifest(**over):
    base = {
        "model": MODEL_A, "box": "M5", "timestamp": 1000,
        "git": {"stack_head": "deadbeef" * 5, "submodules": {}},
        "kv": {}, "quant": {}, "sampling": {"thinking_budget": 16384, "temperature": 0.5},
        "fingerprint_version": 3,
        "sampling_profile": "deployed",
        "runtime": {
            "corpus_sha256": "corpus-sha-a", "exclusions_sha256": "excl-sha-a",
            "round_limit": 30, "exec_timeout_s": 60.0, "draft_kind": "off",
            "sampling_profile": "deployed", "llm_timeout_s": 300.0,
            "apc_enabled": False, "apc_source": "default",
        },
        "router": {"pid": 123, "config_sha256": "router-sha-a"},
    }
    base.update(over)
    return base


def _row(id_, *, group=1, passed=True, outcome="solved", converged=True,
        completion_tokens_total=100, wall_total_s=10.0, setup_error=False,
        exec_timeout=False, shell_died=False, harness_error=False,
        nonconv_kinds=None, labels=None):
    return {"id": id_, "group": group, "labels": labels or [], "passed": passed,
           "outcome": outcome, "turns": 1, "answer": "x", "gold_live": None,
           "per_turn_completion_tokens": [completion_tokens_total],
           "completion_tokens_total": completion_tokens_total,
           "per_turn_finish_reasons": ["stop"], "converged": converged, "budget_hits": 0,
           "per_turn_resolved_budget": [16384], "nonconv_kinds": nonconv_kinds or [],
           "wall_s": wall_total_s, "tool_calls": 1, "tool_timeouts": 0, "repeat_calls": 0,
           "exec_timeout": exec_timeout, "shell_died": shell_died, "setup_error": setup_error,
           "decode_tps": 10.0, "per_turn_decode_tps": [10.0], "error": None,
           "infra_evidence": None, "exec_started": True, "harness_error": harness_error,
           "multi_call_turns": 0, "container_removed_verified": True,
           "wall_total_s": wall_total_s, "submitted_via": "answer", "gold_prepare": None}


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_manifest(path, manifest):
    path.write_text(json.dumps(manifest), encoding="utf-8")


# --------------------------------------------------------------------------- read_manifest / load_arm
def test_read_manifest_missing_file_returns_none(tmp_path):
    assert C.read_manifest(tmp_path / "nope.json") is None


def test_read_manifest_corrupt_json_returns_none(tmp_path):
    p = tmp_path / "m.json"
    p.write_text("not json{", encoding="utf-8")
    assert C.read_manifest(p) is None


def test_read_manifest_valid_reads_it_back(tmp_path):
    p = tmp_path / "m.json"
    man = _manifest()
    _write_manifest(p, man)
    assert C.read_manifest(p) == man


def test_load_arm_derives_manifest_path_from_rows_path_by_default(tmp_path):
    rows_path = tmp_path / "agentbench_os.v1.jsonl"
    manifest_path = tmp_path / "agentbench_os.v1.manifest.json"
    _write(rows_path, [_row("std-001-0")])
    _write_manifest(manifest_path, _manifest())
    arm = C.load_arm(MODEL_A, rows_path)
    assert arm["manifest_path"] == manifest_path
    assert arm["manifest"]["model"] == MODEL_A
    assert len(arm["rows"]) == 1


def test_load_arm_explicit_manifest_path_overrides_default(tmp_path):
    rows_path = tmp_path / "rows.jsonl"
    elsewhere = tmp_path / "custom.manifest.json"
    _write(rows_path, [_row("std-001-0")])
    _write_manifest(elsewhere, _manifest())
    arm = C.load_arm(MODEL_A, rows_path, elsewhere)
    assert arm["manifest_path"] == elsewhere
    assert arm["manifest"] is not None


# --------------------------------------------------------------------------- check_comparability (the gate)
def _arms_pair(man_a=None, man_b=None, rows_a=None, rows_b=None):
    return [
        {"model": MODEL_A, "manifest": man_a if man_a is not None else _manifest(),
         "rows": rows_a if rows_a is not None else [_row("std-001-0")]},
        {"model": MODEL_B, "manifest": man_b if man_b is not None else _manifest(model=MODEL_B),
         "rows": rows_b if rows_b is not None else [_row("std-001-0")]},
    ]


def test_check_comparability_identical_manifests_is_clean():
    assert C.check_comparability(_arms_pair()) == []


@pytest.mark.parametrize("field_path,bad_value", [
    (("runtime", "corpus_sha256"), "corpus-sha-DIFFERENT"),
    (("runtime", "exclusions_sha256"), "excl-sha-DIFFERENT"),
    (("runtime", "round_limit"), 999),
    (("runtime", "exec_timeout_s"), 9999.0),
    (("git", "stack_head"), "cafebabe" * 5),
    (("runtime", "draft_kind"), "mtp"),
    (("runtime", "sampling_profile"), "production"),
])
def test_check_comparability_refuses_on_each_gate_field(field_path, bad_value):
    man_b = _manifest(model=MODEL_B)
    d = man_b
    for k in field_path[:-1]:
        d = d[k]
    d[field_path[-1]] = bad_value
    problems = C.check_comparability(_arms_pair(man_b=man_b))
    assert problems
    assert any(str(bad_value) in p or field_path[-1] in p for p in problems)


def test_check_comparability_missing_manifest_is_a_problem():
    arms = _arms_pair()
    arms[1]["manifest"] = None
    problems = C.check_comparability(arms)
    assert problems
    assert MODEL_B in problems[0]


def test_check_comparability_three_arms_checks_every_pair_against_the_first():
    man_c = _manifest(model=MODEL_C)
    man_c["runtime"]["round_limit"] = 15   # differs from arm A's 30
    arms = _arms_pair() + [{"model": MODEL_C, "manifest": man_c, "rows": [_row("std-001-0")]}]
    problems = C.check_comparability(arms)
    assert any("round_limit" in p for p in problems)


# --------------------------------------------------------------------------- llm_timeout_note (allowed, printed)
def test_llm_timeout_note_none_when_equal():
    assert C.llm_timeout_note(_arms_pair()) is None


def test_llm_timeout_note_reports_when_differing():
    man_b = _manifest(model=MODEL_B)
    man_b["runtime"]["llm_timeout_s"] = 600.0
    note = C.llm_timeout_note(_arms_pair(man_b=man_b))
    assert note is not None
    assert "300.0" in note and "600.0" in note


# --------------------------------------------------------------------------- per_arm_stats
def test_per_arm_stats_basic_counts_and_acc():
    rows = [_row("i1", passed=True, converged=True),
           _row("i2", passed=False, converged=True),
           _row("i3", passed=True, converged=False),       # passed but NOT converged
           _row("i4", setup_error=True, outcome="server_error")]
    out = C.per_arm_stats(MODEL_A, rows, _manifest())
    assert out["n"] == 4
    assert out["graded_n"] == 3                              # setup_error excluded
    assert out["acc"] == pytest.approx(2 / 3, abs=1e-3)       # capability ceiling: raw passed
    assert out["acc_strict"] == pytest.approx(1 / 3, abs=1e-3)  # passed AND converged
    assert out["acc_strict_budget"] == 16384


def test_per_arm_stats_outcome_breakdown_separates_flags_from_outcome():
    rows = [_row("i1", outcome="solved", passed=True),
           _row("i2", outcome="failed_tests", passed=False),
           _row("i3", outcome="turn_cap", passed=False),
           _row("i4", outcome="failed_tests", passed=False, exec_timeout=True),
           _row("i5", outcome="failed_tests", passed=False, shell_died=True),
           _row("i6", outcome="server_error", setup_error=True),
           _row("i7", outcome="server_error", setup_error=True, harness_error=True)]
    out = C.per_arm_stats(MODEL_A, rows, _manifest())
    oc = out["outcome_counts"]
    assert oc["solved"] == 1
    assert oc["failed_tests"] == 3
    assert oc["turn_cap"] == 1
    assert oc["exec_timeout"] == 1
    assert oc["shell_died"] == 1
    assert oc["setup_error"] == 2
    assert oc["harness_error"] == 1


def test_per_arm_stats_tokens_and_wall_percentiles():
    rows = [_row(f"i{i}", completion_tokens_total=100 * i, wall_total_s=float(i))
           for i in range(1, 11)]   # 100..1000, 1..10
    out = C.per_arm_stats(MODEL_A, rows, _manifest())
    assert out["tokens"]["mean"] == pytest.approx(550.0)
    assert out["tokens"]["median"] == pytest.approx(550.0)
    assert out["tokens"]["max"] == pytest.approx(1000.0)
    assert out["tokens"]["p90"] is not None
    assert out["wall_total_s"]["mean"] == pytest.approx(5.5)
    assert out["wall_total_s"]["p90"] is not None
    assert out["wall_total_s"]["max"] == pytest.approx(10.0)


def test_per_arm_stats_per_group_pass_rate_is_diagnostic_and_excludes_setup_error():
    rows = [_row("i1", group=1, passed=True), _row("i2", group=1, passed=False),
           _row("i3", group=2, passed=True),
           _row("i4", group=1, setup_error=True)]   # excluded from the group denominator
    out = C.per_arm_stats(MODEL_A, rows, _manifest())
    pg = out["per_group_pass_rate_diagnostic"]
    assert pg[1] == pytest.approx(0.5)   # 1/2, NOT 1/3
    assert pg[2] == pytest.approx(1.0)


def test_per_arm_stats_runaway_tax_counts_turn_cap_and_exec_timeout_union():
    rows = [_row("i1", outcome="turn_cap", wall_total_s=10.0),
           _row("i2", outcome="failed_tests", exec_timeout=True, wall_total_s=20.0),
           _row("i3", outcome="solved", wall_total_s=5.0)]
    out = C.per_arm_stats(MODEL_A, rows, _manifest())
    tax = out["runaway_tax"]
    assert tax["n"] == 2
    assert tax["share"] == pytest.approx(2 / 3, abs=1e-3)
    assert tax["wall_share"] == pytest.approx(30.0 / 35.0, abs=1e-3)


# --------------------------------------------------------------------------- pairwise_stats
def test_pairwise_stats_intersection_and_dropped_ids_reported():
    rows_a = [_row("i1", passed=True), _row("i2", passed=True), _row("only_a", passed=True)]
    rows_b = [_row("i1", passed=True), _row("i2", passed=False), _row("only_b", passed=True)]
    out = C.pairwise_stats(MODEL_A, rows_a, MODEL_B, rows_b, iters=200, seed=0)
    assert out["comparable"] is True
    assert out["intersection_n"] == 2
    assert out["dropped_a_only"] == ["only_a"]
    assert out["dropped_b_only"] == ["only_b"]


def test_pairwise_stats_no_shared_items_is_not_comparable():
    rows_a = [_row("a1", passed=True)]
    rows_b = [_row("b1", passed=True)]
    out = C.pairwise_stats(MODEL_A, rows_a, MODEL_B, rows_b, iters=200, seed=0)
    assert out["comparable"] is False
    assert out["intersection_n"] == 0


def test_pairwise_stats_identical_arms_is_equivalent_verdict():
    rows = [_row(f"i{i}", passed=(i % 2 == 0)) for i in range(20)]
    out = C.pairwise_stats(MODEL_A, rows, MODEL_B, list(rows), iters=500, seed=0, margin=0.05)
    assert out["delta"]["verdict"] == "equivalent"
    assert out["delta"]["delta"] == pytest.approx(0.0)
    assert out["mcnemar_b"] == 0 and out["mcnemar_c"] == 0
    assert out["mcnemar_p"] == pytest.approx(1.0)
    assert out["exclusive_a"] == [] and out["exclusive_b"] == []


def test_pairwise_stats_exclusive_solve_sets_use_acc_strict_passed_and_converged():
    rows_a = [_row("i1", passed=True, converged=True),   # A solves, B doesn't
             _row("i2", passed=True, converged=False),   # A "passed" but NOT converged -> not acc_strict solved
             _row("i3", passed=False, converged=True)]   # B solves, A doesn't
    rows_b = [_row("i1", passed=False, converged=True),
             _row("i2", passed=False, converged=True),
             _row("i3", passed=True, converged=True)]
    out = C.pairwise_stats(MODEL_A, rows_a, MODEL_B, rows_b, iters=200, seed=0)
    assert out["exclusive_a"] == ["i1"]
    assert out["exclusive_b"] == ["i3"]
    assert out["mcnemar_b"] == 1 and out["mcnemar_c"] == 1


def test_pairwise_stats_known_mcnemar_value():
    # 1 item where A solves/B doesn't, 9 where B solves/A doesn't, rest concordant (both solve).
    rows_a = ([_row("d1", passed=True, converged=True)]
             + [_row(f"d{i}", passed=False, converged=True) for i in range(2, 11)]
             + [_row(f"c{i}", passed=True, converged=True) for i in range(5)])
    rows_b = ([_row("d1", passed=False, converged=True)]
             + [_row(f"d{i}", passed=True, converged=True) for i in range(2, 11)]
             + [_row(f"c{i}", passed=True, converged=True) for i in range(5)])
    out = C.pairwise_stats(MODEL_A, rows_a, MODEL_B, rows_b, iters=200, seed=0)
    assert out["mcnemar_b"] == 1 and out["mcnemar_c"] == 9
    assert out["mcnemar_p"] == pytest.approx(S.mcnemar_exact(1, 9))


def test_pairwise_stats_mde_uses_the_intersection_n():
    rows = [_row(f"i{i}", passed=True, converged=True) for i in range(15)]
    out = C.pairwise_stats(MODEL_A, rows, MODEL_B, list(rows), iters=200, seed=0, p_d=0.20)
    assert out["mde"] == pytest.approx(S.mde(15, p_d=0.20))


# --------------------------------------------------------------------------- build_report
def test_build_report_refuses_and_never_computes_stats_when_gate_fails():
    man_b = _manifest(model=MODEL_B)
    man_b["runtime"]["round_limit"] = 999
    arms = _arms_pair(man_b=man_b)
    report = C.build_report(arms, iters=100, seed=0)
    assert report["comparable"] is False
    assert report["problems"]
    assert "arms" not in report


def test_build_report_three_arms_applies_holm_correction_across_the_pairwise_family():
    rows_a = [_row(f"i{i}", passed=True, converged=True) for i in range(20)]
    rows_b = [_row(f"i{i}", passed=(i < 2), converged=True) for i in range(20)]  # very different
    rows_c = [_row(f"i{i}", passed=True, converged=True) for i in range(20)]     # identical to A
    arms = [
        {"model": MODEL_A, "manifest": _manifest(), "rows": rows_a},
        {"model": MODEL_B, "manifest": _manifest(model=MODEL_B), "rows": rows_b},
        {"model": MODEL_C, "manifest": _manifest(model=MODEL_C), "rows": rows_c},
    ]
    report = C.build_report(arms, iters=300, seed=0)
    assert report["comparable"] is True
    assert len(report["pairs"]) == 3   # A-B, A-C, B-C
    for p in report["pairs"]:
        assert "mcnemar_p_holm" in p
        assert p["mcnemar_p_holm"] >= p["mcnemar_p"] - 1e-9   # Holm never makes it smaller
    assert len(report["arms"]) == 3


# --------------------------------------------------------------------------- render_markdown
def test_render_markdown_includes_full_model_names_and_the_four_headline_numbers():
    rows_a = [_row(f"i{i}", passed=True, converged=True) for i in range(10)]
    rows_b = [_row(f"i{i}", passed=False, converged=True) for i in range(10)]
    arms = [{"model": MODEL_A, "manifest": _manifest(), "rows": rows_a},
           {"model": MODEL_B, "manifest": _manifest(model=MODEL_B), "rows": rows_b}]
    report = C.build_report(arms, iters=200, seed=0)
    md = C.render_markdown(report, cli_line="python -m bench.agentbench_compare --rows ...")
    assert MODEL_A in md and MODEL_B in md
    assert "capability ceiling" in md.lower()
    assert "acc_strict" in md
    assert "runaway tax" in md.lower()
    assert "never rank on tokens or wall" in md.lower() or "never ranked on tokens" in md.lower()


def test_render_markdown_never_ranks_on_tokens_or_wall_language_present():
    rows = [_row(f"i{i}", passed=True, converged=True) for i in range(5)]
    arms = [{"model": MODEL_A, "manifest": _manifest(), "rows": rows},
           {"model": MODEL_B, "manifest": _manifest(model=MODEL_B), "rows": list(rows)}]
    report = C.build_report(arms, iters=100, seed=0)
    md = C.render_markdown(report, cli_line="cli")
    assert "tokens" in md.lower()
    assert "wall" in md.lower()


# --------------------------------------------------------------------------- CLI (main)
def test_main_end_to_end_writes_markdown_and_json_sidecar(tmp_path):
    rows_a_path = tmp_path / "a.rows.jsonl"
    rows_b_path = tmp_path / "b.rows.jsonl"
    _write(rows_a_path, [_row(f"i{i}", passed=True, converged=True) for i in range(10)])
    _write(rows_b_path, [_row(f"i{i}", passed=False, converged=True) for i in range(10)])
    _write_manifest(tmp_path / "a.rows.manifest.json", _manifest())
    _write_manifest(tmp_path / "b.rows.manifest.json", _manifest(model=MODEL_B))
    out_path = tmp_path / "report.md"
    rc = C.main(["--rows", f"{MODEL_A}={rows_a_path}", "--rows", f"{MODEL_B}={rows_b_path}",
                "--out", str(out_path), "--iters", "200", "--seed", "0"])
    assert rc == 0
    assert out_path.exists()
    json_path = out_path.with_suffix(".json")
    assert json_path.exists()
    doc = json.loads(json_path.read_text())
    assert doc["comparable"] is True
    assert MODEL_A in out_path.read_text()


def test_main_refuses_on_a_gate_mismatch_prints_the_reason_exits_nonzero(tmp_path, capsys):
    rows_a_path = tmp_path / "a.rows.jsonl"
    rows_b_path = tmp_path / "b.rows.jsonl"
    _write(rows_a_path, [_row("i1")])
    _write(rows_b_path, [_row("i1")])
    _write_manifest(tmp_path / "a.rows.manifest.json", _manifest())
    man_b = _manifest(model=MODEL_B)
    man_b["runtime"]["corpus_sha256"] = "DIFFERENT"
    _write_manifest(tmp_path / "b.rows.manifest.json", man_b)
    out_path = tmp_path / "report.md"
    rc = C.main(["--rows", f"{MODEL_A}={rows_a_path}", "--rows", f"{MODEL_B}={rows_b_path}",
                "--out", str(out_path)])
    assert rc == 2
    assert not out_path.exists()
    err = capsys.readouterr().err
    assert "corpus sha" in err


def test_main_refuses_with_fewer_than_two_arms(tmp_path, capsys):
    rows_path = tmp_path / "a.rows.jsonl"
    _write(rows_path, [_row("i1")])
    _write_manifest(tmp_path / "a.rows.manifest.json", _manifest())
    rc = C.main(["--rows", f"{MODEL_A}={rows_path}", "--out", str(tmp_path / "report.md")])
    assert rc == 2
    assert "at least 2" in capsys.readouterr().err


def test_main_malformed_rows_kv_refuses_cleanly_never_crashes(tmp_path, capsys):
    """_parse_kv is called OUTSIDE argparse's own parsing step -- a malformed MODEL=PATH value
    must produce a clean REFUSED message and exit 2, never an uncaught ArgumentTypeError."""
    rc = C.main(["--rows", "NO_EQUALS_SIGN_HERE", "--rows", f"{MODEL_B}={tmp_path / 'b.jsonl'}",
                "--out", str(tmp_path / "report.md")])
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().err


def test_main_llm_timeout_mismatch_alone_does_not_refuse(tmp_path):
    rows_a_path = tmp_path / "a.rows.jsonl"
    rows_b_path = tmp_path / "b.rows.jsonl"
    _write(rows_a_path, [_row(f"i{i}") for i in range(5)])
    _write(rows_b_path, [_row(f"i{i}") for i in range(5)])
    _write_manifest(tmp_path / "a.rows.manifest.json", _manifest())
    man_b = _manifest(model=MODEL_B)
    man_b["runtime"]["llm_timeout_s"] = 999.0
    _write_manifest(tmp_path / "b.rows.manifest.json", man_b)
    out_path = tmp_path / "report.md"
    rc = C.main(["--rows", f"{MODEL_A}={rows_a_path}", "--rows", f"{MODEL_B}={rows_b_path}",
                "--out", str(out_path), "--iters", "100"])
    assert rc == 0
    assert "llm_timeout_s differs" in out_path.read_text()
