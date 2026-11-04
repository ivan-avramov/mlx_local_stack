"""Tolerant readers for the §4.5 subjective section of SIGNALS.json and the panel-run helpers of the signals tests.

The contract fixes WHAT is reported per member (admitted items, raw per-item score, permutation p, length-adjusted headline, judged
n, missing / excluded counts, one-arm-pass left out, provenance) but not the JSON key names. Lookups therefore search the
member's subtree for a list of alias keys; a lookup that finds nothing FAILS the test with the list of keys tried (that failure
is a contract ambiguity to be settled, not a pass).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bench.tests.p613s3 import s3world as S

CLA, CUR = S.CLAUDE_JUDGE["label"], S.CURSOR_JUDGE["label"]
ALL_IDS = S.S1_SEL + S.S2_SEL
SLOT = {(CLA, "AB"): 0, (CLA, "BA"): 1, (CUR, "AB"): 2, (CUR, "BA"): 3}
STATUS = "PROVISIONAL — final review pending (step 4)"
MISSING = object()

ON, OFF, TIE = "on", "off", "tie"
PLAN_S1 = {"python/alpha": [ON] * 4, "python/beta": [ON, ON, ON, TIE], "python/book-store": [ON, OFF, ON, OFF],
           "go/two-fer": [TIE] * 4, "go/eta": [ON, ON, OFF, TIE], "go/zeta": [ON] * 4}
SCORES_S1 = {"python/alpha": 1.0, "python/beta": 0.875, "python/book-store": 0.5, "go/two-fer": 0.5, "go/eta": 0.625,
             "go/zeta": 1.0}
PLAN_S2_OFF = {r: [OFF] * 4 for r in S.S2_SEL}
PLAN_S2_ON = {r: [ON] * 4 for r in S.S2_SEL}


def planned_choices(out, plan, panel):
    """[(manifest row, rid, choice)] following `plan` {id: [outcome x4]} (the choice is in the SHOWN order)."""
    on_tune = panel.tunes("s2")[1]
    res = []
    for r in S.manifest_of(out):
        rid = S.short_id(r["item_id"], ALL_IDS)
        if rid not in plan:
            continue
        outcome = plan[rid][SLOT[(r["judge"], r["order"])]]
        first_key = r["a_key"] if r["order"] == "AB" else r["b_key"]
        first_on = f"@{on_tune}::" in first_key
        choice = "tie" if outcome == TIE else ("A" if (outcome == ON) == first_on else "B")
        res.append((r, rid, choice))
    return res


def packet_of(out, r):
    p = Path(r["path"])
    return p if p.is_absolute() else Path(out) / p


def write_verdicts(out, plan, panel, *, drop=(), unbound=(), bare_override=None, seal=True):
    """Verdicts written by the CODE UNDER TEST (so the provenance and any FROZEN binding are the implementation's): the Claude
    judge's bare verdicts are sealed by `a7-seal`; the Cursor judge's go through `a7-cursor` with a fake `cursor-agent` that answers
    from a plan file. `drop` = {(id, judge, order)} left unjudged (Claude: no bare file; Cursor: the fake agent fails);
    `bare_override` = {(id, judge, order): raw text} written instead of a valid bare verdict; `unbound` = {(id, judge, order)}
    sealed verdicts whose `packet_sha` is then overwritten."""
    out = Path(out)
    bare_override = bare_override or {}
    fake = S.install_fake_cursor(out.parent / "fakebin")
    cursor_plan, fail = {}, []
    for r, rid, choice in planned_choices(out, plan, panel):
        key = (rid, r["judge"], r["order"])
        packet = packet_of(out, r)
        if r["judge"] == CLA:
            if key in drop:
                continue
            text = bare_override.get(key)
            packet.with_name(r["pkt"] + ".verdict.json").write_text(
                text if text is not None else json.dumps({"choice": choice, "rationale": "r"}) + "\n")
        else:
            cursor_plan[r["pkt"]] = choice
            if key in drop:
                fail.append(r["pkt"])
    plan_file = out.parent / "cursor_plan.json"
    plan_file.write_text(json.dumps(cursor_plan))
    if seal:                                       # seal=False: the caller runs `a7-seal` itself (and checks its outcome)
        p1 = S.run_cli("bench.p426_panel", ["a7-seal", "--out", out, "--judge", CLA, "--client-version", "2.3.4"],
                       home=out.parent)
        assert p1.returncode == 0, p1.stderr[-600:]
    p2 = S.run_cli("bench.p426_panel", ["a7-cursor", "--out", out, "--judge", CUR], path_prefix=str(fake), home=out.parent,
                   env_extra={"FAKE_CURSOR_PLAN": str(plan_file), "FAKE_CURSOR_FAIL": ",".join(fail)})
    assert p2.returncode == 0, p2.stderr[-600:]
    for r, rid, choice in planned_choices(out, plan, panel):
        if (rid, r["judge"], r["order"]) in unbound:
            v = packet_of(out, r).with_name(r["pkt"] + ".verdict.json")
            doc = json.loads(v.read_text())
            doc["packet_sha"] = "0" * 64
            v.write_text(json.dumps(doc) + "\n")


def run_all(case, out_dir, panel_dir, *, extra=None, with_panel=True, b8=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md, js = out_dir / "SIGNALS.md", out_dir / "SIGNALS.json"
    args = ["all", "--results-root", case.results_root, "--rows-root", case.rows_root, "--b8", b8 or case.b8_path,
            "--out-md", md, "--out-json", js]
    if with_panel:
        args += ["--panel", panel_dir]
    proc = S.run_cli("bench.p426_signals", args + list(extra or []), env_extra={"MLX_BENCH_RESULTS": str(case.rows_root)},
                     home=case.rows_root)
    return proc, md, js


def load(js):
    return json.loads(Path(js).read_text())


# ------------------------------------------------------------------------------------------------------------ lookups
def subjective(sig):
    keys = [k for k in sig if "subjective" in k.lower() or "panel" in k.lower()]
    assert keys, f"no subjective / panel section in SIGNALS.json; top-level keys: {sorted(sig)}"
    return sig[keys[0]]


def walk(node):
    """Every dict in the subtree, breadth first."""
    queue = [node]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, dict):
            yield cur
            queue.extend(cur.values())
        elif isinstance(cur, list):
            queue.extend(cur)


def member(sig, name):
    for d in walk(subjective(sig)):
        if name in d and isinstance(d[name], dict):
            return d[name]
    raise AssertionError(f"no member {name!r} in the subjective section; keys: {sorted(subjective(sig))}")


def field(node, *aliases, default=MISSING):
    for d in walk(node):
        for a in aliases:
            if a in d:
                return d[a]
    if default is MISSING:
        raise AssertionError(f"none of {aliases} found under {sorted(node) if isinstance(node, dict) else node!r}")
    return default


def count(v):
    if v is None:
        return 0
    if isinstance(v, dict):
        return sum(len(x) for x in v.values() if isinstance(x, list))
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else len(v)


def judged_n(m):
    return count(field(m, "n_judged", "judged_n", "judged", "n_items", "n_admitted", "admitted_n"))


def raw_p(m):
    return field(m, "permutation_p", "raw_p", "p_raw", "p")


def holm_p(m):
    return field(m, "holm_p")


def item_scores(m, ids):
    """{id: score} from the first dict of the member whose keys name the ids (id or `<session>/<id>`)."""
    for d in walk(m):
        hit = {}
        for k, v in d.items():
            for rid in ids:
                if isinstance(k, str) and (k == rid or k.endswith("/" + rid)):
                    hit[rid] = v["score"] if isinstance(v, dict) and "score" in v else (
                        v["raw"] if isinstance(v, dict) and "raw" in v else v)
        if len(hit) >= len(ids) and all(isinstance(v, (int, float)) for v in hit.values()):
            return hit
    raise AssertionError(f"no per-item score map for {ids[:2]}... under the member; keys: {sorted(m)}")


def one_arm_left_out(m):
    for d in walk(m):
        for k, v in d.items():
            if isinstance(k, str) and re.search(r"one[-_ ]?arm", k, re.I):
                return count(v)
    raise AssertionError(f"no one-arm-pass count under the member; keys: {sorted(m)}")


def family(sig):
    sub = subjective(sig)
    for d in walk(sub):
        if "members" in d and "m" in d:
            return d
    raise AssertionError(f"no family record (members + m) in the subjective section; keys: {sorted(sub)}")


def subjective_flags(sig):
    return [f for f in sig["flags"] if "subjective" in f["text"].lower()]
