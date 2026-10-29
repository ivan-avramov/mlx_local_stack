"""P541 implementation extras: receipt lookup helper and path quoting in the level computation."""

import json
import subprocess

from bench import local_gate as G


def test_pass_receipt_returns_the_name_of_a_pass_receipt_only(tmp_path):
    sha, digest = "a" * 40, "d" * 64
    assert G.pass_receipt(tmp_path, "stack", sha, digest) is None
    (tmp_path / f"stack-{sha}-{digest[:12]}.json").write_text(
        json.dumps(dict(sha=sha, verdict="FAIL", policy_digest=digest)))
    assert G.pass_receipt(tmp_path, "stack", sha, digest) is None
    (tmp_path / f"stack-{sha}-{digest[:12]}-1.json").write_text(
        json.dumps(dict(sha=sha, verdict="PASS", policy_digest=digest)))
    assert G.pass_receipt(tmp_path, "stack", sha, digest) == f"stack-{sha}-{digest[:12]}-1.json"
    assert G.has_pass(tmp_path, "stack", sha, digest)


def test_a_non_ascii_docs_path_is_still_docs_only(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    for a in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "t"),
              ("config", "commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(work), *a], check=True, capture_output=True)
    (work / "docs").mkdir()
    (work / "docs" / "café.md").write_text("x\n")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "d"], check=True, capture_output=True)
    sha = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert G._touched(work, sha) == ["docs/café.md"]


def test_a_non_utf8_path_is_classified_as_code_without_raising(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    remote, work = tmp_path / "remote.git", tmp_path / "w"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, capture_output=True)

    def git(*a, **kw):
        return subprocess.run(["git", "-C", str(work), *a], check=True, capture_output=True, **kw).stdout

    for a in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "t"),
              ("config", "commit.gpgsign", "false"), ("config", "core.hooksPath", "/dev/null"),
              ("remote", "add", "origin", str(remote))):
        git(*a)
    (work / "README.md").write_text("r\n")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    git("push", "-q", "origin", "main")
    blob = git("hash-object", "-w", "--stdin", input=b"x\n").decode().strip()
    git("update-index", "--add", "--cacheinfo", b"100644," + blob.encode() + b",bad\xff.py")  # a real 0xff byte in the name
    git("commit", "-q", "-m", "bad path")
    sha = git("rev-parse", "HEAD").decode().strip()
    assert G._touched(work, sha) == [b"bad\xff.py".decode("utf-8", "surrogateescape")]
    level, _detail, problems = G.push_level("mlx-serve", work, "origin", "refs/heads/main", sha, "refs/heads/main",
                                            gate_dir=tmp_path / "gate", digest_for=lambda repo, s: "d" * 64)
    assert level == "full" and len(problems) == 1 and "no PASS gate receipt" in problems[0]
