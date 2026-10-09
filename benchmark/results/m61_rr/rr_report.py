"""M61 C139(b) re-record report (opencode-v2-web, 48K first-write allowance, audited web). Per leg: answer_key.report_rows
(scored copies; provisional/cheat counts), acc_strict@budget with cluster-bootstrap CI, nonconv kinds, wall. Per session:
head-to-head pick 1 minus pick 2 (two-stage paired bootstrap, Holm per session family, TOST 0.05). M59 (16K, no web, same
seeds) comparison DESCRIPTIVE only — different scaffold, never pooled. Misses with loop metrics. Usage: rr_report.py"""
import json, math, os, sys
from pathlib import Path
REPO = Path(os.environ.get("STACK_REPO") or (Path.home() / "ws/mlx_local_stack"))
sys.path.insert(0, str(REPO / "benchmark"))
from bench import stats, answer_key  # noqa: E402

WD = Path(os.environ.get("STACK_WORKDIR") or (Path.home() / "ws/mlx_local_stack_workdir"))
RR = WD / "m61/rr"
RES = REPO / "benchmark/results"
P1, P2 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit"
SESS, LANGS = ("s1", "s2"), ("python", "go")
out = []
def p(s=""):
    out.append(s); print(s)

def rows(f):
    return [json.loads(l) for l in open(f) if l.strip()] if f.exists() else []

def strict(r):
    return int(r.get("passed") is True and not r.get("nonconv_kind") and r.get("stop_reason") in (None, "completed"))

def pv(d):
    se = (d["hi"] - d["lo"]) / (2 * 1.96)
    z = abs(d["delta"]) / se if se > 0 else 0.0
    return 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))

def family(title, pairs):
    p(f"\n## {title}\n")
    p("| comparison | n | delta | 95% CI | verdict (TOST ±5 pp) | MDE | p (approx) | Holm |")
    p("|---|---|---|---|---|---|---|---|")
    res = []
    for label, a, b in pairs:
        common = sorted(set(a) & set(b))
        d = stats.paired_delta({k: a[k] for k in common}, {k: b[k] for k in common}, iters=20000, seed=61, margin=0.05)
        res.append((label, d, pv(d)))
    adj = stats.holm([r[2] for r in res])
    for (label, d, pval), h in zip(res, adj):
        p(f"| {label} | {d['n_items']} | {d['delta']:+.3f} | [{d['lo']:+.2f}, {d['hi']:+.2f}] | {d['verdict']} | {d['mde']:.2f} | {pval:.3f} | {h:.3f} |")

p("# M61 C139(b) re-record report — opencode-v2-web, 48K first-write allowance, audited web\n")
p("## Per leg (answer_key.report_rows; acc_strict@budget = pass AND converged)\n")
p("| model | lang | session | acc_strict | 95% CI | nonconv kinds | cheat attempts | reruns | provisional | web fetches | mean wall s | window s |")
p("|---|---|---|---|---|---|---|---|---|---|---|---|")
items, raw = {}, {}
for m in (P1, P2):
    for l in LANGS:
        for s in SESS:
            f = RR / f"{m}.rr.{s}.opencode_{l}.jsonl"
            rs = rows(f); raw[(m, l, s)] = rs
            side = Path(str(f) + ".webaudit.jsonl")
            rep = answer_key.report_rows(rs, audit_sidecar=side if side.exists() else None)
            pm = rep["per_model"].get(m, {})
            it = {k: v for k, v in rep["strict_items"].items()}
            items[(m, l, s)] = it
            cb = stats.cluster_bootstrap(it, iters=20000, seed=61)
            kinds = {}
            for r in rep["scored_rows"]:
                k = r.get("nonconv_kind") or "converged"; kinds[k] = kinds.get(k, 0) + 1
            ok = sum(sum(v) for v in it.values())
            web = sum(len(r.get("web_fetches") or []) for r in rs)
            win = json.load(open(f.with_suffix(".manifest.json")))["runtime"].get("first_write_window_s")
            wall = sum(r["wall_s"] for r in rs) / len(rs)
            p(f"| {m} | {l} | {s} | {ok}/{rep['strict_n']} = {rep['acc_strict']:.3f} | [{cb['lo']:.2f}, {cb['hi']:.2f}] | {kinds} | "
              f"{pm.get('cheat_attempts')} | {pm.get('reruns')} | {pm.get('provisional')} | {web} | {wall:.0f} | {win} |")

p("\n## Per-item consistency across sessions\n")
for m in (P1, P2):
    for l in LANGS:
        a = {k: v[0] for k, v in items[(m, l, "s1")].items()}; b = {k: v[0] for k, v in items[(m, l, "s2")].items()}
        p(f"- {m} {l}: discordant {sorted(i for i in a if a[i] != b.get(i))}; missed in both {sorted(i for i in a if a[i] == 0 and b.get(i) == 0)}")

for s in SESS:
    family(f"Head-to-head {s}: {P1} minus {P2}", [(l, items[(P1, l, s)], items[(P2, l, s)]) for l in LANGS])

INVALID = {"go/counter"}   # C145: deprecated inverted exercise; passes are "[no tests to run]", doing the task trips the tamper check
p("\n## Sensitivity: go/counter excluded (C145 proposal)\n")
for m in (P1, P2):
    for s in SESS:
        it = {k: v for k, v in items[(m, "go", s)].items() if k not in INVALID}
        p(f"- {m} go {s}: {sum(v[0] for v in it.values())}/{len(it)}")
for s in SESS:
    a = {k: v for k, v in items[(P1, "go", s)].items() if k not in INVALID}
    b = {k: v for k, v in items[(P2, "go", s)].items() if k not in INVALID}
    family(f"Sensitivity head-to-head {s} go, go/counter excluded: {P1} minus {P2}", [("go", a, b)])

for s in SESS:
    pairs = []
    for m in (P1, P2):
        for l in LANGS:
            m59 = {r["id"]: [strict(r)] for r in rows(RES / m / f"opencode_v2_{l}.m59.{s}.jsonl")}
            pairs.append((f"{m} {l}", items[(m, l, s)], m59))
    family(f"DESCRIPTIVE: M61 re-record {s} minus M59 {s} (same seeds; scaffold opencode-v2-web 48K vs opencode-v2 16K — never pooled)", pairs)

p("\n## Misses (all legs)\n")
p("| model | lang | session | item | kind | wall s | turns | output tokens | tool calls | error calls | repeated identical | max identical run | web | test_modified |")
p("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for (m, l, s), rs in raw.items():
    for r in rs:
        if strict(r): continue
        t, lm = r.get("traffic") or {}, r.get("loop_metrics") or {}
        p(f"| {m} | {l} | {s} | {r['id']} | {r.get('nonconv_kind') or ('fail' if not r.get('passed') else r.get('stop_reason'))} | {r['wall_s']:.0f} | "
          f"{t.get('turns')} | {t.get('output_tokens')} | {lm.get('tool_calls')} | {lm.get('error_calls')} | {lm.get('repeat_identical_calls')} | "
          f"{lm.get('max_identical_run')} | {len(r.get('web_fetches') or [])} | {r.get('test_modified')} |")

p("\n## Runaway tax per session (descriptive, no interval)\n")
p("| model | session | stalled | budget-hit | turn-cap | exec-timeout | dedup union / 44 | leg wall h |")
p("|---|---|---|---|---|---|---|---|")
for m in (P1, P2):
    for s in SESS:
        rs = raw[(m, "python", s)] + raw[(m, "go", s)]
        kinds = [r.get("nonconv_kind") for r in rs]
        p(f"| {m} | {s} | {kinds.count('stalled')} | {kinds.count('budget_hit')} | {kinds.count('turn_cap')} | {kinds.count('exec_timeout')} | "
          f"{sum(1 for k in kinds if k)} | {sum(r['wall_s'] for r in rs) / 3600:.1f} |")
(WD / "m61/RR_REPORT.md").write_text("\n".join(out) + "\n")
