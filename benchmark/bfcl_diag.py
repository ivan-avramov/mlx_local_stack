"""Quick BFCL result diagnostic: per-category n / accuracy / thinking-truncation / completion sizes.

Usage: python benchmark/bfcl_diag.py <model_name> [runroot]
Reads <runroot>/result/<model>/non_live/BFCL_v4_<cat>_result.json and the matching score files.
"""
import glob
import json
import os
import sys

model = sys.argv[1]
runroot = sys.argv[2] if len(sys.argv) > 2 else "benchmark/bfcl_runs"
mdir = model.replace("/", "_")

for rf in sorted(glob.glob(f"{runroot}/result/{mdir}/non_live/*_result.json")):
    cat = os.path.basename(rf).replace("BFCL_v4_", "").replace("_result.json", "")
    res = [json.loads(l) for l in open(rf) if l.strip()]
    trunc = [e["id"] for e in res
             if "<think>" in str(e.get("result", "")) and "</think>" not in str(e.get("result", ""))]
    lens = sorted(len(str(e.get("result", ""))) for e in res)
    med = lens[len(lens) // 2] if lens else 0
    print(f"{cat}: n={len(res)} truncated_in_think={len(trunc)} median_chars={med} max_chars={lens[-1] if lens else 0}")
    if trunc:
        print(f"   still-truncated ids: {trunc}")
