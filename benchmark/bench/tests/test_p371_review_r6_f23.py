"""P371 review r5 F23: every immutable evidence file the chain or the core publishes is written to a same-directory temp, fsynced,
then published exclusively (hard link, no replace) and the directory fsynced, so the destination is absent or complete; a resume
removes leftover temps with a listing. AUDIT (exclusive-create / immutable publishers): `web_evidence.extract` (`.web.jsonl`),
`worker_receipts.write_receipts_file` (`.receipts.json`), `corpus_tg1.final_tree` (manifest + content-addressed objects), the A4
copies (`chain_core.bind_receipt`, F13, already temp + link), `chain_core.barrier_signal` (temp + link), `fsync_json` /
`atomic_json` / `pg.atomic_write` (temp + replace on fresh paths). Not publishers of chain evidence: `pg.reserve_evidence` (an empty
reservation the client then appends to), `tg2_grade._registry_write` and `run_capacity` journals (operator markers outside the
chain). Interruption is injected at the first fsync: the file is cut to half its length (a torn write) and the process dies."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bench import corpus as cp
from bench import corpus_tg1, web_evidence as we, worker_receipts as wr


class Died(BaseException):
    pass


def die_torn_at_first_fsync(monkeypatch, module):
    real = os.fsync
    state = {"n": 0}

    def fsync(fd):
        state["n"] += 1
        if state["n"] == 1:
            size = os.fstat(fd).st_size
            os.ftruncate(fd, size // 2)
            raise Died()
        return real(fd)
    monkeypatch.setattr(os, "fsync", fsync)
    return real


RULES = {"schema": 1, "client": "opencode", "messages": "messages", "message_role_field": "type", "message_role": "assistant",
         "parts": "content", "part_type_field": "type", "part_type": "tool", "name_field": "name", "id_field": "id",
         "tool_names": ["webfetch", "websearch", "shell"], "name_contains": ["search"], "input_path": ["state", "input"],
         "output_paths": [["state", "output"], ["state", "content"]], "status_path": ["state", "status"]}


def transcript(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"messages": [{"type": "assistant", "content": [
        {"type": "tool", "name": "webfetch", "id": "c1", "state": {"status": "completed", "input": {"url": "u"}, "output": "o" * 400}}]}]}))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_web_evidence_dest_is_absent_or_complete_after_a_torn_write_and_a_rerun_succeeds(tmp_path, monkeypatch):
    path, sha = transcript(tmp_path)
    want = we.extract(RULES, path, sha, tmp_path / "clean.web.jsonl")
    dest = tmp_path / "t.web.jsonl"
    real = die_torn_at_first_fsync(monkeypatch, we)
    with pytest.raises(Died):
        we.extract(RULES, path, sha, dest)
    assert not dest.exists() or dest.read_bytes() == (tmp_path / "clean.web.jsonl").read_bytes()
    monkeypatch.setattr(os, "fsync", real)
    assert we.extract(RULES, path, sha, dest)["sha256"] == want["sha256"]


def test_the_receipts_file_is_absent_or_complete_after_a_torn_write_and_a_rerun_succeeds(tmp_path, monkeypatch):
    ctx = wr.AttemptContext.make("python/x", 1)
    mark, fence = wr.StartMark(worker=dict(pid=1, create_time=1.0), seq=0), wr.Fence(worker=dict(pid=1, create_time=1.0), last_seq=0, receipts=())
    clean = tmp_path / "clean.json"
    want = wr.write_receipts_file(clean, ctx, mark, fence)
    dest = tmp_path / "x.receipts.json"
    real = die_torn_at_first_fsync(monkeypatch, wr)
    with pytest.raises(Died):
        wr.write_receipts_file(dest, ctx, mark, fence)
    assert not dest.exists() or dest.read_bytes() == clean.read_bytes()
    monkeypatch.setattr(os, "fsync", real)
    assert wr.write_receipts_file(dest, ctx, mark, fence) == want


def test_the_final_tree_manifest_and_objects_are_absent_or_complete_after_a_torn_write(tmp_path, monkeypatch):
    from bench import arm_runner
    work = tmp_path / "work"
    work.mkdir()
    (work / "sol.py").write_text("print('x')\n" * 40)
    prepared = cp.PreparedItem(item_id="python/x", lang="python", name="x", work=work, entry={}, editable=("sol.py",),
                               baseline={"sol.py": hashlib.sha256(b"x").hexdigest()}, protected={}, prepared={}, tests=("t",))
    corpus = corpus_tg1.Tg1Corpus(arm_runner.DEFAULT_UNIVERSE)
    clean = corpus.final_tree(prepared, tmp_path / "clean")
    real = die_torn_at_first_fsync(monkeypatch, corpus_tg1)
    with pytest.raises(Died):
        corpus.final_tree(prepared, tmp_path / "torn")
    manifest = tmp_path / "torn" / "manifest.json"
    assert not manifest.exists() or manifest.read_bytes() == clean.manifest_path.read_bytes()
    for obj in (tmp_path / "torn" / "objects").glob("*"):
        assert not obj.name.startswith(".") and hashlib.sha256(obj.read_bytes()).hexdigest() == obj.name


def test_the_chain_removes_leftover_evidence_temps_at_hydration_with_a_listing(tmp_path):
    from bench.tests.m64_support import FakeOps, M, SMOKE
    a = M.parse_args(SMOKE + ["--out-root", str(tmp_path / "o")])
    lines = []
    chain = M.build_chain(a, FakeOps(tmp_path), M.Timers(), lines.append, {"python": ["a"], "go": ["b"]}, tmp_path / "o", {})
    stray = tmp_path / ".t.web.jsonl.tmp.4242"
    stray.write_text("half")
    assert chain.sweep_temps(tmp_path) == [stray.name] and not stray.exists()
    assert any("removed leftover" in l and stray.name in l for l in lines)
