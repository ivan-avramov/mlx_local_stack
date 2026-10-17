"""Per-arm (model x predictor) identity of a tg1 worker (P311-lite, spec 4).

The generation composite is shared by every arm; this is the model-specific half: a sha256 of the EFFECTIVE worker
fingerprint, built from the verified worker argv and the served registry entry, covering the target AND draft
artifacts (HF repo + revision + the content-addressed blob of every file, or a local content hash) and every
output-determining flag. A flag this table does not know REFUSES: a new serving knob must be classified here
(output-determining or inert) before any arm may run with it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# Flags that take a value and shape the tokens a worker returns (or the cache state they are computed from).
OUTPUT_VALUE_FLAGS = (
    "--model", "--draft-kind", "--draft-model", "--draft-block-size", "--suffix-min-match", "--draft-cooldown",
    "--mtp-verify-scan", "--attention-policy", "--max-kv-size", "--kv-prealloc-tokens", "--kv-bits",
    "--kv-quant-scheme", "--quantized-kv-start", "--prefill-step-size", "--generation-defaults", "--moe-expand",
    "--cache-session-retain-prompt-end",
)
OUTPUT_BOOL_FLAGS = ("--mtp-verify-ab", "--lazy-prompt-embeddings")
# Serving plumbing that changes where or how much memory, never the output: parsed, recorded as seen, not hashed.
INERT_VALUE_FLAGS = ("--host", "--port", "--memory-limit-frac", "--cache-limit-gb")
# Registry keys that are client presentation, not serving.
ENTRY_IGNORED = ("presentation",)


class ArmIdentityError(ValueError):
    """The worker or its artifacts cannot be identified (unknown flag, mismatch with the entry, artifact missing)."""


def parse_argv(argv):
    """{flag: value | True} of a worker argv (program and script tokens skipped). Unknown or duplicate flags and a
    missing `--model` refuse."""
    tokens = list(argv)
    start = next((i for i, t in enumerate(tokens) if t.startswith("--")), len(tokens))
    tokens = tokens[start:]
    flags, i = {}, 0
    while i < len(tokens):
        token = tokens[i]
        if not token.startswith("--"):
            raise ArmIdentityError(f"unexpected worker argument {token!r}")
        flag, eq, inline = token.partition("=")
        if flag in OUTPUT_BOOL_FLAGS and not eq:
            value = True
        elif flag in OUTPUT_VALUE_FLAGS + INERT_VALUE_FLAGS:
            if eq:
                value = inline
            elif i + 1 < len(tokens):
                i += 1
                value = tokens[i]
            else:
                raise ArmIdentityError(f"worker flag {flag} has no value")
        else:
            raise ArmIdentityError(f"unknown worker flag {flag}: classify it in bench/arm_identity.py before any arm runs")
        if flag in flags:
            raise ArmIdentityError(f"duplicate worker flag {flag}")
        flags[flag] = value
        i += 1
    if "--model" not in flags:
        raise ArmIdentityError("worker argv has no --model")
    return flags


def _home_normalised(text):
    home = os.path.expanduser("~")
    return ("$HOME" + text[len(home):]) if text == home or text.startswith(home + os.sep) else text


def _normalise(value):
    """Home-normalise every string in a JSON-able value: the fingerprint carries no absolute home path and is the
    same on every box that serves the same artifacts."""
    if isinstance(value, str):
        return _home_normalised(value)
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    return value


def _dir_sha256(path):
    digest = hashlib.sha256()
    root = Path(path)
    for file in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(file.relative_to(root).as_posix().encode() + b"\0")
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def artifact_identity(spec, hf_home=None):
    """Identity of one model artifact: a local directory (content hash) or a HF repo id (repo, the revision `main`
    points at, and the content-addressed blob name of every snapshot file). Absent from the local cache refuses."""
    local = Path(os.path.expandvars(os.path.expanduser(spec)))
    if local.is_dir():
        return {"kind": "local", "path": _home_normalised(str(local)), "sha256": _dir_sha256(local)}
    hub = Path(hf_home or os.environ.get("HF_HOME") or "~/.cache/huggingface").expanduser() / "hub"
    root = hub / ("models--" + spec.replace("/", "--"))
    snapshots = root / "snapshots"
    if not snapshots.is_dir():
        raise ArmIdentityError(f"artifact {spec} is not in the local cache (no snapshot directory)")
    try:
        revision = (root / "refs/main").read_text().strip()
    except OSError:
        revision = None
    if not revision:
        names = sorted(p.name for p in snapshots.iterdir() if p.is_dir())
        if len(names) != 1:
            raise ArmIdentityError(f"artifact {spec}: no refs/main and {len(names)} snapshots; revision is ambiguous")
        revision = names[0]
    snap = snapshots / revision
    if not snap.is_dir():
        raise ArmIdentityError(f"artifact {spec}: revision {revision} has no snapshot in the local cache")
    files = {}
    for file in sorted(p for p in snap.rglob("*") if p.is_file() or p.is_symlink()):
        rel = file.relative_to(snap).as_posix()
        if file.is_symlink():
            files[rel] = os.path.basename(os.readlink(file))
        else:
            files[rel] = "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest()
    if not files:
        raise ArmIdentityError(f"artifact {spec}: empty snapshot {revision}")
    return {"kind": "hf", "repo": spec, "revision": revision, "files": files}


def fingerprint(argv, entry, *, hf_home=None):
    """The effective worker fingerprint (JSON-able): output-determining flags, the served registry entry without
    its presentation block, and the target and (when a drafter is on) draft artifacts. The argv must agree with
    the entry on the model and the drafter."""
    flags = parse_argv(argv)
    entry = {k: v for k, v in (entry or {}).items() if k not in ENTRY_IGNORED}
    if flags["--model"] != entry.get("hf_path"):
        raise ArmIdentityError(f"worker --model {flags['--model']!r} != served entry hf_path {entry.get('hf_path')!r}")
    kind = flags.get("--draft-kind") or "off"
    entry_kind = entry.get("draft_kind") or "off"
    if kind != entry_kind:
        raise ArmIdentityError(f"worker draft kind {kind!r} != served entry draft_kind {entry_kind!r}")
    drafter = flags.get("--draft-model")
    if kind not in ("off", "none"):
        if not drafter:
            raise ArmIdentityError(f"worker has draft kind {kind!r} but no --draft-model")
        if drafter != entry.get("draft_model"):
            raise ArmIdentityError(f"worker --draft-model {drafter!r} != served entry draft_model "
                                   f"{entry.get('draft_model')!r}")
    elif drafter:
        raise ArmIdentityError("worker has --draft-model without a draft kind")
    return _normalise({
        "flags": {k: v for k, v in sorted(flags.items()) if k not in INERT_VALUE_FLAGS},
        "entry": entry,
        "target": artifact_identity(flags["--model"], hf_home),
        "draft": artifact_identity(drafter, hf_home) if drafter else None,
    })


def arm_identity_sha256(fp):
    return hashlib.sha256(json.dumps(fp, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def observe(model, router, *, registry_path=None, hf_home=None):
    """(fingerprint, sha256) of THE live worker serving `model`: the single mlx_port listener, an mlx_vlm server
    descending from `router`, whose argv equals the served entry (`provenance._worker_argvs` already refuses an
    unreadable, squatting or ambiguous listener). Anything unverifiable refuses."""
    from . import provenance
    path = Path(registry_path) if registry_path else Path(provenance.paths.registry_path())
    try:
        doc = provenance.yaml.safe_load(path.read_text())
        entry = next(e for e in doc.get("models", []) if isinstance(e, dict) and e.get("name") == model)
        before = provenance._port_listener_pids(int(doc["mlx_port"]))
        workers = provenance._worker_argvs(doc)
        after = provenance._port_listener_pids(int(doc["mlx_port"]))
    except (OSError, ValueError, TypeError, KeyError, StopIteration, provenance.ServingStateError) as exc:
        raise ArmIdentityError(f"cannot observe the worker for {model}: {type(exc).__name__}") from exc
    if len(before) != 1 or before != after or len(workers) != 1:
        raise ArmIdentityError("worker listener is absent, ambiguous or changed during observation")
    if not provenance._descends_from(before[0], {router["pid"]}):
        raise ArmIdentityError("worker does not descend from the verified router")
    fp = fingerprint(workers[0], entry, hf_home=hf_home)
    return fp, arm_identity_sha256(fp)
