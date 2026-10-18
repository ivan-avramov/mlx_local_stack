"""M63 MTP-ON vs OFF report (spec docs/specs/m63-mtp-on-tg1-arm.md; C155, C71). Both arms: opencode-v2-web-tg1, same probe
(8d1b4c84…), same items/seeds/budgets, k=2 sessions + reload control, m5max-128. OFF rows = P223
(`opencode_v2_<lang>.p223.<s>.jsonl`), ON rows = M63 (`.m63.<s>.jsonl`). Per pick and session: paired ON−OFF on
acc_strict@budget (two-stage paired bootstrap, Holm within (pick, session), TOST ±5 pp), with all rows AND excluding
items where either arm ended `client_inactivity` (C154). Never pooled across sessions. Plus: the ON outcome of every OFF
`client_inactivity` item (P293), arm-only misses, reload control, tokens and wall per session (runaway tax in tokens,
C71). Usage: m63_report.py (writes M63_REPORT.md beside itself)."""
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark"))
from bench import answer_key, chain_rows, row_scores, stats, tg1_pairing  # noqa: E402

RES = REPO / "benchmark/results"
P1, P2 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit"
SESS, LANGS, ARMS = ("s1", "s2"), ("python", "go"), {"ON": "m63", "OFF": "p223"}
out = []


def p(s=""):
    out.append(s)
    print(s)


def load(m, lang, s, arm):
    f = chain_rows.stored_path(RES / m, lang, ARMS[arm], s)
    rows = row_scores.effective_rows(chain_rows.read_rows(f), row_scores.sidecar_path(f))   # P311-lite: one fail-closed join
    side = Path(str(f) + ".webaudit.jsonl")
    rep = answer_key.report_rows(rows, audit_sidecar=side if side.exists() else None,
                                 score_sidecar=row_scores.sidecar_path(f))
    return rows, rep


def pv(d):
    se = (d["hi"] - d["lo"]) / (2 * 1.96)
    z = abs(d["delta"]) / se if se > 0 else 0.0
    return 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))


def verdict_label(d, names=("first", "second")):
    """P359 (C172): A better / B better (CI excludes 0) or wash with MDE and the directional pick."""
    return stats.verdict_label(d, *names)


def family(title, pairs, names=("first", "second")):
    p(f"\n### {title}\n")
    p("| comparison | n | ON−OFF | 95% CI | verdict (CI excludes 0, else wash) | MDE | p (approx) | Holm |")
    p("|---|---|---|---|---|---|---|---|")
    res = []
    for label, a, b in pairs:
        common = sorted(set(a) & set(b))
        d = stats.paired_delta({k: a[k] for k in common}, {k: b[k] for k in common}, iters=20000, seed=63, margin=0.05)
        res.append((label, d, pv(d)))
    for (label, d, pval), h in zip(res, stats.holm([r[2] for r in res])):
        p(f"| {label} | {d['n_items']} | {d['delta']:+.3f} | [{d['lo']:+.2f}, {d['hi']:+.2f}] | {verdict_label(d, names)} | "
          f"{d['mde']:.2f} | {pval:.3f} | {h:.3f} |")


data = {(m, lang, s, arm): load(m, lang, s, arm) for m in (P1, P2) for lang in LANGS for s in SESS for arm in ARMS}

# L5: current-epoch ON/OFF rows pair only on equal generation composite and prompt date (legacy rows pass through)
gate_notes = []
for m in (P1, P2):
    for s in SESS:
        for lang in LANGS:
            (ron, aon), (roff, aoff) = data[(m, lang, s, "ON")], data[(m, lang, s, "OFF")]
            a, b, gate = tg1_pairing.gate_items(aon["strict_items"], aon["scored_rows"], aoff["strict_items"], aoff["scored_rows"])
            if gate is not None:
                aon["strict_items"], aoff["strict_items"] = a, b
                gate_notes.append(tg1_pairing.gate_note(f"{m} {s} {lang}", gate))

p("# M63 report — MTP-ON vs predictor-OFF on the tg1 agentic axis (both picks, k=2)\n")
for note in gate_notes:
    p(note)
prov = [f"{m} {lang} {s} {arm}" for (m, lang, s, arm), (_, rep) in data.items()
        if rep["per_model"].get(m, {}).get("provisional")]
if prov:
    p("**PROVISIONAL:** cells with unaudited web fetches: " + "; ".join(prov) + "\n")
p("## Per leg, acc_strict@budget\n")
p("| model | lang | session | ON | OFF | ON nonconv | OFF nonconv | ON wall h | OFF wall h | ON out tokens | OFF out tokens |")
p("|---|---|---|---|---|---|---|---|---|---|---|")
for m in (P1, P2):
    for s in SESS:
        for lang in LANGS:
            (ron, aon), (roff, aoff) = data[(m, lang, s, "ON")], data[(m, lang, s, "OFF")]
            k = lambda rs: {r["nonconv_kind"] for r in rs} - {None}  # noqa: E731
            sk = lambda rep: sum(sum(v) for v in rep["strict_items"].values())  # noqa: E731
            tok = lambda rs: sum((r.get("gate") or {}).get("output_tokens_completed") or 0 for r in rs)  # noqa: E731
            p(f"| {m} | {lang} | {s} | {sk(aon)}/{len(aon['strict_items'])} | {sk(aoff)}/{len(aoff['strict_items'])} | "
              f"{sorted(k(ron)) or '—'} | {sorted(k(roff)) or '—'} | {sum(r['wall_s'] for r in ron) / 3600:.2f} | "
              f"{sum(r['wall_s'] for r in roff) / 3600:.2f} | {tok(ron)} | {tok(roff)} |")

p("\n## Paired ON−OFF (pre-registered)\n")
for m in (P1, P2):
    for s in SESS:
        family(f"{m}, {s}: all rows", [(lang, data[(m, lang, s, 'ON')][1]["strict_items"],
                                         data[(m, lang, s, 'OFF')][1]["strict_items"]) for lang in LANGS],
               names=("ON", "OFF"))
for m in (P1, P2):
    for s in SESS:
        pairs, dropped = [], []
        for lang in LANGS:
            hit = {r["id"] for arm in ARMS for r in data[(m, lang, s, arm)][0] if r.get("nonconv_kind") == "client_inactivity"}
            dropped += sorted(hit)
            a = {k: v for k, v in data[(m, lang, s, "ON")][1]["strict_items"].items() if k not in hit}
            b = {k: v for k, v in data[(m, lang, s, "OFF")][1]["strict_items"].items() if k not in hit}
            pairs.append((lang, a, b))
        family(f"{m}, {s}: excluding client_inactivity items (dropped {dropped or 'none'})", pairs, names=("ON", "OFF"))

p("\n## P293: ON outcome of every OFF client_inactivity item\n")
p("| model | session | item | OFF | ON kind | ON passed | ON wall s | ON output tokens |")
p("|---|---|---|---|---|---|---|---|")
for (m, lang, s, arm), (rows, _) in data.items():
    if arm != "OFF":
        continue
    on = {r["id"]: r for r in data[(m, lang, s, "ON")][0]}
    for r in rows:
        if r.get("nonconv_kind") == "client_inactivity":
            o = on.get(r["id"], {})
            p(f"| {m} | {s} | {r['id']} | client_inactivity | {o.get('nonconv_kind') or 'converged'} | {o.get('passed')} | "
              f"{o.get('wall_s', 0):.0f} | {(o.get('gate') or {}).get('output_tokens_completed')} |")

p("\n## Discordant items (strict)\n")
p("| model | session | item | ON | OFF | ON kind | OFF kind |")
p("|---|---|---|---|---|---|---|")
for m in (P1, P2):
    for s in SESS:
        for lang in LANGS:
            a, b = data[(m, lang, s, "ON")][1]["strict_items"], data[(m, lang, s, "OFF")][1]["strict_items"]
            kon = {r["id"]: r.get("nonconv_kind") for r in data[(m, lang, s, "ON")][0]}
            koff = {r["id"]: r.get("nonconv_kind") for r in data[(m, lang, s, "OFF")][0]}
            for i in sorted(set(a) & set(b)):
                if a[i][0] != b[i][0]:
                    p(f"| {m} | {s} | {i} | {a[i][0]} | {b[i][0]} | {kon.get(i) or '—'} | {koff.get(i) or '—'} |")

p("\n## Reload control (pick 1, fresh instance, s1 seed)\n")
for arm in ARMS:
    rl = chain_rows.read_rows(chain_rows.stored_path(RES / P1, "python", ARMS[arm], "reload"))
    s1 = {r["id"]: r for r in data[(P1, "python", "s1", arm)][0]}
    st = lambda r: int(bool(r.get("passed")) and not r.get("nonconv_kind"))  # noqa: E731
    p(f"- {arm}: reload strict {sum(st(r) for r in rl)}/{len(rl)}; agreement with s1 on the same items "
      f"{sum(st(r) == st(s1[r['id']]) for r in rl)}/{len(rl)}")

p("\n## Session totals (descriptive; runaway tax in tokens, C71)\n")
p("| model | session | ON strict | OFF strict | ON wall h | OFF wall h | speed-up | ON output tokens | OFF output tokens |")
p("|---|---|---|---|---|---|---|---|---|")
for m in (P1, P2):
    for s in SESS:
        tot = {}
        for arm in ARMS:
            rs = [r for lang in LANGS for r in data[(m, lang, s, arm)][0]]
            reps = [data[(m, lang, s, arm)][1] for lang in LANGS]
            tot[arm] = (sum(sum(sum(v) for v in rep["strict_items"].values()) for rep in reps),
                        sum(len(rep["strict_items"]) for rep in reps), sum(r["wall_s"] for r in rs) / 3600,
                        sum((r.get("gate") or {}).get("output_tokens_completed") or 0 for r in rs))
        on, off = tot["ON"], tot["OFF"]
        p(f"| {m} | {s} | {on[0]}/{on[1]} | {off[0]}/{off[1]} | {on[2]:.2f} | {off[2]:.2f} | {off[2] / on[2]:.2f}× | "
          f"{on[3]} | {off[3]} |")
p("\nOutput tokens are charged (completed requests); OFF `client_inactivity` requests streamed ≈ 70–79K uncharged tokens each (C154).")

Path(__file__).with_name("M63_REPORT.md").write_text("\n".join(out) + "\n")
