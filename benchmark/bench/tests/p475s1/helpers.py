"""Drivers for the P475 stage-1 tests: every call into `bench.p475_kv` goes through here (one place to adapt the call shapes the
contract does not fix; delivery 2 adapted them to the candidate's actual signatures)."""
from __future__ import annotations

import json
import shutil

from .fakes import ARMS, PICK, FakeOps, World, arm_lower, leg_name

LEG_ROOT = "p475/legs"
EXPECTED_S = [60.0, 400.0, 800.0, 1500.0]       # the fake's expected rung seconds for every arm (sum 2760 s)


def K():
    import bench.p475_kv as mod
    return mod


def cfg(w, **kw):
    return K().Config(repo=w.main, workdir=w.wd, base=w.base, expected={a: list(EXPECTED_S) for a in ARMS}, **kw)


def parse(w, sub, *flags):
    """The candidate's own CLI parser, over the fake world's roots."""
    top = ["--workdir", str(w.wd), "--repo", str(w.main), "--base", w.base]
    for a in ARMS:
        top += ["--expected-rung-seconds", f"{a}=" + ",".join(f"{x:g}" for x in EXPECTED_S)]
    return K().parse_args(top + [sub, *map(str, flags)])


def world(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch).make_worktrees()
    # the idle gap is satisfied unless a test says otherwise: the previous leg ended long ago
    w.write_last_leg_end("p475", w.epoch0 - 7200)
    return w


def prepare(w, ops=None):
    """The problems `prepare` reports ([] = every arm consistent)."""
    return K().prepare(ops or FakeOps(w), cfg(w))


def preflight(w, arm, max_retries=None, ops=None):
    """The preflight record (dict with `status` PASS / REFUSED and its attempts)."""
    return K().preflight(arm, ops or FakeOps(w), cfg(w), max_retries=max_retries)


def preflight_ok(w, arm, **kw):
    return preflight(w, arm, **kw)["status"] == "PASS"


def ready(w, arms=ARMS):
    """prepare + one passing preflight per arm (through the implementation, so the PASS record has its own format)."""
    ops = FakeOps(w)
    assert prepare(w, ops) == []
    for a in arms:
        assert preflight_ok(w, a, ops=ops), f"preflight {a} did not pass on the fake"
    w.events.clear()                   # the leg under test starts from a clean event log (setup used the lease too)
    w.run_calls.clear()
    w.git_calls.clear()
    return ops


def run_leg(w, arm, block=1, attempt=1, smoke=False, ops=None):
    ops = ops or FakeOps(w)
    name = f"u4-{arm_lower(arm)}-smoke.a{attempt}" if smoke else leg_name(arm, block, attempt)
    return K().run_leg(name, arm, ops, cfg(w))


def run_all(w, ops=None, blocks=2, max_replacements=4, max_not_started=3, max_deciding=1, max_preflight=2, smoke=False):
    flags = ["--blocks", blocks, "--max-replacements", max_replacements, "--max-not-started", max_not_started,
             "--max-deciding", max_deciding, "--max-preflight", max_preflight] + (["--smoke"] if smoke else [])
    return K().run(parse(w, "run", *flags), ops or FakeOps(w))


def matrix(w):
    """(exit code, path) of `matrix` over the world's harvested dossiers."""
    return K().matrix(cfg(w))


def matrix_rc(w):
    return matrix(w)[0]


def receipt_path(w, leg):
    return w.wd / LEG_ROOT / leg / "receipt.json"


def read_receipt(w, leg):
    return json.loads(receipt_path(w, leg).read_text())


def receipts(w):
    """{leg: canonical receipt} of every leg directory."""
    out = {}
    for p in sorted((w.wd / LEG_ROOT).glob("*/receipt.json")):
        out[p.parent.name] = json.loads(p.read_text())
    return out


def dossier(w, leg):
    return w.main / "benchmark/results/p475" / leg


def matrix_path(w, partial=False):
    return w.main / "benchmark/results/p475" / f"MATRIX.{PICK}{'.PARTIAL' if partial else ''}.md"


def clone(src, tmp_path, monkeypatch):
    """A second World over a COPY of src's workdir and main-root trees (a finished run to mutate)."""
    w = World(tmp_path, monkeypatch)
    shutil.rmtree(w.wd)
    shutil.rmtree(w.main)
    shutil.copytree(src.wd, w.wd, symlinks=True)
    shutil.copytree(src.main, w.main, symlinks=True)
    w.t = src.t
    return w


def resign(d):
    """Recompute the dossier's SCRUB_MANIFEST shas after a deliberate edit, so only the dossier's SEMANTIC validation (not its
    integrity hash) can refuse it; files the manifest lists but that no longer exist are dropped from it."""
    import hashlib
    man_path = d / "SCRUB_MANIFEST.json"
    man = json.loads(man_path.read_text())
    for name in list(man["files"]):
        p = d / name
        if p.exists():
            man["files"][name]["published_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            del man["files"][name]
    man_path.write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
