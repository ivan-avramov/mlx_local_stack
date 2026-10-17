"""c144-base report: both picks re-recorded on probe d4319705 (C164/C165 R1), same design and seeds as P223 (tg1, predictor OFF,
k=2 + same-seed reload control). Descriptive / power-input evidence for M64 (C165): NOT the M64 baseline.

Rows: benchmark/results/<model>/opencode_v2_<lang>.c144base.<session>.jsonl (copied from $STACK_WORKDIR/c144-base/ after the
chain validated every leg). Per leg: answer_key.report_rows (inline web audit), acc_strict@budget (pass AND converged)
with cluster-bootstrap CI, nonconv kinds, wall. Per session: head-to-head pick 1 minus pick 2 (two-stage paired
bootstrap, Holm per session family, TOST 0.05), plus the C154 sensitivity cut excluding items where either pick ended
`client_inactivity`. Reload control vs s1 on the same items. The P223 comparison (same scaffold and seeds, probe 8d1b4c84
vs d4319705) is DESCRIPTIVE only — a run-to-run replication measure, never pooled. Usage: c144base_report.py (writes
C144BASE_REPORT.md beside itself)."""
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark"))
from bench import answer_key, row_scores, stats  # noqa: E402

RES = REPO / "benchmark/results"
P1, P2 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit"
SESS, LANGS = ("s1", "s2"), ("python", "go")
INVALID = {"go/counter"}   # C145: deprecated inverted exercise (not in the tg1 universe; kept for the M61 comparison)
out = []


def p(s=""):
    out.append(s)
    print(s)


def rows(f):
    return [json.loads(line) for line in open(f) if line.strip()] if f.exists() else []


def strict(r):
    return int(r.get("passed") is True and not r.get("nonconv_kind"))


def pv(d):
    se = (d["hi"] - d["lo"]) / (2 * 1.96)
    z = abs(d["delta"]) / se if se > 0 else 0.0
    return 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))


def verdict_label(d, names=("first", "second")):
    """P359 (C172): A better / B better (CI excludes 0) or wash with MDE and the directional pick."""
    return stats.verdict_label(d, *names)


def family(title, pairs, names=("first", "second")):
    p(f"\n## {title}\n")
    p("| comparison | n | delta | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |")
    p("|---|---|---|---|---|---|---|---|")
    res = []
    for label, a, b in pairs:
        common = sorted(set(a) & set(b))
        d = stats.paired_delta({k: a[k] for k in common}, {k: b[k] for k in common}, iters=20000, seed=223, margin=0.05)
        res.append((label, d, pv(d)))
    adj = stats.holm([r[2] for r in res])
    for (label, d, pval), h in zip(res, adj):
        p(f"| {label} | {d['n_items']} | {d['delta']:+.3f} | [{d['lo']:+.2f}, {d['hi']:+.2f}] | {verdict_label(d, names)} | "
          f"{d['mde']:.2f} | {pval:.3f} | {h:.3f} |")


p("# c144-base report — both picks re-recorded on probe d4319705 (opencode-v2-web-tg1, predictor OFF, k=2 + reload)\n")
p("Scaffold `opencode-v2-web-tg1`, opencode 2.0.20, probe sha `d4319705…`, box `m5max-128`; s1 2026-10-15 (attempt 1), "
  "s2 + reload 2026-10-16 (attempt 2 after a guard-residual abort; attempt 1 archived with a sha256 manifest), rc 0, every leg "
  "validated. Status (C165): descriptive / power-input evidence, not the M64 baseline. acc_strict@budget = pass AND converged (any nonconv kind fails strict). "
  "`client_inactivity` = opencode 2.0.20's 60-min single-request interrupt (C154).\n")
p("## Per leg (answer_key.report_rows, inline web audit)\n")
p("| model | lang | session | acc_strict | 95% CI | lenient | nonconv kinds | web fetches | answer-key contact | "
  "audit incomplete | provisional | mean wall s | leg wall h |")
p("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
items, raw, provisional = {}, {}, []
for m in (P1, P2):
    for lang in LANGS:
        for s in SESS:
            f = RES / m / f"opencode_v2_{lang}.c144base.{s}.jsonl"
            rs = row_scores.effective_rows(rows(f), row_scores.sidecar_path(f))   # P311-lite: one fail-closed join
            raw[(m, lang, s)] = rs
            side = Path(str(f) + ".webaudit.jsonl")      # P201 sidecar (C158: codex or Cursor auditor)
            rep = answer_key.report_rows(rs, audit_sidecar=side if side.exists() else None,
                                         score_sidecar=row_scores.sidecar_path(f))
            pm = rep["per_model"].get(m, {})
            it = {k: v for k, v in rep["strict_items"].items() if k not in INVALID}
            items[(m, lang, s)] = it
            if pm.get("provisional"):
                provisional.append(f"{m} {lang} {s} (missing audits {pm.get('missing_audits')})")
            cb = stats.cluster_bootstrap(it, iters=20000, seed=223)
            kinds = {}
            for r in [r for r in rep["scored_rows"] if r["id"] not in INVALID]:
                k = r.get("nonconv_kind") or "converged"
                kinds[k] = kinds.get(k, 0) + 1
            ok = sum(sum(v) for v in it.values())
            lenient = sum(bool(r.get("passed")) for r in rs)
            web = sum(len(r.get("web_fetches") or []) for r in rs)
            contact = sum(bool(r.get("answer_key_contact")) for r in rs)
            inc = sum(bool(r.get("web_audit_incomplete")) for r in rs)
            p(f"| {m} | {lang} | {s} | {ok}/{len(it)} = {ok / len(it):.3f} | [{cb['lo']:.2f}, {cb['hi']:.2f}] | "
              f"{lenient}/{len(rs)} | {kinds} | {web} | {contact} | {inc} | {pm.get('provisional')} | "
              f"{sum(r['wall_s'] for r in rs) / len(rs):.0f} | {sum(r['wall_s'] for r in rs) / 3600:.1f} |")

p("\n## Per-item consistency across sessions\n")
for m in (P1, P2):
    for lang in LANGS:
        a = {k: v[0] for k, v in items[(m, lang, "s1")].items()}
        b = {k: v[0] for k, v in items[(m, lang, "s2")].items()}
        p(f"- {m} {lang}: discordant {sorted(i for i in a if a[i] != b.get(i))}; "
          f"missed in both {sorted(i for i in a if a[i] == 0 and b.get(i) == 0)}")

for s in SESS:
    family(f"Head-to-head {s}: {P1} minus {P2}", [(lang, items[(P1, lang, s)], items[(P2, lang, s)]) for lang in LANGS], names=(P1, P2))


def drop_inactivity(s, lang):
    hit = {r["id"] for m in (P1, P2) for r in raw[(m, lang, s)] if r.get("nonconv_kind") == "client_inactivity"}
    return hit, ({k: v for k, v in items[(P1, lang, s)].items() if k not in hit},
                 {k: v for k, v in items[(P2, lang, s)].items() if k not in hit})


for s in SESS:
    pairs, dropped = [], []
    for lang in LANGS:
        hit, (a, b) = drop_inactivity(s, lang)
        dropped += sorted(hit)
        pairs.append((lang, a, b))
    family(f"C154 sensitivity {s}: head-to-head excluding items where either pick ended client_inactivity "
           f"(dropped {dropped or 'none'})", pairs, names=(P1, P2))

p("\n## Reload control (pick 1, fresh instance, s1 seed, the s1 pilot items)\n")
rl = {r["id"]: strict(r) for r in rows(RES / P1 / "opencode_v2_python.c144base.reload.jsonl")}
s1 = {k: v[0] for k, v in items[(P1, "python", "s1")].items()}
agree = sum(rl[k] == s1.get(k) for k in rl)
p(f"- {len(rl)} items {sorted(rl)}; reload strict {sum(rl.values())}/{len(rl)}, s1 strict on the same items "
  f"{sum(s1.get(k, 0) for k in rl)}/{len(rl)}; agreement {agree}/{len(rl)}")

disc_rep = []
for s in SESS:
    pairs = []
    for m in (P1, P2):
        for lang in LANGS:
            ref = {r["id"]: [strict(r)] for r in rows(RES / m / f"opencode_v2_{lang}.p223.{s}.jsonl") if r["id"] not in INVALID}
            pairs.append((f"{m} {lang}", items[(m, lang, s)], ref))
            a = {k: v[0] for k, v in items[(m, lang, s)].items()}
            disc_rep.append(f"- {s} {m} {lang}: c144-base vs P223 discordant {sorted(i for i in a if i in ref and a[i] != ref[i][0])} of {len(a)}")
    family(f"DESCRIPTIVE replication: c144-base {s} minus P223 {s} (same scaffold and seeds; probe d4319705 vs 8d1b4c84 — never pooled)",
           pairs, names=("c144-base", "P223"))

p("\n## Paired discordance (input to the M64 power simulation)\n")
for m in (P1, P2):
    for lang in LANGS:
        for sx in SESS:
            pass
for line in disc_rep:
    p(line)
for sx in SESS:
    for lang in LANGS:
        a = {k: v[0] for k, v in items[(P1, lang, sx)].items()}
        b = {k: v[0] for k, v in items[(P2, lang, sx)].items()}
        p(f"- {sx} {lang}: pick 1 vs pick 2 discordant {sorted(i for i in a if i in b and a[i] != b[i])} of {len(a)}")

p("\n## Misses (all legs, all sessions, reload included)\n")
p("| model | lang | session | item | kind | passed (lenient) | wall s | requests | output tokens charged | "
  "uncharged reasoning chars | uncharged streamed s | max identical run |")
p("|---|---|---|---|---|---|---|---|---|---|---|---|")
legs = dict(raw)
legs[(P1, "python", "reload")] = rows(RES / P1 / "opencode_v2_python.c144base.reload.jsonl")
for (m, lang, s), rs in legs.items():
    for r in rs:
        if strict(r) or r["id"] in INVALID:
            continue
        g = r.get("gate") or {}
        u = (r.get("reconciliation") or {}).get("uncharged_trailing") or {}
        p(f"| {m} | {lang} | {s} | {r['id']} | {r.get('nonconv_kind') or 'fail'} | {bool(r.get('passed'))} | "
          f"{r['wall_s']:.0f} | {g.get('requests_completed')} | {g.get('output_tokens_completed')} | "
          f"{u.get('reasoning_chars', '')} | {u.get('streamed_s', '')} | {g.get('max_identical_run_live')} |")

p("\n## Runaway tax per session (descriptive, no interval)\n")
p("| model | session | client_inactivity | looping | stalled | hard_ceiling | exec_timeout | budget_hit (flag) | "
  "dedup union / 43 | session wall h |")
p("|---|---|---|---|---|---|---|---|---|---|")
for m in (P1, P2):
    for s in SESS:
        rs = [r for r in raw[(m, "python", s)] + raw[(m, "go", s)] if r["id"] not in INVALID]
        kinds = [r.get("nonconv_kind") for r in rs]
        flags = [set(r.get("nonconv_flags") or []) for r in rs]
        p(f"| {m} | {s} | {kinds.count('client_inactivity')} | {kinds.count('looping')} | {kinds.count('stalled')} | "
          f"{kinds.count('hard_ceiling')} | {kinds.count('exec_timeout')} | {sum('budget_hit' in f for f in flags)} | "
          f"{sum(1 for k in kinds if k)} | {sum(r['wall_s'] for r in rs) / 3600:.1f} |")

p("\n## Web fetches (inline audit)\n")
for (m, lang, s), rs in legs.items():
    for r in rs:
        for w in r.get("web_fetches") or []:
            p(f"- {m} {lang} {s} {r['id']}: {json.dumps(w)[:200]}")

if provisional:   # web fetches without a current P201 audit are held out of acc_strict until resolved
    out.insert(1, "\n**PROVISIONAL:** web fetches without a current P201 audit are held out of `acc_strict` in: "
               + "; ".join(provisional) + ". Every other cell is final.\n")
Path(__file__).with_name("C144BASE_REPORT.md").write_text("\n".join(out) + "\n")
