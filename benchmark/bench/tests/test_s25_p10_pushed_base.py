"""S25-P10: a "this build" diff names a base that cannot be the build itself — GitHub's last-pushed `main` (the source repo's
`refs/remotes/origin/main`), recorded in the stack gate's receipt and exported to its pytest run as `GATE_PUSHED_BASE`; never
the local `main` (a gate from a non-`main` clone has none; a `main` that already contains the build makes the diff vacuous)."""
import json
import subprocess
from pathlib import Path

import pytest

from bench import local_gate as G
from bench.tests.test_m64_arm_closure import carrier_edits

CANON = "git@github.com:ivan-avramov/mlx_local_stack.git"
PLUGIN = "benchmark/opencode_plugins/datefreeze.js"


def _git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()


def _init(path):
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    _git(path, "config", "core.hooksPath", "/dev/null")


def _commit(path, files, msg="c"):
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", msg)
    return _git(path, "rev-parse", "HEAD")


@pytest.fixture
def stack(tmp_path):
    """A stack checkout whose pushed `main` (refs/remotes/origin/main) is `base`; local `main` = base + an edit of datefreeze.js."""
    repo = tmp_path / "ws" / "mlx_local_stack"
    _init(repo)
    base = _commit(repo, {PLUGIN: "v1\n", "benchmark/opencode_bench_v2_web_tg1.json": "{}\n"})
    head = _commit(repo, {PLUGIN: "v2\n"}, "the build edits a plugin")
    _git(repo, "remote", "add", "origin", CANON)
    _git(repo, "update-ref", G.PUSHED_REF, base)
    return dict(repo=repo, base=base, head=head)


# ------------------------------------------------------------------ the base
def test_pushed_base_is_the_source_repos_origin_main(stack):
    assert G.pushed_base(stack["repo"]) == stack["base"]


def test_pushed_base_refuses_without_origin_main(stack):
    _git(stack["repo"], "update-ref", "-d", G.PUSHED_REF)
    with pytest.raises(G.GateError, match="no pushed base"):
        G.pushed_base(stack["repo"])


def test_resolve_prefers_the_gate_export(stack):
    env = {G.PUSHED_BASE_ENV: stack["head"]}
    assert G.resolve_pushed_base(stack["repo"], env) == stack["head"]


def test_resolve_falls_back_to_origin_main_only_on_the_canonical_remote(stack):
    assert G.resolve_pushed_base(stack["repo"], {}) == stack["base"]


def test_a_non_main_clone_without_the_export_refuses_with_a_clear_message(stack, tmp_path):
    """The S25-P10 failure shape: a gate clone (origin = the local repository) of a branch, no local `main`, no export."""
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--no-checkout", str(stack["repo"]), str(clone)], check=True)
    _git(clone, "checkout", "-q", "--detach", stack["head"])
    _git(clone, "branch", "-D", "main")
    with pytest.raises(G.GateError, match=G.PUSHED_BASE_ENV):
        G.resolve_pushed_base(clone, {})


@pytest.mark.parametrize("value", ["HEAD", "main", "abc123", "z" * 40])
def test_the_export_must_be_a_full_sha(stack, value):
    with pytest.raises(G.GateError, match="full commit sha"):
        G.resolve_pushed_base(stack["repo"], {G.PUSHED_BASE_ENV: value})


def test_an_exported_base_absent_from_the_checkout_refuses(stack):
    with pytest.raises(G.GateError, match="not a commit"):
        G.resolve_pushed_base(stack["repo"], {G.PUSHED_BASE_ENV: "1" * 40})


# ------------------------------------------------------------------ the closure check against that base
def test_a_build_editing_datefreeze_is_caught_from_a_main_that_contains_it(stack):
    """The vacuous case: local `main` == HEAD contains the edit; the old merge-base(HEAD, main) diff was empty."""
    assert _git(stack["repo"], "merge-base", "HEAD", "main") == stack["head"]
    assert carrier_edits(stack["repo"], G.resolve_pushed_base(stack["repo"], {})) == [PLUGIN]


def test_no_edit_since_the_pushed_base_is_clean(stack):
    assert carrier_edits(stack["repo"], stack["head"]) == []


def test_carrier_edits_fails_closed_on_a_git_error(stack):
    with pytest.raises(subprocess.CalledProcessError):
        carrier_edits(stack["repo"], "1" * 40)


# ------------------------------------------------------------------ the gate records and exports it
def test_the_stack_pytest_step_exports_the_pushed_base(tmp_path):
    step = G.steps_for("stack", tmp_path / "s", parity=None, pushed_base="b" * 40)[-1]
    assert step.name == "pytest" and step.env[G.PUSHED_BASE_ENV] == "b" * 40


def test_without_a_base_the_export_is_removed_not_inherited(tmp_path):
    step = G.steps_for("stack", tmp_path / "s", parity=None)[-1]
    assert G.PUSHED_BASE_ENV in step.env and step.env[G.PUSHED_BASE_ENV] is None


def _gitlink(repo, path, sha):
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},{path}")


@pytest.fixture
def live(tmp_path):
    ws = tmp_path / "ws"
    links = {}
    for name in ("mlx-vlm", "mlx-serve"):
        _init(ws / name)
        links[name] = _commit(ws / name, {"x.txt": name})
    repo = ws / "mlx_local_stack"
    _init(repo)
    _commit(repo, {"a.txt": "a\n"})
    base_tree_commit = _git(repo, "rev-parse", "HEAD")
    _gitlink(repo, "src/mlx-vlm", links["mlx-vlm"])
    _gitlink(repo, "src/mlx-serve", links["mlx-serve"])
    _git(repo, "commit", "-q", "-m", "gitlinks")
    _git(repo, "remote", "add", "origin", CANON)
    # the pushed base is reachable ONLY from refs/remotes/origin/main (e.g. after a local history rewrite)
    _git(repo, "checkout", "-q", "-b", "old", base_tree_commit)
    pushed = _commit(repo, {"old.txt": "pre-rewrite\n"}, "pushed, later rewritten locally")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "branch", "-D", "old")
    _git(repo, "update-ref", G.PUSHED_REF, pushed)
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    (baselines / "stack.skips.txt").write_text("")
    return dict(repo=repo, sha=_git(repo, "rev-parse", "HEAD"), pushed=pushed, gate=tmp_path / "gate", baselines=baselines)


class EnvRunner:
    def __init__(self):
        self.pytest_env, self.base_in_scratch = None, None

    def __call__(self, argv, cwd, env):
        name = " ".join(argv)
        if "import mlx_vlm, mlx_serve" in name:
            return 0, f"{cwd}/src/mlx-vlm/mlx_vlm/__init__.py {cwd}/src/mlx-serve/src/mlx_serve/__init__.py"
        if "--junitxml" in name:
            self.pytest_env = dict(env)
            base = env.get(G.PUSHED_BASE_ENV)
            self.base_in_scratch = subprocess.run(["git", "-C", str(Path(cwd).parent), "cat-file", "-t", str(base)],
                                                  capture_output=True, text=True).stdout.strip()
            xml = next(a.split("=", 1)[1] for a in argv if a.startswith("--junitxml="))
            Path(xml).write_text("<testsuites><testsuite></testsuite></testsuites>")
        return 0, ""


def _run(live, runner):
    return G.run("stack", live["sha"], live=live["repo"], gate_dir=live["gate"], baselines=live["baselines"], runner=runner,
                 busy=lambda: [], dirty=lambda s, n: False, artifacts=lambda d: True)


def test_a_stack_run_records_the_pushed_base_and_exports_it_present_in_the_scratch(live):
    r = EnvRunner()
    doc = json.loads(Path(_run(live, r)).read_text())
    assert doc["verdict"] == "PASS", doc["problems"]
    assert doc["pushed_base"] == live["pushed"]
    assert r.pytest_env[G.PUSHED_BASE_ENV] == live["pushed"]
    assert r.base_in_scratch == "commit"


def test_a_stack_run_without_a_pushed_base_refuses_before_any_step(live):
    _git(live["repo"], "update-ref", "-d", G.PUSHED_REF)
    with pytest.raises(G.GateError, match="no pushed base"):
        _run(live, EnvRunner())
    assert not (live["gate"] / "scratch").exists() or not list((live["gate"] / "scratch").glob("*"))


# ------------------------------------------------------------------ cold read r1 (docs/reviews/s25-p10/)
def test_a_protected_file_renamed_away_is_an_edit_P2(stack):
    _git(stack["repo"], "mv", PLUGIN, "benchmark/opencode_plugins/datefreeze.old.js")
    _git(stack["repo"], "commit", "-q", "-m", "rename")
    assert PLUGIN in carrier_edits(stack["repo"], stack["head"])


def test_the_stack_pytest_step_drops_inherited_pytest_options_P1(tmp_path):
    env = G.steps_for("stack", tmp_path / "s", parity=None, pushed_base="b" * 40)[-1].env
    assert env["PYTEST_ADDOPTS"] is None and env["PYTEST_PLUGINS"] is None

