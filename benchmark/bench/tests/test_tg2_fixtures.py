"""G9: parsers against REAL raw outputs captured from the built tg2 image (m65/tg2_image/capture_fixtures.py), with
leaf sets derived independently from the exercise test sources."""

import json
from pathlib import Path

import pytest

from bench import tg2_grade as tg

FIX = Path(__file__).parent / "fixtures/tg2"
NAMES = sorted(p.name for p in FIX.iterdir()) if FIX.is_dir() else []


def load(name):
    doc = json.loads((FIX / name / "expected.json").read_text())
    return doc, (FIX / name / doc["raw"]).read_text()


def parse(doc, text):
    lang = doc["lang"]
    if lang == "rust":
        return tg.parse_rust(text)
    if lang == "javascript":
        return tg.parse_jest(text, "/work/" + doc["slug"])
    return tg.parse_junit(text)


def test_fixture_set_is_present():
    assert {"rust-gigasecond", "java-affine-cipher", "javascript-affine-cipher", "cpp-gigasecond",
            "javascript-affine-cipher-suite-failure"} <= set(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_real_output_parses_to_exactly_the_independently_derived_leaf_set(name):
    doc, text = load(name)
    leaves = parse(doc, text)
    expected = set(doc["expected_all_pass"])
    extra = set(doc.get("extra_failures", []))
    assert len(expected) > 0
    assert set(leaves) == expected | extra
    assert {k for k, ok in leaves.items() if not ok} == extra
    # the grader's own scoring over the real output
    g = tg.Tg2Grade(leaves=leaves)
    assert g.failing(expected) == len(extra)


def test_suite_level_failure_fixture_is_a_counted_failure_with_every_assertion_passing():
    doc, text = load("javascript-affine-cipher-suite-failure")
    raw = json.loads(text)
    assert raw["success"] is False
    assert all(a["status"] == "passed" for s in raw["testResults"] for a in s["assertionResults"])
    assert tg.Tg2Grade(leaves=parse(doc, text)).failing(set(doc["expected_all_pass"])) == 1
