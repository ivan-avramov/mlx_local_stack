"""The pre-P371 tree, executed in isolation (plan 4 A14).

`make_bundle(dest)`: `git archive 0c9bd32a` of every tracked path except `benchmark/results/` and `docs/`, extracted to
`dest`, plus `BUNDLE_MANIFEST.json` (sha256 of every file). Root runtime inputs (`main_models.yaml`, carriers, plugins,
`benchmark/m62/universe.json`, `scripts/`) are tracked and therefore included.

TWO files are overlaid onto the archived tree (P476 change review): `benchmark/opencode_bench_v2_web.json` (the carrier the
baseline probe core reads) and `benchmark/opencode_bench_v2_web_tg1.json` (a probe generation-data file, so it moves
`probe_code_sha256`), each replaced by a committed pinned copy next to this module (the post-P476 carriers; the sha256 of each
is asserted in `OVERLAY_SHA256` and `make_bundle` refuses a copy that differs). The other two carriers (`opencode_bench.json`,
`opencode_bench_v2.json`) are not read by any scenario and stay at 0c9bd32a (verified: goldens are identical without them). The
override is recorded in `BUNDLE_MANIFEST.json` as `overlaid_files: {path: sha256}`. The live tree is NOT read: a later carrier
change makes the differential fail on purpose, and the pins are then refreshed deliberately (copy the carrier, update
`OVERLAY_SHA256`, `./regen_p371_goldens.sh`, record old -> new below)."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

COMMIT = "0c9bd32a"
EXCLUDES = ("benchmark/results", "docs")
# P476 golden refresh (old -> new; only these carrier-derived fields moved, 11 item goldens):
#   carrier_source_sha256 / opencode_bench_config_sha256 / carrier_sha256
#     ac67688b16ab239467e2c38f4fd20cdef4a3600a3749b75d1f7adb6d2ba79bad -> 29d3c0bab93a28ba2dc3ca90a645dfe9a0013dce70162aa5a283a1e5179fab84
#   probe_code_sha256  ae7fca94e77b1ea025f67bbac27a0b816aa0f8de8b771aa3683a8170a80fc2a1 -> 4e9e19d273a369922ebd1c6a3fd3bdf00b1bdf4fffb9cb9c9625daa1cfcf3ebe
#   scaffold_policy_sha256 (one value per gate-policy variant):
#     eb5fa7a7b9a8c46e1d622d32a8662757c284a5440b5515ba25464533740fd36a -> 4963d2f92833333f574c2303c3f685936802c22048fcf796645805184bc8ccd3
#     6420eab4418a77ac8fbcdbe15cf71b15c1e53c3aa2daea7603614c8c44c3687d -> 05cbd3296446d587fbee3a8b22fe5b9abad468d2c3cf7f7c8e0d17fdd96733cd (hard_ceiling_kill)
#     823c0b1182bc7b3d808a7c2ebba9e17a28df4a69ed425f41abbc154a4b891886 -> 40561e99c5cc94b9972799b019c3cc775adb7f283fa36fa6b12d30ed309f1c9c (stall_kill)
#     c4a89115fcf1a98d8eb20d6e6b14ed94d86cfb11172d1544ff77cb9d624957f5 -> 7140cf6efcbdd62947b27dbcc6bf8e27c42b6cfc6baaf441e59454a39e9c8b49 (loop_kill)
# the carriers the P371 scenarios read, overlaid from committed pinned copies, not the live tree
HERE = Path(__file__).resolve().parent
OVERLAY_SOURCES = {"benchmark/opencode_bench_v2_web_tg1.json": HERE / "opencode_bench_v2_web_tg1.json",
                   "benchmark/opencode_bench_v2_web.json": HERE / "opencode_bench_v2_web.json"}
OVERLAY_SHA256 = {"benchmark/opencode_bench_v2_web_tg1.json":
                  "cc76c89f0420469b0ecc63b9c9adb0882bdfa36871aa541777565fbc477a210b",
                  "benchmark/opencode_bench_v2_web.json":
                  "5673d726c794b475395bb1bf6ceec670fc4c72118f268e22931d82a6fbe57e5c"}
MANIFEST_NAME = "BUNDLE_MANIFEST.json"
# the only files the harness adds to an extracted bundle (copies of the stdlib-only harness modules)
HARNESS_FILES = ("benchmark/bench/tests/p371_driver_run.py", "benchmark/bench/tests/p371_scenario.py",
                 "benchmark/bench/tests/p371_normalize.py", "benchmark/bench/tests/p371_hermetic_scan.py")


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
    overlaid = {}
    for rel, src in sorted(OVERLAY_SOURCES.items()):
        # P476: the tg1 carrier is registry-derived INPUT DATA the scenarios read; the goldens describe the baseline code
        # run against the post-P476 carrier, taken from the committed pin (asserted), never from the live tree.
        data = src.read_bytes()
        got = hashlib.sha256(data).hexdigest()
        if got != OVERLAY_SHA256[rel]:
            raise BundleError("pinned overlay %s has sha256 %s, expected %s" % (src.name, got, OVERLAY_SHA256[rel]))
        (dest / rel).write_bytes(data)
        overlaid[rel] = got
    files = {}
    for path in sorted(p for p in dest.rglob("*") if p.is_file() and not p.is_symlink()):
        files[path.relative_to(dest).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if "benchmark/bench/tg1_runner.py" not in files:
        raise BundleError("archive lacks benchmark/bench/tg1_runner.py")
    manifest = {"commit": full, "excluded": list(EXCLUDES), "overlaid_files": overlaid, "files": files}
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
