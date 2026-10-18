"""P371 phase 1: `bench.web_evidence` (plan 4 A12): chain-side extraction of raw web evidence from the hashed transcript."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import arm_opencode as ao
from bench import token_turn_gate as tg
from bench import web_evidence as we

REPO = Path(__file__).resolve().parents[3]

DOC = {"messages": [
    {"type": "user", "content": [{"type": "text", "text": "do it"}]},
    {"type": "assistant", "content": [
        {"type": "text", "text": "thinking"},
        {"type": "tool", "name": "websearch", "id": "c1",
         "state": {"status": "completed", "input": {"query": "rust borrow checker"},
                   "content": [{"type": "text", "text": "result one\nresult two"}]}},
        {"type": "tool", "name": "read", "id": "c2", "state": {"status": "completed", "input": {"path": "a.py"},
                                                                "content": "x"}}]},
    {"type": "assistant", "content": [
        {"type": "tool", "name": "webfetch", "id": "c3",
         "state": {"status": "completed", "input": {"url": "https://example.test/doc"}, "output": "<html>body</html>"}},
        {"type": "tool", "name": "shell", "id": "c4",
         "state": {"status": "error", "input": {"command": "curl -s https://example.test"},
                   "content": "curl: (6) Could not resolve host"}},
        {"type": "tool", "name": "mcp_searxng_search", "id": "c5", "state": {"status": "running", "input": {"q": "x"}}}]},
    {"type": "assistant", "content": []}]}


def write(tmp_path, doc=DOC, name="t.json"):
    path = tmp_path / name
    raw = json.dumps(doc).encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def lines(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines()]


def test_the_opencode_rules_are_data():
    rules = we.OPENCODE_RULES
    assert json.loads(json.dumps(rules)) == rules
    assert set(rules["tool_names"]) == {"webfetch", "websearch", "shell"} and rules["name_contains"] == ["search"]


def test_extract_writes_raw_calls_with_returned_content_and_returns_path_sha_count(tmp_path):
    path, sha = write(tmp_path)
    dest = tmp_path / "ev/x.web.jsonl"
    out = we.extract(we.OPENCODE_RULES, path, sha, dest)
    assert out["path"] == str(dest) and out["count"] == 4
    assert out["sha256"] == hashlib.sha256(dest.read_bytes()).hexdigest()
    got = lines(dest)
    assert [(g["request"], g["tool"], g["id"], g["status"]) for g in got] == [
        (1, "websearch", "c1", "completed"), (2, "webfetch", "c3", "completed"), (2, "shell", "c4", "error"),
        (2, "mcp_searxng_search", "c5", "running")]
    assert got[0]["input"] == {"query": "rust borrow checker"}
    assert got[0]["output"] == [{"type": "text", "text": "result one\nresult two"}]          # raw returned content
    assert got[1]["output"] == "<html>body</html>"                                         # `state.output` wins
    assert got[2]["output"] == "curl: (6) Could not resolve host"                           # `state.content` fallback
    assert got[3]["output"] is None                                                         # still running: no output


def test_the_transcript_sha_is_verified_before_anything_is_written(tmp_path):
    path, sha = write(tmp_path)
    dest = tmp_path / "ev/x.web.jsonl"
    with pytest.raises(we.TranscriptShaMismatch) as exc:
        we.extract(we.OPENCODE_RULES, path, "0" * 64, dest)
    assert isinstance(exc.value, tg.TransportAbort)
    assert not dest.exists() and not dest.parent.exists()


def test_no_transcript_or_an_unreadable_export_is_unavailable_never_no_contact(tmp_path):
    dest = tmp_path / "w.jsonl"
    assert we.extract(we.OPENCODE_RULES, None, None, dest) == we.unavailable("no transcript")
    assert we.extract(we.OPENCODE_RULES, tmp_path / "missing.json", "a" * 64, dest)["web_evidence"] == "unavailable"
    bad = tmp_path / "bad.json"
    bad.write_text("not json (export failed)")
    sha = hashlib.sha256(bad.read_bytes()).hexdigest()
    out = we.extract(we.OPENCODE_RULES, bad, sha, dest)
    assert out["web_evidence"] == "unavailable" and "unreadable" in out["reason"]
    assert not dest.exists()
    notdict = tmp_path / "list.json"
    notdict.write_text("[1]")
    assert we.extract(we.OPENCODE_RULES, notdict, hashlib.sha256(b"[1]").hexdigest(), dest)["web_evidence"] == "unavailable"


def test_unavailable_record_shape():
    assert we.unavailable("why") == dict(web_evidence="unavailable", reason="why")
    with pytest.raises(ValueError):
        we.unavailable("")


def test_a_partial_transcript_of_a_killed_or_cancelled_session_still_extracts(tmp_path):
    doc = copy.deepcopy(DOC)
    doc["messages"] = doc["messages"][:3]                      # cut mid-session: last tool never returned
    path, sha = write(tmp_path, doc, "partial.json")
    out = we.extract(we.OPENCODE_RULES, path, sha, tmp_path / "p.web.jsonl")
    assert out["count"] == 4 and lines(out["path"])[-1]["output"] is None


def test_an_empty_evidence_file_is_a_hashed_zero_count_not_unavailable(tmp_path):
    path, sha = write(tmp_path, {"messages": [{"type": "assistant", "content": [{"type": "text", "text": "hi"}]}]})
    out = we.extract(we.OPENCODE_RULES, path, sha, tmp_path / "z.web.jsonl")
    assert out["count"] == 0 and out["sha256"] == hashlib.sha256(b"").hexdigest()


def test_evidence_is_immutable(tmp_path):
    path, sha = write(tmp_path)
    dest = tmp_path / "w.jsonl"
    we.extract(we.OPENCODE_RULES, path, sha, dest)
    with pytest.raises(we.WebEvidenceError):
        we.extract(we.OPENCODE_RULES, path, sha, dest)


def test_rules_are_validated():
    for bad in ({}, dict(we.OPENCODE_RULES, schema=2), {k: v for k, v in we.OPENCODE_RULES.items() if k != "tool_names"}):
        with pytest.raises(ValueError):
            we.validate_rules(bad)
    assert we.validate_rules(we.OPENCODE_RULES) is we.OPENCODE_RULES


def test_a_second_client_shape_is_served_by_rules_alone(tmp_path):
    rules = dict(we.OPENCODE_RULES, client="other", messages="turns", message_role_field="role",
                 message_role="assistant", parts="parts", name_field="tool", tool_names=["fetch"], name_contains=[],
                 input_path=["args"], output_paths=[["result"]], status_path=["status"])
    doc = {"turns": [{"role": "assistant", "parts": [{"type": "tool", "tool": "fetch", "id": "z", "args": {"u": 1},
                                                      "result": "ok", "status": "completed"}]}]}
    path, sha = write(tmp_path, doc, "o.json")
    out = we.extract(rules, path, sha, tmp_path / "o.web.jsonl")
    assert lines(out["path"]) == [dict(request=1, tool="fetch", id="z", status="completed", input={"u": 1},
                                       output="ok")]


def test_web_evidence_is_in_no_probe_closure():
    code = ("from bench import identity_closure as ic; from pathlib import Path; R = Path('..').resolve(); "
            "print(sorted(p.name for e in ('benchmark/run_tg1_probe.py','benchmark/run_oc_probe.py') "
            "for p in ic.python_closure(R / e, R) if p.name == 'web_evidence.py'))")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO / "benchmark", capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"
