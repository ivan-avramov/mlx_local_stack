"""Pair 1.18 medium vs v2 (s1, s2) per item: turns, output tokens, reasoning chars, first prompt, tools."""
import sqlite3, json, os, collections, statistics as st
W = os.path.expanduser("~/ws/mlx_local_stack_workdir"); R = os.path.expanduser("~/ws/mlx_local_stack/benchmark/results")
P1, P2 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit"
BASE = {(P1, "python"): f"{P1}-MED/opencode", (P1, "go"): f"{P1}/opencode_go.medium",
        (P2, "python"): f"{P2}-MED/opencode", (P2, "go"): f"{P2}/opencode_go.medium"}
c = sqlite3.connect(f"file:{W}/m59_debug/ocdb/opencode.db?mode=ro", uri=True)

def v118(model, lang):
    stem = BASE[(model, lang)]
    rows = {json.loads(l)["id"]: json.loads(l) for l in open(f"{R}/{stem}.jsonl")}
    t0 = json.load(open(f"{R}/{stem}.manifest.json"))["timestamp"] * 1000
    t1 = t0 + (sum(r["wall_s"] for r in rows.values()) + 7200) * 1000
    out = {}
    for sid, d, tc in c.execute("select id,directory,time_created from session where version like '1.18%' and time_created between ? and ? order by time_created", (t0 - 600000, t1)):
        item = d.rstrip("/").split("/")[-1]; key = f"{lang}/{item}"
        if key not in rows: continue
        parts = [json.loads(x[0]) for x in c.execute("select data from part where session_id=? order by time_created", (sid,))]
        utext = next((p["text"] for p in parts if p.get("type") == "text"), "")
        if (lang == "go") != (".go" in utext): continue
        msgs = [json.loads(x[0]) for x in c.execute("select data from message where session_id=? order by time_created", (sid,))]
        a = [m for m in msgs if m["role"] == "assistant"]
        if not a or not a[0].get("modelID", "").startswith(model): continue
        tools = collections.Counter(p["tool"] for p in parts if p.get("type") == "tool")
        rchars = sum(len(p.get("text", "")) for p in parts if p.get("type") == "reasoning")
        tchars = sum(len(p.get("text", "")) for p in parts if p.get("type") == "text") - len(utext)
        out[key] = dict(passed=rows[key]["passed"], wall=rows[key]["wall_s"], turns=len(a),
                        out=sum(m["tokens"]["output"] for m in a), first_out=a[0]["tokens"]["output"],
                        first_prompt=a[0]["tokens"]["input"] + a[0]["tokens"]["cache"]["read"],
                        maxctx=max(m["tokens"]["input"] + m["tokens"]["cache"]["read"] for m in a),
                        rchars=rchars, tchars=tchars, tools=dict(tools))
    return out

def v2(model, lang, s):
    out = {}
    for l in open(f"{R}/{model}/opencode_v2_{lang}.m59.{s}.jsonl"):
        r = json.loads(l); p = r["transcript_path"].replace("$STACK_WORKDIR", W)
        if not os.path.exists(p): continue
        d = json.load(open(p)); a = [m for m in d["messages"] if m["type"] == "assistant"]
        parts = [p for m in a for p in m.get("content", [])]
        tools = collections.Counter(p["name"] for p in parts if p.get("type") == "tool")
        tok = [m.get("tokens", {}) for m in a]
        out[r["id"]] = dict(passed=r["passed"], wall=r["wall_s"], turns=len(a), out=r["traffic"]["output_tokens"],
                            first_out=(tok[0].get("output") if tok and tok[0] else None),
                            first_prompt=None, maxctx=r["traffic"]["max_context"],
                            rchars=sum(len(p.get("text", "")) for p in parts if p.get("type") == "reasoning"),
                            tchars=sum(len(p.get("text", "")) for p in parts if p.get("type") == "text"),
                            tools=dict(tools), nonconv=r.get("nonconv_kind"))
    return out

res = {}
for m in (P1, P2):
    for lang in ("python", "go"):
        a, b1, b2 = v118(m, lang), v2(m, lang, "s1"), v2(m, lang, "s2")
        res[f"{m}|{lang}"] = dict(v118=a, s1=b1, s2=b2)
        common = sorted(set(a) & set(b1) & set(b2))
        def agg(d, k): return sum(d[i][k] for i in common)
        print(f"\n{m} {lang}: n118={len(a)} common={len(common)}")
        for k in ("out", "turns", "rchars", "tchars", "wall"):
            print(f"  {k:7s} 1.18={agg(a,k):>9.0f}  s1={agg(b1,k):>9.0f} ({agg(b1,k)/max(agg(a,k),1):.2f}x)  s2={agg(b2,k):>9.0f} ({agg(b2,k)/max(agg(a,k),1):.2f}x)")
        # passed-in-all items only (clean comparison of effort on solved items)
        ok = [i for i in common if a[i]["passed"] and b1[i]["passed"] and b2[i]["passed"]]
        ratios = [((b1[i]["out"] + b2[i]["out"]) / 2) / max(a[i]["out"], 1) for i in ok]
        print(f"  items passed everywhere {len(ok)}: median per-item out ratio {st.median(ratios):.2f}, geo-ish mean {st.mean(ratios):.2f}")
        t118 = collections.Counter(); tv2 = collections.Counter()
        for i in common: t118.update(a[i]["tools"]); tv2.update(b1[i]["tools"])
        print("  tools 1.18", dict(t118)); print("  tools v2s1", dict(tv2))
        print("  first_prompt 1.18 median", st.median([a[i]["first_prompt"] for i in common]))
json.dump(res, open(f"{W}/m59_debug/pair.json", "w"), indent=1)
