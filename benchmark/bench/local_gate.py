"""P434 local pre-push gate (`docs/specs/p434-local-gate.md` v3.1) — GitHub Actions minutes are exhausted; nothing remote checks a
push, so every push of the stack, `../mlx-vlm` or `../mlx-serve` needs a PASS receipt from this gate for the exact commit.

  .venv-bench/bin/python -m bench.local_gate run --repo stack|mlx-vlm|mlx-serve [--sha <sha>]   # in a test window
  .venv-bench/bin/python -m bench.local_gate install-hooks                                    # bootstrap
  (pre-push shim) … -m bench.local_gate check --repo-dir <top> <remote> <url>  < git's pre-push lines

`run` works in a disposable local CLONE at the exact sha (never the live tree, never a linked worktree), refuses while the box
is busy (any live `bench.p426_wave1` sequencer, a `chain_ops.BUSY` process, a :8000 listener), re-checks before every step,
holds `$STACK_WORKDIR/gate/RUNNING` while `run` / `release` work and refuses while `p426/SEQUENCER.lock` or `p426/LEG.lock` is held
(B2 spec 9, `bench.p426_locks`),
and writes `$STACK_WORKDIR/gate/<repo>-<sha>-<policy12>[-n].json` (exclusive create; a FAIL is kept,
with the failing step's full output `<receipt stem>.<step>.log` and the pytest JUnit `<receipt stem>.junit.xml` beside it — M75). `check` fetches
(`--prune`) the remote, requires a PASS receipt under the CURRENT policy digest for every pushed sha, scans every introduced
commit (added lines: PII + naming; message: naming), and for the stack requires PASS receipts for both gitlinks and their
reachability from the fork's `origin/main`. Threat model: accidental pushes only (§1).

M80 (`docs/specs/m80-gate-sibling-mlx-serve.md`): an mlx-vlm run's scratch is a per-run directory holding the fork clone
(`<run>/mlx-vlm`) and a sibling `<run>/mlx-serve` cloned from `../mlx-serve` at a pinned sha (`--mlx-serve-sha`, else the stack
HEAD's `src/mlx-serve` gitlink) with its own venv; the receipt records `paired`, and every test marked `requires_mlx_serve`
must have passed.
"""

import argparse
import ast
import collections
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
MLX_VLM_ORIGIN_URLS = (
    f"git@github.com:{CANONICAL['mlx-vlm']}",
    f"git@github.com:{CANONICAL['mlx-vlm']}.git",
    f"https://github.com/{CANONICAL['mlx-vlm']}",
    f"https://github.com/{CANONICAL['mlx-vlm']}.git",
)
# P8: approved scanner finding fingerprints for the upstream sync through fd6404fb3261102600541127d59103dac65c2756.
MLX_VLM_UPSTREAM_SCAN_EXCEPTIONS = {
    "08b7fd8765148a6a541839fec3a7bddce23f8587": "a799baffeff4d9a8fb30f7c3d0d797d3dc2ed040f95d8eed747d4c0261ad39a3",
    "09b95b17281a40611d23acb62b9a66a91d879d11": "635f16604040e94df262d33f8914f1a711abf8c094c8b30c6a9fad555d75285a",
    "1009b626859e09844446be1b8dc434dfb83719ff": "1da4c448f52c601474e514d8220b62e27075d33c5afa9107e5fafca495647886",
    "168a299d41755b8a3bf7a94610702e9bb4c01c09": "323c304e33ddbad85ab6663aef07576009e3522bb9ae3b4fc9dae53b44767d9e",
    "1c84b33d3ea9a0a015932fb13d55d450e3a256f2": "5ecf231915e26d306e96f1a6cf64f600015a8fafaa591826c3f5ba44fd3ba8b2",
    "24ec162ad92b70998e2f4b3b30bc229267944148": "0273389a3f14cf93e2b0e1a0e00bcfa44b759577a8277f022535452504c2c732",
    "25ead5d2c72f509c03ff570cae2041cbf54fa408": "21aca868b0bcde776bc58441f24495dd63c24e02e58d487e89a123d156135370",
    "2d8095467a1a72f7bc3d145abfd9e3a1466d988c": "e3bfa7b9d1ac48f327b054c095835f17cf16afe3de96488b4102e20ea19313d7",
    "2e52f924a204608c6177b19e5897766a6a0a424c": "a83707512f6190460485ea3339f35625d89c9ec60490a8b027f30936dd2d3f62",
    "3070dcc31948f48f9d8639b606af7bc019494fac": "dd5523332af1d8e05c34027e3866db2ed37236aa3cb270dbd258177ff1371558",
    "3ba1383d67006c3da9bd8e6590ab5777ff3e1fce": "bb84d19bbde1ca10e2e69510dafeab97d51a28fbc6a3d0e33a7ccb0a63e304b4",
    "3d461369b70c7fda4977154562fe247bdea057be": "689e865bc35d630e6a6649e068c55e2822d305ae3148ab0461e4cc6558ddb0b0",
    "3d58bac96aed22e2046ae71d03b7e43ce0578418": "4b069fc7ce456e8c8f4b7e6b55509c89a0b34f7fd03d6855056c8f13b79964d8",
    "4a991d7f8aaad61e5b7834eb86206f957074b660": "53388dff6c0d5afe534f6876840b7e79c6e3020b78570bea9a8b6ce68bfc57a2",
    "4feb2d9e30b2fef62b9c6630111ff2e590806724": "4cfe5af53c4ab7094e9cf1daf405b6fcea747d740d9bbbb0c326aa10f3ff4cef",
    "5061bd7f3848f720cb2ba8d0bc1a1a181d733359": "f16f1560add64cc19fd37ac0df1c65a840289146c1dd6de9f5f228072788d1f2",
    "5d65a184762bf1fe8decc2b9b6a4b9a100cffa0b": "027114a8ca7bb8d3b6ed1f44fd8efa5e57c34e830f509223774fdc37d1281b09",
    "626e3e7dae8812dab939c4837e192bd0be9f549f": "0e8bda7e25cc34b813d88bcf6f6db1a93f122b63ba585539410c1d86293cb7ae",
    "6b64f19713faeea64cba82d2878585074e5f6014": "736dc90f1b04218fb6e85a84b61c764f2be631aa4de6b8d8d3a3dc7dca834f82",
    "6dc15626a1c82e88df2198ce397a6aef3349c579": "b247f0bb2af9bdef130beb33fe6a06c815ffabc3673b2a8cd9d56a39fdcb89d9",
    "7b197478718fcb9d3b164523a4134b062b1ac62c": "20968bb0a4e5c42d05c654ba7d8cb5e2ae7676a0b5c9812e025943e1f9763d4c",
    "820b067c4276e39eeb1ce819510ef42d3c8f47e6": "168e97c00d2ad7a0df0e92db11cf1f443bcf6d96e971ebd824fddba9f39f4531",
    "89b0aebf083d88d1ada0d8fca79bc4a7abd2ed10": "7f3db265aceb249ccfb8f99966bc31f8ba2243b95241fb34504d22cab83d0913",
    "8b7c99094fa14c2b5a28fbf9f8d1fecb62ddf605": "8a76b516c01988ad5e28274fb98ab06ec892641a831bcf503e1b01e936a7d169",
    "9543e2f2ab51276d01da977aa93e8aa0503370b5": "a15a7d7d724725b111d88543ed69516c7c3e4aeab99634b4713b5f9e60372909",
    "9be4b98f6bbdbd5081901868e676dd766710a92e": "8205cfed38b99636fbcd78fc992d368f1cb93c50c2d98da0bd142c63326516bf",
    "9f76a9bfbb7093cfc54f3de55a8976d3756fcc3d": "5e25e68008824666c23d659e3e82e7a2cf557db3ac69784707a6dab1c93331ba",
    "a704c3b70816df4390232e6abae4f15311e118bc": "de8d613f70ba9127385545c6501175a38b4d6d51e7bf8c369885555b08302051",
    "a78e7ef60b431492209569d1e3452c62f20b6696": "173e26f6476e2816c81ecf5e5f10fb48206e01181676639d09f8cbb2530b3cf5",
    "b167017e17ae901538d498989db74a40912d6bd0": "4f6b2b6bac992f1b53128bba645a85ecb64ff28a9ca48a16f6e92d7a669a5383",
    "ba9259b9b0a19855c6f9cfb71c2bf12e8a332ed0": "c3f670facedd42b6e5db81e24f7aacacedd9049a865493dc2fee14ce583652f2",
    "bdc6bd733acfbb7a0916cfd38e7ed68536056b19": "0b03c430ef8de7f144f572e127a28c4a6fdafddddbfa15bda26faec9401d0784",
    "c0980db2182d57e7e76d05cbcba8d04a194e6b17": "1ee0ccaf74464d8bb7cb2b0327a18871a4fa3e4add44f2f322546db97b015647",
    "d3a16c344b9cb9311060fb189019a9582b202fdd": "d8527729c2f56cabf6ce630ed50f4e3be95bf9eefd692625be35eb5df54d3324",
    "dcdb3e81debe46f99e143abe37d6a2d977c89c3c": "73a6430cdb86590ca4b0970ac2d941fda3baa14397b1d7fefcbf1670b7b1b4fe",
    "e5fea63fe65a31d740fbf72911d468ce3ac9d832": "0236b05b4ae8d60963312ed619b229683adb8e240947020fad54e72a848dcdc8",
    "fb8a76b7e287d314bcf9621b2d0337c5ea7cb3b2": "9af84f3f1d1e275bb759169894a31aa3ba4723408698141bcf48fe6576ca5b9c",
}
AUDITS = ("check_upstream_parity.py", "check_upstream_symbols.py", "check_upstream_deletions.py", "check_fork_markers.py",
          "check_dead_helpers.py", "check_body_divergence.py", "check_upstream_registries.py", "check_call_arguments.py")
GITLINKS = {"src/mlx-vlm": "mlx-vlm", "src/mlx-serve": "mlx-serve"}
EVIDENCE_REF = "refs/heads/evidence"  # P447
SEMVER_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")  # P448: stack releases
FORK_EXTRAS = ("pytest-subtests", "pytest-asyncio", "cryptography>=43.0.0", "psutil")  # psutil: P452 topology tests
SIBLING = "mlx-serve"                 # M80: the mlx-vlm gate's sibling clone, `<run>/mlx-serve` beside `<run>/mlx-vlm`
SIBLING_MARKER = "requires_mlx_serve"  # M80: a test carrying it must pass in the mlx-vlm gate
PYTEST_NO_ADDOPTS = ("-o", "addopts=")  # M80: the mlx-vlm pytest runs ignore configured addopts ...
PYTEST_ENV_DROP = {"PYTEST_ADDOPTS": None, "PYTEST_PLUGINS": None}  # ... and these (None = removed from the environment)
PUSHED_REF = "refs/remotes/origin/main"       # S25-P10: GitHub's last-pushed `main`, as the source repository records it
PUSHED_BASE_ENV = "GATE_PUSHED_BASE"          # S25-P10: exported to the stack gate's pytest run
GATE_BASE_REF = "refs/gate/pushed-base"       # S25-P10: the pushed base fetched into the scratch clone


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


def sync_ref_text(text):
    """The first non-blank, non-comment line of a fork's `.upstream-sync-ref` (the file its `dev/ci.py` reads)."""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    raise GateError(".upstream-sync-ref: no ref")


def audit_argvs(py, ref, audits=None):
    """`audits`: the fork's own (script, extra args) list at the sha (`audits_at`); None = the S layout's eight."""
    if audits is None:
        audits = [(name, ("--strict",) if name == "check_upstream_deletions.py" else ()) for name in AUDITS]
    return [[py, f"dev/{name}", "--upstream-ref", ref, *extra] for name, extra in audits]


def policy_digest(repo, gate_source, baseline, parity, audits=None):
    doc = dict(repo=repo, canonical=CANONICAL[repo], gate=hashlib.sha256(gate_source).hexdigest(), baseline=baseline,
               parity=parity)
    if audits is not None:
        doc["audits"] = [[name, list(extra)] for name, extra in audits]
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


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


def ran_and_passed_from_junit(path):
    if not Path(path).exists():
        return None
    root = ET.parse(path).getroot()
    clean = {}
    for tc in root.iter("testcase"):
        tid = f"{tc.get('classname')}::{tc.get('name')}"
        clean[tid] = clean.get(tid, True) and all(tc.find(k) is None for k in ("skipped", "failure", "error"))
    return sorted(tid for tid, ok in clean.items() if ok)


def marked_from_junit(path, marker=SIBLING_MARKER):
    """M80: junit ids of testcases carrying a `<property>` whose name or value is `marker`."""
    if not Path(path).exists():
        return []
    root = ET.parse(path).getroot()
    return sorted({f"{tc.get('classname')}::{tc.get('name')}" for tc in root.iter("testcase")
                   if any(marker in (p.get("name"), p.get("value")) for p in tc.iter("property"))})


def nodeid_to_junit(nodeid):
    """`a/b/test_x.py::C::test_y[p]` → `a.b.test_x.C::test_y[p]` (pytest's junit classname::name); None if not a test node id."""
    if "::" not in nodeid:
        return None
    path, *rest = nodeid.split("::")
    if not path.endswith(".py") or not rest:
        return None
    mod = path[:-3].replace("/", ".").replace("\\", ".")
    return f"{'.'.join([mod, *rest[:-1]])}::{rest[-1]}"


def marked_from_listing(output):
    """M80: junit ids from a `pytest --collect-only -q -m <marker>` listing (one node id per line; summary lines ignored).
    GateError when the listing cannot be read as node ids: per-file counts (`-qq`) or a collected count that differs."""
    ids = sorted({j for j in (nodeid_to_junit(line.strip()) for line in output.splitlines()) if j})
    if any(re.fullmatch(r"\S+\.py: \d+", line.strip()) for line in output.splitlines()):
        raise GateError(f"{SIBLING_MARKER} listing holds per-file counts, not test ids (extra -q?)")
    m = re.search(r"^(\d+)(?:/\d+)? tests? collected", output, re.MULTILINE)
    if m and int(m.group(1)) != len(ids):
        raise GateError(f"{SIBLING_MARKER} listing: {m.group(1)} collected but {len(ids)} test ids read")
    return ids


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


def sibling_path(scratch):
    """M80: the sibling mlx-serve clone of an mlx-vlm scratch (`<run>/mlx-vlm` → `<run>/mlx-serve`)."""
    return Path(scratch).parent / SIBLING


def steps_for(repo, scratch, parity, audits=None, pushed_base=None):
    """mlx-vlm (M80): `scratch` is the fork clone `<run>/mlx-vlm`; `sibling` / `sibling-sync` (in `<run>/mlx-serve`) always
    follow `clone`. stack (S25-P10): the pytest step exports `pushed_base` as `GATE_PUSHED_BASE` (None removes it)."""
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
                 env={"STACK_WORKDIR": _workdir_or_placeholder(), "NLTK_DATA": os.environ.get("NLTK_DATA", ""),
                      PUSHED_BASE_ENV: pushed_base, **PYTEST_ENV_DROP}),
        ]
    if repo == "mlx-vlm":
        py = str(s / ".venv" / "bin" / "python")
        sib = sibling_path(s)
        return [
            Step("clone", [], s),
            Step("sibling", [], sib),
            Step("sibling-sync", ["uv", "sync", "--frozen", "--all-extras"], sib),
            Step("upstream", ["git", "fetch", "--quiet", "--no-tags", "upstream", "main", "+refs/tags/*:refs/tags/*"], s),
            Step("sync", ["uv", "sync", "--python", "3.12", "--locked", "--extra", "test"], s),
            Step("extras", ["uv", "pip", "install", "--python", py, *FORK_EXTRAS], s),
            Step("pre-commit", ["uvx", "pre-commit", "run", "--all-files"], s),
            *[Step(f"audit:{i}", argv, s) for i, argv in enumerate(audit_argvs(py, parity, audits))],
            Step("pytest", [py, "-m", "pytest", "-q", *PYTEST_NO_ADDOPTS, junit, "mlx_vlm/tests"], s, env=dict(PYTEST_ENV_DROP)),
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


def _hold_running(wd):
    """B2 spec 9: own `gate/RUNNING` under the arbiter, held while the gate works; `p426/SEQUENCER.lock` / `p426/LEG.lock` held
    (a Wave-2 sequencer or a P426 chain leg is running) is a refusal."""
    from bench import p426_locks

    try:
        return p426_locks.acquire("gate", wd)
    except p426_locks.LockRefused as exc:
        raise GateError(str(exc)) from None


def _workdir_or_placeholder():
    return os.environ.get("STACK_WORKDIR", "")  # validated by `run` / `main` (P445: the suite keeps it set)


# ------------------------------------------------------------------ effects
def _git(cwd, *a, check=True):
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise GateError(f"git {' '.join(a)} in {cwd}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def pushed_base(live):
    """S25-P10: the source repository's `refs/remotes/origin/main` (GitHub's last-pushed `main`); GateError when absent."""
    sha = _git(live, "rev-parse", "--verify", "--quiet", f"{PUSHED_REF}^{{commit}}", check=False)
    if not sha:
        raise GateError(f"no pushed base: {live} has no {PUSHED_REF} (fetch origin first)")
    return sha


def resolve_pushed_base(repo, environ=None):
    """S25-P10: the base of a "this build" diff — `GATE_PUSHED_BASE` (a full sha, exported by the stack gate), else
    `refs/remotes/origin/main` of a checkout whose `origin` is the canonical GitHub stack remote. Never the local `main`, which
    can contain the build. GateError when neither holds or the commit is not in `repo`."""
    environ = os.environ if environ is None else environ
    sha = environ.get(PUSHED_BASE_ENV)
    if sha:
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise GateError(f"{PUSHED_BASE_ENV}={sha!r} is not a full commit sha")
        source = PUSHED_BASE_ENV
    else:
        if identity(_git(repo, "remote", "get-url", "origin", check=False)) != "stack":
            raise GateError(f"no pushed base: {PUSHED_BASE_ENV} is unset and the origin of {repo} is not the canonical stack "
                            f"remote (a gate clone's origin is the local repository; the stack gate exports {PUSHED_BASE_ENV})")
        sha, source = pushed_base(repo), PUSHED_REF
    if _git(repo, "cat-file", "-t", sha, check=False) != "commit":
        raise GateError(f"pushed base {sha} ({source}) is not a commit in {repo}")
    return sha


def _fetch_pushed_base(scratch, live, base):
    """S25-P10: the scratch clone holds the pushed base even when only `refs/remotes/origin/main` reaches it."""
    _git(scratch, "fetch", "--quiet", "--no-tags", str(live), f"+{PUSHED_REF}:{GATE_BASE_REF}")
    if _git(scratch, "rev-parse", f"{GATE_BASE_REF}^{{commit}}") != base:
        raise GateError(f"{PUSHED_REF} of {live} moved during the run (want {base})")


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


def pinned_mlx_serve(live, override=None, stack=None):
    """M80: the mlx-serve sha an mlx-vlm run pairs with — `override` (`--mlx-serve-sha`) if given, else the `src/mlx-serve`
    gitlink of the stack repository's HEAD (`stack`, default `_stack_repo()`); GateError unless it is a commit in
    `<live>.parent / "mlx-serve"`. Returns the full sha."""
    source = Path(live).parent / SIBLING
    if not (source / ".git").exists():
        raise GateError(f"no mlx-serve checkout at {source}: an mlx-vlm run always pairs with ../mlx-serve")
    if override:
        if not re.fullmatch(r"[0-9a-fA-F]{4,40}", override):
            raise GateError(f"--mlx-serve-sha {override!r} is not a hex commit sha")
        sha = override
    else:
        stack = Path(stack) if stack is not None else _stack_repo()
        row = _git(stack, "ls-tree", "HEAD", "src/mlx-serve", check=False).split()
        if len(row) < 3 or row[1] != "commit":
            raise GateError(f"no src/mlx-serve gitlink at the HEAD of {stack} (pass --mlx-serve-sha)")
        sha = row[2]
    if _git(source, "cat-file", "-t", sha, check=False) != "commit":
        raise GateError(f"mlx-serve {sha} is not a commit in {source}")
    return _git(source, "rev-parse", f"{sha}^{{commit}}")


def _real_runner(argv, cwd, env):
    merged = {k: v for k, v in {**os.environ, **env}.items() if v is not None}   # a None value removes the variable (M80)
    r = subprocess.run(argv, cwd=cwd, env=merged, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout + r.stderr   # full: a FAIL keeps it beside the receipt (M75)


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
    """The fork's upstream ref at the sha: `.upstream-sync-ref` when it has one (S′ layout), else the parity workflow (S)."""
    if repo != "mlx-vlm":
        return None
    if _git(live, "cat-file", "-t", f"{sha}:.upstream-sync-ref", check=False) == "blob":
        return sync_ref_text(_git(live, "show", f"{sha}:.upstream-sync-ref"))
    return parity_ref(_git(live, "show", f"{sha}:.github/workflows/upstream-parity.yml"))


def audits_at(live, sha):
    """The fork's gating audits at the sha: the `AUDITS` list of its own `dev/ci.py` (parsed, never executed); a sha without
    one (the S layout) has the fixed eight."""
    if _git(live, "cat-file", "-t", f"{sha}:dev/ci.py", check=False) != "blob":
        return [(name, ("--strict",) if name == "check_upstream_deletions.py" else ()) for name in AUDITS]
    for node in ast.parse(_git(live, "show", f"{sha}:dev/ci.py")).body:
        target = node.target if isinstance(node, ast.AnnAssign) else (node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == "AUDITS":
            try:
                audits = [(name, tuple(extra)) for name, extra in ast.literal_eval(node.value)]
            except (ValueError, TypeError) as exc:
                raise GateError(f"dev/ci.py at {sha[:8]}: AUDITS is not a literal list of (script, args): {exc}") from exc
            if not audits or not all(isinstance(n, str) and all(isinstance(a, str) for a in e) for n, e in audits):
                raise GateError(f"dev/ci.py at {sha[:8]}: AUDITS is empty or malformed")
            return audits
    raise GateError(f"dev/ci.py at {sha[:8]}: no AUDITS list")


def _audits_for(repo, live, sha):
    return audits_at(live, sha) if repo == "mlx-vlm" else None


def digest_for(repo, sha, live, baselines):
    base = (Path(baselines) / f"{repo}.skips.txt")
    return policy_digest(repo, _gate_source(), base.read_text() if base.exists() else "<none>", current_parity(repo, live, sha),
                         _audits_for(repo, live, sha))


def _prefix_paths(entry):
    """Every dotted prefix of the entry's module part as a relative `.py` path, longest first; [] if underivable."""
    if "::" not in entry:
        return []
    parts = entry.split("::", 1)[0].split(".")
    if not all(p and p not in ("..", ".") and "/" not in p and "\\" not in p for p in parts):
        return []
    return [Path(*parts[:i - 1], parts[i - 1] + ".py") for i in range(len(parts), 0, -1)]


def _absent_allowed(entry, *, scratch, live, sha, junit_ids):
    """P627 v1.3: the baseline entry's test file was added on the live side after the histories diverged."""
    if entry in junit_ids:
        return False
    paths = _prefix_paths(entry)
    if not paths or any((Path(scratch) / p).is_file() for p in paths):
        return False  # v1.1 gated tree first
    tracked = [(p, _git(live, "ls-tree", "HEAD", "--", p.as_posix(), check=False)) for p in paths]
    tracked = [(p, row) for p, row in tracked if row]
    if len(tracked) != 1:
        return False
    rel, row = tracked[0]
    if row.split()[0] not in ("100644", "100755"):
        return False
    added = _git(live, "log", "--diff-filter=A", "--format=%H", "-1", "HEAD", "--", rel.as_posix(), check=False)
    if not added:
        return False
    base = _git(live, "merge-base", sha, "HEAD", check=False)
    if not base:
        return False
    return _is_ancestor(live, base, added) and not _is_ancestor(live, added, sha)


def _is_ancestor(live, a, b):
    r = subprocess.run(["git", "-C", str(live), "merge-base", "--is-ancestor", a, b], capture_output=True, text=True)
    return r.returncode == 0


def _junit_ids(path):
    return {f"{tc.get('classname')}::{tc.get('name')}" for tc in ET.parse(path).getroot().iter("testcase")}


def uses_marker(scratch, marker=SIBLING_MARKER):
    """M80: the fork's test sources (`mlx_vlm/tests/**/*.py`) mention the marker."""
    tests = Path(scratch) / "mlx_vlm" / "tests"
    return tests.is_dir() and any(marker in p.read_text(errors="replace") for p in tests.rglob("*.py") if p.is_file())


def _marked_problems(runner, scratch, passed_ids, junit):
    """M80: (problems, marked ids, listing output) — every `requires_mlx_serve` test (junit properties ∪ a `--collect-only` listing in the
    same scratch) must be among the passed ids; when the test sources use the marker the listing must name at least one."""
    py = str(Path(scratch) / ".venv" / "bin" / "python")
    argv = [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *PYTEST_NO_ADDOPTS, "--collect-only", "-m", SIBLING_MARKER,
            "mlx_vlm/tests"]
    rc, out = runner(argv, scratch, dict(PYTEST_ENV_DROP))
    if rc not in (0, 5):  # 5: nothing selected
        return [f"{SIBLING_MARKER} listing: rc {rc}"], [], out
    try:
        listed = marked_from_listing(out)
    except GateError as exc:
        return [str(exc)], [], out
    if not listed and uses_marker(scratch):
        return [f"{SIBLING_MARKER} marked tests expected but none collected"], [], out
    marked = sorted(set(listed) | set(marked_from_junit(junit)))
    not_passed = [t for t in marked if t not in set(passed_ids)]
    return ([f"{SIBLING_MARKER} tests skipped: {not_passed}"] if not_passed else []), marked, out


def run(repo, sha, *, live, gate_dir, baselines, runner=_real_runner, busy=_real_busy, dirty=_real_dirty, artifacts=_artifacts,
        mlx_serve_sha=None):
    live, gate_dir = Path(live), Path(gate_dir)
    if busy():
        raise GateError("box busy: " + "; ".join(busy())[:400])
    if identity(_git(live, "remote", "get-url", "origin")) != repo:
        raise GateError(f"{live} origin is not the canonical {repo}")
    if mlx_serve_sha and repo != "mlx-vlm":
        raise GateError("--mlx-serve-sha pairs an mlx-vlm run only")
    sha = _git(live, "rev-parse", f"{sha}^{{commit}}")
    base = pushed_base(live) if repo == "stack" else None   # S25-P10: refused before any step when absent
    # M80: an mlx-vlm run always pairs — the pin resolves to a commit in `../mlx-serve` or the run is refused before any step
    paired = pinned_mlx_serve(live, mlx_serve_sha) if repo == "mlx-vlm" else None
    parity = current_parity(repo, live, sha)
    audits = _audits_for(repo, live, sha)
    baseline_file = Path(baselines) / f"{repo}.skips.txt"
    baseline = baseline_file.read_text() if baseline_file.exists() else None
    digest = policy_digest(repo, _gate_source(), baseline if baseline is not None else "<none>", parity, audits)
    run_dir = gate_dir / "scratch" / f"{repo}-{sha[:12]}-{time.time_ns()}"
    scratch = run_dir / "mlx-vlm" if repo == "mlx-vlm" else run_dir   # M80: the fork clone beside `<run>/mlx-serve`
    receipt = dict(repo=repo, sha=sha, policy_digest=digest, parity_ref=parity, python="3.12", steps=[], problems=[],
                   baseline_skips_ran=[], baseline_skips_absent=[], live_head=_git(live, "rev-parse", "HEAD", check=False),
                   started=time.strftime("%Y-%m-%d %H:%M:%S"),
                   not_covered="python 3.10 (fork CI)" if repo == "mlx-vlm" else
                   ("python 3.11 / 3.13 (CI matrix)" if repo == "mlx-serve" else None))
    if repo == "mlx-vlm":
        receipt["paired"] = {SIBLING: paired}
    if repo == "stack":
        receipt["pushed_base"] = base
    last = None          # (step name, full output) of the last step that ran — kept on FAIL (M75)
    junit_bytes = None
    try:
        for step in steps_for(repo, scratch, parity, audits, pushed_base=base):
            if busy():
                receipt["problems"].append(f"box became busy before {step.name}")
                break
            t0 = time.monotonic()
            if step.name == "clone":
                clone_scratch(live, sha, scratch)
                if base:
                    _fetch_pushed_base(scratch, live, base)
                rc, out = 0, ""
            elif step.name == "submodules":
                _submodules(scratch, live)
                rc, out = 0, ""
            elif step.name == "sibling":   # M80: `<live>.parent / "mlx-serve"` at the pinned sha, beside the fork clone
                clone_scratch(live.parent / SIBLING, paired, step.cwd)
                rc, out = 0, ""
            elif step.name == "upstream":
                _git(scratch, "remote", "add", "upstream", UPSTREAM_VLM)
                _git(scratch, "remote", "set-url", "--push", "upstream", "no_push")
                rc, out = runner(step.argv, step.cwd, step.env)
            else:
                rc, out = runner(step.argv, step.cwd, step.env)
            last = (step.name, out)
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
            if step.name not in ("clone", "submodules", "sibling") and dirty(scratch, step.name):
                receipt["problems"].append(f"{step.name} left tracked files modified")
                break
        else:
            junit = scratch / ".gate-junit.xml"
            skipped = skipped_from_junit(junit)
            passed_ids = ran_and_passed_from_junit(junit)
            receipt["skipped_tests"] = skipped or []
            if baseline is None:
                receipt["problems"].append(f"no skip baseline {baseline_file} — review the skipped tests, then commit it")
            if skipped is None or passed_ids is None:
                receipt["problems"].append("pytest junit not written")
            elif baseline is not None:
                want = sorted(l for l in baseline.splitlines() if l.strip())
                passed = set(passed_ids)
                missing = sorted(set(want) - set(skipped))
                receipt["baseline_skips_ran"] = [w for w in missing if w in passed]
                extra = sorted((collections.Counter(skipped) - collections.Counter(want)).elements())
                if extra:
                    receipt["problems"].append(f"skip list != baseline: +{extra} -{missing}")
                duplicated = sorted(w for w, n in collections.Counter(want).items() if n > 1)
                if duplicated:
                    receipt["problems"].append(f"skip baseline lists an entry more than once: {duplicated}")
                unexplained = [w for w in missing if w not in passed]
                ids = _junit_ids(junit) if unexplained else set()
                absent = [w for w in unexplained if _absent_allowed(w, scratch=scratch, live=live, sha=sha, junit_ids=ids)]
                receipt["baseline_skips_absent"] = sorted(absent)
                unexplained = [w for w in unexplained if w not in absent]
                if unexplained:
                    receipt["problems"].append(f"baseline skip neither skipped nor passed: {unexplained}")
            if repo == "mlx-vlm" and passed_ids is not None:   # M80: no marked test skips (or is deselected) silently
                problems, marked, out = _marked_problems(runner, scratch, passed_ids, junit)
                receipt[f"{SIBLING_MARKER}_tests"] = len(marked)
                if problems:
                    receipt["problems"] += problems
                    last = (SIBLING_MARKER, out)
    except (GateError, subprocess.CalledProcessError, OSError) as exc:
        receipt["problems"].append(f"{type(exc).__name__}: {exc}"[:600])
    finally:
        try:
            junit_bytes = (scratch / ".gate-junit.xml").read_bytes()
        except OSError:
            junit_bytes = None
        shutil.rmtree(run_dir, ignore_errors=True)
    receipt["verdict"] = "PASS" if not receipt["problems"] and len(receipt["steps"]) == len(steps_for(repo, scratch, parity, audits)) \
        else "FAIL"
    receipt["ended"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path, fd = _receipt_path(gate_dir, repo, sha, digest)
    receipt["failure_artifacts"] = []
    if receipt["verdict"] == "FAIL":
        keep = [(f".{last[0]}.log", last[1].encode())] if last and last[1] else []
        keep += [(".junit.xml", junit_bytes)] if junit_bytes is not None else []
        for suffix, data in keep:
            side = path.with_name(path.stem + suffix)
            try:
                sfd = os.open(side, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
                os.write(sfd, data)
                os.close(sfd)
                receipt["failure_artifacts"].append(side.name)
            except OSError as exc:
                receipt["problems"].append(f"failure artifact {side.name} not kept: {exc}"[:300])
    os.write(fd, (json.dumps(receipt, indent=1) + "\n").encode())
    os.close(fd)
    return path


# ------------------------------------------------------------------ check (pre-push)
def pass_receipt(gate_dir, repo, sha, digest):
    """The file name of a PASS receipt for exactly `sha` under `digest`, else None."""
    for p in sorted(Path(gate_dir).glob(f"{repo}-{sha}-{digest[:12]}*.json")):
        try:
            doc = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("verdict") == "PASS" and doc.get("sha") == sha and doc.get("policy_digest") == digest:
            return p.name
    return None


def has_pass(gate_dir, repo, sha, digest):
    return pass_receipt(gate_dir, repo, sha, digest) is not None


# P541: a push passes a named level
def is_docs_path(path):
    return path.startswith("docs/") or ("/" not in path and path.endswith(".md"))


def is_data_path(path):
    return path.startswith("benchmark/results/")


def _git_raw(cwd, *a):
    """`git` stdout as bytes, nothing stripped (NUL-separated path lists; git paths are byte strings)."""
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True)
    if r.returncode != 0:
        raise GateError(f"git {' '.join(a)} in {cwd}: {r.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return r.stdout


def _touched(repo_dir, commit):
    """Paths a commit touches, read losslessly (`-z`, split on NUL, nothing stripped); a merge contributes its diff against
    its first parent."""
    parents = _git(repo_dir, "rev-list", "--parents", "-n", "1", commit).split()[1:]
    if len(parents) > 1:
        raw = _git_raw(repo_dir, "diff-tree", "-r", "-z", "--name-only", parents[0], commit)
    else:
        raw = _git_raw(repo_dir, "diff-tree", "-r", "-z", "--no-commit-id", "--name-only", "--root", commit)
    return [p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p]


def push_level(repo, repo_dir, remote, local_ref, local_sha, remote_ref, *, gate_dir, digest_for):
    """P541: (level, detail, problems) for one pushed ref update; detail = the receipt file name for `full`."""
    sha = _git(repo_dir, "rev-parse", f"{local_sha}^{{commit}}")
    local_sha = sha
    if repo == "stack" and remote_ref == EVIDENCE_REF:  # P447: the orphan data branch (no merge base with <remote>/main)
        if subprocess.run(["git", "-C", str(repo_dir), "merge-base", sha, f"{remote}/main"], capture_output=True).returncode == 0:
            return "full", "", [f"REFUSED: {repo} {sha[:8]}: pushed to {EVIDENCE_REF} shares history with {remote}/main: "
                                f"not an orphan data commit"]
        return "data-only", "", []
    commits = introduced(repo_dir, remote, sha, exclude_evidence=remote_ref != EVIDENCE_REF)
    if not commits:
        return "none-new", "", []
    paths = {p for c in commits for p in _touched(repo_dir, c)}
    if paths and repo == "stack" and all(is_data_path(p) for p in paths):
        return "data-only", "", []
    if paths and all(is_docs_path(p) for p in paths):
        return "docs-only", "", []
    try:
        name = pass_receipt(gate_dir, repo, local_sha, digest_for(repo, local_sha))
    except Exception as exc:  # v1.4: any failure computing the digest refuses this ref only
        return "full", "", [f"REFUSED: {repo} {local_sha[:8]}: cannot compute the policy digest ({type(exc).__name__}: {exc})"]
    if name and repo == "stack":
        # S27 §12 (C371 (2), option B): the gate's closure proof holds only while the protected files are unchanged between the
        # receipt's `pushed_base` and the fetched `<remote>/main` (any ref at level full; `check` has fetched by now)
        problems = push_binding_problems(repo_dir, remote, Path(gate_dir) / name, local_sha)
        if problems:
            return "full", "", problems
    if name:
        return "full", name, []
    return "full", "", [f"REFUSED: {repo} {local_sha[:8]}: no PASS gate receipt for a code push (level full required; "
                        f"run: bench.local_gate run --repo {repo} --sha {local_sha})"]


def __getattr__(name):
    if name == "PROTECTED_PUSH_PATHS":            # S27 §12: the imported constant, resolved lazily (no client import at load)
        return protected_push_paths()
    raise AttributeError(name)


def protected_push_paths():
    """S27 §12: `PROTECTED_PUSH_PATHS` — the tg1 carrier and the three plugins (`arm_specs.OC.generation_data`, the existing
    four-file constant; a test pins its equality with the closure test's paths)."""
    from bench import arm_specs
    return tuple(arm_specs.OC.generation_data)


def push_binding_problems(repo_dir, remote, receipt_path, sha):
    """S27 §12: [] when the PASS receipt DOCUMENT carries a `pushed_base` that exists in the repo and
    `git diff --no-renames --name-only <pushed_base> <remote>/main -- <PROTECTED_PUSH_PATHS>` succeeds and is empty; else the
    refusal (any git error refuses), with a regate hint."""
    hint = f"(regate against the current {remote}/main: bench.local_gate run --repo stack --sha {sha})"
    try:
        doc = json.loads(Path(receipt_path).read_text())
    except (OSError, ValueError) as exc:
        return [f"REFUSED: stack {sha[:8]}: the PASS receipt {Path(receipt_path).name} is unreadable ({type(exc).__name__}) {hint}"]
    base = doc.get("pushed_base") if isinstance(doc, dict) else None
    if not (isinstance(base, str) and re.fullmatch(r"[0-9a-f]{40}", base)):
        return [f"REFUSED: stack {sha[:8]}: the PASS receipt carries no pushed_base (the protected-path binding cannot be "
                f"checked) {hint}"]
    exists = subprocess.run(["git", "-C", str(repo_dir), "cat-file", "-e", f"{base}^{{commit}}"], capture_output=True)
    if exists.returncode:
        return [f"REFUSED: stack {sha[:8]}: the receipt's pushed_base {base[:12]} is not a commit of this repository {hint}"]
    diff = subprocess.run(["git", "-C", str(repo_dir), "diff", "--no-renames", "--name-only", base, f"{remote}/main", "--",
                           *protected_push_paths()], capture_output=True, text=True)
    if diff.returncode:
        return [f"REFUSED: stack {sha[:8]}: git diff of the protected paths failed ({diff.stderr.strip()[:200]}) {hint}"]
    moved = [p for p in diff.stdout.splitlines() if p.strip()]
    if moved:
        return [f"REFUSED: stack {sha[:8]}: {remote}/main changed protected file(s) {moved} since the gate's pushed_base "
                f"{base[:12]}: the closure proof no longer describes this push {hint}"]
    return []


def introduced(repo_dir, remote, sha, exclude_evidence=False):
    """v1.3: for a non-evidence push `exclude_evidence` leaves `refs/remotes/<remote>/evidence` out of the `--not` set."""
    ex = [f"--exclude={remote}/evidence"] if exclude_evidence else []  # git: the pattern is relative to refs/remotes/
    return _git(repo_dir, "rev-list", sha, "--not", *ex, f"--remotes={remote}").split()


def _scan(repo_dir, commits, naming=True, *, exceptions=None):
    from bench import modelnames, piicheck

    out = []
    for c in commits:
        diff = _git(repo_dir, "show", "--format=", "--unified=0", "--root", c)
        findings = [f"{c[:8]} PII: {v}" for v in piicheck.diff_violations(diff)]
        if naming:
            msg = _git(repo_dir, "show", "-s", "--format=%B", c)
            findings += [f"{c[:8]} naming: {v}" for v in modelnames.diff_violations(diff)]
            findings += [f"{c[:8]} message: {v}" for v in modelnames.message_violations(msg)]
        if exceptions is not None and c in exceptions:
            payload = json.dumps(findings, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            if hashlib.sha256(payload).hexdigest() == exceptions[c]:
                continue
        out += findings
    return out


def pairing_problems(links, *, gate_dir, digest_for):
    """M81 (C332): the fork gitlink needs a PASS receipt (current policy) whose `paired` mlx-serve is the stack commit's own
    src/mlx-serve gitlink — the M80 pairing is checked against what the stack actually pins. No-op without both gitlinks."""
    fork, serve = links.get("src/mlx-vlm"), links.get("src/mlx-serve")
    if not fork or not serve:
        return []
    digest = digest_for(GITLINKS["src/mlx-vlm"], fork)
    for p in sorted(Path(gate_dir).glob(f"mlx-vlm-{fork}-{digest[:12]}*.json")):
        try:
            doc = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if (doc.get("verdict") == "PASS" and doc.get("sha") == fork and doc.get("policy_digest") == digest
                and (doc.get("paired") or {}).get(SIBLING) == serve):
            return []
    return [f"src/mlx-vlm {fork[:8]}: its PASS receipts are not paired with src/mlx-serve {serve[:8]} (run: bench.local_gate run "
            f"--repo mlx-vlm --sha {fork} --mlx-serve-sha {serve})"]


def gitlink_problems(links, forks, *, gate_dir, digest_for):
    out = pairing_problems(links, gate_dir=gate_dir, digest_for=digest_for)
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


def check_lines(repo, repo_dir, remote, lines, *, gate_dir, digest_for, forks=None, levels=None, remote_url=None):
    """P541: every pushed ref (branch, or fork tag) passes a level (`push_level`, which also owns the P447 evidence orphan
    rule) and the per-commit scans; a stack TAG must be SemVer `vX.Y.Z` and carries the release rule (P448: PASS receipt for
    the tagged commit under the current policy + both gitlinks' receipts and reachability). `levels`, when a list, receives
    one `level: …` line per ref that has no problem at all (level or scan)."""
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
        ref_out, shown = [], None
        evidence = repo == "stack" and remote_ref == EVIDENCE_REF  # P447: data — PII only
        exceptions = None
        if (repo == "mlx-vlm" and remote == "origin" and remote_url in MLX_VLM_ORIGIN_URLS
                and remote_ref == "refs/heads/main"):
            exceptions = MLX_VLM_UPSTREAM_SCAN_EXCEPTIONS
        ref_out += _scan(repo_dir, introduced(repo_dir, remote, sha, exclude_evidence=remote_ref != EVIDENCE_REF),
                         naming=not evidence, exceptions=exceptions)
        if repo == "stack" and remote_ref.startswith("refs/tags/"):
            name = remote_ref[len("refs/tags/"):]
            if not SEMVER_TAG.match(name):
                ref_out.append(f"tag {name}: a stack tag must be SemVer vMAJOR.MINOR.PATCH (refused)")
            else:
                if not has_pass(gate_dir, repo, sha, digest_for(repo, sha)):
                    ref_out.append(f"tag {name} {sha[:8]}: no PASS release receipt under the current gate policy "
                                   f"(run: bench.local_gate release --version {name[1:]})")
                links, missing = _gitlinks_at(repo_dir, sha)
                ref_out += missing
                if links:
                    ref_out += gitlink_problems(links, forks or {p: Path(repo_dir).parent / r for p, r in GITLINKS.items()},
                                                gate_dir=gate_dir, digest_for=digest_for)
        else:
            level, detail, problems = push_level(repo, repo_dir, remote, local_ref, sha, remote_ref, gate_dir=gate_dir,
                                                 digest_for=digest_for)
            ref_out += problems
            if repo == "stack" and not evidence and any(  # M81: a push that changes a gitlink re-checks the pairing
                    p in GITLINKS for c in introduced(repo_dir, remote, sha, exclude_evidence=True)
                    for p in _touched(repo_dir, c)):
                links, missing = _gitlinks_at(repo_dir, sha)  # a deleted gitlink fails closed (cold read, GLM)
                ref_out += missing + pairing_problems(links, gate_dir=gate_dir, digest_for=digest_for)
            shown = f"full (receipt {detail})" if level == "full" else level
        out += ref_out
        if shown and not ref_out and levels is not None:
            levels.append(f"level: {shown} {remote_ref} {sha[:8]}")
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
    r.add_argument("--mlx-serve-sha", default=None,
                   help="mlx-vlm only: the ../mlx-serve commit to pair with (default: the stack HEAD's src/mlx-serve gitlink)")
    c = sub.add_parser("check")
    c.add_argument("--repo-dir", required=True)
    c.add_argument("remote")
    c.add_argument("url", nargs="?")
    sub.add_parser("install-hooks")
    rel = sub.add_parser("release")
    rel.add_argument("--version", required=True, help="MAJOR.MINOR.PATCH (the tag is v<version>, on the stack HEAD)")
    args = ap.parse_args(argv)
    stack = _stack_repo()
    lock = None
    try:
        if args.cmd == "install-hooks":
            print(install_hooks(stack))
            return 0
        if args.cmd == "check" and identity(_git(args.repo_dir, "remote", "get-url", "origin", check=False)) is None:
            print(f"[pre-push] REFUSED: unknown origin for {args.repo_dir}", file=sys.stderr)
            return 1
        gate_dir = Path(_workdir()) / "gate"
        if args.cmd in ("run", "release"):          # B2 spec 9: a test window excludes the Wave-2 sequencer and its chain legs
            lock = _hold_running(Path(_workdir()))
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
            path = run(args.repo, args.sha, live=live[args.repo], gate_dir=gate_dir, baselines=_baselines(),
                       mlx_serve_sha=args.mlx_serve_sha)
            doc = json.loads(path.read_text())
            print(json.dumps({k: doc.get(k) for k in ("repo", "sha", "verdict", "problems")}, indent=1), f"\n{path}")
            return 0 if doc["verdict"] == "PASS" else 1
        repo = identity(_git(args.repo_dir, "remote", "get-url", "origin"))
        levels = []
        problems = check_lines(repo, args.repo_dir, args.remote, sys.stdin.read().splitlines(), gate_dir=gate_dir,
                               digest_for=lambda rp, sha: digest_for(rp, sha, live[rp], _baselines()), levels=levels,
                               remote_url=args.url)
    except GateError as exc:
        print(f"[local_gate] REFUSED: {exc}", file=sys.stderr)
        return 1
    finally:
        if lock is not None:
            lock.release()
    for lv in levels:
        print(f"[pre-push] {lv}", file=sys.stderr)
    for p in problems:
        print(f"[pre-push] {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
