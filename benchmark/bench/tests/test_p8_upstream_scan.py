"""P8: exact upstream scan exceptions, exercised with local Git and real scanners."""

import hashlib
import inspect
import io
import json
import subprocess

import pytest

from bench import local_gate as G
from bench import modelnames, piicheck


CURRENT_POLICY = "d" * 64
HTTPS_ORIGIN = "https://github.com/ivan-avramov/mlx-vlm.git"
SSH_ORIGIN = "git@github.com:ivan-avramov/mlx-vlm.git"
_UNSET = object()


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _fingerprint(findings):
    payload = json.dumps(findings, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _findings(work, sha):
    """The published ordered format; scanners and Git are deliberately never mocked."""
    diff = _git(work, "show", "--format=", "--unified=0", "--root", sha)
    message = _git(work, "show", "-s", "--format=%B", sha)
    return (
        [f"{sha[:8]} PII: {v}" for v in piicheck.diff_violations(diff)]
        + [f"{sha[:8]} naming: {v}" for v in modelnames.diff_violations(diff)]
        + [f"{sha[:8]} message: {v}" for v in modelnames.message_violations(message)]
    )


def _commit(work, filename, content, message):
    (work / filename).write_text(content)
    _git(work, "add", filename)
    _git(work, "commit", "-q", "-m", message)
    return _git(work, "rev-parse", "HEAD")


def _receipt(case, *, repo="mlx-vlm", sha=None, policy=CURRENT_POLICY, verdict="PASS"):
    sha = sha or case["head"]
    case["gate"].mkdir(exist_ok=True)
    path = case["gate"] / f"{repo}-{sha}-{policy[:12]}.json"
    path.write_text(json.dumps(dict(repo=repo, sha=sha, policy_digest=policy, verdict=verdict)))
    return path


def _check(case, *, repo="mlx-vlm", remote="origin", ref="refs/heads/main", url=HTTPS_ORIGIN,
           sha=None, levels=None):
    sha = sha or case["head"]
    kwargs = dict(gate_dir=case["gate"], digest_for=lambda *_: CURRENT_POLICY, levels=levels)
    # Keep preservation tests meaningful on the old baseline, instead of failing at TypeError.
    # The separate interface test below still requires the approved new keyword and default.
    if url is not _UNSET and "remote_url" in inspect.signature(G.check_lines).parameters:
        kwargs["remote_url"] = url
    return G.check_lines(
        repo, case["work"], remote,
        [f"refs/heads/main {sha} {ref} {case['base']}"], **kwargs
    )


@pytest.fixture
def case(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    work = tmp_path / "unrelated-copy-name"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "core.hooksPath", "/dev/null")
    _git(work, "config", "commit.gpgsign", "false")
    _git(work, "config", "user.name", "Fixture")
    _git(work, "config", "user.email", "fixture@example.invalid")
    base = _commit(work, "base.txt", "clean\n", "initial")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "remote", "add", "other", str(remote))
    _git(work, "push", "-q", "origin", "main")
    home = "/".join(("", "Users", "synthetic_fixture_person", "example"))
    content = home + "\nthe 35B model\n"  # allow-shorthand: deliberate scanner input
    message = "document the dense model"  # allow-shorthand: deliberate scanner input
    head = _commit(work, "sample.txt", content, message)
    findings = _findings(work, head)
    assert len(findings) >= 3
    assert all(any(f" {kind}: " in f for f in findings) for kind in ("PII", "naming", "message"))
    approved = {head: _fingerprint(findings)}
    monkeypatch.setattr(G, "MLX_VLM_UPSTREAM_SCAN_EXCEPTIONS", approved, raising=False)
    return dict(work=work, base=base, head=head, gate=tmp_path / "gate", findings=findings,
                approved=approved, content=content, message=message)


def test_supported_interface_has_optional_remote_url():
    parameter = inspect.signature(G.check_lines).parameters.get("remote_url")
    assert parameter is not None and parameter.default is None


@pytest.mark.parametrize("url", [HTTPS_ORIGIN, SSH_ORIGIN])
def test_exact_findings_pass_from_arbitrarily_named_local_copy_with_current_receipt(case, url):
    _receipt(case)
    levels = []
    assert _check(case, url=url, levels=levels) == []
    assert len(levels) == 1 and levels[0].startswith("level: full (receipt ")


@pytest.mark.parametrize("overrides", [
    {"url": _UNSET},
    {"url": None},
    {"url": ""},
    {"url": "https://github.com/Blaizzy/mlx-vlm.git"},
    {"url": "https://github.com/ivan-avramov/mlx-serve.git"},
    {"url": "https://example.invalid/ivan-avramov/mlx-vlm.git"},
    {"url": "https://github.com.example.invalid/ivan-avramov/mlx-vlm.git"},
    {"url": "file:///ivan-avramov/mlx-vlm.git"},
    {"url": "/scratch/mirror/github.com:ivan-avramov/mlx-vlm.git"},
    {"url": "https://example.invalid/mirror/github.com:ivan-avramov/mlx-vlm.git"},
    {"remote": "other"},
    {"repo": "mlx-serve"},
    {"repo": "stack"},
    {"ref": "refs/heads/topic"},
    {"ref": "refs/tags/upstream"},
])
def test_exception_scope_mismatch_preserves_every_original_finding(case, overrides):
    _receipt(case, repo=overrides.get("repo", "mlx-vlm"))
    assert _check(case, **overrides) == case["findings"]


@pytest.mark.parametrize("mutation", ["missing", "extra", "changed", "reordered"])
def test_fingerprint_difference_reports_the_entire_current_finding_set(case, mutation):
    approved_findings = list(case["findings"])
    if mutation == "missing":
        # The approved set had one more finding than the current scan; remaining ones still refuse.
        approved_findings.append(case["findings"][0] + " previously present")
    elif mutation == "extra":
        approved_findings.pop()
    elif mutation == "changed":
        approved_findings[0] += " changed"
    else:
        approved_findings.reverse()
    case["approved"][case["head"]] = _fingerprint(approved_findings)
    _receipt(case)
    assert _check(case) == case["findings"]


@pytest.mark.parametrize("key_kind", ["abbreviated", "different_full_sha"])
def test_exception_requires_the_matching_full_commit_sha(case, key_kind):
    fingerprint = case["approved"].pop(case["head"])
    key = case["head"][:8] if key_kind == "abbreviated" else case["head"][:8] + "0" * 32
    assert key != case["head"]
    case["approved"][key] = fingerprint
    _receipt(case)
    assert _check(case) == case["findings"]


def test_a_different_commit_with_the_same_added_content_and_message_is_not_approved(case):
    original = case["head"]
    _git(case["work"], "checkout", "-q", "--detach", case["base"])
    _commit(case["work"], "other.txt", "clean change\n", "prepare alternate parent")
    alternate = _commit(case["work"], "sample.txt", case["content"], case["message"])
    alternate_findings = _findings(case["work"], alternate)
    assert alternate != original
    assert [f[8:] for f in alternate_findings] == [f[8:] for f in case["findings"]]
    # Even the exact current fingerprint under another full SHA must not waive this commit.
    case["approved"][original] = _fingerprint(alternate_findings)
    _receipt(case, sha=alternate)
    assert _check(case, sha=alternate) == alternate_findings


@pytest.mark.parametrize("receipt_kind", ["absent", "ancestor", "old_policy", "fail"])
def test_exact_scan_exception_still_needs_current_exact_tip_pass_receipt(case, receipt_kind):
    if receipt_kind == "ancestor":
        _receipt(case, sha=case["base"])
    elif receipt_kind == "old_policy":
        _receipt(case, policy="e" * 64)
    elif receipt_kind == "fail":
        _receipt(case, verdict="FAIL")
    out = _check(case)
    assert len(out) == 1 and "no PASS gate receipt" in out[0], out


def test_an_unapproved_descendant_is_still_scanned_and_exact_tip_receipted(case):
    token = "hf_" + "A" * 24
    descendant = _commit(case["work"], "new.txt", token + "\n", "new violation")
    findings = _findings(case["work"], descendant)
    assert len(findings) == 1 and "Hugging Face token" in findings[0]
    _receipt(case, sha=descendant)
    assert _check(case, sha=descendant) == findings
    case["gate"].joinpath(f"mlx-vlm-{descendant}-{CURRENT_POLICY[:12]}.json").unlink()
    _receipt(case)  # A receipt for the approved parent cannot authorize the new tip.
    out = _check(case, sha=descendant)
    assert out[0] == findings[0]
    assert len(out) == 2 and "no PASS gate receipt" in out[1]


def test_an_unapproved_commit_that_introduces_then_removes_a_violation_still_refuses(case):
    descendant = _commit(case["work"], "new.txt", "hf_" + "A" * 24 + "\n", "new violation")
    tip = _commit(case["work"], "new.txt", "clean\n", "remove violation")
    _receipt(case, sha=tip)
    assert _check(case, sha=tip) == _findings(case["work"], descendant)


def test_fetch_failure_still_refuses_before_applying_approved_scans(case):
    _receipt(case)
    _git(case["work"], "remote", "set-url", "origin", str(case["work"].parent / "missing.git"))
    out = _check(case)
    assert len(out) == 1 and "fetch" in out[0] and "refused" in out[0]


def test_hook_facing_cli_forwards_the_supplied_push_url(tmp_path, monkeypatch):
    """Only this wiring test spies on calls; behavior tests above use real Git and scans."""
    captured = {}

    def check_spy(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return []

    monkeypatch.setattr(G, "_git", lambda *_args, **_kwargs: HTTPS_ORIGIN)
    monkeypatch.setattr(G, "_workdir", lambda: tmp_path)
    monkeypatch.setattr(G, "check_lines", check_spy)
    monkeypatch.setattr(G.sys, "stdin", io.StringIO("push input\n"))
    assert G.main(["check", "--repo-dir", str(tmp_path), "origin", SSH_ORIGIN]) == 0
    assert captured["args"] == ("mlx-vlm", str(tmp_path), "origin", ["push input"])
    assert captured["kwargs"].get("remote_url") == SSH_ORIGIN
