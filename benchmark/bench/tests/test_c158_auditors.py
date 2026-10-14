"""C158 (operator 2026-10-14): scoring accepts a declared set of P201 auditors — codex gpt-6-astra (pinned, first) and
Cursor gpt-5.6-sol-high (boxes without codex) — each keyed on its own currently installed CLI version."""
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


def test_cursor_audit_from_another_version_is_missing(tmp_path, monkeypatch, cursor_only):
    import web_audit_cursor
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: "2026.11.01-other")
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "missing" for st in states for label in st["labels"])


def test_no_auditor_available_means_missing(tmp_path, monkeypatch, cursor_only):
    import web_audit_cursor
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    monkeypatch.setattr(web_audit_cursor, "cursor_version", _no_codex)
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert all(label == "missing" for st in states for label in st["labels"])


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
