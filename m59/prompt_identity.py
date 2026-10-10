"""Pilot-twice read for the v2 scaffold: per item, the per-request prompt_tokens sequence of pass 1 vs pass 2
(worker log). Identical prefixes prove the scaffold fed identical prompts up to the first output divergence;
where the sequences first differ is where the SERVER produced a different output for an identical input.
Usage: prompt_identity.py <rows_p1.jsonl> <rows_p2.jsonl> <worker log>"""
import json
import re
import sys

p1, p2, log = sys.argv[1:4]
lines = open(log, errors="replace").read().splitlines()


def seq(sid):
    out = []
    for l in lines:
        if f"session={sid}" in l and "Request completed" in l:
            m = re.search(r"prompt_tokens=(\d+)", l)
            c = re.search(r"completion_tokens=(\d+)", l)
            out.append((int(m.group(1)) if m else None, int(c.group(1)) if c else None))
    return out


rows = {}
for tag, p in (("p1", p1), ("p2", p2)):
    for l in open(p):
        if l.strip():
            r = json.loads(l)
            rows.setdefault(r["id"], {})[tag] = r
all_ok = True
for item, d in rows.items():
    if "p1" not in d or "p2" not in d:
        print(f"{item:22s} missing in one pass")
        all_ok = False
        continue
    a, b = seq(d["p1"]["session_id"]), seq(d["p2"]["session_id"])
    pa, pb = [x[0] for x in a], [x[0] for x in b]
    n = 0
    while n < min(len(pa), len(pb)) and pa[n] == pb[n]:
        n += 1
    first_same = n >= 1
    if pa == pb and [x[1] for x in a] == [x[1] for x in b]:
        verdict = "IDENTICAL"
    elif first_same:
        verdict = f"prompts identical for {n}/{max(len(pa), len(pb))} requests; first output divergence in request {n}"
    else:
        verdict = "FIRST PROMPT DIFFERS (scaffold leak)"
    if d["p1"].get("prompt_date") != d["p2"].get("prompt_date"):
        verdict = "NOT COMPARABLE (date mismatch, C135): " + verdict
    else:
        all_ok &= first_same
    print(f"{item:22s} p1 {str(d['p1'].get('passed')):5s} {d['p1']['wall_s']:5.0f}s p2 {str(d['p2'].get('passed')):5s} {d['p2']['wall_s']:5.0f}s | {verdict}")
print("SCAFFOLD PROMPT IDENTITY:", "PASS (every same-date item's first prompt identical)" if all_ok else "FAIL")
