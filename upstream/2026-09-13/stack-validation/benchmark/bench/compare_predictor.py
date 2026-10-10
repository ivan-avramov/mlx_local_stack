"""Paired same-model, same-items, ON-vs-OFF predictor comparison (M40).

`compare.py` REFUSES whenever `runtime.draft_kind` differs between the two sides — the correct
default for a general cross-MODEL comparison, because draft/suffix decoding changes the
generated TEXT (docs/serving-path.md), so an unnoticed draft mismatch would silently turn a
model comparison into a (model x serving-path) composite. `compare.py` also only WARNS on a
handful of axes (temperature, top_p/top_k/min_p, penalties, kv_bits, kv_quant_scheme, ...)
because those are legitimate per-MODEL tune choices in a cross-model comparison.

M40 needs the mirror image of BOTH rules: the SAME model, the SAME items and samples, at two
tunes that differ in `draft_kind` ON PURPOSE (predictor ON vs OFF) and NOTHING ELSE — including
the axes compare.py treats as a per-model tune choice, because here there is only one model and
one tune otherwise, so a difference on any of them is a harness drift, not an intended design.
This module reuses compare.py's own field-classification tuples (so the two tools cannot
silently drift apart on what counts as output-determining) but folds every WARN-tier tuple into
its must-match set, and inverts the one rule (`draft_kind`) that exists to keep the tools apart.
"""
import argparse
import json
import random
import sys

from . import compare as CMP
from . import convergence, generate, grade, provenance, rowschema, stats, traces

# Sampling: EVERY fingerprinted sampling key must match — compare.py's _TUNE_SAMPLING_WARN
# (temperature, top_p, top_k, min_p, presence_penalty, repetition_penalty) is WARN-only there
# because different MODELS legitimately run different operating points; here it is the SAME
# model at the SAME tune otherwise, so that exemption does not apply.
_SAMPLING_MUST_MATCH = tuple(CMP._MUST_MATCH_SAMPLING) + tuple(CMP._TUNE_SAMPLING_WARN)

# KV: every fingerprinted kv key, for the same reason (_TUNE_KV_WARN, _CAP_BINDING_KV,
# _CROSS_MODEL_IDENTITY_KV, _MUST_MATCH_KV — see test_every_fingerprint_key_is_classified_here).
_KV_MUST_MATCH = (tuple(CMP._TUNE_KV_WARN) + tuple(CMP._CAP_BINDING_KV)
                 + tuple(CMP._CROSS_MODEL_IDENTITY_KV) + tuple(CMP._MUST_MATCH_KV))
# kv_prealloc_tokens is deliberately OUTSIDE the correctness fingerprint (provenance.py: "the KV
# cap is an EXTERNAL ceiling... text-invariant") but this tool also reports tokens/wall/decode-tps
# RATIOS, and prealloc alone is proven to move wall-clock (24.7 vs 27.8s, 2026-08-14 OFAT) — so it
# is checked here anyway, kept in its own tuple so the fingerprint-parity test can still assert
# `_KV_MUST_MATCH` exactly equals the fingerprinted kv keys.
_KV_HARDWARE_EXTRA = ("kv_prealloc_tokens",)

# Runtime: every fingerprinted runtime key except draft_kind (compare.py's
# _SERVING_PATH_RUNTIME = (apc_enabled, draft_kind); apc_enabled joins the must-match set here,
# draft_kind is handled separately below because it must DIFFER, not match).
_RUNTIME_MUST_MATCH = tuple(CMP._MUST_MATCH_RUNTIME) + ("apc_enabled",)

# A nonzero presence/repetition penalty silently disables suffix speculation FOR THAT REQUEST
# (mlx-vlm generate/ar.py:163, `_suffix_structured_fallback`) — under an ON/OFF predictor pair
# this would mean the non-off arm secretly ran plain decode on the affected rows, invisibly to
# the registry-derived draft_kind. Refused outright (regardless of whether the two sides MATCH on
# the penalty value — a matched nonzero penalty is just as broken as a mismatched one).
_PENALTY_FIELDS = ("presence_penalty", "repetition_penalty")

# Relabel stats.paired_delta's generic positional a_better/b_better (it is called (B, A) below,
# so its "a" is our B) to name the actual tune instead of the function's argument order.
_VERDICT_RELABEL = {"a_better": "tune_b_better", "b_better": "tune_a_better",
                    "equivalent": "equivalent", "inconclusive": "inconclusive"}


def _refuse(reason):
    return {"comparable": False, "reason": reason}


def _manifest_diffs(ma, mb):
    """Every output-determining mismatch between manifests A and B EXCEPT `draft_kind` (checked
    separately in `_gate`, and required to DIFFER) and `probe_timeout_s` (needs rows; checked
    separately by `_probe_timeout_gate` once rows are available). Returns (diffs, warnings) —
    diffs are fatal, warnings are recorded but do not refuse."""
    diffs, warnings = [], []
    sa, sb = ma.get("sampling") or {}, mb.get("sampling") or {}
    kva, kvb = ma.get("kv") or {}, mb.get("kv") or {}
    ra, rb = ma.get("runtime") or {}, mb.get("runtime") or {}

    if ma.get("box") != mb.get("box"):
        diffs.append(f"box differs ({ma.get('box')!r} vs {mb.get('box')!r}) — this tool also "
                     f"reports hardware-sensitive ratios (tokens/wall/decode_tps)")

    for k in _SAMPLING_MUST_MATCH:
        if sa.get(k) != sb.get(k):
            diffs.append(f"sampling.{k} differs ({sa.get(k)!r} vs {sb.get(k)!r})")
    for k in _PENALTY_FIELDS:
        va, vb = sa.get(k) or 0, sb.get(k) or 0
        if va or vb:
            diffs.append(f"sampling.{k} is nonzero ({va!r} vs {vb!r}) — a nonzero penalty "
                         f"silently disables speculation for its requests (mlx-vlm "
                         f"generate/ar.py:163, _suffix_structured_fallback), which would make "
                         f"the non-off arm secretly run plain decode regardless of draft_kind")
    for k in _KV_MUST_MATCH + _KV_HARDWARE_EXTRA:
        if kva.get(k) != kvb.get(k):
            diffs.append(f"kv.{k} differs ({kva.get(k)!r} vs {kvb.get(k)!r})")
    for k in _RUNTIME_MUST_MATCH:
        if ra.get(k) != rb.get(k):
            diffs.append(f"runtime.{k} differs ({ra.get(k)!r} vs {rb.get(k)!r})")

    # Serving-path (C47): the tree hash when either side can produce one, else the raw commit
    # sha — same fallback compare.py's DEPLOYED CODE block uses (compare.py:218-256), ported via
    # `provenance.serving_path_for` rather than re-deriving it from the raw submodule dict.
    ga = (ma.get("git") or {}).get("submodules") or {}
    gb = (mb.get("git") or {}).get("submodules") or {}
    if not ga and not gb:
        warnings.append("deployed-code shas unrecorded on both sides — cannot rule out a "
                        "code-version composite (pre-provenance rows)")
    else:
        spa, spb = provenance.serving_path_for(ma), provenance.serving_path_for(mb)
        for k in ("src/mlx-vlm", "src/mlx-serve"):
            va, vb = ga.get(k), gb.get(k)
            ha, hb = spa.get(k), spb.get(k)
            if ha is not None and hb is not None:
                if ha != hb:
                    diffs.append(f"serving path differs at {k} ({ha[:12]} vs {hb[:12]})")
                continue
            if va and vb and va != vb:
                diffs.append(f"deployed code differs at {k} ({va[:12]} vs {vb[:12]})")
            elif bool(va) != bool(vb):
                warnings.append(f"{k} sha recorded on only one side ({va!r} vs {vb!r}) — cannot "
                                f"rule out a code-version composite")
    return diffs, warnings


def _probe_timeout_gate(ma, mb, rows_a, rows_b, tune_a, tune_b):
    """Port of compare.py's probe_timeout_s binding rule (compare.py:365-383): the client's
    patience decides which draws become DNFs, so it is output-determining only for a draw that
    actually REACHED it — refuse only when the smaller bound COULD have bound. Returns
    (fatal_reason|None, warning|None)."""
    pt_a = (ma.get("runtime") or {}).get("probe_timeout_s")
    pt_b = (mb.get("runtime") or {}).get("probe_timeout_s")
    if pt_a == pt_b:
        return None, None
    smaller = min([p for p in (pt_a, pt_b) if p], default=None)
    bound_rows = [f"{tune}: {r.get('id')}"
                  for tune, rr in ((tune_a, rows_a), (tune_b, rows_b)) for r in rr
                  if r.get("error_kind") == "probe_timeout"
                  or (smaller and (r.get("wall_s") or 0) >= CMP.PROBE_BOUND_NEAR * smaller)]
    if bound_rows:
        return (f"probe_timeout_s differs ({pt_a} vs {pt_b}) and the smaller bound COULD HAVE "
               f"BOUND — draws that ran to it are recorded as DNFs, which is a harness event, "
               f"not a predictor property (e.g. {bound_rows[:3]})"), None
    return None, (f"probe_timeout_s differs ({pt_a} vs {pt_b}) but never bound (no draw came "
                 f"near the smaller bound) — rows are bound-invariant")


def _gate(model, bench, tune_a, tune_b):
    """Every comparability check this tool runs, short of the actual scoring. Returns a refusal
    dict (`_refuse(...)`) or `{"comparable": True, "tune_a", "tune_b", "rows_a", "rows_b",
    "n_items", "draft_a", "draft_b", "ma", "mb", "warnings"}`.
    """
    tune_a, tune_b = generate.validate_tune(tune_a), generate.validate_tune(tune_b)
    ma, mb = CMP._manifest(model, bench, tune=tune_a), CMP._manifest(model, bench, tune=tune_b)
    if ma is None or mb is None:
        missing = [t for t, m in ((tune_a, ma), (tune_b, mb)) if m is None]
        return _refuse(f"missing provenance manifest for tune(s) {', '.join(map(str, missing))}")

    ra_rt, rb_rt = ma.get("runtime") or {}, mb.get("runtime") or {}
    draft_a, draft_b = ra_rt.get("draft_kind"), rb_rt.get("draft_kind")
    if draft_a is None or draft_b is None:
        return _refuse(f"draft_kind is unrecorded on at least one side (tune {tune_a}={draft_a!r}, "
                       f"tune {tune_b}={draft_b!r}) — compare_predictor exists to measure a known "
                       f"predictor ON/OFF delta and cannot when the state is unobserved")
    if draft_a == draft_b:
        return _refuse(f"draft_kind is the SAME on both tunes ({draft_a!r}) — compare_predictor "
                       f"is for a same-model, DIFFERENT-predictor-state pair; use compare.py for "
                       f"a same-state comparison")

    diffs, warnings = _manifest_diffs(ma, mb)
    if diffs:
        return _refuse(f"tune {tune_a} vs {tune_b} differ on output-determining fields other "
                       f"than draft_kind — not a clean predictor ON/OFF pair: " + "; ".join(diffs))

    rows_a = grade._rows(model, bench, tune=tune_a)
    rows_b = grade._rows(model, bench, tune=tune_b)
    if not rows_a or not rows_b:
        empty = [t for t, r in ((tune_a, rows_a), (tune_b, rows_b)) if not r]
        return _refuse(f"no results for tune(s) {', '.join(empty)}")

    ids_a, ids_b = {r["id"] for r in rows_a}, {r["id"] for r in rows_b}
    if ids_a != ids_b:
        diff = sorted((ids_a - ids_b) | (ids_b - ids_a))[:6]
        return _refuse(f"item id sets differ ({len(ids_a - ids_b)} only in tune {tune_a}, "
                       f"{len(ids_b - ids_a)} only in tune {tune_b}; e.g. {diff}) — a paired "
                       f"ON/OFF comparison needs the SAME items on both sides")

    keys_a = {rowschema.row_key(r) for r in rows_a}
    keys_b = {rowschema.row_key(r) for r in rows_b}
    if keys_a != keys_b:
        diff = sorted(str(k) for k in (keys_a - keys_b) | (keys_b - keys_a))[:6]
        return _refuse(f"sample sets differ within the shared items (tune {tune_a} vs "
                       f"{tune_b}); e.g. {diff} — a paired comparison needs the SAME (item, "
                       f"sample) draws on both sides")

    pt_fatal, pt_warning = _probe_timeout_gate(ma, mb, rows_a, rows_b, tune_a, tune_b)
    if pt_fatal:
        return _refuse(pt_fatal)
    if pt_warning:
        warnings.append(pt_warning)

    return {"comparable": True, "tune_a": tune_a, "tune_b": tune_b,
            "rows_a": rows_a, "rows_b": rows_b, "n_items": len(ids_a),
            "draft_a": draft_a, "draft_b": draft_b, "ma": ma, "mb": mb, "warnings": warnings}


def _numeric_per_item(rows, field):
    out = {}
    for r in rows:
        v = r.get(field)
        if v is None:
            continue
        out.setdefault(r["id"], []).append(float(v))
    return out


def _draft_acceptance(rows):
    """Draft-acceptance telemetry over rows carrying a `draft` field with a nonzero `draft_n`:
    both the MEAN of each row's own ratio (draft_n_accepted/draft_n) and the POOLED ratio
    (sum(accepted)/sum(n) across rows) — they differ whenever rows carry very different draft_n,
    and reporting only one hides that. None when no row carries usable telemetry (plain decode,
    or a pre-M34 row)."""
    accepted_total = n_total = 0
    ratios = []
    for d in (r.get("draft") or {} for r in rows):
        n = d.get("draft_n")
        if not n:
            continue
        acc = d.get("draft_n_accepted") or 0
        ratios.append(acc / n)
        accepted_total += acc
        n_total += n
    if not ratios:
        return None
    return {"mean_of_ratios": round(sum(ratios) / len(ratios), 4),
           "pooled_ratio": round(accepted_total / n_total, 4) if n_total else None,
           "n_rows": len(ratios)}


def _discordant(pa, pb):
    """Count of shared items whose per-item mean score differs between the two arms — the
    general form (for graded/multi-sample items) of the binary discordant-pair count
    `stats.mde`'s p_d is about; only discordant items carry information about a delta."""
    ids = set(pa) & set(pb)
    return sum(1 for i in ids
               if (sum(pa[i]) / len(pa[i])) != (sum(pb[i]) / len(pb[i])))


def _unpairable_reason(pa, pb, label):
    """None if `pa`/`pb` ({item_id: [scores]}, `pa` = tune_a's, `pb` = tune_b's) share the same
    non-empty item-id set — else a clear refusal reason.

    Guards `stats.paired_delta`'s uncaught ValueError: `_gate` already checks the RAW rows carry
    the same (id, sample) keys on both sides, but `grade.grade`'s non-strict `items` DROPS error
    rows entirely (`strict_items` does not) — so an error/probe_timeout row on only ONE arm can
    still leave the two per-item score vectors asymmetric for the "acc" metric even though the
    raw rows matched."""
    ids_a = {i for i, d in pa.items() if d}
    ids_b = {i for i, d in pb.items() if d}
    if not ids_a or not ids_b:
        empty = [t for t, s in (("tune_a", ids_a), ("tune_b", ids_b)) if not s]
        return f"{label}: no scored items on {' and '.join(empty)}"
    if ids_a != ids_b:
        diff = sorted((ids_a - ids_b) | (ids_b - ids_a))[:6]
        return (f"{label}: per-item score sets differ between tune_a and tune_b "
               f"({len(ids_a - ids_b)} only in tune_a, {len(ids_b - ids_a)} only in tune_b; "
               f"e.g. {diff}) — likely an error/probe_timeout row scored on only one side "
               f"despite matching (id, sample) rows")
    return None


def _paired_metric(pa, pb, *, iters, seed, margin):
    """B-A paired cluster-bootstrap delta on a {id: [scores]} pair (`pa` = tune_a, `pb` =
    tune_b), with stats.paired_delta's generic a_better/b_better relabelled to name the tune
    (see _VERDICT_RELABEL), plus each arm's own point estimate (`stats.pass_at_1`)."""
    d = stats.paired_delta(pb, pa, iters=iters, seed=seed, margin=margin)
    d["verdict"] = _VERDICT_RELABEL[d["verdict"]]
    d["discordant"] = _discordant(pa, pb)
    d["a"] = stats.pass_at_1(pa)
    d["b"] = stats.pass_at_1(pb)
    return d


def _paired_ratio(per_item_a, per_item_b, *, iters=4000, seed=0):
    """Paired bootstrap CI for mean(B)/mean(A) over the shared item set — same two-stage
    resampling as `stats.paired_delta` (item ids resampled once and shared across arms; each
    arm's own draws resampled independently), but for a RATIO statistic (tokens-per-task,
    wall-clock, decode-tps) instead of a difference. `stats.paired_delta` itself only computes
    differences, so this is a small local analogue rather than a reuse. `n_reps_used` records how
    many of `iters` replicates actually contributed (a replicate whose resampled tune_a mean is
    exactly 0 is dropped to avoid a division by zero — visible here rather than silently
    shrinking the effective iteration count)."""
    ids = sorted(set(i for i, d in per_item_a.items() if d)
                & set(i for i, d in per_item_b.items() if d))
    if not ids:
        return {"point": None, "lo": None, "hi": None, "iters": iters, "n_items": 0,
               "n_reps_used": 0}
    a_draws = [list(per_item_a[i]) for i in ids]
    b_draws = [list(per_item_b[i]) for i in ids]
    n = len(ids)
    point_a = sum(sum(d) / len(d) for d in a_draws) / n
    point_b = sum(sum(d) / len(d) for d in b_draws) / n
    point = (point_b / point_a) if point_a else None
    rng = random.Random(seed)
    reps = []
    for _ in range(iters):
        sa = sb = 0.0
        for _ in range(n):
            idx = rng.randrange(n)                # ONE item index for both arms => paired
            da, db = a_draws[idx], b_draws[idx]
            sa += sum(da[rng.randrange(len(da))] for _ in range(len(da))) / len(da)
            sb += sum(db[rng.randrange(len(db))] for _ in range(len(db))) / len(db)
        ma_, mb_ = sa / n, sb / n
        if ma_:
            reps.append(mb_ / ma_)
    reps.sort()
    lo = stats._percentile(reps, 0.025) if reps else None
    hi = stats._percentile(reps, 0.975) if reps else None
    return {"point": point, "lo": lo, "hi": hi, "iters": iters, "n_items": n,
           "n_reps_used": len(reps)}


def _verdict(chosen, margin):
    """PASS/FAIL/INCONCLUSIVE from one metric's paired_delta result.

    PRECEDENCE: PASS is evaluated BEFORE FAIL — a significant but sub-margin regression (e.g. CI
    [-0.03, -0.01] at margin 0.05) reads PASS: that is the <=5% lossy-lever rule (AGENTS.md), not a
    statistical tie, and it is the likely shape of a small real predictor cost. Strict inequalities match
    `stats.paired_delta`'s own "equivalent" verdict boundary exactly (`-margin < lo and hi <
    margin`) — a CI edge sitting AT the margin does not count as "within" it.
    """
    lo, hi, delta = chosen["lo"], chosen["hi"], chosen["delta"]
    if -margin < lo and hi < margin:
        return "PASS"
    if hi < 0 or delta < -margin:
        return "FAIL"
    return "INCONCLUSIVE"


def compare_predictor(model, bench, tune_a, tune_b, *, key="acc_strict", margin=0.05,
                      iters=4000, seed=0):
    """The full M40 paired ON-vs-OFF report for one (model, bench), or a refusal.

    `key` picks which delta ("acc" or "acc_strict") the top-line PASS/FAIL/INCONCLUSIVE verdict
    is read off (see `_verdict`); both are always computed and reported. Never writes a file or
    prints anything — that is `main()`'s job, so this stays a plain, testable function.
    """
    if key not in ("acc", "acc_strict"):
        raise ValueError(f"compare_predictor: key must be 'acc' or 'acc_strict', got {key!r}")

    gate = _gate(model, bench, tune_a, tune_b)
    if not gate["comparable"]:
        return gate
    tune_a, tune_b = gate["tune_a"], gate["tune_b"]
    rows_a, rows_b = gate["rows_a"], gate["rows_b"]
    warnings = list(gate["warnings"])

    score_a = grade.grade(bench, model, tune=tune_a)
    score_b = grade.grade(bench, model, tune=tune_b)
    if score_a.get("strict_items") is None or score_b.get("strict_items") is None:
        return _refuse("acc_strict per-item vector missing on at least one tune (grader too old, "
                       "or a cached score) — re-grade to populate it")

    pa_acc, pb_acc = CMP._per_item(score_a), CMP._per_item(score_b)
    pa_strict, pb_strict = CMP._per_item(score_a, strict=True), CMP._per_item(score_b, strict=True)

    for label, pa, pb in (("acc", pa_acc, pb_acc), ("acc_strict", pa_strict, pb_strict)):
        err = _unpairable_reason(pa, pb, label)
        if err:
            return _refuse(err)

    deltas = {
        "acc": _paired_metric(pa_acc, pb_acc, iters=iters, seed=seed, margin=margin),
        "acc_strict": _paired_metric(pa_strict, pb_strict, iters=iters, seed=seed, margin=margin),
    }
    verdict = _verdict(deltas[key], margin)

    tokens_ratio = _paired_ratio(_numeric_per_item(rows_a, "completion_tokens"),
                                 _numeric_per_item(rows_b, "completion_tokens"),
                                 iters=iters, seed=seed)
    wall_ratio = _paired_ratio(_numeric_per_item(rows_a, "wall_s"),
                               _numeric_per_item(rows_b, "wall_s"), iters=iters, seed=seed)
    decode_a, decode_b = (_numeric_per_item(rows_a, "decode_tps"),
                          _numeric_per_item(rows_b, "decode_tps"))
    decode_ratio = _paired_ratio(decode_a, decode_b, iters=iters, seed=seed)
    conv_a, conv_b = convergence.audit(rows_a), convergence.audit(rows_b)
    draft_accept_a, draft_accept_b = _draft_acceptance(rows_a), _draft_acceptance(rows_b)

    for tune, draft_kind, accept in ((tune_a, gate["draft_a"], draft_accept_a),
                                     (tune_b, gate["draft_b"], draft_accept_b)):
        if draft_kind != "off" and accept is None:
            warnings.append(f"tune {tune} has draft_kind={draft_kind!r} but no row carries "
                            f"draft_n telemetry — cannot verify the predictor actually ran")

    ma, mb = gate["ma"], gate["mb"]
    registry_sha = {tune_a: (ma.get("registry") or {}).get("sha256"),
                    tune_b: (mb.get("registry") or {}).get("sha256")}

    return {
        "comparable": True, "model": model, "bench": bench,
        "tune_a": tune_a, "tune_b": tune_b, "draft_a": gate["draft_a"], "draft_b": gate["draft_b"],
        "key": key, "margin": margin, "n_items": gate["n_items"], "verdict": verdict,
        "delta": deltas,
        "tokens_per_task_ratio_b_over_a": tokens_ratio,
        "wall_ratio_b_over_a": wall_ratio,
        "decode_tps": {"mean": {tune_a: stats.pass_at_1(decode_a), tune_b: stats.pass_at_1(decode_b)},
                      "ratio_b_over_a": decode_ratio},
        "convergence": {tune_a: conv_a, tune_b: conv_b},
        "nonconv_kinds": {tune_a: traces.summarize(rows_a)["kinds"],
                         tune_b: traces.summarize(rows_b)["kinds"]},
        "draft_acceptance": {tune_a: draft_accept_a, tune_b: draft_accept_b},
        "registry_sha": registry_sha,
        "warnings": warnings,
    }


def _out_path(model, bench, tune_a, tune_b):
    return (generate.result_path(model, bench, tune=generate.validate_tune(tune_b)).parent
            / f"{bench}.{tune_b}.vs.{tune_a}.json")


def _summary_line(result):
    d = result["delta"][result["key"]]
    return (f"{result['verdict']}: {result['model']} {result['bench']} "
            f"{result['tune_b']}(draft={result['draft_b']}) vs "
            f"{result['tune_a']}(draft={result['draft_a']}) — {result['key']} "
            f"delta(B-A)={d['delta']:+.4f} CI[{d['lo']:+.4f},{d['hi']:+.4f}] "
            f"n_items={result['n_items']} margin=±{result['margin']:.2f}")


def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m bench.compare_predictor",
        description="Paired same-model, same-items, different-tune predictor ON/OFF comparison "
                    "(M40). Refuses unless the two tunes differ ONLY in runtime.draft_kind.")
    p.add_argument("--model", required=True)
    p.add_argument("--bench", required=True)
    p.add_argument("--tune-a", required=True)
    p.add_argument("--tune-b", required=True)
    p.add_argument("--key", default="acc_strict", choices=("acc", "acc_strict"))
    p.add_argument("--margin", type=float, default=0.05)
    p.add_argument("--iters", type=int, default=4000)
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    result = compare_predictor(args.model, args.bench, args.tune_a, args.tune_b,
                               key=args.key, margin=args.margin, iters=args.iters, seed=args.seed)
    if not result["comparable"]:
        print(f"REFUSED: {result['reason']}", file=sys.stderr)
        return 1
    out_path = _out_path(args.model, args.bench, args.tune_a, args.tune_b)
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(_summary_line(result))
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
