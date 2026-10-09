"""P205 scoring exactly per PREREG.md."""
import json, random, re, itertools, statistics as st
from pathlib import Path
D = Path(__file__).parent; man = [json.loads(l) for l in open(D / "manifest.private.jsonl")]
def parse(p):
    v = Path(p).with_suffix(".verdict.json")
    if not v.exists(): return None
    t = v.read_text(); m = re.search(r'"choice"\s*:\s*"(A|B|tie)"', t, re.I)
    return None if not m else {"a": "A", "b": "B"}.get(m.group(1).lower(), "tie")
def arm(row, c):  # translate shown label -> arm
    if c in (None, "tie"): return c
    return row["shown_A_is_arm"] if c == "A" else ("B" if row["shown_A_is_arm"] == "A" else "A")
for kind in ("code", "msg"):
    rows = [r for r in man if r["kind"] == kind]; judges = sorted({r["judge"] for r in rows})
    per = {}; missing = 0; flips = {j: [0, 0] for j in judges}
    for (pid, j), grp in itertools.groupby(sorted(rows, key=lambda r: (r["pair_id"], r["judge"])), key=lambda r: (r["pair_id"], r["judge"])):
        g = {r["order"]: arm(r, parse(r["path"])) for r in grp}; missing += sum(v is None for v in g.values())
        a, b = g.get("AB"), g.get("BA"); flips[j][1] += 1; flips[j][0] += (a != b)
        per[(pid, j)] = a if (a is not None and a == b) else "tie"
    pairs = sorted({r["pair_id"] for r in rows}); item = {r["pair_id"]: r["item"] for r in rows}; model = {r["pair_id"]: r["model"] for r in rows}
    panel = {}
    for p in pairs:
        vs = [per[(p, j)] for j in judges]; c = {v: vs.count(v) for v in set(vs)}; best = max(c.values()); w = [k for k in c if c[k] == best]
        panel[p] = w[0] if len(w) == 1 and best >= 2 else "tie"
    sc = {p: 1.0 if panel[p] == "A" else 0.0 if panel[p] == "B" else 0.5 for p in pairs}
    share = st.mean(sc.values()); items = sorted(set(item.values())); rng = random.Random(205); bs = []
    for _ in range(20000):
        v = []
        for i in rng.choices(items, k=len(items)):
            ps = [sc[p] for p in pairs if item[p] == i]; v += rng.choices(ps, k=len(ps))
        bs.append(st.mean(v))
    bs.sort(); lo, hi = bs[500], bs[19499]
    reading = "extra tokens buy quality" if lo > 0.5 else "brevity better" if hi < 0.5 else "no detectable difference"
    print(f"== {kind}: share preferring arm A (plain v2) = {share:.3f} [{lo:.3f}, {hi:.3f}] -> {reading}; missing/unparseable {missing}")
    print("   panel A/B/tie:", sum(v == 'A' for v in panel.values()), sum(v == 'B' for v in panel.values()), sum(v == 'tie' for v in panel.values()))
    for m in sorted(set(model.values())):
        ps = [p for p in pairs if model[p] == m]; print(f"   {m}: share A {st.mean(sc[p] for p in ps):.3f} (n={len(ps)}) A/B/tie {[sum(panel[p]==x for p in ps) for x in ('A','B','tie')]}")
    for j in judges:
        vs = [per[(p, j)] for p in pairs]; print(f"   judge {j}: A {vs.count('A')} B {vs.count('B')} tie {vs.count('tie')} | order-flip {flips[j][0]}/{flips[j][1]}")
    for j1, j2 in itertools.combinations(judges, 2):
        print(f"   agreement {j1} vs {j2}: {sum(per[(p,j1)]==per[(p,j2)] for p in pairs)}/{len(pairs)}")
