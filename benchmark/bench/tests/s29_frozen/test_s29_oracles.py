"""S29 frozen tests: the instruments the other S29 modules search records with, checked against known positives and negatives (a
test that searches a record for a change, a listing or a supersession must be shown to find one that is there and miss one that is
not, with field names it has never seen)."""
from __future__ import annotations

import hashlib

from bench.tests.s29_frozen import s29_support as S
from bench.tests.s29_frozen import test_s29_harvest as HV


def test_inv_containers_separates_two_changes_whatever_the_field_names():
    doc = {"state": "VALID", "launch": {"x": [S.ADDED]}, "end": {"y": [S.JEST]}}
    assert S.containers(doc, S.JDK) == {("launch", "x")} and S.containers(doc, "jest") == {("end", "y")}
    both = {"state": "VALID", "note": f"{S.ADDED}; {S.JEST}"}
    assert S.containers(both, S.JDK) & S.containers(both, "jest")            # one field holding both is detected


def test_inv_the_listing_oracle_finds_a_listed_file_and_misses_an_unlisted_one():
    data = b"some bytes\n"
    doc = {"files": [{"source": "leg:leg.json", "sha256": "0" * 64}],
           "unrecognised": [{"where": "evidence:r/a.grades/seq-0001/x.dat", "bytes": len(data)}]}
    assert HV.listing(doc, "x.dat", data)
    assert not HV.listing(doc, "x.dat", b"other bytes\n")                      # another size
    leaky = {"unrecognised": [{"where": "x.dat", "bytes": len(data), "digest": hashlib.sha256(data).hexdigest()}]}
    assert not HV.listing(leaky, "x.dat", data)                                # v1.1: a digest of the bytes is refused
    assert not HV.listing(doc, "y.dat", data)                                  # another path
    assert not HV.listing({"files": doc["files"]}, "x.dat", data)


def test_inv_the_published_copies_oracle_finds_a_copy(tmp_path):
    from bench.tests import test_b2_s9_harvest as T
    w = T.World(tmp_path)
    T.put(w.stage / "somewhere" / "copy.bin", b"payload")
    assert HV.published_copies(w, b"payload") and not HV.published_copies(w, b"absent")
