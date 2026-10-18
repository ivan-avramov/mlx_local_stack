#!/usr/bin/env python3
"""tg1 probe (M62/C147): token/turn-gated, seeded opencode 2.x sessions. GENERATION ONLY (P311-lite).

Imports only the generation core and the tg1 runner. The rows it writes carry no web-audit or answer-key-contact
fields; `benchmark/bench/tg1_score.py` derives those post hoc from the stored transcripts. `probe_code_sha256` is
the static import closure of this file (`bench/identity_closure.py`), so a scoring fix never changes it.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benchmark"))
from bench import opencode_v2_core as _core
from bench import tg1_runner

_core.bind(globals())
REPO = Path(__file__).resolve().parent.parent


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
    ap.add_argument("--scaffold", choices=["opencode-v2-web-tg1"], default="opencode-v2-web-tg1")
    ap.add_argument("--universe", type=Path)
    ap.add_argument("--expect-items")
    ap.add_argument("--agent-system-file")
    ap.add_argument("--lang", choices=["python", "go", "rust", "java", "javascript"], default="python")
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
                    "required, never defaulted (a stored reference arm pairs only on the same date)")
    ap.add_argument("--attempt", type=int, default=1,
                    help="attempt number of each slot in this invocation (worker receipt attempt id; the chain sets it)")
    ap.add_argument("--attempt-rerun-index", type=int, default=0,
                    help="same-slot re-run index of this invocation's attempt ids (the chain sets it)")
    ap.add_argument("--invocation-nonce", type=_nonce,
                    help="P384: the chain's per-invocation nonce, written into the manifest as runtime.invocation_nonce")
    ap.add_argument("--print-identity", action="store_true", help="print the probe identity JSON and exit")
    # Legacy v2 flags: parsed only so that `tg1_runner.main` refuses them with its own message.
    for flag, kind in (("--extra-deny-file", Path), ("--rerun-of", str), ("--rerun-index", int), ("--tick-s", int),
                       ("--first-write-tokens", int), ("--hard-ceiling-s", int), ("--stall-ticks", int),
                       ("--loop-repeats", int), ("--poll-s", float)):
        ap.add_argument(flag, type=kind, help=argparse.SUPPRESS)
    return ap


def _main():
    if _print_identity_requested():
        # C147 §3: read-only provenance identity; no router, worker or model is touched.
        pre = argparse.ArgumentParser(allow_abbrev=False)
        pre.add_argument("--print-identity", action="store_true")
        pre.add_argument("--universe", type=Path)
        pre.add_argument("--agent-system-file")
        pre.add_argument("--tg1-inject", choices=("stall", "loop", "alloc"))
        pre.add_argument("--sampling-profile", choices=("deployed",), default="deployed")
        known, _ = pre.parse_known_args()
        return tg1_runner.print_identity(sys.modules[__name__], known)
    a = _parser().parse_args()
    return tg1_runner.main(sys.modules[__name__], a)


if __name__ == "__main__":
    raise SystemExit(main())
