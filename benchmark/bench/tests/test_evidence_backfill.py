"""P438: stage cited, local-only `$STACK_WORKDIR` directories for the `evidence` branch — scrubbed like the P437 harvest, large
files xz-compressed, `.npz` arrays NOT copied (sha256 + size in `EXTERNAL_MANIFEST.json`, P441), venvs / caches skipped."""

import hashlib
import json
import lzma

import pytest

from bench import evidence_backfill as B
from bench import p426_harvest as H

USER, HOST = "someuser", "somebox"


@pytest.fixture
def box(tmp_path):
    home = tmp_path / "home" / USER
    wd, repo, stage = home / "wd", home / "repo", tmp_path / "stage"
    (wd / "p400" / "perf" / "run1").mkdir(parents=True)
    repo.mkdir(parents=True)
    scrub = H.Scrub(workdir=wd, repo=repo, home=home, user=USER, hosts=(HOST,))
    return dict(home=home, wd=wd, stage=stage, scrub=scrub)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def test_stage_mirrors_the_workdir_scrubs_and_manifests(box):
    run = box["wd"] / "p400" / "perf" / "run1"
    (run / "report.json").write_text(json.dumps({"out": str(run), "host": HOST}))
    (run / "leg.log").write_text(f"{USER} ran it\n")
    m = B.stage(box["wd"], ["p400/perf"], box["stage"], box["scrub"])
    assert json.loads((box["stage"] / "p400/perf/run1/report.json").read_text()) == {
        "out": "$STACK_WORKDIR/p400/perf/run1", "host": "localhost"}
    assert (box["stage"] / "p400/perf/run1/leg.log").read_text() == "<user> ran it\n"
    assert set(m["files"]) == {"p400/perf/run1/report.json", "p400/perf/run1/leg.log"}
    for rel, rec in m["files"].items():
        assert _sha((box["stage"] / rel).read_bytes()) == rec["published_sha256"]


def test_npz_is_listed_not_copied_and_caches_are_skipped(box):
    run = box["wd"] / "p400" / "perf" / "run1"
    (run / "rows-0.npz").write_bytes(b"\x93NUMPY" + bytes(100))
    for skip in (".venv/lib/x.py", "node_modules/a/b.js", "__pycache__/m.pyc", "tmp/scratch.txt"):
        (run / skip).parent.mkdir(parents=True, exist_ok=True)
        (run / skip).write_text("x")
    m = B.stage(box["wd"], ["p400/perf"], box["stage"], box["scrub"])
    assert m["files"] == {}
    assert m["external"] == {"p400/perf/run1/rows-0.npz": {"sha256": _sha(b"\x93NUMPY" + bytes(100)), "bytes": 106}}
    assert not (box["stage"] / "p400/perf/run1/rows-0.npz").exists()
    assert sorted(m["skipped"]) == ["p400/perf/run1/.venv", "p400/perf/run1/__pycache__", "p400/perf/run1/node_modules",
                                    "p400/perf/run1/tmp"]


def test_a_large_log_is_published_xz(box, monkeypatch):
    monkeypatch.setattr(H, "COMPRESS_BYTES", 64)
    log = "chunk 512 ok\n" * 100
    (box["wd"] / "p400" / "perf" / "run1" / "worker.log").write_text(log)
    m = B.stage(box["wd"], ["p400/perf"], box["stage"], box["scrub"])
    assert lzma.decompress((box["stage"] / "p400/perf/run1/worker.log.xz").read_bytes()).decode() == log
    assert m["files"]["p400/perf/run1/worker.log.xz"]["compression"] == "xz"


def test_residual_pii_refuses_and_stages_nothing(box):
    leak = "/".join(("", "Users", "otherperson", "x"))  # built at runtime: the literal fails the repo PII scan
    (box["wd"] / "p400" / "perf" / "run1" / "a.log").write_text(leak + "\n")
    with pytest.raises(H.HarvestError, match="PII"):
        B.stage(box["wd"], ["p400/perf"], box["stage"], box["scrub"])
    assert not box["stage"].exists()


def test_an_existing_stage_refuses(box):
    box["stage"].mkdir()
    with pytest.raises(H.HarvestError, match="exists"):
        B.stage(box["wd"], ["p400/perf"], box["stage"], box["scrub"])


def test_a_missing_or_escaping_directory_refuses(box):
    with pytest.raises(H.HarvestError, match="not a directory"):
        B.stage(box["wd"], ["p999/none"], box["stage"], box["scrub"])
    with pytest.raises(H.HarvestError, match="outside"):
        B.stage(box["wd"], ["../escape"], box["stage"], box["scrub"])
