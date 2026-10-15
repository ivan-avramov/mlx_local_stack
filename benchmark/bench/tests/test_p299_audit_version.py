"""P299 (operator 2026-10-14: auditor CLIs update daily): an audit is valid by (declared auditor, recorded version,
prompt sha, evidence identity). The version installed NOW is provenance only and never gates acceptance."""
import contextlib
import json
from pathlib import Path

import pytest

from bench import answer_key
from bench.tests.test_c158_auditors import CURSOR_V, RES, _cursor_audit, _genuine, cursor_only  # noqa: F401
from bench.tests.test_m61_p201 import fixture_rows


def _labels(rows, sidecar):
    return [label for st in answer_key.audit_states(rows, audit_sidecar=sidecar) for label in st["labels"]]


@contextlib.contextmanager
def _as_cursor():
    import web_audit
    import web_audit_cursor
    saved = (web_audit.AUDITOR, web_audit.auditor_version)
    web_audit.AUDITOR, web_audit.auditor_version = web_audit_cursor.AUDITOR, web_audit_cursor.cursor_version
    try:
        yield web_audit
    finally:
        web_audit.AUDITOR, web_audit.auditor_version = saved


def _fail_probe(*a, **k):
    pytest.fail("scoring called an auditor version probe")


def _no_cli():
    raise FileNotFoundError("gone")


def _set_version(monkeypatch, version):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: version)


def test_declared_auditors_are_names_only():
    assert answer_key.declared_auditors() == ["codex:gpt-6-astra", "cursor:gpt-5.6-sol-high"]


def test_a_cli_update_keeps_the_audit_accepted(tmp_path, monkeypatch, cursor_only):
    rows, sidecar, _ = _genuine(tmp_path, monkeypatch, {"label": "docs", "reason": "language documentation"})
    _set_version(monkeypatch, "2026.11.01-other")
    assert set(_labels(rows, sidecar)) == {"docs"}


def test_scoring_needs_no_installed_cli(tmp_path, monkeypatch, cursor_only):
    import web_audit
    import web_audit_cursor
    rows, sidecar, _ = _genuine(tmp_path, monkeypatch, {"label": "docs", "reason": "language documentation"})
    monkeypatch.setattr(web_audit, "auditor_version", _fail_probe)
    monkeypatch.setattr(web_audit_cursor, "cursor_version", _fail_probe)
    assert set(_labels(rows, sidecar)) == {"docs"}
    assert answer_key.report_rows(rows, audit_sidecar=sidecar)["missing_audits"] == 0


def test_a_new_version_audits_only_new_evidence(tmp_path, monkeypatch, cursor_only):
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    before = sidecar.read_text()
    _set_version(monkeypatch, "2026.11.01-other")
    calls = []
    with _as_cursor() as web_audit:
        again = web_audit.audit_rows(path, polyglot_root=corpus, auditor=lambda p: calls.append(p) or "{}")
    assert not calls and again.read_text() == before


def test_retry_errors_under_a_new_version_replaces_the_error(tmp_path, monkeypatch, cursor_only):
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)

    def fail(_):
        raise OSError("offline")
    with _as_cursor() as web_audit:
        sidecar = web_audit.audit_rows(path, polyglot_root=corpus, auditor=fail)
        assert set(_labels(rows, sidecar)) == {"audit_error"}
        web_audit.auditor_version = lambda: "2026.11.01-other"      # the CLI updated between the two runs
        web_audit.audit_rows(path, polyglot_root=corpus, retry_errors=True,
                             auditor=lambda p: json.dumps({"label": "docs", "reason": "language documentation"}))
    assert set(_labels(rows, sidecar)) == {"docs"}
    assert "2026.11.01-other" in sidecar.read_text()


def test_a_resolved_audit_error_is_not_retried(tmp_path, monkeypatch, cursor_only):
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "unclear", "reason": "ambiguous"})
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    sidecar.write_text("".join(json.dumps({**r, "label": "audit_error"}) + "\n" for r in records))
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps({**r, "label": "audit_error", "operator_label": "generic",
                                     "operator_reason": "reviewed"}) + "\n")
    calls = []
    with _as_cursor() as web_audit:
        web_audit.audit_rows(path, polyglot_root=corpus, retry_errors=True, auditor=lambda p: calls.append(p) or "{}")
    assert not calls
    assert set(_labels(rows, sidecar)) == {"generic"}


def test_a_resolution_must_match_the_base_version(tmp_path, monkeypatch, cursor_only):
    rows, sidecar, records = _genuine(tmp_path, monkeypatch, {"label": "unclear", "reason": "ambiguous"})
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps({**r, "auditor_version": "other-version", "operator_label": "generic",
                                     "operator_reason": "reviewed"}) + "\n")
    assert set(_labels(rows, sidecar)) == {"unclear"}


def test_the_latest_record_wins_across_versions(tmp_path, monkeypatch, cursor_only):
    rows, sidecar, records = _genuine(tmp_path, monkeypatch, {"label": "docs", "reason": "language documentation"})
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps({**r, "auditor_version": "2026.11.01-other", "label": "solution",
                                     "reason": "the answer"}) + "\n")
    assert set(_labels(rows, sidecar)) == {"solution"}


def test_an_unobtainable_version_fails_before_anything_is_appended(tmp_path, monkeypatch):
    import web_audit
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)      # conftest: every version probe is absent
    sidecar = Path(str(path) + ".webaudit.jsonl")
    calls = []
    with pytest.raises(web_audit.AuditorVersionError):
        web_audit.audit_rows(path, polyglot_root=corpus, auditor=lambda p: calls.append(p) or "{}")
    assert not calls and not sidecar.exists()


def test_a_fully_audited_leg_needs_no_cli(tmp_path, monkeypatch, cursor_only):
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    before = sidecar.read_text()
    _set_version(monkeypatch, None)
    monkeypatch.setattr("web_audit_cursor.cursor_version", _no_cli)
    with _as_cursor() as web_audit:
        assert web_audit.audit_rows(path, polyglot_root=corpus, auditor=_fail_probe).read_text() == before


@pytest.mark.parametrize("model,cell", [("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", (22, 22)),
                                        ("Qwen3.8-27B-mlx-uniform-4bit", (20, 22))])
def test_real_p223_s1_python_cells_are_final_with_every_cli_absent(model, cell):
    f = RES / model / "opencode_v2_python.p223.s1.jsonl"
    rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    rep = answer_key.report_rows(rows, audit_sidecar=Path(str(f) + ".webaudit.jsonl"))     # conftest: probes absent
    assert (sum(sum(v) for v in rep["strict_items"].values()), len(rep["strict_items"])) == cell
    assert rep["per_model"][model]["provisional"] is False and rep["per_model"][model]["missing_audits"] == 0
