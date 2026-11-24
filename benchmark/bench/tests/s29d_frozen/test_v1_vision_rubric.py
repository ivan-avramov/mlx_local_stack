"""S29 main-small V1 (spec `docs/specs/s29-main-small.md`): the KV `vision` rubric asks for accuracy / coverage / precision against the
image and names no reference captions; the frozen M76 A3 records keep verifying against the rubric text and sha they were frozen with;
a new export binds the new text under its own `rubric_sha256`.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from bench import p426_panel as P

A3 = Path(__file__).resolve().parents[3] / "results" / "m76" / "panel" / "A3"
# The rubric text A3 was frozen with (baseline f8851c108), pinned verbatim: the frozen record is checked against this, not the code.
OLD_VISION = (
    "You are judging two descriptions of the SAME image (the image file is named in the prompt; look at it) against the "
    "human reference captions given in the prompt. Judge ONLY: accuracy (nothing described that is not in the image), "
    "coverage of what matters in the image, and precision. Penalize hallucinated objects, attributes or text heavily. "
    "Ignore length except where it hurts precision. The descriptions are labeled A and B; all identifying information "
    "has been removed. "
    'Reply with ONLY a JSON object: {"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}. No prose outside the JSON.'
)
OLD_SHA = hashlib.sha256(OLD_VISION.encode()).hexdigest()


def KV_KEY():
    """The rubric key the KV A3 member resolves to (the spec's 'KV vision rubric'; the key's name is free)."""
    return P.kv_rubric("A3")


def NEW_TEXT():
    return P.RUBRICS[KV_KEY()]


def NEW_SHA():
    return P.rubric_sha(KV_KEY())


def _frozen():
    return json.loads((A3 / "FROZEN.json").read_text())


# ------------------------------------------------------------------ the new text
def test_v1_the_vision_rubric_names_no_reference_captions():
    text = NEW_TEXT().lower()
    assert "caption" not in text
    assert "reference" not in text
    assert "human" not in text


def test_v1_the_vision_rubric_asks_for_accuracy_coverage_precision_against_the_image():
    text = NEW_TEXT().lower()
    for word in ("accuracy", "coverage", "precision", "image"):
        assert word in text
    assert "hallucinat" in text                                   # the penalty the old text carried survives


def test_v1_the_vision_rubric_keeps_the_reply_contract():
    text = NEW_TEXT()
    assert '{"choice": "A"|"B"|"tie"' in text and "No prose outside the JSON" in text


def test_v1_the_vision_rubric_changed_and_its_sha_follows_the_text():
    assert NEW_TEXT() != OLD_VISION
    assert NEW_SHA() == hashlib.sha256(NEW_TEXT().encode()).hexdigest() != OLD_SHA


def test_v1_the_other_rubrics_are_unchanged():
    for name in ("reasoning", "code", "cjudge"):
        assert P.rubric_sha(name) == hashlib.sha256(P.RUBRICS[name].encode()).hexdigest()
    assert "reference captions" not in P.RUBRICS["reasoning"] + P.RUBRICS["code"] + P.RUBRICS["cjudge"]


# ------------------------------------------------------------------ the frozen records
def test_v1_the_frozen_a3_record_carries_the_old_rubric_sha():
    doc = _frozen()
    assert doc["member"] == "A3" and doc["rubric"] == "vision"
    assert doc["rubric_sha256"] == OLD_SHA                        # frozen with the old text, whatever the code says now


def test_v1_the_frozen_a3_packets_still_carry_the_old_text_under_the_old_sha():
    rows = [json.loads(ln) for ln in (A3 / "manifest.jsonl").read_text().splitlines() if ln.strip()]
    assert len(rows) == _frozen()["counts"]["packet_files"] > 0
    assert {r["prompt_sha"] for r in rows} == {OLD_SHA}
    for r in rows:
        assert OLD_VISION in (A3 / r["path"]).read_text()


def test_v1_the_frozen_a3_record_still_verifies():
    doc = P.kv_check_frozen(A3)                                    # files unchanged, manifest consistent, rubric / sha as frozen
    assert doc["rubric_sha256"] == OLD_SHA


def test_v1_the_frozen_a3_files_are_byte_identical_to_their_recorded_shas():
    for rel, sha in _frozen()["files"].items():
        assert hashlib.sha256((A3 / rel).read_bytes()).hexdigest() == sha, rel


# ------------------------------------------------------------------ a new export
def _export(tmp_path):
    img = tmp_path / "img.jpeg"
    img.write_bytes(b"\xff\xd8\xff\xe0fake")
    pairs = [dict(pair_id="m76-v1", item_id="v1", a_key="ka", b_key="kb", a_text="A sunny field with a red barn.",
                  b_text="A field with a barn.")]
    out = tmp_path / "out"
    out.mkdir()
    rows = P._kv_write_packets(pairs, ["j1"], {"v1": "Describe this image in detail."}, out, KV_KEY(), attachments={"v1": img})
    return out, rows


def test_v1_a_new_export_binds_the_new_text_and_its_own_sha(tmp_path):
    out, rows = _export(tmp_path)
    assert {r["prompt_sha"] for r in rows} == {NEW_SHA()}
    assert NEW_SHA() != OLD_SHA
    for r in rows:
        packet = (out / r["path"]).read_text()
        assert NEW_TEXT() in packet
        assert "caption" not in packet.lower()
        assert OLD_VISION not in packet
    on_disk = [json.loads(ln) for ln in (out / "manifest.jsonl").read_text().splitlines()]
    assert {r["prompt_sha"] for r in on_disk} == {NEW_SHA()}


def test_v1_a_new_freeze_records_the_new_rubric_sha(tmp_path):
    out, _ = _export(tmp_path)
    meta = dict(member="A3", pair=["n16", "x"], items=[dict(item="v1", test_slot="A", len_ref=1, len_test=1)], identical=[], excluded={})
    path = P.kv_freeze(out, meta, [dict(label="j1", family="f", client="c", model="m")], KV_KEY(), single_family=dict(label="t"))
    doc = json.loads(Path(path).read_text())
    assert doc["rubric"] == KV_KEY() and doc["rubric_sha256"] == NEW_SHA() != OLD_SHA
