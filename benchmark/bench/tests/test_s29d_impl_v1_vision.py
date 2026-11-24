"""S29 main-small V1 (implementer tests): the KV `vision` rubric (member A3) asks for accuracy / coverage / precision against the
image and names no reference captions; a new export binds the new text (its own `rubric_sha256`); the frozen stage-3 A3 record
keeps verifying against the rubric text and sha it was frozen with."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import p426_panel as P

PANEL = Path(__file__).resolve().parents[2] / "results" / "m76" / "panel"
A3_FROZEN_SHA = "5987d169d9084cc3b980be1069e17697d60b84e02dbc7fcae8d0d2aed0ea97b8"     # FROZEN.json rubric_sha256 at f8851c108


def _kv_vision_text():
    return P.RUBRICS[P.kv_rubric("A3")]


def test_v1_the_kv_vision_rubric_names_no_reference_captions():
    text = _kv_vision_text().lower()
    assert "caption" not in text and "reference" not in text
    for ask in ("accuracy", "coverage", "precision", "image"):
        assert ask in text


def test_v1_a_new_a3_export_binds_the_new_text_by_its_own_sha():
    rubric = P.kv_rubric("A3")
    assert P.rubric_sha(rubric) == hashlib.sha256(_kv_vision_text().encode()).hexdigest()
    assert P.rubric_sha(rubric) != A3_FROZEN_SHA


def test_v1_the_frozen_a3_record_still_verifies_against_its_own_rubric():
    doc = json.loads((PANEL / "A3" / "FROZEN.json").read_text())
    assert doc["rubric_sha256"] == A3_FROZEN_SHA
    assert hashlib.sha256(P.RUBRICS[doc["rubric"]].encode()).hexdigest() == A3_FROZEN_SHA    # its own text is still there
    assert "reference captions" in P.RUBRICS[doc["rubric"]]                                  # unchanged, as frozen
    got = P.kv_check_frozen(PANEL / "A3")
    assert got["rubric_sha256"] == A3_FROZEN_SHA
    _, rows, _ = P.kv_ingest(PANEL / "A3")                              # its verdicts stay bound to the frozen sha
    assert rows and {r["prompt_sha"] for r in rows} == {A3_FROZEN_SHA}


def test_v1_the_other_frozen_kv_members_still_verify():
    for member in ("A1", "A2", "A4", "A5", "A7-s1", "A7-s2", "A7-s3"):
        assert P.kv_check_frozen(PANEL / member)["member"] == member


A3_FROZEN_JSON_SHA = "9ff014b5f52a7d25e1ef24d70f2e51933353b54fed8a0d279be33409944e7d06"   # FROZEN.json sha256 at f8851c108


def _a3_copy(tmp_path):
    import shutil

    out = tmp_path / "A3"
    shutil.copytree(PANEL / "A3", out)
    return out


def test_v1_fix1_the_old_pair_is_bound_to_the_exact_frozen_a3_record(tmp_path):
    assert P._sha(PANEL / "A3" / P.FROZEN_NAME) == A3_FROZEN_JSON_SHA
    assert P.kv_check_frozen(_a3_copy(tmp_path))["rubric"] == "vision"          # the same bytes verify wherever they lie
    assert P._kv_rubric_ok("A3", "vision", A3_FROZEN_SHA, A3_FROZEN_JSON_SHA)
    assert not P._kv_rubric_ok("A3", "vision", A3_FROZEN_SHA)                     # no record identity: refused
    assert not P._kv_rubric_ok("A3", "vision", A3_FROZEN_SHA, "0" * 64)
    assert not P._kv_rubric_ok("A1", "vision", A3_FROZEN_SHA, A3_FROZEN_JSON_SHA)  # never another member


def test_v1_fix1_a_new_a3_record_carrying_the_old_pair_refuses(tmp_path):
    from bench.p426_verify import RefusalError

    out = _a3_copy(tmp_path)
    doc = json.loads((out / P.FROZEN_NAME).read_text())
    assert (doc["rubric"], doc["rubric_sha256"]) == ("vision", A3_FROZEN_SHA)
    doc["note"] = "a new A3 record"                                               # another record, same (vision, sha) pair
    (out / P.FROZEN_NAME).write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n")
    with pytest.raises(RefusalError, match="rubric is not this member's"):
        P.kv_check_frozen(out)
