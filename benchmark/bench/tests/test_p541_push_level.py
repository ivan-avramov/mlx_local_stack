"""P541 (`docs/specs/p541-push-levels.md` v1.1): a branch push (and a fork tag push) passes its stated level — data-only,
docs-only, full (a PASS gate receipt for exactly the pushed sha under the current policy), or none-new — and the pre-push hook
prints the level per ref.
Hermetic: tiny local git repositories under `tmp_path` with a bare remote, an injected `gate_dir` / `digest_for`, the global
git config and the machine hooks shut out, `STACK_WORKDIR` pointed at `tmp_path`."""

import io
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from bench import local_gate as G

ZERO = "0" * 40
DIGEST = "d" * 64
REPOS = ("stack", "mlx-vlm", "mlx-serve")
FORKS = ("mlx-vlm", "mlx-serve")


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(k, raising=False)


def _git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()


def _commit(work, files=None, msg="change", allow_empty=False):
    for rel, text in (files or {}).items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", msg, *(["--allow-empty"] if allow_empty else []))
    return _git(work, "rev-parse", "HEAD")


@pytest.fixture
def box(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, capture_output=True)
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("core.hooksPath", os.devnull),
                 ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        _git(work, "config", k, v)
    base = _commit(work, {"README.md": "r\n", "code.py": "x = 1\n"}, "init")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "origin", "main")
    return SimpleNamespace(tmp=tmp_path, work=work, remote=remote, base=base, gate=tmp_path / "gate")


class Digests:
    def __init__(self, value=DIGEST):
        self.value, self.calls = value, []

    def __call__(self, repo, sha):
        self.calls.append((repo, sha))
        return self.value


def _receipt(gate, repo, sha, digest=DIGEST, verdict="PASS"):
    gate.mkdir(parents=True, exist_ok=True)
    name = f"{repo}-{sha}-{digest[:12]}.json"
    (gate / name).write_text(json.dumps(dict(repo=repo, sha=sha, verdict=verdict, policy_digest=digest)))
    return name


def _receipt_named(gate, repo, name_sha, name_digest=DIGEST, **doc):
    """A receipt FILE named for `name_sha` / `name_digest` whose content overrides `doc` (wrong inner sha / digest /
    verdict)."""
    gate.mkdir(parents=True, exist_ok=True)
    body = dict(dict(repo=repo, sha=name_sha, verdict="PASS", policy_digest=name_digest), **doc)
    (gate / f"{repo}-{name_sha}-{name_digest[:12]}.json").write_text(json.dumps(body))


def _not_orphan(sha, remote="origin"):
    return (f"REFUSED: stack {sha[:8]}: pushed to refs/heads/evidence shares history with {remote}/main: "
            f"not an orphan data commit")


def _digest_refusal_prefix(repo, sha):
    return f"REFUSED: {repo} {sha[:8]}: cannot compute the policy digest ("


def _refusal(repo, sha):
    return (f"REFUSED: {repo} {sha[:8]}: no PASS gate receipt for a code push (level full required; "
            f"run: bench.local_gate run --repo {repo} --sha {sha})")


def _level(b, sha, repo, remote_ref="refs/heads/main", local_ref=None, digest_for=None):
    return G.push_level(repo, b.work, "origin", local_ref or remote_ref, sha, remote_ref, gate_dir=b.gate,
                        digest_for=digest_for or Digests())


def _check(b, lines, repo):
    return G.check_lines(repo, b.work, "origin", lines, gate_dir=b.gate, digest_for=Digests())


def _line(sha, remote_ref="refs/heads/main", old=None, local_ref=None):
    return f"{local_ref or remote_ref} {sha} {remote_ref} {old or ZERO}"


def _leak():
    return "/".join(("", "Users", "otherperson", "x"))  # built at runtime: the literal fails the repo PII scan


def _orphan(work, files, branch="evidence"):
    _git(work, "checkout", "-q", "--orphan", branch)
    _git(work, "rm", "-rq", "--cached", ".")
    for rel, text in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    _git(work, "add", *files)
    _git(work, "commit", "-q", "-m", "data(bench): evidence backfill")
    return _git(work, "rev-parse", "HEAD")


# ------------------------------------------------------------------ path classification
@pytest.mark.parametrize("path, want", [
    ("docs/x.md", True), ("docs/specs/p541-push-levels.md", True), ("docs/img/a.png", True),
    ("README.md", True), ("AGENTS.md", True),
    ("benchmark/README.md", False), ("src/docs/x.md", False), ("docsx/a.md", False), ("README.txt", False),
    ("code.py", False), ("benchmark/results/a.jsonl", False),
    # v1.1: case-sensitive; `docs/**` needs the `docs/` prefix; top-level `*.md` is lower-case `.md` only
    ("docs", False), ("Docs/x.md", False), ("DOCS/x.md", False), ("README.MD", False), ("README.Md", False),
    # v1.3: no stripping — a top-level directory ` docs` is not `docs/`; `README.md ` does not end in `.md`
    (" docs/x.py", False), (" docs/x.md", False), ("README.md ", False), ("\ndocs/x.md", False),
])
def test_is_docs_path(path, want):
    assert G.is_docs_path(path) is want


@pytest.mark.parametrize("path, want", [
    ("benchmark/results/a.jsonl", True), ("benchmark/results/m1/receipt.json", True),
    ("benchmark/resultsx/a.jsonl", False), ("results/a.jsonl", False), ("benchmark/bench/x.py", False),
    ("docs/x.md", False), ("README.md", False),
    # v1.1: case-sensitive; needs the `benchmark/results/` prefix
    ("benchmark/results", False), ("Benchmark/results/a.jsonl", False), ("benchmark/Results/a.jsonl", False),
    (" benchmark/results/x.py", False),  # v1.3
])
def test_is_data_path(path, want):
    assert G.is_data_path(path) is want


# ------------------------------------------------------------------ levels (push_level)
@pytest.mark.parametrize("repo", REPOS)
def test_a_docs_only_push_is_docs_only_without_a_receipt(box, repo):
    sha = _commit(box.work, {"docs/specs/x.md": "s\n", "README.md": "r2\n"})
    assert _level(box, sha, repo) == ("docs-only", "", [])


def test_a_stack_results_only_branch_push_is_data_only(box):
    sha = _commit(box.work, {"benchmark/results/m1/a.jsonl": "{}\n", "benchmark/results/b.json": "{}\n"})
    assert _level(box, sha, "stack") == ("data-only", "", [])


@pytest.mark.parametrize("repo", FORKS)
def test_a_fork_results_path_is_not_data_only_and_needs_a_receipt(box, repo):
    sha = _commit(box.work, {"benchmark/results/a.jsonl": "{}\n"})
    assert _level(box, sha, repo) == ("full", "", [_refusal(repo, sha)])


@pytest.mark.parametrize("repo", REPOS)
def test_a_code_push_without_a_receipt_refuses(box, repo):
    sha = _commit(box.work, {"code.py": "x = 2\n"})
    level, _detail, problems = _level(box, sha, repo)
    assert level == "full" and problems == [_refusal(repo, sha)]


@pytest.mark.parametrize("repo", REPOS)
def test_a_code_push_with_a_PASS_receipt_for_the_sha_is_full(box, repo):
    sha = _commit(box.work, {"code.py": "x = 2\n"})
    name = _receipt(box.gate, repo, sha)
    digests = Digests()
    assert _level(box, sha, repo, digest_for=digests) == ("full", name, [])  # v1.1: detail = the receipt file name
    assert (repo, sha) in digests.calls


@pytest.mark.parametrize("kind", ["another-sha", "FAIL", "another-digest"])
def test_a_receipt_that_is_not_a_PASS_for_this_sha_under_this_policy_refuses(box, kind):
    sha = _commit(box.work, {"code.py": "x = 2\n"})
    if kind == "another-sha":
        _receipt(box.gate, "mlx-serve", box.base)
    elif kind == "FAIL":
        _receipt(box.gate, "mlx-serve", sha, verdict="FAIL")
    else:
        _receipt(box.gate, "mlx-serve", sha, digest="e" * 64)
    assert _level(box, sha, "mlx-serve") == ("full", "", [_refusal("mlx-serve", sha)])


@pytest.mark.parametrize("inner", [dict(policy_digest="e" * 64), dict(sha="a" * 40), dict(verdict="FAIL")],
                         ids=["inner-digest", "inner-sha", "inner-FAIL"])
def test_a_receipt_file_named_right_but_wrong_inside_refuses(box, inner):
    """The file name matches the sha and the digest; the content does not."""
    sha = _commit(box.work, {"code.py": "x = 2\n"})
    _receipt_named(box.gate, "mlx-serve", sha, **inner)
    assert _level(box, sha, "mlx-serve") == ("full", "", [_refusal("mlx-serve", sha)])


@pytest.mark.parametrize("split", [False, True], ids=["one-commit", "two-commits"])
def test_mixed_docs_and_code_is_full(box, split):
    if split:
        _commit(box.work, {"docs/x.md": "d\n"})
        sha = _commit(box.work, {"code.py": "x = 2\n"})
    else:
        sha = _commit(box.work, {"docs/x.md": "d\n", "code.py": "x = 2\n"})
    assert _level(box, sha, "stack") == ("full", "", [_refusal("stack", sha)])


@pytest.mark.parametrize("split", [False, True], ids=["one-commit", "two-commits"])
def test_mixed_docs_and_data_is_full(box, split):
    if split:
        _commit(box.work, {"docs/x.md": "d\n"})
        sha = _commit(box.work, {"benchmark/results/a.jsonl": "{}\n"})
    else:
        sha = _commit(box.work, {"docs/x.md": "d\n", "benchmark/results/a.jsonl": "{}\n"})
    assert _level(box, sha, "stack") == ("full", "", [_refusal("stack", sha)])


@pytest.mark.parametrize("repo", REPOS)
@pytest.mark.parametrize("n", [1, 2], ids=["one-empty-commit", "two-empty-commits"])
def test_an_empty_P_is_full(box, repo, n):
    """v1.1: a push whose P is empty (only empty-diff commits) is full."""
    for _ in range(n):
        sha = _commit(box.work, allow_empty=True)
    assert _level(box, sha, repo) == ("full", "", [_refusal(repo, sha)])


@pytest.mark.parametrize("repo", REPOS)
@pytest.mark.parametrize("empty_last", [False, True], ids=["empty-first", "empty-last"])
def test_a_docs_commit_plus_an_empty_commit_is_docs_only(box, repo, empty_last):
    """v1.1: P is non-empty and all docs; the empty commit adds nothing."""
    if empty_last:
        _commit(box.work, {"docs/x.md": "d\n"})
        sha = _commit(box.work, allow_empty=True)
    else:
        _commit(box.work, allow_empty=True)
        sha = _commit(box.work, {"docs/x.md": "d\n"})
    assert _level(box, sha, repo) == ("docs-only", "", [])


@pytest.mark.parametrize("repo", REPOS)
def test_a_new_branch_name_for_a_pushed_commit_is_none_new(box, repo):
    assert _level(box, box.base, repo, remote_ref="refs/heads/topic") == ("none-new", "", [])


def test_a_merge_contributes_its_diff_against_its_first_parent(box):
    """The merge brings in code already on the remote (`origin/topic`): its first-parent diff is code, so the push is full."""
    w = box.work
    _git(w, "checkout", "-q", "-b", "topic")
    _commit(w, {"code2.py": "y = 1\n"})
    _git(w, "push", "-q", "origin", "topic")
    _git(w, "checkout", "-q", "main")
    _commit(w, {"docs/a.md": "a\n"})
    _git(w, "merge", "-q", "--no-ff", "-m", "merge topic", "topic")
    sha = _git(w, "rev-parse", "HEAD")
    assert _level(box, sha, "stack") == ("full", "", [_refusal("stack", sha)])


def test_a_merge_of_docs_only_commits_stays_docs_only(box):
    w = box.work
    _git(w, "checkout", "-q", "-b", "topic")
    _commit(w, {"docs/b.md": "b\n"})
    _git(w, "checkout", "-q", "main")
    _commit(w, {"docs/a.md": "a\n"})
    _git(w, "merge", "-q", "--no-ff", "-m", "merge topic", "topic")
    sha = _git(w, "rev-parse", "HEAD")
    assert _level(box, sha, "stack") == ("docs-only", "", [])


@pytest.mark.parametrize("repo, path, want", [
    ("stack", " docs/x.py", "full"), ("mlx-vlm", " docs/x.py", "full"), ("mlx-serve", " docs/x.py", "full"),
    ("stack", " benchmark/results/x.py", "full"),
    ("mlx-vlm", "README.md ", "full"),          # a trailing space: not `.md`
    ("mlx-vlm", "\ndocs/x.md", "full"),          # a leading newline: not `docs/`
    ("mlx-vlm", "docs/a\nb.py", "docs-only"),    # a newline inside a docs path: one path, not two
], ids=["space-docs-stack", "space-docs-vlm", "space-docs-serve", "space-results-stack", "trailing-space-md",
        "leading-newline-docs", "inner-newline-docs"])
def test_paths_are_read_losslessly(box, repo, path, want):
    """v1.3: the `-z` path list is split on NUL with nothing stripped (the sole / first path included)."""
    sha = _commit(box.work, {path: "x\n"})
    expected = ("full", "", [_refusal(repo, sha)]) if want == "full" else (want, "", [])
    assert _level(box, sha, repo) == expected


def _evidence_only_commit(b, files):
    """An orphan commit pushed to `origin/evidence` only (the work tree stays on the orphan branch)."""
    sha = _orphan(b.work, files)
    _git(b.work, "push", "-q", "origin", "evidence")
    return sha


def test_a_branch_at_an_evidence_only_code_commit_is_classified_by_its_paths(box):
    """v1.3: `origin/evidence` is not in the `--not` set of a non-evidence push — never none-new."""
    sha = _evidence_only_commit(box, {"code.py": "z = 1\n"})
    assert _level(box, sha, "stack", remote_ref="refs/heads/topic") == ("full", "", [_refusal("stack", sha)])
    assert _check(box, [_line(sha, "refs/heads/topic")], "stack") == [_refusal("stack", sha)]


def test_a_branch_at_an_evidence_only_data_commit_is_data_only_not_none_new(box):
    sha = _evidence_only_commit(box, {"benchmark/results/a.jsonl": "{}\n"})
    assert _level(box, sha, "stack", remote_ref="refs/heads/topic") == ("data-only", "", [])


def test_push_level_refuses_a_stack_evidence_push_sharing_history_with_main(box):
    """v1.3: `push_level` owns the evidence orphan rule."""
    sha = _commit(box.work, {"benchmark/results/a.jsonl": "{}\n"})
    _level_name, _detail, problems = _level(box, sha, "stack", remote_ref="refs/heads/evidence", local_ref="refs/heads/main")
    assert problems == [_not_orphan(sha)]


def test_push_level_accepts_a_stack_evidence_orphan_as_data_only(box):
    sha = _orphan(box.work, {"report.log": "ok\n"})
    assert _level(box, sha, "stack", remote_ref="refs/heads/evidence") == ("data-only", "", [])


@pytest.mark.parametrize("repo", FORKS)
def test_push_level_resolves_a_tag_to_its_commit(box, repo):
    """v1.3: `push_level` resolves `<local_sha>^{commit}` itself — the refusal names the tagged commit."""
    sha = _commit(box.work, {"code.py": "x = 2\n"})
    tag = _tag(box.work, "v1.0.0")
    assert tag != sha
    assert _level(box, tag, repo, remote_ref="refs/tags/v1.0.0") == ("full", "", [_refusal(repo, sha)])


@pytest.mark.parametrize("exc", [G.GateError("no UPSTREAM_SYNC_REF"), OSError("baseline unreadable")],
                         ids=["GateError", "OSError"])
def test_push_level_turns_a_failing_policy_digest_into_a_level_problem(box, exc):
    sha = _commit(box.work, {"code.py": "x = 2\n"})

    def raising(repo, s):
        raise exc

    _level_name, _detail, problems = _level(box, sha, "mlx-vlm", digest_for=raising)
    assert len(problems) == 1 and problems[0].startswith(_digest_refusal_prefix("mlx-vlm", sha))
    assert str(exc) in problems[0] and problems[0].endswith(")")


def test_push_level_does_not_fetch(box):
    """Interface: pure apart from git reads — the fetch stays in `check_lines`."""
    sha = _commit(box.work, {"docs/x.md": "d\n"})
    _git(box.work, "remote", "set-url", "origin", str(box.tmp / "missing.git"))
    assert _level(box, sha, "mlx-serve") == ("docs-only", "", [])


# ------------------------------------------------------------------ evidence (P447 unchanged)
def test_a_stack_evidence_orphan_is_data_only_and_pii_only(box):
    content = "Ornith ran fine\n"  # data: naming is not checked  # allow-shorthand
    sha = _orphan(box.work, {"report.log": content, "code.py": "z = 1\n"})
    assert _level(box, sha, "stack", remote_ref="refs/heads/evidence") == ("data-only", "", [])
    assert _check(box, [_line(sha, "refs/heads/evidence")], "stack") == []


def test_a_stack_evidence_push_sharing_history_with_main_still_refuses_as_not_orphan(box):
    """v1.1: stays refused; v1.3: with the `push_level` problem text, once (no duplicate check in `check_lines`)."""
    sha = _commit(box.work, {"benchmark/results/a.jsonl": "{}\n"})
    out = _check(box, [_line(sha, "refs/heads/evidence", local_ref="refs/heads/main")], "stack")
    assert out == [_not_orphan(sha)]


@pytest.mark.parametrize("repo", FORKS)
def test_a_fork_evidence_branch_is_not_exempt(box, repo):
    sha = _orphan(box.work, {"code.py": "z = 1\n"})
    assert _check(box, [_line(sha, "refs/heads/evidence")], repo) == [_refusal(repo, sha)]


# ------------------------------------------------------------------ check_lines: scans at every level, the refusal
@pytest.mark.parametrize("repo", REPOS)
def test_check_lines_refuses_a_code_branch_push_without_a_receipt(box, repo):
    sha = _commit(box.work, {"code.py": "x = 2\n"})
    assert _check(box, [_line(sha, old=box.base)], repo) == [_refusal(repo, sha)]


def test_check_lines_refuses_a_new_code_branch_without_a_receipt(box):
    sha = _commit(box.work, {"code.py": "x = 2\n"})
    assert _check(box, [_line(sha, "refs/heads/topic")], "stack") == [_refusal("stack", sha)]


@pytest.mark.parametrize("repo, path, want", [
    ("mlx-vlm", "docs/x.md", "docs-only"),
    ("stack", "benchmark/results/a.jsonl", "data-only"),
    ("mlx-serve", "code.py", "full"),
], ids=["docs-only", "data-only", "full"])
def test_the_pii_scan_still_runs_at_every_level(box, repo, path, want):
    """v1.1: scan problems come from `check_lines`; `push_level` returns only level problems."""
    sha = _commit(box.work, {path: _leak() + "\n"})
    name = _receipt(box.gate, repo, sha) if want == "full" else ""
    assert _level(box, sha, repo) == (want, name, [])
    assert any("PII" in o for o in _check(box, [_line(sha, old=box.base)], repo))


def test_the_pii_scan_still_runs_on_evidence(box):
    sha = _orphan(box.work, {"report.log": _leak() + "\n"})
    assert _level(box, sha, "stack", remote_ref="refs/heads/evidence") == ("data-only", "", [])
    assert any("PII" in o for o in _check(box, [_line(sha, "refs/heads/evidence")], "stack"))


def test_the_message_scan_still_runs_on_a_docs_only_push(box):
    sha = _commit(box.work, {"docs/x.md": "d\n"}, msg="Ornith regressed")  # allow-shorthand: the violation under test
    assert _level(box, sha, "mlx-vlm") == ("docs-only", "", [])
    assert any("message" in o for o in _check(box, [_line(sha, old=box.base)], "mlx-vlm"))


# ------------------------------------------------------------------ tags (v1.1: fork tags need a level; stack tags P448)
def _tag(work, name):
    _git(work, "tag", "-a", name, "-m", "release")
    return _git(work, "rev-parse", name)


@pytest.mark.parametrize("repo", FORKS)
def test_a_fork_code_tag_without_a_receipt_refuses(box, repo):
    """v1.1: a fork tag uploads its commits, so it needs a level like a branch push; v1.2: the refusal names the tagged
    commit."""
    sha = _commit(box.work, {"code.py": "x = 2\n"})
    tag = _tag(box.work, "v1.0.0")
    assert tag != sha
    assert _check(box, [_line(tag, "refs/tags/v1.0.0")], repo) == [_refusal(repo, sha)]


@pytest.mark.parametrize("repo", FORKS)
def test_a_fork_code_tag_with_a_receipt_for_the_tagged_commit_passes(box, repo):
    """Passes before P541 too (scan-only); guards that receipts are looked up by the tagged commit (receipts are per commit)."""
    sha = _commit(box.work, {"code.py": "x = 2\n"})
    tag = _tag(box.work, "v1.0.0")
    _receipt(box.gate, repo, sha)
    assert _check(box, [_line(tag, "refs/tags/v1.0.0")], repo) == []


@pytest.mark.parametrize("repo", FORKS)
def test_a_fork_docs_only_tag_passes(box, repo):
    """Passes before P541 too (scan-only); the level line is `test_main_prints_the_level_of_a_fork_docs_only_tag`."""
    _commit(box.work, {"docs/x.md": "d\n"})
    tag = _tag(box.work, "v1.0.0")
    assert _check(box, [_line(tag, "refs/tags/v1.0.0")], repo) == []


def test_a_stack_tag_keeps_the_release_rule_not_the_branch_refusal(box):
    """Regression guard (passes before P541 too): stack tags keep P448 unchanged."""
    _commit(box.work, {"code.py": "x = 2\n"})
    tag = _tag(box.work, "v1.0.0")
    out = _check(box, [_line(tag, "refs/tags/v1.0.0")], "stack")
    assert any("no PASS release receipt" in o for o in out)
    assert not any("for a code push" in o for o in out)


# ------------------------------------------------------------------ the printed level lines (main → check)
@pytest.fixture
def hook(box, monkeypatch):
    """`main check` against the box: origin carries the canonical URL (never fetched), `local` is the bare remote."""
    w = box.work
    _git(w, "remote", "rename", "origin", "local")
    monkeypatch.setattr(G, "digest_for", lambda *a, **k: DIGEST)

    def run(repo, lines):
        if "origin" in _git(w, "remote").split():
            _git(w, "remote", "remove", "origin")
        _git(w, "remote", "add", "origin", f"https://github.com/{G.CANONICAL[repo]}.git")
        _git(w, "remote", "set-url", "--push", "origin", "no_push")
        monkeypatch.setattr(sys, "stdin", io.StringIO("".join(l + "\n" for l in lines)))
        return G.main(["check", "--repo-dir", str(w), "local", "x"])

    box.run, box.gate = run, box.tmp / "wd" / "gate"
    return box


def _stderr_lines(capsys):
    return capsys.readouterr().err.splitlines()


def test_main_prints_the_docs_only_level(hook, capsys):
    sha = _commit(hook.work, {"docs/x.md": "d\n"})
    assert hook.run("mlx-vlm", [_line(sha, old=hook.base)]) == 0
    assert f"[pre-push] level: docs-only refs/heads/main {sha[:8]}" in _stderr_lines(capsys)


def test_main_prints_the_data_only_level(hook, capsys):
    sha = _commit(hook.work, {"benchmark/results/a.jsonl": "{}\n"})
    assert hook.run("stack", [_line(sha, old=hook.base)]) == 0
    assert f"[pre-push] level: data-only refs/heads/main {sha[:8]}" in _stderr_lines(capsys)


def test_main_prints_the_data_only_level_for_evidence(hook, capsys):
    sha = _orphan(hook.work, {"report.log": "ok\n"})
    assert hook.run("stack", [_line(sha, "refs/heads/evidence")]) == 0
    assert f"[pre-push] level: data-only refs/heads/evidence {sha[:8]}" in _stderr_lines(capsys)


def test_main_prints_the_none_new_level(hook, capsys):
    assert hook.run("mlx-serve", [_line(hook.base, "refs/heads/topic")]) == 0
    assert f"[pre-push] level: none-new refs/heads/topic {hook.base[:8]}" in _stderr_lines(capsys)


def test_main_prints_the_full_level_with_the_receipt_file_name(hook, capsys):
    sha = _commit(hook.work, {"code.py": "x = 2\n"})
    name = _receipt(hook.gate, "mlx-serve", sha)
    assert hook.run("mlx-serve", [_line(sha, old=hook.base)]) == 0
    assert f"[pre-push] level: full (receipt {name}) refs/heads/main {sha[:8]}" in _stderr_lines(capsys)


def test_main_prints_the_refusal_and_exits_1(hook, capsys):
    sha = _commit(hook.work, {"code.py": "x = 2\n"})
    assert hook.run("stack", [_line(sha, old=hook.base)]) == 1
    assert f"[pre-push] {_refusal('stack', sha)}" in _stderr_lines(capsys)  # v1.1: `main` prefixes `[pre-push] `


@pytest.mark.parametrize("refused_first", [False, True], ids=["refused-last", "refused-first"])
def test_main_prints_the_passing_refs_level_lines_when_another_ref_refuses(hook, capsys, refused_first):
    """v1.1: the level lines of the refs that passed are still printed; the push exits 1."""
    w = hook.work
    docs = _commit(w, {"docs/x.md": "d\n"})
    _git(w, "checkout", "-q", "-b", "topic")
    code = _commit(w, {"code.py": "x = 2\n"})
    lines = [_line(docs, old=hook.base), _line(code, "refs/heads/topic")]
    assert hook.run("mlx-vlm", lines[::-1] if refused_first else lines) == 1
    err = _stderr_lines(capsys)
    assert f"[pre-push] level: docs-only refs/heads/main {docs[:8]}" in err
    assert f"[pre-push] {_refusal('mlx-vlm', code)}" in err
    assert not any(l.startswith("[pre-push] level: ") and "refs/heads/topic" in l for l in err)


@pytest.mark.parametrize("repo", FORKS)
def test_main_prints_the_level_of_a_fork_docs_only_tag(hook, capsys, repo):
    """v1.2: the level line names the tagged commit's sha8."""
    sha = _commit(hook.work, {"docs/x.md": "d\n"})
    tag = _tag(hook.work, "v1.0.0")
    assert tag[:8] != sha[:8]
    assert hook.run(repo, [_line(tag, "refs/tags/v1.0.0")]) == 0
    assert f"[pre-push] level: docs-only refs/tags/v1.0.0 {sha[:8]}" in _stderr_lines(capsys)


@pytest.mark.parametrize("repo", FORKS)
def test_main_prints_the_full_level_of_a_fork_code_tag_and_its_refusal_with_the_commit_sha(hook, capsys, repo):
    sha = _commit(hook.work, {"code.py": "x = 2\n"})
    tag = _tag(hook.work, "v1.0.0")
    assert hook.run(repo, [_line(tag, "refs/tags/v1.0.0")]) == 1
    assert f"[pre-push] {_refusal(repo, sha)}" in _stderr_lines(capsys)
    name = _receipt(hook.gate, repo, sha)
    assert hook.run(repo, [_line(tag, "refs/tags/v1.0.0")]) == 0
    assert f"[pre-push] level: full (receipt {name}) refs/tags/v1.0.0 {sha[:8]}" in _stderr_lines(capsys)


@pytest.mark.parametrize("bad_first", [False, True], ids=["bad-last", "bad-first"])
def test_main_a_failing_policy_digest_refuses_its_ref_and_the_other_ref_keeps_its_line(hook, capsys, monkeypatch, bad_first):
    """v1.3: `digest_for` raising is a level problem for that ref; the other refs still get their lines."""
    w = hook.work
    good = _commit(w, {"code.py": "x = 2\n"})
    name = _receipt(hook.gate, "mlx-serve", good)
    _git(w, "checkout", "-q", "-b", "topic")
    bad = _commit(w, {"code.py": "x = 3\n"})

    def digest_for(repo, sha, *a, **k):
        if sha == bad:
            raise G.GateError("no UPSTREAM_SYNC_REF")
        return DIGEST

    monkeypatch.setattr(G, "digest_for", digest_for)
    lines = [_line(good, old=hook.base), _line(bad, "refs/heads/topic")]
    assert hook.run("mlx-serve", lines[::-1] if bad_first else lines) == 1
    err = _stderr_lines(capsys)
    assert f"[pre-push] level: full (receipt {name}) refs/heads/main {good[:8]}" in err
    refused = [l for l in err if l.startswith("[pre-push] " + _digest_refusal_prefix("mlx-serve", bad))]
    assert len(refused) == 1 and "no UPSTREAM_SYNC_REF" in refused[0]
    assert not any(l.startswith("[pre-push] level: ") and "refs/heads/topic" in l for l in err)


def test_main_a_ref_with_a_scan_problem_prints_no_level_line(hook, capsys):
    """v1.3: only refs with no problems at all (level or scan) print their level line."""
    w = hook.work
    _git(w, "checkout", "-q", "-b", "topic")
    leaky = _commit(w, {"docs/x.md": _leak() + "\n"})
    lines = [_line(leaky, "refs/heads/topic"), _line(hook.base, "refs/heads/old-name")]
    assert hook.run("mlx-vlm", lines) == 1
    err = _stderr_lines(capsys)
    assert any("PII" in l for l in err)
    assert not any(l.startswith("[pre-push] level: ") and "refs/heads/topic" in l for l in err)
    assert f"[pre-push] level: none-new refs/heads/old-name {hook.base[:8]}" in err


def test_main_prints_one_level_line_per_ref(hook, capsys):
    docs = _commit(hook.work, {"docs/x.md": "d\n"})
    assert hook.run("mlx-vlm", [_line(docs, old=hook.base), _line(hook.base, "refs/heads/old-name")]) == 0
    levels = [l for l in _stderr_lines(capsys) if l.startswith("[pre-push] level: ")]
    assert levels == [f"[pre-push] level: docs-only refs/heads/main {docs[:8]}",
                      f"[pre-push] level: none-new refs/heads/old-name {hook.base[:8]}"]
