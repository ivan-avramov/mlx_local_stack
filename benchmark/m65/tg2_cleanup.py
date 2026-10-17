#!/usr/bin/env python3
"""Explicit tg2 recovery (P363): list labelled leftovers, or remove exactly the objects one grade registry file records.

    tg2_cleanup.py --list   --private <private dir>
    tg2_cleanup.py --remove <private>/.tg2-registry/<file>.json --private <private dir>

Nothing is ever removed automatically; --remove touches only the names in the given registry file, verifies each
removal and exits nonzero when it cannot."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench import tg2_grade as tg  # noqa: E402
from bench.token_turn_gate import TransportAbort  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--private", required=True, help="private dir used by the grades (holds .tg2-registry)")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true")
    group.add_argument("--remove", metavar="REGISTRY_FILE")
    args = ap.parse_args(argv)
    run = tg.LocalDocker().run_grader
    try:
        if args.list:
            print(json.dumps(tg.list_leftovers(run, args.private), indent=1))
        else:
            print(json.dumps(tg.remove_registered(run, args.remove, args.private), indent=1))
    except TransportAbort as exc:
        print("tg2_cleanup: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
