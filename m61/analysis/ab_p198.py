"""P198 system-prompt A/B: per model geometric mean of per-(session,item) B/A output-token ratios, two-stage cluster bootstrap."""
import json, os, math, random, glob, statistics as st
W = os.path.expanduser("~/ws/mlx_local_stack_workdir"); AB = f"{W}/m61/ab"
MODELS = ["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit"]
def rows(model, s, arm):
    out = {}
    for f in glob.glob(f"{AB}/{model}.m61ab.{s}.{arm}.opencode_*.jsonl"):
        for l in open(f):
            r = json.loads(l); out[r["id"]] = r
    return out
def tx(r):
    t = json.load(open(r["transcript_path"].replace("$STACK_WORKDIR", W)))
    fw, wrote, vis = 0, False, 0
    for m in t["messages"]:
        if m.get("type") != "assistant": continue
        for x in m.get("content", []):
            if x.get("type") == "text": vis += len(x.get("text") or "")
        if not wrote:
            fw += (m.get("tokens") or {}).get("output", 0)
            if any(x.get("type") == "tool" and x.get("name") in ("write", "edit", "apply_patch") for x in m.get("content", [])): wrote = True
    return fw, vis
def boot(cells, n=20000, seed=198):
    items = sorted({i for _, i in cells}); rng = random.Random(seed); g = []
    for _ in range(n):
        v = []
        for i in rng.choices(items, k=len(items)):
            ss = [cells[k] for k in cells if k[1] == i]
            v += rng.choices(ss, k=len(ss))
        g.append(math.exp(st.mean(v)))
    g.sort(); return g[int(.025 * n)], g[int(.975 * n) - 1]
for m in MODELS:
    cells, fwc, visc, misses, det = {}, {}, {}, [], []
    for s in ("s1", "s2"):
        A, B = rows(m, s, "A"), rows(m, s, "B")
        assert set(A) == set(B) and len(A) == 5, (m, s, len(A), len(B))
        for i in sorted(A):
            a, b = A[i], B[i]
            assert a["sampler_seed"] == b["sampler_seed"] and b["agent_system_sha256"] and not a["agent_system_sha256"]
            ta, tb = a["traffic"]["output_tokens"], b["traffic"]["output_tokens"]
            cells[(s, i)] = math.log(tb / ta)
            (fa, va), (fb, vb) = tx(a), tx(b)
            fwc[(s, i)] = math.log(max(fb, 1) / max(fa, 1)); visc[(s, i)] = math.log(max(vb, 1) / max(va, 1))
            if a["passed"] and not b["passed"]: misses.append((s, i))
            det.append(f"  {s} {i:16s} out A={ta:6d} B={tb:6d} B/A={tb/ta:.2f} | firstwrite A={fa:6d} B={fb:6d} | vis A={va:5d} B={vb:5d} | pass {a['passed']}/{b['passed']} turns {a['traffic']['turns']}/{b['traffic']['turns']} wall {a['wall_s']:.0f}/{b['wall_s']:.0f}")
    pt = math.exp(st.mean(cells.values())); lo, hi = boot(cells)
    verdict = "prompt-causal" if hi < 1.0 and pt <= 0.85 else ("null" if lo <= 1.0 <= hi else "inconclusive")
    print(f"{m}\n  PRIMARY output-token GM B/A = {pt:.3f}  95% CI [{lo:.3f}, {hi:.3f}]  -> {verdict}")
    for name, c in (("first-write tokens", fwc), ("visible-text chars", visc)):
        p = math.exp(st.mean(c.values())); l, h = boot(c); print(f"  secondary {name} GM B/A = {p:.3f} [{l:.3f}, {h:.3f}]")
    print(f"  B-only misses: {misses or 'none'}"); print("\n".join(det))
