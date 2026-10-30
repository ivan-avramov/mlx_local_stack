"""B2 slice s9 (spec docs/specs/p426-b2-tg1-wave2.md v3.2, sections 11, 12, 16.1, 16.2, 16.4, 16.6-16.8): the Wave-2 harvest
`bench.p426_harvest wave2` (inventory, closed rule table, transitive references, symlink rule, staged publication with
`HARVEST.json` as the commit point, portable records, scrub + secret gate) and `publish_dossier` / `publish_run_files`.
Hermetic: every tree is under `tmp_path`, every secret is a fake injected through the `secrets` argument or `main(environ=, home=)`;
no real registry, token file or machine config is read, nothing is written outside `tmp_path`."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path

import pytest

from bench import p426_harvest as H
from bench import p426_secrets as S
from bench import schedules

LEG, N = "tg1-p426-off-s1", 1
NAME = f"{LEG}.a{N}"
MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
RUN_ID = "20261028T100000-abcdef012345"
STEM = f"{MODEL}.s1"
SLOT = f"e|off|{MODEL}|s1|python|beer-song"
SLOT_FILE = SLOT.replace("|", "__").replace("/", "--")
WAVE2 = "benchmark/results/p426/wave2"
FAKE_SECRET = "Zk3" + "x7Pq" * 9 + "W"                       # a 40-char opaque fake credential (no known format)
FAKE_HF = "hf_" + "Q" * 34


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canon_sha(doc) -> str:
    body = {k: v for k, v in doc.items() if k != "sha256"}
    return sha(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def seal(doc):
    return dict(doc, sha256=canon_sha(doc))


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def pjson(path, doc):
    return put(path, json.dumps(doc, indent=1, sort_keys=True))


def scrub_for(tmp_path, emails=()):
    return H.Scrub(workdir=tmp_path / "wd", repo=tmp_path / "main", home=tmp_path / "home", user="b2opuser", hosts=("b2host",),
                   emails=tuple(emails))


class World:
    """A leg root as the chain / probe / sequencer leave it, with its run and evidence directories (`$STACK_WORKDIR/...`)."""

    def __init__(self, tmp_path, *, state="VALID", dnf=False, invalid=False, log=False, items=1):
        self.tmp = tmp_path
        self.wd = tmp_path / "wd"
        self.main, self.stage = tmp_path / "main", tmp_path / "stage"
        self.root = self.wd / "p426" / "wave2" / NAME
        self.run = self.wd / "opencode-probe-v2" / f"run-{RUN_ID}"
        self.ev = self.wd / "opencode_transcripts" / MODEL / f"{STEM}.{RUN_ID}"
        self.state = state
        self.wt = tmp_path / "wt-off"
        self.build(dnf=dnf, invalid=invalid, log=log, items=items)

    # portable form of a workdir path
    def p(self, path):
        return "$STACK_WORKDIR/" + Path(path).relative_to(self.wd).as_posix()

    def build(self, *, dnf, invalid, log, items):
        r = self.root
        state = self.state
        pjson(r / "leg.json", seal(dict(leg=LEG, attempt=N, state=state, **{"class": state.lower()}, reason="", chain_rc=0,
                                        started="2026-10-28T10:00:00Z", ended="2026-10-28T11:00:00Z")))
        put(r / "RUNLOG.md", "chain: started\n")
        if state == "NOT_STARTED":
            return
        names = [f"beer-song{i}" if i else "beer-song" for i in range(items)]
        slots = [f"e|off|{MODEL}|s1|python|{n}" for n in names]
        ledger = []
        for i, s in enumerate(slots):
            ledger.append(dict(slot=s, kind="row", invocation="s1/rows.jsonl", index=i))
        dnfs = []
        if dnf:
            ds = f"e|off|{MODEL}|s1|python|zzz"
            ledger.append(dict(slot=ds, kind="dnf", invocation="s1/rows.jsonl", index=len(slots)))
            dsf = ds.replace("|", "__")
            dnf_rec = seal(dict(slot=ds, item_record=f"items/{dsf}.dnf.json"))       # an immutable record: chain.json and the sidecar agree
            dnfs.append(dnf_rec)
            dready = seal(dict(slot=ds, item="python/zzz", k=len(slots), log_cursor=dict(path="<WT>/logs/m", device=1, inode=2, offset=0),
                               worker_snapshot={}, at="t"))
            pjson(r / "items" / f"{dsf}.ready.json", dready)                          # a DNF has its ready record too (fix round 5)
            pjson(r / "items" / f"{dsf}.dnf.json", seal(dict(slot=ds, ready_sha256=dready["sha256"], case="dnf_boundary", requests=[],
                                                              verdict="reconciled")))
            pjson(r / "s1" / "p426_dnf" / f"{dsf}.json", dnf_rec)
        sched = dict(builder="tg1", blocks=[dict(session="s1", legs=[dict(lang="python", full_names=names, invocations=[
            dict(phase="full", names=names, limit=None, expect=[f"python/{n}" for n in names])])])])
        pjson(r / "schedule.json", sched)
        invalid_recs = [dict(slot=slots[0], reason="reconciliation mismatch (injected)")] if invalid else []
        pjson(r / "chain.json", dict(status="finished", rc=0, schedule_sha256=schedules.schedule_sha256(sched), p426_ledger=ledger,
                                     p426_dnf=dnfs, p426_invalid=invalid_recs, argv=["chain", "s1", "--frozen-record",
                                     "$STACK_WORKDIR/p426/records/amendment.json"],
                                     progress=dict(invocations=[dict(file="s1/rows.jsonl", manifest="s1/rows.manifest.json",
                                                                     status="validated", leg_key=[0, "python", 0])])))
        pjson(r / "receipt.json", seal(dict(argv=dict(router=[], worker=[]), env={}, credential_keys={})))
        put(r / "watch.jsonl", json.dumps(dict(t=1)) + "\n" + json.dumps(dict(exit_state="driver_exited")) + "\n")
        rows = []
        for i, (s, n) in enumerate(zip(slots, names)):
            sf = s.replace("|", "__")
            ready = seal(dict(slot=s, item=f"python/{n}", k=i, log_cursor=dict(path="<WT>/logs/m", device=1, inode=2, offset=0),
                              worker_snapshot={}, at="t"))
            pjson(r / "items" / f"{sf}.ready.json", ready)
            pjson(r / "items" / f"{sf}.json", seal(dict(slot=s, ready_sha256=ready["sha256"], log_range=dict(start=0, end=1, sha256="0" * 64),
                                                        requests=[], verdict="reconciled", case="completed")))
            rows.append(self.row(n))
            base = r / "s1" / "rows"
            if not invalid or i:
                put(f"{base}.item{i}.ready", "{}")
                put(f"{base}.item{i}.go", "{}")
                put(f"{base}.item{i}.done", "{}")
                put(f"{base}.item{i}.continue", "{}")
            else:
                put(f"{base}.item{i}.ready", "{}")
                put(f"{base}.item{i}.stop", json.dumps(dict(disposition="invalidate")))
        put(r / "s1" / "rows.jsonl", "".join(json.dumps(x) + "\n" for x in rows))
        pjson(r / "s1" / "rows.manifest.json", dict(run_id=RUN_ID, model=MODEL, worker={}))
        pjson(r / "log_bounds.json", dict(files=[], created="t", finalized="t"))
        if log:
            self.add_log()

    def row(self, n):
        ev = self.ev
        files = {}
        for key, suffix in (("events", ".events.jsonl"), ("stderr", ".stderr.txt"), ("export", ".json"), ("datefreeze", ".datefreeze.jsonl")):
            files[key] = put(ev / f"python__{n}{suffix}", f"{key} of {n}\n")
        put(ev / f"python__{n}.web.jsonl", "{}\n")
        tree = ev / f"python__{n}.final_tree"
        code = b"answer = 42\n"
        put(tree / "objects" / sha(code), code)
        manifest = pjson(tree / "manifest.json", dict(files={"solution.py": sha(code)}, missing=[]))
        report = pjson(self.run / "grading-private" / "keep" / "seq-1" / "report.json", dict(outcome="pass"))
        pjson(self.run / "grading-private" / "keep" / "seq-1" / "index.json", dict(boundary=1, seq=1, final=True, outcome="pass",
                                                                                   artifacts=dict(report=dict(path="report.json", sha256=sha(report.read_bytes())))))
        put(self.run / "grading-private" / "keep" / "seq-1" / "change.diff", "--- a\n+++ b\n")
        put(self.run / "cfg" / "opencode" / "plugins" / "noretry.js", "// plugin\n")
        pjson(self.run / "cfg" / "opencode" / "opencode.json", {"provider": {}})
        put(self.run / "home" / ".config" / "state.db", b"\x00sqlite private state")
        return dict(id=f"python/{n}", slot_base="x", passed=True, events_path=self.p(files["events"]), stderr_path=self.p(files["stderr"]),
                    transcript_path=self.p(files["export"]), datefreeze_path=self.p(files["datefreeze"]),
                    evidence_sha256={k: sha(v.read_bytes()) for k, v in files.items()},
                    final_tree=dict(manifest=self.p(manifest), manifest_sha256=sha(manifest.read_bytes()), files={"solution.py": sha(code)}, missing=[]),
                    grade_reports=[dict(boundary=1, seq=1, final=True, outcome="pass",
                                        artifacts=dict(report=dict(path=self.p(report), sha256=sha(report.read_bytes()))))])

    def add_log(self, body=b"line one\nline two\n"):
        logs = self.wt / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        lg = put(logs / "mlx_vlm.log", b"before\n" + body + b"after\n")
        st = lg.stat()
        put(logs / "main_model.log", b"")
        st2 = (logs / "main_model.log").stat()
        pjson(self.root / "log_bounds.json", dict(files=[
            dict(path="<WT>/logs/mlx_vlm.log", device=st.st_dev, inode=st.st_ino, offset_start=len(b"before\n"),
                 offset_end=len(b"before\n") + len(body)),
            dict(path="<WT>/logs/main_model.log", device=st2.st_dev, inode=st2.st_ino, offset_start=0, offset_end=0)],
            created="t", finalized="t"))
        return lg

    def harvest(self, *, secrets=None, emails=(), worktree=None, **kw):
        return H.harvest_wave2(self.root, main_root=self.main, evidence_stage=self.stage, scrub=scrub_for(self.tmp, emails),
                               secrets=secrets if secrets is not None else {}, worktree=worktree, workdir=self.wd, **kw)

    def dest(self, attempt=NAME):
        return self.main / WAVE2 / attempt

    def evdest(self, attempt=NAME):
        return self.stage / WAVE2 / attempt

    def harvest_json(self):
        p = self.dest() / "HARVEST.json"
        return json.loads(p.read_text()) if p.exists() else None


def entries(doc, prefix=None):
    return [f for f in doc["files"] if prefix is None or f["source"].startswith(prefix)]


def entry(doc, source):
    (e,) = [f for f in doc["files"] if f["source"] == source]
    return e


def nothing_published(w):
    assert not (w.main / WAVE2).exists() or not any((w.main / WAVE2).iterdir()), list((w.main / WAVE2).iterdir())
    assert not w.stage.exists() or not any(w.stage.rglob("*")), list(w.stage.rglob("*"))


# ------------------------------------------------------------------------------------------------ every leg state
@pytest.mark.parametrize("state,kw", [("VALID", {}), ("VALID_WITH_DNF", dict(dnf=True)), ("INVALID", dict(invalid=True)),
                                      ("NOT_STARTED", {}), ("OVERRUN", {})])
def test_every_leg_state_is_harvested_and_labelled(tmp_path, state, kw):
    w = World(tmp_path, state=state, **kw)
    doc = w.harvest()
    assert doc["state"] == state and doc["leg"] == LEG and doc["attempt"] == N
    assert canon_sha(doc) == doc["sha256"]
    assert w.harvest_json() == doc
    assert entry(doc, "leg:leg.json")["destination"] == "main" and entry(doc, "leg:RUNLOG.md")["destination"] == "evidence"
    assert {f["destination"] for f in doc["files"]} <= {"main", "evidence", "excluded"}


def test_a_leg_state_outside_the_five_refuses(tmp_path):
    w = World(tmp_path)
    leg = json.loads((w.root / "leg.json").read_text())
    (w.root / "leg.json").write_text(json.dumps(dict(leg, state="WEIRD")))
    with pytest.raises(H.HarvestError, match="leg.json"):
        w.harvest()
    nothing_published(w)


def test_the_leg_root_name_must_match_its_leg_record(tmp_path):
    w = World(tmp_path)
    other = w.root.with_name(f"{LEG}.a2")
    w.root.rename(other)
    w.root = other
    with pytest.raises(H.HarvestError, match="leg.json"):
        w.harvest()


def test_the_leg_root_is_never_modified_by_its_harvest(tmp_path):
    w = World(tmp_path, log=True)
    keep = [w.root, w.run, w.ev, w.wt]                           # everything the harvest reads; its only write under the workdir is the review file
    snap = {p: p.read_bytes() for d in keep for p in d.rglob("*") if p.is_file()}
    w.harvest(worktree=w.wt)
    assert {p: p.read_bytes() for d in keep for p in d.rglob("*") if p.is_file()} == snap


# ------------------------------------------------------------------------------------------------ inventory, rule table, references
def test_an_unmatched_file_fails_the_harvest_and_names_it(tmp_path):
    w = World(tmp_path)
    put(w.root / "stray.unknown-kind", "x")
    with pytest.raises(H.HarvestError, match="stray.unknown-kind"):
        w.harvest()
    nothing_published(w)


def test_an_unmatched_file_in_a_named_run_directory_fails_too(tmp_path):
    w = World(tmp_path)
    put(w.run / "grading-private" / "keep" / "seq-1" / "mystery.bin", "x")
    with pytest.raises(H.HarvestError, match="mystery.bin"):
        w.harvest()


def test_the_inventory_maps_every_file_of_the_leg_run_and_evidence_directories(tmp_path):
    w = World(tmp_path)
    doc = w.harvest()
    seen = {f["source"] for f in doc["files"]}
    on_disk = ({"leg:" + p.relative_to(w.root).as_posix() for p in w.root.rglob("*") if p.is_file()}
               | {f"run:{RUN_ID}/" + p.relative_to(w.run).as_posix() for p in w.run.rglob("*") if p.is_file()}
               | {f"evidence:{RUN_ID}/" + p.relative_to(w.ev).as_posix() for p in w.ev.rglob("*") if p.is_file()})
    assert seen == on_disk
    for f in doc["files"]:
        assert set(f) >= {"source", "sha256", "destination", "published", "published_sha256", "compression", "exclusion_reason"}
        src = {"leg": w.root, "run": w.run, "evidence": w.ev}[f["source"].split(":")[0]]
        rel = f["source"].split(":", 1)[1]
        rel = rel.split("/", 1)[1] if not f["source"].startswith("leg:") else rel
        assert f["sha256"] == sha((src / rel).read_bytes())


def test_destinations_follow_the_rule_table_main_structured_evidence_raw(tmp_path):
    w = World(tmp_path)
    doc = w.harvest()
    main = ["leg:leg.json", "leg:chain.json", "leg:schedule.json", "leg:receipt.json", "leg:watch.jsonl", "leg:log_bounds.json",
            "leg:s1/rows.jsonl", "leg:s1/rows.manifest.json", f"leg:items/{SLOT_FILE}.ready.json", f"leg:items/{SLOT_FILE}.json",
            f"run:{RUN_ID}/grading-private/keep/seq-1/report.json", f"run:{RUN_ID}/grading-private/keep/seq-1/index.json",
            f"run:{RUN_ID}/grading-private/keep/seq-1/change.diff",
            f"evidence:{RUN_ID}/python__beer-song.final_tree/manifest.json"]
    raw = ["leg:RUNLOG.md", "leg:s1/rows.item0.ready", "leg:s1/rows.item0.go", "leg:s1/rows.item0.done", "leg:s1/rows.item0.continue",
           f"evidence:{RUN_ID}/python__beer-song.events.jsonl", f"evidence:{RUN_ID}/python__beer-song.stderr.txt",
           f"evidence:{RUN_ID}/python__beer-song.json", f"evidence:{RUN_ID}/python__beer-song.web.jsonl",
           f"evidence:{RUN_ID}/python__beer-song.datefreeze.jsonl"]
    for s in main:
        assert entry(doc, s)["destination"] == "main", s
    for s in raw:
        assert entry(doc, s)["destination"] == "evidence", s
    objects = [f for f in entries(doc, f"evidence:{RUN_ID}/python__beer-song.final_tree/objects/")]
    assert objects and all(f["destination"] == "evidence" for f in objects)
    private = entry(doc, f"run:{RUN_ID}/home/.config/state.db")
    assert private["destination"] == "excluded" and private["exclusion_reason"] and private["published"] is None
    assert entry(doc, f"run:{RUN_ID}/cfg/opencode/plugins/noretry.js")["destination"] in ("evidence", "excluded")


def test_main_files_are_published_byte_identical_and_evidence_files_scrubbed_into_the_stage(tmp_path):
    w = World(tmp_path)
    put(w.root / "RUNLOG.md", f"wrote {w.wd}/p426/x as b2opuser on b2host\n")
    doc = w.harvest()
    e = entry(doc, "leg:chain.json")
    assert (w.main / e["published"]).read_bytes() == (w.root / "chain.json").read_bytes() and e["published_sha256"] == e["sha256"]
    r = entry(doc, "leg:RUNLOG.md")
    got = (w.stage / r["published"]).read_text()
    assert got == "wrote $STACK_WORKDIR/p426/x as <user> on localhost\n"
    assert r["published_sha256"] == sha(got.encode()) and r["sha256"] == sha((w.root / "RUNLOG.md").read_bytes())


@pytest.mark.parametrize("what", ["events", "stderr", "export", "datefreeze"])
def test_a_missing_row_evidence_file_fails_the_harvest(tmp_path, what):
    w = World(tmp_path)
    suffix = {"events": ".events.jsonl", "stderr": ".stderr.txt", "export": ".json", "datefreeze": ".datefreeze.jsonl"}[what]
    (w.ev / f"python__beer-song{suffix}").unlink()
    with pytest.raises(H.HarvestError, match="beer-song"):
        w.harvest()
    nothing_published(w)


@pytest.mark.parametrize("target", ["final_manifest", "final_object", "grade_report", "item_record", "ready_record", "rows", "row_manifest",
                                    "schedule", "dnf_sidecar"])
def test_a_missing_referenced_file_fails_the_harvest(tmp_path, target):
    w = World(tmp_path, dnf=True)
    victim = {"final_manifest": w.ev / "python__beer-song.final_tree" / "manifest.json",
              "final_object": next((w.ev / "python__beer-song.final_tree" / "objects").iterdir()),
              "grade_report": w.run / "grading-private" / "keep" / "seq-1" / "report.json",
              "item_record": w.root / "items" / f"{SLOT_FILE}.json", "ready_record": w.root / "items" / f"{SLOT_FILE}.ready.json",
              "rows": w.root / "s1" / "rows.jsonl", "row_manifest": w.root / "s1" / "rows.manifest.json",
              "schedule": w.root / "schedule.json",
              "dnf_sidecar": w.root / "s1" / "p426_dnf" / f"e__off__{MODEL}__s1__python__zzz.json"}[target]
    victim.unlink()
    with pytest.raises(H.HarvestError):
        w.harvest()
    nothing_published(w)


def test_a_row_whose_evidence_changed_after_the_row_was_written_fails(tmp_path):
    w = World(tmp_path)
    (w.ev / "python__beer-song.events.jsonl").write_text("tampered\n")
    with pytest.raises(H.HarvestError, match="events"):
        w.harvest()


def test_an_item_record_must_name_the_ready_records_hash(tmp_path):
    w = World(tmp_path)
    p = w.root / "items" / f"{SLOT_FILE}.json"
    doc = json.loads(p.read_text())
    doc["ready_sha256"] = "f" * 64
    p.write_text(json.dumps(seal(doc)))
    with pytest.raises(H.HarvestError, match="ready"):
        w.harvest()


def test_a_self_hashed_record_with_a_wrong_hash_fails(tmp_path):
    w = World(tmp_path)
    p = w.root / "receipt.json"
    doc = json.loads(p.read_text())
    p.write_text(json.dumps(dict(doc, env={"x": "y"})))
    with pytest.raises(H.HarvestError, match="receipt.json"):
        w.harvest()


def test_the_frozen_schedule_must_match_the_chains_hash(tmp_path):
    w = World(tmp_path)
    s = json.loads((w.root / "schedule.json").read_text())
    s["blocks"][0]["session"] = "s2"
    (w.root / "schedule.json").write_text(json.dumps(s))
    with pytest.raises(H.HarvestError, match="schedule"):
        w.harvest()


def test_a_reference_outside_the_inventoried_roots_fails(tmp_path):
    w = World(tmp_path)
    outside = put(w.wd / "elsewhere" / "x.json", "{}")
    rows = w.root / "s1" / "rows.jsonl"
    row = json.loads(rows.read_text())
    row["transcript_path"] = w.p(outside)
    row["evidence_sha256"]["export"] = sha(outside.read_bytes())
    rows.write_text(json.dumps(row) + "\n")
    with pytest.raises(H.HarvestError, match="elsewhere|outside"):
        w.harvest()


def test_a_run_directory_without_this_attempts_run_id_is_not_taken(tmp_path):
    w = World(tmp_path)
    foreign = put(w.wd / "opencode-probe-v2" / "run-20260101T000000-ffffffffffff" / "cfg" / "x.json", "{}")
    doc = w.harvest()
    assert not any("ffffffffffff" in f["source"] for f in doc["files"]) and foreign.exists()


# ------------------------------------------------------------------------------------------------ barrier and control files
def test_a_stop_is_required_for_every_invalidate_and_only_for_those(tmp_path):
    w = World(tmp_path, state="INVALID", invalid=True)
    assert w.harvest()["state"] == "INVALID"
    w2 = World(tmp_path / "b", state="INVALID", invalid=True)
    (w2.root / "s1" / "rows.item0.stop").unlink()
    with pytest.raises(H.HarvestError, match=r"\.stop"):
        w2.harvest()
    w3 = World(tmp_path / "c")
    put(w3.root / "s1" / "rows.item0.stop", "{}")
    with pytest.raises(H.HarvestError, match=r"\.stop"):
        w3.harvest()


def test_every_go_has_its_ready_and_a_valid_leg_answers_every_ready_and_done(tmp_path):
    w = World(tmp_path)
    (w.root / "s1" / "rows.item0.ready").unlink()
    with pytest.raises(H.HarvestError, match=r"\.go"):
        w.harvest()
    w2 = World(tmp_path / "b")
    (w2.root / "s1" / "rows.item0.continue").unlink()
    with pytest.raises(H.HarvestError, match=r"\.continue|\.done"):
        w2.harvest()
    w3 = World(tmp_path / "c")
    (w3.root / "s1" / "rows.item0.go").unlink()
    with pytest.raises(H.HarvestError, match=r"\.ready|\.go"):
        w3.harvest()


def test_a_not_started_leg_has_no_barrier_or_row_files(tmp_path):
    w = World(tmp_path, state="NOT_STARTED")
    put(w.root / "s1" / "rows.item0.go", "{}")
    with pytest.raises(H.HarvestError, match="NOT_STARTED"):
        w.harvest()


def test_ack_cancel_and_stop_control_files_are_harvested_to_evidence(tmp_path):
    w = World(tmp_path)
    put(w.root / "STOP", "")
    put(w.root / "s1" / "rows.manifest.ack", "")
    put(w.root / "s1" / "rows.cancel", "")
    doc = w.harvest()
    for s in ("leg:STOP", "leg:s1/rows.manifest.ack", "leg:s1/rows.cancel"):
        assert entry(doc, s)["destination"] == "evidence"


# ------------------------------------------------------------------------------------------------ symlinks
def test_a_symlink_in_a_final_tree_is_recorded_and_excluded_never_followed(tmp_path):
    w = World(tmp_path)
    outside = put(tmp_path / "outside.txt", "SENTINEL-NEVER-READ")
    tree = w.ev / "python__beer-song.final_tree"
    (tree / "link_to_outside").symlink_to(outside)
    doc = w.harvest()
    e = entry(doc, f"evidence:{RUN_ID}/python__beer-song.final_tree/link_to_outside")
    assert e["destination"] == "excluded" and e["exclusion_reason"] == "symlink" and e["published"] is None
    assert e["link_target"] == str(outside) or "outside.txt" in e["link_target"]
    assert "SENTINEL-NEVER-READ" not in json.dumps(doc)
    assert not any("SENTINEL" in p.read_text(errors="ignore") for p in list(w.stage.rglob("*")) + list(w.main.rglob("*")) if p.is_file())


def test_a_final_tree_under_the_leg_root_follows_the_same_rule(tmp_path):
    w = World(tmp_path)
    outside = put(tmp_path / "outside.txt", "SENTINEL-NEVER-READ")
    tree = w.root / "transcripts" / "python__x.final_tree"
    pjson(tree / "manifest.json", dict(files={}, missing=[]))
    put(tree / "objects" / ("a" * 64), "code\n")
    (tree / "link_to_outside").symlink_to(outside)
    put(tree / "solution.py", "loose file\n")                        # a regular file the rule table does not know: the refusal names it
    with pytest.raises(H.HarvestError) as exc:
        w.harvest()
    assert "solution.py" in str(exc.value) and "link_to_outside" not in str(exc.value)
    (tree / "solution.py").unlink()
    doc = w.harvest()
    assert entry(doc, "leg:transcripts/python__x.final_tree/link_to_outside")["exclusion_reason"] == "symlink"
    assert entry(doc, "leg:transcripts/python__x.final_tree/manifest.json")["destination"] == "main"


@pytest.mark.parametrize("where", ["leg", "run", "evidence"])
def test_a_symlink_anywhere_else_fails_the_harvest_without_being_read(tmp_path, where, capsys):
    w = World(tmp_path)
    outside = put(tmp_path / "outside.txt", "SENTINEL-NEVER-READ")
    base = {"leg": w.root, "run": w.run / "cfg", "evidence": w.ev}[where]
    (base / "linked.log").symlink_to(outside)
    with pytest.raises(H.HarvestError, match="linked.log") as exc:
        w.harvest()
    assert "SENTINEL" not in str(exc.value) and "SENTINEL" not in capsys.readouterr().out
    nothing_published(w)


def test_a_directory_symlink_is_not_followed_either(tmp_path):
    w = World(tmp_path)
    d = tmp_path / "somedir"
    put(d / "secret.txt", "SENTINEL-NEVER-READ")
    (w.root / "linkdir").symlink_to(d, target_is_directory=True)
    with pytest.raises(H.HarvestError, match="linkdir"):
        w.harvest()


def test_a_required_artifact_that_is_a_symlink_fails_even_in_a_final_tree(tmp_path):
    w = World(tmp_path)
    tree = w.ev / "python__beer-song.final_tree"
    (tree / "manifest.json").rename(tree / "manifest.real")
    (tree / "manifest.json").symlink_to(tree / "manifest.real")
    with pytest.raises(H.HarvestError, match="manifest.json"):
        w.harvest()


def test_a_non_regular_file_fails(tmp_path):
    w = World(tmp_path)
    os.mkfifo(w.root / "pipe")
    with pytest.raises(H.HarvestError, match="pipe"):
        w.harvest()


# ------------------------------------------------------------------------------------------------ log slices
def test_the_legs_server_log_byte_range_is_inventoried_and_published_to_evidence(tmp_path):
    w = World(tmp_path, log=True)
    doc = w.harvest(worktree=w.wt)
    (log,) = [f for f in doc["files"] if f["source"].startswith("log:mlx_vlm.log:")]
    assert log["source"] == f"log:mlx_vlm.log:{len(b'before\n')}-{len(b'before\n') + len(b'line one\nline two\n')}"
    assert log["destination"] == "evidence" and (w.stage / log["published"]).read_bytes() == b"line one\nline two\n"
    assert log["sha256"] == sha(b"line one\nline two\n")


def test_log_bounds_that_are_unfinalized_or_report_problems_or_a_replaced_log_refuse(tmp_path):
    w = World(tmp_path, log=True)
    bounds = json.loads((w.root / "log_bounds.json").read_text())
    (w.root / "log_bounds.json").write_text(json.dumps(dict(bounds, finalized=None)))
    with pytest.raises(H.HarvestError, match="log_bounds"):
        w.harvest(worktree=w.wt)
    (w.root / "log_bounds.json").write_text(json.dumps(dict(bounds, problems=["x was replaced"])))
    with pytest.raises(H.HarvestError, match="log_bounds"):
        w.harvest(worktree=w.wt)
    (w.root / "log_bounds.json").write_text(json.dumps(bounds))
    lg = w.wt / "logs" / "mlx_vlm.log"
    lg.rename(lg.with_name("old.log"))
    put(lg, b"before\nline one\nline two\nafter\n")             # a new inode
    with pytest.raises(H.HarvestError, match="mlx_vlm.log"):
        w.harvest(worktree=w.wt)
    nothing_published(w)


def test_log_bounds_without_a_resolvable_worktree_refuse(tmp_path):
    w = World(tmp_path, log=True)
    with pytest.raises(H.HarvestError, match="worktree"):
        w.harvest(worktree=None)


# ------------------------------------------------------------------------------------------------ compression
def test_a_file_above_8_mb_is_published_xz_of_its_scrubbed_bytes(tmp_path):
    import lzma
    w = World(tmp_path)
    big = (f"{w.wd}/x line\n" * 1_000_000).encode()
    assert len(big) > H.COMPRESS_BYTES
    put(w.root / "RUNLOG.md", big)
    doc = w.harvest()
    e = entry(doc, "leg:RUNLOG.md")
    assert e["compression"] == "xz" and e["published"].endswith("RUNLOG.md.xz")
    pub = (w.stage / e["published"]).read_bytes()
    assert e["published_sha256"] == sha(pub) and e["sha256"] == sha(big)
    assert lzma.decompress(pub) == big.replace(str(w.wd).encode(), b"$STACK_WORKDIR")
    assert entry(doc, "leg:chain.json")["compression"] is None


def test_a_main_record_above_8_mb_stays_whole_and_is_never_compressed(tmp_path):
    w = World(tmp_path)
    put(w.root / "watch.jsonl", ("{\"t\": 1}\n" * 1_100_000))
    doc = w.harvest()
    assert entry(doc, "leg:watch.jsonl")["compression"] is None and entry(doc, "leg:watch.jsonl")["destination"] == "main"


# ------------------------------------------------------------------------------------------------ staged publication
def test_the_published_trees_hold_exactly_the_files_harvest_json_names(tmp_path):
    w = World(tmp_path, log=True)
    doc = w.harvest(worktree=w.wt)
    on_main = {p.relative_to(w.main).as_posix() for p in (w.main / WAVE2).rglob("*") if p.is_file()}
    on_ev = {p.relative_to(w.stage).as_posix() for p in (w.stage / WAVE2).rglob("*") if p.is_file()}
    named = {f["published"] for f in doc["files"] if f["published"]}
    assert on_main | on_ev == named | {f"{WAVE2}/{NAME}/HARVEST.json"} and not on_main & on_ev
    assert {f["published"] for f in doc["files"] if f["destination"] == "main"} <= on_main
    assert not [p for p in (w.main / WAVE2).iterdir() if p.name.endswith(".stage")]
    for f in doc["files"]:
        if f["published"]:
            base = w.main if f["destination"] == "main" else w.stage
            assert sha((base / f["published"]).read_bytes()) == f["published_sha256"]


def test_the_main_rename_is_the_single_commit_point(tmp_path, monkeypatch):
    w = World(tmp_path)
    real = H._rename
    calls = []

    def boom(src, dst):
        calls.append(dst)
        if str(dst).startswith(str(w.main)):
            raise OSError("simulated crash at the main rename")
        return real(src, dst)
    monkeypatch.setattr(H, "_rename", boom)
    with pytest.raises(OSError):
        w.harvest()
    assert w.evdest().exists() and not w.dest().exists() and w.harvest_json() is None     # evidence first, main never half-visible
    assert calls[0] == w.evdest()
    monkeypatch.setattr(H, "_rename", real)
    doc = w.harvest()                                                                     # the retry restarts and completes
    assert w.harvest_json() == doc and not [p for p in (w.main / WAVE2).iterdir() if p.name.endswith(".stage")]


def test_a_retry_with_a_verifying_harvest_json_is_done_and_changes_nothing(tmp_path):
    w = World(tmp_path)
    doc = w.harvest()
    snap = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in list(w.main.rglob("*")) + list(w.stage.rglob("*")) if p.is_file()}
    shutil_rm = __import__("shutil").rmtree
    shutil_rm(w.root / "s1")                                                                # the sources may even be gone: it is done
    again = w.harvest()
    assert again == doc
    assert snap == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in list(w.main.rglob("*")) + list(w.stage.rglob("*")) if p.is_file()}


def test_a_retry_discards_only_this_attempts_incomplete_destinations_and_stages(tmp_path):
    w = World(tmp_path)
    mine, other = w.dest(), w.dest(f"{LEG}.a2")
    put(mine / "leg.json", '{"partial": true}')                                  # an interrupted publication: no HARVEST.json
    put(w.evdest() / "stale.txt", "half")                                       # its evidence side
    put(mine.with_name(NAME + ".stage") / "x", "half stage")
    put(w.evdest().with_name(NAME + ".stage") / "x", "half stage")
    put(other / "chain.json", '{"other attempt": true}')
    put(other.with_name(f"{LEG}.a2.stage") / "y", "other's stage")
    put(w.evdest(f"{LEG}.a2") / "z", "other's evidence")
    doc = w.harvest()
    assert w.harvest_json() == doc and json.loads((mine / "leg.json").read_text())["state"] == "VALID"
    assert not (w.evdest() / "stale.txt").exists() and not (mine.with_name(NAME + ".stage")).exists()
    assert not w.evdest().with_name(NAME + ".stage").exists()
    assert (other / "chain.json").read_text() == '{"other attempt": true}' and not (other / "HARVEST.json").exists()
    assert (other.with_name(f"{LEG}.a2.stage") / "y").exists() and (w.evdest(f"{LEG}.a2") / "z").exists()


def test_a_harvest_json_that_does_not_verify_is_not_a_commit(tmp_path):
    w = World(tmp_path)
    doc = w.harvest()
    p = w.dest() / "chain.json"
    p.write_text(p.read_text() + " ")                                              # a published file no longer matches
    again = w.harvest()
    assert again["sha256"] and (w.dest() / "chain.json").read_bytes() == (w.root / "chain.json").read_bytes()
    assert again["files"] == doc["files"]


# ------------------------------------------------------------------------------------------------ portable main records, scrub
@pytest.mark.parametrize("rel", ["leg.json", "chain.json", "s1/rows.jsonl", "s1/rows.manifest.json", "log_bounds.json"])
def test_a_scrub_change_to_a_main_record_fails_the_harvest(tmp_path, rel):
    w = World(tmp_path)
    p = w.root / rel
    note = f"see {w.wd}/p426/where"                                  # an absolute path of this box: the scrub would rewrite it
    if rel.endswith(".jsonl"):
        row = json.loads(p.read_text().splitlines()[0])
        p.write_text(p.read_text() + json.dumps(dict(row, note=note)) + "\n")
    else:
        p.write_text(json.dumps(dict(json.loads(p.read_text()), note=note)))
    with pytest.raises(H.HarvestError, match=Path(rel).name):
        w.harvest()
    nothing_published(w)


def test_a_main_record_carrying_a_username_or_host_fails(tmp_path):
    w = World(tmp_path)
    p = w.root / "leg.json"
    doc = json.loads(p.read_text())
    doc["reason"] = "run by b2opuser on b2host"
    p.write_text(json.dumps(doc))
    with pytest.raises(H.HarvestError, match="leg.json"):
        w.harvest()


# ------------------------------------------------------------------------------------------------ secret gate
def refused_text(exc):
    return str(exc.value)


@pytest.mark.parametrize("value", [FAKE_HF, "sk-" + "s" * 40, "ghp_" + "R" * 36, "github_pat_" + "A" * 30, "AKIA" + "Z" * 16,
                                   "-----BEGIN " + "RSA PRIVATE KEY-----", "Authorization: Bearer " + "b" * 32],
                         ids=["hf", "sk", "ghp", "pat", "akia", "pem", "bearer"])
def test_a_credential_format_quarantines_the_file_and_fails_without_printing_it(tmp_path, value, capsys):
    w = World(tmp_path)
    log = w.root / "RUNLOG.md"
    log.write_text(f"captured: {value}\n")
    with pytest.raises(H.HarvestError) as exc:
        w.harvest()
    assert "RUNLOG.md" in str(exc.value) and value not in str(exc.value) and value not in "".join(capsys.readouterr())
    nothing_published(w)
    for p in tmp_path.rglob("*"):
        if p.is_file() and p != log:
            assert value.encode() not in p.read_bytes(), p


def test_an_exact_credential_value_quarantines_the_file_and_fails_without_printing_it(tmp_path, capsys):
    w = World(tmp_path)
    log = w.root / "RUNLOG.md"
    log.write_text(f"probe stderr: token {FAKE_SECRET}\n")
    with pytest.raises(H.HarvestError) as exc:
        w.harvest(secrets={"environ:P426_TEST_API_KEY": FAKE_SECRET})
    msg = str(exc.value)
    assert "RUNLOG.md" in msg and "exact:environ:P426_TEST_API_KEY" in msg and FAKE_SECRET not in msg
    assert FAKE_SECRET not in "".join(capsys.readouterr())
    nothing_published(w)
    for p in tmp_path.rglob("*"):
        if p.is_file() and p != log:
            assert FAKE_SECRET.encode() not in p.read_bytes(), p


def test_the_exact_value_is_matched_in_the_scrubbed_bytes_too(tmp_path):
    """A value hidden by the scrub's own rewriting is still found: the refusal scan covers the original AND the scrubbed bytes."""
    w = World(tmp_path)
    secret = "pw-" + "q" * 20
    put(w.root / "RUNLOG.md", f"x {secret}\n")
    with pytest.raises(H.HarvestError, match="RUNLOG.md"):
        w.harvest(secrets={"file:.hftoken": secret})


def test_a_secret_in_a_main_record_quarantines_it_too(tmp_path):
    w = World(tmp_path)
    p = w.root / "s1" / "rows.manifest.json"
    doc = json.loads(p.read_text())
    doc["env"] = FAKE_HF
    p.write_text(json.dumps(doc))
    with pytest.raises(H.HarvestError, match="rows.manifest.json"):
        w.harvest()


def test_a_binary_file_is_scanned_for_credentials_too(tmp_path):
    w = World(tmp_path)
    tree = w.ev / "python__beer-song.final_tree" / "objects"
    blob = b"\x00\xff\xfe junk " + FAKE_HF.encode() + b"\x00"
    put(tree / sha(blob), blob)
    with pytest.raises(H.HarvestError, match="objects"):
        w.harvest()


def test_placeholders_short_values_and_allowlisted_keys_never_quarantine(tmp_path):
    w = World(tmp_path)
    put(w.root / "RUNLOG.md", "TOKENIZERS_PARALLELISM=false keys=1 tokens=abc ok=true\n")
    values = S.credential_values(home=w.tmp / "home", config_path=w.tmp / "none.sh",
                                 environ={"TOKENIZERS_PARALLELISM": "false", "SOME_FEATURE_KEY": "1", "SHORT_TOKEN": "abc"})
    assert values == {}
    assert w.harvest(secrets=values)["state"] == "VALID"


def test_the_operator_email_and_its_domain_refuse_other_emails_are_listed(tmp_path):
    w = World(tmp_path)
    put(w.root / "RUNLOG.md", "the model wrote maintainer@example.org into a comment\n")
    doc = w.harvest(emails=("op.erator@corp-mail.example",))
    # J8 ruling: the addresses go to a local review file, never published; HARVEST.json carries the count and the file's portable path
    assert doc["review"]["emails_count"] == 1 and "emails" not in doc["review"]
    assert doc["review"]["emails_file"] == f"$STACK_WORKDIR/p426/review/{NAME}.emails.json"
    review = json.loads((w.wd / "p426" / "review" / f"{NAME}.emails.json").read_text())
    assert review == [dict(address="maintainer@example.org", sources=["leg:RUNLOG.md"])]
    for base in (w.main, w.stage):
        assert not any(b"maintainer@example.org" in p.read_bytes() for p in base.rglob("*") if p.is_file() and p.name != "RUNLOG.md"), base
    assert entry(doc, "leg:RUNLOG.md")["destination"] == "evidence"
    for text in ("mail op.erator@corp-mail.example now", "other colleague@corp-mail.example", "UPPER OP.ERATOR@CORP-MAIL.EXAMPLE"):
        w2 = World(tmp_path / text.split()[1].replace("@", "_").replace(".", "_"))
        put(w2.root / "RUNLOG.md", text + "\n")
        with pytest.raises(H.HarvestError, match="RUNLOG.md") as exc:
            w2.harvest(emails=("op.erator@corp-mail.example",))
        assert "op.erator@corp-mail.example" not in str(exc.value).lower().replace("email", "")  # the address itself is not echoed
        nothing_published(w2)


def test_an_operator_email_in_a_main_record_refuses(tmp_path):
    w = World(tmp_path)
    p = w.root / "leg.json"
    doc = json.loads(p.read_text())
    doc["reason"] = "owner op.erator@corp-mail.example"
    p.write_text(json.dumps(doc))
    with pytest.raises(H.HarvestError, match="leg.json"):
        w.harvest(emails=("op.erator@corp-mail.example",))


# ------------------------------------------------------------------------------------------------ credential sources (the CLI wiring)
def box(tmp_path, **extra):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return dict(environ=dict(STACK_WORKDIR=str(tmp_path / "wd"), HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"), **extra), home=home)


def run_main(w, tmp_path, *extra, **boxkw):
    argv = ["wave2", "--leg-root", str(w.root), "--main-root", str(w.main), "--evidence-stage", str(w.stage), *extra]
    return H.main(argv, **box(tmp_path, **boxkw))


@pytest.mark.parametrize("source", ["hftoken", "hf_cache_token", "machine_config", "environment", "worktree_env"])
def test_every_credential_source_is_used_for_exact_matching(tmp_path, source, capsys):
    w = World(tmp_path)
    home = tmp_path / "home"
    extra = {}
    if source == "hftoken":
        put(home / ".hftoken", FAKE_SECRET)
    elif source == "hf_cache_token":
        put(home / ".cache/huggingface/token", FAKE_SECRET + "\n")
    elif source == "machine_config":
        put(home / ".config/mlx_local_stack/config.sh", f'export HF_TOKEN="{FAKE_SECRET}"\n')
    elif source == "environment":
        extra["P426_TEST_API_KEY"] = FAKE_SECRET
    else:
        put(w.wt / ".env", f"SERVICE_API_KEY={FAKE_SECRET}\n")
        put(w.wd / "p426" / "records" / "amendment.json", "{}")
        put(w.wd / "p426" / "records" / "v8_base.json", json.dumps(dict(off_worktree="$STACK_WORKDIR/../wt-off", on_worktree="$STACK_WORKDIR/../wt-off")))
    log = w.root / "RUNLOG.md"
    log.write_text(f"stderr: {FAKE_SECRET}\n")
    rc = run_main(w, tmp_path, *(["--env-file", str(w.wt / ".env")] if source == "worktree_env" else []), **extra)
    out = capsys.readouterr()
    assert rc == 2 and "REFUSED:" in out.err and "RUNLOG.md" in out.err
    assert FAKE_SECRET not in out.out + out.err
    nothing_published(w)
    for p in tmp_path.rglob("*"):
        if p.is_file() and p.parent.name not in ("home", "wt-off") and p != log and p.name not in (".hftoken", "token", "config.sh", ".env"):
            assert FAKE_SECRET.encode() not in p.read_bytes(), p


def test_an_unreadable_token_file_refuses_and_an_absent_one_is_recorded(tmp_path, capsys):
    w = World(tmp_path)
    token = put(tmp_path / "home" / ".hftoken", FAKE_SECRET)
    os.chmod(token, 0)
    try:
        rc = run_main(w, tmp_path)
    finally:
        os.chmod(token, 0o600)
    err = capsys.readouterr().err
    assert rc == 2 and "REFUSED:" in err and ".hftoken" in err and FAKE_SECRET not in err
    nothing_published(w)
    token.unlink()
    assert run_main(w, tmp_path) == 0
    doc = w.harvest_json()
    absent = json.dumps(doc["review"]["absent_secret_sources"])
    assert ".hftoken" in absent and ".cache/huggingface/token" in absent and "config" in absent


# ------------------------------------------------------------------------------------------------ the CLI
def test_the_cli_publishes_prints_nothing_secret_and_returns_zero(tmp_path, capsys):
    w = World(tmp_path)
    assert run_main(w, tmp_path, "--operator-email", "op.erator@corp-mail.example") == 0
    out = capsys.readouterr()
    assert "REFUSED" not in out.err and w.harvest_json()["state"] == "VALID"


def test_the_cli_takes_the_operator_email_flag_repeatedly_and_refuses_it(tmp_path, capsys):
    w = World(tmp_path)
    put(w.root / "RUNLOG.md", "from op.erator@corp-mail.example\n")
    assert run_main(w, tmp_path, "--operator-email", "x@y.example", "--operator-email", "op.erator@corp-mail.example") == 2
    assert "REFUSED:" in capsys.readouterr().err
    nothing_published(w)


def test_a_harvest_error_prints_one_refused_line_exits_2_and_publishes_nothing(tmp_path, capsys):
    w = World(tmp_path)
    put(w.root / "stray.unknown-kind", "x")
    assert run_main(w, tmp_path) == 2
    err = capsys.readouterr().err
    assert [ln for ln in err.splitlines() if ln.startswith("REFUSED: ")] and "stray.unknown-kind" in err
    nothing_published(w)


@pytest.mark.parametrize("argv", [["wave2"], ["wave2", "--leg-root", "/nonexistent-leg"], ["nonsense"]])
def test_the_cli_refuses_bad_arguments_with_rc_2(tmp_path, capsys, argv):
    assert H.main(argv, **box(tmp_path)) == 2
    assert "REFUSED:" in capsys.readouterr().err


def test_the_cli_refuses_without_a_stack_workdir(tmp_path, capsys):
    w = World(tmp_path)
    kw = box(tmp_path)
    kw["environ"].pop("STACK_WORKDIR")
    assert H.main(["wave2", "--leg-root", str(w.root), "--main-root", str(w.main), "--evidence-stage", str(w.stage)], **kw) == 2
    assert "STACK_WORKDIR" in capsys.readouterr().err


def test_the_cli_resolves_the_arms_worktree_from_the_chains_frozen_record_for_log_slices(tmp_path):
    w = World(tmp_path, log=True)
    put(w.wd / "p426" / "records" / "amendment.json", "{}")
    pjson(w.wd / "p426" / "records" / "v8_base.json", dict(off_worktree="$STACK_WORKDIR/../wt-off", on_worktree="$STACK_WORKDIR/../wt-on"))
    assert run_main(w, tmp_path) == 0
    assert any(f["source"].startswith("log:mlx_vlm.log:") for f in w.harvest_json()["files"])


def test_both_arms_worktree_env_files_are_credential_sources_without_a_flag(tmp_path, capsys):
    """§11.3: `<WT>/.env` of BOTH arms, found through the chain's frozen record (here the ON arm's, not the leg's own)."""
    w = World(tmp_path)
    put(tmp_path / "wt-on" / ".env", f"SERVICE_API_KEY={FAKE_SECRET}\n")
    put(w.wd / "p426" / "records" / "amendment.json", "{}")
    pjson(w.wd / "p426" / "records" / "v8_base.json", dict(off_worktree="$STACK_WORKDIR/../wt-off", on_worktree="$STACK_WORKDIR/../wt-on"))
    (w.root / "RUNLOG.md").write_text(f"leaked {FAKE_SECRET}\n")
    assert run_main(w, tmp_path) == 2
    err = capsys.readouterr().err
    assert "RUNLOG.md" in err and "exact:env_file" in err and FAKE_SECRET not in err
    nothing_published(w)


def test_the_module_runs_as_python_dash_m_from_a_scratch_copy(tmp_path):
    import shutil
    import subprocess
    import sys
    w = World(tmp_path)
    repo = tmp_path / "repo" / "benchmark"
    shutil.copytree(Path(H.__file__).parent, repo / "bench", ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"), symlinks=True)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "TMPDIR")}
    env.update(HOME=str(tmp_path / "home"), XDG_CONFIG_HOME=str(tmp_path / "home/.config"), STACK_WORKDIR=str(w.wd), PYTHONDONTWRITEBYTECODE="1")
    (tmp_path / "home").mkdir(exist_ok=True)
    got = subprocess.run([sys.executable, "-m", "bench.p426_harvest", "wave2", "--leg-root", str(w.root), "--main-root", str(w.main),
                          "--evidence-stage", str(w.stage)], cwd=str(repo), env=env, capture_output=True, text=True, timeout=120,
                         stdin=subprocess.DEVNULL)
    assert got.returncode == 0, got.stderr[-1500:]
    assert w.harvest_json()["state"] == "VALID"


# ------------------------------------------------------------------------------------------------ publish_dossier / publish_run_files
def a_dossier(tmp_path, **over):
    doc = dict(pair="pilot", arms={"off": {"attempt": "tg1-p426-off-pilot.a1", "receipt_sha256": "1" * 64, "harvest_sha256": "2" * 64},
                                   "on": {"attempt": "tg1-p426-on-pilot.a1", "receipt_sha256": "3" * 64, "harvest_sha256": "4" * 64}},
               differences=[], verdict="PASS", at="2026-10-27T00:00:00Z")
    doc.update(over)
    return pjson(tmp_path / "wd/p426/wave2/pairs/pilot__off-a1__on-a1.json", seal(doc))


def test_publish_dossier_signature_and_return_shape(tmp_path):
    assert list(inspect.signature(H.publish_dossier).parameters) == ["path", "main_root", "evidence_stage", "scrub"]     # (unchanged by
    assert list(inspect.signature(H.publish_run_files).parameters) == ["paths", "main_root", "scrub"]                   # fix round 4)
    assert all(inspect.signature(H.publish_dossier).parameters[n].kind is inspect.Parameter.KEYWORD_ONLY for n in ("main_root", "evidence_stage", "scrub"))
    assert inspect.signature(H.harvest_wave2).parameters["secrets"].kind is inspect.Parameter.KEYWORD_ONLY
    src = a_dossier(tmp_path)
    main, stage = tmp_path / "main", tmp_path / "stage"
    res = H.publish_dossier(src, main_root=main, evidence_stage=stage, scrub=scrub_for(tmp_path))
    dst = main / WAVE2 / "pairs" / src.name
    assert dst.read_bytes() == src.read_bytes()
    assert set(res) == {"published", "harvest_sha256"}
    (pub,) = res["published"]
    assert set(pub) >= {"source", "destination", "sha256"} and pub["sha256"] == sha(src.read_bytes()) and Path(pub["destination"]).name == src.name
    assert res["harvest_sha256"] is None or len(res["harvest_sha256"]) == 64
    again = H.publish_dossier(src, main_root=main, evidence_stage=stage, scrub=scrub_for(tmp_path))
    assert again == res and dst.read_bytes() == src.read_bytes()
    assert not [p for p in dst.parent.iterdir() if p.name.endswith(".stage") or p.name.startswith(".")]


def test_publish_dossier_refuses_a_dossier_the_scrub_would_change_and_publishes_nothing(tmp_path):
    src = a_dossier(tmp_path, verdict=f"PASS (see {tmp_path}/wd/p426/wave2/RUNLOG.md)")
    with pytest.raises(H.HarvestError):
        H.publish_dossier(src, main_root=tmp_path / "main", evidence_stage=tmp_path / "stage", scrub=scrub_for(tmp_path))
    assert not (tmp_path / "main").exists() or not list((tmp_path / "main").rglob("*.json"))


def test_publish_dossier_refuses_a_credential_an_operator_email_and_a_bad_self_hash(tmp_path):
    for over in (dict(verdict="x " + FAKE_HF), dict(verdict="x op.erator@corp-mail.example")):
        src = a_dossier(tmp_path / str(len(over["verdict"])), **over)
        with pytest.raises(H.HarvestError) as exc:
            H.publish_dossier(src, main_root=tmp_path / "main", evidence_stage=tmp_path / "stage",
                              scrub=scrub_for(tmp_path, emails=("op.erator@corp-mail.example",)))
        assert FAKE_HF not in str(exc.value)
    src = a_dossier(tmp_path / "z")
    doc = json.loads(src.read_text())
    src.write_text(json.dumps(dict(doc, verdict="FAIL")))
    with pytest.raises(H.HarvestError, match="sha256|self"):
        H.publish_dossier(src, main_root=tmp_path / "main", evidence_stage=tmp_path / "stage", scrub=scrub_for(tmp_path))
    assert not (tmp_path / "main" / WAVE2 / "pairs").exists()


def test_publish_dossier_never_replaces_a_different_published_dossier(tmp_path):
    src = a_dossier(tmp_path)
    main, stage = tmp_path / "main", tmp_path / "stage"
    H.publish_dossier(src, main_root=main, evidence_stage=stage, scrub=scrub_for(tmp_path))
    src.unlink()
    a_dossier(tmp_path, verdict="FAIL")
    with pytest.raises(H.HarvestError, match="differs|exists"):
        H.publish_dossier(src, main_root=main, evidence_stage=stage, scrub=scrub_for(tmp_path))
    assert json.loads((main / WAVE2 / "pairs" / src.name).read_text())["verdict"] == "PASS"


def test_publish_run_files_publishes_each_file_to_wave2_run_byte_identical(tmp_path):
    rec = tmp_path / "wd/p426/records"
    files = [pjson(rec / "v8_base.json", seal(dict(kind="p426_v8_base", off_worktree="$STACK_WORKDIR/stack-p426-off"))),    # fix round 4:
             pjson(rec / "amendment.json", seal(dict(kind="p426_timeout_amendment"))),                          # sealed immutable records
             pjson(tmp_path / "wd/p426/wave2/sequence.json", dict(legs=[], pairs=[], previous_sha256=None))]
    main = tmp_path / "main"
    res = H.publish_run_files(files, main_root=main, scrub=scrub_for(tmp_path))
    assert set(res) == {"published", "harvest_sha256"}
    by = {Path(e["destination"]).name: e for e in res["published"]}
    for f in files:
        assert (main / WAVE2 / "run" / f.name).read_bytes() == f.read_bytes()
        assert by[f.name]["sha256"] == sha(f.read_bytes()) and by[f.name]["source"].startswith("record:")
    assert H.publish_run_files(files, main_root=main, scrub=scrub_for(tmp_path)) == res


def test_publish_run_files_lets_sequence_json_advance_but_never_rewrites_a_frozen_record(tmp_path):
    rec = tmp_path / "wd/p426/records"
    v8 = pjson(rec / "v8_base.json", seal(dict(kind="p426_v8_base")))
    seqf = pjson(tmp_path / "wd/p426/wave2/sequence.json", dict(legs=[], pairs=[], previous_sha256=None))
    main = tmp_path / "main"
    H.publish_run_files([v8, seqf], main_root=main, scrub=scrub_for(tmp_path))
    seqf.write_text(json.dumps(dict(legs=[dict(leg=LEG)], pairs=[], previous_sha256="a" * 64)))      # the sequencer's atomic replace
    H.publish_run_files([v8, seqf], main_root=main, scrub=scrub_for(tmp_path))
    assert json.loads((main / WAVE2 / "run" / "sequence.json").read_text())["legs"] == [dict(leg=LEG)]
    v8.write_text(json.dumps(seal(dict(kind="changed"))))
    with pytest.raises(H.HarvestError, match="v8_base.json"):
        H.publish_run_files([v8], main_root=main, scrub=scrub_for(tmp_path))
    assert json.loads((main / WAVE2 / "run" / "v8_base.json").read_text()) == seal(dict(kind="p426_v8_base"))


def test_publish_run_files_refuses_a_file_the_scrub_would_change_and_publishes_nothing(tmp_path):
    ok = pjson(tmp_path / "wd/p426/records/v8_base.json", seal(dict(kind="p426_v8_base")))
    bad = pjson(tmp_path / "wd/p426/wave2/sequence.json", dict(legs=[], note=f"{tmp_path}/wd/p426/x"))
    with pytest.raises(H.HarvestError, match="sequence.json"):
        H.publish_run_files([ok, bad], main_root=tmp_path / "main", scrub=scrub_for(tmp_path))
    assert not (tmp_path / "main").exists() or not list((tmp_path / "main").rglob("*.json"))


def test_publish_run_files_refuses_a_symlink_and_a_non_regular_path(tmp_path):
    real = pjson(tmp_path / "wd/p426/records/v8_base.json", dict(kind="p426_v8_base"))
    link = tmp_path / "wd/p426/records/link.json"
    link.symlink_to(real)
    with pytest.raises(H.HarvestError, match="link.json"):
        H.publish_run_files([link], main_root=tmp_path / "main", scrub=scrub_for(tmp_path))
    with pytest.raises(H.HarvestError, match="records"):
        H.publish_run_files([real.parent], main_root=tmp_path / "main", scrub=scrub_for(tmp_path))


# ------------------------------------------------------------------------------------------------ Wave 1 unchanged
def test_the_wave1_entry_points_and_scrub_constructor_are_unchanged():
    assert callable(H.harvest) and callable(H.harvest_run_files) and H.WAVE1.as_posix() == "benchmark/results/p426/wave1"
    s = H.Scrub(workdir=Path("/w"), repo=Path("/r"), home=Path("/h"), user="u", hosts=("h",))
    assert s.emails == () and s.text("/w/x") == "$STACK_WORKDIR/x"
    assert list(inspect.signature(H.harvest).parameters) == ["name", "plan", "main_root", "receipts", "stdout", "log_slice", "scrub", "build"]


# ------------------------------------------------------------------------------------------------ s9 follow-up: rulings U1, U2, J8
# U1: a REAL `--p426` chain leg (the s8c topology harness: the real sequencer and chain, the fake item-barrier probe, absolute tmp_path
# paths) harvests without a scrub refusal. The harvest of an actual leg root is the proof the chain's records are portable.
from bench.tests.test_b2_s8c_chain import topo, go_topology    # noqa: E402,F401  (fixture + driver of the existing harness)


def topo_scrub(t, emails=()):
    return H.Scrub(workdir=t.wd, repo=t.wd.parent / "main", home=t.wd.parent / "home", user="b2opuser", hosts=("b2host",), emails=tuple(emails))


def test_a_real_p426_leg_harvests_without_a_scrub_refusal(topo, monkeypatch):
    for key, value in list(os.environ.items()):                  # the receipt records the launch environment: keep this host's home
        if str(Path.home()) in value:                            # paths (PATH, shell state) out of the fixture's receipt
            monkeypatch.delenv(key)
    assert go_topology(topo, "run", "--through", "tg1-p426-off-pilot") == 0
    root = topo.out / "tg1-p426-off-pilot.a1"
    # Fixture step, not product behaviour: `receipt.json` is the s5 receipt, which canonicalizes `$HOME` from the router's HOME. The
    # harness's fake environment has a placeholder HOME and its fake probe / interpreter live in this checkout (production's probe is
    # `<WT>/benchmark/run_tg1_probe.py`), so re-canonicalize those host paths as production's real HOME would, and re-seal.
    from bench import chain_core as cc
    from bench import p426_hooks as ph
    receipt = json.loads((root / "receipt.json").read_text())
    (root / "receipt.json").write_text(json.dumps(ph.seal(cc.portable_doc(receipt, out_root=root, workdir=topo.wd, worktree=topo.off,
                                                                            home=Path.home()))))
    assert str(Path.home()) not in (root / "receipt.json").read_text()
    main, stage = topo.wd.parent / "main", topo.wd.parent / "stage"
    doc = H.harvest_wave2(root, main_root=main, evidence_stage=stage, scrub=topo_scrub(topo), secrets={}, worktree=topo.off, workdir=topo.wd)
    assert doc["state"] == "VALID"
    chain = entry(doc, "leg:chain.json")
    assert chain["destination"] == "main" and chain["published_sha256"] == chain["sha256"]
    text = (root / "chain.json").read_text()
    assert str(topo.wd) not in text and str(topo.wd.resolve()) not in text, "an absolute path of this box is left in chain.json"
    probe_cmd = json.loads(text)["attempts"][0]["argv"]                # the launched probe command (the in-process `argv` is pytest's)
    assert probe_cmd[probe_cmd.index("--out") + 1].startswith("<OUT>/")
    assert probe_cmd[probe_cmd.index("--universe") + 1] == "$STACK_WORKDIR/universe.json"
    assert json.loads(text)["probe"].startswith("$HOME/")             # the harness's fake probe lives under this host's home
    ready = next((root / "items").glob("*.ready.json"))
    assert json.loads(ready.read_text())["log_cursor"]["path"] == "<WT>/logs/mlx_vlm.log"
    assert str(Path.home()) not in text


def test_chain_core_portable_doc_round_trips_and_leaves_other_strings_alone(tmp_path):
    from bench import chain_core as cc
    roots = dict(out_root=tmp_path / "wd/p426/wave2/leg.a1", workdir=tmp_path / "wd", worktree=tmp_path / "wd/p426/wt", home=tmp_path / "hm")
    doc = dict(argv=["--out-root", str(roots["out_root"]), "--probe", str(roots["worktree"] / "benchmark/run.py"), "--n", "3"],
               nested=[dict(log=str(roots["out_root"] / "s1/x.log"), home=str(roots["home"] / ".cache/y"), universe=str(roots["workdir"] / "u.json"))],
               plain="not a path", number=7, none=None, near=str(roots["workdir"]) + "-other")
    port = cc.portable_doc(doc, **roots)
    assert port["argv"] == ["--out-root", "<OUT>", "--probe", "<WT>/benchmark/run.py", "--n", "3"]
    assert port["nested"] == [dict(log="<OUT>/s1/x.log", home="$HOME/.cache/y", universe="$STACK_WORKDIR/u.json")]
    assert port["plain"] == "not a path" and port["number"] == 7 and port["none"] is None and port["near"] == doc["near"]
    assert cc.expand_doc(port, **roots) == doc


# U2: the sequencer's launch log lives in `<out-base>/logs/<attempt>.stdout`, never inside the attempt's out-root (which the chain
# creates fresh), and the harvest inventories it with the attempt, routed to `evidence`.
def test_the_box_ops_write_each_launch_stdout_to_out_base_logs_attempt_stdout(tmp_path):
    import sys
    from bench import p426_wave2 as w2
    out_base = tmp_path / "wd" / "p426" / "wave2"
    root = out_base / "tg1-p426-off-pilot.a1"
    ops = w2.BoxSeqOps(tmp_path / "wd", main_root=tmp_path / "main", evidence_stage=tmp_path / "stage")
    handle = ops.launch([sys.executable, "-c", "print('launch says hi')", "--out-root", str(root)], cwd=tmp_path, pass_fds=())
    assert ops.wait(handle) == 0
    assert (out_base / "logs" / "tg1-p426-off-pilot.a1.stdout").read_text() == "launch says hi\n"
    assert not root.exists() and not (out_base / "tg1-p426-off-pilot.a1.stdout").exists()


def test_the_harvest_inventories_the_launch_log_with_the_attempt_and_routes_it_to_evidence(tmp_path):
    w = World(tmp_path)
    log = put(w.root.parent / "logs" / f"{NAME}.stdout", f"chain stdout in {w.wd}/p426 by b2opuser\n")
    doc = w.harvest()
    e = entry(doc, f"record:logs/{NAME}.stdout")
    assert e["destination"] == "evidence" and e["sha256"] == sha(log.read_bytes())
    assert (w.stage / e["published"]).read_text() == "chain stdout in $STACK_WORKDIR/p426 by <user>\n"
    assert not (w.main / e["published"]).exists()


def test_the_launch_log_is_optional_never_a_symlink_and_passes_the_secret_gate(tmp_path):
    assert not [f for f in World(tmp_path / "a").harvest()["files"] if f["source"].startswith("record:")]
    w = World(tmp_path / "b")
    outside = put(tmp_path / "outside.txt", "SENTINEL-NEVER-READ")
    (w.root.parent / "logs").mkdir(parents=True)
    (w.root.parent / "logs" / f"{NAME}.stdout").symlink_to(outside)
    with pytest.raises(H.HarvestError, match="stdout"):
        w.harvest()
    w2 = World(tmp_path / "c")
    put(w2.root.parent / "logs" / f"{NAME}.stdout", f"leak {FAKE_HF}\n")
    with pytest.raises(H.HarvestError, match="stdout") as exc:
        w2.harvest()
    assert FAKE_HF not in str(exc.value)


def test_a_leg_without_foreign_addresses_has_an_empty_review_file_and_a_zero_count(tmp_path):
    w = World(tmp_path)
    doc = w.harvest()
    assert doc["review"]["emails_count"] == 0
    assert json.loads((w.wd / "p426" / "review" / f"{NAME}.emails.json").read_text()) == []


def test_a_refused_harvest_writes_no_review_file(tmp_path):
    w = World(tmp_path)
    put(w.root / "RUNLOG.md", f"maintainer@example.org and {FAKE_HF}\n")
    with pytest.raises(H.HarvestError):
        w.harvest()
    assert not (w.wd / "p426" / "review").exists()
