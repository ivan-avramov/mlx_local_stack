"""P311-lite (iii): the generation identity is the static import closure of the tg1 entry (spec tests 1, 3a-d, 3 scoring-edit)."""
import ast
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bench import identity_closure as ic

REPO = Path(__file__).resolve().parents[3]
ENTRY = "benchmark/run_tg1_probe.py"
SCORING = ("bench/answer_key.py", "web_audit.py", "web_audit_cursor.py", "bench/web_scan.py", "bench/tg1_score.py",
           "bench/row_scores.py", "bench/generate.py")


def tree(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


FIXED = {
    "benchmark/entry.py": "import json\nimport yaml\nfrom bench import a\nimport pkg.sub.leaf\n",
    "benchmark/bench/__init__.py": "",
    "benchmark/bench/a.py": "from . import b\nfrom .c import X\nfrom bench.fn import helper\n",
    "benchmark/bench/b.py": "def f():\n    import d\n    return d\n",
    "benchmark/bench/c.py": "X = 1\n",
    "benchmark/bench/fn.py": "def helper():\n    pass\n",
    "benchmark/d.py": "",
    "benchmark/pkg/__init__.py": "",
    "benchmark/pkg/sub/__init__.py": "",
    "benchmark/pkg/sub/leaf.py": "",
    "benchmark/unrelated.py": "import entry\n",
    "benchmark/data.txt": "data",
}
FIXED_CLOSURE = ["benchmark/bench/__init__.py", "benchmark/bench/a.py", "benchmark/bench/b.py", "benchmark/bench/c.py",
                 "benchmark/bench/fn.py", "benchmark/d.py", "benchmark/entry.py", "benchmark/pkg/__init__.py",
                 "benchmark/pkg/sub/__init__.py", "benchmark/pkg/sub/leaf.py"]
# Golden digest of the recipe (relpath + NUL + bytes, sorted relpaths, plus the data list) on the tree above.
FIXED_GOLDEN = "ed15015d90fc4ca4d390554c0477aa797b063ebfa38b4eee36c7af468f568e44"


def test_closure_on_a_fixed_tree(tmp_path):
    repo = tree(tmp_path, FIXED)
    got = ic.python_closure(repo / "benchmark/entry.py", repo)
    assert [p.relative_to(repo).as_posix() for p in got] == FIXED_CLOSURE


def test_digest_recipe_is_relpath_nul_bytes_over_sorted_paths_and_data(tmp_path):
    repo = tree(tmp_path, FIXED)
    want = hashlib.sha256()
    for rel in sorted(FIXED_CLOSURE + ["benchmark/data.txt"]):
        want.update(rel.encode() + b"\0")
        want.update((repo / rel).read_bytes())
    got = ic.closure_sha256("benchmark/entry.py", repo, data=["benchmark/data.txt"])
    assert got == want.hexdigest()
    assert ic.closure_sha256("benchmark/entry.py", repo) != got        # data inputs are part of the identity


def test_golden_value_on_the_fixed_tree(tmp_path):
    repo = tree(tmp_path, FIXED)
    assert ic.closure_sha256("benchmark/entry.py", repo, data=["benchmark/data.txt"]) == FIXED_GOLDEN


def test_an_edit_to_a_closure_file_changes_the_digest_an_edit_outside_does_not(tmp_path):
    repo = tree(tmp_path, FIXED)
    base = ic.closure_sha256("benchmark/entry.py", repo, data=["benchmark/data.txt"])
    (repo / "benchmark/unrelated.py").write_text("# edited\n")
    assert ic.closure_sha256("benchmark/entry.py", repo, data=["benchmark/data.txt"]) == base
    (repo / "benchmark/bench/c.py").write_text("X = 2\n")
    assert ic.closure_sha256("benchmark/entry.py", repo, data=["benchmark/data.txt"]) != base


def test_function_level_and_relative_imports_are_followed_and_missing_data_refuses(tmp_path):
    repo = tree(tmp_path, FIXED)
    assert (repo / "benchmark/d.py") in ic.python_closure(repo / "benchmark/entry.py", repo)
    with pytest.raises(FileNotFoundError):
        ic.closure_sha256("benchmark/entry.py", repo, data=["benchmark/nope.txt"])


def test_a_syntax_error_in_the_closure_fails_closed(tmp_path):
    repo = tree(tmp_path, {**FIXED, "benchmark/bench/c.py": "def (:\n"})
    with pytest.raises(SyntaxError):
        ic.python_closure(repo / "benchmark/entry.py", repo)


# ---- the real tg1 closure (spec 3a)
def real_closure():
    return {p.relative_to(REPO).as_posix() for p in ic.python_closure(REPO / ENTRY, REPO)}


def test_real_closure_excludes_scoring_and_legacy_generation():
    got = real_closure()
    for rel in ("benchmark/" + s for s in SCORING):
        assert rel not in got, rel
    assert {"benchmark/run_tg1_probe.py", "benchmark/bench/opencode_v2_core.py", "benchmark/bench/tg1_runner.py",
            "benchmark/bench/provenance.py", "benchmark/bench/deny_rules.py"} <= got


def imported_names(path):
    """[(resolved local module file, names bound by the import)] for module-level and function-level imports."""
    out = []
    tree_ = ast.parse(Path(path).read_text())
    for node in ast.walk(tree_):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for dest, bound in ic.import_edges(node, Path(path), REPO):
                out.append((dest, bound))
    return tree_, out


def test_every_closure_module_is_actually_used_by_an_importer():
    """Spec 3c: an import that nothing uses must not widen the identity. A module counts as used when some importer
    references a name the import bound (parent package inits are implied by their members)."""
    files = [REPO / rel for rel in real_closure()]
    used = {REPO / ENTRY}
    for path in files:
        tree_, edges = imported_names(path)
        refs = {n.id for n in ast.walk(tree_) if isinstance(n, ast.Name)}
        for dest, bound in edges:
            if dest.name == "__init__.py" or (bound & refs):
                used.add(dest)
    unused = sorted(p.relative_to(REPO).as_posix() for p in files
                    if p not in used and p.name != "__init__.py")
    assert not unused, unused


# ---- scoring-only edits do not move the identity (spec test 3)
@pytest.fixture(scope="module")
def repo_copy(tmp_path_factory):
    dest = tmp_path_factory.mktemp("repo")
    shutil.copytree(REPO / "benchmark", dest / "benchmark", ignore=shutil.ignore_patterns(
        "results", "tests", "__pycache__", "reviews", "*.jsonl", "*.pyc", "opencode_transcripts", "sessions"))
    return dest


def test_scoring_edits_leave_the_closure_digest_unchanged_and_generation_edits_change_it(repo_copy):
    from bench import tg1_runner
    sha = lambda: ic.closure_sha256(ENTRY, repo_copy, data=tg1_runner.GENERATION_DATA)    # noqa: E731
    base = sha()
    for rel in SCORING[:5] + ("web_audit_prompt.md",):
        path = repo_copy / "benchmark" / rel
        if not path.exists():
            continue
        original = path.read_bytes()
        path.write_bytes(original + b"\n# scoring-only edit\n")
        assert sha() == base, rel
        path.write_bytes(original)
    for rel in ("benchmark/bench/opencode_v2_core.py", "benchmark/bench/tg1_runner.py", "benchmark/run_tg1_probe.py",
                "benchmark/bench/provenance.py", "benchmark/opencode_plugins/toolbounds.js",
                "benchmark/opencode_plugins/noretry.js", "benchmark/opencode_bench_v2_web_tg1.json"):
        path = repo_copy / rel
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        assert sha() != base, rel
        path.write_bytes(original)
    assert sha() == base


def test_every_repo_local_module_loaded_by_a_fake_end_to_end_item_is_in_the_closure(tmp_path):
    """Spec 3b, the other direction: what the process really imports (dynamic imports included) is inside the
    static closure. Runs the mocked tg1 integration item in a fresh interpreter with no conftest."""
    out = tmp_path / "modules.json"
    env = {**__import__("os").environ, "P311_REPO": str(REPO), "P311_MODULES_OUT": str(out)}
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "--noconftest", "-p", "bench.tests.p311_modules_plugin",
         "-p", "no:cacheprovider", "-q",
         "bench/tests/test_tg1_integration.py::test_mocked_tg1_rows_evidence_resume_and_worker_drift"],
        cwd=REPO / "benchmark", env=env, capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    loaded = {m for m in __import__("json").loads(out.read_text())
              if not m.startswith("benchmark/bench/tests/") and "/__pycache__/" not in m}
    assert {"benchmark/run_tg1_probe.py", "benchmark/bench/tg1_runner.py", "benchmark/bench/proc_guard.py"} <= loaded
    outside = sorted(loaded - real_closure())
    assert not outside, outside


# ---- review L6: entry-rooted reachability (spec 3c), allow-list, runtime-path coverage
REACH = {
    "benchmark/entry.py": "from bench import a\nimport sys\n\ndef main():\n    a.used()\n",
    "benchmark/bench/__init__.py": "",
    "benchmark/bench/a.py": ("from . import b\n\ndef used():\n    return b.f()\n\n"
                              "def never_called():\n    import dead\n    return dead\n"),
    "benchmark/bench/b.py": "def f():\n    import lazy\n    return lazy\n",
    "benchmark/lazy.py": "X = 1\n",
    "benchmark/dead.py": "Y = 1\n",
}


def test_reachability_follows_calls_and_ignores_imports_in_never_referenced_functions(tmp_path):
    repo = tree(tmp_path, REACH)
    static = {p.relative_to(repo).as_posix() for p in ic.python_closure(repo / "benchmark/entry.py", repo)}
    assert "benchmark/dead.py" in static                               # the static walk sees every import
    reached = ic.reachable_modules(repo / "benchmark/entry.py", repo)
    assert "benchmark/lazy.py" in reached and "benchmark/dead.py" not in reached


def test_reachability_resolves_calls_through_an_injected_object(tmp_path):
    files = {**REACH, "benchmark/entry.py": "from bench import a\n\ndef main(p):\n    p.never_called()\n"}
    reached = ic.reachable_modules(tree(tmp_path, files) / "benchmark/entry.py", tmp_path)
    assert "benchmark/dead.py" in reached                              # `p.never_called` may be that function


# modules the static closure holds but no tg1 path in the real fake end-to-end run executes
RUNTIME_ALLOW = {
    "benchmark/bench/client.py": "provenance.gather's `router is None` branch (`router_block(client.BASE)`); the tg1 "
                                 "probe always passes the verified router, other callers of gather do not",
}


def test_every_real_closure_module_is_reachable_from_the_entry():
    reached = set(ic.reachable_modules(REPO / ENTRY, REPO))
    unreachable = sorted(real_closure() - reached)
    assert not unreachable, unreachable


def test_every_closure_module_is_loaded_by_the_fake_end_to_end_item_or_allow_listed(tmp_path):
    out = tmp_path / "modules.json"
    env = {**__import__("os").environ, "P311_REPO": str(REPO), "P311_MODULES_OUT": str(out)}
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "--noconftest", "-p", "bench.tests.p311_modules_plugin",
         "-p", "no:cacheprovider", "-q",
         "bench/tests/test_tg1_integration.py::test_mocked_tg1_rows_evidence_resume_and_worker_drift"],
        cwd=REPO / "benchmark", env=env, capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stdout[-1500:]
    loaded = set(__import__("json").loads(out.read_text()))
    never = sorted(real_closure() - loaded - set(RUNTIME_ALLOW))
    assert not never, never
    assert all(RUNTIME_ALLOW[k].strip() for k in RUNTIME_ALLOW) and set(RUNTIME_ALLOW) <= real_closure()
