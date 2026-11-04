"""P613 B6 — the P426 signals sheet (step 1: axis A7 only, PROVISIONAL).

Computes the A7 signals of spec `docs/specs/p613-b8-b6-signals.md` v2 §4 (per session s1 / s2, never pooled) from B8-accepted
pairs only, per the step-1 contract `docs/specs/p613-step1-contract.md`. Deterministic: the same inputs give byte-identical
`SIGNALS.md` / `SIGNALS.json` (no wall-clock time, no absolute path). Refuses (`RefusalError`) when any B8 input changed.

CLI: `python -m bench.p426_signals a7 --results-root <dir> --b8 <B8.json> --out-md <SIGNALS.md> --out-json <SIGNALS.json>`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
    if isinstance(signals.get("header"), dict) and signals["header"].get("generator_version") == ALL_VERSION:
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


def compute_all(results_root, rows_root, b8, b8_sha256=None):
    """One signals record: A7 (step 1) + Wave 1 (A1, M1, A2, A3, A4) + the complete mechanical family + flags."""
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
    lines += ["", "## Flags (`flags`; listed, never vetoes)", ""]
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
    lines += ["", "## Pending (`pending`)", ""] + [f"- {k}: {v}" for k, v in sorted(signals["pending"].items())]
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
    args = ap.parse_args(argv)
    try:
        V.check_out_dirs([args.out_md, args.out_json])
        try:
            b8_bytes = args.b8.read_bytes()
            b8 = json.loads(b8_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            raise RefusalError("B8.json is missing or unreadable") from None
        if args.axis == "all":
            signals = compute_all(args.results_root, args.rows_root, b8,
                                  b8_sha256=hashlib.sha256(b8_bytes).hexdigest())
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
