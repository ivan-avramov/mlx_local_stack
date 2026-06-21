"""Tests for IFEval: vendored verifiers presence, item shaping, aggregation, grading."""
import os

import pytest

import bench.benchmarks as B

VENDOR = os.path.join(os.path.dirname(__file__), "..", "vendor", "instruction_following_eval")


def test_vendored_modules_present():
    for fn in ("instructions.py", "instructions_registry.py", "instructions_util.py",
               "evaluation_lib.py", "__init__.py", "NOTICE"):
        assert os.path.isfile(os.path.join(VENDOR, fn)), f"missing vendored file: {fn}"


def test_requirements_list_ifeval_deps():
    req = open(os.path.join(os.path.dirname(__file__), "..", "..", "requirements.txt")).read().lower()
    for dep in ("absl-py", "langdetect", "nltk", "immutabledict"):
        assert dep in req, f"requirements.txt missing {dep}"


def test_vendored_registry_imports_if_deps_present():
    """If the verifier deps are installed, the registry imports and has known ids.
    Skips where deps/nltk-data are absent (the default test env)."""
    import sys
    vend_parent = os.path.join(os.path.dirname(__file__), "..", "vendor")
    if vend_parent not in sys.path:
        sys.path.insert(0, vend_parent)
    ir = pytest.importorskip("instruction_following_eval.instructions_registry")
    assert "keywords:existence" in ir.INSTRUCTION_DICT


def test_ifeval_item_filters_none_kwargs_and_shapes():
    row = {
        "key": 42,
        "prompt": "Write a poem with no commas.",
        "instruction_id_list": ["punctuation:no_comma", "length_constraints:number_words"],
        "kwargs": [
            {"num_words": None, "relation": None, "num_highlights": None},          # all None -> {}
            {"num_words": 50, "relation": "at least", "num_highlights": None},       # keep non-None
        ],
    }
    item = B._ifeval_item(row)
    assert item["id"] == 42
    assert item["prompt"] == "Write a poem with no commas."
    assert item["meta"]["instruction_id_list"] == ["punctuation:no_comma", "length_constraints:number_words"]
    assert item["meta"]["kwargs"] == [{}, {"num_words": 50, "relation": "at least"}]


def test_ifeval_in_specs_and_messages():
    assert "ifeval" in B.SPECS
    assert B.SPECS["ifeval"]["gated"] is False
    item = B._ifeval_item({"key": 1, "prompt": "Do X.", "instruction_id_list": [], "kwargs": []})
    msgs = B.build_messages("ifeval", item)
    assert msgs == [{"role": "user", "content": "Do X."}]  # prompt sent verbatim (it IS the instruction)


def test_ifeval_in_tiers():
    import importlib, sys, pathlib
    sys.path.insert(0, str(pathlib.Path(B.__file__).resolve().parents[1]))  # benchmark/
    run = importlib.import_module("run")
    assert "ifeval" in run.TIERS["heavy"][0]
    assert "ifeval" in run.TIERS["mid"][0]
