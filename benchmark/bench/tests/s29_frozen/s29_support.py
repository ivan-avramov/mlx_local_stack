"""S29 frozen tests: shared fixtures (spec docs/specs/s29-record-not-block.md v1.0; C384 / S29-P6). TESTS ONLY; temp trees and fakes, no
GPU / network / docker / real Homebrew. Every fixture is in the format of the code it stands for:

- the host: `s26_frozen.s26_support.HostWorld` (a temp host the REAL `bench.host_env.fingerprint()` / `diff()` read) and the sequencer
  fake `HostSeqOps` (the frozen B2 sequencer driver + the `host_env` seam);
- a leg record in the shape of the recorded `tg2-m76-x-s1.a3` (`attempt`, `chain_rc` 0, `class` systemic, `overrun` false, a
  `reason` that starts with the host-change phrase and carries no `(prior: ...)`, `speed_valid` true, state INVALID), sealed by
  `p426_hooks.write_exclusive` (the sequencer's own writer);
- the evidence layout of a tg2 grade directory: `<lang>__<slug>.grades/seq-NNNN/{execute.marker, execute.out, execute-readback.*}`.

Where the spec leaves a mechanism free (the field names a record uses for a host diff, the file the original `leg.json` is kept
under, how an unrecognised file is listed) the helpers here search the record for the OUTCOME a reader needs, never for a name."""
from __future__ import annotations

import json
from pathlib import Path

from bench import host_env
from bench import p426_hooks as ph
from bench import p426_wave2 as W2
from bench.tests.s26_frozen import s26_support as X

OFF_PILOT, ON_PILOT = "tg1-p426-off-pilot", "tg1-p426-on-pilot"
LAST_LEG = "tg1-p426-off-reload"
JDK = "openjdk@17/17.0.9"
ADDED = f"Homebrew Cellar: added {JDK}"
JEST = "npm -g jest: absent -> 29.7.0"
VIM_NEW = "vim/9.2.1380"
HOST_REASON = W2.HOST_ENV_REASON            # "host environment changed during the leg"


# ------------------------------------------------------------------------------------------------------- host changes
def add_jdk(world):
    world.formula("openjdk@17", "17.0.9")


def add_jest(world):
    world.npm_pkg("jest", "29.7.0")


def vim_world(root):
    """A `HostWorld` that already has the old vim (the a3 upgrade 9.2.1373 -> 9.2.1380 needs something to replace)."""
    world = X.HostWorld(root)
    world.formula("vim", "9.2.1373")
    return world


def upgrade_vim(world):
    world.rm_formula("vim", "9.2.1373")
    world.formula("vim", "9.2.1380")


def at(attr, leg, action):
    """`before=` hook: run `action(world)` at the named seam (`on_launch` / `on_harvest`) of the named leg."""
    def before(ops, clock):
        setattr(ops, attr, lambda name: action(ops.world) if name == leg else None)
    return before


def at_both(**seams):
    """`before=` hook with several seams: `at_both(on_harvest=(leg, action), on_launch=(leg, action))`."""
    def before(ops, clock):
        for attr, (leg, action) in seams.items():
            setattr(ops, attr, (lambda lg, act: lambda name: act(ops.world) if name == lg else None)(leg, action))
    return before


# ------------------------------------------------------------------------------------------------------- reading records
def leaves(doc, path=()):
    """[(path, str)] of every string leaf of a JSON value (list elements carry their index in the path)."""
    if isinstance(doc, str):
        return [(path, doc)]
    out = []
    if isinstance(doc, dict):
        for k, v in doc.items():
            out += leaves(v, path + (k,))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out += leaves(v, path + (i,))
    return out


def containers(doc, needle):
    """The set of parent containers (the path of a leaf without its trailing list index) of every string leaf containing `needle`."""
    out = set()
    for path, text in leaves(doc):
        if needle in text:
            while path and isinstance(path[-1], int):
                path = path[:-1]
            out.add(path)
    return out


def dict_nodes(doc):
    """Every dict inside a JSON value (the value itself first)."""
    out = []
    if isinstance(doc, dict):
        out.append(doc)
        for v in doc.values():
            out += dict_nodes(v)
    elif isinstance(doc, list):
        for v in doc:
            out += dict_nodes(v)
    return out


def text_of(path):
    return Path(path).read_text()


def entry_of(r, leg, attempt=1):
    (e,) = [e for e in X.sequence(r)["legs"] if e["leg"] == leg and e["attempt"] == attempt]
    return e


def sha_of(path_or_bytes):
    import hashlib
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------------------------------------------- the a3 shape
def make_a3(tmp_path, monkeypatch, *, reason_suffix="", harvested=False, chain_status=None, overrun=False, upgrade=True,
            committed_harvest=False):
    """The recorded `tg2-m76-x-s1.a3` situation on the sequencer driver: the first leg of the run has ended and the host was upgraded
    (vim, as the a3 was); its `leg.json` is INVALID with the host-change reason and no `(prior: ...)`, `chain_rc` 0, class
    systemic, sealed by the sequencer's own writer; `sequence.json` says INVALID, and the leg is NOT harvested (the a3's harvest was
    refused). `reason_suffix` = a `(prior: ...)` tail; `harvested=True` keeps the leg's harvest record; `chain_status` damages the
    chain.json (so `classify_leg` no longer says VALID); `overrun` = the recorded overrun flag. v1.1: `committed_harvest=True`
    keeps the harvest the first run published (its `HARVEST.json` exists) although `sequence.json` does not record it; by default
    that published file is removed (a refused harvest publishes nothing). The host stays upgraded (as the
    box did). Returns dict(r1, world, base, root, orig_bytes, orig_sha, reason, baseline_bytes)."""
    world = vim_world(tmp_path / "host")
    r1 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, world=world)
    assert r1["rc"] == 0, r1["err"]
    base = r1["base"]
    baseline = json.loads((base / "host_env.json").read_text())["fingerprint"]
    if upgrade:
        upgrade_vim(world)
    reason = HOST_REASON + ": " + "; ".join(host_env.diff(baseline, world.fingerprint())) + reason_suffix
    root = base / f"{OFF_PILOT}.a1"
    old = json.loads((root / "leg.json").read_text())
    (root / "leg.json").unlink()
    doc = {k: v for k, v in old.items() if k != "sha256"}
    doc.update(state="INVALID", reason=reason, overrun=overrun, **{"class": "systemic"})
    ph.write_exclusive(root / "leg.json", doc)
    seq = W2.read_sequence(base)
    for e in seq["legs"]:
        if e["leg"] == OFF_PILOT:
            e.update(state="INVALID", reason=reason)
    if not harvested:
        seq["harvested"] = [h for h in seq["harvested"] if h["attempt"] != f"{OFF_PILOT}.a1"]
    published = r1["ops"].harvest_path(f"{OFF_PILOT}.a1") / "HARVEST.json"
    if not committed_harvest and published.exists():          # v1.1: the a3's harvest was REFUSED: nothing is published for it
        published.unlink()
    W2.write_sequence(base, seq)
    if chain_status is not None:
        chain = json.loads((root / "chain.json").read_text())
        chain["status"] = chain_status
        (root / "chain.json").write_text(json.dumps(chain))
    return dict(r1=r1, world=world, base=base, root=root, orig_bytes=(root / "leg.json").read_bytes(),
                orig_sha=sha_of(root / "leg.json"), reason=reason, baseline_bytes=(base / "host_env.json").read_bytes())


def resume(tmp_path, monkeypatch, a3, *extra, through=OFF_PILOT, before=None):
    """`run --through <leg>` on the box state of `make_a3`, with NO `--rerun` (the resume trace of the spec)."""
    return X.drive(tmp_path, monkeypatch, "run", "--through", through, *extra, world=a3["world"], records=False, before=before)


def files_under(root):
    return {p.relative_to(root).as_posix(): p for p in Path(root).rglob("*") if p.is_file()}
