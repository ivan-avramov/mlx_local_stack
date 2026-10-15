"""C163 (operator go 2026-10-15; from the P299 cold review P1): the auditor is shown the fetch's url/command/status
besides its content, so the audit identity carries `context_sha256` = sha256 of those three fields. A record whose
context differs from the row's does not apply and is re-audited. Legacy records (no `context_sha256`) stay accepted
as recorded and are counted per model as `legacy_audits`."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import answer_key
from bench.tests.test_c158_auditors import CURSOR_V, _cursor_audit, _no_codex
from bench.tests.test_m61_p201 import fixture_rows

REPO = Path(__file__).resolve().parents[3]
RES = REPO / "benchmark/results"


def _records(sidecar):
    return [json.loads(line) for line in sidecar.read_text().splitlines() if line.strip()]


def _labels(states):
    return [label for st in states for label in st["labels"]]


def _rewrite_rows(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


@pytest.fixture
def audited(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    return path, corpus, rows, sidecar


def test_context_sha256_is_the_digest_of_url_command_and_status():
    entry = {"url": "https://x.invalid/a", "command": None, "status": "completed", "path": "p", "sha256": "s"}
    expected = hashlib.sha256(json.dumps({"url": "https://x.invalid/a", "command": None, "status": "completed"},
                                         sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert answer_key.context_sha256(entry) == expected
    assert answer_key.context_sha256({"url": "https://x.invalid/a", "status": "completed"}) == expected   # absent == null


def test_new_records_carry_the_context_digest(audited):
    path, corpus, rows, sidecar = audited
    for r in _records(sidecar):
        assert r["context_sha256"] == answer_key.context_sha256(rows[0]["web_fetches"][0])


@pytest.mark.parametrize("field,value", [("url", "https://fixture.invalid/other"), ("command", "curl x"),
                                         ("status", "denied")])
def test_a_changed_context_field_makes_the_recorded_audit_not_apply(audited, field, value):
    path, corpus, rows, sidecar = audited
    rows[1]["web_fetches"][0][field] = value
    states = answer_key.audit_states(rows, audit_sidecar=sidecar)
    assert _labels(states) == ["docs", "missing", "docs"]


@pytest.mark.parametrize("field,value", [("url", "https://fixture.invalid/other"), ("command", "curl x"),
                                         ("status", "denied")])
def test_a_changed_context_field_is_re_audited_and_only_it(audited, field, value):
    path, corpus, rows, sidecar = audited
    rows[1]["web_fetches"][0][field] = value
    _rewrite_rows(path, rows)
    calls = []
    def fake(prompt):
        calls.append(json.loads(prompt.split("INPUT_JSON\n", 1)[1]))
        return json.dumps({"label": "generic", "reason": "re-audited"})
    import web_audit
    import web_audit_cursor
    saved = (web_audit.AUDITOR, web_audit.auditor_version)
    web_audit.AUDITOR, web_audit.auditor_version = web_audit_cursor.AUDITOR, web_audit_cursor.cursor_version
    try:
        web_audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    finally:
        web_audit.AUDITOR, web_audit.auditor_version = saved
    assert len(calls) == 1 and calls[0][field] == value
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs", "generic", "docs"]


def _make_legacy(sidecar, monkeypatch, tmp_path, records=None):
    """Strip the digest from the sidecar's records and grandfather exactly those records (review P1)."""
    records = _records(sidecar) if records is None else records
    legacy = [{k: v for k, v in r.items() if k != "context_sha256"} for r in records]
    sidecar.write_text("".join(json.dumps(r) + "\n" for r in legacy))
    inventory = tmp_path / "legacy_audit_records.json"
    inventory.write_text(json.dumps({"records": [answer_key.record_digest(r) for r in legacy]}))
    monkeypatch.setattr(answer_key, "LEGACY_INVENTORY", inventory)
    return legacy


def test_legacy_records_without_a_context_digest_stay_accepted_and_are_counted(audited, monkeypatch, tmp_path):
    path, corpus, rows, sidecar = audited
    _make_legacy(sidecar, monkeypatch, tmp_path)
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs"] * 3
    rep = answer_key.report_rows(rows, audit_sidecar=sidecar)
    assert rep["per_model"][None]["legacy_audits"] == 3 and rep["legacy_audits"] == 3
    assert rep["missing_audits"] == 0 and rep["provisional"] is False


def test_legacy_records_are_not_re_audited(audited, monkeypatch, tmp_path):
    path, corpus, rows, sidecar = audited
    _make_legacy(sidecar, monkeypatch, tmp_path)
    sidecar2 = _cursor_audit(path, corpus, {"label": "solution", "reason": "must not be called"})
    assert sidecar2 == sidecar and len(_records(sidecar)) == 3


def test_a_grandfathered_legacy_record_applies_after_a_context_change_counted_and_not_re_audited(
        audited, monkeypatch, tmp_path):
    """Review P3: a legacy record cannot see a context change; it applies to the row as it is now, the
    `legacy_audits` count is the disclosure, and no auditor call is made."""
    path, corpus, rows, sidecar = audited
    _make_legacy(sidecar, monkeypatch, tmp_path)
    rows[1]["web_fetches"][0]["status"] = "denied"
    _rewrite_rows(path, rows)
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs"] * 3
    assert answer_key.report_rows(rows, audit_sidecar=sidecar)["legacy_audits"] == 3
    _cursor_audit(path, corpus, {"label": "solution", "reason": "must not be called"})
    assert len(_records(sidecar)) == 3


@pytest.mark.parametrize("digest_value", ["omitted", None])
def test_a_new_record_without_a_digest_is_not_an_audit(audited, digest_value):
    """Review P1: only the frozen inventory is legacy; an appended record without a digest is rejected."""
    path, corpus, rows, sidecar = audited
    records = _records(sidecar)
    forged = []
    for r in records:
        f = {k: v for k, v in r.items() if k != "context_sha256"} | {"label": "docs", "reason": "no digest"}
        if digest_value is None:
            f["context_sha256"] = None
        forged.append(f)
    sidecar.write_text("".join(json.dumps(r) + "\n" for r in forged))
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["missing"] * 3


def test_the_frozen_inventory_equals_the_committed_digest_less_records_exactly():
    built = answer_key.build_legacy_inventory(RES)["records"]
    assert sorted(answer_key.legacy_record_digests()) == built and len(built) == 5


@pytest.mark.parametrize("legacy_first", [True, False])
def test_retry_errors_re_audits_a_digest_error_even_when_a_legacy_success_exists(audited, monkeypatch, tmp_path,
                                                                                 legacy_first):
    """Review P2: the record the scorer applies (digest first) decides the retry; exactly one call, both orders."""
    path, corpus, rows, sidecar = audited
    digest_records = _records(sidecar)
    legacy = _make_legacy(sidecar, monkeypatch, tmp_path, records=digest_records[1:2])          # legacy docs, row 1
    error = {**digest_records[1], "label": "audit_error", "reason": "Auditor failed: OSError."}  # digest error, row 1
    others = [digest_records[0], digest_records[2]]
    order = legacy + [error] if legacy_first else [error] + legacy
    sidecar.write_text("".join(json.dumps(r) + "\n" for r in others + order))
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs", "audit_error", "docs"]
    calls = []
    def fake(prompt):
        calls.append(prompt)
        return json.dumps({"label": "generic", "reason": "retried"})
    import web_audit
    import web_audit_cursor
    saved = (web_audit.AUDITOR, web_audit.auditor_version)
    web_audit.AUDITOR, web_audit.auditor_version = web_audit_cursor.AUDITOR, web_audit_cursor.cursor_version
    try:
        web_audit.audit_rows(path, polyglot_root=corpus, auditor=fake, retry_errors=True)
    finally:
        web_audit.AUDITOR, web_audit.auditor_version = saved
    assert len(calls) == 1
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs", "generic", "docs"]


def test_a_digest_mismatch_never_falls_back_to_a_legacy_match(audited):
    """A record WITH a digest for the old context never matches as legacy after a context change."""
    path, corpus, rows, sidecar = audited
    rows[1]["web_fetches"][0]["status"] = "denied"
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs", "missing", "docs"]


@pytest.mark.parametrize("legacy_first", [True, False])
def test_a_digest_record_is_preferred_over_a_legacy_record_whatever_the_order(audited, monkeypatch, tmp_path,
                                                                             legacy_first):
    path, corpus, rows, sidecar = audited
    records = _records(sidecar)
    legacy = _make_legacy(sidecar, monkeypatch, tmp_path,
                          records=[{**r, "label": "solution", "reason": "legacy says solution"} for r in records])
    order = legacy + records if legacy_first else records + legacy
    sidecar.write_text("".join(json.dumps(r) + "\n" for r in order))
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs"] * 3


def test_counts_do_not_count_digest_records_as_legacy(audited):
    path, corpus, rows, sidecar = audited
    rep = answer_key.report_rows(rows, audit_sidecar=sidecar)
    assert rep["legacy_audits"] == 0


@pytest.mark.parametrize("model,cell,legacy", [("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", (22, 22), 1),
                                               ("Qwen3.8-27B-mlx-uniform-4bit", (20, 22), 2)])
def test_real_p223_s1_python_cells_stay_final_with_their_legacy_audits_counted(model, cell, legacy):
    f = RES / model / "opencode_v2_python.p223.s1.jsonl"
    rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    rep = answer_key.report_rows(rows, audit_sidecar=Path(str(f) + ".webaudit.jsonl"))
    assert (sum(sum(v) for v in rep["strict_items"].values()), len(rep["strict_items"])) == cell
    assert rep["per_model"][model]["provisional"] is False and rep["per_model"][model]["missing_audits"] == 0
    assert rep["per_model"][model]["legacy_audits"] == legacy
