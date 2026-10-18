"""The pre-P371 tree, executed in isolation (plan 4 A14).

`make_bundle(dest)`: `git archive 0c9bd32a` of every tracked path except `benchmark/results/` and `docs/`, extracted to
`dest`, plus `BUNDLE_MANIFEST.json` (sha256 of every file). Root runtime inputs (`main_models.yaml`, carriers, plugins,
`benchmark/m62/universe.json`, `scripts/`) are tracked and therefore included."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

COMMIT = "0c9bd32a"
EXCLUDES = ("benchmark/results", "docs")
MANIFEST_NAME = "BUNDLE_MANIFEST.json"
# the only files the harness adds to an extracted bundle (copies of the stdlib-only harness modules)
HARNESS_FILES = ("benchmark/bench/tests/p371_driver_run.py", "benchmark/bench/tests/p371_scenario.py",
                 "benchmark/bench/tests/p371_normalize.py")


class BundleError(RuntimeError):
    """The baseline commit is unavailable (missing object or shallow history) or the archive is unusable."""


def run_git(args, cwd):
    got = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=300)
    if got.returncode:
        raise BundleError("git %s failed: %s" % (" ".join(args[:2]), got.stderr.strip()[-300:]))
    return got.stdout.strip()


def repo_root(git=run_git):
    return Path(git(["rev-parse", "--show-toplevel"], Path(__file__).resolve().parent))


def check_history(root=None, commit=COMMIT, git=run_git):
    """Raise `BundleError` unless `commit` resolves to a commit in this repository's (non-shallow) history."""
    root = Path(root) if root else repo_root(git)
    if git(["rev-parse", "--is-shallow-repository"], root) == "true":
        raise BundleError("shallow clone: the baseline commit %s needs full history (git fetch --unshallow)" % commit)
    try:
        kind = git(["cat-file", "-t", commit + "^{commit}"], root)
    except BundleError as exc:
        raise BundleError("baseline commit %s not found in this repository (%s)" % (commit, exc)) from None
    if kind != "commit":
        raise BundleError("baseline commit %s not found (resolves to %r)" % (commit, kind))
    return git(["rev-parse", commit + "^{commit}"], root)


def make_bundle(dest, *, commit=COMMIT, root=None, git=run_git):
    """Extract the baseline tree to `dest` (must not exist yet) and write its manifest; returns the manifest dict."""
    root = Path(root) if root else repo_root(git)
    full = check_history(root, commit, git)
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise BundleError("bundle destination %s is not empty" % dest.name)
    dest.mkdir(parents=True, exist_ok=True)
    got = subprocess.run(["git", "archive", "--format=tar", commit, "--", ".", *[":(exclude)%s" % e for e in EXCLUDES]],
                         cwd=str(root), capture_output=True, timeout=600)
    if got.returncode:
        raise BundleError("git archive failed: " + got.stderr.decode(errors="replace")[-300:])
    with tarfile.open(fileobj=io.BytesIO(got.stdout)) as tar:
        tar.extractall(dest, filter="tar")
    files = {}
    for path in sorted(p for p in dest.rglob("*") if p.is_file() and not p.is_symlink()):
        files[path.relative_to(dest).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if "benchmark/bench/tg1_runner.py" not in files:
        raise BundleError("archive lacks benchmark/bench/tg1_runner.py")
    manifest = {"commit": full, "excluded": list(EXCLUDES), "files": files}
    (dest / MANIFEST_NAME).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def verify_manifest(dest):
    """Problems (empty = intact): files changed, missing or unlisted since the bundle was built."""
    dest = Path(dest)
    manifest = json.loads((dest / MANIFEST_NAME).read_text())
    problems = []
    seen = set()
    for path in sorted(p for p in dest.rglob("*") if p.is_file() and not p.is_symlink()):
        rel = path.relative_to(dest).as_posix()
        if rel == MANIFEST_NAME or "/__pycache__/" in "/" + rel or rel.endswith(".pyc") or rel in HARNESS_FILES:
            continue
        seen.add(rel)
        want = manifest["files"].get(rel)
        if want is None:
            problems.append("unlisted file: " + rel)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != want:
            problems.append("changed file: " + rel)
    problems += ["missing file: " + rel for rel in sorted(set(manifest["files"]) - seen)]
    return problems
