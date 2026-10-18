"""P371 phase 1: `bench.corpus_tg1` wraps today's tg1 code paths; compared against `tg1_runner` / `structured_grade`."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from bench import corpus as cp
from bench import corpus_tg1 as ct
from bench import structured_grade as sg
from bench import tg1_runner
from bench.token_turn_gate import TransportAbort

SOLUTION = "def f():\n    pass\n"
TEST = "from foo import f\n\n\ndef test_f():\n    assert f() == 1\n"


def make_polyglot(root):
    src = root / "python/exercises/practice/foo"
    (src / ".meta").mkdir(parents=True)
    (src / ".docs").mkdir()
    (src / "foo.py").write_text(SOLUTION)
    (src / "foo_test.py").write_text(TEST)
    (src / ".docs/instructions.md").write_text("Make f return 1.\n")
    (src / ".meta/config.json").write_text(json.dumps(
        {"files": {"solution": ["foo.py"], "test": ["foo_test.py"], "example": [".meta/example.py"]}}))
    (src / ".meta/example.py").write_text("def f():\n    return 1\n")
    return src


def make_universe(tmp, src, **entry_over):
    work = tmp / "ref"
    shutil.copytree(src, work, ignore=shutil.ignore_patterns(".meta"))
    prepared = sg.manifest(work)
    entry = dict(leaves=[["foo_test.py", "test_f"]], baseline_failing=1,
                 protected=sg.protected_manifest(prepared, ["foo.py"]), prepared=prepared, solution="foo.py",
                 test="foo_test.py", grader_version=sg.VERSION)
    entry.update(entry_over)
    doc = {"grader_version": sg.VERSION, "items": {"python/foo": entry}}
    path = tmp / "universe.json"
    raw = (json.dumps(doc, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(raw)
    Path(str(path) + ".sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    shutil.rmtree(work)
    return path


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "polyglot"
    src = make_polyglot(root)
    universe = make_universe(tmp_path, src)
    c = ct.Tg1Corpus(universe, polyglot_root=root)
    c.load_universe()
    return c


def test_the_prompt_template_and_inject_addenda_are_byte_equal_to_tg1_runners(corpus, tmp_path):
    assert ct.INJECT_ADDENDA == tg1_runner.INJECT_ADDENDA
    for kind in tg1_runner.INJECT_ADDENDA:
        assert ct.inject_addendum_sha256(kind) == tg1_runner.inject_addendum_sha256(kind)
    assert ct.INJECT_LABELS == {k: tg1_runner.inject_label(k) for k in tg1_runner.INJECT_ADDENDA}
    item = corpus.prepare("python/foo", tmp_path / "scratch/foo")
    entry = item.entry
    # the literal `tg1_runner._main` builds today (copied from its source)
    want = (f'Implement the solution in {entry["solution"]} so that the tests in {entry["test"]} pass. '
            "The specification is in .docs/instructions.md — read it first. "
            f'Do NOT modify {entry["test"]}. Do not create new files unless required by the spec.')
    assert corpus.prompt(item, None) == want
    for kind, addendum in tg1_runner.INJECT_ADDENDA.items():
        assert corpus.prompt(item, kind) == want + " " + addendum
    with pytest.raises(ValueError):
        corpus.prompt(item, "bogus")


def test_load_universe_is_universe_preflight_load_and_excludes_go_counter(tmp_path, corpus):
    from m62 import universe_preflight
    doc, sha = universe_preflight.load(corpus.universe_path)
    assert corpus.universe == doc and corpus.universe_sha256 == sha
    assert corpus.excluded == frozenset({"go/counter"})
    assert corpus.items("python") == ["python/foo"] and corpus.items("go") == []
    assert corpus.languages == ("python", "go")
    assert corpus.needs_docker("go") and not corpus.needs_docker("python")


def test_require_items_refuses_go_counter_and_unknown_items(corpus):
    corpus.require_items("python", ["foo"])
    for lang, name in (("go", "counter"), ("python", "nope")):
        with pytest.raises(TransportAbort, match="absent/refused"):
            corpus.require_items(lang, [name])


def test_load_universe_refuses_a_sidecar_mismatch(tmp_path):
    root = tmp_path / "polyglot"
    path = make_universe(tmp_path, make_polyglot(root))
    Path(str(path) + ".sha256").write_text("0" * 64 + "\n")
    with pytest.raises(TransportAbort):
        ct.Tg1Corpus(path, polyglot_root=root).load_universe()


def test_prepare_does_what_tg1_runner_does_today(corpus, tmp_path):
    work = tmp_path / "scratch/foo"
    item = corpus.prepare("python/foo", work)
    assert item.work == work and (work / ".git").is_dir()
    assert not (work / ".meta").exists()
    assert sg.manifest(work) == corpus.universe["items"]["python/foo"]["prepared"] == item.prepared
    assert os.stat(work / "foo.py").st_mtime == 1759708800 and os.stat(work).st_mtime == 1759708800
    assert item.editable == ("foo.py",) and item.tests == ("foo_test.py",)
    assert item.baseline == {"foo.py": hashlib.sha256(SOLUTION.encode()).hexdigest()}
    assert item.protected == corpus.universe["items"]["python/foo"]["protected"]
    assert item.entry["lang"] == "python" and item.entry["id"] == "python/foo" and item.lang == "python"


def test_prepare_refuses_a_tree_that_differs_from_the_frozen_universe(tmp_path):
    root = tmp_path / "polyglot"
    src = make_polyglot(root)
    path = make_universe(tmp_path, src)
    (src / "foo_test.py").write_text(TEST + "# drift\n")
    c = ct.Tg1Corpus(path, polyglot_root=root)
    c.load_universe()
    with pytest.raises(TransportAbort, match="differs from frozen universe"):
        c.prepare("python/foo", tmp_path / "scratch/foo")


def snap_of(work, tmp_path, boundary=0):
    with sg.snapshot(work, tmp_path / "private", boundary=boundary) as snap:
        yield_snap = snap
    return yield_snap


def test_tampered_matches_structured_grade_on_fixture_trees(corpus, tmp_path):
    (tmp_path / "private").mkdir()
    work = tmp_path / "scratch/foo"
    item = corpus.prepare("python/foo", work)
    with sg.snapshot(work, tmp_path / "private", boundary=0) as snap:
        assert corpus.tampered(snap, item) is sg.tampered(snap.path, item.protected, item.prepared, "python") is False
    (work / "foo.py").write_text("def f():\n    return 1\n")                   # the editable solution: allowed
    with sg.snapshot(work, tmp_path / "private", boundary=1) as snap:
        assert corpus.tampered(snap, item) is False
    (work / "foo_test.py").write_text("def test_f():\n    pass\n")              # a protected file: tamper
    with sg.snapshot(work, tmp_path / "private", boundary=2) as snap:
        assert corpus.tampered(snap, item) is sg.tampered(snap.path, item.protected, item.prepared, "python") is True
    (work / "foo_test.py").write_text(TEST)
    (work / "sitecustomize.py").write_text("")                                 # forbidden new python file
    with sg.snapshot(work, tmp_path / "private", boundary=3) as snap:
        assert corpus.tampered(snap, item) is True
    assert corpus.tampered(None, item) is True                                 # no snapshot: treated as tampered


def fake_grade(passing, **kw):
    calls = []

    def grade(lang, work, test, private, **kwargs):
        calls.append((lang, Path(work), test, Path(private), kwargs))
        return sg.Grade(passing=set(passing), collected={("foo_test.py", "test_f")}, returncode=0, **kw)
    return grade, calls


def test_grade_forwards_to_structured_grade_and_maps_the_outcome(corpus, tmp_path, monkeypatch):
    (tmp_path / "private").mkdir()
    work = tmp_path / "scratch/foo"
    item = corpus.prepare("python/foo", work)
    grade, calls = fake_grade({("foo_test.py", "test_f")}, grader_mem_kill=True)
    monkeypatch.setattr(sg, "grade", grade)
    guard = object()
    with sg.snapshot(work, tmp_path / "private", boundary=7) as snap:
        out = corpus.grade(snap, item, tmp_path / "private", guard, tmp_path / "keep", 4, 7, False)
    (lang, gwork, test, private, kwargs), = calls
    assert (lang, gwork, test) == ("python", snap.path, "foo_test.py")
    assert kwargs == dict(guard=guard, keep=tmp_path / "keep", seq=4, boundary=7, final=False)
    assert out.failing == 0 and out.passed and not out.tampered and out.outcome == "model"
    assert out.leaves == (("foo_test.py", "test_f"),)
    assert out.resources == dict(grader_mem_kill=True, grader_oom=False)
    assert [(p["seq"], p["boundary"], p["final"], p["outcome"]) for p in out.phases] == [(4, 7, False, "parsed")]


def test_grade_counts_failing_leaves_like_the_runner(corpus, tmp_path, monkeypatch):
    (tmp_path / "private").mkdir()
    item = corpus.prepare("python/foo", tmp_path / "scratch/foo")
    grade, _ = fake_grade(set(), grader_oom=True, outcome="oom")
    monkeypatch.setattr(sg, "grade", grade)
    with sg.snapshot(tmp_path / "scratch/foo", tmp_path / "private", boundary=1) as snap:
        out = corpus.grade(snap, item, tmp_path / "private", None, None, 1, 1, True)
    assert out.failing == 1 and not out.passed and out.resources["grader_oom"] and out.phases[0]["outcome"] == "oom"


def test_a_tampered_grade_runs_no_grader_and_final_leaves_a_typed_receipt(corpus, tmp_path, monkeypatch):
    (tmp_path / "private").mkdir()
    work = tmp_path / "scratch/foo"
    item = corpus.prepare("python/foo", work)
    (work / "foo_test.py").write_text("tampered\n")
    grade, calls = fake_grade(set())
    monkeypatch.setattr(sg, "grade", grade)
    keep = tmp_path / "keep"
    with sg.snapshot(work, tmp_path / "private", boundary=2) as snap:
        mid = corpus.grade(snap, item, tmp_path / "private", None, keep, 1, 2, False)
        final = corpus.grade(snap, item, tmp_path / "private", None, keep, 2, 2, True)
        none = corpus.grade(None, item, tmp_path / "private", None, keep, 3, 2, True)
    assert not calls
    for out in (mid, final, none):
        assert out.tampered and out.failing is None and not out.passed
    assert not (keep / "seq-0001").exists()                  # a mid-run tamper writes no receipt (as today)
    idx = json.loads((keep / "seq-0002/index.json").read_text())
    assert (idx["outcome"], idx["final"], idx["boundary"]) == ("tampered", True, 2)
    assert json.loads((keep / "seq-0003/index.json").read_text())["outcome"] == "tampered"


def test_changed_is_the_untouched_solution_fails_rule(corpus, tmp_path):
    work = tmp_path / "scratch/foo"
    item = corpus.prepare("python/foo", work)
    assert corpus.changed(item) is False                                   # untouched stub fails
    (work / "foo.py").write_text(SOLUTION)                                 # same bytes rewritten
    assert corpus.changed(item) is False
    (work / "foo.py").write_text("def f():\n    return 1\n")
    assert corpus.changed(item) is True
    (work / "foo.py").unlink()
    assert corpus.changed(item) is False                                   # `is_file() and differs` (tg1_runner)


def test_final_tree_is_content_addressed_with_a_sha256_manifest(corpus, tmp_path):
    work = tmp_path / "scratch/foo"
    item = corpus.prepare("python/foo", work)
    (work / "foo.py").write_text("def f():\n    return 1\n")
    dest = tmp_path / "ev/x.final_tree"
    ft = corpus.final_tree(item, dest)
    sha = hashlib.sha256(b"def f():\n    return 1\n").hexdigest()
    assert ft.files == {"foo.py": sha} and ft.missing == () and ft.root == dest
    assert (dest / "objects" / sha).read_bytes() == b"def f():\n    return 1\n"
    manifest = json.loads(ft.manifest_path.read_text())
    assert manifest == dict(files={"foo.py": sha}, missing=[])
    assert ft.manifest_sha256 == hashlib.sha256(ft.manifest_path.read_bytes()).hexdigest()
    assert corpus.final_tree(item, tmp_path / "ev/y.final_tree").manifest_sha256 == ft.manifest_sha256
    (work / "foo.py").unlink()
    gone = corpus.final_tree(item, tmp_path / "ev/z.final_tree")
    assert gone.files == {} and gone.missing == ("foo.py",)
    with pytest.raises(TransportAbort):
        corpus.final_tree(item, dest)                                      # evidence is immutable


def test_identity_carries_the_corpus_sha_grader_version_timeouts_and_image(corpus):
    ident = corpus.identity()
    assert ident["corpus_id"] == "tg1" and ident["universe_sha256"] == corpus.universe_sha256
    assert ident["grader_version"] == sg.VERSION and ident["grader_timeout_s"] == sg.TIMEOUTS
    assert ident["image"] == "aider-benchmark"
    from bench import toolchain
    assert ident["image"] == toolchain.GRADER_IMAGE
    assert json.loads(json.dumps(ident)) == ident


def test_identity_before_load_universe_refuses(tmp_path):
    with pytest.raises(TransportAbort):
        ct.Tg1Corpus(tmp_path / "u.json", polyglot_root=tmp_path).identity()


def test_it_is_a_corpus():
    assert issubclass(ct.Tg1Corpus, cp.Corpus)
