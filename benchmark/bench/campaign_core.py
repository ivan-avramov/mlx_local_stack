"""P371 phase 3a (plan 5 "Campaign freeze (P377)", C179): the CORE closures of a campaign.

A decision campaign freezes the shared core at a tagged commit. The core is the probe entry's static import closure
(`probe_code_sha256` recipe: Python closure + the entry's generation data files) AND the chain entry's static import
closure (`identity_closure`). `at_ref(ref, ...)` extracts the repository at `ref` (`git archive` into a temp dir) and
computes both closures there; `closure_shas(repo, ...)` computes them over a working tree. A chain that is given
`--campaign-core <ref>` records `{tag, commit, probe_closure_sha256, chain_closure_sha256}` and refuses unless the
closures at the ref equal the current ones, at creation and again at every launch, resume and exit (the recorded shas
are the comparison). Chain-side module only: no probe closure imports it."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path

from . import identity_closure as ic

EXCLUDES = ("benchmark/results", "docs")


class CampaignError(Exception):
    """The campaign core cannot be established (the ref does not resolve, git or the archive fails)."""


class CampaignCoreMismatch(CampaignError):
    """The current core closures differ from the campaign's."""


def _git(repo, *args, binary=False):
    try:
        got = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, timeout=600, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CampaignError(f"git {args[0]} could not run ({type(exc).__name__})") from None
    if got.returncode:
        raise CampaignError(f"git {args[0]} failed: {got.stderr.decode(errors='replace').strip()[-300:]}")
    return got.stdout if binary else got.stdout.decode().strip()


def members(root, entry, data=()):
    """{repo-relative path: sha256 of its bytes} of the Python closure of `entry` plus `data`, under `root`."""
    import hashlib
    root = Path(root)
    rels = {p.resolve().relative_to(root.resolve()).as_posix() for p in ic.python_closure(root / entry, root)}
    rels |= set(data)
    return {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest() for rel in sorted(rels)}


def _entries(probe_entry=None, probe_data=(), probes=None, chain_entry=None, chain_data=()):
    """`[(label, entry, data)]`: the probe entry (`probe`) or one per arm (`probe[<arm>]`), then the chain entry."""
    if probes is None:
        out = [("probe", probe_entry, probe_data)]
    else:
        out = [(f"probe[{arm}]", spec["entry"], tuple(spec.get("data", ()))) for arm, spec in sorted(probes.items())]
    return out + [("chain", chain_entry, chain_data)]


def closure_shas(repo, *, probe_entry=None, probe_data=(), probes=None, chain_entry, chain_data=()):
    """The core closure sha256s over the tree at `repo` (the `identity_closure.closure_sha256` recipe): one probe closure
    (`probe_closure_sha256`) or one per arm (`probe_closures`, with `probe_closure_sha256` the sha256 of that map), and the
    chain entry's."""
    if probes is None:
        out = dict(probe_closure_sha256=ic.closure_sha256(probe_entry, repo, data=probe_data))
    else:
        closures = {arm: ic.closure_sha256(spec["entry"], repo, data=tuple(spec.get("data", ())))
                    for arm, spec in sorted(probes.items())}
        out = dict(probe_closures=closures, probe_closure_sha256=hashlib.sha256(
            json.dumps(closures, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
    return dict(**out, chain_closure_sha256=ic.closure_sha256(chain_entry, repo, data=chain_data))


def at_ref(ref, repo, **specs):
    """`{tag, commit, probe_closure_sha256 [, probe_closures], chain_closure_sha256}` of the closures AT `ref`."""
    commit = _resolve(ref, repo)
    with tempfile.TemporaryDirectory(prefix="campaign-core-") as tmp:
        _extract(commit, repo, tmp)
        try:
            shas = closure_shas(tmp, **specs)
        except (OSError, SyntaxError) as exc:
            raise CampaignError(f"the core closures at {ref} cannot be computed ({type(exc).__name__}: {exc})") from None
    return dict(tag=ref, commit=commit, **shas)


def _resolve(ref, repo):
    try:
        return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except CampaignError:
        raise CampaignError(f"--campaign-core {ref!r} does not resolve to a commit in this repository") from None


def _extract(commit, repo, dest):
    raw = _git(repo, "archive", "--format=tar", commit, "--", ".", *[f":(exclude){e}" for e in EXCLUDES], binary=True)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(dest, filter="tar")


def differing_members(recorded, repo, **specs):
    """Closure member paths whose bytes differ between the recorded commit and the working tree (diagnostic)."""
    with tempfile.TemporaryDirectory(prefix="campaign-core-") as tmp:
        _extract(recorded["commit"], repo, tmp)
        out = set()
        for _, entry, data in _entries(**specs):
            try:
                then = members(tmp, entry, data)
            except (OSError, SyntaxError):
                then = {}
            try:
                now = members(repo, entry, data)
            except (OSError, SyntaxError):
                now = {}
            out |= {rel for rel in set(then) | set(now) if then.get(rel) != now.get(rel)}
    return sorted(out)


def drifted(recorded, now):
    """The closure labels (`probe`, `probe[<arm>]`, `chain`) whose sha256 differs between two records."""
    rec_maps, now_maps = recorded.get("probe_closures"), now.get("probe_closures")
    bad = []
    if rec_maps is None and now_maps is None:
        if recorded.get("probe_closure_sha256") != now.get("probe_closure_sha256"):
            bad.append("probe")
    elif rec_maps is None or now_maps is None:
        bad.append("probe")                          # one side names the arms' probes, the other a single probe
    else:
        bad += [f"probe[{arm}]" for arm in sorted(set(rec_maps) | set(now_maps)) if rec_maps.get(arm) != now_maps.get(arm)]
    if recorded.get("chain_closure_sha256") != now.get("chain_closure_sha256"):
        bad.append("chain")
    return bad


def require_equal(recorded, now, *, repo=None, **specs):
    """Raise `CampaignCoreMismatch` unless every closure sha256 of `recorded` equals `now`'s (the chain's, and the probe's or
    each arm's). With `repo` and the entry specs the message names the closure members that differ."""
    bad = drifted(recorded, now)
    if not bad:
        return
    names = ""
    if repo is not None and specs and recorded.get("commit"):
        try:
            names = ": " + ", ".join(differing_members(recorded, repo, **specs))
        except CampaignError:
            names = ""
    raise CampaignCoreMismatch(f"campaign core drift: the {' and '.join(bad)} closure differs from the campaign core "
                               f"{recorded.get('tag')} ({str(recorded.get('commit'))[:12]}){names}")


class Campaign:
    """The chain-facing handle: closures at a ref and now, for one chain entry's specs (tests inject a fake)."""

    def __init__(self, repo, **specs):
        self.repo, self.specs = Path(repo), specs

    def at_ref(self, ref):
        return at_ref(ref, self.repo, **self.specs)

    def current(self):
        return closure_shas(self.repo, **self.specs)

    def require_equal(self, recorded, now):
        require_equal(recorded, now, repo=self.repo, **self.specs)
