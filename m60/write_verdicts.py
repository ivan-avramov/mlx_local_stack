"""Write <packet>.verdict.json files from judge text output: stdin = one JSON object per line
{"packet": "pNNNN.md", "choice": "A"|"B"|"tie", "rationale": "..."}; argv[1] = the part-list file
(packet paths). Refuses to overwrite an existing verdict; reports written / skipped / unknown."""
import json, sys, os
paths = {os.path.basename(p.strip()): p.strip() for p in open(sys.argv[1]) if p.strip()}
written = skipped = bad = 0
seen = set()
for line in sys.stdin:
    line = line.strip().strip("`")
    if not line or not line.startswith("{"):
        continue
    try:
        o = json.loads(line)
    except json.JSONDecodeError:
        bad += 1; print("BAD JSON:", line[:80]); continue
    name = o.get("packet"); choice = o.get("choice"); rat = (o.get("rationale") or "").strip()
    if name not in paths or choice not in ("A", "B", "tie") or not rat:
        bad += 1; print("BAD ROW:", line[:80]); continue
    out = paths[name][:-3] + ".verdict.json" if paths[name].endswith(".md") else paths[name] + ".verdict.json"
    if os.path.exists(out):
        skipped += 1; continue
    with open(out, "w") as f:
        json.dump({"choice": choice, "rationale": rat}, f)
    written += 1; seen.add(name)
missing = sorted(set(paths) - seen - {n for n in paths if os.path.exists(paths[n][:-3] + ".verdict.json")})
print(f"written={written} skipped_existing={skipped} bad={bad} missing={missing}")
