"""S29 frozen tests, the Wave 2 harvest (spec docs/specs/s29-record-not-block.md P6a, P6b; S29-P6: the 34-byte grader `execute.marker`
refused a whole leg).

P6a: a `<step>.marker` directly in a tg2 `<item>.grades/seq-NNNN/` is evidence, harvested and scrubbed like the other grade outputs,
at that boundary only. P6b: a regular file no rule matches is NOT copied, is listed in the harvest's own record (source path in
portable scrubbed form and size, NOTHING derived from its unscanned bytes: no digest; spec v1.1) and logged, and the harvest goes on;
a reference to such a file is listed with whether the recorded digest matches, not refused. Every OTHER
refusal is unchanged (PII scrub / quarantine, symlink outside a final tree, non-regular file, self-hash, missing `leg.json`,
references outside the inventoried roots).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant (a refusal that stays); [NEW] new behaviour.
Fixtures: `test_b2_s9_harvest.World` (a leg root as the chain / probe / sequencer leave it, with its run and evidence directories
under `$STACK_WORKDIR`, real `Scrub`, the real `harvest_wave2`), plus the evidence layout of the recorded zebra-puzzle grade
directory: `javascript__zebra-puzzle.grades/seq-0002/{execute.marker, execute.out, execute-readback.out}` and a row of the leg that
names the marker (the a3 refusal: "referenced file ... is missing").

ASSUMPTIONS (mechanism free): "listed" = some record inside `HARVEST.json` (any field names) mentions the file's portable path and
carries its byte size (v1.1: and no digest of the file's bytes appears in `HARVEST.json`, except where a row reference legitimately
records one: tests with a reference skip that check), and `HARVEST.json` stays self-hashed; "a reference is listed" = some record other than the
document root mentions both the referencing file and the unrecognised file; "not copied" = no file below the main / evidence
destinations holds the bytes."""
from __future__ import annotations

import json
import os

import pytest

from bench import p426_harvest as H
from bench.tests import test_b2_s9_harvest as T
from bench.tests.s29_frozen import s29_support as S

MARKER = b"TG2_RUNNER_START 0255500343d02559\n"                # the recorded 34-byte marker
SEQ = "javascript__zebra-puzzle.grades/seq-0002"
OPERATOR = "op.erator@corp-mail.example"


def put_marker(w, rel=f"{SEQ}/execute.marker", data=MARKER):
    """The grade directory of the recorded tg2 item (marker, stdout, readback) in the leg's evidence directory."""
    T.put(w.ev / f"{SEQ}/execute.out", "ok 1 - zebra\n")
    T.put(w.ev / f"{SEQ}/execute-readback.out", "ok\n")
    return T.put(w.ev / rel, data)


def reference(w, path, *, key="grade_marker"):
    """The row of the leg names `path` (portable path + sha256 of its bytes) as an artifact, as the a3's row line 14 did."""
    rows = w.root / "s1" / "rows.jsonl"
    docs = [json.loads(line) for line in rows.read_text().splitlines() if line.strip()]
    docs[0][key] = dict(path=w.p(path), sha256=T.sha(path.read_bytes()))
    rows.write_text("".join(json.dumps(d) + "\n" for d in docs))


def nodes_mentioning(doc, needle):
    return [n for n in S.dict_nodes(doc) if n is not doc and any(needle in t for _, t in S.leaves(n))]


def listing(doc, tail, data, *, digest_free=True):
    """The record(s) of `doc` that list the file `tail` with its byte size (key names are free). v1.1: no value of the record is the
    sha256 of the file's bytes, and (`digest_free`; off for tests whose row legitimately records a digest) that digest is nowhere in
    the document."""
    sha, size = T.sha(data), len(data)
    out = []
    for n in nodes_mentioning(doc, tail):
        values = list(n.values())
        if size in values and sha not in values:
            out.append(n)
    if digest_free and out and sha in json.dumps(doc):
        return []
    return out


def published_copies(w, data):
    """Every file under the harvest's main / evidence destinations (and the review file dir) holding exactly `data`."""
    hits = []
    for base in (w.main, w.stage):
        if base.exists():
            hits += [p for p in base.rglob("*") if p.is_file() and p.read_bytes() == data]
    return hits


def harvest_or_none(w, **kw):
    try:
        return w.harvest(**kw)
    except H.HarvestError as exc:
        return exc


# ---------------------------------------------------------------------------------------------------- P6a: the marker
def test_fix_p6a_the_grader_marker_in_a_tg2_grade_dir_is_evidence_and_the_leg_harvests(tmp_path):
    """[FIX] the a3 refusal: `<item>.grades/seq-0002/execute.marker` (+ its row's reference) -> the harvest succeeds; the marker is an
    EVIDENCE file of its evidence directory, published byte-identical (nothing in it to scrub), its record carries its sha256."""
    w = T.World(tmp_path)
    marker = put_marker(w)
    reference(w, marker)
    doc = w.harvest()
    src = f"evidence:{T.RUN_ID}/{SEQ}/execute.marker"
    e = T.entry(doc, src)
    assert e["destination"] == "evidence" and e["sha256"] == T.sha(MARKER)
    pub = w.stage / e["published"]
    assert pub.read_bytes() == MARKER and e["published_sha256"] == T.sha(MARKER)
    assert T.canon_sha(doc) == doc["sha256"] and w.harvest_json() == doc
    siblings = {f["source"] for f in doc["files"]}
    assert f"evidence:{T.RUN_ID}/{SEQ}/execute.out" in siblings and f"evidence:{T.RUN_ID}/{SEQ}/execute-readback.out" in siblings


def test_fix_p6a_a_marker_is_scrubbed_like_the_other_grade_outputs(tmp_path):
    """[FIX] the published copy of a marker that names a box path carries the portable form, not the path; the recorded sha256 is
    the raw file's (the row's reference verifies against it)."""
    w = T.World(tmp_path)
    data = f"TG2_RUNNER_START cwd={w.wd}/tg2/x\n".encode()
    marker = put_marker(w, data=data)
    reference(w, marker)
    doc = w.harvest()
    e = T.entry(doc, f"evidence:{T.RUN_ID}/{SEQ}/execute.marker")
    published = (w.stage / e["published"]).read_bytes()
    assert str(w.wd).encode() not in published and b"$STACK_WORKDIR/tg2/x" in published
    assert e["sha256"] == T.sha(data)


def test_fix_p6a_a_marker_with_the_operators_address_is_quarantined_not_published(tmp_path):
    """[FIX] "harvested and scrubbed like the other grade outputs": the secret / address gate applies to it: a marker carrying the
    operator's address refuses the harvest as a QUARANTINE (it is a harvested file now, not an unrecognised one), nothing published."""
    w = T.World(tmp_path)
    marker = put_marker(w, data=f"TG2_RUNNER_START {OPERATOR}\n".encode())
    reference(w, marker)
    with pytest.raises(H.HarvestError, match="quarantined"):
        w.harvest(emails=(OPERATOR,))
    T.nothing_published(w)


def test_fix_p6a_a_marker_with_a_credential_is_quarantined_not_published(tmp_path):
    w = T.World(tmp_path)
    marker = put_marker(w, data=f"TG2_RUNNER_START {T.FAKE_HF}\n".encode())
    reference(w, marker)
    with pytest.raises(H.HarvestError, match="quarantined"):
        w.harvest()
    T.nothing_published(w)


@pytest.mark.parametrize("rel", [
    "javascript__zebra-puzzle.grades/execute.marker",                    # not inside a seq-NNNN directory
    "javascript__zebra-puzzle.grades/seq-0002/deeper/execute.marker",    # one level too deep
    "javascript__zebra-puzzle.grades/seq-2/execute.marker",              # not seq-<4 digits>
    "javascript__zebra-puzzle.grades/seq-0002x/execute.marker",
    "execute.marker",                                                    # flat in the evidence directory
    "zebra-puzzle.grades/seq-0002/execute.marker",                       # not a tg2 language's grade directory
    "javascript__zebra-puzzle/seq-0002/execute.marker",                  # not a `.grades` directory
], ids=["no-seq-dir", "too-deep", "seq-digits", "seq-suffix", "flat", "no-language", "no-grades-suffix"])
def test_fix_p6a_a_marker_is_evidence_only_directly_in_a_grade_seq_dir(tmp_path, rel):
    """[FIX] + P6b: "at that boundary only": a `.marker` anywhere else is not a recognised evidence file: the harvest goes on, the
    file is NOT copied and IS listed with its sha256 and size."""
    w = T.World(tmp_path)
    data = f"elsewhere {rel}\n".encode()
    T.put(w.ev / rel, data)
    doc = w.harvest()
    assert published_copies(w, data) == []
    assert listing(doc, rel, data), f"{rel} is not listed in HARVEST.json"
    assert not [f for f in doc["files"] if f["source"] == f"evidence:{T.RUN_ID}/{rel}" and f.get("published")]


def test_fix_p6a_a_marker_in_the_leg_root_is_not_evidence(tmp_path):
    """[FIX] `.marker` is a grade-dir rule: in a leg root (here a session directory) it is unrecognised: listed, not copied."""
    w = T.World(tmp_path)
    data = b"leg root marker\n"
    T.put(w.root / "s1" / "execute.marker", data)
    doc = w.harvest()
    assert published_copies(w, data) == []
    assert listing(doc, "s1/execute.marker", data)


# ---------------------------------------------------------------------------------------------------- P6b: unrecognised files
@pytest.mark.parametrize("where", ["leg", "evidence", "run"])
def test_fix_p6b_an_unrecognised_file_is_listed_not_copied_and_the_harvest_succeeds(tmp_path, where):
    """[FIX] the old pin "an unmatched file fails the harvest" (leg root, evidence directory, run directory) becomes: harvest
    succeeds; the file is listed (portable path, size, sha256) and never copied; HARVEST.json is still self-hashed, verifies on
    the idempotent second call, and the other files are harvested as before."""
    w = T.World(tmp_path)
    data = f"unrecognised bytes of the {where} root\n".encode()
    base = {"leg": w.root, "evidence": w.ev, "run": w.run}[where]
    T.put(base / "stray.unknown-kind", data)
    doc = w.harvest()
    assert T.canon_sha(doc) == doc["sha256"] and w.harvest_json() == doc
    assert listing(doc, "stray.unknown-kind", data), f"not listed with its size (and no digest): {doc}"
    assert published_copies(w, data) == []
    assert not any(f["source"].endswith("stray.unknown-kind") and f.get("published") for f in doc["files"])
    assert T.entry(doc, "leg:leg.json")["destination"] == "main"
    assert w.harvest() == doc                                          # a committed destination verifies: done, unchanged


def test_fix_p6b_the_listing_carries_no_box_path(tmp_path):
    """[FIX] "source path in portable form": no workdir / tmp path in the harvest record."""
    w = T.World(tmp_path)
    T.put(w.ev / "javascript__zebra-puzzle.grades/seq-0002/odd.dat", b"odd\n")
    doc = w.harvest()
    text = json.dumps(doc)
    assert "odd.dat" in text and str(w.wd) not in text and str(tmp_path) not in text


def test_fix_p6b_a_path_that_names_the_operator_account_is_scrubbed_in_the_listing(tmp_path):
    """[FIX] edge (assumption): the unrecognised file's path goes through the harvest's scrub like every path of the record; a
    directory named after the account would otherwise make `HARVEST.json` itself refuse as "not portable"."""
    w = T.World(tmp_path)
    T.put(w.root / "b2opuser" / "notes.dat", b"n\n")
    doc = w.harvest()
    assert "b2opuser" not in json.dumps(doc) and "notes.dat" in json.dumps(doc)


def test_fix_p6b_a_row_reference_to_an_unrecognised_file_is_listed_and_not_refused(tmp_path):
    """[FIX] the other half of the a3 refusal ("referenced file ... is missing"): the row names an unrecognised file by portable path
    and sha256 -> the harvest succeeds, the file is listed, and the reference (the row file naming it) is listed beside it."""
    w = T.World(tmp_path)
    data = b"a grader product no rule knows\n"
    path = T.put(w.ev / f"{SEQ}/execute.unknown", data)
    reference(w, path, key="grade_extra")
    doc = w.harvest()
    assert listing(doc, "execute.unknown", data, digest_free=False) and published_copies(w, data) == []
    both = [n for n in nodes_mentioning(doc, "execute.unknown") if any("rows.jsonl" in t for _, t in S.leaves(n))]
    assert both, "the reference from s1/rows.jsonl to the unrecognised file is not listed"


def test_fix_p6b_the_a3_leg_harvests_with_its_marker_and_a_second_unknown_file(tmp_path):
    """[FIX] the recorded a3 refusal as a whole: marker (recognised) + an unknown readback product, both referenced by the row."""
    w = T.World(tmp_path)
    marker = put_marker(w)
    extra = T.put(w.ev / f"{SEQ}/execute-readback.bin", b"\x00\x01binary readback\n")
    reference(w, marker)
    reference(w, extra, key="grade_readback")
    doc = w.harvest()
    assert T.entry(doc, f"evidence:{T.RUN_ID}/{SEQ}/execute.marker")["destination"] == "evidence"
    assert listing(doc, "execute-readback.bin", b"\x00\x01binary readback\n", digest_free=False)


# ---------------------------------------------------------------------------------------------------- every other refusal stays
def test_inv_a_reference_outside_the_inventoried_roots_still_refuses(tmp_path):
    """[INV] "references outside the inventoried roots" is unchanged."""
    w = T.World(tmp_path)
    outside = T.put(w.wd / "elsewhere" / "file.dat", b"outside every root\n")
    reference(w, outside, key="grade_extra")
    with pytest.raises(H.HarvestError, match="outside the inventoried roots"):
        w.harvest()
    T.nothing_published(w)


def test_inv_a_reference_to_a_file_that_does_not_exist_still_refuses(tmp_path):
    """[INV] (assumption: not the P6b case) a reference to a path that holds NO file at all is a real integrity fault: refused."""
    w = T.World(tmp_path)
    ghost = w.ev / f"{SEQ}/ghost.dat"
    rows = w.root / "s1" / "rows.jsonl"
    docs = [json.loads(line) for line in rows.read_text().splitlines() if line.strip()]
    docs[0]["grade_extra"] = dict(path=w.p(ghost), sha256="0" * 64)
    rows.write_text("".join(json.dumps(d) + "\n" for d in docs))
    with pytest.raises(H.HarvestError, match="ghost.dat"):
        w.harvest()
    T.nothing_published(w)


@pytest.mark.parametrize("stray", [False, True], ids=["alone", "beside-an-unrecognised-file"])
def test_inv_a_credential_in_a_recognised_file_still_quarantines_the_harvest(tmp_path, stray):
    """[INV] (alone) the quarantine refusal is unchanged; [FIX] (beside an unrecognised file) listing an unknown file is not a
    licence: the same refusal still happens, as a quarantine, with nothing published."""
    w = T.World(tmp_path)
    if stray:
        T.put(w.root / "stray.unknown-kind", b"x\n")
    T.put(w.ev / f"{SEQ}/execute.out", f"token {T.FAKE_HF}\n".encode())
    with pytest.raises(H.HarvestError, match="quarantined"):
        w.harvest()
    T.nothing_published(w)


@pytest.mark.parametrize("stray", [False, True], ids=["alone", "beside-an-unrecognised-file"])
def test_inv_a_main_record_the_scrub_would_change_still_refuses(tmp_path, stray):
    """[INV] PII scrub: a main record carrying a box path is not portable at creation: refused, with or without an unrecognised
    file in the same leg ([FIX] for the second: the unknown file must not turn the refusal into a success)."""
    w = T.World(tmp_path)
    T.pjson(w.root / "log_bounds.json", dict(files=[], created="t", finalized="t", note=str(w.wd / "x")))
    if stray:
        T.put(w.root / "stray.unknown-kind", b"x\n")
    with pytest.raises(H.HarvestError, match="log_bounds.json"):
        w.harvest()
    T.nothing_published(w)


def test_inv_a_symlink_outside_a_final_tree_still_refuses_even_when_it_is_named_like_a_marker(tmp_path):
    """[INV] symlinks are refused before any rule: a link called `execute.marker` in a grade dir is never followed or copied."""
    w = T.World(tmp_path)
    secret = tmp_path / "outside.txt"
    secret.write_text("SENTINEL-NEVER-READ")
    (w.ev / SEQ).mkdir(parents=True)
    (w.ev / SEQ / "execute.marker").symlink_to(secret)
    with pytest.raises(H.HarvestError, match="symlink"):
        w.harvest()
    T.nothing_published(w)
    assert not published_copies(w, b"SENTINEL-NEVER-READ")


def test_inv_a_non_regular_file_still_refuses(tmp_path):
    """[INV] a FIFO (never opened) in the leg root is refused as not a regular file, not listed as unrecognised."""
    w = T.World(tmp_path)
    os.mkfifo(w.root / "pipe.unknown-kind")
    with pytest.raises(H.HarvestError, match="not a regular file"):
        w.harvest()
    T.nothing_published(w)


@pytest.mark.parametrize("what", ["wrong", "missing"])
def test_inv_an_immutable_record_without_a_valid_self_hash_still_refuses(tmp_path, what):
    """[INV] self-hash: `leg.json` with a wrong or missing `sha256` refuses."""
    w = T.World(tmp_path)
    doc = json.loads((w.root / "leg.json").read_text())
    doc = {k: v for k, v in doc.items() if k != "sha256"} if what == "missing" else dict(doc, sha256="f" * 64)
    (w.root / "leg.json").write_text(json.dumps(doc))
    T.put(w.root / "stray.unknown-kind", b"x\n")
    with pytest.raises(H.HarvestError, match="leg.json"):
        w.harvest()
    T.nothing_published(w)


def test_inv_a_leg_without_leg_json_still_refuses(tmp_path):
    w = T.World(tmp_path)
    (w.root / "leg.json").unlink()
    with pytest.raises(H.HarvestError, match="leg.json"):
        w.harvest()
    T.nothing_published(w)


def test_inv_the_marker_rule_does_not_loosen_the_other_grade_outputs(tmp_path):
    """[INV] the existing grade-dir rule is unchanged: `.out` / `.err` / `.inspect` files directly in `seq-NNNN` are still evidence
    (copied), and a file with another suffix beside the marker is unrecognised (listed, not copied)."""
    w = T.World(tmp_path)
    put_marker(w)
    data = b"neither\n"
    T.put(w.ev / f"{SEQ}/execute.neither", data)
    doc = w.harvest()
    assert T.entry(doc, f"evidence:{T.RUN_ID}/{SEQ}/execute.out")["destination"] == "evidence"
    assert T.entry(doc, f"evidence:{T.RUN_ID}/{SEQ}/execute.marker")["destination"] == "evidence"
    assert published_copies(w, data) == [] and listing(doc, "execute.neither", data)
