"""Publish an immutable evidence file so its destination is either ABSENT or COMPLETE (P371 review r5 F23). Stdlib only.

The bytes are written to a same-directory temp file and fsynced, then hard-linked into the destination (a link never replaces: an
existing destination raises `FileExistsError`), the temp is removed and the directory fsynced. A process death leaves at most a
dot-prefixed `.<name>.tmp.<pid>` temp, which `leftover_temps` lists and a resume removes."""
from __future__ import annotations

import os
from pathlib import Path

TEMP_GLOB = ".*.tmp.*"


def publish_exclusive(dest, raw, mode=0o644):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp.{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "wb") as fp:
        fp.write(raw)
        fp.flush()
        os.fsync(fp.fileno())
    try:
        os.link(tmp, dest)
    except FileExistsError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.unlink(missing_ok=True)
    dfd = os.open(dest.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def leftover_temps(directory, recursive=False):
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted((directory.rglob(TEMP_GLOB) if recursive else directory.glob(TEMP_GLOB)))
