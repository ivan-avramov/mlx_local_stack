"""Tests for IFEval: vendored verifiers presence, item shaping, aggregation, grading."""
import os

import pytest

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
