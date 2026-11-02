"""P586 fix round 1, X7 / X8 (red-first): Go telemetry counters in a run HOME harvest cleanly (one `HARVEST.json` entry per private
directory, the per-file list in the evidence stage); the harvest's destination namespace."""
from __future__ import annotations

import hashlib
import json

import pytest

from bench import p426_harvest as H
from bench.tests import test_b2_s9_harvest as T

GO_TELEMETRY = "home/Library/Application Support/go/telemetry/local"
GO_NAMES = [f"{n}@go1.27.3-go1.27.3-darwin-arm64-2026-11-01.v1.count" for n in ("compile", "asm", "go", "link", "vet")]


def _go_telemetry(w):
    for n in GO_NAMES:
        T.put(w.run / GO_TELEMETRY / n, f"counters of {n}\n")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


# -- X7
def test_x7_go_telemetry_counters_in_a_run_home_do_not_stop_the_harvest(tmp_path):
    w = T.World(tmp_path)
    _go_telemetry(w)
    doc = w.harvest()
    assert not [f for f in doc["files"] if "compile@" in f["source"]]
    assert w.harvest_json() == doc
    assert "compile@" not in (w.dest() / "HARVEST.json").read_text()


def test_x7_a_private_run_directory_is_one_harvest_entry_with_a_count_and_a_digest(tmp_path):
    w = T.World(tmp_path)
    _go_telemetry(w)
    doc = w.harvest()
    private = [f for f in doc["files"] if f["exclusion_reason"] == "private_state"]
    (home,) = private
    assert home["source"] == f"run:{T.RUN_ID}/home/" and home["destination"] == "excluded" and home["published"] is None
    files = sorted((p.relative_to(w.run / "home").as_posix(), _sha(p.read_bytes())) for p in (w.run / "home").rglob("*") if p.is_file())
    assert home["files"] == len(files) == 6
    assert home["sha256"] == _sha("".join(f"{r}\t{s}\n" for r, s in files).encode())


def test_x7_each_private_run_directory_gets_its_own_entry(tmp_path):
    w = T.World(tmp_path)
    T.put(w.run / "data" / "a.db", "a")
    T.put(w.run / "data" / "sub" / "b.db", "b")
    T.put(w.run / "tmp" / "c", "c")
    doc = w.harvest()
    got = {f["source"]: f["files"] for f in doc["files"] if f["exclusion_reason"] == "private_state"}
    assert got == {f"run:{T.RUN_ID}/home/": 1, f"run:{T.RUN_ID}/data/": 2, f"run:{T.RUN_ID}/tmp/": 1}


def test_x7_the_per_file_list_goes_to_the_evidence_stage(tmp_path):
    w = T.World(tmp_path)
    _go_telemetry(w)
    w.harvest()
    listing = json.loads((w.evdest() / "excluded_private_state.json").read_text())
    names = {e["relpath"] for e in listing}
    assert {f"{GO_TELEMETRY[len('home/'):]}/{n}" for n in GO_NAMES} <= names
    assert all(set(e) >= {"source", "relpath", "sha256"} and len(e["sha256"]) == 64 for e in listing)
    assert not (w.dest() / "excluded_private_state.json").exists()


def test_x7_other_exclusions_stay_per_file(tmp_path):
    w = T.World(tmp_path)
    T.put(w.root / "tmp" / "uv-0123abcd.lock", "")
    doc = w.harvest()
    (lock,) = [f for f in doc["files"] if f["source"] == "leg:tmp/uv-0123abcd.lock"]
    assert lock["destination"] == "excluded" and "files" not in lock


def test_x7_the_dry_run_is_clean_too_and_writes_nothing(tmp_path):
    w = T.World(tmp_path)
    _go_telemetry(w)
    doc = w.harvest(dry_run=True)
    assert not [f for f in doc["files"] if "compile@" in f["source"]]
    T.nothing_published(w)


def test_x7_a_foreign_address_in_a_main_bound_record_still_refuses(tmp_path):
    w = T.World(tmp_path)
    _go_telemetry(w)
    with (w.root / "watch.jsonl").open("a") as f:
        f.write(json.dumps(dict(note="mail someone@elsewhere.net")) + "\n")
    with pytest.raises(H.HarvestError):
        w.harvest()
    T.nothing_published(w)


# -- X8
NS = "wave2.v8-af0711cf"


def test_x8_the_namespace_replaces_wave2_in_every_destination_and_published_path(tmp_path):
    w = T.World(tmp_path)
    doc = w.harvest(namespace=NS)
    base = f"benchmark/results/p426/{NS}/{T.NAME}"
    assert (w.main / base / "HARVEST.json").is_file()
    assert (w.stage / base / "RUNLOG.md").is_file()
    assert not (w.main / "benchmark/results/p426/wave2").exists() and not (w.stage / "benchmark/results/p426/wave2").exists()
    pubs = [f["published"] for f in doc["files"] if f["published"]]
    assert pubs and all(p.startswith(base + "/") for p in pubs)


def test_x8_the_default_is_unchanged(tmp_path):
    w = T.World(tmp_path)
    doc = w.harvest()
    assert (w.dest() / "HARVEST.json").is_file()
    assert all(f["published"].startswith(f"{T.WAVE2}/{T.NAME}/") for f in doc["files"] if f["published"])


@pytest.mark.parametrize("ns", ["../x", "wave3", "wave2/", "wave2.", "wave2.-x", "wave2.A", "wave2./x", "wave2.a/b", "", "WAVE2", "wave2 "])
def test_x8_an_invalid_namespace_is_refused_and_nothing_is_published(tmp_path, ns):
    w = T.World(tmp_path)
    with pytest.raises(H.HarvestError, match="namespace"):
        w.harvest(namespace=ns)
    T.nothing_published(w)


def test_x8_the_cli_takes_a_namespace(tmp_path):
    w = T.World(tmp_path)
    env = dict(STACK_WORKDIR=str(w.wd))
    argv = ["wave2", "--leg-root", str(w.root), "--main-root", str(w.main), "--evidence-stage", str(w.stage)]
    assert H.main(argv + ["--namespace", "../x"], environ=env, home=tmp_path / "home") == 2
    T.nothing_published(w)
    assert H.main(argv + ["--namespace", NS], environ=env, home=tmp_path / "home") == 0
    assert (w.main / f"benchmark/results/p426/{NS}/{T.NAME}/HARVEST.json").is_file()


def test_x8_the_record_publishers_take_the_namespace(tmp_path):
    w = T.World(tmp_path)
    rec = T.pjson(tmp_path / "recs" / "dossier.json", T.seal(dict(a=1)))
    run = T.pjson(tmp_path / "recs" / "frozen.json", T.seal(dict(b=2)))
    out = H.publish_dossier(rec, main_root=w.main, evidence_stage=w.stage, scrub=T.scrub_for(tmp_path), namespace=NS)
    assert out["published"][0]["destination"] == f"benchmark/results/p426/{NS}/pairs/dossier.json"
    out = H.publish_run_files([run], main_root=w.main, scrub=T.scrub_for(tmp_path), namespace=NS)
    assert out["published"][0]["destination"] == f"benchmark/results/p426/{NS}/run/frozen.json"
    assert (w.main / f"benchmark/results/p426/{NS}/run/frozen.json").is_file()
    assert not (w.main / "benchmark/results/p426/wave2").exists()
    with pytest.raises(H.HarvestError, match="namespace"):
        H.publish_run_files([run], main_root=w.main, scrub=T.scrub_for(tmp_path), namespace="wave3")
