"""S27 §12 (C371 (2), option B): a stack code push at level `full` is bound to the PASS receipt's `pushed_base` — the protected
files must be unchanged between it and the fetched `<remote>/main`; any git error refuses."""
from __future__ import annotations

from bench import arm_opencode, arm_specs
from bench import local_gate as G
from bench.tests.test_p541_push_level import _commit, _git, _hermetic, _level, _receipt, box  # noqa: F401  (fixtures)

PROTECTED = {"benchmark/opencode_bench_v2_web_tg1.json": "{}\n", "benchmark/opencode_plugins/noretry.js": "// n\n",
             "benchmark/opencode_plugins/toolbounds.js": "// t\n", "benchmark/opencode_plugins/datefreeze.js": "// d\n"}


def seeded(box):
    """The remote `main` holds the protected files; the gate ran against that base (`pushed_base`)."""
    base = _commit(box.work, PROTECTED, "protected files")
    _git(box.work, "push", "-q", "origin", "main")
    return base


def moved_remote(box, base, files):
    """The remote `main` moves after the gate ran against `base` (a push of `files`); the code commit then lands on top."""
    _commit(box.work, files, "remote moved")
    _git(box.work, "push", "-q", "origin", "main")
    _git(box.work, "fetch", "-q", "origin")


def test_the_protected_push_paths_are_the_closure_tests_four_files():
    assert set(G.protected_push_paths()) == set(PROTECTED) == set(arm_opencode.GENERATION_DATA)
    assert G.PROTECTED_PUSH_PATHS == tuple(arm_specs.OC.generation_data)


def test_a_moved_remote_main_with_the_protected_files_unchanged_is_accepted(box):
    base = seeded(box)
    moved_remote(box, base, {"docs/other.md": "x\n"})
    sha = _commit(box.work, {"code.py": "x = 3\n"})
    name = _receipt(box.gate, "stack", sha, pushed_base=base)
    assert _level(box, sha, "stack") == ("full", name, [])


def test_a_moved_remote_main_that_edits_datefreeze_is_refused(box):
    base = seeded(box)
    moved_remote(box, base, {"benchmark/opencode_plugins/datefreeze.js": "// changed\n"})
    sha = _commit(box.work, {"code.py": "x = 3\n"})
    _receipt(box.gate, "stack", sha, pushed_base=base)
    level, detail, problems = _level(box, sha, "stack")
    assert level == "full" and detail == "" and "datefreeze.js" in problems[0] and "regate" in problems[0]


def test_a_receipt_without_a_pushed_base_is_refused(box):
    seeded(box)
    sha = _commit(box.work, {"code.py": "x = 3\n"})
    _receipt(box.gate, "stack", sha)
    level, _, problems = _level(box, sha, "stack")
    assert level == "full" and problems and "pushed_base" in problems[0]


def test_a_pushed_base_absent_from_the_repo_is_refused(box):
    seeded(box)
    sha = _commit(box.work, {"code.py": "x = 3\n"})
    _receipt(box.gate, "stack", sha, pushed_base="f" * 40)
    _, _, problems = _level(box, sha, "stack")
    assert problems and "not a commit" in problems[0]


def test_a_non_main_pushed_ref_at_level_full_takes_the_same_rule(box):
    base = seeded(box)
    moved_remote(box, base, {"benchmark/opencode_plugins/datefreeze.js": "// changed\n"})
    sha = _commit(box.work, {"code.py": "x = 4\n"})
    _receipt(box.gate, "stack", sha, pushed_base=base)
    _, _, problems = _level(box, sha, "stack", remote_ref="refs/heads/feature")
    assert problems and "datefreeze.js" in problems[0]


def test_a_git_error_refuses(box, monkeypatch):
    base = seeded(box)
    sha = _commit(box.work, {"code.py": "x = 5\n"})
    _receipt(box.gate, "stack", sha, pushed_base=base)
    assert G.push_binding_problems(box.work, "no-such-remote", box.gate / f"stack-{sha}-{'d' * 12}.json", sha)


def test_forks_are_unchanged(box):
    sha = _commit(box.work, {"code.py": "x = 6\n"})
    name = _receipt(box.gate, "mlx-vlm", sha)
    assert _level(box, sha, "mlx-vlm") == ("full", name, [])
