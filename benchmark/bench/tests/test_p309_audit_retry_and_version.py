"""P309 (m5max-128 P299 plan review P8/P9, ported onto the merged P299 + C163 audit code): `--retry-errors` never
re-audits an operator-RESOLVED `audit_error`; an unreadable auditor version fails the audit command before anything
is appended (a null-version record is not an audit), while a leg with nothing pending needs no CLI at all."""
import contextlib
import json
from pathlib import Path

import pytest

from bench import answer_key
from bench.tests.test_c158_auditors import CURSOR_V, _cursor_audit, cursor_only  # noqa: F401
from bench.tests.test_m61_p201 import fixture_rows


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


def _labels(rows, sidecar):
    return [label for st in answer_key.audit_states(rows, audit_sidecar=sidecar) for label in st["labels"]]


def test_retry_errors_never_re_audits_an_operator_resolved_error(tmp_path, monkeypatch, cursor_only):
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)

    def fail(_):
        raise OSError("offline")
    with _as_cursor() as web_audit:
        sidecar = web_audit.audit_rows(path, polyglot_root=corpus, auditor=fail)
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert {r["label"] for r in records} == {"audit_error"}
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps({**r, "operator_label": "generic", "operator_reason": "reviewed"}) + "\n")
    assert set(_labels(rows, sidecar)) == {"generic"}
    calls = []
    with _as_cursor() as web_audit:
        web_audit.audit_rows(path, polyglot_root=corpus, retry_errors=True,
                             auditor=lambda p: calls.append(p) or json.dumps({"label": "solution", "reason": "x"}))
    assert not calls
    assert set(_labels(rows, sidecar)) == {"generic"}


def test_an_unreadable_version_fails_before_anything_is_appended(tmp_path, monkeypatch):
    import web_audit
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)      # conftest: every version probe is absent
    sidecar = Path(str(path) + ".webaudit.jsonl")
    calls = []
    with pytest.raises(web_audit.AuditorVersionError):
        web_audit.audit_rows(path, polyglot_root=corpus, auditor=lambda p: calls.append(p) or "{}")
    assert not calls and not sidecar.exists()


def test_a_fully_audited_leg_needs_no_cli(tmp_path, monkeypatch, cursor_only):
    import web_audit_cursor
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    before = sidecar.read_text()

    def gone():
        raise FileNotFoundError("cursor-agent")
    monkeypatch.setattr(web_audit_cursor, "cursor_version", gone)
    with _as_cursor() as web_audit:
        web_audit.audit_rows(path, polyglot_root=corpus, auditor=lambda p: pytest.fail("auditor called"))
    assert sidecar.read_text() == before


# ----------------------------------------------------------------------------- P309 review round 1 (f76eaa4b)
def _failed_audit(tmp_path, monkeypatch):
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)

    def fail(_):
        raise OSError("offline")
    with _as_cursor() as web_audit:
        sidecar = web_audit.audit_rows(path, polyglot_root=corpus, auditor=fail)
    return path, corpus, rows, sidecar, [json.loads(line) for line in sidecar.read_text().splitlines()]


def _resolve(sidecar, records):
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps({**r, "operator_label": "generic", "operator_reason": "reviewed"}) + "\n")


def test_r1p1_a_grandfathered_legacy_error_can_be_operator_resolved(tmp_path, monkeypatch, cursor_only):
    path, corpus, rows, sidecar, records = _failed_audit(tmp_path, monkeypatch)
    legacy = [{k: v for k, v in r.items() if k != "context_sha256"} for r in records]      # pre-C163 shape
    inventory = tmp_path / "legacy.json"
    inventory.write_text(json.dumps({"records": [answer_key.record_digest(r) for r in legacy]}))
    monkeypatch.setattr(answer_key, "LEGACY_INVENTORY", inventory)
    sidecar.write_text("".join(json.dumps(r) + "\n" for r in legacy))
    assert set(_labels(rows, sidecar)) == {"audit_error"}
    _resolve(sidecar, legacy)
    assert set(_labels(rows, sidecar)) == {"generic"}
    calls = []
    with _as_cursor() as web_audit:
        web_audit.audit_rows(path, polyglot_root=corpus, retry_errors=True, auditor=lambda p: calls.append(p) or "{}")
    assert not calls


@pytest.mark.parametrize("version", [CURSOR_V, "2026.11.01-other"])
def test_r1p4_a_later_genuine_record_supersedes_a_resolution(tmp_path, monkeypatch, cursor_only, version):
    path, corpus, rows, sidecar, records = _failed_audit(tmp_path, monkeypatch)
    _resolve(sidecar, records)
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps({**r, "auditor_version": version, "label": "docs",
                                     "reason": "language documentation"}) + "\n")
    assert set(_labels(rows, sidecar)) == {"docs"}


def test_r1p4_a_resolved_error_needs_no_cli_even_with_retry_errors(tmp_path, monkeypatch, cursor_only):
    import web_audit_cursor
    path, corpus, rows, sidecar, records = _failed_audit(tmp_path, monkeypatch)
    _resolve(sidecar, records)
    before = sidecar.read_text()

    def gone():
        raise FileNotFoundError("cursor-agent")
    monkeypatch.setattr(web_audit_cursor, "cursor_version", gone)
    with _as_cursor() as web_audit:
        web_audit.audit_rows(path, polyglot_root=corpus, retry_errors=True, auditor=lambda p: pytest.fail("called"))
    assert sidecar.read_text() == before


def test_r1p4_an_unreadable_version_leaves_an_existing_sidecar_untouched(tmp_path, monkeypatch, cursor_only):
    import web_audit_cursor
    path, corpus, rows, sidecar, records = _failed_audit(tmp_path, monkeypatch)      # unresolved errors: pending
    before = sidecar.read_bytes()

    def gone():
        raise FileNotFoundError("cursor-agent")
    monkeypatch.setattr(web_audit_cursor, "cursor_version", gone)
    with _as_cursor() as web_audit:
        with pytest.raises(web_audit.AuditorVersionError):
            web_audit.audit_rows(path, polyglot_root=corpus, retry_errors=True, auditor=lambda p: pytest.fail("x"))
    assert sidecar.read_bytes() == before
