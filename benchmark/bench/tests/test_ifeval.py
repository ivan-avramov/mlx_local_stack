"""Tests for IFEval: vendored verifiers presence, item shaping, aggregation, grading."""
import os
import types

import pytest

import bench.benchmarks as B
import bench.grade as G

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


class _Out:
    """Stand-in for evaluation_lib.OutputExample."""
    def __init__(self, follow_all, follow_list):
        self.follow_all_instructions = follow_all
        self.follow_instruction_list = follow_list


def test_ifeval_aggregate_prompt_and_instruction_levels():
    # 2 prompts. Strict: p1 all-follow [T,T]; p2 partial [T,F].
    strict = [_Out(True, [True, True]), _Out(False, [True, False])]
    # Loose more lenient: p2 now all-follow.
    loose = [_Out(True, [True, True]), _Out(True, [True, True])]
    agg = G._ifeval_aggregate(strict, loose)
    assert agg["prompt_strict"] == 0.5            # 1 of 2 prompts fully followed
    assert agg["inst_strict"] == 0.75             # 3 of 4 instructions followed
    assert agg["prompt_loose"] == 1.0
    assert agg["inst_loose"] == 1.0


def _fake_ev():
    """A fake evaluation_lib whose strict/loose echo a deterministic verdict keyed on the response."""
    mod = types.SimpleNamespace()
    class InputExample:
        def __init__(self, key, instruction_id_list, prompt, kwargs):
            self.key = key; self.instruction_id_list = instruction_id_list
            self.prompt = prompt; self.kwargs = kwargs
    mod.InputExample = InputExample

    def strict(inp, p2r):
        resp = p2r[inp.prompt]
        follow = [("GOOD" in resp)] * len(inp.instruction_id_list)
        return _Out(all(follow) and bool(follow), follow)

    def loose(inp, p2r):  # loose: always all-follow (lenient)
        follow = [True] * len(inp.instruction_id_list)
        return _Out(True, follow)

    mod.test_instruction_following_strict = strict
    mod.test_instruction_following_loose = loose
    return mod


def test_grade_ifeval_success(monkeypatch):
    rows = [{"id": 1, "content": "GOOD answer"}, {"id": 2, "content": "bad answer"}]
    monkeypatch.setattr(G, "_rows", lambda m, n: rows)
    monkeypatch.setattr(G, "_load_ifeval_lib", lambda: _fake_ev())
    meta = [
        {"id": 1, "prompt": "P1", "meta": {"instruction_id_list": ["a"], "kwargs": [{}]}},
        {"id": 2, "prompt": "P2", "meta": {"instruction_id_list": ["a", "b"], "kwargs": [{}, {}]}},
    ]
    monkeypatch.setattr(G.benchmarks, "load", lambda name, limit, seed: meta)
    out = G.grade_ifeval("ifeval", "m")
    assert out["n"] == 2
    assert out["prompt_strict"] == 0.5            # only id=1 ("GOOD") follows all
    assert out["acc"] == out["prompt_strict"]
    assert out["prompt_loose"] == 1.0


def test_grade_ifeval_no_completions(monkeypatch):
    monkeypatch.setattr(G, "_rows", lambda m, n: [])
    out = G.grade_ifeval("ifeval", "m")
    assert out["n"] == 0 and out["acc"] is None and "note" in out


def test_grade_ifeval_graceful_degrade_when_verifiers_missing(monkeypatch):
    monkeypatch.setattr(G, "_rows", lambda m, n: [{"id": 1, "content": "x"}])

    def boom():
        raise ImportError("no module named instruction_following_eval")
    monkeypatch.setattr(G, "_load_ifeval_lib", boom)
    out = G.grade_ifeval("ifeval", "m")
    assert out["acc"] is None and "note" in out
