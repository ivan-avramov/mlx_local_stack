"""Publish configgen's OpenWebUI model defaults, allowlists and default selection.

Generate with `python -m configgen generate` from the stack root first.
Dry-run by default. --apply reconciles and verifies live state; --prune removes
only generated excluded IDs, preserving unrelated personal registrations.
"""

import argparse
from datetime import datetime, timezone
import os
import subprocess
import sys
from pathlib import Path

from reconcile_models import API, authenticate, load_desired, reconcile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--url", default=os.environ.get("OWUI_URL"))
    parser.add_argument("--email", default=os.environ.get("OWUI_ADMIN_EMAIL"))
    parser.add_argument(
        "--main-port", default=os.environ.get("MAIN_MODEL_PORT", "8000")
    )
    parser.add_argument(
        "--task-port", default=os.environ.get("TASK_MODEL_PORT", "8092")
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="Private directory under STACK_WORKDIR; required with --apply",
    )
    args = parser.parse_args()
    if not args.url or (args.apply and not args.backup_dir):
        parser.error("--url is required; --apply also requires --backup-dir")
    root = Path(__file__).resolve().parent.parent
    if (root / "main_models.yaml").exists():
        subprocess.run(
            [sys.executable, "-m", "configgen", "check"], cwd=root, check=True
        )
    models, settings = load_desired()
    headers = authenticate(args.url, args.email, os.environ.get("OWUI_ADMIN_PASSWORD"))
    backup = None
    if args.apply:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        backup = args.backup_dir / f"openwebui-before-{stamp}.json"
    reconcile(
        API(args.url, headers),
        models,
        settings,
        f"http://host.docker.internal:{args.main_port}/v1",
        f"http://host.docker.internal:{args.task_port}/v1",
        apply=args.apply,
        prune=args.prune,
        backup=backup,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
