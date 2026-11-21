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


def _rerun(w, arm="x", session="pilot", record=True, latest_record=True, a1_speed_valid=False, reason="AC dropout in a1's window"):
    """Copy `<arm>-<session>.a1` to `.a2` (attempt 2 in its own records), add the leg attempt, (optionally) its pair record and the
    sequencer's `reruns` entry; a1's leg.json gets `speed_valid` = `a1_speed_valid` (the real run: False, an AC dropout)."""
    wave = w.root / "wave2"
    a1, a2 = wave / f"tg1-m76-{arm}-{session}.a1", wave / f"tg1-m76-{arm}-{session}.a2"
    leg1 = json.loads((a1 / "leg.json").read_text())
    leg1.pop("sha256", None)
    leg1.update(speed_valid=a1_speed_valid, speed_reason="ok" if a1_speed_valid else "on-battery interval(s) in the leg window: 1")
    (a1 / "leg.json").write_text(dumps(sealed(leg1)))
    shutil.copytree(a1, a2)
    for name in ("HARVEST.json", "leg.json"):
        doc = json.loads((a2 / name).read_text())
        doc.pop("sha256", None)
        doc["attempt"] = 2
        if name == "HARVEST.json":       # B4b-2 §3.3: a2's harvest publishes a2's own files (as the real rerun's did)
            for f in doc.get("files") or []:
                f["published"] = f["published"].replace(f"/{a1.name}/", f"/{a2.name}/")
        (a2 / name).write_text(dumps(sealed(doc)))
    seq_path = wave / "run" / "sequence.json"
    seq = json.loads(seq_path.read_text())
    seq["legs"].append(dict(leg=f"tg1-m76-{arm}-{session}", attempt=2, state="VALID"))
    if reason is not None:
        seq.setdefault("reruns", []).append(dict(leg=f"tg1-m76-{arm}-{session}", attempt=2, reason=reason, at="2026-11-18T01:20:53Z"))
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


# ---- S26-P15b (side-agent note): a rerun may supersede only an attempt that was not clean, and only with a recorded reason
def test_a_clean_first_attempt_cannot_be_superseded(tmp_path):
    """[FIX] a VALID, speed-valid a1 replaced by a2: the session pair is rejected with the reason, never silently replaced."""
    w = KVWorld(tmp_path)
    _rerun(w, session="s1", a1_speed_valid=True)
    s1 = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]
    assert not s1["accepted"] and any("superseded a clean attempt" in r for r in s1["reasons"])


def test_a_rerun_without_a_recorded_reason_cannot_supersede(tmp_path):
    """[FIX] a speed-invalid a1 replaced by a2 with no `reruns` reason: rejected."""
    w = KVWorld(tmp_path)
    _rerun(w, session="s1", reason=None)
    s1 = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]
    assert not s1["accepted"] and any("no recorded rerun reason" in r for r in s1["reasons"])


def test_the_real_rerun_shape_is_accepted_with_its_reason(tmp_path):
    """[INV] the real Wave 2: a1 speed-invalid (AC dropout), a2 with its recorded reason: accepted."""
    w = KVWorld(tmp_path)
    _rerun(w, session="s1")
    s1 = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]
    assert s1["accepted"], s1["reasons"]


# ---- S26-P15b cold read r1 (Sol P1–P3): fail closed on a tampered / missing earlier record; independent of the pair records; per hop
def test_a_tampered_unsealed_earlier_attempt_cannot_be_superseded(tmp_path):
    """[FIX] Sol P1: a1's leg.json edited to speed-invalid without its self-hash: rejected (fail closed)."""
    w = KVWorld(tmp_path)
    _rerun(w, session="s1", a1_speed_valid=True)
    p = w.root / "wave2" / "tg1-m76-x-s1.a1" / "leg.json"
    doc = json.loads(p.read_text())
    doc["speed_valid"] = False                                  # the seal no longer verifies
    p.write_text(dumps(doc))
    s1 = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]
    assert not s1["accepted"] and any("not self-hash-verified" in r for r in s1["reasons"])


def test_removing_the_old_pair_record_does_not_hide_a_clean_attempt(tmp_path):
    """[FIX] Sol P2: a clean a1 replaced by a2, the old pair record removed: still rejected (anchored on the chosen attempt)."""
    w = KVWorld(tmp_path)
    seq = _rerun(w, session="s1", a1_speed_valid=True)
    seq["pairs"] = [p for p in seq["pairs"] if not (p["pair"] == "s1" and p["x"].endswith(".a1"))]
    (w.root / "wave2" / "run" / "sequence.json").write_text(dumps(seq))
    s1 = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]
    assert not s1["accepted"] and any("superseded a clean attempt" in r for r in s1["reasons"])


def test_every_hop_of_a_multi_rerun_needs_its_reason(tmp_path):
    """[FIX] Sol P3: speed-invalid a1 -> unlabelled a2 -> labelled a3: rejected for the missing a2 reason."""
    w = KVWorld(tmp_path)
    _rerun(w, session="s1", reason=None)                        # a2 with no reason
    wave = w.root / "wave2"
    a2, a3 = wave / "tg1-m76-x-s1.a2", wave / "tg1-m76-x-s1.a3"
    leg2 = json.loads((a2 / "leg.json").read_text())
    leg2.pop("sha256", None)
    leg2.update(speed_valid=False)
    (a2 / "leg.json").write_text(dumps(sealed(leg2)))
    shutil.copytree(a2, a3)
    for name in ("HARVEST.json", "leg.json"):
        doc = json.loads((a3 / name).read_text())
        doc.pop("sha256", None)
        doc["attempt"] = 3
        if name == "leg.json":
            doc["speed_valid"] = True
        (a3 / name).write_text(dumps(sealed(doc)))
    seq_path = wave / "run" / "sequence.json"
    seq = json.loads(seq_path.read_text())
    seq["legs"].append(dict(leg="tg1-m76-x-s1", attempt=3, state="VALID"))
    seq["reruns"] = [dict(leg="tg1-m76-x-s1", attempt=3, reason="labelled", at="t")]
    old = next(p for p in seq["pairs"] if p["pair"] == "s1" and p["x"].endswith(".a2"))
    d = json.loads((wave / old["dossier"]).read_text())
    d.pop("sha256", None)
    d["arms"]["x"] = dict(d["arms"]["x"], attempt="tg1-m76-x-s1.a3", harvest_sha256=sha_bytes((a3 / "HARVEST.json").read_bytes()))
    (wave / "pairs" / "s1__n16-a1__x-a3.json").write_text(dumps(sealed(d)))
    seq["pairs"].append(dict(old, x="tg1-m76-x-s1.a3", dossier="pairs/s1__n16-a1__x-a3.json"))
    seq_path.write_text(dumps(seq))
    s1 = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]
    assert not s1["accepted"] and any("tg1-m76-x-s1.a2 has no recorded rerun reason" in r for r in s1["reasons"])


# ---- S26-P15b verify r2 (Sol P4–P6): confined, identity-bound earlier record; a textual reason
def test_an_earlier_attempt_record_copied_from_another_leg_cannot_stand_in(tmp_path):
    """[FIX] Sol P5: a1's leg.json replaced by a sealed INVALID record of ANOTHER leg: rejected (identity-bound)."""
    w = KVWorld(tmp_path)
    _rerun(w, session="s1", a1_speed_valid=True)
    wave = w.root / "wave2"
    other = json.loads((wave / "tg1-m76-n16-s2.a1" / "leg.json").read_text())
    other.pop("sha256", None)
    other["state"] = "INVALID"
    (wave / "tg1-m76-x-s1.a1" / "leg.json").write_text(dumps(sealed(other)))
    s1 = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]
    assert not s1["accepted"] and any("is not the record of" in r for r in s1["reasons"])


def test_an_earlier_attempt_outside_wave2_through_a_symlink_is_refused(tmp_path):
    """[FIX] Sol P4: x-s1.a1 a symlink to an outside directory holding a sealed speed-invalid leg.json: rejected."""
    w = KVWorld(tmp_path)
    _rerun(w, session="s1")
    wave = w.root / "wave2"
    outside = tmp_path / "outside" / "tg1-m76-x-s1.a1"
    shutil.copytree(wave / "tg1-m76-x-s1.a1", outside)
    shutil.rmtree(wave / "tg1-m76-x-s1.a1")
    (wave / "tg1-m76-x-s1.a1").symlink_to(outside)
    s1 = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]
    assert not s1["accepted"] and any("outside wave2" in r or "not self-hash-verified" in r for r in s1["reasons"])


def test_a_non_text_rerun_reason_does_not_count(tmp_path):
    """[FIX] Sol P6: a `reruns` reason that is not a non-empty string: rejected."""
    w = KVWorld(tmp_path)
    seq = _rerun(w, session="s1")
    seq["reruns"][-1]["reason"] = {"note": "x"}
    (w.root / "wave2" / "run" / "sequence.json").write_text(dumps(seq))
    s1 = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]
    assert not s1["accepted"] and any("no recorded rerun reason" in r for r in s1["reasons"])
