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


def test_grade_ifeval_skips_row_when_loose_raises(monkeypatch):
    """If loose raises after strict succeeds for a row, that row is skipped ENTIRELY
    (strict/loose lists stay aligned), not partially appended."""
    rows = [{"id": 1, "content": "x"}, {"id": 2, "content": "y"}]
    monkeypatch.setattr(G, "_rows", lambda m, n: rows)
    meta = [
        {"id": 1, "prompt": "P1", "meta": {"instruction_id_list": ["a"], "kwargs": [{}]}},
        {"id": 2, "prompt": "P2", "meta": {"instruction_id_list": ["a"], "kwargs": [{}]}},
    ]
    monkeypatch.setattr(G.benchmarks, "load", lambda *a: meta)

    class EV:
        class InputExample:
            def __init__(self, key, instruction_id_list, prompt, kwargs):
                self.key = key; self.instruction_id_list = instruction_id_list
                self.prompt = prompt; self.kwargs = kwargs

        @staticmethod
        def test_instruction_following_strict(inp, p2r):
            ok = inp.prompt == "P1"
            return _Out(ok, [ok])

        @staticmethod
        def test_instruction_following_loose(inp, p2r):
            if inp.prompt == "P2":
                raise RuntimeError("loose blew up")
            return _Out(True, [True])

    monkeypatch.setattr(G, "_load_ifeval_lib", lambda: EV())
    out = G.grade_ifeval("ifeval", "m")
    assert out["n"] == 1                 # P2 skipped (loose raised) -> only P1 graded
    assert out["prompt_strict"] == 1.0   # aggregated over the 1 aligned row, not the desynced 2
    assert out["prompt_loose"] == 1.0


# ---------------------------------------------------------------- the acc-clobber regression
def test_a_grader_computed_acc_survives_the_convergence_postprocessor():
    """IFEval computes its own headline (prompt-level strict) and populates NO per-item list.

    `_finalize` sets `score["acc"]` from `score["items"]` unconditionally
    (grade.py:84), so for any bench that computes acc its own way the headline was silently
    REPLACED WITH None. Measured 2026-08-13 on a 5-item IFEval smoke: grade_ifeval returned
    acc=0.75 (prompt_strict), and scores.json recorded `"acc": null, "prompt_strict": 0.75` — the
    real number was present but the headline column read "—", which looks exactly like a grading
    failure and would have been read as "IFEval is still broken".

    Per-item benches must keep winning (their acc is the pass@1 over items); only the
    no-items-but-acc-already-set case changes.
    """
    import bench.grade as G
    score = {"benchmark": "ifeval", "model": "M", "n": 4, "acc": 0.75, "prompt_strict": 0.75}
    G._finalize(score, rows=[{"id": 1, "finish_reason": "stop",
                                               "completion_tokens": 10, "thinking_budget": 81920}])
    assert score["acc"] == 0.75, "the grader's own headline was clobbered by the post-processor"


def test_per_item_acc_still_overrides_for_benches_that_provide_items():
    """The normal path is unchanged: where per-item scores exist they define acc."""
    import bench.grade as G
    score = {"benchmark": "humanevalplus", "model": "M", "acc": 0.99,
             "items": [{"id": 1, "sample": 0, "score": 0.0},
                       {"id": 2, "sample": 0, "score": 1.0}]}
    G._finalize(score, rows=[{"id": 1, "finish_reason": "stop",
                                               "completion_tokens": 10, "thinking_budget": 81920}])
    assert score["acc"] == 0.5, "per-item pass@1 must still define acc where items exist"


def test_acc_is_None_when_there_is_neither_items_nor_a_grader_acc():
    import bench.grade as G
    score = {"benchmark": "gpqa", "model": "M"}
    G._finalize(score, rows=[{"id": 1, "finish_reason": "stop",
                                               "completion_tokens": 10, "thinking_budget": 81920}])
    assert score["acc"] is None


def test_verifier_skips_are_COUNTED_not_silently_dropped(monkeypatch):
    """A bare `continue` on a verifier exception shrinks n invisibly.

    Measured on the 5-item smoke: 5 rows generated, n=4 reported — one item's verifier raised and was
    dropped with no trace. At 541 items a silent 4% loss is undetectable, and n is the denominator of
    the headline. Skips must be counted and reported so the reader can see the real denominator.
    """
    import bench.grade as G

    class FakeEv:
        class InputExample:
            def __init__(self, **kw): pass
        @staticmethod
        def test_instruction_following_strict(inp, p2r):
            raise RuntimeError("verifier blew up")
        @staticmethod
        def test_instruction_following_loose(inp, p2r):
            raise RuntimeError("verifier blew up")

    monkeypatch.setattr(G, "_load_ifeval_lib", lambda: FakeEv)
    monkeypatch.setattr(G, "_rows", lambda m, b: [{"id": 7, "content": "x"}])
    monkeypatch.setattr(G.benchmarks, "load", lambda *a, **k: [
        {"id": 7, "prompt": "p", "meta": {"instruction_id_list": ["a"], "kwargs": [{}]}}])
    out = G.grade_ifeval("ifeval", "M")
    assert out["n_verifier_skipped"] == 1, "a dropped item must be counted"
    assert "1" in str(out.get("note", "")), "and surfaced in the note"


# ---------------------------------------------------------------- nltk corpora must fail LOUD
def test_missing_nltk_corpora_RAISES_instead_of_silently_dropping_items(monkeypatch):
    """Measured 2026-08-13 on the live IFEval run: 8 of 38 completions (21%) were dropped by
    `LookupError: Resource 'punkt_tab' not found`, and acc was reported over the surviving subset.

    The excluded items were HARDER than average: re-grading after downloading the corpora moved acc
    from 93.3% (n=30) to 90.2% (n=41). So a silent skip does not just shrink n, it BIASES the
    headline upward.

    _load_ifeval_lib already tried to ensure the tokenizer, but checked only `punkt` while modern
    nltk needs `punkt_tab`, and its `except Exception: pass` was annotated "verifiers that need it
    will fail closed" — they do not; they fail per item, inside the loop, where a bare `continue`
    swallowed them. A whole-bench acc:null with an actionable note is strictly better than a
    plausible-looking number over a biased 79% subset.
    """
    import bench.grade as G

    class FakeNltkData:
        @staticmethod
        def find(path):
            raise LookupError(f"Resource {path} not found")

    fake_nltk = type("nltk", (), {"data": FakeNltkData,
                                  "download": staticmethod(lambda *a, **k: False)})
    monkeypatch.setitem(__import__("sys").modules, "nltk", fake_nltk)
    with pytest.raises(Exception) as ei:
        G._load_ifeval_lib()
    msg = str(ei.value).lower()
    assert "punkt" in msg, "the error must name the missing resource"
    assert "nltk" in msg and "download" in msg, "and say how to fix it"


def test_the_check_covers_punkt_tab_not_just_punkt(monkeypatch):
    """`punkt` alone satisfied the old check while the verifiers needed `punkt_tab` — which is
    exactly how this passed silently and then failed 21% of items at use time."""
    import bench.grade as G
    looked = []

    class FakeNltkData:
        @staticmethod
        def find(path):
            looked.append(path)
            return "/fake"

    fake_nltk = type("nltk", (), {"data": FakeNltkData,
                                  "download": staticmethod(lambda *a, **k: True)})
    monkeypatch.setitem(__import__("sys").modules, "nltk", fake_nltk)
    try:
        G._load_ifeval_lib()
    except Exception:
        pass
    assert any("punkt_tab" in p for p in looked), f"punkt_tab never checked; looked at {looked}"


# ---------------------------------------------------------------- items, so the ranking key exists
def test_grade_ifeval_emits_per_item_scores(monkeypatch):
    """Without `items`, the shared post-processor cannot compute acc_strict — the RANKING KEY — nor a
    CI nor an MDE. Surfacing acc_strict as a column (2026-08-13) exposed it as "—" for the very axis
    being run, i.e. the ruling that a DNF fails in the denominator could not be applied to IFEval.

    The per-item score is prompt-level strict (follow_all_instructions), so acc computed from items is
    IDENTICAL to the prompt_strict the grader already reported — this adds capability without moving
    any existing number.
    """
    import bench.grade as G

    class Out:
        def __init__(self, ok):
            self.follow_all_instructions = ok
            self.follow_instruction_list = [ok]

    class FakeEv:
        class InputExample:
            def __init__(self, **kw):
                pass
        @staticmethod
        def test_instruction_following_strict(inp, p2r):
            return Out(True)
        @staticmethod
        def test_instruction_following_loose(inp, p2r):
            return Out(True)

    monkeypatch.setattr(G, "_load_ifeval_lib", lambda: FakeEv)
    monkeypatch.setattr(G, "_rows", lambda m, b: [
        {"id": 7, "sample": 0, "content": "x"}, {"id": 8, "sample": 0, "content": "y"}])
    monkeypatch.setattr(G.benchmarks, "load", lambda *a, **k: [
        {"id": i, "prompt": f"p{i}", "meta": {"instruction_id_list": ["a"], "kwargs": [{}]}}
        for i in (7, 8)])
    out = G.grade_ifeval("ifeval", "M")
    assert "items" in out, "grade_ifeval must emit per-item scores"
    assert len(out["items"]) == 2
    assert {i["id"] for i in out["items"]} == {7, 8}
    assert all(set(i) >= {"id", "sample", "score"} for i in out["items"])
    # acc from items must equal the grader's own prompt-level strict number
    assert out["acc"] == out["prompt_strict"] == 1.0


def test_ifeval_items_carry_the_row_sample_index(monkeypatch):
    """acc_strict keys on (id, sample); a wrong sample index would silently mis-join at --samples>1."""
    import bench.grade as G

    class Out:
        follow_all_instructions = True
        follow_instruction_list = [True]

    class FakeEv:
        class InputExample:
            def __init__(self, **kw):
                pass
        test_instruction_following_strict = staticmethod(lambda i, p: Out())
        test_instruction_following_loose = staticmethod(lambda i, p: Out())

    monkeypatch.setattr(G, "_load_ifeval_lib", lambda: FakeEv)
    monkeypatch.setattr(G, "_rows", lambda m, b: [{"id": 7, "sample": 3, "content": "x"}])
    monkeypatch.setattr(G.benchmarks, "load", lambda *a, **k: [
        {"id": 7, "prompt": "p", "meta": {"instruction_id_list": ["a"], "kwargs": [{}]}}])
    assert G.grade_ifeval("ifeval", "M")["items"][0]["sample"] == 3
