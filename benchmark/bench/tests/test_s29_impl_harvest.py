"""S29 (C384 / S29-P6) implementer tests, the Wave 2 harvest: P6a a `<step>.marker` directly in a tg2 `<item>.grades/seq-NNNN/` is
harvested and scrubbed as evidence (that boundary only); P6b a regular file no rule matches is not copied, it is listed in
HARVEST.json (scrubbed portable source and size; spec v1.1: no digest) and the harvest continues, and a reference to it is listed
(whether its digest matches), not refused; every other refusal is unchanged; H5 the kept original `leg.c360.json` is harvested
beside the superseding `leg.json`, and a superseding `leg.json` publishes only with it (v1.1 link check). Hermetic: the B2
s9 harvest world plus the a3 grade layout (`javascript__zebra-puzzle.grades/seq-0002/` with `execute.marker`, `execute.out`,
`execute-readback.*`)."""
from __future__ import annotations

import json
import os

import pytest

from bench import p426_harvest as H
from bench.tests.test_b2_s9_harvest import FAKE_HF, NAME, WAVE2, World, entry, nothing_published, put, seal, sha

MARKER = b"TG2_RUNNER_START 0255500343d02559\n"          # the a3 grader marker's shape (34 bytes)
GRADES = "javascript__zebra-puzzle.grades"
READBACK = ("execute-readback-n.err", "execute-readback-n.out", "execute-readback-pre.err", "execute-readback-pre.out",
            "execute-readback-rm.err", "execute-readback-rm.out", "execute-readback-v.err", "execute-readback-v.out",
            "execute-readback.inspect", "execute-readback.inspect.err", "execute-readback.stderr", "execute-readback.stdout")


def a3_grades(w, *, extra=(), marker=MARKER):
    """The timeout grade's seq dir as tg2_grade leaves it, every file referenced by the row (as the a3 row's artifacts are)."""
    seq = w.ev / GRADES / "seq-0002"
    files = {"execute.marker": marker, "execute.out": marker, "index.json": b"{}\n"}
    files.update({n: b"" for n in READBACK})
    files.update(dict(extra))
    for n, data in files.items():
        put(seq / n, data)
    rows_path = w.root / "s1" / "rows.jsonl"
    rows = [json.loads(x) for x in rows_path.read_text().splitlines() if x.strip()]
    arts = rows[0]["grade_reports"][0]["artifacts"]
    for n in files:
        arts[n] = dict(path=w.p(seq / n), sha256=sha((seq / n).read_bytes()))
    rows_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return seq


def src(w, seq, name):
    from bench.tests.test_b2_s9_harvest import RUN_ID
    return f"evidence:{RUN_ID}/{GRADES}/{seq.name}/{name}"


# ----------------------------------------------------------------------------------------------- P6a
def test_p6a_the_marker_is_evidence_at_the_grade_boundary_only():
    assert H.classify("evidence", f"{GRADES}/seq-0002/execute.marker") == ("evidence", None)
    assert H.classify("evidence", "rust__say.grades/seq-0001/compile.marker") == ("evidence", None)
    for other in (f"{GRADES}/execute.marker", f"{GRADES}/seq-0002/sub/execute.marker", "javascript__zebra-puzzle/seq-0002/x.marker",
                  "x.marker", f"{GRADES}/seq-2/execute.marker", "python__x.grades/seq-0001/execute.marker"):
        assert H.classify("evidence", other) is None, other
    assert H.classify("leg", "s1/x.marker") is None and H.classify("run", "grading-private/x.marker") is None


def test_p6a_the_a3_grade_dir_harvests_with_the_marker(tmp_path):
    w = World(tmp_path)
    seq = a3_grades(w)
    doc = w.harvest()
    e = entry(doc, src(w, seq, "execute.marker"))
    assert e["destination"] == "evidence" and e["sha256"] == sha(MARKER)
    assert (w.stage / e["published"]).read_bytes() == MARKER
    for n in ("execute.out", *READBACK):
        assert entry(doc, src(w, seq, n))["destination"] == "evidence", n
    assert doc.get("unrecognised", []) == [] and doc.get("unrecognised_references", []) == []


def test_p6a_the_marker_is_scrubbed_like_the_other_grade_outputs(tmp_path):
    w = World(tmp_path)
    seq = a3_grades(w, marker=f"TG2_RUNNER_START at {w.wd}/m65/x\n".encode())
    doc = w.harvest()
    e = entry(doc, src(w, seq, "execute.marker"))
    assert (w.stage / e["published"]).read_bytes() == b"TG2_RUNNER_START at $STACK_WORKDIR/m65/x\n"


def test_p6a_a_credential_in_the_marker_still_refuses(tmp_path):
    w = World(tmp_path)
    a3_grades(w, marker=f"token {FAKE_HF}\n".encode())
    with pytest.raises(H.HarvestError, match="execute.marker"):
        w.harvest()
    nothing_published(w)


# ----------------------------------------------------------------------------------------------- P6b
def test_p6b_an_unrecognised_file_and_its_row_reference_are_listed_not_refused(tmp_path):
    w = World(tmp_path)
    odd = b"a file no rule matches\n"
    seq = a3_grades(w, extra={"execute.weird": odd})
    doc = w.harvest()
    s = src(w, seq, "execute.weird")
    assert doc["unrecognised"] == [dict(source=s, size=len(odd))]                 # v1.1: nothing derived from its bytes
    (ref,) = doc["unrecognised_references"]
    assert set(ref) == {"reference", "source", "sha256_matches"}
    assert ref["source"] == s and ref["reference"].startswith("leg:s1/rows.jsonl:1") and ref["sha256_matches"] is True
    assert s not in [f["source"] for f in doc["files"]]
    for base in (w.main, w.stage):                                           # never copied
        assert not any(p.name == "execute.weird" for p in base.rglob("*")), base
    assert doc["sha256"] == H._canon_sha(doc)


def test_p6b_unrecognised_files_in_every_root_are_listed(tmp_path):
    w = World(tmp_path)
    put(w.root / "stray.unknown-kind", "x")
    put(w.run / "grading-private" / "keep" / "seq-1" / "mystery.bin", "yy")
    doc = w.harvest()
    from bench.tests.test_b2_s9_harvest import RUN_ID
    got = {u["source"]: u for u in doc["unrecognised"]}
    assert set(got) == {"leg:stray.unknown-kind", f"run:{RUN_ID}/grading-private/keep/seq-1/mystery.bin"}
    assert got["leg:stray.unknown-kind"] == dict(source="leg:stray.unknown-kind", size=1)
    assert doc["unrecognised_references"] == []
    assert not (w.dest() / "stray.unknown-kind").exists()


def test_p6b_a_reference_whose_digest_differs_is_listed_with_the_mismatch(tmp_path):
    w = World(tmp_path)
    seq = a3_grades(w, extra={"execute.weird": b"one\n"})
    (seq / "execute.weird").write_bytes(b"two\n")
    doc = w.harvest()
    (ref,) = doc["unrecognised_references"]
    assert ref["sha256_matches"] is False and "sha256" not in ref
    assert sha(b"two\n") not in json.dumps(doc)


def test_p6b_the_cli_logs_the_unrecognised_files(tmp_path, capsys):
    w = World(tmp_path)
    put(w.root / "stray.unknown-kind", "x")
    home = tmp_path / "home"
    home.mkdir()
    rc = H.main(["wave2", "--leg-root", str(w.root), "--main-root", str(w.main), "--evidence-stage", str(w.stage),
                 "--operator-email", "op.erator@corp-mail.example"],
                environ=dict(STACK_WORKDIR=str(w.wd), HOME=str(home), XDG_CONFIG_HOME=str(home / ".config")), home=home)
    assert rc == 0
    err = capsys.readouterr().err
    assert "UNRECOGNISED: leg:stray.unknown-kind (1 bytes): no harvest rule" in err and sha(b"x") not in err


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_p6b_links_and_non_regular_files_still_refuse(tmp_path, kind):
    w = World(tmp_path)
    p = w.root / "s1" / "odd.thing"
    if kind == "symlink":
        os.symlink(w.root / "leg.json", p)
    else:
        os.mkfifo(p)
    with pytest.raises(H.HarvestError, match="odd.thing"):
        w.harvest()
    nothing_published(w)


def test_p6b_a_reference_outside_the_roots_still_refuses(tmp_path):
    w = World(tmp_path)
    outside = put(w.wd / "elsewhere" / "x.out", "x")
    rows_path = w.root / "s1" / "rows.jsonl"
    rows = [json.loads(x) for x in rows_path.read_text().splitlines() if x.strip()]
    rows[0]["grade_reports"][0]["artifacts"]["x"] = dict(path=w.p(outside), sha256=sha(b"x"))
    rows_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(H.HarvestError, match="outside"):
        w.harvest()


def test_p6b_a_dry_run_reports_no_problem_for_an_unrecognised_file(tmp_path):
    w = World(tmp_path)
    put(w.root / "stray.unknown-kind", "x")
    doc = w.harvest(dry_run=True)
    assert [u["source"] for u in doc["unrecognised"]] == ["leg:stray.unknown-kind"]
    nothing_published(w)


# ----------------------------------------------------------------------------------------------- H5: the kept original
def superseding(w, original, **c384):
    """`leg.json` becomes a sealed C384 successor of `original` (the sequencer's `c384` block; overrides in `c384`)."""
    old = json.loads(original)
    block = dict(rule="C384", superseded=H.C384_SUPERSEDED, superseded_sha256=old["sha256"],
                 superseded_file_sha256=sha(original))
    block.update(c384)
    new = seal(dict({k: v for k, v in old.items() if k != "sha256"}, c384=block))
    (w.root / "leg.json").write_text(json.dumps(new, indent=1, sort_keys=True) + "\n")
    return new


def test_h5_the_kept_original_is_harvested_as_a_main_record_beside_the_new_leg_json(tmp_path):
    w = World(tmp_path)
    original = (w.root / "leg.json").read_bytes()
    (w.root / "leg.c360.json").write_bytes(original)
    old = json.loads(original)
    superseding(w, original)
    doc = w.harvest()
    assert entry(doc, "leg:leg.c360.json")["destination"] == "main"
    assert (w.dest() / "leg.c360.json").read_bytes() == original
    assert json.loads((w.dest() / "leg.json").read_text())["c384"]["superseded_sha256"] == old["sha256"]


def test_h5_a_tampered_kept_original_refuses(tmp_path):
    w = World(tmp_path)
    old = json.loads((w.root / "leg.json").read_text())
    assert old["state"] == "VALID"
    (w.root / "leg.c360.json").write_text(json.dumps(dict(old, state="INVALID")))     # edited, not resealed
    with pytest.raises(H.HarvestError, match="leg.c360.json"):
        w.harvest()
    assert not (w.main / WAVE2 / NAME).exists()


# ----------------------------------------------------------------------------------------------- fix round 1
def test_p6b_nothing_derived_from_an_unrecognised_files_bytes_is_published(tmp_path):
    """v1.1 P6b: the listing (file and reference) carries no digest of the unscanned bytes, in the record or the log line."""
    w = World(tmp_path)
    odd = b"a short secret-ish value\n"
    a3_grades(w, extra={"execute.weird": odd})
    put(w.root / "stray.unknown-kind", "x")
    doc = w.harvest()
    text = (w.dest() / "HARVEST.json").read_text()
    for digest in (sha(odd), sha(b"x")):
        assert digest not in text and digest not in json.dumps(doc)
    assert all(set(u) == {"source", "size"} for u in doc["unrecognised"])
    assert all("sha256" not in r for r in doc["unrecognised_references"])


def test_p6b_a_listed_path_the_scrub_would_change_is_listed_scrubbed_and_never_refuses(tmp_path):
    """v1.1 P6b: an unrecognised file under a directory named after the operator account: listed in its scrubbed form."""
    w = World(tmp_path)
    put(w.root / "b2opuser" / "notes.dat", b"n\n")
    doc = w.harvest()
    (u,) = doc["unrecognised"]
    assert "b2opuser" not in u["source"] and u["source"].endswith("/notes.dat") and u["size"] == 2
    assert "b2opuser" not in (w.dest() / "HARVEST.json").read_text()
    assert w.harvest() == doc                                                # idempotent: the committed record verifies


def test_p6b_a_reference_to_a_scrubbed_path_is_listed_scrubbed(tmp_path):
    from bench.tests.test_b2_s9_harvest import scrub_for
    p = put(tmp_path / "b2opuser" / "odd.bin", b"o\n")
    unrec = H.Unrecognised()
    unrec.files["evidence:r/b2opuser/odd.bin"] = p
    unrec.refs.append(dict(reference="leg:b2opuser/rows.jsonl:1 artifact", source="evidence:r/b2opuser/odd.bin",
                           sha256_matches=True))
    scrub = scrub_for(tmp_path)
    recs = unrec.records(scrub) + unrec.ref_records(scrub)
    assert len(recs) == 2 and all("b2opuser" not in json.dumps(r) for r in recs)
    assert recs[0]["source"].endswith("/odd.bin") and recs[1]["sha256_matches"] is True


@pytest.mark.parametrize("damage", ["missing", "other-bytes", "no-file-sha", "not-a-dict", "symlink"])
def test_h5_a_superseding_leg_json_without_its_kept_original_refuses(tmp_path, damage):
    """v1.1 H5: a `leg.json` carrying the C384 supersession publishes only with a kept original that exists, is a regular file,
    hashes to `superseded_file_sha256` and verifies its own self-hash."""
    w = World(tmp_path)
    original = (w.root / "leg.json").read_bytes()
    kept = w.root / H.C384_SUPERSEDED
    if damage == "missing":
        superseding(w, original)
    elif damage == "other-bytes":                    # a sealed, self-hash-valid record, but not the original's bytes
        old = json.loads(original)
        kept.write_text(json.dumps(seal(dict({k: v for k, v in old.items() if k != "sha256"}, state="INVALID")), indent=1) + "\n")
        superseding(w, original)
    elif damage == "no-file-sha":
        kept.write_bytes(original)
        superseding(w, original, superseded_file_sha256=None)
    elif damage == "not-a-dict":
        kept.write_bytes(original)
        old = json.loads(original)
        (w.root / "leg.json").write_text(json.dumps(seal(dict({k: v for k, v in old.items() if k != "sha256"}, c384="C384"))))
    else:
        (w.wd / "elsewhere").mkdir(parents=True, exist_ok=True)
        target = put(w.wd / "elsewhere" / "orig.json", original)
        os.symlink(target, kept)
        superseding(w, original)
    with pytest.raises(H.HarvestError, match=H.C384_SUPERSEDED.replace(".", r"\.")):
        w.harvest()
    nothing_published(w)


def test_h5_the_supersession_link_check_passes_with_the_kept_original(tmp_path):
    w = World(tmp_path)
    original = (w.root / "leg.json").read_bytes()
    (w.root / H.C384_SUPERSEDED).write_bytes(original)
    superseding(w, original)
    doc = w.harvest()
    assert entry(doc, f"leg:{H.C384_SUPERSEDED}")["sha256"] == sha(original)
