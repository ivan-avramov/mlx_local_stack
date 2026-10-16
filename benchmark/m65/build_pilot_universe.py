#!/usr/bin/env python3
"""M65 step 1: freeze the headroom-pilot universe — every polyglot Python + Go item outside the tg1 universe.

Same format and builder as `m62/universe_preflight.py` (V1b; that module is probe identity and stays untouched).
`go/counter` is excluded (C145, invalid item). An item whose reference solution does not pass is reported and
left out (an invalid item, never a model-based selection). No model calls.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench import paths  # noqa: E402
from bench.token_turn_gate import TransportAbort  # noqa: E402
from m62 import universe_preflight as up  # noqa: E402

HERE = Path(__file__).resolve().parent


def candidates(corpus, tg1):
    ids = []
    for lang in ("python", "go"):
        for d in sorted((Path(corpus) / lang / "exercises/practice").iterdir()):
            item = f"{lang}/{d.name}"
            if d.is_dir() and item not in tg1 and item != "go/counter":
                ids.append(item)
    return ids


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE / "pilot_universe.json")
    ap.add_argument("--tg1", type=Path, default=HERE.parent / "m62/universe.json")
    ap.add_argument("--corpus", type=Path)
    a = ap.parse_args(argv)
    from bench.opencode_common import _polyglot_root

    corpus = a.corpus or _polyglot_root()
    tg1, _ = up.load(a.tg1)
    ids = candidates(corpus, tg1["items"])
    private = paths.stack_workdir().resolve() / "m65/universe-private"
    private.mkdir(parents=True, exist_ok=True)
    doc, failed = {"grader_version": up.sg.VERSION, "items": {}}, {}
    for item in ids:
        try:
            one = up.build({"entries": [{"id": item}]}, corpus, private, expected_count=1)
            doc["items"].update(one["items"])
            print(f"ok   {item}: {len(one['items'][item]['leaves'])} leaves", flush=True)
        except TransportAbort as exc:
            failed[item] = str(exc)
            print(f"FAIL {item}: {exc}", flush=True)
    doc = json.loads(json.dumps(doc))
    up.freeze(a.out, doc)
    print(f"{len(doc['items'])} of {len(ids)} items frozen; excluded {sorted(failed)}; sha256={up.load(a.out)[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
