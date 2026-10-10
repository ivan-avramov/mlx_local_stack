import hashlib
import json
from pathlib import Path
import pytest
from m62 import universe_preflight as up, replay
from bench.structured_grade import Grade
from bench.token_turn_gate import TransportAbort
from bench.tests.test_token_turn_gate import event, usage, assistant


def test_universe_reference_mapping_baseline_freeze_hash_and_refusal(tmp_path):
    src = tmp_path / "corpus/python/exercises/practice/one"
    (src / ".meta").mkdir(parents=True)
    (src / ".meta/config.json").write_text(
        json.dumps(
            {
                "files": {
                    "solution": ["solution.py"],
                    "example": [".meta/example.py"],
                    "test": ["official_test.py"],
                }
            }
        )
    )
    (src / "solution.py").write_text("stub")
    (src / ".meta/example.py").write_text("reference")
    (src / "official_test.py").write_text("test")
    manifest = {"entries": [{"id": "python/one"}, {"id": "go/counter"}]}
    private = tmp_path / "private"
    private.mkdir()
    out = tmp_path / "universe.json"
    calls = []

    def grade(lang, work, test, private, **kw):
        assert not (work / ".meta").exists()
        text = (work / "solution.py").read_text()
        calls.append(text)
        return Grade(
            passing=(
                {("official_test.py", "C", "test")} if text == "reference" else set()
            ),
            collected={("official_test.py", "C", "test")},
            returncode=0 if text == "reference" else 1,
        )

    doc = up.build(
        manifest, tmp_path / "corpus", private, grader=grade, expected_count=1
    )
    assert (
        calls == ["stub", "reference"]
        and doc["items"]["python/one"]["baseline_failing"] == 1
    )
    assert not list(private.iterdir())
    up.freeze(out, doc)
    loaded, sha = up.load(out)
    assert loaded == doc and sha == hashlib.sha256(out.read_bytes()).hexdigest()
    with pytest.raises(TransportAbort):
        up.freeze(out, doc)
    out.write_text("{}")
    with pytest.raises(TransportAbort):
        up.load(out)


def test_universe_refuses_missing_reference_and_wrong_count(tmp_path):
    with pytest.raises(TransportAbort):
        up.build({"entries": []}, tmp_path, tmp_path)
    with pytest.raises(TransportAbort):
        up.build(
            {"entries": [{"id": "python/one"}]}, tmp_path, tmp_path, expected_count=1
        )


def test_replay_ingestion_sha_and_no_progress(tmp_path):
    path = tmp_path / "events.jsonl"
    raw = b"".join(
        (json.dumps(e) + "\n").encode()
        for e in [event("step_start"), event("step_finish", tokens=usage(81920))]
    )
    path.write_bytes(raw)
    entry = {
        "events_path": str(path),
        "events_sha256": hashlib.sha256(raw).hexdigest(),
        "id": "python/one",
        "identity_matched": True,
        "valid_item": True,
        "passed": True,
        "fixture": None,
    }
    export = tmp_path / "export.json"
    export.write_text(json.dumps(dict(messages=[assistant(output=81920)])))
    entry.update(transcript_path=str(export), export_sha256=hashlib.sha256(export.read_bytes()).hexdigest())
    result = replay.replay_entry(entry, tmp_path)
    assert result["stop_reason"] == "stalled" and result["first_crossing_request"] == 1
    assert not replay.criteria([entry], [result], expected_valid=1)[
        "valid_passes_unstopped"
    ]
    path.write_bytes(raw + b"changed")
    with pytest.raises(TransportAbort, match="sha256"):
        replay.replay_entry(entry, tmp_path)


def test_replay_criteria_oracles_and_missing_final_usage(tmp_path):
    entries = [
        {"passed": False, "fixture": k} for k in ("looping@request15", "looping@request22", "no_stop")
    ]
    results = [
        dict(
            stop_reason="looping",
            first_crossing_request=15,
            terminal_usage_complete=True,
        ),
        dict(
            stop_reason="looping",
            first_crossing_request=22,
            terminal_usage_complete=True,
        ),
        dict(
            stop_reason=None, first_crossing_request=None, terminal_usage_complete=False
        ),
    ]
    checks = replay.criteria(entries, results, expected_valid=0)
    assert (
        checks["looping_at_15"]
        and checks["alphametics_looping_at_22"]
        and checks["book_store_no_stop"]
    )
    assert not checks["all_request_usage_available"]


def test_universe_first_test_entry_is_official_helpers_protected(tmp_path):
    """python/paasio lists `["paasio_test.py", "test_utils.py"]`: files.test[0] is the official test (as the legacy
    probe's `_solution_and_test`), later entries are helpers and stay protected like every prepared file."""
    src = tmp_path / "corpus/python/exercises/practice/one"
    (src / ".meta").mkdir(parents=True)
    (src / ".meta/config.json").write_text(json.dumps({"files": {
        "solution": ["solution.py"], "example": [".meta/example.py"],
        "test": ["official_test.py", "test_utils.py"]}}))
    (src / "solution.py").write_text("stub")
    (src / ".meta/example.py").write_text("reference")
    (src / "official_test.py").write_text("test")
    (src / "test_utils.py").write_text("helper")
    private = tmp_path / "private"
    private.mkdir()
    seen = []

    def grade(lang, work, test, private, **kw):
        seen.append(test)
        ok = (work / "solution.py").read_text() == "reference"
        ident = ("official_test.py", "C", "test")
        return Grade(passing={ident} if ok else set(), collected={ident}, returncode=0 if ok else 1)

    doc = up.build({"entries": [{"id": "python/one"}]}, tmp_path / "corpus", private, grader=grade, expected_count=1)
    entry = doc["items"]["python/one"]
    assert seen == ["official_test.py", "official_test.py"] and entry["test"] == "official_test.py"
    assert "test_utils.py" in entry["protected"]


def test_replay_misattributed_entries_sha_verified_never_ingested(tmp_path):
    """Spec §6 V2: the 54 misattributed rows are listed and excluded; their files are still sha-verified."""
    events, export = tmp_path / "e.jsonl", tmp_path / "x.json"
    events.write_bytes(b"not json at all\n")
    export.write_text("{}")
    entry = dict(id="go/bowling", identity_matched=False, passed=True, valid_item=True, fixture=None,
                 events_path=str(events), events_sha256=hashlib.sha256(events.read_bytes()).hexdigest(),
                 transcript_path=str(export), export_sha256=hashlib.sha256(export.read_bytes()).hexdigest())
    r = replay.replay_entry(entry, tmp_path)
    assert r["stop_reason"] == "excluded_misattributed" and r["terminal_usage_complete"]
    entry["events_sha256"] = "0" * 64
    with pytest.raises(TransportAbort, match="sha256"):
        replay.replay_entry(entry, tmp_path)
