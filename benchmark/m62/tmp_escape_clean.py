#!/usr/bin/env python3
"""C147 §4 operator tool: list /tmp candidates of tg1 rows and, on explicit --yes, retry the removal of the
recorded WRITE files the probe itself left behind.

    tmp_escape_clean.py --rows <rows.jsonl> [--yes] [--root /tmp]

Same rule as the automatic path (`proc_guard.tmp_clean`): only a completed `write` part whose on-disk bytes still
equal the recorded content hash, with the ownership and birthtime-window checks, is removed. Shell mentions and
`edit` parts are diagnostic only: they are listed and NEVER removed, with or without --yes. The pre/post listings of
the item are not available here, so the pre_existing and replaced checks are skipped; the item's recorded
`tmp_window` ties a path to the item. Without --yes this is a dry run.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench import proc_guard as pg  # noqa: E402


def main(argv=None, out=print):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True, type=Path)
    ap.add_argument("--yes", action="store_true", help="retry removal of recorded write files that pass the checks")
    ap.add_argument("--root", default=None, help="the /tmp root (tests)")
    a = ap.parse_args(argv)
    removed = kept = listed = 0
    for line in a.rows.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        window = row.get("tmp_window")
        found = row.get("tmp_escapes") or []
        for c in found:
            listed += 1
            kind = "write (removable)" if c.get("source") == "write" else f"{c.get('source')} (diagnostic only)"
            out(f"{row.get('id')}: {kind} {c['path']}  (token: {c.get('token')!r})")
        writes = [c for c in found if c.get("source") == "write"]
        if not writes or not a.yes:
            continue
        if not (isinstance(window, list) and len(window) == 2):
            out(f"{row.get('id')}: no tmp_window recorded; nothing removed")
            continue
        cleaned, not_removed = pg.tmp_clean(writes, None, None, tuple(window), root=a.root)
        for path in cleaned:
            out(f"{row.get('id')}: removed {path}")
        for path, reason in not_removed:
            out(f"{row.get('id')}: kept {path} ({reason})")
        removed += len(cleaned)
        kept += len(not_removed)
    out(f"listed={listed} removed={removed} kept={kept}" + ("" if a.yes else " (dry run; pass --yes to remove)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
