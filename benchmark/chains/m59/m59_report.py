# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m59/m59_report.py, the driver behind the opencode_v2_*.m59.* (M59) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
"""M59 report: v2 re-baseline of the two B picks (Python + Go, 22 items, k=2 sessions). Per (model, lang, session):
acc_strict@budget (miss = fail or any non-convergence), convergence, nonconv kinds, wall; per-item consistency; paired
two-stage bootstrap deltas (descriptive): v2 session vs 1.18 medium (k=1, scaffold delta, never pooled) and pick 1 vs
pick 2 per session; Holm within each family; TOST margin 0.05. Stall re-run (P182) conversions. Usage: m59_report.py"""
import json, os, sys
from pathlib import Path
REPO = Path(os.environ.get("STACK_REPO") or (Path.home() / "ws/mlx_local_stack"))
sys.path.insert(0, str(REPO / "benchmark"))
from bench import stats  # noqa: E402

WD = Path(os.environ.get("STACK_WORKDIR") or (Path.home() / "ws/mlx_local_stack_workdir"))
M = WD / "m59"
P1, P2 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit"
RES = REPO / "benchmark/results"
BASE118 = {(P1, "python"): RES / f"{P1}-MED/opencode.jsonl", (P1, "go"): RES / P1 / "opencode_go.medium.jsonl",  # allow-shorthand
           (P2, "python"): RES / f"{P2}-MED/opencode.jsonl", (P2, "go"): RES / P2 / "opencode_go.medium.jsonl"}  # allow-shorthand
MEMORY_PRESSURE = {(P1, "s2", "python/food-chain")}   # P183 trigger item


def rows(p):
    try:
        return [json.loads(l) for l in open(p) if l.strip()]
    except FileNotFoundError:
        return []


def v2_file(s, model, lang):
    return M / s / (f"{model}.opencode_{lang}.jsonl" if s == "s1" else f"{model}.{s}.opencode_{lang}.jsonl")


def strict(r):
    return 1 if (r.get("passed") is True and not r.get("nonconv_kind")) else 0


def per_item(rs):
    return {r["id"]: [strict(r)] for r in rs}


def summ(rs):
    n = len(rs)
    k = {}
    for r in rs:
        # legacy 1.18 rows carry no nonconv_kind; their gate outcome is in stop_reason (Codex RCA 2026-10-08)
        legacy = r.get("stop_reason") if r.get("stop_reason") not in (None, "completed") else None
        key = r.get("nonconv_kind") or legacy or "converged"
        k[key] = k.get(key, 0) + 1
    return n, sum(strict(r) for r in rs), k, (sum(r.get("wall_s", 0) for r in rs) / n if n else 0)


def first_write_s(r):
    """Seconds from the session's first message to the first completed write/edit tool call, from the transcript."""
    import os
    p = r.get("transcript_path", "").replace("$STACK_WORKDIR", os.environ.get("STACK_WORKDIR", str(Path.home() / "ws/mlx_local_stack_workdir")))
    try:
        d = json.load(open(p))
    except (OSError, ValueError):
        return None
    t0 = d["messages"][0]["time"]["created"]
    for m in d["messages"]:
        if m.get("type") != "assistant":
            continue
        if any(c.get("type") == "tool" and c.get("name") in ("write", "edit") for c in m.get("content", [])):
            return (m["time"].get("completed", m["time"]["created"]) - t0) / 1000
    return None


out = []
def p(s=""):
    out.append(s); print(s)

p("# M59 v2 re-baseline report")
p("\n## Per (model, language, session) — acc_strict@budget (miss = fail or non-convergence)\n")
p("| model | lang | arm | n | acc_strict | 95% CI (cluster bootstrap) | nonconv kinds | mean wall s | window s |")
p("|---|---|---|---|---|---|---|---|---|")
data = {}
for model in (P1, P2):
    for lang in ("python", "go"):
        arms = [("1.18 medium", BASE118[(model, lang)], None)]
        arms += [(s, v2_file(s, model, lang), v2_file(s, model, lang).with_suffix(".manifest.json")) for s in ("s1", "s2")]
        if model == P2:
            a = M / "archive/s1_pick2_window558" / f"{model}.opencode_{lang}.jsonl"
            arms.append(("s1@558 (superseded)", a, a.with_suffix(".manifest.json")))
        for name, f, mf in arms:
            rs = rows(f)
            data[(model, lang, name)] = rs
            if not rs:
                p(f"| {model} | {lang} | {name} | 0 | — | — | — | — | — |"); continue
            n, ok, kinds, wall = summ(rs)
            cb = stats.cluster_bootstrap(per_item(rs), iters=5000, seed=59)
            win = "600 (1.18 wall)" if mf is None else (json.load(open(mf))["runtime"].get("first_write_window_s") if mf.exists() else "?")
            p(f"| {model} | {lang} | {name} | {n} | {ok}/{n} = {ok/n:.3f} | [{cb['lo']:.2f}, {cb['hi']:.2f}] | {kinds} | {wall:.0f} | {win} |")

p("\n## Per-item consistency across the two v2 sessions (discordant items)\n")
for model in (P1, P2):
    for lang in ("python", "go"):
        a = {r["id"]: strict(r) for r in data[(model, lang, "s1")]}; b = {r["id"]: strict(r) for r in data[(model, lang, "s2")]}
        disc = sorted(i for i in a if i in b and a[i] != b[i])
        both_miss = sorted(i for i in a if i in b and a[i] == 0 and b[i] == 0)
        p(f"- {model} {lang}: discordant {len(disc)} {disc}; missed in both {both_miss}")

def family(title, pairs):
    p(f"\n## {title}\n")
    p("| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | p (approx) | Holm-adjusted |")
    p("|---|---|---|---|---|---|---|")
    res = []
    for label, a, b in pairs:
        if not a or not b:
            res.append((label, None)); continue
        ia, ib = per_item(a), per_item(b)
        common = sorted(set(ia) & set(ib))
        d = stats.paired_delta({k: ia[k] for k in common}, {k: ib[k] for k in common}, iters=5000, seed=59, margin=0.05)
        # approximate two-sided p from the bootstrap CI width (normal approximation)
        se = (d["hi"] - d["lo"]) / (2 * 1.96) if d["hi"] > d["lo"] else float("inf")
        import math
        z = abs(d["delta"]) / se if se and se != float("inf") else 0.0
        pv = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
        res.append((label, d, len(common), pv))
    adj = stats.holm([r[3] for r in res if r[1] is not None]) if any(r[1] for r in res) else []
    j = 0
    for r in res:
        if r[1] is None:
            p(f"| {r[0]} | — | — | — | missing data | — | — |"); continue
        label, d, n, pv = r
        p(f"| {label} | {n} | {d['delta']:+.3f} | [{d['lo']:+.2f}, {d['hi']:+.2f}] | {d['verdict']} | {pv:.3f} | {adj[j]:.3f} |"); j += 1

for s in ("s1", "s2"):
    family(f"Scaffold delta (descriptive, never pooled): v2 {s} minus 1.18 medium",
           [(f"{m} {l}", data[(m, l, s)], data[(m, l, "1.18 medium")]) for m in (P1, P2) for l in ("python", "go")])
for s in ("s1", "s2"):
    family(f"Head-to-head v2 {s}: {P1} minus {P2}",
           [(f"{l}", data[(P1, l, s)], data[(P2, l, s)]) for l in ("python", "go")])

p("\n## P182 stall re-run (48K-token allowance, same item seeds, one fresh instance per model)\n")
WINDOW = {P1: 662, P2: 630}
p("| model | session | item | chain window s | re-run first write s | re-run wall s | output tokens | result | kind |")
p("|---|---|---|---|---|---|---|---|---|")
tally = {}
sp = M / "stallprobe"
for f in sorted(sp.glob("*.jsonl")) if sp.exists() else []:
    model = P1 if f.name.startswith(P1) else P2
    sess = "s1" if ".s1." in f.name else "s2"
    lang = "go" if f.name.endswith("_go.jsonl") else "python"
    for r in rows(f):
        ok = strict(r) == 1
        # allowance = the FIRST WRITE came after the chain window (completion time over-counts; Codex RCA 2026-10-08)
        fw = first_write_s(r)
        kind = ("allowance" if fw is not None and fw > WINDOW[model] else "variance") if ok else "real miss"
        tally.setdefault((model, sess, lang), {"allowance": 0, "variance": 0, "real miss": 0})[kind] += 1
        p(f"| {model} | {sess} | {r['id']} | {WINDOW[model]} | {fw if fw is None else round(fw)} | {r['wall_s']:.0f} | {r.get('traffic', {}).get('output_tokens')} | {'pass' if ok else (r.get('nonconv_kind') or 'fail')} | {kind} |")
p("\n### What the gate cost (descriptive; chain rows are unchanged and remain the record)\n")
p("| model | lang | session | chain acc_strict | + allowance conversions | + variance conversions | still missed |")
p("|---|---|---|---|---|---|---|")
for model in (P1, P2):
    for lang in ("python", "go"):
        for sess in ("s1", "s2"):
            rs = data[(model, lang, sess)]; ok = sum(strict(r) for r in rs)
            t = tally.get((model, sess, lang), {"allowance": 0, "variance": 0, "real miss": 0})
            p(f"| {model} | {lang} | {sess} | {ok}/{len(rs)} | +{t['allowance']} -> {ok + t['allowance']}/{len(rs)} | +{t['variance']} | {len(rs) - ok - t['allowance'] - t['variance']} |")
p("\n## Flags\n")
for (m, s, i) in sorted(MEMORY_PRESSURE):
    r = next((x for x in data.get((m, "python", s), []) if x["id"] == i), None)
    p(f"- memory-pressure event during {m} {s} {i} (a model-written loop reached 117 GB before P183): row passed={r and r.get('passed')} wall={r and r.get('wall_s')}")
p("- s1 pick-2 arm re-run after observing stalls (adaptive; C136 addendum); the 558 s arm is shown separately and never pooled.")
p("- 1.18 medium rows: opencode 1.18.15, unseeded (C121), wall-clock 600 s stall window, k=1 — the scaffold delta mixes scaffold, seed and gate-policy changes.")
(M / "M59_REPORT.md").write_text("\n".join(out) + "\n")
