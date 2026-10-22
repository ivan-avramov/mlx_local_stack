"""P434 (`docs/specs/p434-local-gate.md` v3.1): the local pre-push gate — receipts, policy digest, busy refusal, scratch clones,
exact step argvs, the pre-push `check`, the machine-local hook shims. The runner is mocked; the shims and the git plumbing run
for real against temporary repositories (no network: every case refuses before a fetch, or the remote is a local path)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bench import local_gate as G
from bench import paths

REPO = paths.repo_root()
ZERO = "0" * 40


def _git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()


def _repo(path, files=None, origin=None):
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    _git(path, "config", "core.hooksPath", "/dev/null")
    for rel, text in (files or {"a.txt": "a\n"}).items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    if origin:
        _git(path, "remote", "add", "origin", origin)
    return _git(path, "rev-parse", "HEAD")


# ------------------------------------------------------------------ identity / parity ref / audits
@pytest.mark.parametrize("url, want", [
    ("git@github.com:ivan-avramov/mlx_local_stack.git", "stack"),
    ("https://github.com/ivan-avramov/mlx-vlm", "mlx-vlm"),
    ("git@github.com:ivan-avramov/mlx-serve", "mlx-serve"),
    ("git@github.com:someone-else/mlx-vlm", None),
    ("", None),
])
def test_identity_from_origin_url(url, want):
    assert G.identity(url) == want


def test_parity_ref_is_parsed_from_the_workflow():
    wf = "env:\n  # comment\n  UPSTREAM_SYNC_REF: 952d4f6b\njobs: {}\n"
    assert G.parity_ref(wf) == "952d4f6b"
    with pytest.raises(G.GateError, match="UPSTREAM_SYNC_REF"):
        G.parity_ref("env: {}\n")


def test_the_eight_audit_argvs_are_exact_including_strict():
    argvs = G.audit_argvs("PY", "952d4f6b")
    assert len(argvs) == 8
    names = [a[1] for a in argvs]
    assert names == [f"dev/{n}" for n in ("check_upstream_parity.py", "check_upstream_symbols.py",
                                           "check_upstream_deletions.py", "check_fork_markers.py", "check_dead_helpers.py",
                                           "check_body_divergence.py", "check_upstream_registries.py",
                                           "check_call_arguments.py")]
    for a in argvs:
        assert a[0] == "PY" and a[2:4] == ["--upstream-ref", "952d4f6b"]
    assert argvs[2][4:] == ["--strict"] and all(len(a) == 4 for i, a in enumerate(argvs) if i != 2)


# ------------------------------------------------------------------ policy digest
def test_policy_digest_changes_with_every_input():
    base = dict(repo="mlx-vlm", gate_source=b"x", baseline="a\n", parity="952d4f6b")
    d0 = G.policy_digest(**base)
    for k, v in (("repo", "mlx-serve"), ("gate_source", b"y"), ("baseline", "b\n"), ("parity", "abc")):
        assert G.policy_digest(**dict(base, **{k: v})) != d0
    assert G.policy_digest(**base) == d0


# ------------------------------------------------------------------ busy box
@pytest.mark.parametrize("ps, listeners, n", [
    ("1 /usr/bin/python something idle\n", 0, 0),
    ("2 python -m bench.p426_wave1 --stack-root x\n", 0, 1),     # any live sequencer, paused or not
    ("3 uv run mlx-serve start\n", 0, 1),
    ("4 zsh\n", 1, 1),                                            # a listener on :8000
])
def test_busy_problems(ps, listeners, n):
    assert len(G.busy_problems(ps, listeners, my_pid=999)) == n


# ------------------------------------------------------------------ run (mocked runner)
class Runner:
    def __init__(self, rcs=None, dirty_after=None, skipped=(), imports_inside=True):
        self.calls, self.rcs, self.dirty_after, self.skipped, self.inside = [], rcs or {}, dirty_after, skipped, imports_inside

    def __call__(self, argv, cwd, env):
        self.calls.append((list(argv), str(cwd)))
        name = " ".join(argv)
        for key, rc in self.rcs.items():
            if key in name:
                return rc, f"{key} failed"
        if "--junitxml" in name:
            xml = next(a.split("=", 1)[1] for a in argv if a.startswith("--junitxml="))
            cases = "".join(f'<testcase classname="{c}" name="{n}"><skipped/></testcase>' for c, n in self.skipped)
            Path(xml).write_text(f'<testsuites><testsuite>{cases}</testsuite></testsuites>')
        if "import mlx_vlm, mlx_serve" in name:
            where = cwd if self.inside else "/elsewhere"
            return 0, f"{where}/src/mlx-vlm/mlx_vlm/__init__.py {where}/src/mlx-serve/src/mlx_serve/__init__.py"
        return 0, ""

    def dirty(self, scratch, after_step):
        return self.dirty_after is not None and after_step == self.dirty_after


@pytest.fixture
def env(tmp_path):
    live = tmp_path / "live" / "mlx-serve"
    sha = _repo(live, {"pyproject.toml": "[project]\nname='x'\n", "uv.lock": "x\n"},
                origin="git@github.com:ivan-avramov/mlx-serve")
    baseline = tmp_path / "baselines"
    baseline.mkdir()
    (baseline / "mlx-serve.skips.txt").write_text("")
    return dict(tmp=tmp_path, live=live, sha=sha, gate=tmp_path / "gate", baselines=baseline)


def _run(env, runner, **kw):
    return G.run("mlx-serve", env["sha"], live=env["live"], gate_dir=env["gate"], baselines=env["baselines"], runner=runner,
                 busy=kw.pop("busy", lambda: []), dirty=runner.dirty, artifacts=kw.pop("artifacts", lambda d: True), **kw)


def test_a_passing_run_writes_one_PASS_receipt_and_removes_the_scratch(env):
    r = Runner()
    receipt = _run(env, r)
    doc = json.loads(Path(receipt).read_text())
    assert doc["verdict"] == "PASS" and doc["sha"] == env["sha"] and doc["repo"] == "mlx-serve"
    assert doc["policy_digest"] and all(s["rc"] == 0 for s in doc["steps"])
    assert not list((env["gate"] / "scratch").glob("*"))
    names = [s["name"] for s in doc["steps"]]
    assert names == ["clone", "sync", "ruff-check", "ruff-format", "pytest", "build"]
    sync = next(c for c, _ in r.calls if "sync" in c)
    assert sync[:2] == ["uv", "sync"] and "--locked" in sync and sync[sync.index("--python") + 1] == "3.12"


def test_a_failing_step_writes_a_FAIL_receipt_kept_beside_a_later_PASS(env):
    first = json.loads(Path(_run(env, Runner(rcs={"ruff check": 1}))).read_text())
    assert first["verdict"] == "FAIL" and first["steps"][-1]["name"] == "ruff-check"
    second = _run(env, Runner())
    assert json.loads(Path(second).read_text())["verdict"] == "PASS"
    assert len(list(env["gate"].glob(f"mlx-serve-{env['sha']}-*.json"))) == 2
    assert not list((env["gate"] / "scratch").glob("*"))


def test_a_skip_list_unequal_to_the_baseline_fails(env):
    doc = json.loads(Path(_run(env, Runner(skipped=[("tests.test_x", "test_y")]))).read_text())
    assert doc["verdict"] == "FAIL" and doc["skipped_tests"] == ["tests.test_x::test_y"]
    assert "baseline" in " ".join(doc["problems"])


def test_a_step_that_dirties_the_tree_fails(env):
    doc = json.loads(Path(_run(env, Runner(dirty_after="ruff-format"))).read_text())
    assert doc["verdict"] == "FAIL" and "ruff-format" in " ".join(doc["problems"])


def test_a_busy_box_refuses_before_any_step(env):
    r = Runner()
    with pytest.raises(G.GateError, match="busy"):
        _run(env, r, busy=lambda: ["2 python -m bench.p426_wave1"])
    assert r.calls == []


def test_busy_appearing_mid_run_fails_the_receipt(env):
    state = {"n": 0}

    def busy():
        state["n"] += 1
        return ["3 mlx-serve start"] if state["n"] > 2 else []

    doc = json.loads(Path(_run(env, Runner(), busy=busy)).read_text())
    assert doc["verdict"] == "FAIL" and "busy" in " ".join(doc["problems"])


def test_missing_build_artifacts_fail(env):
    doc = json.loads(Path(_run(env, Runner(), artifacts=lambda d: False)).read_text())
    assert doc["verdict"] == "FAIL" and "wheel" in " ".join(doc["problems"])


def test_the_scratch_is_an_independent_clone(env):
    """G11: remotes / refs configured in the scratch never reach the live repository."""
    scratch = G.clone_scratch(env["live"], env["sha"], env["gate"] / "scratch" / "x")
    _git(scratch, "remote", "add", "upstream", "https://example.invalid/u.git")
    assert "upstream" not in _git(env["live"], "remote")
    assert not (scratch / ".git").is_file()  # a clone, not a linked worktree
    assert _git(scratch, "rev-parse", "HEAD") == env["sha"]


def test_stack_steps_build_the_scratch_venv_and_assert_imports_inside_it(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    steps = G.steps_for("stack", tmp_path / "s", parity=None)
    names = [s.name for s in steps]
    assert names[:4] == ["clone", "submodules", "venv", "venv-sync"] and "imports" in names and names[-1] == "pytest"
    pytest_step = steps[-1]
    assert pytest_step.cwd == tmp_path / "s" / "benchmark" and "bench/tests/" in pytest_step.argv
    assert pytest_step.env.get("STACK_WORKDIR")  # P445: kept set


def test_fork_steps_order_and_audits(tmp_path):
    steps = G.steps_for("mlx-vlm", tmp_path / "s", parity="952d4f6b")
    names = [s.name for s in steps]
    assert names[:4] == ["clone", "upstream", "sync", "extras"] and names[4] == "pre-commit"
    assert [n for n in names if n.startswith("audit:")] == [f"audit:{i}" for i in range(8)]
    assert names[-1] == "pytest"


def test_a_stack_import_outside_the_scratch_fails(tmp_path, monkeypatch):
    assert G.imports_inside("/s/src/mlx-vlm/mlx_vlm/__init__.py /s/src/mlx-serve/src/mlx_serve/__init__.py", Path("/s"))
    assert not G.imports_inside("/live/src/mlx-vlm/mlx_vlm/__init__.py /s/src/mlx-serve/src/mlx_serve/__init__.py",
                                Path("/s"))


# ------------------------------------------------------------------ check (pre-push)
def _receipt(gate, repo, sha, digest, verdict="PASS"):
    gate.mkdir(parents=True, exist_ok=True)
    (gate / f"{repo}-{sha}-{digest[:12]}.json").write_text(json.dumps(dict(repo=repo, sha=sha, verdict=verdict,
                                                                          policy_digest=digest)))


@pytest.fixture
def pushed(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    work = tmp_path / "work"
    base = _repo(work, {"a.txt": "a\n"}, origin=str(remote))
    _git(work, "push", "-q", "origin", "main")
    (work / "b.txt").write_text("b\n")
    _git(work, "add", "b.txt")
    _git(work, "commit", "-q", "-m", "second")
    head = _git(work, "rev-parse", "HEAD")
    return dict(work=work, base=base, head=head, gate=tmp_path / "gate")


def _check(p, lines, digest="d" * 64, repo="mlx-serve", **kw):
    return G.check_lines(repo, p["work"], "origin", lines, gate_dir=p["gate"], digest_for=lambda repo, sha: digest, **kw)


def test_check_accepts_a_PASS_receipt_for_the_pushed_sha(pushed):
    _receipt(pushed["gate"], "mlx-serve", pushed["head"], "d" * 64)
    assert _check(pushed, [f"refs/heads/main {pushed['head']} refs/heads/main {pushed['base']}"]) == []


@pytest.mark.parametrize("verdict, digest, want", [(None, "d" * 64, "no PASS receipt"), ("FAIL", "d" * 64, "no PASS"),
                                                    ("PASS", "e" * 64, "no PASS")])
def test_check_refuses_missing_failed_or_stale_policy(pushed, verdict, digest, want):
    if verdict:
        _receipt(pushed["gate"], "mlx-serve", pushed["head"], digest, verdict)
    out = _check(pushed, [f"refs/heads/main {pushed['head']} refs/heads/main {pushed['base']}"])
    assert out and want in out[0]


def test_check_ignores_a_delete_line(pushed):
    assert _check(pushed, [f"(delete) {ZERO} refs/heads/old {pushed['base']}"]) == []


def test_check_scans_every_introduced_commit_not_just_the_endpoints(pushed):
    """G5: a leak added then removed across two commits is caught."""
    w = pushed["work"]
    leak = "/".join(("", "Users", "otherperson", "x"))  # built at runtime: the literal fails the repo PII scan
    (w / "c.txt").write_text(leak + "\n")
    _git(w, "add", "c.txt")
    _git(w, "commit", "-q", "-m", "leak")
    (w / "c.txt").write_text("clean\n")
    _git(w, "commit", "-qam", "scrub")
    head = _git(w, "rev-parse", "HEAD")
    _receipt(pushed["gate"], "mlx-serve", head, "d" * 64)
    out = _check(pushed, [f"refs/heads/main {head} refs/heads/main {pushed['base']}"])
    assert any("PII" in o for o in out)


def test_check_scans_a_new_branch_against_the_remote_refs(pushed):
    _receipt(pushed["gate"], "mlx-serve", pushed["head"], "d" * 64)
    assert _check(pushed, [f"refs/heads/topic {pushed['head']} refs/heads/topic {ZERO}"]) == []
    assert G.introduced(pushed["work"], "origin", pushed["head"]) == [pushed["head"]]


def test_check_refuses_when_the_fetch_fails(pushed):
    _git(pushed["work"], "remote", "set-url", "origin", str(pushed["work"].parent / "missing.git"))
    out = _check(pushed, [f"refs/heads/main {pushed['head']} refs/heads/main {pushed['base']}"])
    assert out and "fetch" in out[0]


def test_check_flags_a_commit_message_violation(pushed):
    w = pushed["work"]
    (w / "d.txt").write_text("d\n")
    _git(w, "add", "d.txt")
    _git(w, "commit", "-q", "-m", "Ornith regressed")  # allow-shorthand: the violation under test
    head = _git(w, "rev-parse", "HEAD")
    _receipt(pushed["gate"], "mlx-serve", head, "d" * 64)
    out = _check(pushed, [f"refs/heads/main {head} refs/heads/main {pushed['base']}"])
    assert any("message" in o for o in out)


def test_stack_check_requires_fork_receipts_and_reachable_gitlinks(tmp_path):
    fork_remote = tmp_path / "fork.git"
    subprocess.run(["git", "init", "-q", "--bare", str(fork_remote)], check=True)
    fork = tmp_path / "mlx-vlm"
    fsha = _repo(fork, origin=str(fork_remote))
    probs = G.gitlink_problems({"src/mlx-vlm": fsha}, {"src/mlx-vlm": fork}, gate_dir=tmp_path / "gate",
                               digest_for=lambda repo, sha: "d" * 64)
    assert any("no PASS receipt" in p for p in probs) and any("not reachable" in p for p in probs)
    _git(fork, "push", "-q", "origin", "main")
    _receipt(tmp_path / "gate", "mlx-vlm", fsha, "d" * 64)
    assert G.gitlink_problems({"src/mlx-vlm": fsha}, {"src/mlx-vlm": fork}, gate_dir=tmp_path / "gate",
                              digest_for=lambda repo, sha: "d" * 64) == []


# ------------------------------------------------------------------ shims (unmocked)
def _shim_env(tmp_path, min_commit):
    hooks = tmp_path / "hooks"
    G.write_shims(hooks, stack_repo=REPO, min_commit=min_commit)
    return hooks


def _run_shim(hooks, cwd, stdin=""):
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    env["STACK_REPO"] = str(REPO)
    return subprocess.run([str(hooks / "pre-push"), "origin", "x"], cwd=cwd, input=stdin, capture_output=True, text=True,
                          env=env, timeout=120)


def test_the_shim_refuses_an_unknown_origin_and_proves_the_gate_imports(tmp_path):
    other = tmp_path / "other"
    _repo(other, origin="git@github.com:someone-else/thing")
    hooks = _shim_env(tmp_path, _git(REPO, "rev-parse", "HEAD"))
    r = _run_shim(hooks, other)
    assert r.returncode == 1 and "unknown origin" in r.stderr  # the gate module imported (PYTHONPATH set, H1)


def test_the_shim_refuses_a_stack_head_without_the_min_commit(tmp_path):
    other = tmp_path / "other"
    _repo(other, origin="git@github.com:someone-else/thing")
    orphan = _repo(tmp_path / "orphan")  # a commit that is not an ancestor of the stack HEAD
    hooks = _shim_env(tmp_path, orphan)
    r = _run_shim(hooks, other)
    assert r.returncode == 1 and "GATE_MIN_COMMIT" in r.stderr


def test_the_pre_commit_shim_delegates_to_the_repo_hooks_or_passes(tmp_path):
    hooks = _shim_env(tmp_path, _git(REPO, "rev-parse", "HEAD"))
    plain = tmp_path / "plain"
    _repo(plain)
    assert subprocess.run([str(hooks / "pre-commit")], cwd=plain).returncode == 0
    withhook = tmp_path / "withhook"
    _repo(withhook, {"githooks/pre-commit": "#!/bin/sh\nexit 7\n"})
    (withhook / "githooks" / "pre-commit").chmod(0o755)
    assert subprocess.run([str(hooks / "pre-commit")], cwd=withhook).returncode == 7


def test_bootstrap_installs_the_shims():
    text = (REPO / "scripts" / "bootstrap_machine.sh").read_text()
    assert "bench.local_gate install-hooks" in text


# ------------------------------------------------------------------ P447: the data-only `evidence` branch
def _orphan_commit(work, files):
    _git(work, "checkout", "-q", "--orphan", "evidence")
    _git(work, "rm", "-rq", "--cached", ".")
    for rel, text in files.items():
        (work / rel).write_text(text)
    _git(work, "add", *files)
    _git(work, "commit", "-q", "-m", "data(bench): evidence backfill")
    return _git(work, "rev-parse", "HEAD")


def test_an_evidence_push_needs_no_receipt_but_is_pii_scanned(pushed):
    sha = _orphan_commit(pushed["work"], {"report.log": "Ornith ran fine\n"})  # data: naming is not checked  # allow-shorthand
    assert _check(pushed, [f"refs/heads/evidence {sha} refs/heads/evidence {ZERO}"], repo="stack") == []


def test_an_evidence_push_with_pii_refuses(pushed):
    leak = "/".join(("", "Users", "otherperson", "x"))  # built at runtime: the literal fails the repo PII scan
    sha = _orphan_commit(pushed["work"], {"report.log": leak + "\n"})
    out = _check(pushed, [f"refs/heads/evidence {sha} refs/heads/evidence {ZERO}"], repo="stack")
    assert any("PII" in o for o in out)


def test_an_evidence_push_sharing_history_with_main_refuses(pushed):
    """The exemption is for an ORPHAN data branch only: code history pushed as `evidence` still needs a receipt."""
    out = _check(pushed, [f"refs/heads/main {pushed['head']} refs/heads/evidence {ZERO}"], repo="stack")
    assert any("orphan" in o for o in out)
