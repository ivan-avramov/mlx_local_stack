"""M27 paired quality OFAT: Ornith-1.0-35B-mlx-uniform-4bit humanevalplus mtpon vs mtpoff.

Same arithmetic as M6b/M6d: per-item score vectors via bench.compare._per_item (graded `items`
for acc, `strict_items` for acc_strict@budget), paired delta + two-stage bootstrap CI + TOST
±5pp via m1.suffix_ofat.accuracy. `compare` itself refuses across draft state by design; this
is the OFAT path. Run from the benchmark dir with PYTHONPATH=.
"""
import json, sys
from pathlib import Path
from bench import compare
from m1 import suffix_ofat

MODEL = "Ornith-1.0-35B-mlx-uniform-4bit"
RES = Path("results") / MODEL
out = {}
for strict in (False, True):
    on = compare._per_item(json.load(open(RES / "humanevalplus.mtpon.score.json")), strict=strict)
    off = compare._per_item(json.load(open(RES / "humanevalplus.mtpoff.score.json")), strict=strict)
    shared = sorted(set(on) & set(off))
    assert len(shared) == 164 and len(on) == len(off) == 164, (len(on), len(off), len(shared))
    res = suffix_ofat.accuracy(on, off, iters=10000, seed=0, margin=0.05)
    res["acc_on"] = sum(v[0] for v in on.values()) / len(on)
    res["acc_off"] = sum(v[0] for v in off.values()) / len(off)
    disc = [(i, on[i][0], off[i][0]) for i in shared if on[i][0] != off[i][0]]
    res["discordant_items"] = disc
    res["on_wins"] = sum(1 for _, a, b in disc if a > b)
    res["off_wins"] = sum(1 for _, a, b in disc if a < b)
    out["acc_strict" if strict else "acc"] = res
json.dump(out, open(sys.argv[1], "w"), indent=2, default=str)
for k, r in out.items():
    print(f"{k}: ON {r['acc_on']:.4f} OFF {r['acc_off']:.4f} delta {r.get('delta')} "
          f"CI [{r.get('lo')}, {r.get('hi')}] discordant {r['on_wins']}:{r['off_wins']} "
          f"verdict={r.get('verdict')} p_d={r.get('p_d')}")
