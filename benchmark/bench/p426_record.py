"""B2 (P426) frozen records (spec 16.1): read a sealed record, check its self-hash, its `kind` against the leg's mode and, for
the timeout amendment, its link to the `v8_base.json` beside it. Used by the CLI at entry (a refusal) and by the chain before
every invocation (a systemic failure): one reading, two callers."""
from __future__ import annotations

import json
from pathlib import Path

from . import p426_hooks as ph

KINDS = {"rehearsal": "p426_rehearsal", "pilot": "p426_v8_base", "chain": "p426_timeout_amendment",
         "makeup": "p426_timeout_amendment"}


class RecordError(Exception):
    """The record is missing, unreadable, tampered with, of the wrong kind for the mode, or not linked to its v8 base."""


def mode_key(mode, rehearsal=False):
    return "rehearsal" if rehearsal else mode


def read_sealed(path):
    path = Path(path)
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        raise RecordError(f"{path.name} is missing, unreadable or not JSON") from None
    if not ph.sealed_ok(doc):
        raise RecordError(f"{path.name}: its sha256 does not verify (changed after sealing)")
    return doc


def load(path, *, mode, rehearsal=False) -> dict:
    """`{path, doc, base}`: `doc` the record, `base` the record that carries the arm commits and identity (the v8 base beside
    an amendment, else the record itself)."""
    path = Path(path)
    doc = read_sealed(path)
    want = KINDS[mode_key(mode, rehearsal)]
    if doc.get("kind") != want:
        raise RecordError(f"{path.name}: kind {doc.get('kind')!r} does not fit this mode (needs {want})")
    base = doc
    if want == "p426_timeout_amendment":
        base = read_sealed(path.parent / "v8_base.json")
        if doc.get("v8_base_sha256") != base["sha256"]:
            raise RecordError(f"{path.name}: v8_base_sha256 is not the sha256 of the v8_base.json beside it")
    return dict(path=str(path), doc=doc, base=base)
