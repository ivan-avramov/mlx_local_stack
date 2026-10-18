"""P371 phase 1: `bench.corpus` (plan 3.1): the Corpus contract and its typed records are pure data."""
from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

from bench import corpus as cp

REPO = Path(__file__).resolve().parents[3]


def prepared(**over):
    kw = dict(item_id="python/foo", lang="python", name="foo", work=Path("/w/foo"), entry={"solution": "foo.py"},
              editable=("foo.py",), baseline={"foo.py": "a" * 64}, protected={"foo_test.py": "b" * 64},
              prepared={"foo.py": "a" * 64, "foo_test.py": "b" * 64}, tests=("foo_test.py",))
    kw.update(over)
    return cp.PreparedItem(**kw)


def test_the_corpus_module_is_pure():
    code = ("import sys; import bench.corpus; bad = [m for m in sys.modules if m in ('bench.structured_grade',"
            "'bench.proc_guard','bench.opencode_v2_core','bench.corpus_tg1','bench.arm_adapter','psutil')]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO / "benchmark", capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


def test_corpus_is_abstract_and_a_complete_subclass_is_instantiable():
    with pytest.raises(TypeError):
        cp.Corpus()
    names = {"load_universe", "items", "excluded", "source_root", "prepare", "prompt", "tampered", "grade", "changed",
             "final_tree", "languages", "needs_docker", "identity"}
    assert names <= set(cp.Corpus.__abstractmethods__)


def test_prepared_item_is_frozen_and_validates():
    p = prepared()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.name = "x"
    with pytest.raises(ValueError):
        prepared(editable=())
    with pytest.raises(ValueError):
        prepared(editable=("missing.py",), baseline={"foo.py": "a" * 64})      # an editable path needs a baseline
    with pytest.raises(ValueError):
        prepared(item_id="foo")                                                # id is `<lang>/<name>`
    assert p.item_id == "python/foo"


def test_grade_outcome_shapes():
    ok = cp.GradeOutcome(failing=0, leaves=(("a", "b"),), tampered=False, outcome="model",
                         resources=dict(grader_mem_kill=False, grader_oom=False), phases=(), reports={})
    assert ok.passed
    assert not dataclasses.replace(ok, failing=2).passed
    tampered = cp.GradeOutcome(failing=None, leaves=(), tampered=True, outcome="model",
                               resources=dict(grader_mem_kill=False, grader_oom=False), phases=(), reports={})
    assert not tampered.passed
    with pytest.raises(ValueError):
        dataclasses.replace(ok, outcome="weird")
    with pytest.raises(ValueError):
        dataclasses.replace(ok, failing=None)                  # no count without tamper
    with pytest.raises(ValueError):
        dataclasses.replace(tampered, failing=1)               # a tampered tree has no count
    with pytest.raises(ValueError):
        dataclasses.replace(ok, resources=dict(grader_oom=False))


def test_final_tree_record():
    ft = cp.FinalTree(root=Path("/e/x.final_tree"), files={"foo.py": "a" * 64}, missing=(),
                      manifest_sha256="c" * 64, manifest_path=Path("/e/x.final_tree/manifest.json"))
    assert ft.files["foo.py"] == "a" * 64
    with pytest.raises(dataclasses.FrozenInstanceError):
        ft.root = Path("/")
