"""Paired head-to-head between two models, or an explicit refusal.

Every comparison the campaign has published mixed something — N (aider 5 vs 16 vs 34), item
subsets (one model's first-16 against another's harder 34), boxes, or thinking budgets — and the
notes said so while still ranking on the number. This module makes the refusal mechanical, and
when a comparison IS valid it reports the paired delta with its interval and the axis resolution,
so a difference the sample size cannot support comes back `inconclusive` instead of a rank.

WHICH MISMATCHES ARE FATAL is a judgement, so it is written down rather than left implicit:

  fatal always   different item-id sets (the defect this exists to stop); different
                 thinking_budget or max_tokens (truncation-sensitive metrics move with them)
  fatal always   a different draft/suffix state. Unlike APC it changes the TEXT, not just the
                 latency (ON and OFF are different fixed points at the deployed config), and its
                 absence here is what let every winner-vs-candidate comparison in the corpus be a
                 (model x serving-path) composite. UNOBSERVED on either side warns instead, because
                 no pre-v3 row records it.
  fatal for      a different box, or a different APC state, when the metric is speed/memory
  speed only     (the apples-to-apples rule; APC is worth 34-147x on TTFT)
  NOT fatal      a different per-model temperature. Ornith runs t0.4 and the distill t0.3 because
                 those are each model's tuned operating point. A rule demanding identical sampling
                 would refuse every comparison we actually need — so it is recorded as a warning.
"""
from . import generate, grade, provenance, rowschema, stats

# Metrics whose value depends on the machine and the serving configuration, not just the model.
_HARDWARE_METRICS = ("decode_tps", "prefill_tps", "wall_s", "peak_mem_gb", "etts",
                     "successes_per_hour")

# Sampling keys that MUST match for a comparison to mean anything. `temperature` is deliberately
# absent (see the module docstring).
_MUST_MATCH_SAMPLING = ("thinking_budget", "max_tokens")


def _manifest(model, bench):
    p = generate.result_path(model, bench).with_suffix(".manifest.json")
    if not p.exists():
        return None
    try:
        import json
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001 — an unparseable manifest is unknown provenance
        return None


def _refuse(reason):
    return {"comparable": False, "reason": reason}


def _per_item(score, converged_only=False, rows=None):
    """{id: [score, ...]} from a grader's per-item results."""
    items = score.get("items") or []
    items = [i for i in items if not i.get("contaminated")]
    if converged_only:
        from . import convergence
        conv = {rowschema.row_key(r): convergence.is_converged(r) for r in (rows or [])}
        items = [i for i in items if conv.get((i["id"], i["sample"])) is not False]
    out = {}
    for i in items:
        out.setdefault(i["id"], []).append(float(i["score"]))
    return out


def compare(model_a, model_b, bench, *, metric="acc", margin=0.05, iters=4000, seed=0,
            intersect=False):
    """Compare two models on one bench. Returns either a refusal or a paired verdict.

    `metric` is "acc" (correctness over generated items), "pass_at_1_converged" (which pairs on
    the items BOTH models converged on — conditioning on convergence conditions on a
    model-dependent, easier subset), or the name of a hardware metric, which triggers the
    box/APC checks.
    """
    warnings = []
    ma, mb = _manifest(model_a, bench), _manifest(model_b, bench)
    if ma is None or mb is None:
        missing = [m for m, man in ((model_a, ma), (model_b, mb)) if man is None]
        return _refuse(f"missing provenance manifest for {', '.join(missing)} — unknown "
                       f"provenance must not be compared")

    sa, sb = ma.get("sampling") or {}, mb.get("sampling") or {}
    for k in _MUST_MATCH_SAMPLING:
        if sa.get(k) != sb.get(k):
            return _refuse(f"{k} differs ({sa.get(k)} vs {sb.get(k)}) — truncation-sensitive "
                           f"metrics move with it, so the delta would not be attributable")
    if sa.get("temperature") != sb.get("temperature"):
        warnings.append(f"temperature differs ({sa.get('temperature')} vs {sb.get('temperature')}) "
                        f"— expected when each model runs at its own tuned operating point")

    # DRAFT/SUFFIX STATE — fatal for EVERY metric, not just speed. This is the refusal whose absence
    # let the corpus's central defect through: suffix decoding was ON for exactly the two winners and
    # OFF for every other candidate, so every cross-model comparison was a (model x serving-path)
    # composite and nothing objected. It differs from APC in kind: APC is a cache, so it moves only
    # latency, while suffix CHANGES THE GENERATED TEXT — ON and OFF are different fixed points at the
    # deployed config, measured byte-for-byte (bench/probe_determinism.py). An UNOBSERVED value
    # (pre-v3 rows carry none) warns rather than refuses; refusing there would make the whole
    # historical corpus incomparable overnight, which costs more than the composite it prevents.
    da = (ma.get("runtime") or {}).get("draft_kind")
    db = (mb.get("runtime") or {}).get("draft_kind")
    _unobserved = {None, "unknown"}
    if da in _unobserved or db in _unobserved:
        warnings.append(f"draft/suffix state is UNOBSERVED on at least one side ({da} vs {db}) — "
                        f"pre-v3 rows do not record it, so this comparison cannot rule out a "
                        f"(model x serving-path) composite")
    elif da != db:
        return _refuse(f"draft/suffix decoding state differs ({da} vs {db}) — it changes the "
                       f"generated text, not just latency, so the delta would be a "
                       f"(model x serving-path) composite rather than a model comparison")

    if metric == "peak_mem_gb":
        # Operator ruling 2026-08-17. The per-row field is the server's SESSION-CUMULATIVE
        # mx.get_peak_memory (verified monotone non-decreasing across all 8 suffix-OFAT arms), so
        # a paired per-item delta on it measures process history, not an effect. No pairing of
        # this field is admissible, matched manifests or not.
        return _refuse("peak_mem_gb is a session-cumulative running max (process history, not a "
                       "per-item measurement) — memory questions go to the capacity ladder's "
                       "per-rung server_peak_gb, measured on a fresh process")

    if metric in _HARDWARE_METRICS:
        if ma.get("box") != mb.get("box"):
            return _refuse(f"{metric} is hardware-dependent and the boxes differ "
                           f"({ma.get('box')} vs {mb.get('box')}) — re-measure on one box")
        apc_a = (ma.get("runtime") or {}).get("apc_enabled")
        apc_b = (mb.get("runtime") or {}).get("apc_enabled")
        if apc_a != apc_b:
            return _refuse(f"{metric} is APC-sensitive (34-147x on TTFT) and APC state differs "
                           f"({apc_a} vs {apc_b})")

    rows_a, rows_b = grade._rows(model_a, bench), grade._rows(model_b, bench)
    if not rows_a or not rows_b:
        empty = [m for m, r in ((model_a, rows_a), (model_b, rows_b)) if not r]
        return _refuse(f"no results for {', '.join(empty)}")

    score_a, score_b = grade.grade(bench, model_a), grade.grade(bench, model_b)
    conv_only = metric == "pass_at_1_converged"
    pa = _per_item(score_a, conv_only, rows_a)
    pb = _per_item(score_b, conv_only, rows_b)

    only_a, only_b = set(pa) - set(pb), set(pb) - set(pa)
    if conv_only and (only_a or only_b):
        # Not a refusal: the whole point of this metric is that each model converges on its own
        # subset. Pair on the intersection and SAY how many items that leaves.
        shared = set(pa) & set(pb)
        warnings.append(f"paired on the {len(shared)} items both models converged on "
                        f"(dropped {len(only_a)} A-only, {len(only_b)} B-only) — conditioning on "
                        f"convergence conditions on a model-dependent subset")
        pa = {k: v for k, v in pa.items() if k in shared}
        pb = {k: v for k, v in pb.items() if k in shared}
    elif (only_a or only_b) and intersect:
        # OPT-IN. The refusal below is right by default, but it also blocks the NESTED case, where
        # one model's items are a subset of the other's and a genuine matched comparison exists.
        # That case is not hypothetical: three valid ifeval runs (541 / 200 / 148 items, each set
        # nested in the last) yielded zero usable head-to-heads for want of a set operation.
        # Caller must ask for it, and the warning names what was dropped so the reader can judge
        # whether the intersection is a fair subset or a biased one — this cannot verify that.
        shared = set(pa) & set(pb)
        if not shared:
            return _refuse(f"intersect requested but there are no shared items "
                           f"({len(only_a)} only in {model_a}, {len(only_b)} only in {model_b})")
        warnings.append(f"INTERSECT: paired on the {len(shared)} shared items (dropped "
                        f"{len(only_a)} {model_a}-only, {len(only_b)} {model_b}-only). Sound only "
                        f"if the shared set is not an easier or harder subset than the whole; the "
                        f"item sets are nested by construction when one run is a prefix of another")
        pa = {k: v for k, v in pa.items() if k in shared}
        pb = {k: v for k, v in pb.items() if k in shared}
    elif only_a or only_b:
        diff = sorted(only_a | only_b)[:6]
        return _refuse(f"item sets differ ({len(only_a)} only in {model_a}, {len(only_b)} only in "
                       f"{model_b}; e.g. {diff}) — an unmatched comparison is the defect this "
                       f"refusal exists to prevent. Pass intersect=True (--intersect) to pair on "
                       f"the shared items if the sets are nested")
    if not pa:
        return _refuse("no shared items with scores")

    ka = {len(v) for v in pa.values()} | {len(v) for v in pb.values()}
    if len(ka) > 1:
        warnings.append(f"ragged sample counts {sorted(ka)} — the bootstrap handles it, but the "
                        f"reliability figures are not comparable across items")

    delta = stats.paired_delta(pa, pb, iters=iters, seed=seed, margin=margin)
    n_items = len(pa)
    return {"comparable": True, "metric": metric, "bench": bench,
            "a": stats.pass_at_1(pa), "b": stats.pass_at_1(pb),
            "delta": delta, "n_items": n_items, "samples": max(ka) if ka else 0,
            "mde": stats.mde(n_items), "n_for_margin": stats.n_for(margin),
            "warnings": warnings}
