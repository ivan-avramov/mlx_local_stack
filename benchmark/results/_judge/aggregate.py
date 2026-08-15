"""Unblind + aggregate the panel. Reads verdict_{fwd,rev}_{1,2}.json (raw judge output).

Unblinding: KEY[id] maps packet labels A/B -> model, but ONLY for the fwd packets. In the rev
packets the labels were swapped at build time, so a rev verdict of "A" means the KEY's B.
Order-consistency (does the judge pick the same MODEL in both orders?) is the panel's own
reliability measure -- the analogue of repeated sampling, and the standard control for the
position bias that is the best-documented failure mode of pairwise LLM judging.
"""
import json, glob, os, sys
from math import comb
from collections import Counter, defaultdict
D = "/tmp/m1_judge"
KEY = json.load(open(f"{D}/KEY.json"))

def load(tag, j):
    p = f"{D}/verdict_{tag}_{j}.json"
    if not os.path.exists(p): return []
    txt = open(p).read().strip()
    if txt.startswith("```"):                      # tolerate a fenced reply
        txt = txt.split("```")[1]
        txt = txt[txt.find("["):]
    return json.loads(txt)

def to_model(vid, label, swapped):
    if vid not in KEY: return None
    if swapped: label = {"A": "B", "B": "A"}.get(label, label)
    return KEY[vid][label] if label in ("A", "B") else "tie"

votes = defaultdict(dict)          # id -> {order: model_or_tie}
scores = defaultdict(lambda: defaultdict(list))   # model -> dim -> [..]
for tag, swapped in (("fwd", False), ("rev", True)):
    for j in (1, 2):
        for v in load(tag, j):
            vid = v.get("id")
            if vid not in KEY: continue
            w = v.get("winner")
            votes[vid][tag] = "tie" if w == "tie" else to_model(vid, w, swapped)
            for lbl in ("A", "B"):
                m = to_model(vid, lbl, swapped)
                for dim, val in (v.get("scores", {}).get(lbl) or {}).items():
                    if isinstance(val, (int, float)): scores[m][dim].append(val)

both = {k: v for k, v in votes.items() if "fwd" in v and "rev" in v}
consistent = {k: v["fwd"] for k, v in both.items() if v["fwd"] == v["rev"]}
flipped    = {k: v for k, v in both.items() if v["fwd"] != v["rev"]}
print(f"items judged in BOTH orders : {len(both)} / {len(KEY)}")
print(f"order-CONSISTENT            : {len(consistent)} ({len(consistent)/len(both)*100:.0f}%)"
      if both else "")
print(f"order-FLIPPED (position bias): {len(flipped)}")
for k, v in sorted(flipped.items()): print(f"    {k:<32} fwd={v['fwd']:<8} rev={v['rev']}")

c = Counter(consistent.values())
print(f"\nCONSISTENT verdicts only (the defensible set, n={len(consistent)}):")
for m, n in c.most_common(): print(f"    {m:<10} {n}")
o, d_, t = c.get("ornith", 0), c.get("distill", 0), c.get("tie", 0)
nd = o + d_
if nd:
    p = 2 * sum(comb(nd, k) for k in range(max(o, d_), nd + 1)) / 2**nd
    print(f"    sign test on {nd} decided pairs: two-sided p = {min(p,1.0):.4f}"
          f"  ({'significant' if p <= .05 else 'NOT significant'} at .05)")
print("\nMean dimension scores (all verdicts, both orders):")
dims = ["readability", "idiom", "simplicity", "structure"]
print(f"    {'model':<10}" + "".join(f"{x:>13}" for x in dims) + f"{'overall':>9}")
for m in ("ornith", "distill"):
    row, allv = [], []
    for x in dims:
        v = scores[m][x]; row.append(sum(v)/len(v) if v else float('nan')); allv += v
    print(f"    {m:<10}" + "".join(f"{r:>13.2f}" for r in row)
          + f"{(sum(allv)/len(allv) if allv else float('nan')):>9.2f}")
