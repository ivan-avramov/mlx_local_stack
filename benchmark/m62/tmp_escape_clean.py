#!/usr/bin/env python3
"""C147 §4 operator tool: list, and on explicit --yes remove, /tmp paths that a tg1 row only MENTIONED in a shell
command (best-effort candidates the probe never removes automatically).

    tmp_escape_clean.py --rows <rows.jsonl> [--yes] [--root /tmp]

Without --yes this is a dry run. With --yes each shell candidate is still subjected to the identity checks of the
automatic path (no symlink component, our uid, creation time inside the item's recorded `tmp_window`, regular file or
a directory whose every entry qualifies). The pre/post listings of the item are not available here, so the
pre_existing and replaced checks are skipped; the birthtime window is what ties a path to the item.
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
    ap.add_argument("--yes", action="store_true", help="remove the listed shell-mention paths that pass the checks")
    ap.add_argument("--root", default=None, help="the /tmp root (tests)")
    a = ap.parse_args(argv)
    removed = kept = listed = 0
    for line in a.rows.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        window = row.get("tmp_window")
        shell = [c for c in row.get("tmp_escapes") or [] if c.get("source") == "shell"]
        for c in shell:
            listed += 1
            out(f"{row.get('id')}: shell mention {c['path']}  (token: {c.get('token')!r})")
        if not shell or not a.yes:
            continue
        if not (isinstance(window, list) and len(window) == 2):
            out(f"{row.get('id')}: no tmp_window recorded; nothing removed")
            continue
        cleaned, not_removed = pg.tmp_clean(shell, None, None, tuple(window), root=a.root, allow_shell=True)
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
