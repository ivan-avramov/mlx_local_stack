"""M81 (S22-P23, C332 / C334 light path): the stack pre-push check refuses a fork gitlink whose PASS gate receipt is not paired with
the pushed stack commit's src/mlx-serve gitlink — on a release tag and on a branch push that changes a gitlink."""

import json
import subprocess

from bench import local_gate as G
from bench.tests.test_local_gate import _git, _repo

D = "d" * 64
FORK = "a" * 40
SERVE_OLD = "b" * 40
SERVE_NEW = "c" * 40


def _fork_receipt(gate, sha, paired=None, verdict="PASS", n=""):
    gate.mkdir(parents=True, exist_ok=True)
    doc = dict(repo="mlx-vlm", sha=sha, verdict=verdict, policy_digest=D)
    if paired is not None:
        doc["paired"] = {"mlx-serve": paired}
    (gate / f"mlx-vlm-{sha}-{D[:12]}{n}.json").write_text(json.dumps(doc))


def test_pairing_problems_wants_a_receipt_paired_with_the_stack_gitlink(tmp_path):
    gate = tmp_path / "gate"
    links = {"src/mlx-vlm": FORK, "src/mlx-serve": SERVE_NEW}
    _fork_receipt(gate, FORK, paired=SERVE_OLD)
    probs = G.pairing_problems(links, gate_dir=gate, digest_for=lambda repo, sha: D)
    assert len(probs) == 1 and "not paired with src/mlx-serve" in probs[0] and SERVE_NEW[:8] in probs[0]
    _fork_receipt(gate, FORK, paired=SERVE_NEW, n="-1")   # a second receipt with the right pairing is enough
    assert G.pairing_problems(links, gate_dir=gate, digest_for=lambda repo, sha: D) == []


def test_an_unpaired_or_failed_receipt_does_not_count(tmp_path):
    gate = tmp_path / "gate"
    links = {"src/mlx-vlm": FORK, "src/mlx-serve": SERVE_NEW}
    _fork_receipt(gate, FORK, paired=None)                       # pre-M80 receipt: no pairing recorded
    _fork_receipt(gate, FORK, paired=SERVE_NEW, verdict="FAIL", n="-1")
    assert G.pairing_problems(links, gate_dir=gate, digest_for=lambda repo, sha: D)


def test_the_release_rule_includes_the_pairing(tmp_path):
    fork_remote = tmp_path / "fork.git"
    subprocess.run(["git", "init", "-q", "--bare", str(fork_remote)], check=True)
    fork = tmp_path / "mlx-vlm"
    fsha = _repo(fork, origin=str(fork_remote))
    _git(fork, "push", "-q", "origin", "main")
    gate = tmp_path / "gate"
    _fork_receipt(gate, fsha, paired=SERVE_OLD)
    probs = G.gitlink_problems({"src/mlx-vlm": fsha, "src/mlx-serve": SERVE_NEW},
                               {"src/mlx-vlm": fork, "src/mlx-serve": tmp_path / "absent"},
                               gate_dir=gate, digest_for=lambda repo, sha: D)
    assert any("not paired with src/mlx-serve" in p for p in probs)


def _stack_with_gitlinks(tmp_path, serve):
    remote = tmp_path / "stack.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    work = tmp_path / "stack"
    _repo(work, origin=str(remote))
    _git(work, "update-index", "--add", "--cacheinfo", f"160000,{FORK},src/mlx-vlm")
    _git(work, "update-index", "--add", "--cacheinfo", f"160000,{SERVE_OLD},src/mlx-serve")
    _git(work, "commit", "-q", "-m", "gitlinks")
    _git(work, "push", "-q", "origin", "main")
    base = _git(work, "rev-parse", "HEAD")
    _git(work, "update-index", "--cacheinfo", f"160000,{serve},src/mlx-serve")
    _git(work, "commit", "-q", "-m", "bump mlx-serve")
    return work, base, _git(work, "rev-parse", "HEAD")


def test_a_branch_push_that_bumps_mlx_serve_needs_a_fork_receipt_paired_with_it(tmp_path):
    work, base, head = _stack_with_gitlinks(tmp_path, SERVE_NEW)
    gate = tmp_path / "gate"
    (gate).mkdir()
    # S27 §12: a stack PASS receipt carries the `pushed_base` the gate ran against; `base` is `origin/main`, so the protected
    # paths are unchanged since it and the push binding passes — this test checks only the mlx-serve pairing
    (gate / f"stack-{head}-{D[:12]}.json").write_text(json.dumps(dict(repo="stack", sha=head, verdict="PASS", policy_digest=D,
                                                                      pushed_base=base)))
    _fork_receipt(gate, FORK, paired=SERVE_OLD)
    line = f"refs/heads/main {head} refs/heads/main {base}"
    out = G.check_lines("stack", work, "origin", [line], gate_dir=gate, digest_for=lambda repo, sha: D)
    assert any("not paired with src/mlx-serve" in o for o in out), out
    _fork_receipt(gate, FORK, paired=SERVE_NEW, n="-1")
    assert G.check_lines("stack", work, "origin", [line], gate_dir=gate, digest_for=lambda repo, sha: D) == []


def test_a_branch_push_that_touches_no_gitlink_is_not_checked_for_pairing(pushed=None):
    # the existing pushed fixture has no gitlinks; a plain code push keeps today's level rule only
    assert G.pairing_problems({}, gate_dir="/nonexistent", digest_for=lambda repo, sha: D) == []


def test_a_branch_push_that_deletes_a_gitlink_fails_closed(tmp_path):
    work, base, _ = _stack_with_gitlinks(tmp_path, SERVE_NEW)
    _git(work, "rm", "-q", "--cached", "src/mlx-serve")
    _git(work, "commit", "-q", "-m", "drop mlx-serve")
    head = _git(work, "rev-parse", "HEAD")
    gate = tmp_path / "gate"
    gate.mkdir()
    (gate / f"stack-{head}-{D[:12]}.json").write_text(json.dumps(dict(repo="stack", sha=head, verdict="PASS", policy_digest=D)))
    out = G.check_lines("stack", work, "origin", [f"refs/heads/main {head} refs/heads/main {base}"], gate_dir=gate,
                        digest_for=lambda repo, sha: D)
    assert any("gitlink src/mlx-serve: absent" in o for o in out), out
