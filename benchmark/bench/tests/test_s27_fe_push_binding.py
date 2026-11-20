"""S27 (spec v1.4, section 12, acceptance 10.1) -- blind test-writer, delivery 1: the push binding.

`local_gate.check_lines` (the pre-push check, which fetches) over real temporary git repositories and a local bare remote, as
`test_local_gate.py` does; the gate's receipt documents are written by hand in the format the gate writes
(`pass_receipt` finds `<repo>-<sha>-<digest12>*.json` with verdict PASS, the sha and the digest, plus `pushed_base`, S25-P10).

Class of each test: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) exercises new behaviour.

Interface assumptions:
  B1  `local_gate.PROTECTED_PUSH_PATHS` is the four-file set (any iterable of paths);
  B2  a refusal is a line starting `REFUSED: stack <sha8>` in `check_lines`' return value and carries a regate hint that names
      `bench.local_gate run` (the baseline's own hint form);
  B3  `push_level` reads the receipt document, not only its name: `pushed_base` must be in it (spec 12).
"""
from __future__ import annotations

import json
import subprocess

import pytest

from bench import arm_opencode
from bench import arm_specs
from bench import local_gate as G
from bench.tests.test_local_gate import _git, _repo

DIGEST = "d" * 64
PROTECTED = ["benchmark/opencode_bench_v2_web_tg1.json", "benchmark/opencode_plugins/noretry.js",
             "benchmark/opencode_plugins/toolbounds.js", "benchmark/opencode_plugins/datefreeze.js"]
FILES = {**{p: f"// {p}\n" for p in PROTECTED}, "code.py": "x = 1\n", "README.md": "readme\n"}
ZERO = "0" * 40


def receipt(gate, sha, **extra):
    gate.mkdir(parents=True, exist_ok=True)
    doc = dict(repo="stack", sha=sha, verdict="PASS", policy_digest=DIGEST)
    doc.update(extra)
    (gate / f"stack-{sha}-{DIGEST[:12]}.json").write_text(json.dumps(doc))


@pytest.fixture
def world(tmp_path):
    """A bare remote, the work clone at `base` (pushed), a second clone to move the remote's main, and a local head one commit
    ahead of `base` that touches code only."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    work = tmp_path / "work"
    base = _repo(work, FILES, origin=str(remote))
    _git(work, "push", "-q", "origin", "main")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
    _git(other, "config", "user.email", "t@example.invalid")
    _git(other, "config", "user.name", "t")
    _git(other, "config", "core.hooksPath", "/dev/null")
    (work / "code.py").write_text("x = 2\n")
    _git(work, "add", "code.py")
    _git(work, "commit", "-q", "-m", "change code")
    head = _git(work, "rev-parse", "HEAD")
    return dict(work=work, other=other, base=base, head=head, gate=tmp_path / "gate", tmp=tmp_path)


def move_remote(w, path=None, text="moved\n"):
    """Someone else pushes to the remote's main: `path` edited (or an unrelated file)."""
    rel = path or "elsewhere.txt"
    target = w["other"] / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    _git(w["other"], "add", rel)
    _git(w["other"], "commit", "-q", "-m", f"move remote main: {rel}")
    _git(w["other"], "push", "-q", "origin", "main")


def check(w, ref="refs/heads/main", repo="stack"):
    line = f"{ref} {w['head']} {ref} {ZERO}"
    return G.check_lines(repo, w["work"], "origin", [line], gate_dir=w["gate"], digest_for=lambda r, s: DIGEST)


# ------------------------------------------------------------------------------------------------ the constant
def test_the_protected_set_is_the_four_file_set_of_the_closure_test():
    """(c) B1: imported from `arm_opencode` / `arm_specs`; a test pins equality with the closure test's paths."""
    assert set(G.PROTECTED_PUSH_PATHS) == set(PROTECTED)
    assert set(G.PROTECTED_PUSH_PATHS) == set(arm_opencode.GENERATION_DATA) == set(arm_specs.OC.generation_data)


# ------------------------------------------------------------------------------------------------ full-level pushes of the stack
def test_a_moved_remote_main_with_the_protected_files_unchanged_is_accepted(world):
    """(b) The binding refuses only what the proof no longer describes."""
    receipt(world["gate"], world["head"], pushed_base=world["base"])
    move_remote(world)
    assert check(world) == []


def test_a_moved_remote_main_that_edits_datefreeze_is_refused_with_a_regate_hint(world):
    """(a) The baseline accepts: the closure proof was made against a base the remote has since moved away from."""
    receipt(world["gate"], world["head"], pushed_base=world["base"])
    move_remote(world, "benchmark/opencode_plugins/datefreeze.js", "// edited upstream\n")
    out = check(world)
    assert len(out) == 1 and out[0].startswith(f"REFUSED: stack {world['head'][:8]}"), out
    assert "bench.local_gate run" in out[0] or "regate" in out[0].lower()


@pytest.mark.parametrize("path", PROTECTED)
def test_every_protected_file_counts(world, path):
    """(a) each of the four paths."""
    receipt(world["gate"], world["head"], pushed_base=world["base"])
    move_remote(world, path, "// edited upstream\n")
    out = check(world)
    assert len(out) == 1 and out[0].startswith("REFUSED"), out


def test_a_receipt_without_pushed_base_is_refused(world):
    """(a) the PASS receipt DOCUMENT must carry `pushed_base`."""
    receipt(world["gate"], world["head"])
    out = check(world)
    assert len(out) == 1 and out[0].startswith("REFUSED"), out


def test_a_pushed_base_that_is_absent_from_the_repo_is_refused(world):
    """(a) 'the commit must exist in the repo (else refuse)'."""
    receipt(world["gate"], world["head"], pushed_base="e" * 40)
    out = check(world)
    assert len(out) == 1 and out[0].startswith("REFUSED"), out


def test_a_pushed_base_that_is_not_a_hex_commit_name_is_refused(world):
    """(b) fail closed on a malformed field: nothing is diffed against it."""
    receipt(world["gate"], world["head"], pushed_base="--output=/tmp/x")
    out = check(world)
    assert len(out) == 1 and out[0].startswith("REFUSED"), out


def test_any_git_error_refuses(world):
    """(a) 'any git error refuses': the remote has no `main` to diff against."""
    receipt(world["gate"], world["head"], pushed_base=world["base"])
    # a remote whose only branch is `trunk`: `origin/main` does not exist after the fetch
    _git(world["work"], "push", "-q", "origin", f"{world['base']}:refs/heads/trunk")       # not `main`: the new head must stay unpushed
    subprocess.run(["git", "--git-dir", str(world["tmp"] / "remote.git"), "symbolic-ref", "HEAD", "refs/heads/trunk"], check=True)
    _git(world["work"], "push", "-q", "origin", ":main")                 # v2: the remote's HEAD is no longer `main`
    out = check(world, ref="refs/heads/feature")
    assert len(out) == 1 and out[0].startswith("REFUSED"), out


def test_a_non_main_pushed_ref_at_level_full_takes_the_same_rule(world):
    """(a) spec 12: 'a non-main pushed ref at level full -> the same rule'."""
    receipt(world["gate"], world["head"], pushed_base=world["base"])
    move_remote(world, "benchmark/opencode_plugins/noretry.js", "// edited upstream\n")
    out = check(world, ref="refs/heads/feature")
    assert len(out) == 1 and out[0].startswith("REFUSED"), out


def test_a_non_main_pushed_ref_with_the_protected_files_unchanged_is_accepted(world):
    """(b)"""
    receipt(world["gate"], world["head"], pushed_base=world["base"])
    move_remote(world)
    assert check(world, ref="refs/heads/feature") == []


def test_a_refused_push_stays_refused_whatever_else_is_in_the_gate_directory(world):
    """(b) 'a refused push stays refused': a second, older PASS receipt of the same commit without the binding does not rescue it."""
    receipt(world["gate"], world["head"], pushed_base=world["base"])
    move_remote(world, "benchmark/opencode_plugins/toolbounds.js", "// edited upstream\n")
    (world["gate"] / f"stack-{world['head']}-{DIGEST[:12]}.0.json").write_text(json.dumps(
        dict(repo="stack", sha=world["head"], verdict="PASS", policy_digest=DIGEST)))
    out = check(world)
    assert out and out[0].startswith("REFUSED")


# ------------------------------------------------------------------------------------------------ the levels that return earlier, and the forks
def test_a_docs_only_push_needs_no_binding(world):
    """(b) `docs-only` returns before the receipt is read."""
    (world["work"] / "docs").mkdir(exist_ok=True)
    (world["work"] / "docs" / "n.md").write_text("n\n")
    _git(world["work"], "reset", "-q", "--hard", world["base"])
    (world["work"] / "docs").mkdir(exist_ok=True)
    (world["work"] / "docs" / "n.md").write_text("n\n")
    _git(world["work"], "add", "docs/n.md")
    _git(world["work"], "commit", "-q", "-m", "docs only")
    world["head"] = _git(world["work"], "rev-parse", "HEAD")
    move_remote(world, "benchmark/opencode_plugins/datefreeze.js", "// edited upstream\n")
    assert check(world) == []


def test_a_data_only_push_needs_no_binding(world):
    """(b)"""
    _git(world["work"], "reset", "-q", "--hard", world["base"])
    (world["work"] / "benchmark" / "results").mkdir(parents=True)
    (world["work"] / "benchmark" / "results" / "r.json").write_text("{}")
    _git(world["work"], "add", "-A")
    _git(world["work"], "commit", "-q", "-m", "data only")
    world["head"] = _git(world["work"], "rev-parse", "HEAD")
    move_remote(world, "benchmark/opencode_plugins/datefreeze.js", "// edited upstream\n")
    assert check(world) == []


def test_a_fork_push_keeps_the_old_rule_without_a_pushed_base(world):
    """(b) 'Forks and tags unchanged': a mlx-serve code push with a PASS receipt and no `pushed_base` is accepted."""
    receipt_doc = dict(repo="mlx-serve", sha=world["head"], verdict="PASS", policy_digest=DIGEST)
    world["gate"].mkdir(parents=True, exist_ok=True)
    (world["gate"] / f"mlx-serve-{world['head']}-{DIGEST[:12]}.json").write_text(json.dumps(receipt_doc))
    move_remote(world, "benchmark/opencode_plugins/datefreeze.js", "// edited upstream\n")
    assert check(world, repo="mlx-serve") == []
