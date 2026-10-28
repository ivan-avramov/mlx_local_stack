"""P426 T3 §3: the local gate on S′ — the upstream ref and the audit list are read per fork sha, from whichever layout the sha has
(S: `.github/workflows/upstream-parity.yml` + the eight fixed audits; S′: `.upstream-sync-ref` + the fork's own `dev/ci.py`
`AUDITS`, nine). Fixtures are tiny local git repositories; the gate is never run against the real forks."""

import subprocess

import pytest

from bench import local_gate as G

S_AUDITS = ("check_upstream_parity.py", "check_upstream_symbols.py", "check_upstream_deletions.py", "check_fork_markers.py",
            "check_dead_helpers.py", "check_body_divergence.py", "check_upstream_registries.py", "check_call_arguments.py")

WORKFLOW = "env:\n  # comment\n  UPSTREAM_SYNC_REF: 952d4f6b\njobs: {}\n"
SYNC_REF = "# The upstream ref the fork last merged.\n# Bump it with every sync.\n\n2ceff4c1\n"
CI_PY = '''"""fixture dev/ci.py"""
from typing import List

AUDITS: List[tuple] = [
    ("check_upstream_parity.py", ()),
    ("check_upstream_symbols.py", ()),
    ("check_upstream_deletions.py", ("--strict",)),
    ("check_fork_markers.py", ()),
    ("check_dead_helpers.py", ()),
    ("check_body_divergence.py", ()),
    ("check_upstream_registries.py", ()),
    ("check_call_arguments.py", ()),
    ("check_upstream_test_copies.py", ()),
]
'''


def _git(cwd, *a):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], check=True,
                   capture_output=True)


def _commit(repo, files, msg="c"):
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def fork(tmp_path):
    repo = tmp_path / "fork"
    repo.mkdir()
    _git(repo, "init", "-q")
    s = _commit(repo, {".github/workflows/upstream-parity.yml": WORKFLOW, "README": "s"}, "S layout")
    s2 = _commit(repo, {".upstream-sync-ref": SYNC_REF, "dev/ci.py": CI_PY}, "S-prime layout")
    return repo, s, s2


def test_the_sync_ref_file_is_read_at_the_sha_when_present_else_the_workflow(fork):
    repo, s, s2 = fork
    assert G.current_parity("mlx-vlm", repo, s) == "952d4f6b"
    assert G.current_parity("mlx-vlm", repo, s2) == "2ceff4c1"  # the file wins even while the workflow still exists
    assert G.current_parity("mlx-serve", repo, s2) is None


def test_the_sync_ref_file_skips_comments_and_blanks_and_refuses_an_empty_one(tmp_path):
    assert G.sync_ref_text(SYNC_REF) == "2ceff4c1"
    with pytest.raises(G.GateError, match="upstream-sync-ref"):
        G.sync_ref_text("# only a comment\n\n")


def test_the_audit_list_is_the_forks_own_per_sha(fork):
    repo, s, s2 = fork
    assert tuple(name for name, _ in G.audits_at(repo, s)) == S_AUDITS  # no dev/ci.py: the S layout's eight
    nine = G.audits_at(repo, s2)
    assert [n for n, _ in nine] == [*S_AUDITS, "check_upstream_test_copies.py"]
    assert dict(nine)["check_upstream_deletions.py"] == ("--strict",)


def test_the_audit_argvs_follow_the_derived_list_and_keep_strict(fork):
    repo, _, s2 = fork
    argvs = G.audit_argvs("PY", "2ceff4c1", G.audits_at(repo, s2))
    assert len(argvs) == 9 and argvs[-1][1] == "dev/check_upstream_test_copies.py"
    assert argvs[2] == ["PY", "dev/check_upstream_deletions.py", "--upstream-ref", "2ceff4c1", "--strict"]
    assert G.audit_argvs("PY", "952d4f6b") == G.audit_argvs("PY", "952d4f6b", [(n, ("--strict",) if "deletions" in n else ())
                                                                              for n in S_AUDITS])


def test_an_unparseable_ci_audit_list_refuses(tmp_path):
    repo = tmp_path / "bad"
    repo.mkdir()
    _git(repo, "init", "-q")
    sha = _commit(repo, {"dev/ci.py": "AUDITS = build_audits()\n"})
    with pytest.raises(G.GateError, match="AUDITS"):
        G.audits_at(repo, sha)


def test_the_mlx_vlm_steps_run_exactly_the_derived_audits(fork, tmp_path):
    repo, _, s2 = fork
    steps = G.steps_for("mlx-vlm", tmp_path / "scratch", "2ceff4c1", audits=G.audits_at(repo, s2))
    audit_steps = [st for st in steps if st.name.startswith("audit:")]
    assert len(audit_steps) == 9 and audit_steps[-1].argv[1] == "dev/check_upstream_test_copies.py"
    assert len(G.steps_for("mlx-vlm", tmp_path / "scratch", "952d4f6b")) == len(steps) - 1  # default = the eight


def test_the_policy_digest_covers_the_audit_list(fork):
    repo, s, s2 = fork
    base = dict(gate_source=b"g", baseline="b", parity="x")
    eight = G.policy_digest("mlx-vlm", base["gate_source"], "b", "x", audits=G.audits_at(repo, s))
    nine = G.policy_digest("mlx-vlm", base["gate_source"], "b", "x", audits=G.audits_at(repo, s2))
    assert eight != nine
    assert G.policy_digest("stack", b"g", "b", None) == G.policy_digest("stack", b"g", "b", None, audits=None)
