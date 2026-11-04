"""P613 step 2 — the Wave 1 signals (A1 math500, M1 256K memory, A2 cjudge, A3 vision, A4 reasoning) for the P426 sheet.

Computes the Wave 1 sections of `docs/specs/p613-step2-contract.md` ("B6 — Wave 1 definitions") from B8-accepted
(kind, block) pairs only; `bench.p426_signals.compute_all` assembles them with A7 into one SIGNALS.md / SIGNALS.json.
Statistics reuse `bench.p426_signals` (`_paired` over `bench.stats.paired_delta`, `permutation_p`, `geomean_ratio_ci`);
A1 regrades through `bench.grade.grade`. Deterministic; no wall-clock time, no absolute path.
"""
from __future__ import annotations

import json
from datetime import datetime

from bench import p426_signals as S
from bench import p426_verify as V
from bench.p426_verify import RefusalError

ROUTER_KINDS = ("math500", "cjudge", "vision", "reasoning")
SECTION_ORDER = ("A1", "M1", "A2", "A3", "A4")
KIND_OF = {v: k for k, v in V.W1_AXIS.items()}
M1_PEAK_MAX = 48e9
M1_PEAK_DELTA = 2e9
WALL_FMT = "%Y-%m-%d %H:%M:%S"
WALL_LABEL = "receipt ended − started, naive local time, descriptive"
A2_LABEL = "panel only (step 3)"
A3_LABEL = "self-check, lenient, descriptive"
A4_LABEL = "descriptive, never tested"
DERIVED_KIND_NOTE = ("A3: the row's nonconv_kind when present, else `finish_reason:<value>` for an unconverged turn 1; "
                     "A4: `budget_hit` when budget_hit, else `finish_reason:<value>` when finish_reason != 'stop'")


# ---------------------------------------------------------------------------------------------------------- helpers
def _wall(receipt):
    try:
        a = datetime.strptime(receipt["started"], WALL_FMT)
        b = datetime.strptime(receipt["ended"], WALL_FMT)
    except (KeyError, TypeError, ValueError):
        return None
    return (b - a).total_seconds()


def _row_map(leg):
    return {json.dumps(r["id"]): r["row"] for r in leg["rows"]}


def _check_b8_pairs(b8w):
    if not isinstance(b8w, dict) or b8w.get("axis") != "wave1" or not isinstance(b8w.get("pairs"), list):
        raise RefusalError("B8.json axes.wave1 is not a Wave 1 verifier record")
    out = {}
    for p in b8w["pairs"]:
        if not isinstance(p, dict) or p.get("kind") not in V.W1_KINDS or p.get("block") not in V.W1_BLOCKS:
            raise RefusalError("B8.json axes.wave1.pairs holds a record with no known (kind, block)")
        k = (p["kind"], p["block"])
        if k in out:
            raise RefusalError(f"B8.json axes.wave1 lists pair {k} twice")
        out[k] = p
    missing = [f"{k}/{b}" for k in V.W1_KINDS for b in V.W1_BLOCKS if (k, b) not in out]
    if missing:
        raise RefusalError(f"B8.json axes.wave1 has no pair record for {missing}")
    return out


def _accepted_keys(kind, block, rec, ids, legs):
    """The pair's accepted keys, recomputed and required equal to B8's."""
    off, on = legs[(kind, block, "off")], legs[(kind, block, "on")]
    if kind == "m1":
        keys = [[block]]
    else:
        acc, _rej, _n = V._w1_keys(kind, block, ids, off, on)
        keys = [k["key"] for k in acc]
    if rec.get("keys_accepted") != len(keys) or [k.get("key") for k in rec.get("keys") or []] != keys:
        raise RefusalError(f"pair {kind} {block}: the pair keys differ from B8.json")
    return keys


def _block_status(rec):
    return dict(off=rec["off"], on=rec["on"], b8_accepted=bool(rec.get("accepted")),
                b8_reasons=list(rec.get("reasons") or []), speed_valid=bool(rec.get("speed_valid")),
                labels=list(rec.get("labels") or []), status="accepted" if rec.get("accepted") else "rejected by B8",
                keys_rejected=list(rec.get("keys_rejected") or []))


def _speed_inference(blocks_status):
    """Rule 4: per block inference when both legs speed-valid; one valid block → descriptive, not order-balanced."""
    valid = [b for b, st in blocks_status.items() if st["status"] == "accepted" and st["speed_valid"]]
    both = ("order-balanced (both blocks speed-valid)" if len(valid) == 2 else
            "descriptive, not order-balanced (one speed-valid block)" if len(valid) == 1 else
            "no speed-valid block")
    return valid, both


# ------------------------------------------------------------------------------------------------------------ speed
def _rate(row):
    v = row.get("decode_tps") if isinstance(row, dict) else None
    return v if S._num(v) and v > 0 else None


def _speed(kind, per_block_keys, legs, blocks_status):
    """Decode ratio ON / OFF per key (A3: turn 1; A4: per draw), geomean + item-bootstrap CI per block and both;
    acceptance Σ draft_n_accepted ÷ Σ draft_n over ON rows (A3: turn 1 only)."""
    valid, both_note = _speed_inference(blocks_status)
    out = dict(blocks={}, inference_note=both_note, bootstrap=S.BOOTSTRAP_METHOD)
    all_ratios, all_dropped, acc_a, acc_p = [], [], 0, 0
    for block, keys in per_block_keys.items():
        mo, mn = _row_map(legs[(kind, block, "off")]), _row_map(legs[(kind, block, "on")])
        ratios, dropped, per_key = [], [], []
        for key in sorted(keys, key=lambda k: k[1]):                # fix 9: keys sorted (block, key)

            ro, rn = mo[json.dumps(key[1])], mn[json.dumps(key[1])]
            xo, xn = _rate(ro), _rate(rn)
            if xo is None or xn is None:
                dropped.append(dict(key=key, off=ro.get("decode_tps"), on=rn.get("decode_tps"),
                                    reason="missing / non-positive decode_tps"))
            else:
                ratios.append(xn / xo)
                per_key.append(dict(key=key, off=xo, on=xn, ratio=xn / xo))
        a, p, per_row = _acceptance_rows(kind, block, legs)            # fix 8: every ON row of the accepted block
        ci = S.geomean_ratio_ci(ratios)
        inference = block in valid
        out["blocks"][block] = dict(geomean_ratio=ci["point"], lo=ci["lo"], hi=ci["hi"], n=ci["n"], dropped=dropped,
                                    per_key=per_key, inference=inference,
                                    acceptance=dict(accepted=a, proposed=p, acceptance=(a / p if p else None),
                                                    basis="every ON row of the B8-accepted block"),
                                    acceptance_rows=per_row,
                                    ratio_min=min(ratios) if ratios else None,
                                    ratio_max=max(ratios) if ratios else None)
        all_ratios += ratios
        all_dropped += dropped
        acc_a += a
        acc_p += p
    ci = S.geomean_ratio_ci(all_ratios)
    out["both"] = dict(geomean_ratio=ci["point"], lo=ci["lo"], hi=ci["hi"], n=ci["n"], dropped=all_dropped,
                       inference=len(valid) == 2, note=both_note,
                       acceptance=dict(accepted=acc_a, proposed=acc_p, acceptance=(acc_a / acc_p if acc_p else None),
                                       basis="every ON row of the B8-accepted blocks"),
                       ratio_min=min(all_ratios) if all_ratios else None,
                       ratio_max=max(all_ratios) if all_ratios else None)
    return out


def _acceptance_rows(kind, block, legs):
    """(Σ draft_n_accepted, Σ draft_n, per-row [{key, off, on}]) over every ON row of the block (A3: turn 1)."""
    on, off = legs[(kind, block, "on")], _row_map(legs[(kind, block, "off")])
    a = p = 0
    rows = []
    for r in sorted(on["rows"], key=lambda r: r["id"]):
        d = r["row"].get("draft") if isinstance(r["row"].get("draft"), dict) else {}
        if S._num(d.get("draft_n")) and S._num(d.get("draft_n_accepted")):
            a += d["draft_n_accepted"]
            p += d["draft_n"]
            ro = off.get(json.dumps(r["id"]))
            od = ro.get("draft") if isinstance(ro, dict) else None
            rows.append(dict(key=[block, r["id"], r["seed"]],
                             off=dict(draft_n_accepted=(od or {}).get("draft_n_accepted"),
                                      draft_n=(od or {}).get("draft_n")),
                             on=dict(draft_n_accepted=d["draft_n_accepted"], draft_n=d["draft_n"])))
    return a, p, rows


def _walls(kind, legs, blocks_status):
    """Fix 10: B8-accepted pairs only (a rejected pair appears in coverage)."""
    out = {}
    for block in V.W1_BLOCKS:
        if blocks_status[block]["status"] != "accepted":
            continue
        for arm in ("off", "on"):
            r = legs[(kind, block, arm)]["receipt"]
            out[legs[(kind, block, arm)]["leg"]] = dict(started=r.get("started"), ended=r.get("ended"),
                                                        wall_s=_wall(r), speed_valid=r.get("speed_valid"))
    return dict(label=WALL_LABEL, legs=out)


# --------------------------------------------------------------------------------------------------------------- A1
def _a1_arm(leg, planned):
    from bench import convergence, grade

    s = grade.grade("math500", V.ENTRY, tune=leg["tune"])
    sc = leg["score"]
    for f in ("n", "errors", "correct", "acc_strict"):
        if s.get(f) != sc.get(f):
            raise RefusalError(f"A1 {leg['leg']}: regrade drift: {f} regraded {s.get(f)!r} != "
                               f"math500.{leg['tune']}.score.json {sc.get(f)!r}")
    lenient, strict = {}, {}
    for src, dst in ((s.get("items") or [], lenient), (s.get("strict_items") or [], strict)):
        for it in src:
            if it.get("sample", 0) != 0 or it["id"] in dst:
                raise RefusalError(f"A1 {leg['leg']}: more than one graded draw for item {it['id']}")
            dst[it["id"]] = float(it["score"])
    graded_rows = grade._rows(V.ENTRY, "math500", tune=leg["tune"])
    conv = {r["id"]: convergence.is_converged(r) for r in graded_rows}
    n = len(planned)
    le = {i: lenient.get(i, 0.0) for i in planned}
    st = {i: strict.get(i, 0.0) for i in planned}
    n_conv = sum(1 for i in planned if conv.get(i) is True)
    budget = s.get("acc_strict_budget")
    return dict(leg=leg["leg"], tune=leg["tune"], planned=n, lenient_correct=sum(le.values()),
                strict_correct=sum(st.values()), acc=sum(le.values()) / n, acc_strict_at_budget=sum(st.values()) / n,
                budget=budget, converged=n_conv, conv_pct=100.0 * n_conv / n,
                nonconv_kinds=dict(sorted((s.get("nonconv_kinds") or {}).items())), errors=s.get("errors"),
                nonconv_items=_nonconv_items(graded_rows, planned),
                regrade=dict(n=s.get("n"), errors=s.get("errors"), correct=s.get("correct"),
                             acc_strict=s.get("acc_strict"), matches_score_json=True)), le, st


def _nonconv_items(graded_rows, planned):
    """[[id, kind, finish_reason]] of the planned rows `bench.traces.classify` (the `nonconv_kinds` tally) names."""
    from bench import traces

    want = {json.dumps(i) for i in planned}
    out = []
    for r in graded_rows:
        k = traces.classify(r)
        if k is not None and json.dumps(r.get("id")) in want:
            out.append([r.get("id"), k, r.get("finish_reason")])
    return sorted(out, key=lambda x: json.dumps(x[0]))


def _sum_quality(per_block):
    """Fix 6: per arm over the accepted blocks — acc, acc_strict@budget (denominator = Σ planned), conv %, errors,
    nonconv_kinds."""
    out = {}
    for arm in ("off", "on"):
        qs = [q[arm] for q in per_block]
        planned = sum(q["planned"] for q in qs)
        lc, sc = sum(q["lenient_correct"] for q in qs), sum(q["strict_correct"] for q in qs)
        conv = sum(q["converged"] for q in qs)
        kinds = {}
        for q in qs:
            for k, v in q["nonconv_kinds"].items():
                kinds[k] = kinds.get(k, 0) + v
        budgets = sorted({q["budget"] for q in qs}, key=json.dumps)
        errs = [q["errors"] for q in qs]
        out[arm] = dict(legs=[q["leg"] for q in qs], planned=planned, lenient_correct=lc, strict_correct=sc,
                        acc=lc / planned if planned else None, acc_strict_at_budget=sc / planned if planned else None,
                        budget=budgets[0] if len(budgets) == 1 else budgets, converged=conv,
                        conv_pct=100.0 * conv / planned if planned else None, nonconv_kinds=dict(sorted(kinds.items())),
                        errors=sum(errs) if all(isinstance(e, int) for e in errs) else errs)
    return out


def _a1(rec_by, ids, legs, blocks_status, keys_by):
    out = dict(blocks={}, label="acc_strict@budget is the ranking key (denominator = the block's planned items)")
    both_s_on, both_s_off, both_l_on, both_l_off, diffs, qualities = {}, {}, {}, {}, [], []
    for block in V.W1_BLOCKS:
        st = dict(blocks_status[block])
        if st["status"] != "accepted":
            out["blocks"][block] = st
            continue
        planned = ids["math500"][block]
        q, scores = {}, {}
        for arm in ("off", "on"):
            q[arm], le, sc = _a1_arm(legs[("math500", block, arm)], planned)
            scores[arm] = (le, sc)
        qualities.append(q)
        keys = [k[1] for k in keys_by[block]]
        s_on = {i: scores["on"][1][i] for i in keys}
        s_off = {i: scores["off"][1][i] for i in keys}
        l_on = {i: scores["on"][0][i] for i in keys}
        l_off = {i: scores["off"][0][i] for i in keys}
        st.update(quality=q, paired_strict=S._paired(s_on, s_off), paired_lenient=S._paired(l_on, l_off),
                  exclusive=dict(on_only=[i for i in keys if s_on[i] == 1 and s_off[i] == 0],
                                 off_only=[i for i in keys if s_off[i] == 1 and s_on[i] == 0]),
                  n_pairs=len(keys))
        out["blocks"][block] = st
        for i in keys:
            k = f"{block}|{i}"
            both_s_on[k], both_s_off[k], both_l_on[k], both_l_off[k] = s_on[i], s_off[i], l_on[i], l_off[i]
            diffs.append(((block, i), s_on[i] - s_off[i]))
    diffs.sort(key=lambda x: x[0])
    out["both"] = dict(quality=_sum_quality(qualities) if qualities else None,
                       paired_strict=S._paired(both_s_on, both_s_off), paired_lenient=S._paired(both_l_on, both_l_off),
                       exclusive=dict(on_only=[[b, i] for (b, i), d in diffs if d > 0],
                                      off_only=[[b, i] for (b, i), d in diffs if d < 0]),
                       permutation_p=S.permutation_p([d for _k, d in diffs]) if diffs else None,
                       permutation=S.PERMUTATION_METHOD + "; differences sorted by (block, id)",
                       n_pairs=len(diffs), blocks=[b for b in V.W1_BLOCKS if blocks_status[b]["status"] == "accepted"])
    out["speed"] = _speed("math500", {b: keys_by[b] for b in V.W1_BLOCKS if blocks_status[b]["status"] == "accepted"},
                          legs, blocks_status)
    out["walls"] = _walls("math500", legs, blocks_status)
    return out


# --------------------------------------------------------------------------------------------------------------- A2
def _a2(ids, legs, blocks_status, keys_by):
    from bench import convergence, grade

    out = dict(blocks={}, label=A2_LABEL, mechanical_quality="N/A (grader acc: null)")
    for block in V.W1_BLOCKS:
        st = dict(blocks_status[block])
        if st["status"] != "accepted":
            out["blocks"][block] = st
            continue
        planned = ids["cjudge"][block]
        q = {}
        for arm in ("off", "on"):
            leg = legs[("cjudge", block, arm)]
            s = grade.grade("cjudge", V.ENTRY, tune=leg["tune"])
            graded_rows = grade._rows(V.ENTRY, "cjudge", tune=leg["tune"])
            conv = {r["id"]: convergence.is_converged(r) for r in graded_rows}
            n_conv = sum(1 for i in planned if conv.get(i) is True)
            q[arm] = dict(leg=leg["leg"], planned=len(planned), converged=n_conv,
                          conv_pct=100.0 * n_conv / len(planned), errors=s.get("errors"), acc=s.get("acc"),
                          nonconv_kinds=dict(sorted((s.get("nonconv_kinds") or {}).items())),
                          nonconv_items=_nonconv_items(graded_rows, planned))
        st.update(quality=q, n_pairs=len(keys_by[block]))
        out["blocks"][block] = st
    out["speed"] = _speed("cjudge", {b: keys_by[b] for b in V.W1_BLOCKS if blocks_status[b]["status"] == "accepted"},
                          legs, blocks_status)
    out["walls"] = _walls("cjudge", legs, blocks_status)
    return out


# --------------------------------------------------------------------------------------------------------------- A3
def _a3_kind(row):
    if "nonconv_kind" in row:
        return row.get("nonconv_kind")
    return None if row.get("converged") is True else f"finish_reason:{row.get('finish_reason')}"


def _a3(ids, legs, blocks_status, keys_by):
    out = dict(blocks={}, label=A3_LABEL, nonconv_kind_basis=DERIVED_KIND_NOTE)
    for block in V.W1_BLOCKS:
        st = dict(blocks_status[block])
        if st["status"] != "accepted":
            out["blocks"][block] = st
            continue
        planned = ids["vision"][block]
        q = {}
        for arm in ("off", "on"):
            leg = legs[("vision", block, arm)]
            rows = _row_map(leg)
            sel = [rows[json.dumps(i)] for i in planned]
            kinds, items = {}, []
            for r in sel:
                k = _a3_kind(r)
                if k is not None:
                    kinds[str(k)] = kinds.get(str(k), 0) + 1
                    items.append([r.get("id"), str(k), r.get("finish_reason")])
            n_conv = sum(1 for r in sel if r.get("converged") is True)
            q[arm] = dict(leg=leg["leg"], planned=len(planned), self_pass=sum(1 for r in sel if r.get("verdict") == "PASS"),
                          converged=n_conv, conv_pct=100.0 * n_conv / len(planned),
                          nonconv_kinds=dict(sorted(kinds.items())), nonconv_items=items)
        st.update(quality=q, n_pairs=len(keys_by[block]))
        out["blocks"][block] = st
    out["speed"] = _speed("vision", {b: keys_by[b] for b in V.W1_BLOCKS if blocks_status[b]["status"] == "accepted"},
                          legs, blocks_status)
    out["walls"] = _walls("vision", legs, blocks_status)
    return out


# --------------------------------------------------------------------------------------------------------------- A4
def _a4_kind(row):
    if row.get("budget_hit") is True:
        return "budget_hit"
    return None if row.get("finish_reason") == "stop" else f"finish_reason:{row.get('finish_reason')}"


def _a4(ids, legs, blocks_status, keys_by):
    out = dict(blocks={}, label=A4_LABEL, nonconv_kind_basis=DERIVED_KIND_NOTE,
               strict_draw="score == 1.0 and budget_hit is False and finish_reason == 'stop'")
    for block in V.W1_BLOCKS:
        st = dict(blocks_status[block])
        if st["status"] != "accepted":
            out["blocks"][block] = st
            continue
        planned = ids["reasoning"][block]
        q = {}
        for arm in ("off", "on"):
            leg = legs[("reasoning", block, arm)]
            rows = _row_map(leg)
            draws, kinds, items = [], {}, []
            for seed in planned:
                r = rows[json.dumps(seed)]
                strict = r.get("score") == 1.0 and r.get("budget_hit") is False and r.get("finish_reason") == "stop"
                draws.append(dict(seed=seed, sampler_seed=r.get("sampler_seed"), score=r.get("score"),
                                  budget_hit=r.get("budget_hit"), finish_reason=r.get("finish_reason"), strict=strict))
                k = _a4_kind(r)
                if k is not None:
                    kinds[k] = kinds.get(k, 0) + 1
                    items.append([seed, k, r.get("finish_reason")])
            rec = leg["record"] or {}
            q[arm] = dict(leg=leg["leg"], planned=len(planned), draws=draws,
                          strict_draws=sum(1 for d in draws if d["strict"]),
                          budget_hits=sum(1 for d in draws if d["budget_hit"] is True),
                          nonconv_kinds=dict(sorted(kinds.items())), nonconv_items=items,
                          record=dict(accuracy=rec.get("accuracy"), samples=rec.get("samples"),
                                      budget_hits=rec.get("budget_hits"), errors=rec.get("errors"),
                                      acceptance_pooled=rec.get("acceptance_pooled")))
        st.update(quality=q, n_pairs=len(keys_by[block]))
        out["blocks"][block] = st
    out["speed"] = _speed("reasoning", {b: keys_by[b] for b in V.W1_BLOCKS if blocks_status[b]["status"] == "accepted"},
                          legs, blocks_status)
    out["walls"] = _walls("reasoning", legs, blocks_status)
    return out


# --------------------------------------------------------------------------------------------------------------- M1
def _m1(legs, blocks_status):
    out = dict(blocks={}, acceptance="not recorded (no counters in result.json)",
               units="bytes; GB = bytes / 1e9 (3 dp)")
    deltas = {}
    for block in V.W1_BLOCKS:
        st = dict(blocks_status[block])
        if st["status"] != "accepted":
            out["blocks"][block] = st
            continue
        per = {}
        for arm in ("off", "on"):
            q = V.m1_qualify(legs[("m1", block, arm)])
            peaks = q.get("peaks") if isinstance(q.get("peaks"), dict) else {}
            rates = q.get("rates") if isinstance(q.get("rates"), dict) else {}
            for f in ("prefill", "decode", "retire"):
                if not S._num(peaks.get(f)):
                    raise RefusalError(f"M1 {legs[('m1', block, arm)]['leg']}: qualify.peaks.{f} is not a number")
            per[arm] = dict(leg=legs[("m1", block, arm)]["leg"],
                            peaks={f: int(peaks[f]) for f in ("prefill", "decode", "retire")},
                            peaks_gb={f: round(peaks[f] / 1e9, 3) for f in ("prefill", "decode", "retire")},
                            rates=dict(prefill_tps=rates.get("prefill_tps"), decode_tps=rates.get("decode_tps")),
                            generation_tokens=q.get("generation_tokens"), finish_reason=q.get("finish_reason"),
                            backend=q.get("backend"), prompt_tokens=((q.get("prompt") or {}).get("sized") or {}).get(
                                "tokens"))
        d = {f: per["on"]["peaks"][f] - per["off"]["peaks"][f] for f in ("prefill", "decode", "retire")}
        do, dn = per["off"]["rates"]["decode_tps"], per["on"]["rates"]["decode_tps"]
        st.update(arms=per, delta_on_minus_off=d, delta_gb={f: round(v / 1e9, 3) for f, v in d.items()},
                  decode_ratio=(dn / do if S._num(do) and S._num(dn) and do > 0 else None),
                  decode_ratio_label="descriptive")
        deltas[block] = d
        out["blocks"][block] = st
    if deltas:
        mean = {f: sum(d[f] for d in deltas.values()) / len(deltas) for f in ("prefill", "decode", "retire")}
        out["both"] = dict(mean_delta_on_minus_off=mean, mean_delta_gb={f: round(v / 1e9, 3) for f, v in mean.items()},
                           blocks=sorted(deltas))
    else:
        out["both"] = None
    out["walls"] = _walls("m1", legs, blocks_status)
    return out


# -------------------------------------------------------------------------------------------------------- coverage
def _coverage(rows_root, b8w, rec_by):
    from pathlib import Path

    base = Path(rows_root) / "p426" / V.W1
    smokes = sorted(p.name for p in base.iterdir() if p.is_dir() and V.SMOKE_LEG_RE.match(p.name))
    arch = base / "archive"
    superseded = sorted(p.name for p in arch.iterdir() if p.is_dir()) if arch.is_dir() else []
    out = {}
    for kind in V.W1_KINDS:
        valid, invalid = [], []
        for block in V.W1_BLOCKS:
            rec = rec_by[(kind, block)]
            entry = [rec["off"], rec["on"]]
            if rec.get("accepted"):
                valid += entry
            else:
                invalid.append(dict(legs=entry, reasons=list(rec.get("reasons") or [])))
        out[V.W1_AXIS[kind]] = dict(kind=kind, full_valid=valid, full_invalid=invalid,
                                    smokes=[s for s in smokes if s.startswith(f"{kind}-")],
                                    superseded=[f"archive/{a}" for a in superseded if a.startswith(f"{kind}-")])
    out["scrub"] = b8w.get("scrub_coverage")
    return out


# ------------------------------------------------------------------------------------------------------------ main
def compute_wave1(rows_root, b8w):
    """(Wave 1 signals, inputs read {rows_root-relative path: sha256})."""
    rec_by = _check_b8_pairs(b8w)
    reader = V.Reader(rows_root, confine=True)
    ids = V.load_ids(reader)
    legs = {}
    for kind in V.W1_KINDS:
        for block in V.W1_BLOCKS:
            for arm in ("off", "on"):
                legs[(kind, block, arm)] = V.load_w1_leg(reader, kind, arm, block)
    keys, status = {}, {}
    for kind in V.W1_KINDS:
        for block in V.W1_BLOCKS:
            keys[(kind, block)] = _accepted_keys(kind, block, rec_by[(kind, block)], ids, legs)
            status[(kind, block)] = _block_status(rec_by[(kind, block)])

    def kb(kind):
        return {b: keys[(kind, b)] for b in V.W1_BLOCKS}

    def sb(kind):
        return {b: status[(kind, b)] for b in V.W1_BLOCKS}

    out = dict(A1=_a1(rec_by, ids, legs, sb("math500"), kb("math500")),
               M1=_m1(legs, sb("m1")),
               A2=_a2(ids, legs, sb("cjudge"), kb("cjudge")),
               A3=_a3(ids, legs, sb("vision"), kb("vision")),
               A4=_a4(ids, legs, sb("reasoning"), kb("reasoning")))
    # fix 10: identity counts from B8-accepted pairs only (a rejected pair is listed in coverage)
    out["identity"] = {V.W1_AXIS[k]: {b: dict(rec_by[(k, b)].get("identical") or {}) for b in V.W1_BLOCKS
                                      if status[(k, b)]["status"] == "accepted"}
                       for k in ROUTER_KINDS}
    out["identity_total"] = dict(n=sum(v["n"] for ax in out["identity"].values() for v in ax.values()),
                                 of=sum(v["of"] for ax in out["identity"].values() for v in ax.values()))
    out["coverage"] = _coverage(rows_root, b8w, rec_by)
    return out, dict(sorted(reader.inputs.items()))


# ----------------------------------------------------------------------------------------------------------- flags
def _flag(flag, member, value, text, **extra):
    return dict(flag=flag, member=member, value=value, text=text, **extra)


def _a1_point_items(a1, scope):
    """Fix 11: the A1 exclusive strict solves of a scope, each with both arms' strict scores."""
    rec = a1["both"] if scope == "both" else a1["blocks"][scope]
    ex = rec["exclusive"]
    items = []
    for side, (off, on) in (("off_only", (1.0, 0.0)), ("on_only", (0.0, 1.0))):
        for x in ex[side]:
            key = list(x) if scope == "both" else [scope, x]
            items.append(dict(key=key, what="strict score", off=off, on=on))
    return sorted(items, key=lambda it: json.dumps(it["key"]))


def _scope_blocks(sp, scope):
    return [b for b in V.W1_BLOCKS if b in sp["blocks"]] if scope == "both" else [scope]


def _decode_items(sp, scope):
    """Fix 11: the keys whose own ON / OFF decode ratio is below the threshold, with both arms' decode_tps."""
    return [dict(key=k["key"], what="decode_tps", off=k["off"], on=k["on"], ratio=k["ratio"])
            for b in _scope_blocks(sp, scope) for k in sp["blocks"][b]["per_key"] if k["ratio"] < S.FLAG_RATIO]


def _acceptance_items(sp, scope):
    """Fix 11: the ON rows whose own acceptance is below the threshold, with both arms' draft counters."""
    out = []
    for b in _scope_blocks(sp, scope):
        for r in sp["blocks"][b]["acceptance_rows"]:
            n, a = r["on"]["draft_n"], r["on"]["draft_n_accepted"]
            if n and a / n < S.FLAG_ACCEPTANCE:
                out.append(dict(key=r["key"], what="draft_n_accepted / draft_n", off=r["off"], on=r["on"]))
    return out


def _nonconv_flag_items(rec, block, kind):
    """Fix 11: the ON keys of that non-convergence kind, with the OFF row's state for the same key."""
    off = {json.dumps(i): (k, fr) for i, k, fr in rec["quality"]["off"]["nonconv_items"]}
    out = []
    for i, k, fr in rec["quality"]["on"]["nonconv_items"]:
        if k != kind:
            continue
        ko, fo = off.get(json.dumps(i), (None, None))
        out.append(dict(key=[block, i], what="nonconv_kind / finish_reason",
                        off=dict(nonconv_kind=ko, finish_reason=fo) if ko is not None else "converged",
                        on=dict(nonconv_kind=k, finish_reason=fr)))
    return out


def flags(w1, a1_holm_p, cross):
    out = []
    a1 = w1["A1"]
    for scope in V.W1_BLOCKS + ("both",):
        rec = a1["blocks"][scope] if scope != "both" else a1["both"]
        if scope != "both" and rec.get("status") != "accepted":
            continue
        ps = rec.get("paired_strict")
        if ps is not None and 100.0 * ps["delta"] < S.FLAG_POINT_PP - S.FLAG_TOL:
            out.append(_flag("strict_point_below_-5pp", f"A1-{scope}", 100.0 * ps["delta"],
                             f"A1-{scope} strict ON - OFF point {100.0 * ps['delta']:+.1f} pp < {S.FLAG_POINT_PP:.0f} pp",
                             items=_a1_point_items(a1, scope)))
    ps = a1["both"].get("paired_strict")
    if a1_holm_p is not None and ps is not None and a1_holm_p < S.FLAG_HOLM_P and ps["delta"] < 0:
        out.append(_flag("holm_p_off_better", "A1-both", a1_holm_p,
                         f"A1 (both blocks) Holm-adjusted p {a1_holm_p:.4f} < {S.FLAG_HOLM_P} with OFF better",
                         items=_a1_point_items(a1, "both")))
    sp = a1["speed"]
    for scope in V.W1_BLOCKS + ("both",):
        d = sp["blocks"].get(scope) if scope != "both" else sp["both"]
        if d is None or not d["inference"] or d["geomean_ratio"] is None:
            continue
        if d["geomean_ratio"] < S.FLAG_RATIO:
            out.append(_flag("decode_ratio_below_1.3", f"A1-{scope}", d["geomean_ratio"],
                             f"A1-{scope} decode ratio ON/OFF {d['geomean_ratio']:.3f} (95 % CI {d['lo']:.3f}–"
                             f"{d['hi']:.3f}) < {S.FLAG_RATIO}", ci=[d["lo"], d["hi"]],
                             items=_decode_items(sp, scope)))
    for axis in ("A1", "A2", "A3", "A4"):
        sp = w1[axis]["speed"]
        for scope in V.W1_BLOCKS + ("both",):
            d = sp["blocks"].get(scope) if scope != "both" else sp["both"]
            if d is None:
                continue
            acc = d["acceptance"]
            if acc["acceptance"] is not None and acc["acceptance"] < S.FLAG_ACCEPTANCE:
                out.append(_flag("acceptance_below_0.70", f"{axis}-{scope}", acc["acceptance"],
                                 f"{axis}-{scope} ON acceptance {acc['accepted']} / {acc['proposed']} = "
                                 f"{acc['acceptance']:.4f} < {S.FLAG_ACCEPTANCE}",
                                 items=_acceptance_items(sp, scope)))
    for block in V.W1_BLOCKS:
        rec = w1["M1"]["blocks"][block]
        if rec.get("status") != "accepted":
            continue
        on_p, off_p = rec["arms"]["on"]["peaks"]["prefill"], rec["arms"]["off"]["peaks"]["prefill"]
        items = [dict(key=[block], what="prefill peak (bytes)", off=off_p, on=on_p,
                      legs=[rec["arms"]["off"]["leg"], rec["arms"]["on"]["leg"]])]
        if on_p > off_p + M1_PEAK_DELTA:
            out.append(_flag("m1_prefill_peak_over_off_plus_2GB", f"M1-{block}", on_p - off_p,
                             f"M1-{block} ON prefill peak {on_p} B exceeds OFF {off_p} B + 2e9 (Δ {on_p - off_p} B)",
                             items=items))
        if on_p > M1_PEAK_MAX:
            out.append(_flag("m1_prefill_peak_over_48GB", f"M1-{block}", on_p,
                             f"M1-{block} ON prefill peak {on_p} B > 48e9 B", items=items))
    for axis in ("A1", "A2", "A3", "A4"):
        for block in V.W1_BLOCKS:
            rec = w1[axis]["blocks"][block]
            if rec.get("status") != "accepted":
                continue
            k_on, k_off = rec["quality"]["on"]["nonconv_kinds"], rec["quality"]["off"]["nonconv_kinds"]
            for kind in sorted(k_on):
                if k_on[kind] > 0 and k_off.get(kind, 0) == 0:
                    out.append(_flag("nonconv_kind_on_only", f"{axis}-{block}", k_on[kind],
                                     f"{axis}-{block} nonconv_kind {kind}: ON {k_on[kind]}, OFF 0", category=kind,
                                     items=_nonconv_flag_items(rec, block, kind)))
    if cross.get("flag"):
        out.append(_flag("cross_wave", "rule 6", len(cross.get("files") or []),
                         f"B8 cross-wave code check: {len(cross['files'])} generation-path file(s) differ between "
                         f"Wave 1 OFF {cross['wave1_off'][:12]} and Wave 2 OFF {cross['wave2_off'][:12]}: "
                         f"{', '.join(cross['files'])}; entry_equal {cross.get('entry_equal')}, globals_equal "
                         f"{cross.get('globals_equal')}", files=list(cross["files"]),
                         entry_equal=cross.get("entry_equal"), globals_equal=cross.get("globals_equal")))
    return out


def flag_item_text(it):
    """One Markdown line for a Wave 1 flag item {key, what, off, on, …}."""
    def v(x):
        return json.dumps(x, sort_keys=True) if isinstance(x, (dict, list)) else str(x)

    key = "/".join(map(str, it["key"]))
    extra = f"; ratio {S._f(it['ratio'])}" if "ratio" in it else ""
    legs = f" (`{'` / `'.join(it['legs'])}`)" if it.get("legs") else ""
    return f"  - `{key}`{legs} {it['what']}: OFF {v(it['off'])}; ON {v(it['on'])}{extra}"


# ---------------------------------------------------------------------------------------------------------- render
def _status_lines(path, st):
    lines = [f"- Pair: OFF `{st['off']}` / ON `{st['on']}`; B8 {st['status']}"
             + (f"; labels {S._list(st['labels'])}" if st["labels"] else "")]
    if st["status"] != "accepted":
        lines += [f"- B8 reasons (`{path}.b8_reasons`):"] + [f"  - {r}" for r in st["b8_reasons"]]
    if st.get("keys_rejected"):
        lines += [f"- Keys rejected (`{path}.keys_rejected`): "
                  + "; ".join(f"{k['key']} ({k['reason']})" for k in st["keys_rejected"])]
    return lines


def _speed_md(axis, sp, what):
    p = f"{axis}.speed"
    lines = [f"### Speed and acceptance (`{p}`; {what}; {sp['inference_note']})", ""]
    for scope in V.W1_BLOCKS + ("both",):
        d = sp["blocks"].get(scope) if scope != "both" else sp["both"]
        if d is None:
            continue
        path = f"{p}.blocks.{scope}" if scope != "both" else f"{p}.both"
        acc = d["acceptance"]
        lines.append(f"- {scope} (`{path}`): decode ratio ON/OFF geometric mean {S._f(d['geomean_ratio'])}, 95 % CI "
                     f"[{S._f(d['lo'])}, {S._f(d['hi'])}], n = {d['n']} (per-key range {S._f(d['ratio_min'])}–"
                     f"{S._f(d['ratio_max'])}; {'inference' if d['inference'] else 'descriptive only'}); dropped "
                     + ("none" if not d["dropped"] else "; ".join(f"{x['key']} ({x['reason']})" for x in d["dropped"]))
                     + f"; ON acceptance {acc['accepted']} / {acc['proposed']} = {S._f(acc['acceptance'], 4)}")
    return lines + [""]


def _walls_md(axis, w):
    lines = [f"### Per-leg wall (`{axis}.walls`; {w['label']})", "", "| leg | started | ended | wall s | speed_valid |",
             "|---|---|---|---|---|"]
    for name, x in sorted(w["legs"].items()):
        lines.append(f"| `{name}` | {x['started']} | {x['ended']} | {S._f(x['wall_s'], 0)} | {x['speed_valid']} |")
    return lines + [""]


def _kinds(k):
    return ", ".join(f"{a} {b}" for a, b in k.items()) or "none"


def _a1_md(a1):
    lines = ["## A1 math500 (`A1`)", "", f"- {a1['label']}; regraded through `bench.grade.grade` and checked against "
                                          "each `math500.<tune>.score.json` (n, errors, correct, acc_strict)", ""]
    for block in V.W1_BLOCKS:
        st = a1["blocks"][block]
        p = f"A1.blocks.{block}"
        lines += [f"### A1 {block}", ""] + _status_lines(p, st)
        if st["status"] != "accepted":
            lines.append("")
            continue
        lines += ["", "| arm | leg | planned | acc_strict@budget | acc (lenient) | conv % | nonconv_kinds | errors |",
                  "|---|---|---|---|---|---|---|---|"]
        for arm in ("off", "on"):
            q = st["quality"][arm]
            lines.append(f"| {arm.upper()} | `{q['leg']}` | {q['planned']} | {q['strict_correct']:.0f}/{q['planned']} "
                         f"({S._pct(q['acc_strict_at_budget'])}) @{q['budget']} | {q['lenient_correct']:.0f}/"
                         f"{q['planned']} ({S._pct(q['acc'])}) | {S._f(q['conv_pct'], 1)} | {_kinds(q['nonconv_kinds'])} | "
                         f"{q['errors']} |")
        lines += [""]
        lines += S._paired_lines("acc_strict@budget (ranking key)", st["paired_strict"], f"{p}.paired_strict")
        lines += S._paired_lines("acc (lenient)", st["paired_lenient"], f"{p}.paired_lenient")
        lines += [f"- Exclusive strict solves (`{p}.exclusive`): ON-only {S._list(st['exclusive']['on_only'])}; "
                  f"OFF-only {S._list(st['exclusive']['off_only'])}", ""]
    b = a1["both"]
    lines += ["### A1 both blocks (`A1.both`)", "",
              f"- B8-accepted blocks (`A1.both.blocks`): {S._list(b['blocks'])}"
              + ("" if b["blocks"] == list(V.W1_BLOCKS) else " — not both blocks: the A1 family member is withheld"),
              ""]
    if b.get("quality"):
        lines += ["| arm | legs | planned | acc_strict@budget | acc (lenient) | conv % | nonconv_kinds | errors |",
                  "|---|---|---|---|---|---|---|---|"]
        for arm in ("off", "on"):
            q = b["quality"][arm]
            lines.append(f"| {arm.upper()} | {' + '.join(f'`{x}`' for x in q['legs'])} | {q['planned']} | "
                         f"{q['strict_correct']:.0f}/{q['planned']} ({S._pct(q['acc_strict_at_budget'])}) "
                         f"@{q['budget']} | {q['lenient_correct']:.0f}/{q['planned']} ({S._pct(q['acc'])}) | "
                         f"{S._f(q['conv_pct'], 1)} | {_kinds(q['nonconv_kinds'])} | {q['errors']} |")
        lines.append("")
    lines += S._paired_lines("acc_strict@budget (ranking key)", b["paired_strict"], "A1.both.paired_strict")
    lines += S._paired_lines("acc (lenient)", b["paired_lenient"], "A1.both.paired_lenient")
    lines += [f"- Exclusive strict solves (`A1.both.exclusive`): ON-only "
              f"{S._list(['/'.join(map(str, x)) for x in b['exclusive']['on_only']])}; OFF-only "
              f"{S._list(['/'.join(map(str, x)) for x in b['exclusive']['off_only']])}",
              f"- Permutation p (strict, both blocks, `A1.both.permutation_p`): {S._f(b['permutation_p'], 4)}; "
              f"Holm-adjusted (`A1.both.holm_p`): {S._f(b.get('holm_p'), 4)} — see the mechanical family", ""]
    lines += _speed_md("A1", a1["speed"], "decode_tps per item")
    lines += _walls_md("A1", a1["walls"])
    return lines


def _m1_md(m1):
    lines = ["## M1 256K memory (`M1`)", "", f"- `mx.get_peak_memory` peaks from `qualify` ({m1['units']}); acceptance: "
                                             f"{m1['acceptance']}", ""]
    for block in V.W1_BLOCKS:
        st = m1["blocks"][block]
        p = f"M1.blocks.{block}"
        lines += [f"### M1 {block}", ""] + _status_lines(p, st)
        if st["status"] != "accepted":
            lines.append("")
            continue
        lines += ["", "| arm | leg | prefill peak | decode peak | retire peak | prefill tok/s | decode tok/s |",
                  "|---|---|---|---|---|---|---|"]
        for arm in ("off", "on"):
            a = st["arms"][arm]
            pk, gb = a["peaks"], a["peaks_gb"]
            lines.append(f"| {arm.upper()} | `{a['leg']}` | {pk['prefill']} ({gb['prefill']:.3f} GB) | {pk['decode']} "
                         f"({gb['decode']:.3f} GB) | {pk['retire']} ({gb['retire']:.3f} GB) | "
                         f"{S._f(a['rates']['prefill_tps'], 2)} | {S._f(a['rates']['decode_tps'], 3)} |")
        d, g = st["delta_on_minus_off"], st["delta_gb"]
        lines += ["", f"- ON − OFF (`{p}.delta_on_minus_off`): prefill {d['prefill']:+d} B ({g['prefill']:+.3f} GB), "
                      f"decode {d['decode']:+d} B ({g['decode']:+.3f} GB), retire {d['retire']:+d} B "
                      f"({g['retire']:+.3f} GB)",
                  f"- Decode ratio ON / OFF (`{p}.decode_ratio`, descriptive): {S._f(st['decode_ratio'])}", ""]
    if m1["both"] is not None:
        mg = m1["both"]["mean_delta_gb"]
        lines += [f"- Mean ON − OFF over blocks {S._list(m1['both']['blocks'])} (`M1.both.mean_delta_on_minus_off`): "
                  f"prefill {mg['prefill']:+.3f} GB, decode {mg['decode']:+.3f} GB, retire {mg['retire']:+.3f} GB", ""]
    lines += _walls_md("M1", m1["walls"])
    return lines


def _simple_md(axis, title, sec, cols, cells, what):
    lines = [f"## {axis} {title} (`{axis}`)", "", f"- {sec['label']}"]
    if sec.get("nonconv_kind_basis"):
        lines.append(f"- nonconv_kinds basis (`{axis}.nonconv_kind_basis`): {sec['nonconv_kind_basis']}")
    lines.append("")
    for block in V.W1_BLOCKS:
        st = sec["blocks"][block]
        p = f"{axis}.blocks.{block}"
        lines += [f"### {axis} {block}", ""] + _status_lines(p, st)
        if st["status"] != "accepted":
            lines.append("")
            continue
        lines += ["", f"| arm | leg | {' | '.join(cols)} |", "|---|---|" + "---|" * len(cols)]
        for arm in ("off", "on"):
            q = st["quality"][arm]
            lines.append(f"| {arm.upper()} | `{q['leg']}` | " + " | ".join(cells(q)) + " |")
        lines.append("")
        if axis == "A4":
            for arm in ("off", "on"):
                lines.append(f"- {arm.upper()} draws (`{p}.quality.{arm}.draws`): "
                             + "; ".join(f"seed {d['seed']}: score {d['score']}, budget_hit {d['budget_hit']}, "
                                         f"finish_reason {d['finish_reason']}, strict {d['strict']}"
                                         for d in st["quality"][arm]["draws"]))
            lines.append("")
    lines += _speed_md(axis, sec["speed"], what)
    lines += _walls_md(axis, sec["walls"])
    return lines


def render_sections(w1):
    lines = {}
    lines["A1"] = _a1_md(w1["A1"])
    lines["M1"] = _m1_md(w1["M1"])
    lines["A2"] = _simple_md("A2", "cjudge", w1["A2"], ["conv %", "nonconv_kinds", "errors"],
                             lambda q: [f"{q['converged']}/{q['planned']} ({S._f(q['conv_pct'], 1)})",
                                        _kinds(q["nonconv_kinds"]), str(q["errors"])], "decode_tps per item")
    lines["A3"] = _simple_md("A3", "vision", w1["A3"], ["self-PASS", "conv % (turn 1)", "nonconv_kinds"],
                             lambda q: [f"{q['self_pass']}/{q['planned']}",
                                        f"{q['converged']}/{q['planned']} ({S._f(q['conv_pct'], 1)})",
                                        _kinds(q["nonconv_kinds"])], "decode_tps turn 1 per item")
    lines["A4"] = _simple_md("A4", "reasoning", w1["A4"], ["strict draws", "budget hits", "nonconv_kinds",
                                                           "record acceptance_pooled"],
                             lambda q: [f"{q['strict_draws']}/{q['planned']}", str(q["budget_hits"]),
                                        _kinds(q["nonconv_kinds"]), S._f(q["record"]["acceptance_pooled"], 4)],
                             "decode_tps per draw")
    return [x for ax in SECTION_ORDER for x in lines[ax]]


def coverage_md(cov, ident, ident_total):
    """Lines for `coverage.wave1` and `identity.per_axis` / `identity.total`."""
    lines = []
    for axis in SECTION_ORDER:
        c = cov[axis]
        inv = "; ".join(f"{' / '.join(x['legs'])} ({'; '.join(x['reasons'])})" for x in c["full_invalid"]) or "none"
        lines.append(f"- {axis} ({c['kind']}): full legs VALID {S._list(c['full_valid'])}; invalid {inv}; smokes "
                     f"(never scored) {S._list(c['smokes'])}; superseded {S._list(c['superseded'])}")
    sc = cov.get("scrub") or {}
    if sc:
        lines.append(f"- Wave 1 SCRUB re-verify (`coverage.wave1.scrub`): full legs {sc['full_legs']['verified']} / "
                     f"{sc['full_legs']['files']} (gate), smokes {sc['smoke_total']['verified']} / "
                     f"{sc['smoke_total']['files']} (coverage only), total {sc['total']['verified']} / "
                     f"{sc['total']['files']}")
    lines.append("- C217 identical outputs, for step 3 (`identity`; B8-accepted pairs only): "
                 + "; ".join(f"{ax} " + " + ".join(f"{ident[ax][b]['n']}/{ident[ax][b]['of']}" if b in ident[ax]
                                                   else f"{b} rejected by B8" for b in V.W1_BLOCKS)
                             for ax in ("A1", "A2", "A3", "A4"))
                 + f" (total {ident_total['n']} / {ident_total['of']}); M1: none")
    return lines
