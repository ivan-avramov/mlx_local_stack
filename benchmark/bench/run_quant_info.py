#!/usr/bin/env python3
"""Print the full quant numbers for local MLX snapshots, to compare candidate variants
(UD / OptiQ / QAT / uniform) at different bit-depths on a quality-vs-bits basis.

Usage:
  python -m bench.run_quant_info --scan "Qwen3.6-27B*" "gemma-4-31*" "gemma-4-26*"
  python -m bench.run_quant_info <model_dir> [<model_dir> ...]

--scan globs the HF hub cache (~/.cache/huggingface/hub/models--*) for matching repos.
Bare args are treated as snapshot dirs or HF repo ids (resolved against the hub cache).
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench import quant_info  # noqa: E402

HUB = os.path.expanduser("~/.cache/huggingface/hub")


def _snapshot_dir(repo_cache_dir: str):
    snaps = sorted(glob.glob(os.path.join(repo_cache_dir, "snapshots", "*")))
    for s in snaps:
        if os.path.exists(os.path.join(s, "config.json")):
            return s
    return None


def _resolve(spec: str):
    if os.path.isdir(spec) and os.path.exists(os.path.join(spec, "config.json")):
        return spec
    cache = os.path.join(HUB, "models--" + spec.replace("/", "--"))
    if os.path.isdir(cache):
        return _snapshot_dir(cache)
    return None


def _scan(patterns):
    out = []
    for d in sorted(glob.glob(os.path.join(HUB, "models--*"))):
        repo = os.path.basename(d)[len("models--"):]
        short = repo.split("--")[-1]
        if any(glob.fnmatch.fnmatch(short, p) for p in patterns):
            snap = _snapshot_dir(d)
            if snap:
                out.append((repo, snap))
    return out


def main():
    import fnmatch
    glob.fnmatch = fnmatch
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*", help="snapshot dirs or HF repo ids")
    ap.add_argument("--scan", nargs="+", default=None, help="HF-cache short-name globs")
    args = ap.parse_args()

    targets = []
    if args.scan:
        targets = _scan(args.scan)
    for m in args.models:
        snap = _resolve(m)
        targets.append((m, snap))

    print(f"{'model':<46}{'nom':>4}{'eff_bits':>9}{'mixed':>6}{'GB':>7}  recipe(bit:#mods)")
    print("-" * 100)
    rows = []
    for label, snap in targets:
        short = label.split("--")[-1] if "--" in label else os.path.basename(label.rstrip("/"))
        if not snap:
            print(f"{short:<46}{'—':>4}{'(not cached / no config)':>9}")
            continue
        try:
            i = quant_info.quant_info(snap)
        except Exception as e:  # noqa: BLE001
            print(f"{short:<46}  ERROR: {type(e).__name__}: {str(e)[:50]}")
            continue
        eff = f"{i['effective_bits']:.2f}" if i["effective_bits"] is not None else "—"
        recipe = " ".join(f"{b}:{n}" for b, n in i["bit_histogram"].items())
        rows.append((short, i))
        print(f"{short:<46}{str(i['nominal_bits']):>4}{eff:>9}{str(i['mixed']):>6}"
              f"{i['footprint_gb']:>7}  {recipe}")
    return rows


if __name__ == "__main__":
    main()
