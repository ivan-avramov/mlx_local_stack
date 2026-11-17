"""P613 B6 — the P426 signals sheet (step 1: axis A7 only, PROVISIONAL).

Computes the A7 signals of spec `docs/specs/p613-b8-b6-signals.md` v2 §4 (per session s1 / s2, never pooled) from B8-accepted
pairs only, per the step-1 contract `docs/specs/p613-step1-contract.md`. Deterministic: the same inputs give byte-identical
`SIGNALS.md` / `SIGNALS.json` (no wall-clock time, no absolute path). Refuses (`RefusalError`) when any B8 input changed.

CLI: `python -m bench.p426_signals a7 --results-root <dir> --b8 <B8.json> --out-md <SIGNALS.md> --out-json <SIGNALS.json>`.
Step 3: `all … --panel <frozen panel dir>` (optional, E1) adds §4.5 `subjective` (`docs/specs/p613-step3-contract.md`).
Step 4: `all … --evidence-ref <sha> [--repo <git work tree>]` adds the A7 first-divergence section (C284;
`bench.p426_signals_divergence`) and status FINAL when every section is present (`docs/specs/p613-step4-contract.md`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

from bench import p426_verify as V
from bench.p426_verify import RefusalError

GENERATOR = "bench.p426_signals"
GENERATOR_VERSION = "p613-step1"
STATUS = "PROVISIONAL — A7 only"
ITERS = 10000
SEED = 426
TAX_CATEGORIES = ("budget_hit", "turn_cap", "exec_timeout", "client_inactivity", "looping", "stalled")
NOISE_NAMESPACE = "wave2.v8-4104c7fc"
FAMILY_LABEL = "PROVISIONAL: family incomplete (A1 pending)"
WASH_LABEL = "WASH — directional (not a shown difference)"
SHOWN_LABEL = "shown difference"
LOSS_MAX_PP = 10.0
FLAG_POINT_PP = -5.0
FLAG_RATIO = 1.3
FLAG_ACCEPTANCE = 0.70
FLAG_HOLM_P = 0.05
PERMUTATION_METHOD = "numpy.random.default_rng(seed).choice([-1.0, 1.0], size=(iters, n))"
BOOTSTRAP_METHOD = "numpy.random.default_rng(seed).integers(0, n, size=(iters, n)); numpy.percentile([2.5, 97.5])"


# ----------------------------------------------------------------------------------------------------------- statistics
def permutation_p(diffs, iters=ITERS, seed=SEED):
    """Two-sided paired sign-flip permutation p: T = mean(d); p = (1 + #{|mean(s*d)| >= |T| - 1e-12}) / (iters + 1)."""
    import numpy as np

    d = np.asarray(list(diffs), dtype=float)
    n = d.size
    if n == 0:
        return 1.0
    t = abs(float(d.mean()))
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=(iters, n))
    stats_ = np.abs((signs * d).mean(axis=1))
    hits = int(np.count_nonzero(stats_ >= t - 1e-12))
    return (1 + hits) / (iters + 1)


def geomean_ratio_ci(ratios, iters=ITERS, seed=SEED):
    """Geometric mean of per-item ratios with a percentile item-bootstrap 95 % interval."""
    import numpy as np

    r = np.asarray(list(ratios), dtype=float)
    n = int(r.size)
    if n == 0:
        return dict(point=None, lo=None, hi=None, n=0)
    if np.any(r <= 0) or not np.all(np.isfinite(r)):
        raise ValueError("geomean_ratio_ci: ratios must be finite and > 0")
    logs = np.log(r)
    point = float(math.exp(float(logs.mean())))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(iters, n))
    boot = np.exp(logs[idx].mean(axis=1))
    lo, hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    return dict(point=point, lo=lo, hi=hi, n=n)


def _paired(on, off):
    """`stats.paired_delta` (ON - OFF) reading only delta / lo / hi / degenerate / discordance_upper95, + labels."""
    from bench import stats
    from bench.compare_predictor import _loss_bound

    ids = sorted(on)
    n = len(ids)
    if n == 0:
        return None
    res = stats.paired_delta({i: [on[i]] for i in ids}, {i: [off[i]] for i in ids}, iters=ITERS, seed=SEED)
    kept = {k: res[k] for k in ("delta", "lo", "hi", "degenerate", "discordance_upper95")}
    discordant = sum(1 for i in ids if on[i] != off[i])
    p_d = discordant / n
    label = SHOWN_LABEL if (kept["lo"] > 0 or kept["hi"] < 0) else WASH_LABEL
    loss_pp = 100.0 * _loss_bound(kept)
    out = dict(kept, n=n, discordant=discordant, p_d=p_d, label=label, loss_bound_pp=loss_pp,
               loss_text=(f"loss not ruled out above {loss_pp:.1f} pp" if loss_pp > LOSS_MAX_PP + 1e-12 else
                          f"loss bound {loss_pp:.1f} pp (<= {LOSS_MAX_PP:.0f} pp)"),
               mde_observed=(stats.mde(n, p_d) if p_d > 0 else None), mde_default=stats.mde(n),
               mde_note=("p_d = 0 observed: mde(n) at the default p_d 0.20 shown" if p_d == 0 else
                         "mde(n, observed p_d)"))
    return out


# ------------------------------------------------------------------------------------------------------------- scoring
def _strict(row):
    return 1 if row is not None and row.get("passed") is True and row.get("converged") is True else 0


def _lenient(row):
    return 1 if row is not None and row.get("passed") is True else 0


def _categories(row):
    if row is None:
        return []
    flags = row.get("nonconv_flags") or []
    kind = row.get("nonconv_kind")
    return [c for c in TAX_CATEGORIES if c in flags or kind == c]


def _arm_quality(att):
    ids = att["planned_ids"]
    planned = att["planned"]
    strict = sum(_strict(att["rows"].get(i)) for i in ids)
    lenient = sum(_lenient(att["rows"].get(i)) for i in ids)
    conv = sum(1 for i in ids if (att["rows"].get(i) or {}).get("converged") is True)
    kinds = {}
    for i in ids:
        row = att["rows"].get(i)
        kind = "transport_dnf" if row is None and i in att["dnf"] else (row or {}).get("nonconv_kind")
        if kind is not None:
            kinds[str(kind)] = kinds.get(str(kind), 0) + 1
    return dict(attempt=att["name"], planned=planned, rows=len(att["rows"]), transport_dnf=sorted(att["dnf"]),
                strict=strict, lenient=lenient, converged=conv,
                acc_strict_at_budget=strict / planned if planned else None, acc=lenient / planned if planned else None,
                conv_pct=100.0 * conv / planned if planned else None, nonconv_kinds=dict(sorted(kinds.items())))


def _edit(att):
    rows = [att["rows"][i] for i in sorted(att["rows"])]
    tbr = [int(r.get("tool_bounds_rejections") or 0) for r in rows]
    return dict(file_changed=sum(1 for r in rows if r.get("file_changed") is True),
                test_modified=sum(1 for r in rows if r.get("test_modified") is True),
                tool_bounds_rejections=sum(tbr), tool_bounds_rejection_items=sum(1 for t in tbr if t > 0))


def _tax(att):
    cats = {c: [] for c in TAX_CATEGORIES}
    union = []
    client_abort = {}
    for i in sorted(att["rows"]):
        row = att["rows"][i]
        hit = _categories(row)
        for c in hit:
            cats[c].append(i)
        if hit:
            union.append(i)
        if "client_inactivity" in hit:
            client_abort[i] = row.get("client_abort")
    return dict(counts={c: len(v) for c, v in cats.items()}, items=cats, union=len(union), union_items=union,
                client_abort=client_abort)


def _dnf_table(att):
    table = {}
    for rec in att["chain"].get("p426_dnf") or []:
        if not isinstance(rec, dict):
            continue
        abort = rec.get("abort") if isinstance(rec.get("abort"), dict) else {}
        cause = str(abort.get("cause") or "unknown")
        table.setdefault(cause, []).append(str(rec.get("slot")))
    return {k: sorted(v) for k, v in sorted(table.items())}


# --------------------------------------------------------------------------------------------------------------- speed
def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


COMPLETED_SOURCE = "completed requests"


def rate_primary(rec):
    """(rate, None) or (None, reason). Uses `totals` only when `totals.decode_rate_source` names completed requests."""
    t = rec.get("totals") if isinstance(rec, dict) else None
    if not isinstance(t, dict):
        return None, "no totals"
    src = t.get("decode_rate_source")
    if not isinstance(src, str) or COMPLETED_SOURCE not in src:
        return None, f"totals.decode_rate_source {src!r} does not name completed requests"
    gen, req, ds = t.get("generated_tokens"), t.get("requests"), t.get("decode_s")
    if not (_num(gen) and _num(req) and _num(ds)) or ds <= 0 or gen - req <= 0:
        return None, "no usable totals rate"
    return (gen - req) / ds, None


def rate_sensitivity(rec):
    """(rate, None) or (None, reason) over request records with decode_tok_s > 0 and gen >= 1."""
    reqs = rec.get("requests") if isinstance(rec, dict) else None
    if not isinstance(reqs, list):
        return None, "no request records"
    num = den = 0.0
    for q in reqs:
        if not isinstance(q, dict):
            continue
        gen, tps = q.get("generated_tokens"), q.get("decode_tok_s")
        if not (_num(gen) and _num(tps)) or tps <= 0 or gen < 1:
            continue
        num += gen - 1
        den += (gen - 1) / tps
    return (num / den, None) if den > 0 else (None, "no usable request rate")


def _rate(fn, att, rid):
    if att["rows"].get(rid) is None:
        return None, "DNF slot (no speed rate)"
    return fn(att["items"].get(rid))


def _speed(keys, off, on, inference):
    out = {}
    for name, fn in (("primary", rate_primary), ("sensitivity", rate_sensitivity)):
        ratios, dropped, per_item = [], [], {}
        for rid in keys:
            (ro, why_o), (rn, why_n) = _rate(fn, off, rid), _rate(fn, on, rid)
            if ro is None or rn is None:
                reason = "; ".join(f"{arm}: {w}" for arm, w in (("off", why_o), ("on", why_n)) if w)
                dropped.append(dict(id=rid, off=ro, on=rn, reason=reason))
                continue
            ratios.append(rn / ro)
            per_item[rid] = dict(off=ro, on=rn, ratio=rn / ro)
        ci = geomean_ratio_ci(ratios)
        out[name] = dict(geomean_ratio=ci["point"], lo=ci["lo"], hi=ci["hi"], n=ci["n"], dropped=dropped,
                         per_item=per_item)
    acc = {}
    for arm, att in (("off", off), ("on", on)):
        a = p = 0
        per_item = {}
        for rid in keys:
            if att["rows"].get(rid) is None:
                continue
            t = (att["items"].get(rid) or {}).get("totals") or {}
            ia = t["accepted"] if _num(t.get("accepted")) else 0
            ip = t["proposed"] if _num(t.get("proposed")) else 0
            a += ia
            p += ip
            if ip > 0:
                per_item[rid] = ia / ip
        acc[arm] = dict(accepted=a, proposed=p, acceptance=(a / p if p > 0 else None), per_item=per_item)
    out["acceptance"] = acc
    out["inference"] = inference
    out["bootstrap"] = BOOTSTRAP_METHOD
    return out


def _wall(leg):
    try:
        a = datetime.strptime(leg["started"], "%Y-%m-%dT%H:%M:%SZ")
        b = datetime.strptime(leg["ended"], "%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, TypeError, ValueError):
        return None
    return (b - a).total_seconds()


# ---------------------------------------------------------------------------------------------------------- inputs / B8
def _sha_doc(doc):
    return hashlib.sha256(V.dumps(doc).encode("utf-8")).hexdigest()


def _check_b8(results_root, b8):
    if not isinstance(b8, dict) or b8.get("axis") != "A7":
        raise RefusalError("B8.json is not an A7 verifier record")
    inputs, pairs = b8.get("inputs"), b8.get("pairs")
    if not isinstance(inputs, dict) or not inputs or not isinstance(pairs, list):
        raise RefusalError("B8.json has no inputs map or pairs list")
    root = Path(results_root)
    for rel in sorted(inputs):
        if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
            raise RefusalError(f"B8.json input {rel!r} is not a results_root-relative path")
        path = root / rel
        try:
            data = path.read_bytes()
        except OSError:
            raise RefusalError(f"B8 input {rel} is missing") from None
        got = hashlib.sha256(data).hexdigest()
        if got != inputs[rel]:
            raise RefusalError(f"B8 input {rel} changed: sha256 {got} != B8 {inputs[rel]}")
    by_session = {}
    for p in pairs:
        if not isinstance(p, dict) or p.get("pair") not in V.SESSIONS:
            raise RefusalError("B8.json pairs hold a record with no known session")
        if p["pair"] in by_session:
            raise RefusalError(f"B8.json lists pair {p['pair']} twice")
        by_session[p["pair"]] = p
    missing = [s for s in V.SESSIONS if s not in by_session]
    if missing:
        raise RefusalError(f"B8.json has no pair record for {missing}")
    return by_session


def _covered(reader, b8_inputs):
    for rel, sha in sorted(reader.inputs.items()):
        if b8_inputs.get(rel) != sha:
            raise RefusalError(f"input {rel} is not covered by B8.json (B8 {b8_inputs.get(rel)!r}, now {sha})")


# --------------------------------------------------------------------------------------------------------- noise floor
def _outcome(row):
    """(passed, converged); a DNF slot (no row) is a non-success."""
    if row is None:
        return (False, False)
    return (row.get("passed") is True, row.get("converged") is True)


def _planned_outcomes(att):
    """{planned slot id: outcome} over the attempt's schedule.json planned slots."""
    return {i: _outcome(att["rows"].get(i)) for i in att["planned_ids"]}


def _flips(map_a, map_b):
    common = sorted(set(map_a) & set(map_b))
    flips = [i for i in common if map_a[i] != map_b[i]]
    return dict(flips=len(flips), flip_items=flips, common=len(common),
                only_first=sorted(set(map_a) - set(map_b)), only_second=sorted(set(map_b) - set(map_a)))


def _plain_attempt(reader, adir, session):
    """A superseded-namespace attempt as {name, rows, planned_ids} (rows + DNF slots == planned slots, else refusal)."""
    where = f"noise floor {reader.rel(adir)}"
    chain = reader.read_json(adir / "chain.json", f"{where} chain.json")
    schedule = reader.read_json(adir / "schedule.json", f"{where} schedule.json")
    if not isinstance(chain, dict) or not isinstance(schedule, dict):
        raise RefusalError(f"{where}: chain.json or schedule.json is not an object")
    rows = V.session_rows(reader, adir / session, session, where)
    dnf = V.load_dnf(chain, rows, session, where)
    _count, ids = V.check_planned(rows, dnf, schedule, where)
    return dict(name=adir.name, rows=rows, planned_ids=ids)


def _noise_floor(results_root, atts, by_session, v8_sha):
    diag_rejected = [f"{s}: " + "; ".join(by_session[s].get("reasons") or ["rejected"]) for s in V.SESSIONS_DIAGNOSTIC
                     if not by_session[s].get("accepted")]
    if diag_rejected:
        same = dict(status=f"not computed: diagnostic pair rejected ({' | '.join(diag_rejected)})")
    else:
        same = dict(status="computed (B8 accepted pilot and reload)")
        for arm in ("off", "on"):
            pilot, reload_ = atts["pilot"][arm], atts["reload"][arm]
            f = _flips(_planned_outcomes(reload_), _planned_outcomes(pilot))
            same[arm] = dict(reload=reload_["name"], pilot=pilot["name"], **f)
    reader = V.Reader(results_root)
    old_root = Path(results_root) / NOISE_NAMESPACE
    cross = dict(namespace=NOISE_NAMESPACE, v8_sha256_current=v8_sha, v8_sha256_superseded=None, matches=[],
                 excluded=[], available=old_root.is_dir())
    if old_root.is_dir():
        old_v8 = reader.read_json(old_root / "run" / "v8_base.json", f"{NOISE_NAMESPACE}/run/v8_base.json")
        cross["v8_sha256_superseded"] = old_v8.get("sha256") if isinstance(old_v8, dict) else None
        for session in V.SESSIONS:
            for arm in ("off", "on"):
                cur = atts[session][arm]
                cur_sched = reader.inputs.get(reader.rel(cur["path"] / "schedule.json"))
                if cur_sched is None:
                    cur_sched = hashlib.sha256(reader.read_bytes(cur["path"] / "schedule.json", "schedule")).hexdigest()
                lname = V.leg_name(cur["name"])
                for old in sorted(p for p in old_root.iterdir() if p.is_dir() and V.ATTEMPT_RE.match(p.name)
                                  and V.leg_name(p.name) == lname):
                    old_leg = reader.read_json(old / "leg.json", f"{NOISE_NAMESPACE} leg.json")
                    old_sched = hashlib.sha256(reader.read_bytes(old / "schedule.json", "schedule")).hexdigest()
                    entry = dict(arm=arm, session=session, current=cur["name"], superseded=old.name)
                    why = []
                    if old_sched != cur_sched:
                        why.append("schedule.json sha256 differs")
                    if (old_leg or {}).get("state") != "VALID":
                        why.append(f"superseded leg state {(old_leg or {}).get('state')!r}")
                    if cur["leg"].get("state") != "VALID":
                        why.append(f"current leg state {cur['leg'].get('state')!r}")
                    if why:
                        cross["excluded"].append(dict(entry, reason="; ".join(why)))
                        continue
                    f = _flips(_planned_outcomes(cur), _planned_outcomes(_plain_attempt(reader, old, session)))
                    cross["matches"].append(dict(entry, **f))
    cross["per_arm"] = {arm: dict(flips=sum(m["flips"] for m in cross["matches"] if m["arm"] == arm),
                                  common=sum(m["common"] for m in cross["matches"] if m["arm"] == arm),
                                  matches=sum(1 for m in cross["matches"] if m["arm"] == arm))
                        for arm in ("off", "on")}
    return dict(same_epoch=same, cross_epoch=cross), dict(sorted(reader.inputs.items()))


# ------------------------------------------------------------------------------------------------------------- compute
def _versions():
    from importlib import metadata

    import numpy

    try:
        scipy_v = metadata.version("scipy")
    except metadata.PackageNotFoundError:
        scipy_v = "unavailable"
    return numpy.__version__, scipy_v


def _session(session, rec, off, on):
    keys_full, rejected = V.pair_keys(session, off, on)
    if rec.get("keys_accepted") != len(keys_full) or (
            "keys" in rec and [k["key"] for k in rec["keys"]] != [k["key"] for k in keys_full]):
        raise RefusalError(f"pair {session}: the pair keys differ from B8.json")
    out = dict(pair=session, off=off["name"], on=on["name"], b8_accepted=bool(rec.get("accepted")),
               b8_reasons=list(rec.get("reasons") or []), speed_valid=bool(rec.get("speed_valid")),
               labels=list(rec.get("labels") or []))
    if not rec.get("accepted"):
        out["status"] = "rejected by B8"
        return out
    out["status"] = "accepted"
    keys = [k["key"][1] for k in keys_full]
    out["quality"] = dict(off=_arm_quality(off), on=_arm_quality(on))
    s_on = {i: _strict(on["rows"].get(i)) for i in keys}
    s_off = {i: _strict(off["rows"].get(i)) for i in keys}
    l_on = {i: _lenient(on["rows"].get(i)) for i in keys}
    l_off = {i: _lenient(off["rows"].get(i)) for i in keys}
    out["paired_strict"] = _paired(s_on, s_off)
    out["paired_lenient"] = _paired(l_on, l_off)
    out["permutation_p"] = permutation_p([s_on[i] - s_off[i] for i in keys])
    out["permutation"] = PERMUTATION_METHOD
    ci_keys = [i for i in keys if (off["rows"].get(i) or {}).get("nonconv_kind") == "client_inactivity"
               or (on["rows"].get(i) or {}).get("nonconv_kind") == "client_inactivity"]
    rest = [i for i in keys if i not in ci_keys]
    out["c269"] = dict(excluded=ci_keys, paired_strict=_paired({i: s_on[i] for i in rest}, {i: s_off[i] for i in rest}))
    out["exclusive"] = dict(on_only=[i for i in keys if s_on[i] == 1 and s_off[i] == 0],
                            off_only=[i for i in keys if s_off[i] == 1 and s_on[i] == 0])
    out["edit"] = dict(off=_edit(off), on=_edit(on))
    out["dnf"] = dict(off=_dnf_table(off), on=_dnf_table(on))
    out["tax"] = dict(off=_tax(off), on=_tax(on))
    out["identical"] = dict(count=sum(1 for k in keys_full if k["identical"]),
                            items=[k["key"][1] for k in keys_full if k["identical"]])
    out["speed"] = _speed(keys, off, on, inference=bool(rec.get("speed_valid")))
    out["n_pairs"] = len(keys)
    return out


FLAG_TOL = 1e-9


def _ending(att, rid):
    row = att["rows"].get(rid)
    if row is None:
        return dict(passed=False, converged=False, nonconv_kind="transport_dnf" if rid in att["dnf"] else None)
    return dict(passed=row.get("passed") is True, converged=row.get("converged") is True,
                nonconv_kind=row.get("nonconv_kind"))


def _flag_items(ids, arm, atts):
    other = "off" if arm == "on" else "on"
    return [dict(id=i, arm=arm, ending=_ending(atts[arm], i), other_arm=other, other_ending=_ending(atts[other], i))
            for i in sorted(ids)]


def _kind_items(att, kind, ids):
    return [i for i in ids if _ending(att, i)["nonconv_kind"] == kind]


def _flags(sessions, atts):
    flags = []
    for s in V.SESSIONS_PAIRED:
        rec = sessions[s]
        if rec.get("status") != "accepted":
            continue
        pair = atts[s]
        discordant = rec["exclusive"]["on_only"] + rec["exclusive"]["off_only"]
        ps = rec["paired_strict"]
        if ps is not None and 100.0 * ps["delta"] < FLAG_POINT_PP - FLAG_TOL:
            flags.append(dict(flag="strict_point_below_-5pp", member=f"A7-{s}", value=100.0 * ps["delta"],
                              items=_flag_items(discordant, "on", pair),
                              text=f"A7-{s} strict ON - OFF point {100.0 * ps['delta']:+.1f} pp < {FLAG_POINT_PP:.0f} pp"))
        hp = rec.get("holm_p")
        if hp is not None and ps is not None and hp < FLAG_HOLM_P and ps["delta"] < 0:
            flags.append(dict(flag="holm_p_off_better", member=f"A7-{s}", value=hp,
                              items=_flag_items(discordant, "on", pair),
                              text=f"A7-{s} Holm-adjusted p {hp:.4f} < {FLAG_HOLM_P} with OFF better"))
        sp = rec["speed"]["primary"]
        if rec["speed"]["inference"] and sp["geomean_ratio"] is not None and sp["geomean_ratio"] < FLAG_RATIO:
            slow = [i for i, d in sp["per_item"].items() if d["ratio"] < FLAG_RATIO]
            flags.append(dict(flag="decode_ratio_below_1.3", member=f"A7-{s}", value=sp["geomean_ratio"],
                              ci=[sp["lo"], sp["hi"]], items=_flag_items(slow, "on", pair),
                              text=f"A7-{s} decode ratio ON/OFF {sp['geomean_ratio']:.3f} (95 % CI {sp['lo']:.3f}–"
                                   f"{sp['hi']:.3f}) < {FLAG_RATIO}"))
        acc_on = rec["speed"]["acceptance"]["on"]
        acc = acc_on["acceptance"]
        if acc is not None and acc < FLAG_ACCEPTANCE:
            below = [i for i, v in acc_on["per_item"].items() if v < FLAG_ACCEPTANCE]
            flags.append(dict(flag="acceptance_below_0.70", member=f"A7-{s}", value=acc,
                              items=_flag_items(below, "on", pair),
                              text=f"A7-{s} ON acceptance {acc:.3f} < {FLAG_ACCEPTANCE}"))
        tax_flagged = set()
        for c in TAX_CATEGORIES:
            n_on, n_off = rec["tax"]["on"]["counts"][c], rec["tax"]["off"]["counts"][c]
            if n_on > 0 and n_off == 0:
                tax_flagged.add(c)
                flags.append(dict(flag="tax_on_only", member=f"A7-{s}", category=c, value=n_on,
                                  items=_flag_items(rec["tax"]["on"]["items"][c], "on", pair),
                                  text=f"A7-{s} runaway-tax {c}: ON {n_on}, OFF 0"))
        k_on, k_off = rec["quality"]["on"]["nonconv_kinds"], rec["quality"]["off"]["nonconv_kinds"]
        for kind in sorted(k_on):
            if k_on[kind] > 0 and k_off.get(kind, 0) == 0 and kind not in tax_flagged:
                flags.append(dict(flag="nonconv_kind_on_only", member=f"A7-{s}", category=kind, value=k_on[kind],
                                  items=_flag_items(_kind_items(pair["on"], kind, pair["on"]["planned_ids"]), "on",
                                                    pair),
                                  text=f"A7-{s} nonconv_kind {kind}: ON {k_on[kind]}, OFF 0"))
    return flags


def _coverage(results_root, seq, atts, by_session):
    """A7 legs: state = the verified leg.json state (+ B8's rejection); a sequence.json disagreement is listed."""
    seq_state = {}
    for leg in seq.get("legs") or []:
        if isinstance(leg, dict):
            seq_state[f"{leg.get('leg')}.a{leg.get('attempt')}"] = leg.get("state")
    legs, mismatch = [], []
    loaded = {}
    for s in V.SESSIONS:
        for arm in ("off", "on"):
            loaded[atts[s][arm]["name"]] = (atts[s][arm], by_session[s])
    for name in sorted(set(seq_state) | set(loaded)):
        att, rec = loaded.get(name, (None, None))
        stem, _, k = name.rpartition(".a")
        entry = dict(leg=stem, attempt=int(k) if k.isdigit() else k, sequence_state=seq_state.get(name), b8=None)
        if att is None:
            entry.update(state=seq_state.get(name), source="sequence.json only (not a B8 pair member)")
        else:
            leg = att["leg"]
            entry.update(state=leg.get("state") if V.self_hash_ok(leg) else "INVALID (leg.json self-hash)",
                         source="leg.json")
            if not rec.get("accepted"):
                entry["b8"] = "rejected: " + "; ".join(rec.get("reasons") or [])
        if att is not None and name in seq_state and seq_state[name] != entry["state"]:
            mismatch.append(dict(leg=name, leg_json=entry["state"], sequence=seq_state[name]))
        if att is not None and name not in seq_state:
            mismatch.append(dict(leg=name, leg_json=entry["state"], sequence=None))
        legs.append(entry)
    root = Path(results_root)
    superseded = []
    for ns in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("wave2.v8-")):
        for a in sorted(p.name for p in ns.iterdir() if p.is_dir() and p.name.startswith("tg1-")):
            superseded.append(f"{ns.name}/{a}")
    smokes = sorted(p.name for p in (root / V.WAVE).iterdir() if p.is_dir() and "smoke" in p.name)
    return dict(A7=dict(done=[d for d in legs if d["state"] == "VALID" and d["b8"] is None],
                        rejected=[d for d in legs if d["state"] == "VALID" and d["b8"] is not None],
                        invalid=[d for d in legs if isinstance(d["state"], str) and d["state"].startswith("INVALID")],
                        pending=[d for d in legs if d["state"] != "VALID" and not (
                            isinstance(d["state"], str) and d["state"].startswith("INVALID"))],
                        state_mismatch=mismatch, superseded=superseded, smokes=smokes),
                **{ax: "pending (step 2)" for ax in ("A1", "A2", "A3", "A4", "M1")})


def _check_makeup(seq):
    """Refuse when sequence.json records any make-up (substitution is not implemented in step 1)."""
    makeup = seq.get("makeup")
    legs = [leg for leg in seq.get("legs") or [] if isinstance(leg, dict)
            and (leg.get("makeup") or "makeup" in str(leg.get("leg")) or "make-up" in str(leg.get("leg")))]
    if makeup or legs:
        raise RefusalError("make-up legs present: substitution not implemented in step 1")


def compute_a7(results_root, b8, b8_sha256=None):
    """`b8_sha256` = sha256 of the B8.json file bytes (the CLI passes it); None → the sha of the canonical dump
    (`p426_verify.dumps`), labelled so in the header."""
    return _compute_a7_parts(results_root, b8, b8_sha256)[0]


def _compute_a7_parts(results_root, b8, b8_sha256=None):
    """(compute_a7 record, the loaded attempts {session: {arm: attempt}}) — `compute_all` re-derives the A7 flags
    under the complete mechanical family from the attempts."""
    root = Path(results_root)
    by_session = _check_b8(root, b8)
    if b8_sha256 is None:
        b8_sha256, b8_basis = _sha_doc(b8), "canonical dump (bench.p426_verify.dumps) of the B8 record"
    else:
        b8_basis = "B8.json file bytes"
    reader = V.Reader(root)
    seq = reader.read_json(root / V.WAVE / "run" / "sequence.json", "wave2/run/sequence.json")
    v8 = reader.read_json(root / V.WAVE / "run" / "v8_base.json", "wave2/run/v8_base.json")
    if not isinstance(seq, dict) or not isinstance(v8, dict):
        raise RefusalError("wave2/run/v8_base.json or sequence.json is not an object")
    _check_makeup(seq)
    atts = {}
    for s in V.SESSIONS:
        rec = by_session[s]
        atts[s] = {arm: V.load_attempt(reader, rec.get(arm), s, f"pair {s} {arm} {rec.get(arm)}") for arm in ("off", "on")}
    _covered(reader, b8["inputs"])
    sessions = {s: _session(s, by_session[s], atts[s]["off"], atts[s]["on"]) for s in V.SESSIONS_PAIRED}
    members = [s for s in V.SESSIONS_PAIRED if sessions[s].get("status") == "accepted" and sessions[s]["n_pairs"] > 0]
    from bench import stats
    adjusted = stats.holm([sessions[s]["permutation_p"] for s in members]) if members else []
    for s, hp in zip(members, adjusted):
        sessions[s]["holm_p"] = hp
    family = dict(label=FAMILY_LABEL, members=[f"A7-{s}" for s in members], m=len(members),
                  raw_p={f"A7-{s}": sessions[s]["permutation_p"] for s in members},
                  holm_p={f"A7-{s}": sessions[s]["holm_p"] for s in members})
    valid_speed = [s for s in members if sessions[s]["speed_valid"]]
    for s in members:
        sessions[s]["speed"]["order_note"] = ("order-balanced (both sessions speed-valid)" if len(valid_speed) == 2 else
                                              "not order-balanced" if sessions[s]["speed_valid"] else
                                              "power-invalid: speed descriptive only")
    pooled_a = sum(sessions[s]["speed"]["acceptance"]["on"]["accepted"] for s in members)
    pooled_p = sum(sessions[s]["speed"]["acceptance"]["on"]["proposed"] for s in members)
    walls = {}
    for s in V.SESSIONS:
        for arm in ("off", "on"):
            a = atts[s][arm]
            walls[a["name"]] = dict(started=a["leg"].get("started"), ended=a["leg"].get("ended"), wall_s=_wall(a["leg"]),
                                    speed_valid=a["leg"].get("speed_valid"))
    reruns = seq.get("reruns") or []
    noise, noise_inputs = _noise_floor(root, atts, by_session, v8.get("sha256"))
    all_inputs = dict(sorted({**b8["inputs"], **noise_inputs}.items()))
    numpy_v, scipy_v = _versions()
    header = dict(generator=GENERATOR, generator_version=GENERATOR_VERSION, status=STATUS, numpy=numpy_v, scipy=scipy_v,
                  b8_sha256=b8_sha256, b8_sha256_basis=b8_basis, inputs_sha256=_sha_doc(all_inputs),
                  n_inputs=len(all_inputs),
                  rng=dict(paired_delta=f"bench.stats.paired_delta(iters={ITERS}, seed={SEED})",
                           permutation=PERMUTATION_METHOD, bootstrap=BOOTSTRAP_METHOD))
    return dict(header=header, axis="A7", sessions=sessions, family=family,
                acceptance_pooled=dict(accepted=pooled_a, proposed=pooled_p,
                                       acceptance=(pooled_a / pooled_p if pooled_p else None), descriptive=True),
                walls=walls, makeup=dict(status="no make-up run", reruns=reruns),
                pending={"4.5 subjective": "pending (step 3: panel run)", "4.6 memory (M1)": "pending (step 2)",
                         "A1": "pending (step 2)", "A2": "pending (step 2)", "A3": "pending (step 2)",
                         "A4": "pending (step 2)", "M1": "pending (step 2)",
                         "cross-wave check (rule 6)": "pending (step 2)"},
                flags=_flags(sessions, atts), noise_floor=noise, coverage=_coverage(root, seq, atts, by_session),
                inputs=all_inputs), atts


# -------------------------------------------------------------------------------------------------------------- render
def _pct(x):
    return "n/a" if x is None else f"{100.0 * x:.1f} %"


def _pp(x):
    return "n/a" if x is None else f"{100.0 * x:+.1f} pp"


def _f(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _list(xs):
    return ", ".join(f"`{x}`" for x in xs) if xs else "none"


def _ending_text(e):
    return f"passed {e['passed']}, converged {e['converged']}, nonconv_kind {e['nonconv_kind']}"


def _paired_lines(label, d, path):
    if d is None:
        return [f"- {label}: no pairs (`{path}`)"]
    mde = (f"MDE {_pp(d['mde_observed'])[1:]} at p_d {d['p_d']:.3f}" if d["mde_observed"] is not None else
           f"MDE {_pp(d['mde_default'])[1:]} ({d['mde_note']})")
    return [f"- {label} (`{path}`): ON − OFF {_pp(d['delta'])}, 95 % CI [{_pp(d['lo'])}, {_pp(d['hi'])}], "
            f"n = {d['n']}, discordant {d['discordant']}; **{d['label']}**; {d['loss_text']}; {mde}"]


def _session_md(s, rec, prefix="sessions", family_label=FAMILY_LABEL):
    p = f"{prefix}.{s}"
    lines = [f"## A7-{s}", "", f"- Pair: OFF `{rec['off']}` / ON `{rec['on']}`; B8 {rec['status']}"
             + (f"; labels {_list(rec['labels'])}" if rec["labels"] else "")]
    if rec["status"] != "accepted":
        lines += [f"- B8 reasons (`{p}.b8_reasons`):"] + [f"  - {r}" for r in rec["b8_reasons"]] + [""]
        return lines
    lines += ["", f"### Quality, mechanical (`{p}.quality`)", "",
              "| arm | attempt | planned | acc_strict@budget | acc (lenient) | conv % | nonconv_kinds | transport_dnf |",
              "|---|---|---|---|---|---|---|---|"]
    for arm in ("off", "on"):
        q = rec["quality"][arm]
        kinds = ", ".join(f"{k} {v}" for k, v in q["nonconv_kinds"].items()) or "none"
        lines.append(f"| {arm.upper()} | `{q['attempt']}` | {q['planned']} | {q['strict']}/{q['planned']} "
                     f"({_pct(q['acc_strict_at_budget'])}) | {q['lenient']}/{q['planned']} ({_pct(q['acc'])}) | "
                     f"{_f(q['conv_pct'], 1)} | {kinds} | {len(q['transport_dnf'])} |")
    lines += [""]
    lines += _paired_lines("acc_strict@budget (ranking key)", rec["paired_strict"], f"{p}.paired_strict")
    lines += _paired_lines("acc (lenient)", rec["paired_lenient"], f"{p}.paired_lenient")
    lines += [f"- Permutation p (strict, `{p}.permutation_p`): {_f(rec['permutation_p'], 4)}; Holm-adjusted "
              f"(`{p}.holm_p`): {_f(rec.get('holm_p'), 4)} — {family_label}"]
    c = rec["c269"]
    lines += _paired_lines(f"C269 sensitivity, without client_inactivity pairs {_list(c['excluded'])}",
                           c["paired_strict"], f"{p}.c269.paired_strict")
    lines += [f"- Identical final trees (C217, recorded for step 3; `{p}.identical`): {rec['identical']['count']} / "
              f"{rec['n_pairs']}", ""]
    ex = rec["exclusive"]
    lines += [f"### Exclusive solves and edit competence (`{p}.exclusive`, `{p}.edit`)", "",
              f"- ON-only strict solves: {_list(ex['on_only'])}", f"- OFF-only strict solves: {_list(ex['off_only'])}",
              "", "| arm | file_changed | test_modified | tool_bounds_rejections (items) |", "|---|---|---|---|"]
    for arm in ("off", "on"):
        e = rec["edit"][arm]
        lines.append(f"| {arm.upper()} | {e['file_changed']} | {e['test_modified']} | {e['tool_bounds_rejections']} "
                     f"({e['tool_bounds_rejection_items']}) |")
    lines += ["", f"### DNF (C235 G1; `{p}.dnf`)", ""]
    for arm in ("off", "on"):
        t = rec["dnf"][arm]
        lines.append(f"- {arm.upper()}: " + ("none" if not t else
                                             "; ".join(f"{k}: {len(v)} ({_list(v)})" for k, v in t.items())))
    lines += ["", f"### Runaway tax (`{p}.tax`)", "", "| arm | " + " | ".join(TAX_CATEGORIES) + " | union |",
              "|---|" + "---|" * (len(TAX_CATEGORIES) + 1)]
    for arm in ("off", "on"):
        t = rec["tax"][arm]
        lines.append(f"| {arm.upper()} | " + " | ".join(str(t["counts"][c]) for c in TAX_CATEGORIES)
                     + f" | {t['union']} |")
    for arm in ("off", "on"):
        t = rec["tax"][arm]
        lines.append(f"- {arm.upper()} union items: {_list(t['union_items'])}")
    sp = rec["speed"]
    lines += ["", f"### Speed (`{p}.speed`; {sp['order_note']}; "
                  f"{'inference' if sp['inference'] else 'descriptive only'})", ""]
    for name in ("primary", "sensitivity"):
        d = sp[name]
        lines.append(f"- Decode ratio ON/OFF, {name}: geometric mean {_f(d['geomean_ratio'])}, 95 % CI "
                     f"[{_f(d['lo'])}, {_f(d['hi'])}], n = {d['n']}; dropped "
                     + ("none" if not d["dropped"] else
                        "; ".join(f"`{x['id']}` ({x['reason']})" for x in d["dropped"])))
    for arm in ("off", "on"):
        a = sp["acceptance"][arm]
        lines.append(f"- Acceptance {arm.upper()}: {a['accepted']} / {a['proposed']} = {_f(a['acceptance'])}")
    lines += [""]
    return lines


def render_md(signals):
    """Fix 15: dispatches on the record shape — an `all` record (generator_version p613-step2) renders through
    `render_all`; an A7 record renders exactly as step 1."""
    if isinstance(signals.get("header"), dict) and signals["header"].get("generator_version") in (
            ALL_VERSION, STEP3_VERSION, STEP4_VERSION):
        return render_all(signals)
    h = signals["header"]
    lines = [f"# P426 signals — {h['status']}", "",
             f"Generated by `{h['generator']}` ({h['generator_version']}); never hand-edited. numpy {h['numpy']}, "
             f"scipy {h['scipy']}.", "",
             f"- B8.json sha256 ({h['b8_sha256_basis']}): `{h['b8_sha256']}`",
             f"- Inputs sha set (`header.inputs_sha256`, sha256 of the canonical `inputs` map, {h['n_inputs']} files): "
             f"`{h['inputs_sha256']}`",
             f"- RNG: {h['rng']['paired_delta']}; permutation {h['rng']['permutation']}; bootstrap {h['rng']['bootstrap']}",
             "- Paired deltas read only delta / lo / hi / degenerate / discordance_upper95 of `bench.stats.paired_delta`.",
             "- No composite, no successes_per_hour, no pass@1|converged ranking.", ""]
    for s in V.SESSIONS_PAIRED:
        lines += _session_md(s, signals["sessions"][s])
    fam = signals["family"]
    lines += ["## Mechanical family (`family`)", "", f"- {fam['label']}; m = {fam['m']}; members {_list(fam['members'])}"]
    for m in fam["members"]:
        lines.append(f"- {m}: raw p {_f(fam['raw_p'][m], 4)}, Holm p {_f(fam['holm_p'][m], 4)}")
    ap = signals["acceptance_pooled"]
    lines += [f"- Pooled ON acceptance s1 + s2 (descriptive; `acceptance_pooled`): {ap['accepted']} / {ap['proposed']} "
              f"= {_f(ap['acceptance'])}", f"- Make-up (`makeup`): {signals['makeup']['status']}", ""]
    lines += ["## Per-leg wall (descriptive; `walls`)", "", "| attempt | started | ended | wall s | speed_valid |",
              "|---|---|---|---|---|"]
    for name, w in sorted(signals["walls"].items()):
        lines.append(f"| `{name}` | {w['started']} | {w['ended']} | {_f(w['wall_s'], 0)} | {w['speed_valid']} |")
    lines += ["", "## Pending (`pending`)", ""] + [f"- {k}: {v}" for k, v in sorted(signals["pending"].items())] + [""]
    lines += ["## Flags (`flags`; listed, never vetoes)", ""]
    if not signals["flags"]:
        lines.append("- none")
    for f in signals["flags"]:
        lines.append(f"- {f['text']}")
        for it in f.get("items") or []:
            lines.append(f"  - `{it['id']}`: {it['arm'].upper()} {_ending_text(it['ending'])}; "
                         f"{it['other_arm'].upper()} {_ending_text(it['other_ending'])}")
    lines += _noise_md(signals["noise_floor"])
    cov = signals["coverage"]
    lines += ["", "## Coverage (`coverage`)", ""] + _a7_coverage_lines(cov["A7"])
    lines += [f"- {ax}: {cov[ax]}" for ax in ("A1", "A2", "A3", "A4", "M1")]
    return "\n".join(lines) + "\n"


def _noise_md(nf):
    lines = ["", "## Noise floor (C273; `noise_floor`)", "",
              f"Same-epoch, reload vs pilot (planned slots; a DNF slot is a non-success): {nf['same_epoch']['status']}"]
    for arm in ("off", "on"):
        d = nf["same_epoch"].get(arm)
        if d is not None:
            lines.append(f"- {arm.upper()} (`{d['reload']}` vs `{d['pilot']}`): {d['flips']} / {d['common']} flips "
                         f"{_list(d['flip_items'])}")
    c = nf["cross_epoch"]
    lines += ["", f"Cross-epoch, `wave2` (v8 `{c['v8_sha256_current']}`) vs `{c['namespace']}` (v8 "
                  f"`{c['v8_sha256_superseded']}`), per arm and matched attempt (no pooled headline)"
              + ("" if c["available"] else " (namespace unavailable)") + ":"]
    for arm in ("off", "on"):
        pa = (c.get("per_arm") or {}).get(arm)
        if pa is not None:
            lines.append(f"- {arm.upper()}: {pa['flips']} / {pa['common']} flips over {pa['matches']} matched "
                         f"attempt(s)")
        for m in c["matches"]:
            if m["arm"] == arm:
                lines.append(f"  - `{m['current']}` vs `{m['superseded']}`: {m['flips']} / {m['common']} "
                             f"{_list(m['flip_items'])}")
    for m in c["excluded"]:
        lines.append(f"- excluded `{m['current']}` vs `{m['superseded']}`: {m['reason']}")
    return lines


def _a7_coverage_lines(a7):
    def _legs(ds):
        return _list([f"{d['leg']}.a{d['attempt']}" + (f" ({d['b8']})" if d.get("b8") else "") for d in ds])

    return [f"- A7 done: {_legs(a7['done'])}",
              f"- A7 rejected by B8: {_legs(a7['rejected'])}",
              f"- A7 invalid: {_legs(a7['invalid'])}",
              f"- A7 pending: {_legs(a7['pending'])}",
              "- A7 state mismatch (leg.json vs sequence.json): "
              + (", ".join(f"`{m['leg']}` leg.json {m['leg_json']} / sequence.json {m['sequence']}"
                           for m in a7["state_mismatch"]) or "none"),
              f"- A7 superseded (never scored): {_list(a7['superseded'])}",
              f"- Smokes (never scored): {_list(a7['smokes'])}"]


# ===================================================================================================== all (step 2)
ALL_VERSION = "p613-step2"
ALL_STATUS = "PROVISIONAL — subjective panel pending (step 3)"
FAMILY_COMPLETE = "complete"
FAMILY_ORDER = ("A1", "A7-s1", "A7-s2")


def _check_all_b8(rows_root, b8):
    """Structure + every `inputs` file (rows_root-relative) unchanged; the union covers each axis's own inputs."""
    if not isinstance(b8, dict) or not isinstance(b8.get("axes"), dict):
        raise RefusalError("B8.json is not an `all` verifier record (no axes)")
    axes = b8["axes"]
    if not isinstance(axes.get("A7"), dict) or not isinstance(axes.get("wave1"), dict):
        raise RefusalError("B8.json axes lack A7 or wave1")
    if not isinstance(b8.get("cross_wave"), dict):
        raise RefusalError("B8.json has no cross_wave record")
    inputs = b8.get("inputs")
    if not isinstance(inputs, dict) or not inputs:
        raise RefusalError("B8.json has no inputs map")
    root = Path(rows_root)
    confined = V.Reader(rows_root, confine=True)
    for rel in sorted(inputs):
        if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
            raise RefusalError(f"B8.json input {rel!r} is not a rows_root-relative path")
        confined.check_confined(root / rel, "B8.json input")     # fix 5: resolved under rows_root
        try:
            data = (root / rel).read_bytes()
        except OSError:
            raise RefusalError(f"B8 input {rel} is missing") from None
        got = hashlib.sha256(data).hexdigest()
        if got != inputs[rel]:
            raise RefusalError(f"B8 input {rel} changed: sha256 {got} != B8 {inputs[rel]}")
    a7_in = axes["A7"].get("inputs") if isinstance(axes["A7"].get("inputs"), dict) else {}
    w1_in = axes["wave1"].get("inputs") if isinstance(axes["wave1"].get("inputs"), dict) else {}
    for rel, sha in list({f"p426/{k}": v for k, v in a7_in.items()}.items()) + list(w1_in.items()):
        if inputs.get(rel) != sha:
            raise RefusalError(f"B8.json inputs union does not cover axis input {rel}")


def compute_all(results_root, rows_root, b8, b8_sha256=None, panel=None, evidence_ref=None, repo=None):
    """One signals record: A7 (step 1) + Wave 1 (A1, M1, A2, A3, A4) + the complete mechanical family + flags.
    ``panel`` (step 3) = the frozen panel directory: adds §4.5 `subjective`, its flag, and the step-3 header / status;
    ``panel=None`` returns the step-2 record unchanged (E1: ``--panel`` is optional).
    ``evidence_ref`` (step 4) adds the A7 first-divergence section (`divergence`, C284), its inputs, the header's
    evidence ref, and status FINAL when every pre-registered section is present; ``None`` → the step-3 record unchanged.
    ``repo`` = the git work tree holding the ref (None: the one containing ``results_root``).
    ``evidence_ref`` without ``panel`` refuses (no step-4 header on a sheet without §4.5)."""
    if evidence_ref is not None and panel is None:
        raise RefusalError("--evidence-ref requires --panel (the step-4 sheet carries §4.5 subjective)")
    rec = _compute_all_step2(results_root, rows_root, b8, b8_sha256)
    if panel is not None:
        subj, panel_header = compute_subjective(panel, results_root, b8, rec, b8_sha256, rows_root=rows_root)
        rec["subjective"] = subj
        rec["flags"] = rec["flags"] + subjective_flags(subj)
        rec["header"] = dict(rec["header"], generator_version=STEP3_VERSION, status=STEP3_STATUS, panel=panel_header)
        rec["pending"] = {k: v for k, v in rec["pending"].items() if k != "4.5 subjective"}
    if evidence_ref is None:
        return rec
    from bench import p426_signals_divergence as D

    div = D.a7_divergence(results_root, b8, evidence_ref, Path(results_root) if repo is None else repo)
    div_inputs = div.pop("inputs")
    rec["divergence"] = dict(div, n_inputs=len(div_inputs))
    rec["flags"] = rec["flags"] + D.flags(div)
    rec["inputs"] = dict(sorted({**rec["inputs"], **div_inputs}.items()))
    final = _final_ready(rec)
    rec["header"] = dict(rec["header"], generator_version=STEP4_VERSION, evidence_ref=div["evidence_ref"],
                         evidence_ref_given=div["evidence_ref_given"],
                         inputs_sha256=_sha_doc(rec["inputs"]), n_inputs=len(rec["inputs"]),
                         status=FINAL_STATUS if final["ready"] else rec["header"]["status"], final=final)
    if final["ready"]:
        rec["pending"] = {k: v for k, v in rec["pending"].items() if k != "final sheet + recommendation"}
    return rec


# ======================================================================================================= final (step 4)
STEP4_VERSION = "p613-step4"
FINAL_STATUS = "FINAL — P426 certification evidence"
WAVE1_AXES = ("A1", "M1", "A2", "A3", "A4")


def _final_ready(rec):
    """{ready, missing}: B8, every Wave 1 axis (every block B8-accepted), A7-s1 / s2 accepted, the panel and a complete
    divergence section present."""
    missing = []
    for ax in WAVE1_AXES:
        blocks = (rec.get(ax) or {}).get("blocks")
        if not isinstance(blocks, dict) or set(blocks) != set(V.W1_BLOCKS) or any(
                not isinstance(b, dict) or b.get("status") != "accepted" for b in blocks.values()):
            missing.append(ax)
    for s in V.SESSIONS_PAIRED:
        if ((rec.get("A7") or {}).get("sessions") or {}).get(s, {}).get("status") != "accepted":
            missing.append(f"A7-{s}")
    if "subjective" not in rec:
        missing.append("panel")
    if not (rec.get("divergence") or {}).get("complete"):
        missing.append("divergence")
    return dict(ready=not missing, missing=missing)


def _compute_all_step2(results_root, rows_root, b8, b8_sha256=None):
    from bench import p426_signals_wave1 as W
    from bench import stats

    V.check_roots(results_root, rows_root)
    _check_all_b8(rows_root, b8)
    if b8_sha256 is None:
        b8_sha256, b8_basis = _sha_doc(b8), "canonical dump (bench.p426_verify.dumps) of the B8 record"
    else:
        b8_basis = "B8.json file bytes"
    a7, atts = _compute_a7_parts(results_root, b8["axes"]["A7"], b8_sha256)
    w1, w1_inputs = W.compute_wave1(rows_root, b8["axes"]["wave1"])
    for rel, sha in sorted(w1_inputs.items()):
        if b8["inputs"].get(rel) != sha:
            raise RefusalError(f"input {rel} is not covered by B8.json (B8 {b8['inputs'].get(rel)!r}, now {sha})")
    sessions = a7["sessions"]
    raw = {}
    a1_blocks_accepted = w1["A1"]["both"]["blocks"] == list(V.W1_BLOCKS)
    if a1_blocks_accepted and w1["A1"]["both"]["permutation_p"] is not None:     # fix 7: both A1 blocks accepted
        raw["A1"] = w1["A1"]["both"]["permutation_p"]
    for m, p in a7["family"]["raw_p"].items():
        raw[m] = p
    members = [m for m in FAMILY_ORDER if m in raw]
    adjusted = stats.holm([raw[m] for m in members]) if members else []
    holm_p = dict(zip(members, adjusted))
    for s in V.SESSIONS_PAIRED:
        if f"A7-{s}" in holm_p:
            sessions[s]["holm_p"] = holm_p[f"A7-{s}"]
    w1["A1"]["both"]["holm_p"] = holm_p.get("A1")
    label = FAMILY_COMPLETE if members == list(FAMILY_ORDER) else (
        f"INCOMPLETE: missing {[m for m in FAMILY_ORDER if m not in members]}"
        + ("" if a1_blocks_accepted else
           f" (A1 is a member only when both A1 blocks are B8-accepted; accepted: {w1['A1']['both']['blocks']})"))
    family = dict(label=label, members=members, m=len(members), raw_p={m: raw[m] for m in members}, holm_p=holm_p,
                  method="bench.stats.holm over the per-member sign-flip permutation p (A1: both blocks, sorted by "
                         "(block, id))")
    flags = _flags(sessions, atts) + W.flags(w1, holm_p.get("A1"), b8["cross_wave"])
    all_inputs = dict(b8["inputs"])
    for rel, sha in a7["inputs"].items():
        all_inputs[f"p426/{rel}"] = sha
    all_inputs.update(w1_inputs)
    all_inputs = dict(sorted(all_inputs.items()))
    numpy_v, scipy_v = _versions()
    header = dict(generator=GENERATOR, generator_version=ALL_VERSION, status=ALL_STATUS, numpy=numpy_v, scipy=scipy_v,
                  b8_sha256=b8_sha256, b8_sha256_basis=b8_basis, inputs_sha256=_sha_doc(all_inputs),
                  n_inputs=len(all_inputs), rng=a7["header"]["rng"])
    cw = b8["cross_wave"]
    coverage = dict(A7=a7["coverage"]["A7"], wave1=w1["coverage"])
    return dict(header=header,
                A7=dict(sessions=sessions, walls=a7["walls"], acceptance_pooled=a7["acceptance_pooled"],
                        makeup=a7["makeup"]),
                A1=w1["A1"], M1=w1["M1"], A2=w1["A2"], A3=w1["A3"], A4=w1["A4"],
                family=family, flags=flags, noise_floor=a7["noise_floor"], coverage=coverage,
                identity=dict(per_axis=w1["identity"], total=w1["identity_total"]),
                cross_wave={k: cw.get(k) for k in ("wave1_off", "wave2_off", "files", "flag", "entry_equal",
                                                   "globals_equal", "gitlinks_equal", "closure_files", "qualify")},
                pending={"4.5 subjective": "pending (step 3: panel run)",
                         "final sheet + recommendation": "pending (step 4)"},
                inputs=all_inputs)


# ================================================================================================= §4.5 subjective (step 3)
STEP3_VERSION = "p613-step3"
STEP3_STATUS = "PROVISIONAL — final review pending (step 4)"
SUBJ_FAMILY = ("A1", "A2", "A3", "A7-s1", "A7-s2")
SUBJ_WAVE1 = ("A1", "A2", "A3")
SUBJ_MIN_JUDGED = 5
IDENTICAL_LABEL = "identical outputs; panel not run"
NOT_TESTED_LABEL = "reported, not tested"
CONDITIONAL_LABEL = "conditional on both-pass"
A4_LABEL = "descriptive, never tested (recert S7)"


def _verdict_score(row):
    """ON 1 / tie 0.5 / OFF 0 of one admitted verdict (`p426_panel.item_scores` on that single row, build s2)."""
    from bench import p426_panel as P

    return P.item_scores([row], build=P.A7_BUILD)[row["item_id"]]["score"]


def _provenance(rows):
    seen = {}
    for r in rows:
        key = tuple(str(r.get(k)) for k in ("judge", "family", "model", "client", "client_version", "prompt_sha"))
        seen[key] = seen.get(key, 0) + 1
    return [dict(zip(("judge", "family", "model", "client", "client_version", "prompt_sha"), k), verdicts=n)
            for k, n in sorted(seen.items())]


def _panel_files_sha(panel_dir):
    root = Path(panel_dir)
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(root.rglob("*")) if p.is_file() and p.name != "FROZEN.json"}
    return dict(sorted(files.items()))


def _canon(doc):
    return json.dumps(doc, sort_keys=True)


def _wave1_member(ax, e, labels):
    n = e["identical"]
    return dict(member=ax, identical=n, eligible=e["eligible"], keys=e["keys"], judged=0, score_identical=0.5,
                tested=False, labels=labels, rule=e["rule"],
                not_both_correct_left_out=e["not_both_correct"], not_both_correct_keys=e["not_both_correct_keys"],
                one_arm_pass_left_out=e["one_arm_correct"], pairs_rejected=e["pairs_rejected"],
                raw_mean=None, mean_with_identical=(0.5 if n else None), permutation_p=None, holm_p=None,
                length_adjusted=None, planned_verdicts=0, missing_verdicts=0, excluded_items={}, provenance=[],
                single_family=None)


def _a4_draws(signals):
    out = {}
    for block, st in sorted(((signals.get("A4") or {}).get("blocks") or {}).items()):
        q = st.get("quality") if isinstance(st, dict) else None
        if not isinstance(q, dict):
            out[block] = dict(status=(st or {}).get("status"))
            continue
        out[block] = {arm: dict(strict_draws=q[arm]["strict_draws"], planned=q[arm]["planned"],
                                budget_hits=q[arm]["budget_hits"]) for arm in ("off", "on")}
    return out


def compute_subjective(panel_dir, results_root, b8, signals, b8_sha256=None, rows_root=None):
    """§4.5: (`subjective` record, header `panel` block). Items enter through `p426_panel.admit`; the frozen item set
    must equal the a7_select set recomputed from the B8-accepted data, the frozen Wave 1 eligibility the one recomputed
    (E3); verdicts only against unchanged packets, bound to this FROZEN.json, provenance from FROZEN (`a7_ingest`)."""
    from bench import judge_pairwise as jp
    from bench import p426_panel as P
    from bench import stats

    panel_dir = Path(panel_dir)
    frozen, rows, report = P.a7_ingest(panel_dir)              # check_frozen first: missing FROZEN.json refuses
    if b8_sha256 is not None and frozen.get("b8_sha256") != b8_sha256:
        raise RefusalError(f"panel FROZEN.json b8_sha256 {frozen.get('b8_sha256')} != B8.json {b8_sha256}")
    elig = P.wave1_eligibility(Path(results_root).parent if rows_root is None else rows_root, b8)
    if _canon(frozen.get("wave1")) != _canon(elig):
        raise RefusalError("panel FROZEN.json wave1 eligibility != the one recomputed from the B8-accepted data")
    part = P.a7_partition(results_root, b8)
    want = sorted((s, rid) for s in P.A7_SESSIONS for rid in part[s]["items"])
    f_items = frozen["items"]
    got = sorted((i["session"], i["id"]) for i in f_items)
    if got != want:
        raise RefusalError(f"panel item set differs from the B8-accepted both-pass non-identical set "
                           f"(frozen {len(got)}, now {len(want)})")
    judges = frozen["judges"]
    labels = [j["label"] for j in judges]
    families = sorted({j["family"] for j in judges})
    per_item_planned = len(labels) * len(jp.ORDERS)
    admitted, adm_excluded = P.admit(rows, labels)
    excluded_by_item = {it: kind for kind, its in adm_excluded.items() for it in its}
    valid_by_item = {}
    for r in rows:
        if r.get("choice") in ("A", "B", "tie"):
            valid_by_item[r["item_id"]] = valid_by_item.get(r["item_id"], 0) + 1
    meta = {i["item"]: i for i in f_items}
    members = {}
    for ax in SUBJ_WAVE1:
        members[ax] = _wave1_member(ax, elig["per_axis"][ax], [IDENTICAL_LABEL, NOT_TESTED_LABEL, CONDITIONAL_LABEL])
    a4 = _wave1_member("A4", elig["per_axis"]["A4"], [IDENTICAL_LABEL, A4_LABEL, CONDITIONAL_LABEL])
    a4["draws"] = _a4_draws(signals)
    for s in P.A7_SESSIONS:
        ax = f"A7-{s}"
        p = part[s]
        s_items = sorted(i["item"] for i in f_items if i["session"] == s)
        adm = {it: admitted[it] for it in s_items if it in admitted}
        adm_rows = [r for it in sorted(adm) for r in adm[it]]
        scores = P.item_scores(adm_rows, build=P.A7_BUILD)
        vec = sorted([(it.split("/", 1)[1], scores[it]["score"] - 0.5) for it in adm]
                     + [(rid, 0.0) for rid in p["identical"]])
        judged = len(adm)
        planned = len(s_items) * per_item_planned
        valid = sum(valid_by_item.get(it, 0) for it in s_items)
        valid_capped = sum(min(valid_by_item.get(it, 0), per_item_planned) for it in s_items)   # fix 10
        duplicates = sum(max(0, valid_by_item.get(it, 0) - per_item_planned) for it in s_items)
        la_rows = [dict(item=r["item_id"], score=_verdict_score(r),
                        log_len_ratio=math.log(meta[r["item_id"]]["len_on"] / meta[r["item_id"]]["len_off"]))
                   for r in adm_rows]
        la = None
        if la_rows:
            res = P.length_adjusted(la_rows)
            la = dict(res, ci=list(res["ci"]))
        fams = sorted({str(r.get("family")) for r in adm_rows})
        members[ax] = dict(
            member=ax, identical=len(p["identical"]), keys=None, judged=judged, score_identical=0.5,
            tested=judged >= SUBJ_MIN_JUDGED,
            labels=[CONDITIONAL_LABEL] + ([] if judged >= SUBJ_MIN_JUDGED else [NOT_TESTED_LABEL]),
            one_arm_pass_left_out=len(p["one-arm-pass"]), one_arm_pass_ids=list(p["one-arm-pass"]),
            neither_pass=len(p["neither-pass"]), packets=len(s_items),
            item_scores={it: scores[it] for it in sorted(adm)},
            raw_mean=(sum(scores[it]["score"] for it in adm) / judged if judged else None),
            mean_with_identical=(0.5 + sum(d for _, d in vec) / len(vec) if vec else None),
            test_vector_n=len(vec), permutation_p=None, holm_p=None, length_adjusted=la,
            planned_verdicts=planned, valid_verdicts=valid, duplicate_verdicts=duplicates,
            missing_verdicts=planned - valid_capped,
            excluded_items={k: sorted(it for it in s_items if excluded_by_item.get(it) == k)
                            for k in sorted(set(excluded_by_item.values()))},
            not_admitted=sorted(it for it in s_items if it not in adm),
            provenance=_provenance(adm_rows),
            single_family=(len(fams) < 2) if adm_rows else None)
        members[ax]["_vec"] = [d for _, d in vec]
    tested = [m for m in SUBJ_FAMILY if members[m]["tested"]]           # m fixed by the < 5 rule before any p
    for m in tested:
        members[m]["permutation_p"] = permutation_p(members[m]["_vec"])
    adjusted = stats.holm([members[m]["permutation_p"] for m in tested]) if tested else []
    for m, hp in zip(tested, adjusted):
        members[m]["holm_p"] = hp
    for m in members.values():
        m.pop("_vec", None)
    frozen_bytes = (panel_dir / P.FROZEN_NAME).read_bytes()
    files = _panel_files_sha(panel_dir)
    verdict_files = {k: v for k, v in files.items() if k.endswith(".verdict.json")}
    header = dict(frozen_sha256=hashlib.sha256(frozen_bytes).hexdigest(), files_sha256=_sha_doc(files),
                  n_files=len(files), n_verdict_files=len(verdict_files))
    rec = dict(family=list(SUBJ_FAMILY), tested=tested, m=len(tested), min_judged=SUBJ_MIN_JUDGED,
               members={m: members[m] for m in SUBJ_FAMILY}, descriptive=dict(A4=a4),
               judges=[{k: j.get(k) for k in ("label", "family", "client", "model")} for j in judges],
               families=families, single_family_panel=len(families) < 2,
               rubric=frozen.get("rubric"), rubric_sha256=frozen.get("rubric_sha256"),
               evidence_ref=frozen.get("evidence_ref"), counts=frozen.get("counts"),
               wave1=dict(keys=elig["keys"], eligible=elig["eligible"], identical=elig["identical"],
                          not_both_correct=elig["not_both_correct"]),
               ingest=dict(report, rows=len(rows), manifest_rows=frozen["counts"]["planned_verdicts"]),
               method=("item score = mean over judges x orders (ON 1 / tie 0.5 / OFF 0; p426_panel.item_scores build "
                       "s2); permutation_p on score - 0.5 over judged + C217-identical (0) items sorted by id; "
                       "length_adjusted on one row per admitted verdict, log_len_ratio = ln(len_ON / len_OFF) of the "
                       "final-tree diff characters (the packet carries the diff verbatim); Holm over the tested "
                       "members; Wave 1 over the panel-eligible keys (E3: A1 both correct, A2 / A3 every key, A4 "
                       "both strict draws)"))
    return rec, header


def subjective_flags(subj):
    flags = []
    for m in subj["tested"]:
        rec = subj["members"][m]
        hp, mean = rec["holm_p"], rec["mean_with_identical"]
        if hp is not None and hp < FLAG_HOLM_P and mean is not None and mean < 0.5:
            flags.append(dict(flag="subjective_holm_p_off_better", member=m, value=hp, items=[],
                              text=f"{m} subjective Holm-adjusted p {hp:.4f} < {FLAG_HOLM_P} favouring OFF "
                                   f"(mean score {mean:.3f})"))
    return flags


def _wave1_line(p, path, r, label):
    return (f"- {r['member']} (`{p}.{path}`): {r['identical']} / {r['eligible']} panel-eligible keys {IDENTICAL_LABEL} "
            f"(rule: {r['rule']}); each scores 0.5; judged 0; {label}; not both correct left out "
            f"{r['not_both_correct_left_out']} of {r['keys']} B8 keys (one arm correct {r['one_arm_pass_left_out']})"
            + (f"; B8-rejected pairs {_list(r['pairs_rejected'])}" if r["pairs_rejected"] else ""))


def _subjective_md(subj):
    p = "subjective"
    c = subj.get("counts") or {}
    ing = subj["ingest"]
    w1 = subj["wave1"]
    lines = ["## Subjective panel (§4.5; `subjective`)", "",
             f"- Two-family blind pairwise panel (C161 / C207), rubric `{subj['rubric']}` (sha256 "
             f"`{subj['rubric_sha256']}`), evidence ref `{subj['evidence_ref']}`; judges "
             + ", ".join(f"`{j['label']}` ({j['family']}, {j['client']})" for j in subj["judges"])
             + ("; **single-family panel (C166 / C206)**" if subj["single_family_panel"] else ""),
             f"- Frozen before any verdict: {c.get('items')} packets, {c.get('planned_verdicts')} planned verdicts; "
             f"ingest (`{p}.ingest`): {ing['rows']} bound verdict rows of {ing['manifest_rows']}, missing "
             f"{ing['missing']}, failed {ing['failed']}, unsealed {ing['unsealed']}, unbound {ing['unbound']}, "
             f"rejected (provenance != FROZEN) {ing['rejected']}, unparseable {ing['unparseable']}",
             f"- Wave 1 (`{p}.wave1`, E3): {w1['identical']} / {w1['eligible']} panel-eligible keys identical "
             f"(of {w1['keys']} B8 keys; {w1['not_both_correct']} not both correct, excluded)",
             f"- Family {_list(subj['family'])}; tested (judged >= {subj['min_judged']}): {_list(subj['tested'])}; "
             f"Holm m = {subj['m']} (`{p}.m`)", f"- Method: {subj['method']}", "",
             "| member | judged | identical (0.5) | raw mean (judged) | mean incl. identical | length-adjusted [95 % CI] "
             "| permutation p | Holm p | missing verdicts | not admitted | left out (one-arm-pass / not both correct) "
             "| labels |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in subj["family"]:
        r = subj["members"][m]
        la = r["length_adjusted"]
        la_text = "n/a" if la is None else f"{la['adjusted']:.3f} [{la['ci'][0]:.3f}, {la['ci'][1]:.3f}]"
        left = r["one_arm_pass_left_out"] if m not in SUBJ_WAVE1 else r["not_both_correct_left_out"]
        lines.append(f"| {m} | {r['judged']} | {r['identical']} | {_f(r['raw_mean'])} | {_f(r['mean_with_identical'])} | "
                     f"{la_text} | {_f(r['permutation_p'], 4)} | {_f(r['holm_p'], 4)} | {r['missing_verdicts']} | "
                     f"{len(r.get('not_admitted') or [])} | {left} | {'; '.join(r['labels'])} |")
    lines.append("")
    for m in subj["family"]:
        r = subj["members"][m]
        if m in SUBJ_WAVE1:
            lines.append(_wave1_line(p, f"members.{m}", r, NOT_TESTED_LABEL))
            continue
        lines.append(f"- {m} (`{p}.members.{m}`): {r['packets']} packets, judged {r['judged']}, planned verdicts "
                     f"{r['planned_verdicts']}, valid {r['valid_verdicts']}, missing {r['missing_verdicts']}, "
                     f"duplicate {r['duplicate_verdicts']}; not admitted {_list(r['not_admitted'])}"
                     + "".join(f"; {k} {_list(v)}" for k, v in r["excluded_items"].items())
                     + f"; one-arm-pass left out {_list(r['one_arm_pass_ids'])}; neither-pass {r['neither_pass']}"
                     + ("; single-family verdicts (C166 / C206)" if r["single_family"] else ""))
        for pv in r["provenance"]:
            lines.append(f"  - verdicts {pv['verdicts']}: judge `{pv['judge']}` ({pv['family']}), model `{pv['model']}`, "
                         f"client `{pv['client']}` {pv['client_version']}, prompt sha `{pv['prompt_sha']}`")
    a4 = subj["descriptive"]["A4"]
    lines.append(_wave1_line(p, "descriptive.A4", a4, A4_LABEL))
    for block, d in a4["draws"].items():
        if "off" not in d:
            lines.append(f"  - {block}: {d.get('status')}")
            continue
        lines.append(f"  - {block} draw distribution: " + "; ".join(
            f"{arm.upper()} strict draws {d[arm]['strict_draws']} / {d[arm]['planned']}, budget hits "
            f"{d[arm]['budget_hits']}" for arm in ("off", "on")))
    return lines + [""]


def _flag_item_text(it):
    from bench import p426_signals_wave1 as W

    if isinstance(it, dict) and "what" in it and "key" in it:
        return W.flag_item_text(it)
    if isinstance(it, dict) and "ending" in it:
        return (f"  - `{it['id']}`: {it['arm'].upper()} {_ending_text(it['ending'])}; "
                f"{it['other_arm'].upper()} {_ending_text(it['other_ending'])}")
    return f"  - `{'/'.join(map(str, it)) if isinstance(it, list) else it}`"


def render_all(signals):
    from bench import p426_signals_wave1 as W

    h = signals["header"]
    lines = [f"# P426 signals — {h['status']}", "",
             f"Generated by `{h['generator']}` ({h['generator_version']}); never hand-edited. numpy {h['numpy']}, "
             f"scipy {h['scipy']}.", "",
             f"- B8.json sha256 ({h['b8_sha256_basis']}): `{h['b8_sha256']}`",
             f"- Inputs sha set (`header.inputs_sha256`, sha256 of the canonical `inputs` map, {h['n_inputs']} files): "
             f"`{h['inputs_sha256']}`",
             f"- RNG: {h['rng']['paired_delta']}; permutation {h['rng']['permutation']}; bootstrap {h['rng']['bootstrap']}",
             "- Paired deltas read only delta / lo / hi / degenerate / discordance_upper95 of `bench.stats.paired_delta`.",
             "- No composite, no successes_per_hour, no pass@1|converged ranking.", ""]
    if "panel" in h:
        pn = h["panel"]
        lines[-1:-1] = [f"- Panel (`header.panel`): FROZEN.json sha256 `{pn['frozen_sha256']}`; panel files sha set "
                        f"`{pn['files_sha256']}` ({pn['n_files']} files, {pn['n_verdict_files']} verdict files)"]
    if "evidence_ref" in h:
        fin = h["final"]
        lines[-1:-1] = [f"- Evidence ref (`header.evidence_ref`, the `evidence` branch commit read with `git show`): "
                        f"`{h['evidence_ref']}` (given as `{h['evidence_ref_given']}`, "
                        "`header.evidence_ref_given`)",
                        "- Final (`header.final`): " + ("every pre-registered section present" if fin["ready"] else
                                                       f"not final, missing {_list(fin['missing'])}")]
    fam = signals["family"]
    fam_label = f"mechanical family {fam['label']} (m = {fam['m']})"
    for s in V.SESSIONS_PAIRED:
        lines += _session_md(s, signals["A7"]["sessions"][s], prefix="A7.sessions", family_label=fam_label)
    ap = signals["A7"]
    lines += [f"### A7 pooled acceptance and make-up", "",
              f"- Pooled ON acceptance s1 + s2 (descriptive; `A7.acceptance_pooled`): "
              f"{ap['acceptance_pooled']['accepted']} / {ap['acceptance_pooled']['proposed']} = "
              f"{_f(ap['acceptance_pooled']['acceptance'])}", f"- Make-up (`A7.makeup`): {ap['makeup']['status']}", "",
              "### A7 per-leg wall (descriptive; `A7.walls`)", "", "| attempt | started | ended | wall s | speed_valid |",
              "|---|---|---|---|---|"]
    for name, w in sorted(ap["walls"].items()):
        lines.append(f"| `{name}` | {w['started']} | {w['ended']} | {_f(w['wall_s'], 0)} | {w['speed_valid']} |")
    lines += [""]
    lines += W.render_sections(signals)
    lines += ["## Mechanical family (`family`)", "", f"- {fam['label']}; m = {fam['m']}; members {_list(fam['members'])}; "
                                                    f"{fam['method']}"]
    for m in fam["members"]:
        lines.append(f"- {m}: raw p {_f(fam['raw_p'][m], 4)}, Holm p {_f(fam['holm_p'][m], 4)}")
    lines += [""]
    if "subjective" in signals:
        lines += _subjective_md(signals["subjective"])
    if "divergence" in signals:
        from bench import p426_signals_divergence as D

        lines += D.render_md(signals["divergence"])
    lines += ["## Flags (`flags`; listed, never vetoes)", ""]
    if not signals["flags"]:
        lines.append("- none")
    for f in signals["flags"]:
        lines.append(f"- {f['text']}")
        for it in f.get("items") or []:
            lines.append(_flag_item_text(it))
    lines += _noise_md(signals["noise_floor"])
    cov = signals["coverage"]
    cw = signals["cross_wave"]
    lines += ["", "## Coverage (`coverage`)", ""] + _a7_coverage_lines(cov["A7"]) + W.coverage_md(
        cov["wave1"], signals["identity"]["per_axis"], signals["identity"]["total"])
    lines += [f"- Rule 6 cross-wave code check (`cross_wave`): Wave 1 OFF `{cw['wave1_off']}` vs Wave 2 OFF "
              f"`{cw['wave2_off']}`; files {_list(cw['files'])}; flag {cw['flag']}; entry_equal {cw['entry_equal']}; "
              f"globals_equal {cw['globals_equal']}; gitlinks_equal {cw['gitlinks_equal']}; closure files "
              f"{len(cw['closure_files'])}; qualify {cw['qualify']}"]
    lines += ["", "## Pending (`pending`)", ""] + ([f"- {k}: {v}" for k, v in sorted(signals["pending"].items())]
                                                   or ["- none"])
    return "\n".join(lines) + "\n"


# ===================================================================================================== M76 B3: lever kv
# `docs/specs/m76-b3-b5-p426-kv-lever.md` §Signals + errata v1.1 / v1.2: every mechanical verdict is B7's final entry point
# `bench.m76_rule.axis_verdict(axis, look, a, b)` (α from B7's committed plan; A5 through `verdict_a5`), kept with its α, bound,
# verdict, per-session results, interaction flag and `size_warnings` (each warning a BLOCKING flag → the operator);
# `paired_delta` / `paired_session_delta` appear only as descriptive columns. A5's per-task gates (each arm ≥ 0.85, point ≥ −5 pp),
# the N16 within-arm noise floor (A7), the panel (frozen members, Holm), decode per item (P426's T2 estimator: Wave 1
# `p426_signals_wave1._speed`, A7 `_speed`), coverage. Labels "X − N16", "V − X", "V − N16".
KV_VERSION = "m76-b3"
KV_STATUS = "PROVISIONAL — generated from the B8-accepted KV pairs (stage 3 / 4 evidence)"
KV_GATE_ACC = 0.85                  # AGENTS.md effective context: each arm's per-task accuracy
KV_GATE_POINT_PP = -5.0             # the per-task point estimate floor
KV_SESSION = "s1"                   # the single "session" of a single-draw axis (A1 / A5) in B7's item → {session: 0/1} maps
KV_BLOCKING = ("size_warning", "session_interaction", "loss", "undecided", "a5_gate", "panel_holm_reference_better",
               "panel_single_family", "panel_incomplete")


def kv_b7():
    """B7's modules, or a refusal: the KV sheet never computes a verdict of its own."""
    try:
        from bench import m76_rule
    except ImportError:
        m76_rule = None
    if m76_rule is None or not callable(getattr(m76_rule, "axis_verdict", None)):
        raise RefusalError("bench.m76_rule.axis_verdict (M76 B7) is not available: the KV sheet's verdicts are B7's")
    from bench import stats

    return m76_rule, stats


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, str):
        return str(x)
    return x


def kv_axis_verdict(axis, look, a, b):
    """`bench.m76_rule.axis_verdict(axis, look, a, b)` (a = treatment, b = reference; item → {session: 0/1}) as a plain record;
    a B7 refusal (mismatched items / sessions, a missing plan) refuses the sheet."""
    m76_rule, _ = kv_b7()
    try:
        res = m76_rule.axis_verdict(axis, look, a, b)
    except ValueError as exc:
        raise RefusalError(f"bench.m76_rule.axis_verdict({axis!r}, look {look}): {exc}") from None
    return _jsonable(dict(res))


def kv_plan(axis):
    m76_rule, _ = kv_b7()
    try:
        return m76_rule.axis_plan(axis)
    except ValueError as exc:
        raise RefusalError(f"bench.m76_rule.axis_plan({axis!r}): {exc}") from None


def _single(m):
    return {i: {KV_SESSION: int(v)} for i, v in m.items()}


def kv_descriptive(test, ref, alpha):
    """`paired_delta` (test − reference) at the look's two-sided 1 − 2α — a DESCRIPTIVE column, never the verdict."""
    _, stats = kv_b7()
    ids = sorted(test, key=str)
    res = stats.paired_delta({i: [test[i]] for i in ids}, {i: [ref[i]] for i in ids}, iters=ITERS, seed=SEED,
                             interval_alpha=2 * alpha, exact_alpha=alpha)
    return dict(statistic="paired_delta (descriptive)", delta=res["delta"], lo=res["lo"], hi=res["hi"], n=len(ids))


def kv_a1(test, ref, order):
    """A1 at every look of B7's plan (`axis_plan("A1")`): look k reads the first `size` items of the nested Math500 order (look 1
    = tier 1 = P426's 100); a look whose items were not all B8-accepted is pending. The decision: look 1's verdict when PASS or
    LOSS, else look 2's (UNDECIDED at look 1 → tier 2)."""
    looks = []
    for lk in kv_plan("A1")["looks"]:
        keys = list(order[:lk["size"]])
        if len(keys) != lk["size"] or not all(k in test and k in ref for k in keys):
            looks.append(dict(look=lk["look"], size=lk["size"], alpha=lk["alpha"], status="pending (its items are not all B8-accepted)"))
            continue
        t, r = {k: test[k] for k in keys}, {k: ref[k] for k in keys}
        v = kv_axis_verdict("A1", lk["look"], _single(t), _single(r))
        v["descriptive"] = kv_descriptive(t, r, lk["alpha"])
        looks.append(v)
    decided = [lk for lk in looks if lk.get("verdict") in ("PASS", "LOSS")]
    done = [lk for lk in looks if "verdict" in lk]
    final = decided[0] if decided else (done[-1] if done else None)
    return dict(looks=looks, final_look=final.get("look") if final else None)


def a5_strict(row, budget=None):
    """A5 strict scoring at the row's OWN resolved budget (erratum v1.2; `resolved_max_tokens` / `resolved_thinking_budget` as B8
    derives them from the row's prompt tokens and its leg's sampling): converged = finish_reason stop, completion below both;
    retrieval PASS only if all five codes are recovered AND converged; chain-4 exact (score 1.0) AND converged. `budget` is
    ignored (kept for callers of v1.1)."""
    from bench import convergence

    if not isinstance(row, dict):
        return 0
    cap, rtb, ct = row.get("resolved_max_tokens"), row.get("resolved_thinking_budget"), row.get("completion_tokens")
    if not (isinstance(cap, int) and isinstance(ct, int)) or isinstance(ct, bool):
        return 0
    conv = ct < cap and convergence.is_converged(dict(row, resolved_thinking_budget=rtb)) is True
    if row.get("task") == "retrieval":
        hits = row.get("hits")
        return int(conv and isinstance(hits, list) and len(hits) == 5 and all(h is True for h in hits))
    return int(conv and row.get("score") == 1.0)


def _a5_gates(ids, ref_rows, s_ref, s_test):
    """A5's per-task gates (each arm ≥ 0.85, point ≥ −5 pp, pooled over rungs; blocking) and the rung × task table
    (descriptive) over `ids`."""
    gates, cells = {}, {}
    for task in ("retrieval", "reasoning"):
        t = [i for i in ids if ref_rows[i].get("task") == task]
        acc = {"ref": sum(s_ref[i] for i in t) / len(t) if t else None, "test": sum(s_test[i] for i in t) / len(t) if t else None}
        point = 100.0 * (acc["test"] - acc["ref"]) if t else None
        gates[task] = {"n": len(t), "acc": acc, "point_pp": point,
                       "pass": bool(t) and all(v >= KV_GATE_ACC for v in acc.values()) and point >= KV_GATE_POINT_PP}
        for rung in sorted({ref_rows[i].get("rung") for i in t}, key=str):
            r = [i for i in t if ref_rows[i].get("rung") == rung]
            a_ref, a_test = sum(s_ref[i] for i in r) / len(r), sum(s_test[i] for i in r) / len(r)
            cells[f"{task}|{rung}"] = dict(n=len(r), acc_ref=a_ref, acc_test=a_test, delta_pp=100.0 * (a_test - a_ref))
    return gates, cells


def kv_a5(ref_rows, test_rows, order=None, tiers=None):
    """A5 at the looks of B7's plan (`axis_plan("A5")`, v1.4; like A1): look k reads the first `size` items of A5's nested order
    (`order`, tier 1 then tier 2; default the sorted common ids) through `axis_verdict("A5", k, …)` (→ `verdict_a5` at the
    look's α). Look 2 is taken only when look 1 is UNDECIDED (a look-1 PASS or LOSS stops); a look whose items are not all
    B8-accepted is pending. The deciding look: look 1 when PASS / LOSS, else look 2 when taken, else look 1. The per-task
    gates and the rung × task table are at the deciding look. `tiers` = the cumulative tier sizes of m76/ids.json: look k
    reads tier k (B7 then warns when it is not the plan's size); a look without its tier is pending; tiers that are not the
    plan's look sizes are recorded as `tier_mismatch` (a blocking flag). `verdict` / `n` / `gates` / `per_cell` are the
    deciding look's."""
    common = set(ref_rows) & set(test_rows)
    order = sorted(common) if order is None else list(order)
    plan_looks = kv_plan("A5")["looks"]
    sizes = [lk["size"] for lk in plan_looks]
    mismatch = (f"m76/ids.json's A5 tiers {list(tiers)} are not B7's plan look sizes {sizes}"
                if tiers is not None and list(tiers) != sizes else None)
    s_ref = {i: a5_strict(ref_rows[i]) for i in sorted(common)}
    s_test = {i: a5_strict(test_rows[i]) for i in sorted(common)}
    looks, prior = [], None
    for lk in plan_looks:
        head = dict(look=lk["look"], size=lk["size"], alpha=lk["alpha"])
        if prior is not None and prior.get("verdict") != "UNDECIDED":
            looks.append(dict(head, status=f"not taken: look {prior.get('look')} decided "
                                           f"({prior.get('verdict', prior.get('status'))}; a look-1 PASS / LOSS stops)"))
            continue
        k = lk["look"] - 1
        if tiers is not None and k >= len(tiers):
            looks.append(dict(head, status=f"pending (m76/ids.json has no A5 tier {lk['look']})"))
            prior = looks[-1]
            continue
        size = tiers[k] if tiers is not None else lk["size"]
        keys = list(order[:size])
        if not keys or len(keys) != size or not all(x in common for x in keys):
            looks.append(dict(head, status="pending (its items are not all B8-accepted)"))
            prior = looks[-1]
            continue
        v = kv_axis_verdict("A5", lk["look"], _single({k: s_test[k] for k in keys}), _single({k: s_ref[k] for k in keys}))
        looks.append(v)
        prior = v
    done = [lk for lk in looks if "verdict" in lk]
    decided = [lk for lk in done if lk["verdict"] in ("PASS", "LOSS")]
    final = decided[0] if decided else (done[-1] if done else None)
    extra = dict(tier_mismatch=mismatch) if mismatch else {}
    if final is None:
        return dict(looks=looks, final_look=None, status="no look computable (no B8-accepted A5 look)", **extra)
    keys = list(order[:final["n_items"]]) if final.get("n_items") else []
    gates, cells = _a5_gates(keys, ref_rows, s_ref, s_test)
    return dict(looks=looks, final_look=final["look"], n=len(keys), verdict=final, gates=gates, per_cell=cells,
                strict=dict(ref=s_ref, test=s_test), **extra)


def kv_a7(test, ref, ref_arm, look=None):
    """A7 (tg1): B7's `axis_verdict("A7", look, test, ref)` (default: the plan's final look) over item → {session: 0/1} maps of
    the planned sessions — its α*, loss bound, verdict, per-session results (descriptive), interaction flag (blocking) and size
    warnings; `paired_session_delta` beside it (descriptive); the reference arm's within-arm noise floor when it is N16."""
    _, stats = kv_b7()
    plan = kv_plan("A7")
    lk = plan["looks"][-1] if look is None else plan["looks"][look - 1]
    v = kv_axis_verdict("A7", lk["look"], test, ref)
    try:
        d = stats.paired_session_delta(test, ref, iters=ITERS, seed=SEED, interval_alpha=2 * lk["alpha"], exact_alpha=lk["alpha"])
        v["descriptive"] = dict(statistic="paired_session_delta (descriptive)", delta=d["delta"], lo=d["lo"], hi=d["hi"])
    except ValueError as exc:
        raise RefusalError(f"bench.stats.paired_session_delta: {exc}") from None
    sessions = sorted({s for i in ref for s in ref[i]})
    if ref_arm == "n16":
        within = {}
        for x, s in enumerate(sessions):
            for t in sessions[x + 1:]:
                both = [i for i in ref if s in ref[i] and t in ref[i]]
                within[f"{s}-{t}"] = dict(n=len(both), discordant=sum(1 for i in both if ref[i][s] != ref[i][t]))
        v["noise_floor"] = dict(n16_within=within,
                                test_vs_ref=dict(n=sum(len(test[i]) for i in test),
                                                 discordant=sum(1 for i in test for s in test[i] if test[i][s] != ref[i][s])),
                                note="diagnostic only (S22-P9)")
    return v


def kv_panel_family(members):
    """The subjective family: members with >= 5 judged items are tested (permutation p on score − 0.5, identical items 0),
    Holm-adjusted across the tested members; the others are reported, not tested."""
    from bench import stats
    from bench.p426_panel import kv_members

    out = {}
    family = [m for m in kv_members() if m in members]
    for m in family:
        rec = dict(members[m])
        rec["tested"] = rec.get("judged", 0) >= SUBJ_MIN_JUDGED
        rec["permutation_p"] = permutation_p(rec.get("vector") or []) if rec["tested"] else None
        rec["holm_p"] = None
        out[m] = rec
    tested = [m for m in out if out[m]["tested"]]
    for m, hp in zip(tested, stats.holm([out[m]["permutation_p"] for m in tested]) if tested else []):
        out[m]["holm_p"] = hp
    return dict(family=family, tested=tested, m=len(tested), members=out)


def kv_panel_flags(panel):
    flags = []
    for m in panel.get("tested") or []:
        rec = panel["members"][m]
        mean = rec.get("mean")
        if rec["holm_p"] is not None and rec["holm_p"] < FLAG_HOLM_P and mean is not None and mean < 0.5:
            flags.append(dict(flag="panel_holm_reference_better", member=m, value=rec["holm_p"], items=[], blocking=True,
                              text=f"{m} subjective Holm-adjusted p {rec['holm_p']:.4f} < {FLAG_HOLM_P} favouring the reference"))
    for m, rec in (panel.get("members") or {}).items():
        if rec.get("single_family"):
            flags.append(dict(flag="panel_single_family", member=m, value=rec["single_family"].get("label"), items=[],
                              blocking=True, text=f"{m}: single-family judge set (operator label: {rec['single_family']['label']})"))
    return flags


def kv_sheet_skeleton(pair):
    from bench.p426_plan import pair_label

    ref, test = pair
    return dict(header=dict(generator=GENERATOR, generator_version=KV_VERSION, status=KV_STATUS, lever="kv", pair=[ref, test],
                            label=pair_label(ref, test)),
                axes={}, flags=[], coverage={}, inputs={})


def _kv_check_b8_inputs(rows_root, b8):
    inputs = b8.get("inputs")
    if not isinstance(inputs, dict) or not inputs:
        raise RefusalError("B8.json has no inputs map")
    confined = V.Reader(rows_root, confine=True)
    for rel in sorted(inputs):
        if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
            raise RefusalError(f"B8.json input {rel!r} is not a rows_root-relative path")
        confined.check_confined(Path(rows_root) / rel, "B8.json input")
        try:
            got = hashlib.sha256((Path(rows_root) / rel).read_bytes()).hexdigest()
        except OSError:
            raise RefusalError(f"B8 input {rel} is missing") from None
        if got != inputs[rel]:
            raise RefusalError(f"B8 input {rel} changed: sha256 {got} != B8 {inputs[rel]}")


def _kv_decode_wave1(kind, recs, leg, ref, test):
    """P426's T2 estimator for a Wave 1 kind (`p426_signals_wave1._speed`: per-key decode_tps ratio treatment / reference,
    geomean + item-bootstrap CI per block and both, the order-balance rule on speed-valid blocks, acceptance per arm) over the
    B8-accepted blocks; `off` = reference, `on` = treatment in its output."""
    from bench import p426_signals_wave1 as W

    blocks = [label for (k, label), r in sorted(recs.items()) if k == kind and r.get("accepted")]
    if not blocks:
        return None
    legs, status, keys = {}, {}, {}
    for label in blocks:
        legs[(kind, label, "off")], legs[(kind, label, "on")] = leg(kind, ref, label), leg(kind, test, label)
        status[label] = dict(status="accepted", speed_valid=bool(recs[(kind, label)].get("speed_valid")))
        keys[label] = [k["key"] for k in recs[(kind, label)]["keys"]]
    out = W._speed(kind, keys, legs, status)
    out["arms"] = dict(off=ref, on=test)
    out["estimator"] = "P426 T2 (single-request items: the row's decode_tps; per-key ratio, geomean)"
    return out


KV_PANEL_PARTIAL = "PARTIAL — operator-requested ingestion of an incomplete panel (--partial)"


def kv_panel_section(panel, b8, ref, test, b8_sha256, partial=False):
    """The `panel` record (erratum v1.3): the frozen members (`kv_panel_members`) checked for completeness against B8
    (`kv_expected_members`: every expected member, every frozen judge x order slot admitted). An incomplete panel is not
    ingested — `status` incomplete + its completeness record (→ the blocking `panel_incomplete` flag) — unless `partial`, which
    ingests it under the PARTIAL label (the flag stays)."""
    from bench import p426_panel as P

    members = P.kv_panel_members(panel, ref, test, b8_sha256)
    comp = P.kv_panel_completeness(members, P.kv_expected_members(b8))
    if comp["complete"]:
        return dict(kv_panel_family(members), status="complete", completeness=comp)
    if partial:
        return dict(kv_panel_family(members), status=KV_PANEL_PARTIAL, mode="partial", completeness=comp)
    return dict(status="incomplete (not ingested; --partial ingests it, labelled)", completeness=comp)


def compute_kv(rows_root, b8, b8_sha256=None, panel=None, partial=False):
    """The KV signals record (`benchmark/results/m76/SIGNALS.json`) from a lever-kv B8 record; every input re-verified.
    `partial` (erratum v1.3): ingest an incomplete panel, labelled (its `panel_incomplete` flag stays blocking)."""
    from bench import p426_signals_wave1 as W
    from bench.p426_plan import check_kv_pair

    kv_b7()
    if not isinstance(b8, dict) or b8.get("lever") != "kv" or not isinstance(b8.get("axes"), dict):
        raise RefusalError("B8.json is not a lever-kv verifier record")
    ref, test = check_kv_pair(*b8.get("pair") or ())
    V.kv_check_roots(rows_root)
    _kv_check_b8_inputs(rows_root, b8)
    b8_sha256 = b8_sha256 or _sha_doc(b8)
    sig = kv_sheet_skeleton((ref, test))
    reader = V.Reader(rows_root, confine=True)
    ids = V.load_kv_ids(reader)
    w1 = b8["axes"].get("wave1") or {}
    recs = {(p["kind"], p["block"]): p for p in w1.get("pairs") or []}
    legs = {}

    def leg(kind, arm, label):
        if (kind, arm, label) not in legs:
            legs[(kind, arm, label)] = V.load_kv_leg(reader, kind, arm, label, ids)
        return legs[(kind, arm, label)]

    def accepted(kind, label):
        rec = recs.get((kind, label))
        return rec if rec and rec.get("accepted") else None

    dropped = dict(w1.get("dropped") or {})
    coverage = dict(accepted=sorted(f"{k}/{b}" for (k, b), r in recs.items() if r.get("accepted")),
                    rejected={f"{k}/{b}": r["reasons"] for (k, b), r in sorted(recs.items()) if not r.get("accepted")},
                    not_run=list(w1.get("not_run") or []), dropped=dropped,
                    incomplete=_kv_incomplete(_kv_build_of(w1), recs))
    decode = {}
    for kind in ("math500", "cjudge", "vision", "reasoning", "longctx"):
        d = _kv_decode_wave1(kind, recs, leg, ref, test)
        if d is not None:
            decode[kind] = d
    # A1: the strict per item over the accepted blocks (a rejected block's items are not accepted → its look is pending)
    s_ref, s_test = {}, {}
    for label in ("b1", "b2", "t2-b1", "t2-b2"):
        rec = accepted("math500", label)
        if not rec:
            continue
        planned = ids["math500"][label]
        for arm, dst in ((ref, s_ref), (test, s_test)):
            strict = W._a1_arm(leg("math500", arm, label), planned)[2]
            dst.update({k["key"][1]: strict[k["key"][1]] for k in rec["keys"]})
    sig["axes"]["A1"] = kv_a1(s_test, s_ref, ids["math500_order"])
    # A5 (v1.4: two looks — tier 1, then tier 1 + tier 2 when look 1 is UNDECIDED)
    a5 = dict(status="incomplete: both A5 tier-1 blocks must be B8-accepted (no verdict on incomplete evidence)")
    if accepted("longctx", "b1") and accepted("longctx", "b2"):
        rows = {ref: {}, test: {}}
        for label in ("b1", "b2", *V.KV_TIER2):
            if label not in ids["longctx"] or not accepted("longctx", label):
                continue
            keys = {k["key"][1] for k in accepted("longctx", label)["keys"]}
            for arm in (ref, test):
                rows[arm].update({r["id"]: r["row"] for r in leg("longctx", arm, label)["rows"] if r["id"] in keys})
        t1 = len(ids["longctx"]["b1"]) + len(ids["longctx"]["b2"])
        t2 = sum(len(ids["longctx"][x]) for x in V.KV_TIER2 if x in ids["longctx"])
        a5 = kv_a5(rows[ref], rows[test], order=ids["longctx_order"], tiers=[t1, t1 + t2] if t2 else [t1])
        a5.pop("strict", None)
    sig["axes"]["A5"] = a5
    # A2 / A3 / A4 (panel / descriptive) and M1 (memory, descriptive)
    for kind, axis in (("cjudge", "A2"), ("vision", "A3"), ("reasoning", "A4")):
        blocks = {}
        for label in ("b1", "b2"):
            rec = recs.get((kind, label))
            if kind in dropped and not rec:
                blocks[label] = dict(status="not_run", ruling=dropped[kind])
            elif not rec:
                blocks[label] = dict(status="missing")
            elif not rec.get("accepted"):
                blocks[label] = dict(status="rejected")
            else:
                blocks[label] = dict(status="accepted", keys=rec["keys_accepted"], identical=rec["identical"]["n"],
                                     strict_draws=({arm: sum(1 for r in leg(kind, arm, label)["rows"]
                                                             if r["row"].get("score") == 1.0 and r["row"].get("budget_hit") is False
                                                             and r["row"].get("finish_reason") == "stop") for arm in (ref, test)}
                                                   if kind == "reasoning" else None))
        sig["axes"][axis] = dict(role="panel only" if axis != "A4" else "descriptive + panel", blocks=blocks)
    m1 = {}
    for label in ("b1", "b2"):
        rec = recs.get(("m1", label))
        if "m1" in dropped and not rec:           # v1.1 F2: a dropped kind is `not_run` with its ruling, never `missing`
            m1[label] = dict(status="not_run", ruling=dropped["m1"])
            continue
        m1[label] = dict(status="missing" if not rec else "accepted" if rec.get("accepted") else "rejected")
        if rec and rec.get("accepted"):
            m1[label]["peak"] = {arm: (leg("m1", arm, label)["result"].get("peak") or
                                       leg("m1", arm, label)["result"].get("peak_gb")) for arm in (ref, test)}
    sig["axes"]["M1"] = dict(role="memory (descriptive)", blocks=m1)
    # A7
    if "A7" in b8["axes"]:
        sig["axes"]["A7"], decode["A7"] = _kv_a7_section(rows_root, b8["axes"]["A7"], ref, test)
    else:
        sig["axes"]["A7"] = dict(status="pending (no Wave 2 record)")
    if panel is not None:
        sig["panel"] = kv_panel_section(panel, b8, ref, test, b8_sha256, partial=partial)
    else:
        sig["panel"] = dict(status="pending (panel not run)")
    sig["decode"], sig["coverage"] = decode, coverage
    sig["flags"] = kv_flags(sig)
    for rel, digest in reader.inputs.items():
        if b8["inputs"].get(rel) != digest:
            raise RefusalError(f"input {rel} is not covered by B8.json")
    sig["inputs"] = dict(sorted(b8["inputs"].items()))
    sig["header"].update(b8_sha256=b8_sha256, inputs_sha256=_sha_doc(sig["inputs"]), n_inputs=len(sig["inputs"]),
                         rng=dict(seed=SEED, iters=ITERS))
    return sig


KV_FROZEN_REL_RE = re.compile(r"^m76/wave1/run/frozen\.([^./]+)\.json$")


def _kv_build_of(w1):
    """The build B8 verified: the recorded frozen record's path (`m76/wave1/run/frozen.<build>.json`), else a refusal."""
    from bench.p426_plan import check_kv_build

    m = KV_FROZEN_REL_RE.match(str((w1.get("frozen") or {}).get("path") or ""))
    try:
        return check_kv_build(m.group(1) if m else None)
    except ValueError as exc:
        raise RefusalError(f"B8 wave1 names no KV build (frozen.path {(w1.get('frozen') or {}).get('path')!r}): {exc}") from None


def _kv_incomplete(build, recs):
    """v1.1 F2: {"<kind>/<label>": text} of every planned pair (`kv_w1_kinds(build)` × b1, b2) rejected by or absent from B8."""
    from bench.p426_plan import kv_w1_kinds

    out = {}
    for kind in kv_w1_kinds(build):
        for label in ("b1", "b2"):
            rec = recs.get((kind, label))
            if not rec:
                out[f"{kind}/{label}"] = "absent from the B8 record (no pair verified)"
            elif not rec.get("accepted"):
                out[f"{kind}/{label}"] = "rejected: " + "; ".join(str(r) for r in (rec.get("reasons") or [])[:3])
    return out


def _final_of(axis, rec):
    if axis == "A1":
        looks = [lk for lk in rec.get("looks") or [] if "verdict" in lk]
        return next((lk for lk in looks if lk["look"] == rec.get("final_look")), None)
    if axis == "A5":  # v1.4: the deciding look's verdict (`kv_a5`)
        return rec.get("verdict") if isinstance(rec.get("verdict"), dict) and "verdict" in rec["verdict"] else None
    return rec if "verdict" in rec else None


def kv_flags(sig):
    """Every flag of the sheet (all blocking: listed, the operator decides): LOSS / UNDECIDED at an axis's deciding look, each
    B7 size warning, the A7 session × arm interaction, an A5 per-task gate not met, the panel's Holm / single-family flags."""
    flags = []
    label = sig["header"]["label"]
    for member, text in sorted(((sig.get("coverage") or {}).get("incomplete") or {}).items()):
        flags.append(dict(flag="wave1_incomplete", member=member, value=None, items=[], blocking=True,
                          text=f"Wave 1 {member}: planned pair {text}"))
    for axis in ("A1", "A5", "A7"):
        rec = sig["axes"].get(axis) or {}
        looks = ([lk for lk in rec.get("looks") or [] if "verdict" in lk] if axis in ("A1", "A5") and "looks" in rec
                 else [_final_of(axis, rec)])
        for lk in [x for x in looks if x]:
            for w in lk.get("size_warnings") or []:
                flags.append(dict(flag="size_warning", member=axis, value=w, items=[], blocking=True,
                                  text=f"{axis} look {lk.get('look')}: B7 size warning — {w}"))
        final = _final_of(axis, rec)
        if not final:
            continue
        v = final.get("verdict")
        if v == "LOSS":
            flags.append(dict(flag="loss", member=axis, value=final.get("delta"), items=[], blocking=True,
                              text=f"{axis}: LOSS ({label} {100 * final['delta']:+.1f} pp) — {final.get('label')}"))
        elif v == "UNDECIDED":
            flags.append(dict(flag="undecided", member=axis, value=final.get("loss_bound"), items=[], blocking=True,
                              text=f"{axis}: {final.get('label')}"))
        if axis == "A7" and final.get("interaction_flag"):
            p = (final.get("interaction") or {}).get("pvalue")
            flags.append(dict(flag="session_interaction", member="A7", value=p, items=[], blocking=True,
                              text=f"A7 session × arm interaction p {p} (blocks a ship recommendation)"))
    if (sig["axes"].get("A5") or {}).get("tier_mismatch"):
        w = sig["axes"]["A5"]["tier_mismatch"]
        flags.append(dict(flag="size_warning", member="A5", value=w, items=[], blocking=True, text=f"A5: {w}"))
    for task, g in (((sig["axes"].get("A5") or {}).get("gates") or {}).items()):
        if not g["pass"]:
            flags.append(dict(flag="a5_gate", member=f"A5-{task}", value=g["point_pp"], items=[], blocking=True,
                              text=f"A5 {task} gate not met (each arm >= {KV_GATE_ACC}, point >= {KV_GATE_POINT_PP:.0f} pp)"))
    if isinstance(sig.get("panel"), dict) and "members" in sig["panel"]:
        flags += kv_panel_flags(sig["panel"])
    comp = (sig.get("panel") or {}).get("completeness") if isinstance(sig.get("panel"), dict) else None
    if isinstance(comp, dict) and not comp.get("complete"):
        flags.append(dict(flag="panel_incomplete", member="panel", value=None, items=list(comp.get("missing_members") or []),
                          blocking=True, text=f"panel incomplete: missing members {comp.get('missing_members')}, incomplete "
                                              f"members {sorted(comp.get('incomplete') or {})}"
                                              + (" (ingested under --partial)" if sig["panel"].get("mode") == "partial" else
                                                 " (not ingested)")))
    return flags


def _kv_a7_section(rows_root, a7, ref, test):
    """(A7 record, decode): every PLANNED session (`p426_plan.kv_a7_sessions`, B7's plan) must be a B8-accepted pair (a pair with
    a rejected key is rejected by B8) — otherwise the axis is refused ("incomplete"), never verdicted; strict per (item,
    session) over the planned slots (a DNF slot is a strict fail); T2 decode per session (`_speed`, descriptive)."""
    from bench.p426_plan import kv_a7_sessions

    try:
        planned = list(kv_a7_sessions())
    except ValueError as exc:
        raise RefusalError(f"A7 plan: {exc}") from None
    reader = V.Reader(Path(rows_root) / V.KV_ROOT)
    pairs = {p["pair"]: p for p in a7.get("pairs") or []}
    if list(a7.get("sessions") or []) != planned:
        return dict(status=f"incomplete: B8 verified sessions {a7.get('sessions')}, the plan needs {planned}"), None
    bad = [s for s in planned if not (pairs.get(s) or {}).get("accepted")]
    if bad:
        return dict(status=f"incomplete: planned session(s) {bad} not B8-accepted (no verdict on incomplete evidence)"), None
    maps, keysets, decode = {ref: {}, test: {}}, [], {}
    for s in planned:
        p = pairs[s]
        keysets.append({k["key"][1] for k in p["keys"]})
        atts = {arm: V._kv_load_attempt(reader, p["attempts"][arm], s, f"A7 {s} {arm}") for arm in (ref, test)}
        for arm in (ref, test):
            for k in p["keys"]:
                maps[arm].setdefault(k["key"][1], {})[s] = _strict(atts[arm]["rows"].get(k["key"][1]))
        sp = _speed(sorted(k["key"][1] for k in p["keys"]), atts[ref], atts[test], inference=bool(p.get("speed_valid")))
        decode[s] = dict(sp, arms=dict(off=ref, on=test), estimator="P426 T2 (Σ(generated − requests) / Σ decode_s per item)")
    if any(ks != keysets[0] for ks in keysets):
        return dict(status="incomplete: the planned sessions hold different item sets"), decode
    common = sorted(keysets[0])
    rec = kv_a7({i: maps[test][i] for i in common}, {i: maps[ref][i] for i in common}, ref_arm=ref)
    return dict(rec, items=len(common), sessions=planned), decode


def _kv_fmt_verdict(v):
    if "verdict" not in v:
        return f"{v.get('status', 'pending')}"
    lo, hi = v.get("lo"), v.get("hi")
    interval = f" [{_pp(lo)}, {_pp(hi)}]" if lo is not None and hi is not None else ""
    desc = v.get("descriptive") or {}
    d = f"; descriptive {desc.get('statistic')}: {_pp(desc.get('delta'))} [{_pp(desc.get('lo'))}, {_pp(desc.get('hi'))}]" if desc else ""
    warn = f"; SIZE WARNINGS {v['size_warnings']}" if v.get("size_warnings") else ""
    return (f"look {v.get('look')}, one-sided α {v.get('alpha'):.4g}: {v.get('n_items')} items × {v.get('n_sessions')} session(s), "
            f"delta {_pp(v.get('delta'))}{interval}, loss bound {_pp(v.get('loss_bound'))} → **{v.get('verdict')}** "
            f"({v.get('label')}){warn}{d}")


def render_kv(sig):
    h = sig["header"]
    lab = h["label"]
    lines = [f"# M76 signals — {lab} — {h['status']}", "",
             f"Generated by `{h['generator']}` ({h['generator_version']}, lever kv); never hand-edited. Every verdict is "
             f"`bench.m76_rule.axis_verdict` (B7; α from its committed plan); `paired_delta` / `paired_session_delta` are "
             f"descriptive columns only.", ""]
    if "b8_sha256" in h:
        lines += [f"- B8.json sha256: `{h['b8_sha256']}`; inputs sha set `{h['inputs_sha256']}` ({h['n_inputs']} files)",
                  f"- RNG (descriptive columns): seed {h['rng']['seed']}, {h['rng']['iters']} resamples", ""]
    ax = sig["axes"]
    a1 = ax.get("A1") or {}
    lines += [f"## A1 Math500 ({lab}; `axes.A1`)", ""]
    for lk in a1.get("looks") or []:
        lines.append("- " + (_kv_fmt_verdict(lk) if "verdict" in lk else f"look {lk.get('look')}: {lk.get('status', 'pending')}"))
    if not a1.get("looks"):
        lines.append("- pending")
    lines.append(f"- deciding look: {a1.get('final_look')}")
    a5 = ax.get("A5") or {}
    lines += ["", f"## A5 long context ({lab}; `axes.A5`)", ""]
    if isinstance(a5.get("verdict"), dict):
        v = a5["verdict"]
        b, c = (v.get("a5") or {}).get("b"), (v.get("a5") or {}).get("c")
        for lk in a5.get("looks") or []:
            if "verdict" not in lk:
                lines.append(f"- look {lk.get('look')} (n {lk.get('size')}): {lk.get('status', 'pending')}")
            else:
                lb, lc_ = (lk.get("a5") or {}).get("b"), (lk.get("a5") or {}).get("c")
                lines.append(f"- look {lk.get('look')}: `axis_verdict` → `verdict_a5`: b (reference only) {lb}, c (treatment "
                             f"only) {lc_}; " + _kv_fmt_verdict(lk))
        lines.append(f"- deciding look {a5.get('final_look')}: n {a5['n']}, b {b}, c {c}; gates and table at this look")
        if a5.get("tier_mismatch"):
            lines.append(f"- TIER MISMATCH (blocking): {a5['tier_mismatch']}")
        for task, g in a5["gates"].items():
            lines.append(f"- gate {task}: n {g['n']}, accuracy reference {_f(g['acc']['ref'])} / treatment {_f(g['acc']['test'])}, "
                         f"point {_f(g['point_pp'], 1)} pp → {'met' if g['pass'] else 'NOT met'}")
        lines += ["", "| task × rung | n | reference | treatment | delta pp |", "|---|---|---|---|---|"]
        lines += [f"| {cell} | {c['n']} | {_f(c['acc_ref'])} | {_f(c['acc_test'])} | {c['delta_pp']:+.1f} |"
                  for cell, c in a5["per_cell"].items()]
    else:
        lines.append(f"- {a5.get('status', 'pending')}")
    a7 = ax.get("A7") or {}
    lines += ["", f"## A7 tg1 ({lab}; `axes.A7`)", ""]
    if "verdict" in a7:
        lines.append(f"- sessions {a7['sessions']}: {_kv_fmt_verdict(a7)}")
        inter = a7.get("interaction") or {}
        lines.append(f"- session × arm interaction: flag {a7.get('interaction_flag')}, p {inter.get('pvalue')}")
        lines.append(f"- per session (descriptive, α {a7.get('per_session_alpha')}): "
                     f"{json.dumps(a7.get('per_session'), sort_keys=True, default=str)}")
        if a7.get("noise_floor"):
            nf = a7["noise_floor"]
            lines.append(f"- noise floor (diagnostic): N16 within-arm {json.dumps(nf['n16_within'], sort_keys=True)}; {lab} "
                         f"discordant {nf['test_vs_ref']['discordant']} / {nf['test_vs_ref']['n']}")
    else:
        lines.append(f"- {a7.get('status', 'pending')}")
    lines += ["", "## A2 / A3 / A4 / M1 (panel / descriptive)", ""]
    for axis in ("A2", "A3", "A4", "M1"):
        lines.append(f"- {axis}: {json.dumps(ax.get(axis), sort_keys=True, default=str)}")
    lines += ["", "## Decode per item (P426 T2 estimator; descriptive; `off` = reference, `on` = treatment)", ""]
    for k, d in sorted((sig.get("decode") or {}).items()):
        if d is None:
            continue
        if k == "A7":
            for s, ds in sorted(d.items()):
                p = ds["primary"]
                lines.append(f"- A7 {s}: treatment / reference {_f(p['geomean_ratio'])} [{_f(p['lo'])}, {_f(p['hi'])}] (n {p['n']}); "
                             f"acceptance {_f(ds['acceptance']['off']['acceptance'])} / {_f(ds['acceptance']['on']['acceptance'])}")
            continue
        both = d["both"]
        lines.append(f"- {k}: treatment / reference {_f(both['geomean_ratio'])} [{_f(both['lo'])}, {_f(both['hi'])}] (n {both['n']}; "
                     f"{both['note']}); acceptance treatment {_f(both['acceptance']['acceptance'])}")
    p = sig.get("panel") or {}
    lines += ["", "## Panel (frozen members, Holm; `panel`)", ""]
    if isinstance(p.get("completeness"), dict):
        c = p["completeness"]
        lines.append(f"- status: {p.get('status')}; expected members {c.get('expected')}, missing {c.get('missing_members')}, "
                     f"incomplete {json.dumps(c.get('incomplete'), sort_keys=True)}")
    if "members" in p:
        for m in p["family"]:
            r = p["members"][m]
            lines.append(f"- {m}: judged {r.get('judged')}, identical {r.get('identical')}, mean {_f(r.get('mean'))}, tested "
                         f"{r['tested']}, p {_f(r['permutation_p'], 4)}, Holm p {_f(r['holm_p'], 4)}")
    else:
        lines.append(f"- {p.get('status', 'pending')}")
    lines += ["", "## Flags (`flags`; every one blocking — listed, the operator decides)", ""]
    lines += [f"- {f['text']}" for f in sig["flags"]] or ["- none"]
    cov = sig.get("coverage") or {}
    lines += ["", "## Coverage (`coverage`)", "", f"- accepted: {_list(cov.get('accepted') or [])}",
              f"- rejected: {_list(sorted(cov.get('rejected') or {}))}", f"- not run: {_list(cov.get('not_run') or [])}"]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m bench.p426_signals")
    sub = ap.add_subparsers(dest="axis", required=True)
    a7 = sub.add_parser("a7")
    a7.add_argument("--results-root", required=True, type=Path)
    a7.add_argument("--b8", required=True, type=Path)
    a7.add_argument("--out-md", required=True, type=Path)
    a7.add_argument("--out-json", required=True, type=Path)
    al = sub.add_parser("all")
    al.add_argument("--results-root", required=True, type=Path)
    al.add_argument("--rows-root", required=True, type=Path)
    al.add_argument("--b8", required=True, type=Path)
    al.add_argument("--out-md", required=True, type=Path)
    al.add_argument("--out-json", required=True, type=Path)
    al.add_argument("--panel", type=Path, default=None,
                    help="the frozen panel directory (FROZEN.json, packets, verdicts); optional (E1): absent → the "
                         "step-2 record; present with no readable FROZEN.json → refusal")
    al.add_argument("--evidence-ref", default=None,
                    help="the `evidence` branch commit holding the A7 events files (step 4): adds the A7 first-divergence "
                         "section (C284) and the FINAL status; requires --panel; absent → the step-3 record unchanged")
    al.add_argument("--repo", type=Path, default=None,
                    help="the git work tree holding --evidence-ref (default: the one containing --results-root)")
    al.add_argument("--lever", default="mtp", choices=("mtp", "kv"),
                    help="M76 B3: kv = the M76 sheet of a lever-kv B8 (--results-root <rows>/m76; verdicts by B7)")
    al.add_argument("--partial", action="store_true",
                    help="lever kv: ingest an incomplete panel, labelled PARTIAL (its panel_incomplete flag stays blocking)")
    args = ap.parse_args(argv)
    try:
        V.check_out_dirs([args.out_md, args.out_json])
        try:
            b8_bytes = args.b8.read_bytes()
            b8 = json.loads(b8_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            raise RefusalError("B8.json is missing or unreadable") from None
        if args.axis == "all" and args.lever == "kv":
            if Path(args.results_root).resolve() != (Path(args.rows_root) / V.KV_ROOT).resolve():
                raise RefusalError("results_root does not resolve to rows_root/m76 (lever kv)")
            if args.evidence_ref is not None:
                raise RefusalError("--evidence-ref is the P426 step-4 sheet's (lever mtp)")
            if args.partial and args.panel is None:
                raise RefusalError("--partial requires --panel")
            signals = compute_kv(args.rows_root, b8, b8_sha256=hashlib.sha256(b8_bytes).hexdigest(), panel=args.panel,
                                 partial=args.partial)
            md = render_kv(signals)
        elif getattr(args, "partial", False):
            raise RefusalError("--partial is the lever-kv sheet's")
        elif args.axis == "all":
            signals = compute_all(args.results_root, args.rows_root, b8,
                                  b8_sha256=hashlib.sha256(b8_bytes).hexdigest(), panel=args.panel,
                                  evidence_ref=args.evidence_ref, repo=args.repo)
            md = render_all(signals)
        else:
            signals = compute_a7(args.results_root, b8, b8_sha256=hashlib.sha256(b8_bytes).hexdigest())
            md = render_md(signals)
        V.write_atomic({args.out_json: json.dumps(signals, sort_keys=True, indent=1) + "\n", args.out_md: md})
    except RefusalError as exc:
        print(f"REFUSED: {V._one_line(exc)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
