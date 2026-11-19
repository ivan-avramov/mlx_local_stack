"""S24-P9 / B4b-1 acceptance 3: the stage-3b (A8 tg2) sizing report, generated from the committed pilot pair.
Run from benchmark/: ../.venv-bench/bin/python ../docs/reviews/m76-s3b-sizing/sizing.py > ../docs/reviews/m76-s3b-sizing/SIZING.md"""
import json
from datetime import datetime
from pathlib import Path

from bench import p426_freeze as fz

R = Path("results/m76/wave2.tg2")
BUDGETS_H = {"M76 §9 / B7.1 joint plan": 12.0, "M65 v5 (M55 means)": 18.5}   # per arm (S24-P9)
P223_P95_S, P223_MAX_S = 19.3 * 60, fz.TG2_MAX_ITEM_S                         # the heavy-tail allowance (S24-P9; P223)
IDLE_GAP_S = 600                                                               # the sequencer's idle gap before a leg
amend = json.loads((R / "run" / "amendment.json").read_text())
walls, legs = {}, {}
for arm in fz.TG2_PAIR:
    root = R / f"tg2-m76-{arm}-pilot.a1"
    walls[arm] = {lang: v[0] for lang, v in fz.pilot_walls_by_lang(root).items()}
    leg = json.loads((root / "leg.json").read_text())
    t = lambda k: datetime.strptime(leg[k], "%Y-%m-%dT%H:%M:%SZ")
    legs[arm] = (t("ended") - t("started")).total_seconds()
n_lang = {leg: fz.TG2_ITEM_COUNT[leg] for leg in ("s1", "s2", "reload")}
langs = fz.TG2_LANGS
items = {"screen (10 / language, k = 1, C168)": 10 * len(langs), "decider (s1 + s2 + reload)": sum(n_lang.values()) * len(langs)}
n_legs = {"screen (10 / language, k = 1, C168)": 1, "decider (s1 + s2 + reload)": 3}
overhead = {arm: legs[arm] - sum(walls[arm].values()) for arm in walls}
print("# M76 stage 3b (A8 tg2) — sizing report (generated)\n")
print(f"Source: `benchmark/results/m76/wave2.tg2/` (pilot pair, both legs VALID, pilot gate PASS; amendment "
      f"`{amend['v8_base_sha256'][:8]}…` v8). Generator: `docs/reviews/m76-s3b-sizing/sizing.py`. Per-item walls include the "
      "endpoint agent's per-launch overhead (S27-P5); compare them within this pair only.\n")
print("## Pilot (one item per language per arm)\n")
print("| language | " + " | ".join(f"{a} wall (s)" for a in walls) + " |\n|---|" + "---|" * len(walls))
for lang in langs:
    print(f"| {lang} | " + " | ".join(f"{walls[a][lang]:.0f}" for a in walls) + " |")
print("| **sum** | " + " | ".join(f"{sum(walls[a].values()):.0f}" for a in walls) + " |")
print("| leg elapsed (s) | " + " | ".join(f"{legs[a]:.0f}" for a in walls) + " |")
print("| per-leg overhead (s) | " + " | ".join(f"{overhead[a]:.0f}" for a in walls) + " |\n")
allw = [w for a in walls for w in walls[a].values()]
mean_w, max_w = sum(allw) / len(allw), max(allw)
ov = max(overhead.values())
print(f"Item wall over both arms: mean {mean_w:.0f} s, max {max_w:.0f} s (n = {len(allw)}). Amendment floors: "
      + ", ".join(f"w_{lang} {amend[f'w_{lang}_s']:.0f} s" for lang in langs) + ".\n")
print("## Projection per arm (hours)\n")
print("Lower bound = items × mean wall; max-based = items × max pilot wall; tail = mean-based + 5 % of items at the P223 p95 "
      f"({P223_P95_S / 60:.1f} min) + one item at the P223 max ({P223_MAX_S / 60:.0f} min). Each adds per leg "
      f"{ov:.0f} s overhead (the larger measured) + a {IDLE_GAP_S} s idle gap.\n")
print("| tier | items / arm | lower (mean) | max-based | with tail | " + " | ".join(f"budget {k}" for k in BUDGETS_H) + " |")
print("|---|---|---|---|---|" + "---|" * len(BUDGETS_H))
for tier, n in items.items():
    fixed = n_legs[tier] * (ov + IDLE_GAP_S)
    lo, mx = n * mean_w + fixed, n * max_w + fixed
    tail = lo + 0.05 * n * (P223_P95_S - mean_w) + (P223_MAX_S - mean_w)
    print(f"| {tier} | {n} | {lo / 3600:.1f} | {mx / 3600:.1f} | {tail / 3600:.1f} | "
          + " | ".join(f"{b:.1f}" for b in BUDGETS_H.values()) + " |")
cap = sum(amend["leg_deadline_s"][k] for k in ("s1", "s2", "reload"))
print(f"\nThe amendment's leg deadlines (a cap, not an estimate): s1 {amend['leg_deadline_s']['s1'] / 3600:.2f} h, s2 "
      f"{amend['leg_deadline_s']['s2'] / 3600:.2f} h, reload {amend['leg_deadline_s']['reload'] / 3600:.2f} h — "
      f"{cap / 3600:.1f} h per arm at most.\n")
print("Caveats: four pilot items per arm (one per language) are a small sample of a heavy-tailed distribution; the tail column "
      "carries the P223 allowance for that. Pilot walls N16 vs X are one non-order-balanced pair: no speed claim (S27-P5).")
