"""M80 (`docs/specs/m80-gate-sibling-mlx-serve.md` v1): the mlx-vlm gate provides a sibling mlx-serve at a pinned commit,
records the pairing in the receipt and fails when a `requires_mlx_serve` test did not pass. Behaviour through the gate's seams
(`steps_for`, `run(..., runner=, busy=, dirty=, artifacts=)`, the receipt JSON, the junit file); the runner is a fake; git
plumbing runs for real against temporary repositories.

Test classes: (a) acceptance criterion 1 behaviour, red at the baseline; (b) interface detail of the specification;
(c) invariant that holds at the baseline and must keep holding.

Assumptions the specification leaves open (the implementer's choice; named here so a failure is read correctly):
  * `run(...)` takes the override as keyword `mlx_serve_sha=`; the CLI flag is `--mlx-serve-sha`.
  * the marked ids reach the gate either as a junit `<property name="requires_mlx_serve" .../>` inside the testcase or as a
    `--collect-only` listing of `path::name` node ids; the fake runner provides both.
  * `steps_for("mlx-vlm", scratch, ...)` receives the fork clone `<run>/mlx-vlm`; the sibling is `<run>/mlx-serve` (fix round).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bench import local_gate as G
from bench.tests.test_local_gate import _git, _repo

VLM_ORIGIN = "git@github.com:ivan-avramov/mlx-vlm"
M1 = ("mlx_vlm.tests.test_m76_b2_fe_common", "test_marked_one")
M2 = ("mlx_vlm.tests.test_m76_b2_fe_qualify", "test_marked_two")
U1 = ("mlx_vlm.tests.test_other", "test_unmarked")


def _id(c):
    return f"{c[0]}::{c[1]}"


def _node(c):
    return c[0].replace(".", "/") + ".py::" + c[1]


class SibRunner:
    """Records calls; at the pytest step snapshots the layout; writes a junit with marked / unmarked testcases."""

    def __init__(self, marked=(), passed=(), skipped=(), failed=(), listing=None, props=True, rcs=None, emulate_deselect=False):
        self.calls, self.layout, self.envs, self.emulate = [], None, [], emulate_deselect
        self.marked, self.passed, self.skipped, self.failed = marked, passed, skipped, failed
        self.listing, self.props, self.rcs = listing, props, rcs or {}

    def __call__(self, argv, cwd, env):
        self.calls.append((list(argv), Path(cwd)))
        self.envs.append(dict(env or {}))
        name = " ".join(argv)
        deselecting = False
        if self.emulate and argv[1:3] == ["-m", "pytest"]:
            # a PYTEST_ADDOPTS in the effective environment, or configured addopts left in force (no `-o addopts=`),
            # deselects the marked tests (the emulated hostile configuration)
            eff = {k: v for k, v in {**os.environ, **(env or {})}.items() if v is not None}
            cleared = "-o" in argv and argv[argv.index("-o") + 1] == "addopts="
            deselecting = "PYTEST_ADDOPTS" in eff or not cleared
        for key, rc in self.rcs.items():
            if key in name:
                return rc, f"{key} failed"
        if argv[:2] == ["git", "clone"] or argv[:3] == ["git", "-C", str(cwd)] and "clone" in argv:
            subprocess.run(argv, cwd=cwd, check=True, capture_output=True)  # a sibling step done through the runner
            return 0, ""
        if "--collect-only" in argv:
            ids = self.listing if self.listing is not None else self.marked
            if deselecting:
                return 5, "\nno tests collected (9 deselected) in 0.01s\n"
            return 0,"\n".join(_node(c) for c in ids) + "\n"
        if any(a.startswith("--junitxml=") for a in argv):
            xml = next(a.split("=", 1)[1] for a in argv if a.startswith("--junitxml="))
            parent = Path(cwd).parent
            sib = parent / "mlx-serve"
            self.layout = dict(cwd=Path(cwd), sibling=sib, sibling_head=(
                subprocess.run(["git", "-C", str(sib), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()))
            prop = '<properties><property name="requires_mlx_serve" value="true"/></properties>' if self.props else ""

            def case(c, body=""):
                p = prop if c in self.marked else ""
                return f'<testcase classname="{c[0]}" name="{c[1]}">{p}{body}</testcase>'

            keep = (lambda cs: [c for c in cs if c not in self.marked]) if deselecting else (lambda cs: list(cs))
            cases = [case(c, "<skipped/>") for c in keep(self.skipped)] + [case(c) for c in keep(self.passed)]
            cases += [case(c, '<failure message="boom"/>') for c in self.failed]
            Path(xml).write_text(f'<testsuites><testsuite>{"".join(cases)}</testsuite></testsuites>')
        return 0, ""

    def dirty(self, scratch, after_step):
        return False


@pytest.fixture
def world(tmp_path, monkeypatch):
    live = tmp_path / "live"
    serve = live / "mlx-serve"
    s1 = _repo(serve, {"pyproject.toml": "[project]\nname='s'\n", "uv.lock": "x\n"}, origin="git@github.com:ivan-avramov/mlx-serve")
    (serve / "second.txt").write_text("2\n")
    _git(serve, "add", "-A")
    _git(serve, "commit", "-q", "-m", "second")
    s2 = _git(serve, "rev-parse", "HEAD")      # the live mlx-serve HEAD is s2; the stack pins s1
    vlm = live / "mlx-vlm"
    vsha = _repo(vlm, {"pyproject.toml": "[project]\nname='v'\n", ".upstream-sync-ref": "952d4f6b\n"}, origin=VLM_ORIGIN)
    stack = live / "mlx_local_stack"
    _repo(stack, {"README.md": "x\n"}, origin="git@github.com:ivan-avramov/mlx_local_stack")
    _git(stack, "update-index", "--add", "--cacheinfo", f"160000,{s1},src/mlx-serve")
    _git(stack, "commit", "-q", "-m", "pin serve")
    monkeypatch.setattr(G, "_stack_repo", lambda: stack)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    base = tmp_path / "baselines"
    base.mkdir()
    (base / "mlx-vlm.skips.txt").write_text("")
    return dict(tmp=tmp_path, vlm=vlm, vsha=vsha, serve=serve, s1=s1, s2=s2, stack=stack, gate=tmp_path / "gate", base=base)


def _go(w, runner, **kw):
    path = G.run("mlx-vlm", w["vsha"], live=w["vlm"], gate_dir=w["gate"], baselines=w["base"], runner=runner,
                 busy=lambda: [], dirty=runner.dirty, artifacts=lambda d: True, **kw)
    return json.loads(Path(path).read_text())


def _problems(doc):
    return " | ".join(doc["problems"])


# ------------------------------------------------------------------ step list
# (a)
def test_mlx_vlm_steps_gain_sibling_and_sibling_sync_between_clone_and_sync(tmp_path):
    names = [s.name for s in G.steps_for("mlx-vlm", tmp_path / "p", parity="952d4f6b")]
    assert "sibling" in names and "sibling-sync" in names
    assert names.index("clone") < names.index("sibling") and names.index("sibling-sync") == names.index("sibling") + 1
    assert names.index("sibling-sync") < names.index("sync")
    assert names[-1] == "pytest"


# (b)
def test_sibling_sync_is_a_frozen_all_extras_uv_sync_in_the_sibling_clone(tmp_path):
    steps = {s.name: s for s in G.steps_for("mlx-vlm", tmp_path / "run" / "mlx-vlm", parity="952d4f6b")}
    sync = steps["sibling-sync"]
    assert sync.argv[:2] == ["uv", "sync"] and "--frozen" in sync.argv and "--all-extras" in sync.argv
    assert Path(sync.cwd) == tmp_path / "run" / "mlx-serve"
    assert Path(steps["sibling"].cwd) == tmp_path / "run" / "mlx-serve"


# (b)
def test_fork_steps_run_in_the_fork_directory_beside_the_sibling(tmp_path):
    fork = tmp_path / "run" / "mlx-vlm"
    steps = {s.name: s for s in G.steps_for("mlx-vlm", fork, parity="952d4f6b")}
    for n in ("sync", "extras", "pre-commit", "pytest"):
        assert Path(steps[n].cwd) == fork, n
    assert Path(steps["sibling-sync"].cwd).parent == fork.parent and Path(steps["sibling-sync"].cwd) != fork


# (c)
def test_the_remaining_mlx_vlm_steps_keep_their_relative_order_and_count_of_audits(tmp_path):
    names = [s.name for s in G.steps_for("mlx-vlm", tmp_path / "p", parity="952d4f6b")]
    rest = [n for n in names if n not in ("sibling", "sibling-sync")]
    assert rest == ["clone", "upstream", "sync", "extras", "pre-commit", *[f"audit:{i}" for i in range(8)], "pytest"]


# (c) byte-identical stack / mlx-serve step lists (expected values copied from the baseline code)
def test_stack_steps_are_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", "/wd")
    monkeypatch.setenv("NLTK_DATA", "/nl")
    s = tmp_path / "s"
    py = str(s / ".venv-bench" / "bin" / "python")
    got = [(x.name, x.argv, x.cwd, x.env, x.check) for x in G.steps_for("stack", s, parity=None)]
    assert got == [
        ("clone", [], s, {}, None),
        ("submodules", [], s, {}, None),
        ("venv", ["uv", "venv", "--python", "3.12", "--python-preference", "only-managed", str(s / ".venv-bench")], s, {}, None),
        ("venv-sync", ["uv", "pip", "sync", "--python", py, "benchmark/requirements-bench.lock"], s, {}, None),
        ("imports", [py, "-c", "import mlx_vlm, mlx_serve; print(mlx_vlm.__file__, mlx_serve.__file__)"], s, {}, "imports"),
        ("pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={s / '.gate-junit.xml'}", "bench/tests/"],
         s / "benchmark", dict(STACK_WORKDIR="/wd", NLTK_DATA="/nl"), None),
    ]


# (c)
def test_mlx_serve_steps_are_unchanged(tmp_path):
    s = tmp_path / "s"
    got = [(x.name, x.argv, x.cwd, x.env, x.check) for x in G.steps_for("mlx-serve", s, parity=None)]
    assert got == [
        ("clone", [], s, {}, None),
        ("sync", ["uv", "sync", "--python", "3.12", "--locked", "--extra", "dev", "--extra", "all"], s, {}, None),
        ("ruff-check", ["uv", "run", "--no-sync", "ruff", "check", "src/"], s, {}, None),
        ("ruff-format", ["uv", "run", "--no-sync", "ruff", "format", "--check", "src/", "tests/"], s, {}, None),
        ("pytest", ["uv", "run", "--no-sync", "pytest", "-q", f"--junitxml={s / '.gate-junit.xml'}", "tests/"], s, {}, None),
        ("build", ["uv", "build", "--out-dir", str(s / ".gate-dist")], s, {}, "artifacts"),
    ]


# ------------------------------------------------------------------ run: layout and pin
# (a)
def test_a_run_has_the_fork_and_the_sibling_in_one_per_run_directory_at_the_pytest_step(world):
    r = SibRunner(passed=[U1])
    doc = _go(world, r)
    assert doc["verdict"] == "PASS", doc["problems"]
    lay = r.layout
    assert lay["cwd"].name == "mlx-vlm" and lay["sibling"] == lay["cwd"].parent / "mlx-serve"
    assert lay["cwd"].parent.parent == world["gate"] / "scratch"
    assert lay["cwd"].parent.name.startswith(f"mlx-vlm-{world['vsha'][:12]}-")
    assert [s["name"] for s in doc["steps"]].count("sibling") == 1
    assert [s["name"] for s in doc["steps"]].count("sibling-sync") == 1


# (a)
def test_the_sibling_is_checked_out_at_the_stack_head_gitlink_by_default(world):
    r = SibRunner(passed=[U1])
    doc = _go(world, r)
    assert r.layout["sibling_head"] == world["s1"] != world["s2"]
    assert doc["paired"] == {"mlx-serve": world["s1"]}


# (a)
def test_the_flag_overrides_the_gitlink(world):
    r = SibRunner(passed=[U1])
    doc = _go(world, r, mlx_serve_sha=world["s2"])
    assert doc["verdict"] == "PASS", doc["problems"]
    assert r.layout["sibling_head"] == world["s2"]
    assert doc["paired"] == {"mlx-serve": world["s2"]}


# (a)
def test_a_pass_removes_the_whole_per_run_directory(world):
    _go(world, SibRunner(passed=[U1]))
    assert not list((world["gate"] / "scratch").glob("*"))


# (a)
def test_a_fail_also_removes_both_clones(world):
    doc = _go(world, SibRunner(passed=[U1], rcs={"--all-extras": 1}))
    assert doc["verdict"] == "FAIL"
    assert not list((world["gate"] / "scratch").glob("*"))


# (a)
def test_a_failing_sibling_sync_fails_before_the_fork_is_synced(world):
    r = SibRunner(passed=[U1], rcs={"--all-extras": 1})
    doc = _go(world, r)
    names = [s["name"] for s in doc["steps"]]
    assert doc["verdict"] == "FAIL" and names[-1] == "sibling-sync" and "pytest" not in names


def _refusal(world, runner, **kw):
    """The refusal is a GateError or a FAIL receipt with the problem; either way no fork step ran."""
    try:
        doc = _go(world, runner, **kw)
    except G.GateError as exc:
        return str(exc)
    assert doc["verdict"] == "FAIL"
    return _problems(doc)


# (a)
def test_an_override_sha_absent_from_the_sibling_is_refused(world):
    r = SibRunner(passed=[U1])
    msg = _refusal(world, r, mlx_serve_sha="f" * 40)
    assert "f" * 40 in msg or "f" * 8 in msg
    assert r.layout is None and not any("pytest" in " ".join(a) for a, _ in r.calls)


# (a)
def test_a_stack_gitlink_absent_from_the_sibling_is_refused(world):
    bogus = "e" * 40
    _git(world["stack"], "update-index", "--cacheinfo", f"160000,{bogus},src/mlx-serve")
    _git(world["stack"], "commit", "-q", "-m", "pin bogus")
    r = SibRunner(passed=[U1])
    msg = _refusal(world, r)
    assert bogus in msg or bogus[:8] in msg
    assert r.layout is None


# (b)
def test_the_cli_flag_reaches_run(world, monkeypatch):
    seen = {}

    class L:
        def release(self):
            pass

    monkeypatch.setattr(G, "_hold_running", lambda wd: L())

    def fake_run(repo, sha, **kw):
        seen.update(repo=repo, values=[sha, *kw.values()])
        p = world["tmp"] / "r.json"
        p.write_text(json.dumps(dict(verdict="PASS", problems=[])))
        return p

    monkeypatch.setattr(G, "run", fake_run)
    assert G.main(["run", "--repo", "mlx-vlm", "--mlx-serve-sha", world["s2"]]) == 0
    assert seen["repo"] == "mlx-vlm" and world["s2"] in seen["values"]


# ------------------------------------------------------------------ receipt
# (a)
def test_paired_is_recorded_only_for_mlx_vlm(world):
    doc = _go(world, SibRunner(passed=[U1]))
    assert set(doc["paired"]) == {"mlx-serve"} and len(doc["paired"]["mlx-serve"]) == 40


# (c)
def test_the_mlx_serve_receipt_has_no_pairing(world):
    live = world["serve"]
    from bench.tests.test_local_gate import Runner

    r = Runner()
    path = G.run("mlx-serve", world["s2"], live=live, gate_dir=world["gate"], baselines=world["base"], runner=r,
                 busy=lambda: [], dirty=r.dirty, artifacts=lambda d: True)
    assert "paired" not in json.loads(Path(path).read_text())


# (a)
def test_the_policy_digest_does_not_cover_the_pinned_sha(world):
    d1 = _go(world, SibRunner(passed=[U1]))["policy_digest"]
    d2 = _go(world, SibRunner(passed=[U1]), mlx_serve_sha=world["s2"])["policy_digest"]
    assert d1 == d2


# (b)
def test_a_pass_receipt_is_accepted_whatever_sha_it_paired(world):
    doc = _go(world, SibRunner(passed=[U1]), mlx_serve_sha=world["s2"])
    gate = world["gate"]
    assert G.has_pass(gate, "mlx-vlm", world["vsha"], doc["policy_digest"])
    path = next(gate.glob(f"mlx-vlm-{world['vsha']}-*.json"))
    assert json.loads(path.read_text())["paired"] == {"mlx-serve": world["s2"]}


# ------------------------------------------------------------------ requires_mlx_serve rule
# (a)
def test_all_marked_tests_passed_is_a_pass(world):
    doc = _go(world, SibRunner(marked=[M1, M2], passed=[M1, M2, U1]))
    assert doc["verdict"] == "PASS" and doc["problems"] == []


# (a): the marked skip is baselined, so only the new rule can fail it
def test_a_skipped_marked_test_fails_even_when_the_baseline_lists_it(world):
    (world["base"] / "mlx-vlm.skips.txt").write_text(_id(M1) + "\n")
    doc = _go(world, SibRunner(marked=[M1, M2], skipped=[M1], passed=[M2]))
    assert doc["verdict"] == "FAIL"
    assert "requires_mlx_serve tests skipped" in _problems(doc) and _id(M1) in _problems(doc)
    assert _id(M2) not in _problems(doc).split("requires_mlx_serve tests skipped")[1]


# (a)
def test_a_marked_test_absent_from_the_junit_but_collected_fails(world):
    doc = _go(world, SibRunner(marked=[M1, M2], passed=[M1, U1]))
    assert doc["verdict"] == "FAIL"
    assert "requires_mlx_serve tests skipped" in _problems(doc) and _id(M2) in _problems(doc)


# (a): the same test, collection channel only (the junit carries no marker information)
def test_a_marked_test_known_only_from_the_collect_listing_that_skipped_fails(world):
    (world["base"] / "mlx-vlm.skips.txt").write_text(_id(M1) + "\n")
    doc = _go(world, SibRunner(marked=[M1], skipped=[M1], props=False))
    assert doc["verdict"] == "FAIL" and "requires_mlx_serve tests skipped" in _problems(doc)


# (a)
def test_a_failed_marked_test_does_not_pass_the_gate(world):
    doc = _go(world, SibRunner(marked=[M1], failed=[M1], passed=[U1]))
    assert doc["verdict"] == "FAIL"


# (c)
def test_an_unmarked_skip_outside_the_baseline_still_fails_with_todays_message(world):
    doc = _go(world, SibRunner(marked=[M1], passed=[M1], skipped=[U1]))
    assert doc["verdict"] == "FAIL" and f"skip list != baseline: +['{_id(U1)}']" in _problems(doc)
    assert "requires_mlx_serve" not in _problems(doc)


# (c)
def test_no_marked_tests_and_no_skips_is_a_pass(world):
    doc = _go(world, SibRunner(passed=[U1]))
    assert doc["verdict"] == "PASS"


# ------------------------------------------------------------------ the temporary baseline entries
# (a) acceptance 2, the file part
def test_the_baseline_has_no_m76_b2_entries_left():
    text = (Path(__file__).resolve().parents[2] / "gate" / "mlx-vlm.skips.txt").read_text()
    left = [l for l in text.splitlines() if "test_m76_b2_" in l]
    assert left == []


# ------------------------------------------------------------------ fix round: no unpaired path, hardened pytest calls
# (a)
@pytest.mark.parametrize("pin", [False, True])
def test_with_no_sibling_checkout_the_run_is_refused_before_any_step_and_leaves_no_receipt(world, pin):
    s1 = world["s1"]
    shutil.rmtree(world["serve"])
    r = SibRunner(passed=[U1])
    with pytest.raises(G.GateError):
        _go(world, r, **({"mlx_serve_sha": s1} if pin else {}))
    assert r.calls == []
    assert not list(world["gate"].glob("*.json")) if world["gate"].exists() else True
    assert not (world["gate"] / "scratch").exists() or not list((world["gate"] / "scratch").glob("*"))


# (a)
def test_the_mlx_vlm_step_list_has_the_sibling_whatever_the_scratch_is_called(tmp_path):
    for name in ("s", "scratch", "mlx-vlm"):
        names = [s.name for s in G.steps_for("mlx-vlm", tmp_path / name, parity="952d4f6b")]
        assert names.index("clone") < names.index("sibling") < names.index("sibling-sync") < names.index("sync"), name


@pytest.fixture
def marked_world(world):
    """The fork's test sources use the marker."""
    tests = world["vlm"] / "mlx_vlm" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_b2.py").write_text("import pytest\n\n\n@pytest.mark.requires_mlx_serve\ndef test_x():\n    pass\n")
    _git(world["vlm"], "add", "-A")
    _git(world["vlm"], "commit", "-q", "-m", "marked")
    return dict(world, vsha=_git(world["vlm"], "rev-parse", "HEAD"))


# (a)
def test_both_pytest_calls_drop_the_pytest_env_and_clear_configured_addopts(marked_world):
    r = SibRunner(marked=[M1], passed=[M1])
    doc = _go(marked_world, r)
    assert doc["verdict"] == "PASS", doc["problems"]
    pyts = [(a, e) for (a, _), e in zip(r.calls, r.envs) if a[1:3] == ["-m", "pytest"]]
    assert len(pyts) == 2 and sum("--collect-only" in a for a, _ in pyts) == 1
    for argv, env in pyts:
        assert "-o" in argv and argv[argv.index("-o") + 1] == "addopts="
        assert "PYTEST_ADDOPTS" in env and env["PYTEST_ADDOPTS"] is None
        assert "PYTEST_PLUGINS" in env and env["PYTEST_PLUGINS"] is None


# (a): through the real runner, the suite step's env really removes the variables from the child
def test_the_suite_step_env_removes_the_pytest_variables_from_a_real_child(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-m 'not requires_mlx_serve'")
    monkeypatch.setenv("PYTEST_PLUGINS", "x")
    step = next(s for s in G.steps_for("mlx-vlm", tmp_path / "run" / "mlx-vlm", parity="952d4f6b") if s.name == "pytest")
    probe = "import os; print(sorted(k for k in ('PYTEST_ADDOPTS', 'PYTEST_PLUGINS') if k in os.environ))"
    rc, out = G._real_runner(["python3", "-c", probe], tmp_path, step.env)
    assert rc == 0 and out.strip() == "[]"


# (a): the emulated hostile configuration empties the marked set and the junit alike unless the gate neutralises it
def test_a_deselecting_pytest_addopts_in_the_environment_cannot_empty_the_marked_set(marked_world, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-m 'not requires_mlx_serve'")
    r = SibRunner(marked=[M1], passed=[M1, U1], emulate_deselect=True)
    doc = _go(marked_world, r)
    assert doc["verdict"] == "PASS", doc["problems"]
    assert doc.get("requires_mlx_serve_tests") == 1


# (a)
def test_marker_in_the_sources_but_an_empty_listing_fails(marked_world):
    doc = _go(marked_world, SibRunner(marked=[], passed=[U1]))
    assert doc["verdict"] == "FAIL"
    assert "marked tests expected but none collected" in _problems(doc)


# (c)
def test_marker_absent_from_the_sources_and_an_empty_listing_is_not_a_problem(world):
    doc = _go(world, SibRunner(marked=[], passed=[U1]))
    assert doc["verdict"] == "PASS", doc["problems"]


# (a)
def test_a_deselected_marked_test_fails_the_gate(marked_world):
    doc = _go(marked_world, SibRunner(marked=[M1, M2], listing=[M1, M2], passed=[M1, U1]))
    assert doc["verdict"] == "FAIL"
    assert "requires_mlx_serve tests skipped" in _problems(doc) and _id(M2) in _problems(doc)
