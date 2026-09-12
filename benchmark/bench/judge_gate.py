"""Pre-registered reliability gate + ranking for the M38 judge panel —
`docs/judge-panel-c.md` "Reliability gate" and "Ranking".

Every gate metric here is computed from the ANCHOR subset of `verdicts.jsonl` only (the spec's
"re-run the gate only (anchors cost judge calls, not GPU)" implies the gate never needs the
candidate rows — see the module docstring note on this resolved ambiguity in the CLI report).
Ranking runs ONLY if the gate passes, over the CANDIDATE subset (`anchor_type is None`).
"""
import json
import math
import os
from collections import Counter
from itertools import combinations

from . import judge_pairwise as JP
from . import stats

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

THRESHOLDS = {
    "degrade_accuracy": 0.85,             # >=
    "order_flip_rate": 0.30,              # <= (worst judge)
    "panel_kappa_between_orders": 0.60,   # >=
    "krippendorff_alpha": 0.50,           # >=
    "identity_tie_rate": 0.80,            # >=
    # verbosity_shorter_preference_rate <= degrade_accuracy (dynamic, not a fixed constant)
}

TOST_MARGIN = 0.05


# ------------------------------------------------------------------------------------ loading
def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def group_verdicts_by_pair(verdict_rows):
    """{pair_id: {(order, judge): choice}}."""
    out = {}
    for row in verdict_rows:
        out.setdefault(row["pair_id"], {})[(row["order"], row["judge"])] = row["choice"]
    return out


def _normalize(order, choice):
    if order == "BA" and choice in ("A", "B"):
        return {"A": "B", "B": "A"}[choice]
    return choice


# ------------------------------------------------------------------------ per-pair aggregation
def per_judge_verdict(by_order_judge, judge):
    """This judge's verdict for one pair: agreement of its two normalized orders, else 'tie'.
    Either order missing/unparsed -> 'tie' (never guessed)."""
    ab = _normalize("AB", by_order_judge.get(("AB", judge)))
    ba = _normalize("BA", by_order_judge.get(("BA", judge)))
    if ab is None or ba is None:
        return "tie"
    return ab if ab == ba else "tie"


def panel_verdict(per_judge_verdicts):
    """Majority over judges' verdicts; no strict majority (e.g. 1-1-1) -> 'tie'."""
    counts = Counter(per_judge_verdicts)
    if not counts:
        return "tie"
    best = max(counts.values())
    winners = [k for k, c in counts.items() if c == best]
    return winners[0] if len(winners) == 1 else "tie"


def order_is_flip(by_order_judge, judge):
    """True if this judge's two normalized order choices disagree (or either is unparsed —
    an unparsed order cannot CONFIRM consistency, so it counts against reliability)."""
    ab = _normalize("AB", by_order_judge.get(("AB", judge)))
    ba = _normalize("BA", by_order_judge.get(("BA", judge)))
    if ab is None or ba is None:
        return True
    return ab != ba


# --------------------------------------------------------------------------- Cohen's kappa
def cohen_kappa(rater_a, rater_b, categories=None):
    """Cohen's kappa for two same-length label sequences. None if there is nothing to compare
    (n=0). kappa = (Po - Pe) / (1 - Pe); if Pe == 1 (impossible to disagree by chance — a
    single, shared category), returns 1.0 iff observed agreement is also perfect, else 0.0."""
    n = len(rater_a)
    if n != len(rater_b):
        raise ValueError("cohen_kappa: rater sequences must be the same length")
    if n == 0:
        return None
    cats = categories or sorted(set(rater_a) | set(rater_b))
    po = sum(1 for a, b in zip(rater_a, rater_b) if a == b) / n
    ca, cb = Counter(rater_a), Counter(rater_b)
    pe = sum((ca.get(c, 0) / n) * (cb.get(c, 0) / n) for c in cats)
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1 - pe)


# ---------------------------------------------------------------------- Krippendorff's alpha
def krippendorff_alpha(units):
    """Krippendorff's alpha (nominal metric) over {unit_id: [value, ...]} (one value per
    rater; `None` entries are missing and dropped). Units left with <2 valid values are
    unpairable and excluded. Coincidence-matrix formulation (Hayes & Krippendorff 2007):

        n = sum of pairable values; o_ck = weighted coincidence counts; n_c = row sums
        Do = (1/n) * sum_{c!=k} o_ck            (observed disagreement)
        De = (n^2 - sum_c n_c^2) / (n*(n-1))    (expected disagreement by chance)
        alpha = 1 - Do/De

    Hand-verified: {"u1": ["A","A"], "u2": ["A","B"], "u3": ["B","B"]} -> alpha == 4/9
    (2 raters/unit -> weight 1/(m-1)=1 per ordered pair; o_AA=2, o_AB=o_BA=1, o_BB=2; n=6;
    Do=2/6; De=(36-18)/30=0.6; alpha=1-((2/6)/0.6)=4/9).

    Returns None if there is no pairable data at all. If there is pairable data but zero
    variance (every value identical -> De=0), returns 1.0 (perfect agreement by definition).
    """
    o = Counter()
    n = 0.0
    for values in units.values():
        vs = [v for v in values if v is not None]
        m = len(vs)
        if m < 2:
            continue
        w = 1.0 / (m - 1)
        for i in range(m):
            for j in range(m):
                if i != j:
                    o[(vs[i], vs[j])] += w
        n += m
    if n == 0:
        return None
    n_c = Counter()
    for (c, _k), v in o.items():
        n_c[c] += v
    do = sum(v for (c, k), v in o.items() if c != k) / n
    sq = sum(v * v for v in n_c.values())
    denom = n * (n - 1)
    de = (n * n - sq) / denom if denom else 0.0
    if de == 0:
        return 1.0 if do == 0 else None
    return 1.0 - do / de


# -------------------------------------------------------------------------------- gate metrics
def _anchor_pairs_by_type(pairs, anchor_type):
    return [p for p in pairs if p.get("anchor_type") == anchor_type]


def krippendorff_units_collapsed(anchors, verdicts_by_pair, judges):
    """{pair_id: [per_judge_verdict, ...]} — one value PER JUDGE, already order-collapsed
    (agreement of AB/BA else 'tie'). This is what the gate reported before F7: it measures
    whether judges agree on the FINAL verdict, but an order flip on every judge collapses to
    every judge reporting 'tie' — which reads as perfect judge-to-judge AGREEMENT even though
    the panel is unreliable. Kept for visibility, no longer the gate's pass/fail input."""
    return {p["pair_id"]: [per_judge_verdict(verdicts_by_pair.get(p["pair_id"], {}), j)
                           for j in judges]
            for p in anchors}


def krippendorff_units_raw(anchors, verdicts_by_pair, judges):
    """{pair_id: [normalized_choice, ...]} — one value per (judge, order) RATER (2x as many
    raters per unit as `krippendorff_units_collapsed`), never collapsed across orders. An
    order flip now shows up as the (judge, AB) and (judge, BA) raters disagreeing with each
    other, instead of being silently absorbed into 'tie'/'tie' agreement. This is what the
    gate's `krippendorff_alpha` metric is actually thresholded on (F7)."""
    units = {}
    for pair in anchors:
        by_oj = verdicts_by_pair.get(pair["pair_id"], {})
        vals = []
        for j in judges:
            vals.append(_normalize("AB", by_oj.get(("AB", j))))
            vals.append(_normalize("BA", by_oj.get(("BA", j))))
        units[pair["pair_id"]] = vals
    return units


def _expected_match_rate(anchor_pairs, verdicts_by_pair, judges):
    """Fraction of `anchor_pairs` whose panel verdict equals `expected`. Shared by degrade
    accuracy, verbosity shorter-preference rate, and identity tie rate — all three are exactly
    this computation over a different anchor subset (docs/judge-panel-c.md)."""
    if not anchor_pairs:
        return None
    hits = 0
    for pair in anchor_pairs:
        by_oj = verdicts_by_pair.get(pair["pair_id"], {})
        pv = panel_verdict([per_judge_verdict(by_oj, j) for j in judges])
        if pv == pair["expected"]:
            hits += 1
    return hits / len(anchor_pairs)


NULL_REASONS = ("max_tokens", "refusal", "unparseable")
NULL_SHARE_WARN_THRESHOLD = 0.05


def null_verdict_stats(anchors, verdict_rows, judges):
    """Counts of `choice: null` ANCHOR verdict rows — per judge, per `null_reason`
    (`max_tokens`, `refusal`, or `unparseable` when no `null_reason` was set), plus the null
    share overall and per judge.

    A truncated/refused judge call is graded as BOTH a tie (0.5, via `panel_verdict`) and an
    order flip (via `order_is_flip`) — documented intent (AGENTS.md: a budget-hit is a FAIL
    signal to investigate, never silently absorbed) — but that intent was previously invisible
    in `gate.json`: a client-side `max_tokens`/`output_config` regression could silently drag
    down `order_flip_rate`/kappa/alpha and nobody would know WHY. This block, plus `main()`'s
    WARN line above `NULL_SHARE_WARN_THRESHOLD`, surfaces it.

    Membership is by PAIR ID against `anchors` (like every other gate metric here), not by a
    verdict row's own `anchor_type` field — consistent with `order_is_flip`/`per_judge_verdict`,
    and robust to older verdict rows that predate that field."""
    anchor_pair_ids = {p["pair_id"] for p in anchors}
    anchor_rows = [r for r in verdict_rows if r.get("pair_id") in anchor_pair_ids]
    total = len(anchor_rows)
    by_judge, by_reason, per_judge_total = Counter(), Counter(), Counter()
    null_total = 0
    for r in anchor_rows:
        j = r.get("judge")
        per_judge_total[j] += 1
        if r.get("choice") is None:
            null_total += 1
            by_judge[j] += 1
            by_reason[r.get("null_reason") or "unparseable"] += 1
    by_judge_share = {}
    for j in judges:
        pt = per_judge_total.get(j, 0)
        by_judge_share[j] = (by_judge.get(j, 0) / pt) if pt else None
    return {
        "by_judge": {j: by_judge.get(j, 0) for j in judges},
        "by_judge_share": by_judge_share,
        "by_reason": {r: by_reason.get(r, 0) for r in NULL_REASONS},
        "n_anchor_rows": total,
        "n_null": null_total,
        "share": (null_total / total) if total else None,
    }


def compute_gate(pairs, verdict_rows, judges):
    """All reliability-gate metrics + PASS/FAIL, computed from the ANCHOR pairs only."""
    verdicts_by_pair = group_verdicts_by_pair(verdict_rows)
    anchors = [p for p in pairs if p.get("anchor_type") is not None]
    degrade = _anchor_pairs_by_type(anchors, "degrade")
    verbosity = _anchor_pairs_by_type(anchors, "verbosity")
    identity = _anchor_pairs_by_type(anchors, "identity")

    degrade_accuracy = _expected_match_rate(degrade, verdicts_by_pair, judges)
    verbosity_rate = _expected_match_rate(verbosity, verdicts_by_pair, judges)
    identity_tie_rate = _expected_match_rate(identity, verdicts_by_pair, judges)

    flip_rates = {}
    for judge in judges:
        flips = [order_is_flip(verdicts_by_pair.get(p["pair_id"], {}), judge) for p in anchors]
        flip_rates[judge] = (sum(flips) / len(flips)) if flips else None

    panel_ab, panel_ba = [], []
    for pair in anchors:
        by_oj = verdicts_by_pair.get(pair["pair_id"], {})
        panel_ab.append(panel_verdict([_normalize("AB", by_oj.get(("AB", j))) for j in judges]))
        panel_ba.append(panel_verdict([_normalize("BA", by_oj.get(("BA", j))) for j in judges]))
    kappa = cohen_kappa(panel_ab, panel_ba) if anchors else None

    units_collapsed = krippendorff_units_collapsed(anchors, verdicts_by_pair, judges)
    units_raw = krippendorff_units_raw(anchors, verdicts_by_pair, judges)
    alpha_collapsed = krippendorff_alpha(units_collapsed) if anchors else None
    alpha_raw = krippendorff_alpha(units_raw) if anchors else None

    worst_flip = max((v for v in flip_rates.values() if v is not None), default=None)

    metrics = {
        "degrade_accuracy": {
            "value": degrade_accuracy, "threshold": THRESHOLDS["degrade_accuracy"],
            "op": ">=", "n": len(degrade),
            "pass": degrade_accuracy is not None
                    and degrade_accuracy >= THRESHOLDS["degrade_accuracy"]},
        "order_flip_rate": {
            "value": flip_rates, "worst": worst_flip, "threshold": THRESHOLDS["order_flip_rate"],
            "op": "<=", "n": len(anchors),
            "pass": worst_flip is not None and worst_flip <= THRESHOLDS["order_flip_rate"]},
        "panel_kappa_between_orders": {
            "value": kappa, "threshold": THRESHOLDS["panel_kappa_between_orders"], "op": ">=",
            "n": len(anchors),
            "pass": kappa is not None and kappa >= THRESHOLDS["panel_kappa_between_orders"]},
        "krippendorff_alpha": {
            # F7: the gate is thresholded on alpha_raw (per-(judge,order) raters, order flips
            # visible as disagreement) — NOT alpha_collapsed (per-judge, order-collapsed,
            # which silently reads a flip as tie/tie agreement). Both are reported.
            "value": alpha_raw, "alpha_raw": alpha_raw, "alpha_collapsed": alpha_collapsed,
            "threshold": THRESHOLDS["krippendorff_alpha"], "op": ">=",
            "n": len(anchors),
            "pass": alpha_raw is not None and alpha_raw >= THRESHOLDS["krippendorff_alpha"]},
        "verbosity_shorter_preference_rate": {
            "value": verbosity_rate, "threshold": degrade_accuracy, "op": "<=",
            "n": len(verbosity),
            "pass": (verbosity_rate is not None and degrade_accuracy is not None
                     and verbosity_rate <= degrade_accuracy)},
        "identity_tie_rate": {
            "value": identity_tie_rate, "threshold": THRESHOLDS["identity_tie_rate"], "op": ">=",
            "n": len(identity),
            "pass": identity_tie_rate is not None
                    and identity_tie_rate >= THRESHOLDS["identity_tie_rate"]},
    }
    overall = all(m["pass"] for m in metrics.values())
    null_verdicts = null_verdict_stats(anchors, verdict_rows, judges)
    return {"metrics": metrics, "overall": "PASS" if overall else "FAIL", "judges": list(judges),
            "null_verdicts": null_verdicts}


# ------------------------------------------------------------------------------------ ranking
def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


P_VALUE_METHOD = "normal approximation from the bootstrap 95% CI half-width"


def _bootstrap_pvalue_vs_half(ci):
    """Two-sided p-value for H0: preference rate == 0.5, from a normal approximation using the
    bootstrap CI half-width as the standard error (CI assumed ~symmetric 95%,
    se = width/(2*1.96)). Floored at `1/iters` (the bootstrap's own resolution — a percentile
    CI built from `iters` replicates cannot honestly claim a p-value finer than that grid, and
    a zero-variance degenerate case must read as "as small as this method can state", never a
    literal 0.0, which would misrepresent exact certainty). None only when the CI itself is
    unavailable (n=0)."""
    point, lo, hi = ci["point"], ci["lo"], ci["hi"]
    if point is None or lo is None or hi is None:
        return None
    floor = 1.0 / ci.get("iters", 10000)
    se = (hi - lo) / (2 * 1.959964)
    if se == 0:
        return 1.0 if point == 0.5 else floor
    z = abs(point - 0.5) / se
    return max(floor, min(1.0, 2.0 * (1.0 - _phi(z))))


def _pair_verdict(point, lo, hi, margin):
    """TOST-style verdict. The equivalence branch is explicitly labeled
    `equivalent_95ci_within_5pp`, not a bare "equivalent": `stats.cluster_bootstrap` has no
    alpha/level argument (checked — only the hardcoded 2.5/97.5 percentiles), so this is a
    95% CI wholly inside +-margin, not a true 90%-CI TOST at the conventional alpha. Naming it
    plainly stops a reader from assuming the stricter 90% convention was used."""
    if lo > 0.5:
        return "m1_better"
    if hi < 0.5:
        return "m2_better"
    if (0.5 - margin) < lo and hi < (0.5 + margin):
        return "equivalent_95ci_within_5pp"
    return "inconclusive"


def _score_a(panel_v):
    if panel_v == "tie":
        return 0.5
    if panel_v == "A":
        return 1.0
    return 0.0


def _family_preference_splits(candidates, verdicts_by_pair, judges):
    """{pair_key: {family: rate_for_model_1|None}} — a simple (non-bootstrapped) per-family
    mean preference rate, diagnostic only (F10/AGENTS.md: "mixed family is mandatory; report
    per-family splits"). A family absent from `judges` contributes None, not a fabricated 0.5."""
    judge_fam = JP.judge_families(judges)
    families = sorted(set(judge_fam.values()) - {None})
    judges_by_family = {fam: [j for j in judges if judge_fam.get(j) == fam] for fam in families}
    per_family_items = {fam: {} for fam in families}   # fam -> (m1,m2) -> {item: [score_m1]}
    for pair in candidates:
        model_a = pair["a_key"].split("::")[0]
        model_b = pair["b_key"].split("::")[0]
        m1, m2 = sorted((model_a, model_b))
        by_oj = verdicts_by_pair.get(pair["pair_id"], {})
        for fam in families:
            pv = panel_verdict([per_judge_verdict(by_oj, j) for j in judges_by_family[fam]])
            score_a = _score_a(pv)
            score_m1 = score_a if model_a == m1 else (1.0 - score_a)
            per_family_items[fam].setdefault((m1, m2), {}).setdefault(pair["item_id"], []) \
                .append(score_m1)

    splits = {}
    for fam, by_pair in per_family_items.items():
        for (m1, m2), per_item in by_pair.items():
            key = f"{m1}__{m2}"
            vals = [v for draws in per_item.values() for v in draws]
            rate = (sum(vals) / len(vals)) if vals else None
            splits.setdefault(key, {})[fam] = rate
    return splits


def compute_ranking(pairs, verdict_rows, judges, seed=0, margin=TOST_MARGIN):
    """Paired preference rate (tie=0.5) per unordered model pair, over the shared items, with
    a two-stage cluster-bootstrap CI (`stats.cluster_bootstrap`), a bootstrap-normal p-value
    vs 0.5, Holm-adjusted across the 6 pairs, and a TOST +-`margin` equivalence flag. Also
    reports a per-JUDGE-FAMILY preference split per pair (point estimate only, no CI — a
    diagnostic for "did one family drive this result", not a ranking input)."""
    verdicts_by_pair = group_verdicts_by_pair(verdict_rows)
    candidates = [p for p in pairs if p.get("anchor_type") is None]

    per_pair_items = {}   # (m1, m2) -> {item_id: [score_for_m1]}
    for pair in candidates:
        model_a = pair["a_key"].split("::")[0]
        model_b = pair["b_key"].split("::")[0]
        m1, m2 = sorted((model_a, model_b))
        by_oj = verdicts_by_pair.get(pair["pair_id"], {})
        pv = panel_verdict([per_judge_verdict(by_oj, j) for j in judges])
        score_a = _score_a(pv)
        score_m1 = score_a if model_a == m1 else (1.0 - score_a)
        per_pair_items.setdefault((m1, m2), {})[pair["item_id"]] = [score_m1]

    family_splits = _family_preference_splits(candidates, verdicts_by_pair, judges)

    models = sorted({m for key in per_pair_items for m in key})
    results = {}
    raw_pvalues = []
    keys_in_order = []
    for m1, m2 in combinations(models, 2):
        per_item = per_pair_items.get((m1, m2), {})
        n_items = len(per_item)
        if n_items == 0:
            continue
        ci = stats.cluster_bootstrap(per_item, seed=seed)
        p_value = _bootstrap_pvalue_vs_half(ci)
        verdict = _pair_verdict(ci["point"], ci["lo"], ci["hi"], margin)
        key = f"{m1}__{m2}"
        results[key] = {
            "model_1": m1, "model_2": m2,
            "preference_rate_model_1": ci["point"], "ci": [ci["lo"], ci["hi"]],
            "p_value": p_value, "p_value_method": P_VALUE_METHOD,
            "verdict": verdict, "n_items": n_items,
            "mde": stats.mde(n_items),
            "family_splits": family_splits.get(key, {}),
        }
        keys_in_order.append(key)
        raw_pvalues.append(p_value if p_value is not None else 1.0)

    if raw_pvalues:
        adjusted = stats.holm(raw_pvalues)
        for key, p_holm in zip(keys_in_order, adjusted):
            results[key]["p_holm"] = p_holm

    return {"margin": margin, "pairs": results,
            "note": "preference rate for model_1 over model_2, tie counted as 0.5; "
                    "MDE is the paired-comparison floor at this n (see stats.mde), not a CI. "
                    "equivalent_95ci_within_5pp uses the 95% cluster-bootstrap CI (no "
                    "alpha/level knob in stats.cluster_bootstrap), not a strict 90% TOST."}


# -------------------------------------------------------------------------------------- usage
def usage_summary(rows_by_model):
    """Per-model tokens/task, mean latency, and runaway share from the generation rows — the
    "alongside" numbers docs/judge-panel-c.md's Ranking section asks for next to preference
    rate (AGENTS.md: never rank on a composite, report the numbers separately)."""
    out = {}
    for model, rows in rows_by_model.items():
        toks = [r["completion_tokens"] for r in rows if r.get("completion_tokens") is not None]
        lat = [r["wall_s"] for r in rows if r.get("wall_s") is not None]
        n = len(rows)
        runaways = sum(1 for r in rows if r.get("nonconv_kind"))
        out[model] = {
            "tokens_per_task": (sum(toks) / len(toks)) if toks else None,
            "latency_s": (sum(lat) / len(lat)) if lat else None,
            "runaway_share": (runaways / n) if n else None,
            "n": n,
        }
    return out


# ------------------------------------------------------------------------------------ CLI/IO
def write_json(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def main(argv=None):
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Compute the M38 judge-panel reliability gate, then (if it passes) rank.")
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--verdicts", required=True)
    ap.add_argument("--judges", nargs="+", default=None)  # None -> opus, sonnet, and the pinned codex judge (see judge_pairwise.CODEX_MODEL)  # allow-shorthand
    ap.add_argument("--out", default=os.path.join(RESULTS, "judge_c_v1"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--models", nargs="+", default=None,
                    help="if given, wires per-model tokens/task, latency and runaway share "
                         "(usage_summary) into ranking.json alongside preference rates")
    ap.add_argument("--tune", default="m38")
    ap.add_argument("--results-dir", default=JP.RESULTS)
    args = ap.parse_args(argv)

    pairs = read_jsonl(args.pairs)
    verdict_rows = read_jsonl(args.verdicts)
    if args.judges is None:
        args.judges = sorted({r.get("judge") for r in verdict_rows if r.get("judge")})
    gate = compute_gate(pairs, verdict_rows, args.judges)
    gate_path = os.path.join(args.out, "gate.json")
    write_json(gate, gate_path)
    print(f"[judge_gate] gate={gate['overall']} -> {gate_path}", flush=True)
    for name, m in gate["metrics"].items():
        print(f"  {name}: value={m['value']} threshold({m['op']})={m['threshold']} "
              f"pass={m['pass']} n={m['n']}", flush=True)
    for name, share in gate["null_verdicts"]["by_judge_share"].items():
        if share is not None and share > NULL_SHARE_WARN_THRESHOLD:
            print(f"[judge_gate] WARN judge={name} null-verdict share {share:.1%} on anchors "
                  f"exceeds {NULL_SHARE_WARN_THRESHOLD:.0%} — a client-side "
                  "max_tokens/output_config truncation can silently fail order_flip_rate/"
                  "kappa/alpha for this judge; investigate before trusting the gate.",
                  flush=True)

    if gate["overall"] != "PASS":
        print("[judge_gate] REFUSING to rank: reliability gate FAILED. Revise the rubric or "
              "panel and re-run the gate (anchors only) before trusting any candidate "
              "preference rate.", file=sys.stderr, flush=True)
        return 1

    ranking = compute_ranking(pairs, verdict_rows, args.judges, seed=args.seed)
    if args.models:
        rows_by_model = JP.load_model_rows(args.models, tune=args.tune,
                                           results_dir=args.results_dir)
        ranking["usage"] = usage_summary(rows_by_model)
    ranking_path = os.path.join(args.out, "ranking.json")
    write_json(ranking, ranking_path)
    print(f"[judge_gate] wrote ranking -> {ranking_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
