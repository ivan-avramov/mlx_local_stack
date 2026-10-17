#!/usr/bin/env python3
"""M64 `oc` arm probe (spec 5, 5.1): seeded opencode 2.x sessions through the ArmAdapter. GENERATION ONLY (P311-lite).

The M64 configuration of the tg1 path: the compaction-ON carrier `opencode-v2-web-tg1c` with the shared SearXNG MCP
server (D2), retries off, the shell watchdog, compaction accounted. Imports only the generation core, the tg1 runner (as
a library), the ArmAdapter contract, the opencode adapter and the arm runner; the rows carry no web-audit or answer-key
fields (`bench/tg1_score.py` derives those post hoc). `probe_code_sha256` is the static import closure of this file
(`bench/identity_closure.py`), so a scoring fix never changes it. `run_tg1_probe.py` is untouched and keeps its identity.

Until the D2 search service exists (a later build step) this entry REFUSES to run: the shipped service is the
`UnavailableSearchService` stub.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benchmark"))
from bench import arm_adapter, arm_opencode, arm_runner, m64_search
from bench import opencode_v2_core as _core

_core.bind(globals())
REPO = Path(__file__).resolve().parent.parent
SCAFFOLD = arm_opencode.M64_LABEL


def _sigterm_exit(signum, frame):
    """SIGTERM -> SystemExit(143) so `finally` blocks run (scratch removal, client kill)."""
    raise SystemExit(143)


def _install_sigterm_exit():
    signal.signal(signal.SIGTERM, _sigterm_exit)


def main(search=None):
    _install_sigterm_exit()
    try:
        return _main(search)
    except provenance.ServedConfigError as e:
        sys.exit("REFUSED: " + _scrub_error(e))


def _parser():
    ap = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    ap.add_argument("--model", required=True)
    ap.add_argument("--items", required=True)
    ap.add_argument("--seed-base", type=int, required=True)
    ap.add_argument("--scaffold", choices=[SCAFFOLD], default=SCAFFOLD)
    ap.add_argument("--universe", type=Path)
    ap.add_argument("--expect-items")
    ap.add_argument("--agent-system-file")
    ap.add_argument("--lang", choices=["python", "go"], default="python")
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--chain-total", type=int, default=0)
    ap.add_argument("--a4-v2-receipt")
    ap.add_argument("--allow-version-drift", action="store_true")
    ap.add_argument("--tg1-inject", choices=("stall", "loop", "alloc"))
    ap.add_argument("--cancel-file")
    ap.add_argument("--manifest-ack")
    ap.add_argument("--sampling-profile", choices=("deployed",))
    ap.add_argument("--frozen-prompt-date", help="P364: the date opencode shows the model ('Www Mmm DD YYYY'); "
                    "required, never defaulted")
    ap.add_argument("--epoch-id", help="the M64 epoch this run belongs to (recorded in the manifest and every row)")
    ap.add_argument("--print-identity", action="store_true", help="print the probe identity JSON and exit")
    # Legacy v2 flags: parsed only so that the runner refuses them with its own message.
    for flag, kind in (("--extra-deny-file", Path), ("--rerun-of", str), ("--rerun-index", int), ("--tick-s", int),
                       ("--first-write-tokens", int), ("--hard-ceiling-s", int), ("--stall-ticks", int),
                       ("--loop-repeats", int), ("--poll-s", float)):
        ap.add_argument(flag, type=kind, help=argparse.SUPPRESS)
    return ap


def _main(search):
    adapter = arm_opencode.OpencodeArm(sys.modules[__name__], mode="m64",
                                       search=search if search is not None else m64_search.service())
    if "--print-identity" in sys.argv[1:]:
        # read-only provenance identity; no router, worker or model is touched
        pre = argparse.ArgumentParser(allow_abbrev=False)
        pre.add_argument("--print-identity", action="store_true")
        pre.add_argument("--universe", type=Path)
        pre.add_argument("--agent-system-file")
        pre.add_argument("--tg1-inject", choices=("stall", "loop", "alloc"))
        pre.add_argument("--sampling-profile", choices=("deployed",), default="deployed")
        known, _ = pre.parse_known_args()
        try:
            return arm_runner.print_identity(sys.modules[__name__], adapter, known)
        except arm_adapter.ArmRefused as exc:
            sys.exit("REFUSED: " + _scrub_error(exc))
    a = _parser().parse_args()
    return arm_runner.main(sys.modules[__name__], adapter, a)


if __name__ == "__main__":
    raise SystemExit(main())
