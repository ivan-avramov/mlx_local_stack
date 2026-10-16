"""C158 (operator 2026-10-14): scoring accepts a declared set of P201 auditors — codex gpt-6-astra (pinned, first) and
Cursor gpt-5.6-sol-high (boxes without codex). P299 (2026-10-15): a recorded audit is valid whatever CLI version is
installed now (see test_p299_audit_record_validity.py); the installed version is provenance for new audits only."""
import json
from pathlib import Path

import pytest

from bench import answer_key
from bench.tests.test_m61_p201 import fixture_rows

REPO = Path(__file__).resolve().parents[3]
RES = REPO / "benchmark/results"
CURSOR_V = "2026.10.01-e373342"


def _no_codex():
    raise FileNotFoundError("codex")


@pytest.fixture
def cursor_only(monkeypatch):
    import web_audit
    import web_audit_cursor
    monkeypatch.setattr(web_audit, "auditor_version", _no_codex)
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)


def _cursor_audit(path, corpus, answer):
    import web_audit
    import web_audit_cursor
    saved = (web_audit.AUDITOR, web_audit.auditor_version)
    web_audit.AUDITOR, web_audit.auditor_version = web_audit_cursor.AUDITOR, web_audit_cursor.cursor_version
    try:
        return web_audit.audit_rows(path, polyglot_root=corpus, auditor=lambda prompt: json.dumps(answer))
    finally:
        web_audit.AUDITOR, web_audit.auditor_version = saved


def test_declared_auditors_order():
    assert [name for name, _ in answer_key.declared_auditors()] == ["codex:gpt-6-astra", "cursor:gpt-5.6-sol-high"]


def test_cursor_audit_counts_when_codex_is_absent(tmp_path, monkeypatch, cursor_only):
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert {r["auditor"] for r in records} == {"cursor:gpt-5.6-sol-high"} and {r["auditor_version"] for r in records} == {CURSOR_V}
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "docs" for st in states for label in st["labels"])


def test_cursor_audit_from_another_version_stays_accepted_P299(tmp_path, monkeypatch, cursor_only):
    import web_audit_cursor
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: "2026.11.01-other")
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "docs" for st in states for label in st["labels"])


def test_no_auditor_available_still_scores_recorded_audits_P299(tmp_path, monkeypatch, cursor_only):
    import web_audit_cursor
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    monkeypatch.setattr(web_audit_cursor, "cursor_version", _no_codex)
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "docs" for st in states for label in st["labels"])


def test_codex_record_is_preferred_when_both_exist(tmp_path, monkeypatch):
    import web_audit
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    _cursor_audit(path, corpus, {"label": "solution", "reason": "cursor says solution"})
    monkeypatch.setattr(web_audit, "auditor_version", lambda: "codex-cli 0.161.0")
    sidecar = web_audit.audit_rows(path, polyglot_root=corpus,
                                   auditor=lambda prompt: json.dumps({"label": "docs", "reason": "codex says docs"}))
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "docs" for st in states for label in st["labels"])


def test_unknown_auditor_label_is_never_accepted(tmp_path, monkeypatch, cursor_only):
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    text = sidecar.read_text().replace("cursor:gpt-5.6-sol-high", "someone:else")
    sidecar.write_text(text)
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "missing" for st in states for label in st["labels"])


@pytest.mark.parametrize("model,cell", [("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", (22, 22)),
                                        ("Qwen3.8-27B-mlx-uniform-4bit", (20, 22))])
def test_real_p223_s1_python_cells_are_final_with_the_cursor_audit(cursor_only, model, cell):
    f = RES / model / "opencode_v2_python.p223.s1.jsonl"
    rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    rep = answer_key.report_rows(rows, audit_sidecar=Path(str(f) + ".webaudit.jsonl"))
    ok = sum(sum(v) for v in rep["strict_items"].values())
    assert (ok, len(rep["strict_items"])) == cell
    assert rep["per_model"][model]["provisional"] is False and rep["per_model"][model]["missing_audits"] == 0


def test_a2_wrapper_rejects_a_non_positive_timeout(monkeypatch, tmp_path):
    import sys
    import web_audit_cursor
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    for bad in ("0", "-5"):
        monkeypatch.setattr(sys, "argv", ["web_audit_cursor.py", str(tmp_path / "rows.jsonl"), "--timeout", bad])
        with pytest.raises(SystemExit) as ei:
            web_audit_cursor.main()
        assert ei.value.code == 2


def test_a3_rows_without_web_entries_run_no_subprocess(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("version probe ran for rows without web fetches"))
    rows = [dict(id="python/x", model="m", sample=0, session_id="s", scaffold="opencode-v2-web-tg1", passed=True,
                 nonconv_kind=None, web_fetches=[], net_shell=[])]
    assert answer_key.report_rows(rows)["strict_n"] == 1


# --------------------------------------------------------------------------- round 2 (A4 = P298 folded into C158)
def _genuine(tmp_path, monkeypatch, answer):
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, answer)
    return rows, sidecar, [json.loads(line) for line in sidecar.read_text().splitlines()]


@pytest.mark.parametrize("mutate", [
    lambda r: r.pop("reason"),
    lambda r: r.update(reason=""),
    lambda r: r.update(reason="two\nlines"),
    lambda r: r.update(reason=7),
    lambda r: r.update(label="other"),
    lambda r: r.update(auditor_version=""),
    lambda r: r.update(prompt_sha256=None),
])
def test_a4_malformed_or_fabricated_records_count_as_missing(tmp_path, monkeypatch, cursor_only, mutate):
    rows, sidecar, records = _genuine(tmp_path, monkeypatch, {"label": "docs", "reason": "language documentation"})
    for r in records:
        mutate(r)
    sidecar.write_text("".join(json.dumps(r) + "\n" for r in records))
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "missing" for st in states for label in st["labels"])


def test_a4_operator_resolution_without_a_preceding_audit_is_ignored(tmp_path, monkeypatch, cursor_only):
    rows, sidecar, records = _genuine(tmp_path, monkeypatch, {"label": "unclear", "reason": "ambiguous"})
    forged = [{**r, "label": "audit_error", "operator_label": "generic", "operator_reason": "ok"} for r in records]
    sidecar.write_text("".join(json.dumps(r) + "\n" for r in forged))      # resolutions only, no genuine record
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "missing" for st in states for label in st["labels"])


def test_a4_operator_resolution_after_a_genuine_unresolved_audit_is_accepted(tmp_path, monkeypatch, cursor_only):
    rows, sidecar, records = _genuine(tmp_path, monkeypatch, {"label": "unclear", "reason": "ambiguous"})
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps({**r, "operator_label": "generic", "operator_reason": "reviewed"}) + "\n")
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "generic" for st in states for label in st["labels"])


def test_a4_resolution_of_a_different_label_than_the_genuine_record_is_ignored(tmp_path, monkeypatch, cursor_only):
    rows, sidecar, records = _genuine(tmp_path, monkeypatch, {"label": "unclear", "reason": "ambiguous"})
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps({**r, "label": "audit_error", "operator_label": "generic", "operator_reason": "x"}) + "\n")
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "unclear" for st in states for label in st["labels"])


def test_a5_offline_default_has_every_declared_probe_absent(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("a declared probe spawned a real CLI"))   # A6
    for name, probe in answer_key.declared_auditors():
        with pytest.raises(FileNotFoundError):
            probe()


def test_a7_a_malformed_later_resolution_does_not_undo_a_valid_one(tmp_path, monkeypatch, cursor_only):
    rows, sidecar, records = _genuine(tmp_path, monkeypatch, {"label": "unclear", "reason": "ambiguous"})
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps({**r, "operator_label": "generic", "operator_reason": "reviewed"}) + "\n")
        for r in records:
            stream.write(json.dumps({**r, "operator_label": "generic", "operator_reason": ""}) + "\n")
            stream.write(json.dumps({**r, "operator_label": "bogus", "operator_reason": "x"}) + "\n")
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "generic" for st in states for label in st["labels"])


def test_a8_a_malformed_record_does_not_block_a_genuine_re_audit(tmp_path, monkeypatch, cursor_only):
    rows, sidecar, records = _genuine(tmp_path, monkeypatch, {"label": "docs", "reason": "language documentation"})
    sidecar.write_text("".join(json.dumps({**r, "reason": ""}) + "\n" for r in records))      # malformed tail only
    path = Path(str(sidecar)[: -len(".webaudit.jsonl")])
    corpus = tmp_path / "corpus"
    _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})      # must re-audit
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "docs" for st in states for label in st["labels"])
