"""P426 P437: every Wave-1 leg's evidence is copied from the frozen worktree / workdir into the MAIN checkout (rows at their
`benchmark/results/<entry>/` path, everything else in `benchmark/results/p426/wave1/<leg>/`), scrubbed, sha-manifested, fail
closed — so removing the frozen worktree or the workdir can never lose a leg."""

import hashlib
import json

import pytest

from bench import p426_harvest as H

ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
USER, HOST = "someuser", "somebox"


def _sha(b):
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def box(tmp_path):
    home = tmp_path / "home" / USER
    workdir, main = home / "wd", home / "repo"
    frozen = workdir / "worktrees" / "stack-p426"
    receipts = workdir / "p426" / "wave1" / "receipts"
    for d in (frozen / "benchmark" / "results" / ENTRY, frozen / "logs", main / "benchmark" / "results", receipts):
        d.mkdir(parents=True)
    scrub = H.Scrub(workdir=workdir, repo=main, home=home, user=USER, hosts=(HOST, f"{HOST}.local"))
    return dict(home=home, workdir=workdir, main=main, frozen=frozen, receipts=receipts, scrub=scrub)


def _rows_plan(box, name="math500-p426-off-smoke", stem="math500.p426-off-smoke"):
    return dict(kind="rows", entry=ENTRY, stem=stem, results_dir=box["frozen"] / "benchmark" / "results" / ENTRY)


def _seed_rows_leg(box, name="math500-p426-off-smoke", stem="math500.p426-off-smoke"):
    res = box["frozen"] / "benchmark" / "results" / ENTRY
    (res / f"{stem}.jsonl").write_text('{"id": "a", "acc": 1}\n')
    (res / f"{stem}.manifest.json").write_text(json.dumps({"cwd": str(box["frozen"]), "host": HOST}))
    (res / "math500.other-tune.jsonl").write_text("not this leg\n")
    (box["receipts"] / f"{name}.receipt.json").write_text(json.dumps({"verdict": "VALID", "argv": str(box["home"] / "x")}))
    (box["receipts"] / f"{name}.refused-1.receipt.json").write_text('{"verdict": "NOT_STARTED"}')
    (box["receipts"] / f"{name}.watch.log").write_text(f"tick on {HOST}.local by {USER}\n")
    (box["receipts"] / f"{name}.power.json").write_text("{}")
    (box["receipts"] / f"{name}.log").write_text("wrapper log\n")
    (box["receipts"] / "other-leg.receipt.json").write_text("{}")


def _harvest(box, name="math500-p426-off-smoke", plan=None, stdout=b"leg out\n", log_slice=b"Request completed: x\n"):
    return H.harvest(name, plan or _rows_plan(box, name), main_root=box["main"], receipts=box["receipts"],
                     stdout=stdout, log_slice=log_slice, scrub=box["scrub"])


def test_rows_land_at_their_main_path_and_the_dossier_holds_the_rest(box):
    _seed_rows_leg(box)
    manifest = _harvest(box)
    res = box["main"] / "benchmark" / "results" / ENTRY
    assert sorted(p.name for p in res.iterdir()) == ["math500.p426-off-smoke.jsonl", "math500.p426-off-smoke.manifest.json"]
    d = box["main"] / "benchmark" / "results" / "p426" / "wave1" / "math500-p426-off-smoke"
    assert sorted(p.name for p in d.iterdir()) == sorted([
        "math500-p426-off-smoke.receipt.json", "math500-p426-off-smoke.refused-1.receipt.json",
        "math500-p426-off-smoke.watch.log", "math500-p426-off-smoke.power.json", "math500-p426-off-smoke.log",
        "leg.stdout", "server_log_slice.log", "SCRUB_MANIFEST.json"])
    assert (d / "server_log_slice.log").read_bytes() == b"Request completed: x\n"
    on_disk = json.loads((d / "SCRUB_MANIFEST.json").read_text())
    assert on_disk == manifest and len(manifest["files"]) == 9
    for rel, rec in manifest["files"].items():
        assert _sha((box["main"] / rel).read_bytes()) == rec["published_sha256"]


def test_scrub_replaces_paths_user_and_host_and_records_both_shas(box):
    _seed_rows_leg(box)
    manifest = _harvest(box)
    res = box["main"] / "benchmark" / "results" / ENTRY
    text = (res / "math500.p426-off-smoke.manifest.json").read_text()
    assert json.loads(text) == {"cwd": "$STACK_WORKDIR/worktrees/stack-p426", "host": "localhost"}
    d = box["main"] / "benchmark" / "results" / "p426" / "wave1" / "math500-p426-off-smoke"
    assert (d / "math500-p426-off-smoke.watch.log").read_text() == "tick on localhost by <user>\n"
    assert json.loads((d / "math500-p426-off-smoke.receipt.json").read_text())["argv"] == "$HOME/x"
    rows = manifest["files"][f"benchmark/results/{ENTRY}/math500.p426-off-smoke.jsonl"]
    assert rows["original_sha256"] == rows["published_sha256"]  # nothing to scrub: byte-identical
    man = manifest["files"][f"benchmark/results/{ENTRY}/math500.p426-off-smoke.manifest.json"]
    assert man["original_sha256"] != man["published_sha256"]


def test_an_existing_destination_refuses_and_writes_nothing(box):
    _seed_rows_leg(box)
    clash = box["main"] / "benchmark" / "results" / ENTRY / "math500.p426-off-smoke.jsonl"
    clash.parent.mkdir(parents=True)
    clash.write_text("earlier\n")
    with pytest.raises(H.HarvestError, match="exists"):
        _harvest(box)
    assert clash.read_text() == "earlier\n"
    assert not (box["main"] / "benchmark" / "results" / "p426").exists()


def test_residual_pii_after_the_scrub_refuses(box):
    _seed_rows_leg(box)
    leak = "/".join(("", "Users", "otherperson", "models"))  # built at runtime: the literal fails the repo PII scan
    (box["receipts"] / "math500-p426-off-smoke.log").write_text(f"copied from {leak}\n")
    with pytest.raises(H.HarvestError, match="PII"):
        _harvest(box)
    assert not (box["main"] / "benchmark" / "results" / "p426").exists()


def test_a_leg_without_a_receipt_still_harvests_what_exists(box):
    """A crash before the wrapper wrote anything is still evidence: stdout + the log slice."""
    d = _harvest(box, name="vision-p426-on-b1", plan=dict(kind="vision", entry=ENTRY, stem="vision_gate.p426-on-b1",
                                                         results_dir=box["frozen"] / "benchmark" / "results" / ENTRY))
    assert sorted(rel.rsplit("/", 1)[1] for rel in d["files"]) == ["leg.stdout", "server_log_slice.log"]


def test_the_m1_leg_copies_its_qualify_directory(box):
    out = box["workdir"] / "p426" / "m1" / "p426-on-b1"
    (out / "logs").mkdir(parents=True)
    (out / "report.json").write_text(json.dumps({"stack_root": str(box["frozen"])}))
    (out / "logs" / "worker.log").write_text("ok\n")
    (box["receipts"] / "m1-p426-on-b1.receipt.json").write_text('{"verdict": "VALID"}')
    manifest = _harvest(box, name="m1-p426-on-b1", plan=dict(kind="qualify", entry=ENTRY, out_dir=out), log_slice=b"")
    d = box["main"] / "benchmark" / "results" / "p426" / "wave1" / "m1-p426-on-b1"
    assert json.loads((d / "m1" / "report.json").read_text()) == {"stack_root": "$STACK_WORKDIR/worktrees/stack-p426"}
    assert (d / "m1" / "logs" / "worker.log").read_text() == "ok\n"
    assert "benchmark/results/p426/wave1/m1-p426-on-b1/m1/logs/worker.log" in manifest["files"]


def test_an_oversized_file_refuses(box, monkeypatch):
    _seed_rows_leg(box)
    monkeypatch.setattr(H, "MAX_FILE_BYTES", 10)
    with pytest.raises(H.HarvestError, match="bytes"):
        _harvest(box)


def test_a_binary_file_is_copied_raw_only_without_pii(box):
    _seed_rows_leg(box)
    (box["receipts"] / "math500-p426-off-smoke.power.json").write_bytes(b"\xff\xfe" + USER.encode())
    with pytest.raises(H.HarvestError, match="binary"):
        _harvest(box)


def test_run_files_are_copied_once_and_must_match_on_resume(box):
    frozen_json = box["workdir"] / "p426" / "frozen.json"
    frozen_json.write_text('{"stack_head": "abc"}')
    on = box["workdir"] / "p426" / "registry-on.yaml"
    on.write_text("models: []\n")
    H.harvest_run_files([frozen_json, on], main_root=box["main"], scrub=box["scrub"])
    H.harvest_run_files([frozen_json, on], main_root=box["main"], scrub=box["scrub"])  # identical: a no-op
    run = box["main"] / "benchmark" / "results" / "p426" / "wave1" / "run"
    assert (run / "frozen.json").read_text() == '{"stack_head": "abc"}'
    on.write_text("models: [changed]\n")
    with pytest.raises(H.HarvestError, match="differs"):
        H.harvest_run_files([frozen_json, on], main_root=box["main"], scrub=box["scrub"])
