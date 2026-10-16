"""P299 (operator 2026-10-15): tool versions churn daily, so a recorded audit is valid for the record by
(declared auditor, recorded version, prompt sha, evidence identity). The CLI version installed NOW is provenance for
NEW audits only; it never gates acceptance, and a new auditor version audits only new or retried evidence."""
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


def test_a_recorded_audit_is_accepted_after_the_auditor_cli_updates(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: "2026.11.01-other")
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs"] * 3


def test_a_recorded_audit_is_accepted_on_a_box_without_any_auditor_cli(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    monkeypatch.setattr(web_audit_cursor, "cursor_version", _no_codex)      # neither CLI answers (conftest: codex absent)
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs"] * 3


def test_scoring_rows_with_web_entries_never_spawns_a_version_probe(tmp_path, monkeypatch):
    import subprocess
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    import web_audit
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("scoring probed an auditor CLI version"))
    # review P2: the declared probes themselves must not be called either (they are stubs in tests)
    monkeypatch.setattr(web_audit, "auditor_version", lambda: pytest.fail("scoring called the codex version probe"))
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: pytest.fail("scoring called the cursor probe"))
    rep = answer_key.report_rows(rows, audit_sidecar=sidecar)
    assert rep["strict_n"] == 2 and rep["missing_audits"] == 0 and rep["provisional"] is False


def test_a_recorded_audit_still_requires_a_nonempty_recorded_version(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    records = _records(sidecar)
    for r in records:
        r["auditor_version"] = None
    sidecar.write_text("".join(json.dumps(r) + "\n" for r in records))
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["missing"] * 3


def test_a_new_auditor_version_audits_only_new_evidence(tmp_path, monkeypatch):
    import web_audit as audit
    from bench.tests.conftest import REAL_AUDITOR_PROBES
    monkeypatch.setattr(audit, "auditor_version", REAL_AUDITOR_PROBES["codex"])
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    version = ["codex-cli 0.161.0"]
    monkeypatch.setattr(audit.subprocess, "run", lambda argv, **k: SimpleNamespace(stdout=version[0] + "\n"))
    calls = []
    def fake(prompt):
        calls.append(prompt)
        return '{"label":"docs","reason":"Reference."}'
    sidecar = audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    assert len(calls) == 3
    version[0] = "codex-cli 0.162.0"
    audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    assert len(calls) == 3, "a CLI update must not re-audit recorded evidence"
    # new evidence (a fourth row) under the new version is audited, and only it
    extra = dict(rows[1], id="python/bowling", sample=1, session_id="fixture-3")
    path.write_text(path.read_text() + json.dumps(extra) + "\n")
    audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    assert len(calls) == 4
    versions = {r["session_id"]: r["auditor_version"] for r in _records(sidecar)}
    assert versions == {"fixture-0": "codex-cli 0.161.0", "fixture-1": "codex-cli 0.161.0",
                        "fixture-2": "codex-cli 0.161.0", "fixture-3": "codex-cli 0.162.0"}
    monkeypatch.setattr(audit, "auditor_version", _no_codex)
    rep = answer_key.report_rows(rows + [extra], audit_sidecar=sidecar)
    assert rep["missing_audits"] == 0 and rep["provisional"] is False and rep["strict_n"] == 3


def test_retry_errors_under_a_new_version_re_audits_only_the_errors(tmp_path, monkeypatch):
    import web_audit as audit
    from bench.tests.conftest import REAL_AUDITOR_PROBES
    monkeypatch.setattr(audit, "auditor_version", REAL_AUDITOR_PROBES["codex"])
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    version = ["codex-cli 0.161.0"]
    monkeypatch.setattr(audit.subprocess, "run", lambda argv, **k: SimpleNamespace(stdout=version[0] + "\n"))
    answers = iter(['{"label":"docs","reason":"Reference."}', OSError("auditor down"), '{"label":"docs","reason":"Reference."}'])
    calls = []
    def flaky(prompt):
        calls.append(prompt)
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer
    sidecar = audit.audit_rows(path, polyglot_root=corpus, auditor=flaky)
    assert sorted(r["label"] for r in _records(sidecar)) == ["audit_error", "docs", "docs"]
    version[0] = "codex-cli 0.162.0"
    answers = iter(['{"label":"generic","reason":"Retried."}'])
    audit.audit_rows(path, polyglot_root=corpus, auditor=flaky, retry_errors=True)
    assert len(calls) == 4
    records = _records(sidecar)
    assert [r["auditor_version"] for r in records] == ["codex-cli 0.161.0"] * 3 + ["codex-cli 0.162.0"]
    assert sorted(_labels(answer_key.audit_states(rows, audit_sidecar=sidecar))) == ["docs", "docs", "generic"]


def test_the_latest_record_of_the_same_auditor_wins_across_versions(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    older = _records(sidecar)
    with sidecar.open("a") as stream:                         # a later retry under a newer CLI
        for r in older:
            stream.write(json.dumps({**r, "auditor_version": "2026.11.01-other", "label": "solution",
                                     "reason": "reference solution"}) + "\n")
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["solution"] * 3


def test_codex_record_is_preferred_over_cursor_whatever_the_versions(tmp_path, monkeypatch):
    import web_audit
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    _cursor_audit(path, corpus, {"label": "solution", "reason": "cursor says solution"})
    monkeypatch.setattr(web_audit, "auditor_version", lambda: "codex-cli 0.150.0")
    sidecar = web_audit.audit_rows(path, polyglot_root=corpus,
                                   auditor=lambda prompt: json.dumps({"label": "docs", "reason": "codex says docs"}))
    monkeypatch.setattr(web_audit, "auditor_version", _no_codex)
    monkeypatch.setattr(web_audit_cursor, "cursor_version", _no_codex)
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs"] * 3


def test_an_operator_resolution_survives_a_cli_update(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "unclear", "reason": "ambiguous"})
    with sidecar.open("a") as stream:
        for r in _records(sidecar):
            stream.write(json.dumps({**r, "operator_label": "generic", "operator_reason": "reviewed"}) + "\n")
    monkeypatch.setattr(web_audit_cursor, "cursor_version", _no_codex)
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["generic"] * 3


def test_a_changed_prompt_sha_still_invalidates_recorded_audits(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar, prompt_sha256="0" * 64)) == ["missing"] * 3


@pytest.mark.parametrize("model,cell", [("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", (22, 22)),
                                        ("Qwen3.8-27B-mlx-uniform-4bit", (20, 22))])
def test_real_p223_s1_python_cells_are_final_with_no_auditor_cli_installed(model, cell):
    # conftest default: every declared probe absent (the shape of a box without codex or cursor-agent)
    f = RES / model / "opencode_v2_python.p223.s1.jsonl"
    rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    rep = answer_key.report_rows(rows, audit_sidecar=Path(str(f) + ".webaudit.jsonl"))
    assert (sum(sum(v) for v in rep["strict_items"].values()), len(rep["strict_items"])) == cell
    assert rep["per_model"][model]["provisional"] is False and rep["per_model"][model]["missing_audits"] == 0


# --------------------------------------------------------------------------- review round 1 (codex gpt-6-astra) P3
def _append(sidecar, records):
    with sidecar.open("a") as stream:
        for r in records:
            stream.write(json.dumps(r) + "\n")


def test_interleaved_versions_the_last_write_wins_not_the_first_seen_version(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})   # A: docs
    base = _records(sidecar)
    _append(sidecar, [{**r, "auditor_version": "B", "label": "docs", "reason": "docs again"} for r in base])   # B: docs
    _append(sidecar, [{**r, "label": "solution", "reason": "reference solution"} for r in base])                # A: solution
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["solution"] * 3


def test_interleaved_versions_a_valid_resolution_on_the_older_version_is_the_last_word(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "unclear", "reason": "ambiguous"})                  # A: unclear
    base = _records(sidecar)
    _append(sidecar, [{**r, "auditor_version": "B", "label": "docs", "reason": "docs"} for r in base])     # B: docs
    _append(sidecar, [{**r, "operator_label": "generic", "operator_reason": "reviewed"} for r in base])    # A: resolved
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["generic"] * 3


def test_malformed_and_orphan_records_appended_later_never_shadow_an_accepted_one(tmp_path, monkeypatch):
    import web_audit_cursor
    monkeypatch.setattr(web_audit_cursor, "cursor_version", lambda: CURSOR_V)
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    sidecar = _cursor_audit(path, corpus, {"label": "docs", "reason": "language documentation"})
    base = _records(sidecar)
    _append(sidecar, [{**r, "auditor_version": "B", "label": "solution", "reason": ""} for r in base])      # malformed
    _append(sidecar, [{**r, "auditor_version": "C", "label": "unclear", "reason": "x",
                       "operator_label": "solution", "operator_reason": "forged"} for r in base])           # orphan resolution
    _append(sidecar, [{**r, "auditor_version": "D", "auditor": "someone:else", "label": "solution",
                       "reason": "not declared"} for r in base])                                            # undeclared auditor
    assert _labels(answer_key.audit_states(rows, audit_sidecar=sidecar)) == ["docs"] * 3


def test_older_docs_then_newer_error_retries_exactly_once_and_the_error_is_the_latest_word(tmp_path, monkeypatch):
    import web_audit as audit
    from bench.tests.conftest import REAL_AUDITOR_PROBES
    monkeypatch.setattr(audit, "auditor_version", REAL_AUDITOR_PROBES["codex"])
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    version = ["codex-cli 0.161.0"]
    monkeypatch.setattr(audit.subprocess, "run", lambda argv, **k: SimpleNamespace(stdout=version[0] + "\n"))
    calls = []
    def fake(prompt):
        calls.append(prompt)
        return '{"label":"generic","reason":"Retried."}'
    sidecar = audit.audit_rows(path, polyglot_root=corpus, auditor=lambda p: '{"label":"docs","reason":"Reference."}')
    first = _records(sidecar)[0]
    _append(sidecar, [{**first, "auditor_version": "codex-cli 0.162.0", "label": "audit_error", "reason": "Auditor failed: OSError."}])
    assert sorted(_labels(answer_key.audit_states(rows, audit_sidecar=sidecar))) == ["audit_error", "docs", "docs"]
    audit.audit_rows(path, polyglot_root=corpus, auditor=fake)                      # without --retry-errors: nothing
    assert calls == []
    version[0] = "codex-cli 0.163.0"
    audit.audit_rows(path, polyglot_root=corpus, auditor=fake, retry_errors=True)   # exactly the one error
    assert len(calls) == 1
    assert sorted(_labels(answer_key.audit_states(rows, audit_sidecar=sidecar))) == ["docs", "docs", "generic"]
    assert _records(sidecar)[-1]["auditor_version"] == "codex-cli 0.163.0"
