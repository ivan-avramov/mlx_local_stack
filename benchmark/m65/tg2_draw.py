#!/usr/bin/env python3
"""M65 tg2 nested seeded draw (spec §Draw rule, T11 / T19 / T26): per language one permutation
`random.Random(6501).sample(sorted(valid), N_actual)` frozen as canonical JSON with a sha256 sidecar before any tg2
model run. Tiers are NESTED prefixes: screen = first 10 per language, decider = first 20 (a later resolution increase
extends the same prefix, never a redraw). A language with N_actual < 20 is flagged for operator acknowledgement and
is not decided here."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.token_turn_gate import TransportAbort  # noqa: E402

SEED = 6501
TIERS = {"screen": 10, "decider": 20}


def make_draw(universe, universe_sha256):
    languages, flagged = {}, {}
    for lang, entry in sorted(universe["languages"].items()):
        valid = sorted(entry["valid"])
        permutation = random.Random(SEED).sample(valid, len(valid))
        languages[lang] = dict(N_actual=len(valid), permutation=permutation,
                               **{tier: permutation[:size] for tier, size in TIERS.items()})
        if len(valid) < TIERS["decider"]:
            flagged[lang] = len(valid)
    return dict(seed=SEED, tiers=TIERS, universe_sha256=universe_sha256, languages=languages,
                needs_operator_acknowledgement=flagged)


def freeze(out, draw):
    out = Path(out)
    side = out.with_suffix(out.suffix + ".sha256")
    if out.exists() or side.exists():
        raise TransportAbort("frozen tg2 draw already exists (refusing to overwrite)")
    raw = (json.dumps(draw, sort_keys=True, indent=1) + "\n").encode()
    from bench import proc_guard as pg
    pg.atomic_write(out, raw)
    pg.atomic_write(side, (hashlib.sha256(raw).hexdigest() + "\n").encode())
    return hashlib.sha256(raw).hexdigest()


def load(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if path.with_suffix(path.suffix + ".sha256").read_text().strip() != sha:
            raise ValueError("sha256 differs")
        doc = json.loads(raw)
        if doc["seed"] != SEED or not isinstance(doc["languages"], dict):
            raise ValueError("seed / shape")
        return doc, sha
    except (OSError, ValueError, KeyError) as exc:
        raise TransportAbort("invalid frozen tg2 draw: " + str(exc)) from exc


def tier_items(draw, lang, tier):
    """The items of one tier (a nested prefix of the permutation); refuses an unknown tier or a broken prefix."""
    if tier not in TIERS:
        raise TransportAbort("unknown tg2 tier %r" % tier)
    entry = draw["languages"][lang]
    items = entry[tier]
    if items != entry["permutation"][:len(items)] or len(items) != min(TIERS[tier], entry["N_actual"]):
        raise TransportAbort("tg2 %s tier of %s is not the frozen permutation prefix" % (tier, lang))
    return items


def main(argv=None):
    from importlib import util
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--universe", type=Path, default=Path(__file__).with_name("tg2_universe.json"))
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("tg2_draw.json"))
    args = ap.parse_args(argv)
    spec = util.spec_from_file_location("tg2_universe", Path(__file__).with_name("tg2_universe.py"))
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    universe, sha = mod.load(args.universe)
    draw = make_draw(universe, sha)
    print("draw sha256", freeze(args.out, draw))
    if draw["needs_operator_acknowledgement"]:
        print("OPERATOR ACKNOWLEDGEMENT NEEDED (N_actual < 20):", draw["needs_operator_acknowledgement"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
