"""P371 review r4 F21: an unusable final manifest attributes its `unavailable` evidence to the first UNCOMMITTED expected slot,
proven from the invocation's immutable rows file prefix; when the prefix is not provable the slot is null with
`reason: attribution unproven`."""
from __future__ import annotations

import json

from bench.tests.test_p371_review_r3_f16 import build

SLOTS = ["e|oc|m|s1|python|a", "e|oc|m|s1|python|b", "e|oc|m|s1|python|c"]


def attribute(tmp_path, rows_text):
    chain, out, view, worker, good = build(tmp_path)
    if rows_text is not None:
        out.write_text(rows_text)
    att = dict(attempt=1, run_id=None, worker=worker, transport_abort=None, cancelled_item=None, cleanup_status=None)
    chain.hydrate_from_manifest(att, view, out, {"expected_slots": SLOTS})                  # no manifest: unusable
    (found,) = chain.progress["abort_evidence"]
    return found


def rows(*ids):
    return "".join(json.dumps({"id": i}) + "\n" for i in ids)


def test_no_rows_attributes_the_head_slot(tmp_path):
    assert attribute(tmp_path, None)["slot"] == SLOTS[0]


def test_a_committed_prefix_moves_the_attribution_to_the_first_uncommitted_slot(tmp_path):
    assert attribute(tmp_path, rows("python/a"))["slot"] == SLOTS[1]
    assert attribute(tmp_path / "two", rows("python/a", "python/b"))["slot"] == SLOTS[2]


def test_every_slot_committed_or_a_prefix_that_is_not_provable_is_null_unproven(tmp_path):
    for sub, text in (("all", rows("python/a", "python/b", "python/c")), ("gap", rows("python/b")),
                      ("junk", "{not json\n")):
        found = attribute(tmp_path / sub, text)
        assert found["slot"] is None and found["reason"] == "attribution unproven", sub
