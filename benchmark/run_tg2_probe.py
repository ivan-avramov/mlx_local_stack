#!/usr/bin/env python3
"""tg2 probe (M76 B4b-1 / M65 step 3): token/turn-gated, seeded opencode 2.x sessions over the frozen tg2 universe (Rust /
JavaScript / Java / C++), graded in the pinned tg2-grader image. GENERATION ONLY (P311-lite), as `run_tg1_probe.py`: the same
argv and binding, `--scaffold opencode-v2-web-tg2`, `--lang rust|javascript|java|cpp`, `--tg2-inject stall|loop|alloc` (out
under `$STACK_WORKDIR/m65/inject/`) and `--universe` defaulting to `benchmark/m65/tg2_universe.json`. `probe_code_sha256` is the
import closure (read, not executed) of this file plus the tg2 generation data."""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benchmark"))
from bench import opencode_v2_core as _core
from bench import tg2_runner

_INJECT_KINDS = tg2_runner.rc.ALL_INJECT_KINDS      # S27 X1: the one shared kind list (through the runner: entry imports)

_core.bind(globals())
REPO = Path(__file__).resolve().parent.parent
LANGS = ("rust", "javascript", "java", "cpp")
SCAFFOLDS = ["opencode-v2-web-tg2"]
DEFAULT_UNIVERSE = REPO / "benchmark/m65/tg2_universe.json"


def _sigterm_exit(signum, frame):
    """SIGTERM -> SystemExit(143) so `finally` blocks run (scratch removal, client kill)."""
    raise SystemExit(143)


def _install_sigterm_exit():
    signal.signal(signal.SIGTERM, _sigterm_exit)


def main():
    _install_sigterm_exit()
    try:
        return _main()
    except provenance.ServedConfigError as e:
        sys.exit("REFUSED: " + _scrub_error(e))


def _print_identity_requested():
    return "--print-identity" in sys.argv[1:]


def _nonce(value):
    """P384: the chain-issued per-invocation binding nonce: 64 lowercase hex (anything else is refused)."""
    import re
    if not re.fullmatch("[0-9a-f]{64}", value):
        raise argparse.ArgumentTypeError("--invocation-nonce must be 64 lowercase hex characters")
    return value


def _parser():
    ap = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    ap.add_argument("--model", required=True)
    ap.add_argument("--items", required=True)
    ap.add_argument("--seed-base", type=int, required=True)
    ap.add_argument("--scaffold", choices=SCAFFOLDS, default=SCAFFOLDS[0])
    ap.add_argument("--universe", type=Path, help="default: the committed tg2 universe (benchmark/m65/tg2_universe.json)")
    ap.add_argument("--expect-items")
    ap.add_argument("--agent-system-file")
    ap.add_argument("--lang", choices=list(LANGS), default="rust")
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--chain-total", type=int, default=0)
    ap.add_argument("--a4-v2-receipt")
    ap.add_argument("--allow-version-drift", action="store_true")
    ap.add_argument("--tg2-inject", dest="tg1_inject", choices=_INJECT_KINDS,
                    help="an injected positive (one item; --out under $STACK_WORKDIR/m65/inject/)")
    ap.add_argument("--cancel-file")
    ap.add_argument("--manifest-ack")
    ap.add_argument("--sampling-profile", choices=("deployed",))
    ap.add_argument("--frozen-prompt-date", help="P364: the date opencode shows the model ('Www Mmm DD YYYY'); "
                    "required, never defaulted")
    ap.add_argument("--attempt", type=int, default=1,
                    help="attempt number of each slot in this invocation (worker receipt attempt id; the chain sets it)")
    ap.add_argument("--attempt-rerun-index", type=int, default=0,
                    help="same-slot re-run index of this invocation's attempt ids (the chain sets it)")
    ap.add_argument("--invocation-nonce", type=_nonce,
                    help="P384: the chain's per-invocation nonce, written into the manifest as runtime.invocation_nonce")
    ap.add_argument("--evidence", choices=("p426",),
                    help="B2: the evidence policy (default: the tg2 one); p426 = the item barrier on, the transport-cause stamp "
                    "and the request evidence in the abort manifest")
    ap.add_argument("--inject-stall-item", metavar="LANG/ITEM",
                    help="B2 rehearsal (with --evidence p426): the one item that runs with the lowered stall limit")
    ap.add_argument("--inject-stall-s", type=int, metavar="SECONDS",
                    help="B2 rehearsal: the lowered stall (client silence) limit of --inject-stall-item, in seconds")
    ap.add_argument("--print-identity", action="store_true", help="print the probe identity JSON and exit")
    # Legacy v2 flags: parsed only so that the core refuses them with its own message.
    for flag, kind in (("--extra-deny-file", Path), ("--rerun-of", str), ("--rerun-index", int), ("--tick-s", int),
                       ("--first-write-tokens", int), ("--hard-ceiling-s", int), ("--stall-ticks", int),
                       ("--loop-repeats", int), ("--poll-s", float)):
        ap.add_argument(flag, type=kind, help=argparse.SUPPRESS)
    return ap


def _main():
    if _print_identity_requested():
        pre = argparse.ArgumentParser(allow_abbrev=False)
        pre.add_argument("--print-identity", action="store_true")
        pre.add_argument("--universe", type=Path)
        pre.add_argument("--agent-system-file")
        pre.add_argument("--tg2-inject", dest="tg1_inject", choices=_INJECT_KINDS)
        pre.add_argument("--sampling-profile", choices=("deployed",), default="deployed")
        known, _ = pre.parse_known_args()
        return tg2_runner.print_identity(sys.modules[__name__], known)
    a = _parser().parse_args()
    return tg2_runner.main(sys.modules[__name__], a)


if __name__ == "__main__":
    raise SystemExit(main())
