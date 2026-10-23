"""P438: stage cited, local-only `$STACK_WORKDIR` directories for the `evidence` branch (layout mirrors `$STACK_WORKDIR`).

  .venv-bench/bin/python -m bench.evidence_backfill --stage <new dir> p400/perf p415/r7 …

Every file is scrubbed and checked as the P437 harvest does (`bench.p426_harvest`); a file over its compression threshold is
published `<name>.xz`; `.npz` arrays are never copied — their sha256 + size go to `EXTERNAL_MANIFEST.json` (P441); venvs,
`node_modules`, `__pycache__` and `tmp/` are skipped and listed. Fail closed: residual PII, an existing stage or a missing /
escaping directory refuses before anything is written. Publishing the stage to `evidence` (commit + push) is a separate,
operator-approved step.
"""

import argparse
import getpass
import hashlib
import json
import socket
import sys
from pathlib import Path

from bench import p426_harvest as H

SKIP_DIRS = {".venv", ".venv-bench", "node_modules", "__pycache__", "tmp"}
EXTERNAL_SUFFIXES = {".npz", ".safetensors", ".npy"}


def _walk(root, wd):
    files, external, skipped = [], [], []
    stack = [root]
    while stack:
        d = stack.pop()
        for p in sorted(d.iterdir()):
            if p.is_symlink():
                skipped.append(str(p.relative_to(wd)))
            elif p.is_dir():
                (skipped.append(str(p.relative_to(wd))) if p.name in SKIP_DIRS else stack.append(p))
            elif p.suffix in EXTERNAL_SUFFIXES:
                external.append(p)
            else:
                files.append(p)
    return files, external, skipped


def stage_files(workdir, files, stage_dir, scrub):
    """P450 v3: stage exactly the listed files (paths relative to $STACK_WORKDIR) — the raw files committed rows cite."""
    wd = Path(workdir).resolve()
    paths = []
    for rel in files:
        p = (wd / rel).resolve()
        if not p.is_relative_to(wd):
            raise H.HarvestError(f"{rel}: outside {wd}")
        if not p.is_file():
            raise H.HarvestError(f"{rel}: not a file")
        paths.append(p)
    return _write_stage(wd, paths, {}, [], stage_dir, scrub)


def stage(workdir, dirs, stage_dir, scrub):
    wd, stage_dir = Path(workdir).resolve(), Path(stage_dir)
    if stage_dir.exists():
        raise H.HarvestError(f"{stage_dir} exists")
    files_all, external, skipped = [], {}, []
    for rel_dir in dirs:
        root = (wd / rel_dir).resolve()
        if not root.is_relative_to(wd):
            raise H.HarvestError(f"{rel_dir}: outside {wd}")
        if not root.is_dir():
            raise H.HarvestError(f"{rel_dir}: not a directory")
        files, ext, skip = _walk(root, wd)
        skipped += skip
        files_all += files
        for p in ext:
            external[str(p.relative_to(wd))] = dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(), bytes=p.stat().st_size)
    return _write_stage(wd, files_all, external, skipped, stage_dir, scrub)


def _write_stage(wd, files, external, skipped, stage_dir, scrub):
    stage_dir = Path(stage_dir)
    if stage_dir.exists():
        raise H.HarvestError(f"{stage_dir} exists")
    staged, problems = [], []
    for p in files:
        data = p.read_bytes()
        rel, scrubbed, published, found = H._publish(data, str(p.relative_to(wd)), scrub, compressible=True)
        problems += found
        staged.append((rel, data, scrubbed, published))
    if problems:
        raise H.HarvestError("; ".join(problems)[:2000])
    manifest = dict(files={}, external=external, skipped=sorted(skipped))
    for rel, data, scrubbed, published in staged:
        dest = stage_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(published)
        rec = dict(original_sha256=H._sha(data), scrubbed_sha256=H._sha(scrubbed), published_sha256=H._sha(published))
        if published is not scrubbed:
            rec["compression"] = "xz"
        manifest["files"][rel] = rec
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "BACKFILL_MANIFEST.json").write_text(json.dumps(dict(files=manifest["files"], skipped=manifest["skipped"]),
                                                                 indent=1, sort_keys=True) + "\n")
    (stage_dir / "EXTERNAL_MANIFEST.json").write_text(json.dumps(external, indent=1, sort_keys=True) + "\n")
    return manifest


def main(argv=None):
    import os

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", required=True)
    ap.add_argument("dirs", nargs="*", help="directories relative to $STACK_WORKDIR")
    ap.add_argument("--files-from", help="P450 v3: a file listing exact paths relative to $STACK_WORKDIR")
    args = ap.parse_args(argv)
    wd = os.environ.get("STACK_WORKDIR")
    if not wd:
        print("[evidence_backfill] STACK_WORKDIR is not set", file=sys.stderr)
        return 2
    host = socket.gethostname()
    scrub = H.Scrub(workdir=Path(wd), repo=Path(os.environ.get("STACK_REPO") or Path(__file__).resolve().parents[2]),
                    home=Path.home(), user=getpass.getuser(), hosts=tuple({host, host.split(".")[0]}))
    try:
        if args.files_from:
            m = stage_files(wd, [l.strip() for l in Path(args.files_from).read_text().splitlines() if l.strip()], args.stage, scrub)
        else:
            m = stage(wd, args.dirs, args.stage, scrub)
    except H.HarvestError as exc:
        print(f"[evidence_backfill] REFUSED: {exc}", file=sys.stderr)
        return 1
    size = sum((Path(args.stage) / r).stat().st_size for r in m["files"])
    print(json.dumps(dict(files=len(m["files"]), published_bytes=size, external=len(m["external"]),
                          external_bytes=sum(e["bytes"] for e in m["external"].values()), skipped=m["skipped"]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
