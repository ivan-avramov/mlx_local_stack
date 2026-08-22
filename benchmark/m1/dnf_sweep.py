#!/usr/bin/env python3
"""D13: corpus-wide DNF/convergence sweep by quant recipe x bits, from existing rows.

Zero-GPU. Walks benchmark/results/*/<bench>.<tune>.jsonl (main rows only, never
*_samples), classifies every row, and aggregates per (model, bench, tune) with the
model's quant recipe/bits/family derived from its registry name.

Row classes:
  dnf      - row carries an error (probe-timeout / harness-recorded non-completion)
  nonconv  - converged is False (kind from nonconv_kind)
  conv     - converged is True
  unknown  - pre-schema rows with no converged field (counted, never guessed)

Output: a per-arm table and a recipe-level rollup to stdout, plus a JSON artifact
if --json PATH is given. Analysis only: no row is modified.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"

# Registry-name -> (family, recipe, bits). Order matters: first match wins.
_CLASSIFIERS = [
    (r"OptiQ-4\.5bpw-mixed$", ("optiq-mixed", 4.5)),  # allow-shorthand
    (r"OptiQ-4bit", ("optiq-mixed", 4.0)),  # allow-shorthand
    (r"static-mixed-4bit$", ("static-mixed", 4.0)),  # allow-shorthand
    (r"QAT-MLX-4bit$", ("qat", 4.0)),  # allow-shorthand
    (r"qat-6bit$", ("qat", 6.0)),  # allow-shorthand
    (r"UD-MLX-4bit$", ("ud", 4.0)),  # allow-shorthand
    (r"UD-MLX-6bit$", ("ud", 6.0)),  # allow-shorthand
    (r"MLX-8bit$", ("community-default", 8.0)),  # allow-shorthand
    (r"mlx-uniform-4bit(-kv\d)?$", ("uniform", 4.0)),  # allow-shorthand
    (r"mlx-uniform-6bit$", ("uniform", 6.0)),  # allow-shorthand
    (r"-8bit$", ("community-default", 8.0)),  # allow-shorthand
    (r"-6bit$", ("community-default", 6.0)),  # allow-shorthand
    (r"-4bit(-kv\d)?$", ("community-default", 4.0)),  # allow-shorthand
]

_FAMILIES = ["Qwen3.8-27B", "Qwen3.6-35B", "Qwen3.6-27B", "gemma-4-31", "gemma-4-26",  # allow-shorthand
             "Ornith-1.0-35B", "NVIDIA-Nemotron-3.5"]  # allow-shorthand


def classify_model(name: str) -> tuple[str, str, float | None]:
    family = next((f for f in _FAMILIES if name.lower().startswith(f.lower())), "other")
    for pat, (recipe, bits) in _CLASSIFIERS:
        if re.search(pat, name):
            return family, recipe, bits
    return family, "unknown", None


_FNAME = re.compile(r"^(?P<bench>[a-z0-9_]+?)(?:\.(?P<tune>t\d(?:\.\d+)?))?\.jsonl$")


def sweep(results_dir: Path):
    arms = []
    for model_dir in sorted(results_dir.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("_"):
            continue
        for f in sorted(model_dir.glob("*.jsonl")):
            if "_samples" in f.name:
                continue
            m = _FNAME.match(f.name)
            if not m:
                continue
            n = dnf = conv = nonconv = unknown = 0
            kinds: Counter = Counter()
            for line in f.open():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                n += 1
                if r.get("error"):
                    dnf += 1
                elif r.get("converged") is False:
                    nonconv += 1
                    kinds[r.get("nonconv_kind") or "unlabelled"] += 1
                elif r.get("converged") is True:
                    conv += 1
                else:
                    unknown += 1
            if n == 0:
                continue
            family, recipe, bits = classify_model(model_dir.name)
            arms.append({
                "model": model_dir.name, "family": family, "recipe": recipe,
                "bits": bits, "bench": m["bench"], "tune": m["tune"] or "default",
                "n": n, "dnf": dnf, "nonconv": nonconv, "conv": conv,
                "unknown": unknown, "kinds": dict(kinds),
                "fail_rate": (dnf + nonconv) / n,
            })
    return arms


def rollup(arms):
    groups = defaultdict(lambda: {"n": 0, "dnf": 0, "nonconv": 0, "arms": 0,
                                  "kinds": Counter()})
    for a in arms:
        g = groups[(a["recipe"], a["bits"])]
        g["n"] += a["n"]; g["dnf"] += a["dnf"]; g["nonconv"] += a["nonconv"]
        g["arms"] += 1; g["kinds"].update(a["kinds"])
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=RESULTS)
    ap.add_argument("--json", type=Path, default=None,
                    help="also write the per-arm records to this path")
    ap.add_argument("--min-n", type=int, default=5,
                    help="hide arms smaller than this from the table (still rolled up)")
    args = ap.parse_args()

    arms = sweep(args.results)

    print(f"{'model':52s} {'bench':14s} {'tune':7s} {'n':>4s} {'dnf':>4s} "
          f"{'nonconv':>7s} {'unk':>4s} {'fail%':>6s}  kinds")
    for a in sorted(arms, key=lambda a: (a["recipe"], a["bits"] or 0, a["model"],
                                         a["bench"], a["tune"])):
        if a["n"] < args.min_n:
            continue
        ks = ",".join(f"{k}:{v}" for k, v in sorted(a["kinds"].items())) or "-"
        print(f"{a['model']:52s} {a['bench']:14s} {a['tune']:7s} {a['n']:4d} "
              f"{a['dnf']:4d} {a['nonconv']:7d} {a['unknown']:4d} "
              f"{a['fail_rate']*100:5.1f}%  {ks}")

    print("\n== rollup by (recipe, bits) — pooled across families/benches/tunes; "
          "a CROSS-CHECK, not a matched comparison ==")
    print(f"{'recipe':18s} {'bits':>5s} {'arms':>5s} {'rows':>6s} {'dnf%':>6s} "
          f"{'nonconv%':>8s}  kinds")
    for (recipe, bits), g in sorted(rollup(arms).items(),
                                    key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        ks = ",".join(f"{k}:{v}" for k, v in g["kinds"].most_common(4)) or "-"
        print(f"{recipe:18s} {str(bits):>5s} {g['arms']:5d} {g['n']:6d} "
              f"{g['dnf']/g['n']*100:5.1f}% {g['nonconv']/g['n']*100:7.1f}%  {ks}")

    print("\nNOTE: pooled rates mix families, benches, tunes and budgets — use the "
          "per-arm table for any claim; the rollup only flags where to look. "
          "unknown = pre-schema rows with no converged field.")

    if args.json:
        args.json.write_text(json.dumps(arms, indent=1))
        print(f"\nper-arm records -> {args.json}")


if __name__ == "__main__":
    main()
