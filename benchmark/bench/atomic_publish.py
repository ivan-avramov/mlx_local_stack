"""Publish an immutable evidence file so its destination is either ABSENT or COMPLETE (P371 review r5 F23). Stdlib only.

The bytes are written to a same-directory temp file and fsynced, then hard-linked into the destination (a link never replaces: an
existing destination raises `FileExistsError`), the temp is removed and the directory fsynced. A process death leaves at most one
temp named `.<dest name>.tmp.<pid>.<16 hex>` (F26: random per call, created with O_EXCL and never truncated, so two publishers
or a reused pid never share one), which `leftover_temps` lists (F27: exactly that grammar, no other dotfile) and a resume removes."""
from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

TEMP = re.compile(r"^\.(?P<name>.+)\.tmp\.(?P<pid>[0-9]+)\.(?P<rand>[0-9a-f]{16})$")


def temp_name(dest_name):
    return f".{dest_name}.tmp.{os.getpid()}.{secrets.token_hex(8)}"


def parse_temp(name):
    """`{name, pid, rand}` when `name` is exactly a publish temp's name, else None."""
    m = TEMP.match(name)
    return None if m is None else dict(name=m["name"], pid=int(m["pid"]), rand=m["rand"])


def publish_exclusive(dest, raw, mode=0o644):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(16):
        tmp = dest.with_name(temp_name(dest.name))
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)     # never O_TRUNC: a collision is retried
        except FileExistsError:
            continue
        break
    else:
        raise FileExistsError(f"no free temp name for {dest.name}")
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
    found = directory.rglob(".*") if recursive else directory.glob(".*")
    return sorted(p for p in found if p.is_file() and parse_temp(p.name) is not None)
