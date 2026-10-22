"""P426 P437: copy one Wave-1 leg's evidence into the MAIN checkout — the leg's rows / sidecars at their
`benchmark/results/<entry>/` path, everything else (receipts incl. refusals, wrapper / watch logs, power receipt, leg stdout,
the server-log slice, the M1 qualify directory) in `benchmark/results/p426/wave1/<leg>/` — scrubbed as the `evidence` branch is
(workdir / repo / home paths → `$STACK_WORKDIR` / `$STACK_REPO` / `$HOME`, username → `<user>`, hostname → `localhost`), with a
`SCRUB_MANIFEST.json` of original and published sha256. Fail closed: an existing destination, residual PII, a binary file
carrying PII or an oversized file refuses before anything is written. Commits are the operator session's (`data(bench)`).
"""

import dataclasses
import hashlib
import json
import re
from pathlib import Path

from bench import piicheck

MAX_FILE_BYTES = 90 * 1024 * 1024  # GitHub refuses files over 100 MB
WAVE1 = Path("benchmark") / "results" / "p426" / "wave1"


class HarvestError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Scrub:
    workdir: Path
    repo: Path
    home: Path
    user: str
    hosts: tuple

    def _paths(self):
        pairs = []
        for p, token in ((self.workdir, "$STACK_WORKDIR"), (self.repo, "$STACK_REPO"), (self.home, "$HOME")):
            for form in {str(Path(p)), str(Path(p).resolve())}:
                pairs.append((form, token))
        return sorted(pairs, key=lambda kv: -len(kv[0]))  # the longest (most specific) path first

    def text(self, s):
        for form, token in self._paths():
            s = s.replace(form, token)
        s = re.sub(rf"(?<![\w.-]){re.escape(self.user)}(?![\w-])", "<user>", s)
        for host in sorted(self.hosts, key=len, reverse=True):
            s = re.sub(rf"(?<![\w.-]){re.escape(host)}(?![\w-])", "localhost", s)
        return s

    def raw_markers(self):
        return [m.encode() for m in (self.user, *self.hosts, *(f for f, _ in self._paths()))]


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _publish(src_bytes, rel, scrub):
    """(published bytes, problems) for one file."""
    if len(src_bytes) > MAX_FILE_BYTES:
        return None, [f"{rel}: {len(src_bytes)} bytes > {MAX_FILE_BYTES}"]
    try:
        text = src_bytes.decode("utf-8")
    except UnicodeDecodeError:
        hits = [m.decode() for m in scrub.raw_markers() if m and m in src_bytes]
        return src_bytes, ([f"{rel}: binary file carries PII markers {hits}"] if hits else [])
    out = scrub.text(text)
    found = piicheck.violations(out, path=rel, line=1)
    return out.encode("utf-8"), [f"{rel}: PII after scrub: {v}" for v in found]


def _sources(name, plan, receipts, stdout, log_slice, dossier):
    """[(destination rel path, source path or None, bytes)] for the leg."""
    items = []
    if plan.get("kind") == "qualify":
        out_dir = Path(plan["out_dir"])
        if out_dir.exists():
            for p in sorted(q for q in out_dir.rglob("*") if q.is_file()):
                items.append((dossier / "m1" / p.relative_to(out_dir), p))
    else:
        res = Path(plan["results_dir"])
        if res.exists():
            for p in sorted(res.glob(f"{plan['stem']}.*")):
                if p.is_file():
                    items.append((Path("benchmark") / "results" / plan["entry"] / p.name, p))
    for p in sorted(Path(receipts).glob(f"{name}.*")):
        if p.is_file():
            items.append((dossier / p.name, p))
    out = [(rel, src, src.read_bytes()) for rel, src in items]
    out.append((dossier / "leg.stdout", None, stdout or b""))
    out.append((dossier / "server_log_slice.log", None, log_slice or b""))
    return out


def harvest(name, plan, *, main_root, receipts, stdout, log_slice, scrub):
    main_root = Path(main_root)
    dossier = WAVE1 / name
    problems, staged = [], []
    if (main_root / dossier).exists():
        problems.append(f"{dossier} exists (a leg is harvested once)")
    for rel, src, data in _sources(name, plan, receipts, stdout, log_slice, dossier):
        if (main_root / rel).exists():
            problems.append(f"{rel} exists")
        published, found = _publish(data, str(rel), scrub)
        problems += found
        staged.append((rel, src, data, published))
    if problems:
        raise HarvestError(f"{name}: " + "; ".join(problems)[:2000])
    manifest = dict(leg=name, files={})
    for rel, src, data, published in staged:
        dest = main_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(published)
        manifest["files"][str(rel)] = dict(source=scrub.text(str(src)) if src else None, original_sha256=_sha(data),
                                           published_sha256=_sha(published))
    (main_root / dossier / "SCRUB_MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    for rel, rec in manifest["files"].items():  # read back
        if _sha((main_root / rel).read_bytes()) != rec["published_sha256"]:
            raise HarvestError(f"{rel}: read-back sha mismatch")
    return manifest


def harvest_run_files(paths, *, main_root, scrub, overwrite=()):
    """The run-level records (frozen.json, the ON overlay; `overwrite` = append-only logs refreshed each harvest)."""
    run = Path(main_root) / WAVE1 / "run"
    staged, problems = [], []
    for p in paths:
        p = Path(p)
        rel = str(WAVE1 / "run" / p.name)
        published, found = _publish(p.read_bytes(), rel, scrub)
        problems += found
        dest = run / p.name
        if dest.exists() and p.name not in overwrite and dest.read_bytes() != published:
            problems.append(f"{rel} differs from the harvested copy")
        staged.append((dest, published))
    if problems:
        raise HarvestError("; ".join(problems)[:2000])
    run.mkdir(parents=True, exist_ok=True)
    for dest, published in staged:
        if not dest.exists() or dest.read_bytes() != published:
            dest.write_bytes(published)
