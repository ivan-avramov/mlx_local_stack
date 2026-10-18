"""P371 review r5 F24 / F25: the rows-prefix proof compares exact expected row ids INCLUDING the language before it derives slots
(a wrong-language prefix proves nothing), `slot_for` refuses a row id whose language differs from the slot base, and a valid JSON
row whose `id` is not a string is `attribution unproven`, never an exception."""
from __future__ import annotations

import json

import pytest

from bench import chain_rows as cr
from bench.tests.test_p371_review_r4_f21 import SLOTS, attribute, rows


def test_a_wrong_language_prefix_does_not_prove_attribution(tmp_path):
    found = attribute(tmp_path, rows("go/a"))
    assert found["slot"] is None and found["reason"] == "attribution unproven"
    found = attribute(tmp_path / "mixed", rows("python/a", "go/b"))
    assert found["slot"] is None and found["reason"] == "attribution unproven"


def test_the_exact_language_prefix_still_proves_it(tmp_path):
    assert attribute(tmp_path, rows("python/a"))["slot"] == SLOTS[1]


def test_slot_for_refuses_a_row_id_of_another_language_and_a_non_string_id():
    base = "e|oc|m|s1|python"
    assert cr.slot_for(base, "python/a") == base + "|a" and cr.slot_for(base, "a") == base + "|a"
    with pytest.raises(cr.ChainRowsError, match="language"):
        cr.slot_for(base, "go/a")
    for bad in (7, None, ["python/a"], {"x": 1}):
        with pytest.raises(cr.ChainRowsError):
            cr.slot_for(base, bad)


@pytest.mark.parametrize("bad_id", [7, None, ["python/a"], {"x": 1}, True])
def test_a_row_with_a_non_string_id_is_unproven_not_an_exception(tmp_path, bad_id):
    found = attribute(tmp_path, json.dumps({"id": bad_id}) + "\n")
    assert found["slot"] is None and found["reason"] == "attribution unproven"


def test_read_rows_rejects_a_non_string_id(tmp_path):
    path = tmp_path / "r.jsonl"
    path.write_text(json.dumps({"id": 5}) + "\n")
    with pytest.raises(cr.ChainRowsError):
        cr.read_rows(path)
