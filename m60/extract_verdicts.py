"""Extract verdict JSON objects from a judge subagent's transcript JSONL (argv[1]) and print them as
{"packet","choice","rationale"} lines for write_verdicts.py. Accepts both the bare one-object-per-line
form and the 'pNNNN.md: FAILED ...; verdict: {...}' form. Uses the LAST text block that contains them."""
import json, re, sys
src = sys.argv[1]
texts = []
def walk(o):
    if isinstance(o, str):
        if '"choice"' in o and ('"packet"' in o or "FAILED" in o): texts.append(o)
    elif isinstance(o, dict):
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
for line in open(src, errors="replace"):
    try: walk(json.loads(line))
    except Exception: pass
if not texts: sys.exit("no verdict text found")
def _count(t):
    return len(re.findall(r'p\d{4}\.md', t))
t = max(texts, key=_count)
out = {}
for m in re.finditer(r'(p\d{4}\.md)[^\n{]*?(\{.*?"choice".*?\})', t):
    try:
        o = json.loads(m.group(2)); out[m.group(1)] = {"packet": m.group(1), "choice": o["choice"], "rationale": o["rationale"]}
    except Exception: pass
for m in re.finditer(r'\{"packet":\s*"(p\d{4}\.md)".*?\}', t):
    try:
        o = json.loads(m.group(0)); out[o["packet"]] = o
    except Exception: pass
for v in out.values(): print(json.dumps(v))
print(f"extracted={len(out)}", file=sys.stderr)
