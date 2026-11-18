"""S26-P15: B8 refused A7 after a labelled rerun (`wave2/run/sequence.json names 2 pair records for pilot`). The sequencer records a
pair per attempt; the real M76 Wave 2 reran the X pilot (an AC dropout made a1 speed-invalid) and recorded `pilot__n16-a1__x-a1`
and `pilot__n16-a1__x-a2`. B8 takes the pair record whose attempts are, per arm, the highest-numbered attempt of that leg in
`sequence.json`'s legs; exactly one must match; the others are reported as superseded."""
import json
import shutil

import pytest

from bench import p426_verify as V
from bench.tests.p613.a7world import dumps, sealed, sha_bytes
from bench.tests.test_m76_b3_impl_a7 import KVWorld, pairs_by


def _rerun(w, arm="x", session="pilot", record=True, latest_record=True):
    """Copy `<arm>-<session>.a1` to `.a2` (attempt 2 in its own records), add the leg attempt and (optionally) its pair record."""
    wave = w.root / "wave2"
    a1, a2 = wave / f"tg1-m76-{arm}-{session}.a1", wave / f"tg1-m76-{arm}-{session}.a2"
    shutil.copytree(a1, a2)
    for name in ("HARVEST.json", "leg.json"):
        doc = json.loads((a2 / name).read_text())
        doc.pop("sha256", None)
        doc["attempt"] = 2
        (a2 / name).write_text(dumps(sealed(doc)))
    seq_path = wave / "run" / "sequence.json"
    seq = json.loads(seq_path.read_text())
    seq["legs"].append(dict(leg=f"tg1-m76-{arm}-{session}", attempt=2, state="VALID"))
    if record:
        old = next(p for p in seq["pairs"] if p["pair"] == session)
        new = dict(old, **{arm: f"tg1-m76-{arm}-{session}.a2"}, dossier=f"pairs/{session}__n16-a1__x-a2.json")
        d1 = json.loads((wave / old["dossier"]).read_text())
        d1.pop("sha256", None)
        d1["arms"][arm] = dict(d1["arms"][arm], attempt=f"tg1-m76-{arm}-{session}.a2",
                               harvest_sha256=sha_bytes((a2 / "HARVEST.json").read_bytes()))
        (wave / new["dossier"]).write_text(dumps(sealed(d1)))
        seq["pairs"].append(new if latest_record else dict(old))
    seq_path.write_text(dumps(seq))
    return seq


def test_a_rerun_session_reads_the_latest_attempt_pair_and_reports_the_superseded_one(tmp_path):
    """[FIX] the real shape: pilot recorded twice (x a1, x a2); B8 reads the pair of the latest attempts and names a1 superseded."""
    w = KVWorld(tmp_path)
    _rerun(w)
    b8 = V.verify_a7_kv(w.root, ("n16", "x"))
    pilot = pairs_by(b8)["pilot"]
    assert pilot["attempts"] == {"n16": "tg1-m76-n16-pilot.a1", "x": "tg1-m76-x-pilot.a2"}
    assert pilot["superseded"] == [{"n16": "tg1-m76-n16-pilot.a1", "x": "tg1-m76-x-pilot.a1"}]
    for s in ("s1", "s2", "s3"):
        assert pairs_by(b8)[s]["accepted"] and "superseded" not in pairs_by(b8)[s]


def test_two_records_of_the_same_latest_attempts_refuse(tmp_path):
    """[INV] a duplicated record of the latest attempts is ambiguous: refuse."""
    w = KVWorld(tmp_path)
    seq_path = w.root / "wave2" / "run" / "sequence.json"
    seq = json.loads(seq_path.read_text())
    seq["pairs"].append(dict(next(p for p in seq["pairs"] if p["pair"] == "s1")))
    seq_path.write_text(dumps(seq))
    with pytest.raises(V.RefusalError, match="s1"):
        V.verify_a7_kv(w.root, ("n16", "x"))


def test_a_rerun_without_a_pair_record_of_the_latest_attempts_refuses(tmp_path):
    """[INV] the legs say x pilot ran twice, but no pair record names attempt 2: the latest pair is missing — refuse, never fall back."""
    w = KVWorld(tmp_path)
    _rerun(w, record=False)
    with pytest.raises(V.RefusalError, match="pilot"):
        V.verify_a7_kv(w.root, ("n16", "x"))


def test_a_single_record_per_session_is_unchanged(tmp_path):
    """[INV] no rerun: every session has one record and B8's output is the pre-fix shape (no `superseded` key)."""
    w = KVWorld(tmp_path)
    b8 = V.verify_a7_kv(w.root, ("n16", "x"))
    assert all("superseded" not in p for p in b8["pairs"])
