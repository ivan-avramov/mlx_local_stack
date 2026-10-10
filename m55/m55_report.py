"""M55 polyglot gap report: per-language, per-session paired comparisons vs the first pick (C109: acc paired per session,
pooled rate descriptive only). Usage: python m55_report.py [out.md]"""
import json, os, sys, statistics as st
sys.path.insert(0, "$STACK_REPO/benchmark")
from bench import stats
M = "$STACK_WORKDIR/m55"
MODELS = ["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit", "Ornith-1.0-35B-mlx-uniform-4bit"]
LANGS = ["rust", "java", "javascript"]; SESS = ["s1", "s2"]; FIRST = MODELS[0]
def load(s, m, l):
    p = f"{M}/{s}/{m}.opencode_{l}.jsonl"
    if not os.path.exists(p): return None
    r = [json.loads(x) for x in open(p)]
    return r if len(r) == 22 else None
R = {(s, m, l): load(s, m, l) for s in SESS for m in MODELS for l in LANGS}
def per_item(rows):
    # C121/E10: `passed: null` rows (grade-excluded, e.g. a rewritten seed overlay) are neither pass nor fail
    return {x["id"]: [1.0 if x["passed"] else 0.0] for x in rows if x.get("passed") is not None}
out = []
out.append("# M55 polyglot gap — Rust / Java / JavaScript, C37 22-exercise draws, opencode 1.18.30, draft OFF, deployed sampling\n")
out.append("Rule C109: acc is paired PER SESSION (each session = a fresh loaded instance); the pooled rate is DESCRIPTIVE (22 tasks × 2 sessions), no interval. Nominal paired MDE at n=22 ≈ ±27 pp, at n=66 ≈ ±16 pp (p_d=0.2).\n")
out.append("## Pass counts per language (s1 / s2 ; pooled descriptive) with stall / loop kills, sandbox rejections, mean wall s\n")
out.append("| language | model | s1 | s2 | pooled | stall | loop | rejected | test_modified | wall mean s |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for l in LANGS:
    for m in MODELS:
        cells = []; agg = {"stall": 0, "loop": 0, "rej": 0, "tm": 0, "w": [], "p": 0, "n": 0}
        for s in SESS:
            r = R[(s, m, l)]
            if r is None: cells.append("—"); continue
            p = sum(1 for x in r if x.get("passed") is True); ex = sum(1 for x in r if x.get("passed") is None)
            cells.append(str(p) + (f" ({ex} excl)" if ex else "")); agg["p"] += p; agg["n"] += 22 - ex
            agg["stall"] += sum(x["stop_reason"] == "stalled" for x in r); agg["loop"] += sum(x["stop_reason"] == "looping" for x in r)
            agg["rej"] += sum("rejected permission" in str(x.get("log_tail", "")) for x in r); agg["tm"] += sum(bool(x.get("test_modified")) for x in r)
            agg["w"] += [x["wall_s"] for x in r]
        pooled = f"{agg['p']}/{agg['n']}" if agg["n"] else "—"
        out.append(f"| {l} | `{m}` | {cells[0]} | {cells[1]} | {pooled} | {agg['stall']} | {agg['loop']} | {agg['rej']} | {agg['tm']} | {st.mean(agg['w']):.0f} |" if agg["w"] else f"| {l} | `{m}` | — | — | — | | | | | |")
out.append("\n## Paired deltas vs the first pick, per session (cluster bootstrap 95 % CI, TOST ±5 pp, exact McNemar on discordant pairs)\n")
out.append("| language | session | comparator | first pick | comparator | delta pp | 95 % CI | verdict | b:c | McNemar p | first-pick-only solves | comparator-only solves |\n|---|---|---|---:|---:|---:|---|---|---|---:|---|---|")
for l in LANGS + ["ALL"]:
    for s in SESS:
        for m in MODELS[1:]:
            if l == "ALL":
                ra = sum([R[(s, FIRST, x)] or [] for x in LANGS], []); rb = sum([R[(s, m, x)] or [] for x in LANGS], [])
                if len(ra) != 66 or len(rb) != 66: continue
            else:
                ra, rb = R[(s, FIRST, l)], R[(s, m, l)]
                if ra is None or rb is None: continue
            A, B = per_item(ra), per_item(rb)
            common = A.keys() & B.keys(); A = {k: A[k] for k in common}; B = {k: B[k] for k in common}
            strata = {k: k.split("/")[0] for k in A} if l == "ALL" else None
            d = stats.paired_delta(A, B, iters=10000, seed=0, margin=0.05, strata=strata)
            b = sorted(k for k in A if A[k][0] and not B[k][0]); c = sorted(k for k in A if B[k][0] and not A[k][0])
            p = stats.mcnemar_exact(len(b), len(c))
            out.append(f"| {l} | {s} | `{m}` | {int(sum(v[0] for v in A.values()))} | {int(sum(v[0] for v in B.values()))} | {100*d['delta']:+.1f} | [{100*d['lo']:+.1f}, {100*d['hi']:+.1f}] | {d['verdict']} | {len(b)}:{len(c)} | {p:.3f} | {', '.join((x if l=='ALL' else x.split('/')[-1]) for x in b) or '—'} | {', '.join((x if l=='ALL' else x.split('/')[-1]) for x in c) or '—'} |")
out.append("\n## Session repeatability (same model, s1 vs s2: discordant items / 22)\n")
out.append("| language | model | discordant | s1-only | s2-only |\n|---|---|---:|---|---|")
for l in LANGS:
    for m in MODELS:
        a, b = R[("s1", m, l)], R[("s2", m, l)]
        if a is None or b is None: continue
        A = {x["id"]: x["passed"] for x in a if x.get("passed") is not None}
        B = {x["id"]: x["passed"] for x in b if x.get("passed") is not None}
        common = A.keys() & B.keys(); A = {k: A[k] for k in common}; B = {k: B[k] for k in common}
        s1o = [k.split("/")[-1] for k in A if A[k] and not B[k]]; s2o = [k.split("/")[-1] for k in A if B[k] and not A[k]]
        out.append(f"| {l} | `{m}` | {len(s1o)+len(s2o)} | {', '.join(s1o) or '—'} | {', '.join(s2o) or '—'} |")
txt = "\n".join(out) + "\n"
(open(sys.argv[1], "w").write(txt) if len(sys.argv) > 1 else print(txt))
