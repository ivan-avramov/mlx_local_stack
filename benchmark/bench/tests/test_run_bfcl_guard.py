"""A failed BFCL run must not null out a real score.

DOCUMENTED LOSS: campaign-queue.md records "each failed run_bfcl clobbers bfcl.json to null —
re-parse raw or ignore", which is why Qwen3.6-27B-Opus-Distill-OptiQ-4bit's bfcl.json reads acc=null
with an rc=1 traceback even though its real result (n=200, acc 0.94) had already been measured. Same
defect class as a failed evalplus grade overwriting a graded score.
"""
import json

import bench.run_bfcl as RB


def _run(monkeypatch, tmp_path, result):
    monkeypatch.setattr(RB, "RESULTS", str(tmp_path))
    monkeypatch.setattr(RB, "run_bfcl", lambda **kw: result)
    return RB.main(["--model", "M", "--limit", "5"])


def test_a_failed_run_does_not_null_a_real_score(tmp_path, monkeypatch):
    p = tmp_path / "M" / "bfcl.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"model": "M", "acc": 0.94, "n": 200}))
    _run(monkeypatch, tmp_path, {"model": "M", "acc": None, "n": 0,
                                 "note": "bfcl generate failed rc=1"})
    kept = json.loads(p.read_text())
    assert kept["acc"] == 0.94 and kept["n"] == 200, "a failed run clobbered a real score"


def test_a_real_run_still_replaces_an_older_one(tmp_path, monkeypatch):
    p = tmp_path / "M" / "bfcl.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"model": "M", "acc": 0.94, "n": 200}))
    _run(monkeypatch, tmp_path, {"model": "M", "acc": 0.96, "n": 1000})
    got = json.loads(p.read_text())
    assert got["acc"] == 0.96 and got["n"] == 1000


def test_a_failure_still_records_when_there_is_nothing_to_lose(tmp_path, monkeypatch):
    _run(monkeypatch, tmp_path, {"model": "M", "acc": None, "n": 0, "note": "bfcl CLI not found"})
    got = json.loads((tmp_path / "M" / "bfcl.json").read_text())
    assert got["note"] == "bfcl CLI not found"
