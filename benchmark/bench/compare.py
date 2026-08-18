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

# ---- The V3 classification (2026-08-17). Every provenance fingerprint key lives in exactly one
# tier below; test_every_fingerprint_key_is_classified_in_compare_no_silent_gaps enforces it, so
# a key added to the fingerprint without a home here is a red suite, not a silent gap (which is
# how draft_kind spent two fingerprint versions unguarded).

# REFUSE for every metric: harness knobs that make a delta non-attributable. thinking_budget /
# max_tokens move truncation-sensitive metrics; enable_thinking OFF is a different regime
# entirely (thinking ON is a RULED axis).
_MUST_MATCH_SAMPLING = ("thinking_budget", "max_tokens", "enable_thinking")

# WARN only: per-model TUNE axes. Under the (model, tune) taxonomy each model legitimately runs
# its own operating point — Ornith-1.0-35B-mlx-uniform-4bit t0.4 vs
# Qwen3.6-27B-Opus-Distill-OptiQ-4bit t0.3 — and a rule demanding identical sampling would
# refuse every comparison the campaign actually needs.
_TUNE_SAMPLING_WARN = ("temperature", "top_p", "top_k", "min_p", "presence_penalty",
                       "repetition_penalty")

# REFUSE when OBSERVED differing: agentic scaffold knobs. aider-`diff` vs opencode-`tools` rows
# measure different edit protocols (the 3.75-malformed-per-case lesson), not different models.
_MUST_MATCH_RUNTIME = ("client", "edit_format", "max_turns", "deadline_s", "loop_guard")

# Handled by dedicated logic below (draft: text-changing, refuse-with-unobserved-wildcard;
# APC: latency-only cache, hardware metrics only).
_SERVING_PATH_RUNTIME = ("apc_enabled", "draft_kind")

# KV tune axes: WARN for quality (kv_bits/scheme are part of a model's tune; prefill_step_size
# has no proven text effect), while prealloc/prefill REFUSE hardware metrics (prealloc moved
# wall-clock 24.7 vs 27.8 s in the 2026-08-14 OFAT).
_TUNE_KV_WARN = ("kv_bits", "kv_quant_scheme", "quantized_kv_start", "prefill_step_size")
_HARDWARE_KV = ("kv_prealloc_tokens", "prefill_step_size")

# max_kv_cache_size gets the ruling-7 binding rule in compare() (refuse only when the silent
# 0.8 budget clamp could actually have engaged); hf_path differs across models by definition
# (weights identity — it guards RESUME, not cross-model comparison).
_CAP_BINDING_KV = ("max_kv_cache_size",)
_CROSS_MODEL_IDENTITY_KV = ("hf_path",)

# NOTE on the penalties sitting in _TUNE_SAMPLING_WARN (merged 2026-08-18 from the old driver
# box's O28 close): a nonzero repetition/presence penalty ALSO makes `logits_processors`
# non-empty, and `_suffix_structured_fallback` (mlx-vlm `generate/ar.py:163`, called `:648`)
# then skips speculation for that request — suffix's block verify samples raw target logits and
# can apply no processor. With draft OFF everywhere (the current registry) that path difference
# cannot arise and a penalty is a plain tune axis; under a NON-OFF draft state a penalty
# mismatch is a hidden (model x serving-path) composite the registry-derived `draft_kind`
# cannot see, so compare() escalates it to a refusal there (see the draft block).


def cap_partition(rows, resolved_budget, margin=0.10):
    """Split rows into those the KV cap CANNOT have touched and those it could have.

    WHY THIS EXISTS, and it is the operator's point (2026-08-16): `max_kv_cache_size` is a CEILING
    ENFORCED OUTSIDE THE MODEL, so it cannot have affected a row that finished well under it. A blanket
    refusal on a cap mismatch therefore throws away most of a perfectly good corpus, when what is
    actually needed is a TARGETED re-run of the rows that were near the ceiling.

    `margin` is the judgement call and is deliberately a named parameter: a row at 99% of budget is
    treated as sensitive even when `finish_reason == "stop"`, because a model steering into a ceiling it
    can feel is not the same as one that stopped freely. Default 10%.

    Returns the ids in each class, so a re-run can be scoped with `--ids` instead of re-running an axis.
    """
    # ⚠️ DO NOT consult the row's `truncated` field here. It records that the persisted REASONING TEXT
    # was head/tail excerpted for storage (traces.py:111-116) — NOT that generation was truncated. Read
    # as a truncation signal it classified 249 of 541 ifeval rows as cap-sensitive when the real figure
    # is ~5%, because nearly half the rows simply have long reasoning traces. A field name is not a
    # definition; the generation-side signals are `finish_reason` and the token count.
    independent, sensitive = [], []
    threshold = resolved_budget * (1.0 - margin) if resolved_budget else None
    for r in rows:
        ct = r.get("completion_tokens") or 0
        truncated = r.get("finish_reason") == "length"
        if threshold is None or truncated or ct >= threshold:
            sensitive.append(r.get("id"))
        else:
            independent.append(r.get("id"))
    return {"independent": independent, "sensitive": sensitive,
            "n_independent": len(independent), "n_sensitive": len(sensitive),
            "resolved_budget": resolved_budget, "margin": margin}


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
    for k in _TUNE_SAMPLING_WARN:
        if sa.get(k) != sb.get(k):
            warnings.append(f"{k} differs ({sa.get(k)} vs {sb.get(k)}) — a per-model tune axis; "
                            f"expected when each model runs at its own tuned operating point")

    kva, kvb = ma.get("kv") or {}, mb.get("kv") or {}
    for k in _TUNE_KV_WARN:
        if kva.get(k) != kvb.get(k):
            warnings.append(f"{k} differs ({kva.get(k)} vs {kvb.get(k)}) — a per-model KV/tune "
                            f"axis, recorded not refused")

    # DEPLOYED CODE — refuse when OBSERVED differing. Output-determining, measured 2026-08-14:
    # one src/mlx-vlm bump moved a matched item from 2475 to 3526 completion tokens on an
    # identical prompt. Unrecorded on both sides (the pre-provenance corpus) warns instead.
    ga = ((ma.get("git") or {}).get("submodules") or {})
    gb = ((mb.get("git") or {}).get("submodules") or {})
    if not ga and not gb:
        warnings.append("deployed-code shas unrecorded on both sides — cannot rule out a code-"
                        "version composite (pre-provenance rows)")
    else:
        for k in ("src/mlx-vlm", "src/mlx-serve"):
            va, vb = ga.get(k), gb.get(k)
            if va and vb and va != vb:
                return _refuse(f"deployed code differs at {k} ({va[:12]} vs {vb[:12]}) — the "
                               f"code sha is output-determining (measured: 2475 vs 3526 tokens "
                               f"on an identical prompt across one bump), so the delta would be "
                               f"a (model x code-version) composite")
            if bool(va) != bool(vb):
                warnings.append(f"{k} sha recorded on only one side — cannot rule out a "
                                f"code-version composite")

    ra_all = ma.get("runtime") or {}
    rb_all = mb.get("runtime") or {}
    for k in _MUST_MATCH_RUNTIME:
        va, vb = ra_all.get(k), rb_all.get(k)
        if va is not None and vb is not None and va != vb:
            return _refuse(f"{k} differs ({va} vs {vb}) — an agentic scaffold knob: the rows "
                           f"measure different harness protocols, not different models")
        if (va is None) != (vb is None):
            warnings.append(f"{k} recorded on only one side ({va} vs {vb}) — scaffold "
                            f"provenance is one-sided")

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
    elif da != "off":
        # Matched, observed, and NON-OFF. One more trap (old-driver-box O28 close, 2026-08-16,
        # merged 2026-08-18): a nonzero repetition/presence penalty makes `logits_processors`
        # non-empty and `_suffix_structured_fallback` (mlx-vlm generate/ar.py:163) then skips
        # speculation for THAT REQUEST — while the registry-derived draft_kind above still reads
        # "suffix" for both arms. So under a non-off draft state a penalty mismatch is a hidden
        # serving-path composite, and the _TUNE_SAMPLING_WARN treatment is escalated to refusal.
        for k in ("presence_penalty", "repetition_penalty"):
            va, vb = (sa.get(k) or 0), (sb.get(k) or 0)
            if va != vb:
                return _refuse(f"{k} differs ({va} vs {vb}) under draft_kind={da!r} — a nonzero "
                               f"penalty silently disables suffix for its requests (mlx-vlm "
                               f"generate/ar.py:163), so the arms ran different serving paths "
                               f"even though the registry says both were {da!r}")

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
        for k in _HARDWARE_KV:
            va, vb = kva.get(k), kvb.get(k)
            if va is not None and vb is not None and va != vb:
                return _refuse(f"{metric} is hardware/serving-structure-dependent and {k} "
                               f"differs ({va} vs {vb}) — prealloc alone moved wall-clock "
                               f"24.7 vs 27.8 s in the 2026-08-14 OFAT")

    rows_a, rows_b = grade._rows(model_a, bench), grade._rows(model_b, bench)
    if not rows_a or not rows_b:
        empty = [m for m, r in ((model_a, rows_a), (model_b, rows_b)) if not r]
        return _refuse(f"no results for {', '.join(empty)}")

    # max_kv_cache_size — the RULING-7 BINDING RULE (operator, 2026-08-17). The cap is an
    # EXTERNAL ceiling: it changes text only through the silent 0.8 thinking-budget clamp,
    # which engages iff max_tokens > cap - prompt. Rows where it never could have engaged are
    # cap-invariant, so a non-binding cap difference warns; a binding one refuses, because the
    # smaller-cap side ran at a resolved budget nobody chose. Checked against the rows' ACTUAL
    # prompt lengths; rows too old to carry prompt_tokens cannot prove innocence -> refuse.
    cap_a, cap_b = kva.get("max_kv_cache_size"), kvb.get("max_kv_cache_size")
    if cap_a != cap_b:
        if cap_a is None or cap_b is None:
            warnings.append(f"max_kv_cache_size unrecorded on at least one side "
                            f"({cap_a} vs {cap_b}) — cannot check the budget-clamp binding rule")
        else:
            binding = []
            for mdl, rows, cap, s in ((model_a, rows_a, cap_a, sa), (model_b, rows_b, cap_b, sb)):
                mt = s.get("max_tokens")
                prompts = [r.get("prompt_tokens") for r in rows]
                if mt is None or not prompts or any(p is None for p in prompts):
                    binding.append(f"{mdl}: unknowable (rows missing prompt_tokens or manifest "
                                   f"missing max_tokens)")
                elif max(prompts) + mt > cap:
                    binding.append(f"{mdl}: max prompt {max(prompts)} + max_tokens {mt} "
                                   f"exceeds cap {cap}")
            if binding:
                return _refuse(f"max_kv_cache_size differs ({cap_a} vs {cap_b}) and the cap "
                               f"could have BOUND — the silent 0.8 clamp resolves a thinking "
                               f"budget nobody chose ({'; '.join(binding)}). Use "
                               f"compare.cap_partition() to name the near-budget rows and "
                               f"re-run only those with --ids")
            warnings.append(f"max_kv_cache_size differs ({cap_a} vs {cap_b}) but never bound "
                            f"(max_tokens + every prompt fits under both caps) — rows are "
                            f"cap-invariant per the 2026-08-17 ruling")

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
