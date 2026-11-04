"""B8 rule 6 - the cross-wave code check `cross_wave(repo, wave1_off, wave2_off)` on a tiny git repo built under tmp_path.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
`files` = `git diff --name-only <wave1_off> <wave2_off> -- <paths>`; paths = main_models.yaml, src/mlx-vlm, src/mlx-serve and the union
over both commits of the python closure of benchmark/run.py, benchmark/vision_gate.py, benchmark/bench/run_reasoning.py.
"""
from __future__ import annotations

import json

import pytest

from bench.tests.p613s2 import w1view as V
from bench.tests.p613s2 import wave1world as WW

CLOSURE = {"benchmark/run.py", "benchmark/vision_gate.py", "benchmark/bench/run_reasoning.py", "benchmark/bench/helper.py",
           "benchmark/bench/__init__.py"}
PATHS3 = {"main_models.yaml", "src/mlx-vlm", "src/mlx-serve"}


def cw(verify, w):
    return verify.cross_wave(w.repo, w.commits["w1_off"], w.commits["w2_off"])


# class: new-behaviour (no change between the two OFF commits: the record shape, the paths, no flag)
def test_no_change_no_flag(verify, make_w1):
    w = make_w1()
    r = cw(verify, w)
    assert r["wave1_off"] == w.commits["w1_off"] and r["wave2_off"] == w.commits["w2_off"]
    assert r["files"] == [] and r["flag"] is False
    assert r["entry_equal"] is True and r["globals_equal"] is True
    assert r["qualify"] == "covered by gitlink src/mlx-vlm"
    assert set(r["closure_files"]) == CLOSURE and r["closure_files"] == sorted(r["closure_files"])
    assert set(r["paths"]) == PATHS3 | CLOSURE


# class: new-behaviour (a change to main_models.yaml flags; entry and globals evidence say what changed)
@pytest.mark.parametrize("w2,entry_eq,globals_eq", [
    ({"main_models.yaml": WW.registry_text(other="b")}, True, True),
    ({"main_models.yaml": WW.registry_text(entry_rev="r2")}, False, True),
    ({"main_models.yaml": WW.registry_text(glob="7200")}, True, False),
    ({"main_models.yaml": WW.registry_text(other="b", glob="7200", entry_rev="r2")}, False, False),
])
def test_registry_change_flags_with_evidence(verify, make_w1, w2, entry_eq, globals_eq):
    w = make_w1(w2=w2)
    r = cw(verify, w)
    assert r["files"] == ["main_models.yaml"] and r["flag"] is True
    assert r["entry_equal"] is entry_eq and r["globals_equal"] is globals_eq


# class: new-behaviour (a change to a file of the closure of run.py flags and is listed)
def test_closure_file_change_flags(verify, make_w1):
    w = make_w1(w2={"benchmark/bench/helper.py": "VALUE = 2\n"})
    r = cw(verify, w)
    assert r["files"] == ["benchmark/bench/helper.py"] and r["flag"] is True
    assert r["entry_equal"] is True and r["globals_equal"] is True


# class: new-behaviour (a change to each of the three entries themselves flags)
@pytest.mark.parametrize("entry", ["benchmark/run.py", "benchmark/vision_gate.py", "benchmark/bench/run_reasoning.py"])
def test_entry_file_change_flags(verify, make_w1, entry):
    w = make_w1(w2={entry: "from bench import helper  # changed\n" if entry != "benchmark/vision_gate.py" else "import bench.helper  # c\n"})
    r = cw(verify, w)
    assert r["files"] == [entry] and r["flag"] is True


# class: new-behaviour (a change OUTSIDE the paths - docs, a module nothing in the closure imports - is not a flag)
def test_change_outside_the_paths_does_not_flag(verify, make_w1):
    w = make_w1(w2={"docs/note.md": "note v2\n", "benchmark/bench/unrelated.py": "X = 2\n", "README.md": "new\n"})
    r = cw(verify, w)
    assert r["files"] == [] and r["flag"] is False
    assert "benchmark/bench/unrelated.py" not in r["closure_files"]


# class: new-behaviour (the gitlinks src/mlx-vlm and src/mlx-serve are paths: a bumped submodule flags)
@pytest.mark.parametrize("path", ["src/mlx-vlm", "src/mlx-serve"])
def test_gitlink_change_flags(verify, make_w1, path):
    w = make_w1(w2_gitlinks={path: "ab" * 20})
    r = cw(verify, w)
    assert r["files"] == [path] and r["flag"] is True


# class: new-behaviour (the closure is the UNION over both commits: a module only the Wave 1 closure imported still counts)
def test_closure_is_the_union_over_both_commits(verify, make_w1):
    w = make_w1(w1_off={"benchmark/run.py": "from bench import helper, old\n", "benchmark/bench/old.py": "V = 1\n"},
                w2={"benchmark/run.py": "from bench import helper\n", "benchmark/bench/old.py": "V = 2\n"})
    r = cw(verify, w)
    assert "benchmark/bench/old.py" in r["closure_files"]
    assert r["files"] == ["benchmark/bench/old.py", "benchmark/run.py"] and r["flag"] is True


# class: new-behaviour (... and a module only the Wave 2 closure imports counts too)
def test_closure_union_includes_modules_new_at_wave2(verify, make_w1):
    w = make_w1(w2={"benchmark/run.py": "from bench import helper, extra\n", "benchmark/bench/extra.py": "E = 1\n"})
    r = cw(verify, w)
    assert "benchmark/bench/extra.py" in r["closure_files"]
    assert r["files"] == ["benchmark/bench/extra.py", "benchmark/run.py"]


# class: new-behaviour (a file deleted at Wave 2 that the Wave 1 closure imported is a change)
def test_deleted_closure_file_flags(verify, make_w1):
    w = make_w1(w1_off={"benchmark/run.py": "from bench import helper, old\n", "benchmark/bench/old.py": "V = 1\n"},
                w2={"benchmark/bench/old.py": None})
    r = cw(verify, w)
    assert r["files"] == ["benchmark/bench/old.py"] and r["flag"] is True


# class: new-behaviour (a function-level import is part of the closure: python_closure follows it)
def test_function_level_import_is_in_the_closure(verify, make_w1):
    w = make_w1(w1_off={"benchmark/bench/run_reasoning.py": "def f():\n    from bench import lazy\n",
                        "benchmark/bench/lazy.py": "L = 1\n"},
                w2={"benchmark/bench/lazy.py": "L = 2\n"})
    r = cw(verify, w)
    assert r["files"] == ["benchmark/bench/lazy.py"] and r["flag"] is True


# class: invariant (the closure is computed on the COMMIT's tree, not the working tree: an uncommitted edit is invisible)
def test_working_tree_edits_are_ignored(verify, make_w1):
    w = make_w1()
    (w.repo / "benchmark" / "bench" / "helper.py").write_text("VALUE = 99\n")
    (w.repo / "main_models.yaml").write_text("changed: true\n")
    r = cw(verify, w)
    assert r["files"] == [] and r["flag"] is False


# class: invariant (the diff is run at the repo top: the result does not depend on the caller's cwd)
@pytest.mark.parametrize("where", ["sub", "outside"])
def test_cwd_does_not_matter(verify, make_w1, monkeypatch, tmp_path, where):
    w = make_w1(w2={"main_models.yaml": WW.registry_text(other="b"), "benchmark/bench/helper.py": "VALUE = 2\n"})
    here = w.repo / "benchmark" / "bench" if where == "sub" else tmp_path
    monkeypatch.chdir(here)
    r = cw(verify, w)
    assert r["files"] == ["benchmark/bench/helper.py", "main_models.yaml"] and r["flag"] is True


# class: new-behaviour (either commit unresolvable -> RefusalError)
@pytest.mark.parametrize("which", ["wave1", "wave2"])
def test_unresolvable_commit_refuses(verify, make_w1, which):
    w = make_w1()
    a, b = w.commits["w1_off"], w.commits["w2_off"]
    if which == "wave1":
        a = "ab" * 20
    else:
        b = "cd" * 20
    with pytest.raises(verify.RefusalError):
        verify.cross_wave(w.repo, a, b)


# class: invariant (read-only on the repo: HEAD, the index and the tree status are unchanged)
def test_cross_wave_does_not_touch_the_repo(verify, make_w1):
    w = make_w1(w2={"main_models.yaml": WW.registry_text(other="b")})
    before = (WW.git(w.repo, "rev-parse", "HEAD"), WW.git(w.repo, "status", "--porcelain"), WW.git(w.repo, "ls-files", "-s"))
    cw(verify, w)
    after = (WW.git(w.repo, "rev-parse", "HEAD"), WW.git(w.repo, "status", "--porcelain"), WW.git(w.repo, "ls-files", "-s"))
    assert before == after


# class: new-behaviour (the record is JSON-serialisable as is, and has no absolute path (temporary extraction dirs leak nowhere))
def test_record_is_json_and_has_no_absolute_path(verify, make_w1, tmp_path):
    w = make_w1(w2={"benchmark/bench/helper.py": "VALUE = 2\n"})
    blob = json.dumps(cw(verify, w), sort_keys=True)
    assert str(tmp_path) not in blob and str(w.repo) not in blob and "/private/" not in blob and "/var/folders" not in blob


# class: new-behaviour (verify_all carries the check: wave1_off = frozen stack_head_off, wave2_off = v8_base off_commit; flag is NOT a refusal)
def test_verify_all_records_the_cross_wave_check(verify, make_w1):
    w = make_w1(with_a7=True, w2={"main_models.yaml": WW.registry_text(other="b")})
    b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
    c = b8["cross_wave"]
    assert c["wave1_off"] == w.commits["w1_off"] and c["wave2_off"] == w.commits["w2_off"]
    assert c["files"] == ["main_models.yaml"] and c["flag"] is True
    assert V.accepted_all(b8) and all(p["accepted"] for p in b8["axes"]["A7"]["pairs"] if p.get("role") != "diagnostic")


# class: new-behaviour (verify_all without a code change records flag false; the Wave 1 and A7 members equal their own verifiers)
def test_verify_all_members_equal_their_verifiers(verify, make_w1):
    w = make_w1(with_a7=True)
    b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
    assert b8["cross_wave"]["flag"] is False
    assert set(b8["axes"]) == {"A7", "wave1"}
    assert b8["axes"]["A7"] == verify.verify_a7(w.p426)
    assert b8["axes"]["wave1"] == verify.verify_wave1(w.p426, w.rows_root, w.repo)
    # amended (delivery 3): the union is keyed relative to rows_root, so A7's results_root-relative keys may be re-keyed under `p426/`
    a7_keys = set(b8["axes"]["A7"]["inputs"])
    assert a7_keys and all(k in b8["inputs"] or "p426/" + k in b8["inputs"] for k in a7_keys)
    assert set(b8["axes"]["wave1"]["inputs"]) <= set(b8["inputs"])


# class: new-behaviour (a rejected Wave 1 pair does not stop verify_all: the record carries it with its reasons)
def test_verify_all_carries_rejected_pairs(verify, make_w1):
    w = make_w1(with_a7=True)
    w.edit_receipt("math500", "on", "b1", lambda d: d.update(verdict="INVALID"))
    b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
    assert [(p["kind"], V.digit(p["block"])) for p in V.rejected(b8)] == [("math500", "1")]
