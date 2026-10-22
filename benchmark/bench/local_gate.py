"""P434 local pre-push gate (`docs/specs/p434-local-gate.md` v3.1) — GitHub Actions minutes are exhausted; nothing remote checks a
push, so every push of the stack, `../mlx-vlm` or `../mlx-serve` needs a PASS receipt from this gate for the exact commit.

  .venv-bench/bin/python -m bench.local_gate run --repo stack|mlx-vlm|mlx-serve [--sha <sha>]   # in a test window
  .venv-bench/bin/python -m bench.local_gate install-hooks                                    # bootstrap
  (pre-push shim) … -m bench.local_gate check --repo-dir <top> <remote> <url>  < git's pre-push lines

`run` works in a disposable local CLONE at the exact sha (never the live tree, never a linked worktree), refuses while the box
is busy (any live `bench.p426_wave1` sequencer, a `chain_ops.BUSY` process, a :8000 listener), re-checks before every step,
and writes `$STACK_WORKDIR/gate/<repo>-<sha>-<policy12>[-n].json` (exclusive create; a FAIL is kept). `check` fetches
(`--prune`) the remote, requires a PASS receipt under the CURRENT policy digest for every pushed sha, scans every introduced
commit (added lines: PII + naming; message: naming), and for the stack requires PASS receipts for both gitlinks and their
reachability from the fork's `origin/main`. Threat model: accidental pushes only (§1).
"""

import argparse
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ZERO = "0" * 40
CANONICAL = {"stack": "ivan-avramov/mlx_local_stack", "mlx-vlm": "ivan-avramov/mlx-vlm", "mlx-serve": "ivan-avramov/mlx-serve"}
UPSTREAM_VLM = "https://github.com/Blaizzy/mlx-vlm.git"
AUDITS = ("check_upstream_parity.py", "check_upstream_symbols.py", "check_upstream_deletions.py", "check_fork_markers.py",
          "check_dead_helpers.py", "check_body_divergence.py", "check_upstream_registries.py", "check_call_arguments.py")
GITLINKS = {"src/mlx-vlm": "mlx-vlm", "src/mlx-serve": "mlx-serve"}
EVIDENCE_REF = "refs/heads/evidence"  # P447
SEMVER_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")  # P448: stack releases
FORK_EXTRAS = ("pytest-subtests", "pytest-asyncio", "cryptography>=43.0.0")


class GateError(RuntimeError):
    pass


# ------------------------------------------------------------------ pure helpers
def identity(url):
    m = re.search(r"github\.com[:/]+([\w.-]+/[\w.-]+?)(?:\.git)?/?$", url or "")
    if not m:
        return None
    return next((repo for repo, path in CANONICAL.items() if path == m.group(1)), None)


def parity_ref(workflow_text):
    m = re.search(r"^\s*UPSTREAM_SYNC_REF:\s*([\w./-]+)\s*$", workflow_text, re.MULTILINE)
    if not m:
        raise GateError("upstream-parity.yml: no UPSTREAM_SYNC_REF")
    return m.group(1)


def audit_argvs(py, ref):
    return [[py, f"dev/{name}", "--upstream-ref", ref, *(["--strict"] if name == "check_upstream_deletions.py" else [])]
            for name in AUDITS]


def policy_digest(repo, gate_source, baseline, parity):
    doc = json.dumps(dict(repo=repo, canonical=CANONICAL[repo], gate=hashlib.sha256(gate_source).hexdigest(),
                          baseline=baseline, parity=parity), sort_keys=True)
    return hashlib.sha256(doc.encode()).hexdigest()


def busy_problems(ps_text, listeners, my_pid):
    from bench.chain_ops import BUSY

    out = []
    for line in ps_text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2 or not parts[0].isdigit() or int(parts[0]) == my_pid:
            continue
        if "bench.p426_wave1" in parts[1] or any(b in parts[1] for b in BUSY):
            out.append(line.strip()[:200])
    if listeners:
        out.append(f"{listeners} listener(s) on :8000")
    return out


def imports_inside(output, scratch):
    files = output.split()
    return len(files) == 2 and all(str(Path(f).resolve()).startswith(str(Path(scratch).resolve()) + os.sep) for f in files)


def skipped_from_junit(path):
    if not Path(path).exists():
        return None
    root = ET.parse(path).getroot()
    return sorted(f"{tc.get('classname')}::{tc.get('name')}" for tc in root.iter("testcase") if tc.find("skipped") is not None)


# ------------------------------------------------------------------ steps
@dataclasses.dataclass
class Step:
    name: str
    argv: list
    cwd: Path
    env: dict = dataclasses.field(default_factory=dict)
    check: str = None  # "imports" | "artifacts"


def _workdir():
    wd = os.environ.get("STACK_WORKDIR")
    if not wd:
        raise GateError("STACK_WORKDIR is not set (source the machine config)")
    return wd


def steps_for(repo, scratch, parity):
    s = Path(scratch)
    junit = f"--junitxml={s / '.gate-junit.xml'}"
    if repo == "stack":
        py = str(s / ".venv-bench" / "bin" / "python")
        return [
            Step("clone", [], s),
            Step("submodules", [], s),
            Step("venv", ["uv", "venv", "--python", "3.12", "--python-preference", "only-managed", str(s / ".venv-bench")], s),
            Step("venv-sync", ["uv", "pip", "sync", "--python", py, "benchmark/requirements-bench.lock"], s),
            Step("imports", [py, "-c", "import mlx_vlm, mlx_serve; print(mlx_vlm.__file__, mlx_serve.__file__)"], s,
                 check="imports"),
            Step("pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", junit, "bench/tests/"], s / "benchmark",
                 env=dict(STACK_WORKDIR=_workdir_or_placeholder(), NLTK_DATA=os.environ.get("NLTK_DATA", ""))),
        ]
    if repo == "mlx-vlm":
        py = str(s / ".venv" / "bin" / "python")
        return [
            Step("clone", [], s),
            Step("upstream", ["git", "fetch", "--quiet", "--no-tags", "upstream", "main", "+refs/tags/*:refs/tags/*"], s),
            Step("sync", ["uv", "sync", "--python", "3.12", "--locked", "--extra", "test"], s),
            Step("extras", ["uv", "pip", "install", "--python", py, *FORK_EXTRAS], s),
            Step("pre-commit", ["uvx", "pre-commit", "run", "--all-files"], s),
            *[Step(f"audit:{i}", argv, s) for i, argv in enumerate(audit_argvs(py, parity))],
            Step("pytest", [py, "-m", "pytest", "-q", junit, "mlx_vlm/tests"], s),
        ]
    if repo == "mlx-serve":
        return [
            Step("clone", [], s),
            Step("sync", ["uv", "sync", "--python", "3.12", "--locked", "--extra", "dev", "--extra", "all"], s),
            Step("ruff-check", ["uv", "run", "--no-sync", "ruff", "check", "src/"], s),
            Step("ruff-format", ["uv", "run", "--no-sync", "ruff", "format", "--check", "src/", "tests/"], s),
            Step("pytest", ["uv", "run", "--no-sync", "pytest", "-q", junit, "tests/"], s),
            Step("build", ["uv", "build", "--out-dir", str(s / ".gate-dist")], s, check="artifacts"),
        ]
    raise GateError(f"unknown repo {repo!r}")


def _workdir_or_placeholder():
    return os.environ.get("STACK_WORKDIR", "")  # validated by `run` / `main` (P445: the suite keeps it set)


# ------------------------------------------------------------------ effects
def _git(cwd, *a, check=True):
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise GateError(f"git {' '.join(a)} in {cwd}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def clone_scratch(live, sha, dest):
    dest = Path(dest)
    if dest.exists():
        raise GateError(f"{dest} exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(live), str(dest)], check=True,
                   capture_output=True)
    _git(dest, "-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", sha)
    if _git(dest, "rev-parse", "HEAD") != sha:
        raise GateError(f"scratch HEAD != {sha}")
    return dest


def _submodules(scratch, live):
    """The exact gitlinks, cloned from the local sibling forks (refuse when a gitlink is absent locally)."""
    for path, repo in GITLINKS.items():
        sha = _git(scratch, "ls-tree", "HEAD", path).split()[2]
        sibling = Path(live).parent / repo
        if _git(sibling, "cat-file", "-t", sha, check=False) != "commit":
            raise GateError(f"{path} gitlink {sha} is not in {sibling}")
        target = Path(scratch) / path
        if target.exists():
            shutil.rmtree(target)
        clone_scratch(sibling, sha, target)


def _real_runner(argv, cwd, env):
    r = subprocess.run(argv, cwd=cwd, env={**os.environ, **env}, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return r.returncode, (r.stdout + r.stderr)[-4000:]


def _real_dirty(scratch, after_step):
    return _git(scratch, "status", "--porcelain", "--untracked-files=no", check=False) != ""


def _real_busy():
    ps = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    listeners = subprocess.run(["lsof", "-nP", "-t", "-iTCP:8000", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
    return busy_problems(ps, len(listeners.split()), my_pid=os.getpid())


def _artifacts(dist):
    d = Path(dist)
    return d.is_dir() and any(d.glob("*.whl")) and any(d.glob("*.tar.gz"))


def _gate_source():
    return Path(__file__).read_bytes()


def _receipt_path(gate_dir, repo, sha, digest):
    gate_dir.mkdir(parents=True, exist_ok=True)
    base = gate_dir / f"{repo}-{sha}-{digest[:12]}"
    path, n = Path(f"{base}.json"), 1
    while True:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            return path, fd
        except FileExistsError:
            path, n = Path(f"{base}-{n}.json"), n + 1


def current_parity(repo, live, sha):
    if repo != "mlx-vlm":
        return None
    return parity_ref(_git(live, "show", f"{sha}:.github/workflows/upstream-parity.yml"))


def digest_for(repo, sha, live, baselines):
    base = (Path(baselines) / f"{repo}.skips.txt")
    return policy_digest(repo, _gate_source(), base.read_text() if base.exists() else "<none>", current_parity(repo, live, sha))


def run(repo, sha, *, live, gate_dir, baselines, runner=_real_runner, busy=_real_busy, dirty=_real_dirty, artifacts=_artifacts):
    live, gate_dir = Path(live), Path(gate_dir)
    if busy():
        raise GateError("box busy: " + "; ".join(busy())[:400])
    if identity(_git(live, "remote", "get-url", "origin")) != repo:
        raise GateError(f"{live} origin is not the canonical {repo}")
    sha = _git(live, "rev-parse", f"{sha}^{{commit}}")
    parity = current_parity(repo, live, sha)
    baseline_file = Path(baselines) / f"{repo}.skips.txt"
    baseline = baseline_file.read_text() if baseline_file.exists() else None
    digest = policy_digest(repo, _gate_source(), baseline if baseline is not None else "<none>", parity)
    scratch = gate_dir / "scratch" / f"{repo}-{sha[:12]}-{time.time_ns()}"
    receipt = dict(repo=repo, sha=sha, policy_digest=digest, parity_ref=parity, python="3.12", steps=[], problems=[],
                   started=time.strftime("%Y-%m-%d %H:%M:%S"),
                   not_covered="python 3.10 (fork CI)" if repo == "mlx-vlm" else
                   ("python 3.11 / 3.13 (CI matrix)" if repo == "mlx-serve" else None))
    try:
        for step in steps_for(repo, scratch, parity):
            if busy():
                receipt["problems"].append(f"box became busy before {step.name}")
                break
            t0 = time.monotonic()
            if step.name == "clone":
                clone_scratch(live, sha, scratch)
                rc, out = 0, ""
            elif step.name == "submodules":
                _submodules(scratch, live)
                rc, out = 0, ""
            elif step.name == "upstream":
                _git(scratch, "remote", "add", "upstream", UPSTREAM_VLM)
                _git(scratch, "remote", "set-url", "--push", "upstream", "no_push")
                rc, out = runner(step.argv, step.cwd, step.env)
            else:
                rc, out = runner(step.argv, step.cwd, step.env)
            receipt["steps"].append(dict(name=step.name, argv=step.argv, rc=rc, seconds=round(time.monotonic() - t0, 1),
                                         summary=out[-600:]))
            if rc != 0:
                receipt["problems"].append(f"{step.name}: rc {rc}")
                break
            if step.check == "imports" and not imports_inside(out, scratch):
                receipt["problems"].append(f"imports resolve outside the scratch: {out.strip()[:300]}")
                break
            if step.check == "artifacts" and not artifacts(scratch / ".gate-dist"):
                receipt["problems"].append("build: wheel / sdist missing")
                break
            if step.name not in ("clone", "submodules") and dirty(scratch, step.name):
                receipt["problems"].append(f"{step.name} left tracked files modified")
                break
        else:
            skipped = skipped_from_junit(scratch / ".gate-junit.xml") or []
            receipt["skipped_tests"] = skipped
            want = sorted(l for l in (baseline or "").splitlines() if l.strip())
            if baseline is None:
                receipt["problems"].append(f"no skip baseline {baseline_file} — review the skipped tests, then commit it")
            elif skipped != want:
                receipt["problems"].append(f"skip list != baseline: +{sorted(set(skipped) - set(want))} "
                                           f"-{sorted(set(want) - set(skipped))}")
    except (GateError, subprocess.CalledProcessError, OSError) as exc:
        receipt["problems"].append(f"{type(exc).__name__}: {exc}"[:600])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    receipt["verdict"] = "PASS" if not receipt["problems"] and len(receipt["steps"]) == len(steps_for(repo, scratch, parity)) \
        else "FAIL"
    receipt["ended"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path, fd = _receipt_path(gate_dir, repo, sha, digest)
    os.write(fd, (json.dumps(receipt, indent=1) + "\n").encode())
    os.close(fd)
    return path


# ------------------------------------------------------------------ check (pre-push)
def has_pass(gate_dir, repo, sha, digest):
    for p in Path(gate_dir).glob(f"{repo}-{sha}-{digest[:12]}*.json"):
        try:
            doc = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("verdict") == "PASS" and doc.get("sha") == sha and doc.get("policy_digest") == digest:
            return True
    return False


def introduced(repo_dir, remote, sha):
    return _git(repo_dir, "rev-list", sha, "--not", f"--remotes={remote}").split()


def _scan(repo_dir, commits, naming=True):
    from bench import modelnames, piicheck

    out = []
    for c in commits:
        diff = _git(repo_dir, "show", "--format=", "--unified=0", "--root", c)
        out += [f"{c[:8]} PII: {v}" for v in piicheck.diff_violations(diff)]
        if naming:
            msg = _git(repo_dir, "show", "-s", "--format=%B", c)
            out += [f"{c[:8]} naming: {v}" for v in modelnames.diff_violations(diff)]
            out += [f"{c[:8]} message: {v}" for v in modelnames.message_violations(msg)]
    return out


def gitlink_problems(links, forks, *, gate_dir, digest_for):
    out = []
    for path, sha in links.items():
        repo, fork = GITLINKS[path], Path(forks[path])
        if not has_pass(gate_dir, repo, sha, digest_for(repo, sha)):
            out.append(f"{path} {sha[:8]}: no PASS receipt (run: bench.local_gate run --repo {repo} --sha {sha})")
        if subprocess.run(["git", "-C", str(fork), "fetch", "--quiet", "--prune", "origin"], capture_output=True).returncode:
            out.append(f"{path}: fetch of {fork} origin failed")
            continue
        if subprocess.run(["git", "-C", str(fork), "merge-base", "--is-ancestor", sha, "origin/main"],
                          capture_output=True).returncode:
            out.append(f"{path} {sha[:8]}: not reachable from {repo} origin/main (push the fork first)")
    return out


def _gitlinks_at(repo_dir, sha):
    links, out = {}, []
    for p in GITLINKS:
        row = _git(repo_dir, "ls-tree", sha, p, check=False).split()
        if len(row) < 3 or row[1] != "commit":
            out.append(f"gitlink {p}: absent at {sha[:8]}")
        else:
            links[p] = row[2]
    return links, out


def check_lines(repo, repo_dir, remote, lines, *, gate_dir, digest_for, forks=None):
    """P448: a branch push needs only the per-commit scans; a stack TAG must be SemVer `vX.Y.Z` and carries the release rule
    (PASS receipt for the tagged commit under the current policy + both gitlinks' receipts and reachability); P447 evidence."""
    if subprocess.run(["git", "-C", str(repo_dir), "fetch", "--quiet", "--prune", remote], capture_output=True).returncode:
        return [f"git fetch --prune {remote} failed: cannot tell what is new (refused)"]
    out = []
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, _remote_sha = parts
        if local_sha == ZERO:
            continue
        sha = _git(repo_dir, "rev-parse", f"{local_sha}^{{commit}}")
        if repo == "stack" and remote_ref == EVIDENCE_REF:  # P447: the orphan data branch — no code to gate, PII still scanned
            if subprocess.run(["git", "-C", str(repo_dir), "merge-base", sha, f"{remote}/main"], capture_output=True).returncode == 0:
                out.append(f"{sha[:8]} pushed to {EVIDENCE_REF} shares history with {remote}/main: not an orphan data commit")
                continue
            out += _scan(repo_dir, introduced(repo_dir, remote, sha), naming=False)
            continue
        out += _scan(repo_dir, introduced(repo_dir, remote, sha))
        if repo == "stack" and remote_ref.startswith("refs/tags/"):
            name = remote_ref[len("refs/tags/"):]
            if not SEMVER_TAG.match(name):
                out.append(f"tag {name}: a stack tag must be SemVer vMAJOR.MINOR.PATCH (refused)")
                continue
            if not has_pass(gate_dir, repo, sha, digest_for(repo, sha)):
                out.append(f"tag {name} {sha[:8]}: no PASS release receipt under the current gate policy "
                           f"(run: bench.local_gate release --version {name[1:]})")
            links, missing = _gitlinks_at(repo_dir, sha)
            out += missing
            if links:
                out += gitlink_problems(links, forks or {p: Path(repo_dir).parent / r for p, r in GITLINKS.items()},
                                        gate_dir=gate_dir, digest_for=digest_for)
    return out


def _semver(text):
    m = SEMVER_TAG.match(text if text.startswith("v") else "v" + text)
    return tuple(int(x) for x in m.groups()) if m else None


def release(version, pins, *, existing_tags, gate, has_pass, reachable, busy, make_tag):
    """P448: qualify the stack commit + its exact fork pins, then tag `v<version>` (the push stays the operator's)."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version or ""):
        raise GateError(f"version {version!r} is not MAJOR.MINOR.PATCH")
    newest = max((v for v in (_semver(t) for t in existing_tags) if v), default=None)
    if newest and _semver(version) <= newest:
        raise GateError(f"version {version} is not above the newest tag v{'.'.join(map(str, newest))}")
    if busy():
        raise GateError("box busy: " + "; ".join(busy())[:400])
    receipts = {}
    for repo in ("stack", "mlx-vlm", "mlx-serve"):
        sha = pins[repo]
        if has_pass(repo, sha):
            receipts[repo] = "existing PASS receipt"
            continue
        path, verdict = gate(repo, sha)
        if verdict != "PASS":
            raise GateError(f"{repo} {sha[:8]} gate {verdict} ({path}) — no tag")
        receipts[repo] = str(path)
    for repo in ("mlx-vlm", "mlx-serve"):
        if not reachable(repo, pins[repo]):
            raise GateError(f"{repo} {pins[repo][:8]} is not on its origin/main (push the fork first) — no tag")
    tag = f"v{version}"
    msg = "\n".join([f"release {tag}", ""] + [f"{r}: {pins[r]}  receipt: {receipts[r]}" for r in ("stack", "mlx-vlm", "mlx-serve")])
    make_tag(tag, msg)
    return dict(verdict="PASS", tag=tag, pins=pins, receipts=receipts)


# ------------------------------------------------------------------ shims
PRE_PUSH = """#!/usr/bin/env bash
# P434 machine-local pre-push shim (written by `bench.local_gate install-hooks`; never branch-controlled).
set -uo pipefail
STACK_REPO="${{STACK_REPO:-{stack}}}"
GATE_MIN_COMMIT={min_commit}
TOP="$(git rev-parse --show-toplevel)" || exit 1
# git exports GIT_DIR & co. to hooks (the PUSHING repo); every later git call names its repo explicitly
unset $(git rev-parse --local-env-vars)
if ! git -C "$STACK_REPO" merge-base --is-ancestor "$GATE_MIN_COMMIT" HEAD 2>/dev/null; then
  echo "[pre-push] REFUSED: the stack checkout does not contain GATE_MIN_COMMIT $GATE_MIN_COMMIT (an older gate)" >&2
  exit 1
fi
PYTHONPATH="$STACK_REPO/benchmark" "$STACK_REPO/.venv-bench/bin/python" -m bench.local_gate check --repo-dir "$TOP" "$@"
"""
DELEGATE = """#!/usr/bin/env bash
# P434 shim: run the repository's own `githooks/{name}` when it has one (the stack's naming / PII hooks), else pass.
TOP="$(git rev-parse --show-toplevel)" || exit 1
[ -x "$TOP/githooks/{name}" ] && exec "$TOP/githooks/{name}" "$@"
exit 0
"""


def write_shims(hooks_dir, *, stack_repo, min_commit):
    d = Path(hooks_dir)
    d.mkdir(parents=True, exist_ok=True)
    for name, text in (("pre-push", PRE_PUSH.format(stack=stack_repo, min_commit=min_commit)),
                       ("pre-commit", DELEGATE.format(name="pre-commit")), ("commit-msg", DELEGATE.format(name="commit-msg"))):
        p = d / name
        p.write_text(text)
        p.chmod(0o755)
    return d


def install_hooks(stack_repo):
    stack_repo = Path(stack_repo).resolve()
    hooks = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mlx_local_stack" / "hooks"
    write_shims(hooks, stack_repo=stack_repo, min_commit=_git(stack_repo, "rev-parse", "HEAD"))
    for repo_dir, repo in ((stack_repo, "stack"), (stack_repo.parent / "mlx-vlm", "mlx-vlm"),
                           (stack_repo.parent / "mlx-serve", "mlx-serve")):
        if identity(_git(repo_dir, "remote", "get-url", "origin")) != repo:
            raise GateError(f"{repo_dir}: origin is not the canonical {repo}")
        _git(repo_dir, "config", "core.hooksPath", str(hooks))
    return hooks


# ------------------------------------------------------------------ CLI
def _baselines():
    return Path(__file__).resolve().parents[1] / "gate"


def _stack_repo():
    return Path(__file__).resolve().parents[2]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--repo", required=True, choices=sorted(CANONICAL))
    r.add_argument("--sha", default="HEAD")
    c = sub.add_parser("check")
    c.add_argument("--repo-dir", required=True)
    c.add_argument("remote")
    c.add_argument("url", nargs="?")
    sub.add_parser("install-hooks")
    rel = sub.add_parser("release")
    rel.add_argument("--version", required=True, help="MAJOR.MINOR.PATCH (the tag is v<version>, on the stack HEAD)")
    args = ap.parse_args(argv)
    stack = _stack_repo()
    try:
        if args.cmd == "install-hooks":
            print(install_hooks(stack))
            return 0
        if args.cmd == "check" and identity(_git(args.repo_dir, "remote", "get-url", "origin", check=False)) is None:
            print(f"[pre-push] REFUSED: unknown origin for {args.repo_dir}", file=sys.stderr)
            return 1
        gate_dir = Path(_workdir()) / "gate"
        live = {"stack": stack, "mlx-vlm": stack.parent / "mlx-vlm", "mlx-serve": stack.parent / "mlx-serve"}
        if args.cmd == "release":
            if _git(stack, "status", "--porcelain", "--untracked-files=no"):
                raise GateError("the stack checkout has uncommitted tracked changes")
            head = _git(stack, "rev-parse", "HEAD")
            pins = dict(stack=head, **{repo: _git(stack, "ls-tree", head, p).split()[2] for p, repo in GITLINKS.items()})

            def gate(repo, sha):
                path = run(repo, sha, live=live[repo], gate_dir=gate_dir, baselines=_baselines())
                return path, json.loads(Path(path).read_text())["verdict"]

            def reachable(repo, sha):
                fork = live[repo]
                return (subprocess.run(["git", "-C", str(fork), "fetch", "--quiet", "--prune", "origin"], capture_output=True)
                        .returncode == 0 and subprocess.run(["git", "-C", str(fork), "merge-base", "--is-ancestor", sha,
                                                             "origin/main"], capture_output=True).returncode == 0)

            out = release(args.version, pins, existing_tags=_git(stack, "tag", "-l", "v*").split(), gate=gate,
                          has_pass=lambda repo, sha: has_pass(gate_dir, repo, sha, digest_for(repo, sha, live[repo], _baselines())),
                          reachable=reachable, busy=_real_busy,
                          make_tag=lambda name, msg: _git(stack, "tag", "-a", name, "-m", msg, head))
            print(json.dumps(out, indent=1))
            return 0
        if args.cmd == "run":
            path = run(args.repo, args.sha, live=live[args.repo], gate_dir=gate_dir, baselines=_baselines())
            doc = json.loads(path.read_text())
            print(json.dumps({k: doc.get(k) for k in ("repo", "sha", "verdict", "problems")}, indent=1), f"\n{path}")
            return 0 if doc["verdict"] == "PASS" else 1
        repo = identity(_git(args.repo_dir, "remote", "get-url", "origin"))
        problems = check_lines(repo, args.repo_dir, args.remote, sys.stdin.read().splitlines(), gate_dir=gate_dir,
                               digest_for=lambda rp, sha: digest_for(rp, sha, live[rp], _baselines()))
    except GateError as exc:
        print(f"[local_gate] REFUSED: {exc}", file=sys.stderr)
        return 1
    for p in problems:
        print(f"[pre-push] {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
