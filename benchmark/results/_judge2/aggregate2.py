"""Unblind + aggregate the 3-role x 2-order panel.

Reads verdict_{holistic,maintainability,architecture}_{fwd,rev}.json.

Unblinding: KEY[id] maps packet label A/B -> model for the FWD packets. REV packets had the
labels swapped at build time, so a rev "A" means the KEY's B.

Reported, each tied to a documented bias (MT-Bench: position 10-15pp winrate swing, verbosity
15-30pp, self-enhancement 10-25%):
  * per-JUDGE order consistency        -> position bias, per role
  * panel majority over consistent     -> the defensible verdict
  * pairwise inter-JUDGE agreement     -> whether the roles see the same thing
  * Krippendorff alpha (ordinal)       -> chance-corrected inter-rater reliability
  * preference vs LENGTH correlation   -> verbosity bias
"""
import json, os, itertools
from math import comb
from collections import defaultdict, Counter

D = os.path.dirname(os.path.abspath(__file__))
KEY = json.load(open(f"{D}/KEY.json"))
ROLES = ["holistic", "maintainability", "architecture"]


def load(role, tag):
    p = f"{D}/verdict_{role}_{tag}.json"
    if not os.path.exists(p):
        return None
    txt = open(p).read().strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1]
        txt = txt[txt.find("["):]
    return json.loads(txt)


def to_model(vid, label, swapped):
    if label == "tie":
        return "tie"
    if swapped:
        label = {"A": "B", "B": "A"}[label]
    return KEY[vid][label]


# role -> id -> {tag: model}
votes = defaultdict(lambda: defaultdict(dict))
conf = defaultdict(lambda: defaultdict(dict))
dimscore = defaultdict(lambda: defaultdict(list))   # model -> dim -> values
missing = []
for role in ROLES:
    for tag, sw in (("fwd", False), ("rev", True)):
        rows = load(role, tag)
        if rows is None:
            missing.append(f"{role}_{tag}")
            continue
        for v in rows:
            vid = v.get("id")
            if vid not in KEY:
                continue
            votes[role][vid][tag] = to_model(vid, v.get("winner"), sw)
            conf[role][vid][tag] = v.get("confidence")
            for lbl in ("A", "B"):
                m = to_model(vid, lbl, sw)
                for dim, val in (v.get("scores", {}).get(lbl) or {}).items():
                    if isinstance(val, (int, float)):
                        dimscore[m][dim].append(val)

if missing:
    print(f"!! MISSING verdict files (panel incomplete): {missing}\n")

print("=== per-JUDGE order consistency (position-bias control) ===")
consistent = {}          # role -> id -> model
for role in ROLES:
    both = {k: v for k, v in votes[role].items() if "fwd" in v and "rev" in v}
    if not both:
        continue
    ok = {k: v["fwd"] for k, v in both.items() if v["fwd"] == v["rev"]}
    consistent[role] = ok
    hard = sum(1 for k, v in both.items() if v["fwd"] != v["rev"] and "tie" not in v.values())
    print(f"  {role:<17} {len(ok)}/{len(both)} ({len(ok)/len(both)*100:.0f}%)  "
          f"hard reversals {hard}")

print("\n=== PANEL verdict — majority over each judge's order-CONSISTENT calls ===")
tally = Counter()
per_item = {}
for vid in KEY:
    picks = [consistent[r][vid] for r in ROLES if r in consistent and vid in consistent[r]]
    if not picks:
        continue
    c = Counter(picks)
    top, n = c.most_common(1)[0]
    # a majority needs > half of the judges that had a usable call on this item
    win = top if n > len(picks) / 2 else "no-majority"
    per_item[vid] = (win, picks)
    tally[win] += 1
for k, v in tally.most_common():
    print(f"  {k:<14} {v}")
o, d_ = tally.get("ornith", 0), tally.get("distill", 0)
nd = o + d_
if nd:
    p = 2 * sum(comb(nd, k) for k in range(max(o, d_), nd + 1)) / 2 ** nd
    print(f"  sign test on {nd} decided items: two-sided p = {min(p,1.0):.4f}"
          f"  ({'SIGNIFICANT' if p <= .05 else 'not significant'} at .05)")

print("\n=== inter-JUDGE agreement (do the roles see the same thing?) ===")
num = {"ornith": 1, "tie": 0, "distill": -1}
for r1, r2 in itertools.combinations(ROLES, 2):
    if r1 not in consistent or r2 not in consistent:
        continue
    shared = set(consistent[r1]) & set(consistent[r2])
    if not shared:
        continue
    agree = sum(1 for k in shared if consistent[r1][k] == consistent[r2][k])
    print(f"  {r1[:6]:<7} vs {r2[:6]:<7} {agree}/{len(shared)} ({agree/len(shared)*100:.0f}%)")

# Krippendorff alpha, ordinal, over the consistent calls (raters = roles, units = items)
data = {r: {k: num[v] for k, v in consistent.get(r, {}).items()} for r in ROLES}
units = [u for u in KEY if sum(1 for r in ROLES if u in data[r]) >= 2]
if units:
    vals = [-1, 0, 1]
    def d2(a, b):   # ordinal metric on a 3-point scale ~ squared difference
        return (a - b) ** 2
    Do = Dn = 0.0
    for u in units:
        ratings = [data[r][u] for r in ROLES if u in data[r]]
        m = len(ratings)
        if m < 2:
            continue
        Do += sum(d2(a, b) for a in ratings for b in ratings) / (m - 1)
    allr = [data[r][u] for u in units for r in ROLES if u in data[r]]
    n_tot = len(allr)
    Dn = sum(d2(a, b) for a in allr for b in allr) / (n_tot - 1)
    alpha = 1 - (Do / Dn) * ((n_tot - 1) / 1) / (n_tot - 1) if Dn else float("nan")
    alpha = 1 - (Do / n_tot) / (Dn / n_tot) if Dn else float("nan")
    print(f"  Krippendorff alpha (ordinal, {len(units)} units, {len(ROLES)} raters) = {alpha:.3f}")
    print("    (1.0 perfect, 0.0 chance, <0 worse than chance; >0.667 is the usual "
          "minimum for tentative conclusions)")

print("\n=== per-dimension means (all judgments, both orders) ===")
alldims = sorted({d for m in dimscore for d in dimscore[m]})
print(f"  {'dimension':<26}{'ornith':>9}{'distill':>10}{'delta':>8}")
for dim in alldims:
    a = dimscore["ornith"].get(dim, [])
    b = dimscore["distill"].get(dim, [])
    if not a or not b:
        continue
    ma, mb = sum(a)/len(a), sum(b)/len(b)
    print(f"  {dim:<26}{ma:>9.2f}{mb:>10.2f}{mb-ma:>+8.2f}")

print("\n=== verbosity-bias check ===")
lo = [KEY[k]["len_ornith"] for k in KEY]
ld = [KEY[k]["len_distill"] for k in KEY]
print(f"  mean solution chars: ornith {sum(lo)/len(lo):.0f}  distill {sum(ld)/len(ld):.0f}")
wins_longer = wins_shorter = 0
for vid, (win, _) in per_item.items():
    if win not in ("ornith", "distill"):
        continue
    longer = "ornith" if KEY[vid]["len_ornith"] > KEY[vid]["len_distill"] else "distill"
    if win == longer:
        wins_longer += 1
    else:
        wins_shorter += 1
tot = wins_longer + wins_shorter
if tot:
    print(f"  panel picked the LONGER solution in {wins_longer}/{tot} decided items "
          f"({wins_longer/tot*100:.0f}%) — 50% means no verbosity bias")
