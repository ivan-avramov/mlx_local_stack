"""M80 (`docs/specs/m80-gate-sibling-mlx-serve.md`): the mlx-vlm gate clones a sibling mlx-serve at a pinned sha beside the
fork clone, records the pairing, and fails when a `requires_mlx_serve` test did not pass. Runner mocked; git runs for real
against temporary repositories (no network)."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from bench import local_gate as G

MARKED = ("mlx_vlm.tests.test_b2", "test_needs_serve")
PLAIN = ("mlx_vlm.tests.test_other", "test_plain")


def _git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()


def _repo(path, files, origin=None):
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    _git(path, "config", "core.hooksPath", "/dev/null")
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    if origin:
        _git(path, "remote", "add", "origin", origin)
    return _git(path, "rev-parse", "HEAD")


def _commit(path, rel, text):
    (path / rel).write_text(text)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", rel)
    return _git(path, "rev-parse", "HEAD")


def _stack_with_gitlink(path, sha):
    _repo(path, {"README.md": "stack\n"})
    _git(path, "update-index", "--add", "--cacheinfo", f"160000,{sha},src/mlx-serve")
    _git(path, "commit", "-q", "-m", "gitlink")
    return path


class Runner:
    """pytest writes `cases` (classname, name, outcome, marked-property) to the junit; the marker listing prints `listing`."""

    def __init__(self, cases=(), listing="", listing_rc=0):
        self.calls, self.cases, self.listing, self.listing_rc = [], cases, listing, listing_rc
        self.sibling_head = None

    def __call__(self, argv, cwd, env):
        self.calls.append((list(argv), Path(cwd)))
        if argv[:2] == ["uv", "sync"] and "--frozen" in argv:
            self.sibling_head = _git(cwd, "rev-parse", "HEAD")
        if "--collect-only" in argv:
            return self.listing_rc, self.listing
        xml = next((a.split("=", 1)[1] for a in argv if a.startswith("--junitxml=")), None)
        if xml:
            body = ""
            for c, n, outcome, prop in self.cases:
                inner = "<skipped/>" if outcome == "skipped" else ""
                if prop:
                    inner = f'<properties><property name="{G.SIBLING_MARKER}" value="1"/></properties>' + inner
                body += f'<testcase classname="{c}" name="{n}">{inner}</testcase>'
            Path(xml).write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")
        return 0, ""


def _listing(*ids):
    lines = [f"{c.replace('.', '/')}.py::{n}" for c, n in ids]
    return "\n".join(lines + ["", f"{len(ids)}/9 tests collected ({9 - len(ids)} deselected) in 0.01s"]) + "\n"


@pytest.fixture
def box(tmp_path, monkeypatch):
    live = tmp_path / "live" / "mlx-vlm"
    sha = _repo(live, {".upstream-sync-ref": "2ceff4c1\n", "a.py": "x = 1\n"}, origin="git@github.com:ivan-avramov/mlx-vlm")
    serve = tmp_path / "live" / "mlx-serve"
    s1 = _repo(serve, {"pyproject.toml": "[project]\nname='s'\n"})
    s2 = _commit(serve, "b.txt", "two\n")      # serve HEAD; the gitlink pins s1
    stack = _stack_with_gitlink(tmp_path / "stack", s1)
    monkeypatch.setattr(G, "_stack_repo", lambda: stack)
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    (baselines / "mlx-vlm.skips.txt").write_text("")
    return dict(live=live, sha=sha, serve=serve, s1=s1, s2=s2, stack=stack, gate=tmp_path / "gate", baselines=baselines)


def _run(box, runner, **kw):
    return Path(G.run("mlx-vlm", box["sha"], live=box["live"], gate_dir=box["gate"], baselines=box["baselines"], runner=runner,
                      busy=lambda: [], dirty=lambda s, n: False, artifacts=lambda d: True, **kw))


def _doc(path):
    return json.loads(Path(path).read_text())


# ------------------------------------------------------------------ steps
def test_the_mlx_vlm_steps_add_sibling_and_sibling_sync_after_clone_in_the_per_run_layout(tmp_path):
    fork = tmp_path / "run" / "mlx-vlm"
    steps = G.steps_for("mlx-vlm", fork, parity="2ceff4c1")
    names = [s.name for s in steps]
    assert names[:3] == ["clone", "sibling", "sibling-sync"]
    assert names.index("sibling-sync") < names.index("sync")
    sib, sync = steps[1], steps[2]
    assert sib.cwd == sync.cwd == tmp_path / "run" / "mlx-serve" and sib.argv == []
    assert sync.argv == ["uv", "sync", "--frozen", "--all-extras"]
    assert steps[0].cwd == fork and steps[-1].name == "pytest" and steps[-1].cwd == fork


@pytest.mark.parametrize("name", ["s", "scratch", "mlx-vlm"])   # pairing does not depend on the scratch's name
def test_the_mlx_vlm_steps_always_include_the_sibling(tmp_path, name):
    names = [s.name for s in G.steps_for("mlx-vlm", tmp_path / name, parity="2ceff4c1")]
    assert names[:6] == ["clone", "sibling", "sibling-sync", "upstream", "sync", "extras"]


def test_both_mlx_vlm_pytest_invocations_ignore_configured_addopts_and_pytest_env(box):
    r = Runner(listing=_listing())
    _run(box, r)
    suite = next(s for s in G.steps_for("mlx-vlm", Path("/x/mlx-vlm"), "2ceff4c1") if s.name == "pytest")
    assert suite.env == {"PYTEST_ADDOPTS": None, "PYTEST_PLUGINS": None}
    pytests = [(a, c) for a, c in r.calls if a[1:3] == ["-m", "pytest"]]
    assert len(pytests) == 2 and any("--collect-only" in a for a, _ in pytests)
    for argv, _ in pytests:
        i = argv.index("-o")
        assert argv[i + 1] == "addopts="


def test_the_real_runner_removes_variables_given_as_none(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-m 'not requires_mlx_serve'")
    monkeypatch.setenv("PYTEST_PLUGINS", "x")
    probe = "import os; print(sorted(k for k in ('PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'KEEP') if k in os.environ))"
    rc, out = G._real_runner(["python3", "-c", probe], tmp_path, dict(G.PYTEST_ENV_DROP, KEEP="1"))
    assert rc == 0 and out.strip() == "['KEEP']"


def _today_stack(s, wd):
    py = str(s / ".venv-bench" / "bin" / "python")
    junit = f"--junitxml={s / '.gate-junit.xml'}"
    return [
        G.Step("clone", [], s), G.Step("submodules", [], s),
        G.Step("venv", ["uv", "venv", "--python", "3.12", "--python-preference", "only-managed", str(s / ".venv-bench")], s),
        G.Step("venv-sync", ["uv", "pip", "sync", "--python", py, "benchmark/requirements-bench.lock"], s),
        G.Step("imports", [py, "-c", "import mlx_vlm, mlx_serve; print(mlx_vlm.__file__, mlx_serve.__file__)"], s,
               check="imports"),
        G.Step("pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", junit, "bench/tests/"], s / "benchmark",
               env=dict(STACK_WORKDIR=wd, NLTK_DATA=os.environ.get("NLTK_DATA", ""), GATE_PUSHED_BASE=None,
                       PYTEST_ADDOPTS=None, PYTEST_PLUGINS=None)),  # S25-P10
    ]


def _today_serve(s):
    junit = f"--junitxml={s / '.gate-junit.xml'}"
    return [
        G.Step("clone", [], s),
        G.Step("sync", ["uv", "sync", "--python", "3.12", "--locked", "--extra", "dev", "--extra", "all"], s),
        G.Step("ruff-check", ["uv", "run", "--no-sync", "ruff", "check", "src/"], s),
        G.Step("ruff-format", ["uv", "run", "--no-sync", "ruff", "format", "--check", "src/", "tests/"], s),
        G.Step("pytest", ["uv", "run", "--no-sync", "pytest", "-q", junit, "tests/"], s),
        G.Step("build", ["uv", "build", "--out-dir", str(s / ".gate-dist")], s, check="artifacts"),
    ]


@pytest.mark.parametrize("name", ["s", "mlx-vlm"])   # even a scratch named like the fork clone changes nothing
def test_stack_and_mlx_serve_step_lists_are_identical_to_today(tmp_path, monkeypatch, name):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    s = tmp_path / name
    assert G.steps_for("stack", s, None) == _today_stack(s, str(tmp_path / "wd"))
    assert G.steps_for("mlx-serve", s, None) == _today_serve(s)


# ------------------------------------------------------------------ the pinned sha
def test_the_pin_defaults_to_the_stack_head_gitlink(box):
    assert G.pinned_mlx_serve(box["live"]) == box["s1"]
    assert G.pinned_mlx_serve(box["live"], stack=box["stack"]) == box["s1"]


def test_the_pin_override_wins_and_is_resolved_to_the_full_sha(box):
    assert G.pinned_mlx_serve(box["live"], box["s2"][:10]) == box["s2"]
    assert G.pinned_mlx_serve(box["live"], box["s2"]) == box["s2"]


@pytest.mark.parametrize("override", ["d" * 40, "--batch", "HEAD", "main"])
def test_an_absent_or_non_sha_override_is_refused(box, override):
    with pytest.raises(G.GateError):
        G.pinned_mlx_serve(box["live"], override)


def test_a_gitlink_absent_from_the_local_mlx_serve_is_refused(box, tmp_path):
    stack = _stack_with_gitlink(tmp_path / "stack2", "e" * 40)
    with pytest.raises(G.GateError, match="not a commit"):
        G.pinned_mlx_serve(box["live"], stack=stack)


def test_a_stack_head_without_the_gitlink_is_refused(box, tmp_path):
    stack = tmp_path / "bare-stack"
    _repo(stack, {"README.md": "x\n"})
    with pytest.raises(G.GateError, match="gitlink"):
        G.pinned_mlx_serve(box["live"], stack=stack)


def test_run_refuses_an_absent_pin_before_any_step_and_writes_no_receipt(box):
    r = Runner()
    with pytest.raises(G.GateError, match="not a commit"):
        _run(box, r, mlx_serve_sha="d" * 40)
    assert r.calls == [] and not box["gate"].exists()


def test_the_pin_is_mlx_vlm_only(box, tmp_path):
    live = tmp_path / "live2" / "mlx-serve"
    sha = _repo(live, {"pyproject.toml": "x\n"}, origin="git@github.com:ivan-avramov/mlx-serve")
    with pytest.raises(G.GateError, match="mlx-vlm run only"):
        G.run("mlx-serve", sha, live=live, gate_dir=box["gate"], baselines=box["baselines"], runner=Runner(),
              busy=lambda: [], dirty=lambda s, n: False, artifacts=lambda d: True, mlx_serve_sha=box["s1"])


# ------------------------------------------------------------------ run: layout, pairing, receipt
def test_a_paired_run_clones_the_sibling_at_the_pin_beside_the_fork_and_records_it(box):
    r = Runner(cases=[PLAIN + ("passed", False)])
    doc = _doc(_run(box, r))
    assert doc["verdict"] == "PASS", doc["problems"]
    assert doc["paired"] == {"mlx-serve": box["s1"]}
    assert [s["name"] for s in doc["steps"]][:3] == ["clone", "sibling", "sibling-sync"]
    assert r.sibling_head == box["s1"]                    # the pinned commit, not the sibling's HEAD (s2)
    sync_cwd = next(cwd for argv, cwd in r.calls if argv[:2] == ["uv", "sync"] and "--frozen" in argv)
    fork_cwd = next(cwd for argv, cwd in r.calls if any(a.startswith("--junitxml=") for a in argv))
    assert sync_cwd.name == "mlx-serve" and fork_cwd.name == "mlx-vlm" and sync_cwd.parent == fork_cwd.parent
    assert fork_cwd.parent.parent == box["gate"] / "scratch"
    assert fork_cwd.parent.name.startswith(f"mlx-vlm-{box['sha'][:12]}-")
    assert not list((box["gate"] / "scratch").iterdir())  # the whole per-run directory is removed


def test_the_override_pin_is_used_and_recorded(box):
    r = Runner()
    doc = _doc(_run(box, r, mlx_serve_sha=box["s2"]))
    assert doc["verdict"] == "PASS" and doc["paired"] == {"mlx-serve": box["s2"]} and r.sibling_head == box["s2"]


def test_a_failing_sibling_sync_fails_the_run_and_still_cleans_up(box):
    class R(Runner):
        def __call__(self, argv, cwd, env):
            rc, out = super().__call__(argv, cwd, env)
            return (1, "lock mismatch") if "--frozen" in argv else (rc, out)

    doc = _doc(_run(box, R()))
    assert doc["verdict"] == "FAIL" and doc["problems"] == ["sibling-sync: rc 1"] and doc["paired"]
    assert not list((box["gate"] / "scratch").iterdir())


def test_a_mlx_serve_receipt_has_no_pairing(tmp_path):
    live = tmp_path / "live" / "mlx-serve"
    sha = _repo(live, {"pyproject.toml": "x\n"}, origin="git@github.com:ivan-avramov/mlx-serve")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "mlx-serve.skips.txt").write_text("")
    doc = _doc(G.run("mlx-serve", sha, live=live, gate_dir=tmp_path / "gate", baselines=tmp_path / "b", runner=Runner(),
                     busy=lambda: [], dirty=lambda s, n: False, artifacts=lambda d: True))
    assert doc["verdict"] == "PASS" and "paired" not in doc and f"{G.SIBLING_MARKER}_tests" not in doc


@pytest.fixture
def lone(box, tmp_path):
    """An mlx-vlm fork with no `../mlx-serve` at all."""
    live = tmp_path / "alone" / "mlx-vlm"
    sha = _repo(live, {".upstream-sync-ref": "2ceff4c1\n"}, origin="git@github.com:ivan-avramov/mlx-vlm")
    return dict(box, live=live, sha=sha)


@pytest.mark.parametrize("pin", [None, "s1"])
def test_with_no_mlx_serve_checkout_the_run_is_refused_before_any_step(lone, pin):
    r = Runner(cases=[PLAIN + ("passed", False)])
    with pytest.raises(G.GateError, match="no mlx-serve checkout"):
        _run(lone, r, **({"mlx_serve_sha": lone[pin]} if pin else {}))
    assert r.calls == [] and not lone["gate"].exists()


def test_a_directory_named_mlx_serve_that_is_no_repository_is_refused(lone):
    (lone["live"].parent / "mlx-serve").mkdir()
    with pytest.raises(G.GateError, match="no mlx-serve checkout"):
        _run(lone, Runner())


# ------------------------------------------------------------------ requires_mlx_serve must pass
def test_a_marked_test_that_passed_keeps_the_run_green(box):
    doc = _doc(_run(box, Runner(cases=[MARKED + ("passed", False), PLAIN + ("passed", False)], listing=_listing(MARKED))))
    assert doc["verdict"] == "PASS" and doc[f"{G.SIBLING_MARKER}_tests"] == 1


def test_a_skipped_marked_test_from_the_listing_fails(box):
    (box["baselines"] / "mlx-vlm.skips.txt").write_text("::".join(MARKED) + "\n")   # even when the baseline excuses it
    doc = _doc(_run(box, Runner(cases=[MARKED + ("skipped", False)], listing=_listing(MARKED))))
    assert doc["verdict"] == "FAIL"
    assert doc["problems"] == [f"requires_mlx_serve tests skipped: ['{'::'.join(MARKED)}']"]


def test_a_skipped_marked_test_from_the_junit_property_fails(box):
    (box["baselines"] / "mlx-vlm.skips.txt").write_text("::".join(MARKED) + "\n")
    doc = _doc(_run(box, Runner(cases=[MARKED + ("skipped", True), PLAIN + ("passed", False)])))
    assert doc["verdict"] == "FAIL" and doc["problems"] == [f"requires_mlx_serve tests skipped: ['{'::'.join(MARKED)}']"]


def test_a_marked_test_missing_from_the_junit_fails(box):
    doc = _doc(_run(box, Runner(cases=[PLAIN + ("passed", False)], listing=_listing(MARKED))))
    assert doc["verdict"] == "FAIL" and "requires_mlx_serve tests skipped" in doc["problems"][0]


def test_the_listing_runs_in_the_same_scratch_with_the_fork_venv(box):
    r = Runner(listing=_listing())
    _run(box, r)
    argv, cwd = next((a, c) for a, c in r.calls if "--collect-only" in a)
    assert cwd.name == "mlx-vlm" and argv[0] == str(cwd / ".venv" / "bin" / "python")
    assert argv[argv.index("-m", 2) + 1] == G.SIBLING_MARKER and argv.count("-q") == 1


@pytest.mark.parametrize("listing, rc, want", [
    ("mlx_vlm/tests/test_b2.py: 7\n", 0, "per-file counts"),
    ("mlx_vlm/tests/test_b2.py::test_a\n\n2/9 tests collected (7 deselected) in 0.01s\n", 0, "2 collected but 1"),
    ("ERROR collecting\n", 2, "listing: rc 2"),
])
def test_an_unreadable_marker_listing_fails(box, listing, rc, want):
    doc = _doc(_run(box, Runner(listing=listing, listing_rc=rc)))
    assert doc["verdict"] == "FAIL" and want in " ".join(doc["problems"])
    assert any(n.endswith(".requires_mlx_serve.log") for n in doc["failure_artifacts"])


def test_nothing_selected_is_rc_5_and_not_a_problem(box):
    doc = _doc(_run(box, Runner(listing="\nno tests collected (9 deselected) in 0.01s\n", listing_rc=5)))
    assert doc["verdict"] == "PASS" and doc[f"{G.SIBLING_MARKER}_tests"] == 0


@pytest.fixture
def marker_used(box):
    """The fork's test sources use the marker (a test file under `mlx_vlm/tests` names it)."""
    tests = box["live"] / "mlx_vlm" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_b2.py").write_text(f"import pytest\n\n\n@pytest.mark.{G.SIBLING_MARKER}\ndef test_needs_serve():\n    pass\n")
    _git(box["live"], "add", "-A")
    _git(box["live"], "commit", "-q", "-m", "marked test")
    return dict(box, sha=_git(box["live"], "rev-parse", "HEAD"))


@pytest.mark.parametrize("listing, rc", [
    ("\nno tests collected (9 deselected) in 0.01s\n", 5),   # e.g. an addopts / plugin that dropped the marked tests
    ("", 0),
])
def test_marker_in_the_sources_but_an_empty_listing_fails(marker_used, listing, rc):
    doc = _doc(_run(marker_used, Runner(cases=[PLAIN + ("passed", False)], listing=listing, listing_rc=rc)))
    assert doc["verdict"] == "FAIL"
    assert doc["problems"] == [f"{G.SIBLING_MARKER} marked tests expected but none collected"]
    assert any(n.endswith(".requires_mlx_serve.log") for n in doc["failure_artifacts"]) == bool(listing)  # empty output: no log


def test_marker_in_the_sources_with_the_marked_test_listed_and_passed_is_a_pass(marker_used):
    doc = _doc(_run(marker_used, Runner(cases=[MARKED + ("passed", False)], listing=_listing(MARKED))))
    assert doc["verdict"] == "PASS" and doc[f"{G.SIBLING_MARKER}_tests"] == 1


def test_a_marked_test_deselected_from_the_suite_fails(box):
    """Listed by the marker run but absent from the suite's junit (deselected there) → FAIL."""
    other = ("mlx_vlm.tests.test_b2", "test_also_needs_serve")
    doc = _doc(_run(box, Runner(cases=[MARKED + ("passed", False), PLAIN + ("passed", False)], listing=_listing(MARKED, other))))
    assert doc["verdict"] == "FAIL" and doc["problems"] == [f"requires_mlx_serve tests skipped: ['{'::'.join(other)}']"]


# a captured-shape `pytest --collect-only -q -m requires_mlx_serve` transcript (pytest 8): stderr header lines, node ids
# (plain, class, parametrized with spaces / dashes), a warnings summary, and the summary line with deselected + warnings
TRANSCRIPT = """\
/gate/scratch/run/mlx-vlm/.venv/lib/python3.12/site-packages/_pytest/config/__init__.py:1441: PytestConfigWarning: Unknown config option: asyncio_mode

  self._warn_or_fail_if_strict(f"Unknown config option: {key}\\n")
mlx_vlm/tests/test_m76_b2_fe_fixround.py::test_operator_approved_hours_must_be_finite_and_positive[-1]
mlx_vlm/tests/test_m76_b2_fe_fixround.py::test_operator_approved_hours_must_be_finite_and_positive[nan]
mlx_vlm/tests/test_m76_b2_fe_orchestrate.py::test_the_roots_exchanged_are_refused
mlx_vlm/tests/test_m76_b2_fe_qualify.py::TestArms::test_a_bad_mode_arm_refuses_before_any_job[uniform-pick]
mlx_vlm/tests/test_m76_b2_fe_qualify.py::test_a_record_with_another_on_argv_is_refused[a b]

=============================== warnings summary ===============================
mlx_vlm/tests/test_m76_b2_fe_qualify.py:41
  /gate/scratch/run/mlx-vlm/mlx_vlm/tests/test_m76_b2_fe_qualify.py:41: DeprecationWarning: datetime.datetime.utcnow() is deprecated

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
5/2051 tests collected (2046 deselected), 1 warning in 3.42s
"""


def test_a_realistic_marker_listing_parses_to_the_junit_ids():
    assert G.marked_from_listing(TRANSCRIPT) == sorted([
        "mlx_vlm.tests.test_m76_b2_fe_fixround::test_operator_approved_hours_must_be_finite_and_positive[-1]",
        "mlx_vlm.tests.test_m76_b2_fe_fixround::test_operator_approved_hours_must_be_finite_and_positive[nan]",
        "mlx_vlm.tests.test_m76_b2_fe_orchestrate::test_the_roots_exchanged_are_refused",
        "mlx_vlm.tests.test_m76_b2_fe_qualify.TestArms::test_a_bad_mode_arm_refuses_before_any_job[uniform-pick]",
        "mlx_vlm.tests.test_m76_b2_fe_qualify::test_a_record_with_another_on_argv_is_refused[a b]",
    ])


def test_a_realistic_listing_whose_count_disagrees_is_refused():
    with pytest.raises(G.GateError, match="5 collected but 4"):
        G.marked_from_listing(TRANSCRIPT.replace(
            "mlx_vlm/tests/test_m76_b2_fe_orchestrate.py::test_the_roots_exchanged_are_refused\n", ""))


@pytest.mark.parametrize("nodeid, want", [
    ("mlx_vlm/tests/test_x.py::test_y[a-b]", "mlx_vlm.tests.test_x::test_y[a-b]"),
    ("mlx_vlm/tests/test_x.py::TestC::test_y", "mlx_vlm.tests.test_x.TestC::test_y"),
    ("2/9 tests collected (7 deselected) in 0.01s", None),
    ("mlx_vlm/tests/test_x.py", None),
])
def test_node_ids_map_to_junit_ids(nodeid, want):
    assert G.nodeid_to_junit(nodeid) == want


# ------------------------------------------------------------------ pre-push: the pairing is evidence, not a key
def test_a_mlx_vlm_pass_receipt_is_accepted_whatever_its_paired_sha(tmp_path):
    gate, sha, digest = tmp_path / "gate", "a" * 40, "d" * 64
    gate.mkdir()
    (gate / f"mlx-vlm-{sha}-{digest[:12]}.json").write_text(json.dumps(
        dict(repo="mlx-vlm", sha=sha, policy_digest=digest, verdict="PASS", paired={"mlx-serve": "0" * 40})))
    assert G.has_pass(gate, "mlx-vlm", sha, digest)


def test_the_cli_passes_the_override_to_run(box, monkeypatch, tmp_path):
    seen = {}

    def fake_run(repo, sha, **kw):
        seen.update(kw, repo=repo)
        p = tmp_path / "r.json"
        p.write_text(json.dumps(dict(repo=repo, sha=sha, verdict="PASS", problems=[])))
        return p

    class Lock:
        def release(self):
            pass

    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    monkeypatch.setattr(G, "run", fake_run)
    monkeypatch.setattr(G, "_hold_running", lambda wd: Lock())
    assert G.main(["run", "--repo", "mlx-vlm", "--mlx-serve-sha", box["s2"]]) == 0
    assert seen["repo"] == "mlx-vlm" and seen["mlx_serve_sha"] == box["s2"]
    assert G.main(["run", "--repo", "mlx-vlm"]) == 0 and seen["mlx_serve_sha"] is None
