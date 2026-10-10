"""Output tokens spent before the first write/edit of the solution: 1.18 medium vs v2 s1/s2 (per item, paired)."""
import json, os, sqlite3, statistics as st
exec(open("pair.py").read().split("res = {}")[0])   # reuse loaders' constants/paths
def fw118(model, lang):
    stem = BASE[(model, lang)]; rows = {json.loads(l)["id"]: json.loads(l) for l in open(f"{R}/{stem}.jsonl")}
    t0 = json.load(open(f"{R}/{stem}.manifest.json"))["timestamp"] * 1000; t1 = t0 + (sum(r["wall_s"] for r in rows.values()) + 7200) * 1000
    out = {}
    for sid, d in c.execute("select id,directory from session where version like '1.18%' and time_created between ? and ?", (t0 - 600000, t1)):
        key = f"{lang}/{d.rstrip('/').split('/')[-1]}"
        if key not in rows: continue
        msgs = [(i, json.loads(x)) for i, x in c.execute("select id,data from message where session_id=? order by time_created", (sid,))]
        a = [(i, m) for i, m in msgs if m["role"] == "assistant"]
        if not a or not a[0][1].get("modelID", "").startswith(model): continue
        utext = json.loads(c.execute("select data from part where session_id=? order by time_created limit 1", (sid,)).fetchone()[0]).get("text", "")
        if (lang == "go") != (".go" in utext): continue
        tot = 0
        for i, m in a:
            tot += m["tokens"]["output"]
            if any(json.loads(x).get("tool") in ("write", "edit") for (x,) in c.execute("select data from part where message_id=?", (i,))): break
        out[key] = tot
    return out
def fw2(model, lang, s):
    out = {}
    for l in open(f"{R}/{model}/opencode_v2_{lang}.m59.{s}.jsonl"):
        r = json.loads(l); p = r["transcript_path"].replace("$STACK_WORKDIR", W)
        if not os.path.exists(p): continue
        tot = 0
        for m in json.load(open(p))["messages"]:
            if m.get("type") != "assistant": continue
            tot += (m.get("tokens") or {}).get("output", 0)
            if any(x.get("type") == "tool" and x.get("name") in ("write", "edit") for x in m.get("content", [])): break
        out[r["id"]] = tot
    return out
for m in (P1, P2):
    for lang in ("python", "go"):
        a, b1, b2 = fw118(m, lang), fw2(m, lang, "s1"), fw2(m, lang, "s2")
        com = sorted(set(a) & set(b1) & set(b2))
        r = [((b1[i] + b2[i]) / 2) / max(a[i], 1) for i in com]
        print(f"{m} {lang} n={len(com)} first-write tokens median 1.18={st.median(a[i] for i in com):.0f} v2={st.median((b1[i]+b2[i])/2 for i in com):.0f}  per-item ratio median {st.median(r):.2f}  max1.18={max(a[i] for i in com)} max v2={max(max(b1[i],b2[i]) for i in com)}  >16K: 1.18={sum(a[i]>16000 for i in com)} v2={sum(b1[i]>16000 for i in com)+sum(b2[i]>16000 for i in com)}/2 sessions")
