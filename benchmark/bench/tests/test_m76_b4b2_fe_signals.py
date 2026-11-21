"""M76 B4b-2 (spec v1.5) — the A8 section and flags of the signals sheet (`bench.p426_signals.compute_kv(..., b8_a8=, b8_a8_sha256=)`),
driven end to end: a synthetic Wave 1 world gives B8.json, a synthetic tg2 tree gives B8-A8.json (`verify_a8_kv`), the sheet reads both.

Class of each test (comment above it): (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) new behaviour.
Interface assumptions (also in the report): the A8 section is `sig["axes"]["A8"]` (`axis_verdict("A8", ...)`'s fields, `hold` among them),
its decode `sig["decode"]["A8"][session]["primary"]["n"]` (as A7's), the sheet `render_kv(sig)` carries "## A8 tg2" after the A7 heading;
the sensitivity / reload-control / latency items are located by their labels in the A8 record and the sheet text, not by key names.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

import pytest

from bench import m76_rule
from bench import p426_signals as S
from bench import p426_verify as V
from bench.tests import test_m76_b4b2_fe_support as W
from bench.tests.p613.a7world import sha_bytes

PAIR = ("n16", "x")
CONF = ("s1", "s2")


# ------------------------------------------------------------------------------------------------------------------ the world
class Scenario:
    """B8.json (synthetic Wave 1: cjudge + longctx), B8-A8.json over a tg2 tree with the given controls, and the sheet."""

    def __init__(self, tmp_path, monkeypatch, sessions=("pilot", "s1", "s2", "reload"), rechecks=True, with_a8=True, **kw):
        from bench.tests.test_m76_b3_impl_verify import World as B3

        # the candidate re-hashes B8-A8's `repo_inputs` (the pinned draw) at `rows_root.parents[1]/benchmark/m65/tg2_draw.json`:
        # the world is laid out as <tmp>/benchmark/{results,repo,m65}
        bench_dir = tmp_path / "benchmark"
        (bench_dir / "m65").mkdir(parents=True)
        (bench_dir / "m65" / "tg2_draw.json").write_bytes((W.REPO / "benchmark" / "m65" / "tg2_draw.json").read_bytes())
        self.b3 = B3(bench_dir, monkeypatch)
        for kind in ("cjudge", "longctx"):
            for label in ("b1", "b2"):
                for arm in PAIR:
                    self.b3.leg(kind, arm, label)
        self.rows = self.b3.rows
        self.b8 = V.verify_all_kv(self.rows, self.b3.repo, PAIR, kinds=("cjudge", "longctx"))
        self.b8_bytes = V.dumps(self.b8).encode()
        self.b8_sha = hashlib.sha256(self.b8_bytes).hexdigest()
        self.w = W.World(tmp_path / "a8", corpus="tg2", sessions=sessions, root=self.rows / "m76", **kw)
        (self.rows / "m76" / "B8.json").write_bytes(self.b8_bytes)            # the B8.json B8-A8 accompanies
        if rechecks and set(CONF) <= set(sessions):
            self.w.write_rechecks(ack=True)
        self.doc = self.doc_sha = None
        if with_a8:
            self.rebuild()

    def rebuild(self):
        """B8-A8 anew (`verify_a8_kv(results_root, base_b8_sha256)`), as the CLI writes it."""
        self.doc = V.verify_a8_kv(self.rows / "m76", self.b8_sha)
        self.doc_sha = hashlib.sha256(V.dumps(self.doc).encode()).hexdigest()

    def sheet(self, a8=True, **kw):
        extra = dict(b8_a8=self.doc, b8_a8_sha256=self.doc_sha) if a8 else {}
        sig = S.compute_kv(self.rows, self.b8, b8_sha256=self.b8_sha, **extra, **kw)
        return sig, S.render_kv(sig)


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    def build(**kw):
        return Scenario(tmp_path, monkeypatch, **kw)
    return build


def maps(w, drop=()):
    """{arm: {item: {session: 0/1}}} the strict outcomes the world encodes (a DNF slot is 0), over the confirmatory sessions."""
    out = {}
    for arm in PAIR:
        out[arm] = {}
        for s in CONF:
            for rid in w.ids[s]:
                if rid in drop:
                    continue
                dnf = rid in (w.dnf.get((arm, s)) or ()) or rid in (w.hdnf.get((arm, s)) or {})
                o = w._outcome(arm, s, rid)
                out[arm].setdefault(rid, {})[s] = int(bool(o["passed"]) and bool(o["converged"]) and not dnf)
    return out


def expected(w, drop=()):
    m = maps(w, drop)
    return m76_rule.axis_verdict("A8", 1, m["x"], m["n16"], languages={i: W.lang_of(i) for i in m["x"]})


def ids_of(session, lang=None):
    ids = W.schedule_ids(W.tg2_schedule(session))
    return [i for i in ids if lang is None or W.lang_of(i) == lang]


def fails(arm, lang, n, sessions=CONF):
    """`n` failing items of `lang`, in every confirmatory session of `arm`."""
    victims = ids_of("s1", lang)[:n]
    return {(arm, s): {i: False for i in victims} for s in sessions}


def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    else:
        yield o


def find_dicts(o, pred):
    out = []
    if isinstance(o, dict):
        if pred(o):
            out.append(o)
        for v in o.values():
            out += find_dicts(v, pred)
    elif isinstance(o, list):
        for v in o:
            out += find_dicts(v, pred)
    return out


# ------------------------------------------------------------------------------------------------------------------ the verdict
# (c) the A8 verdict is `m76_rule.axis_verdict("A8", look 1, ...)` over the strict map: α* 0.001, 80 items, 2 sessions, unit items
def test_a8_verdict_is_axis_verdict_over_the_strict_outcomes(scenario):
    sc = scenario(outcomes={("x", "s1"): {i: False for i in ids_of("s1", "java")[:2]}, ("n16", "s2"): {i: False for i in ids_of("s1", "cpp")[:1]}})
    sig, md = sc.sheet()
    rec, want = sig["axes"]["A8"], expected(sc.w)
    assert rec["alpha"] == want["alpha"] == 0.001 and rec["n_items"] == 80 and rec["n_sessions"] == 2 and not rec["size_warnings"]
    for k in ("verdict", "delta", "lo", "hi", "loss_bound", "per_session", "interaction_flag", "report_sha256"):
        assert rec[k] == W_json(want[k]), k
    assert rec["hold"]["hold"] is want["hold"]["hold"] and rec["hold"]["languages"] == want["hold"]["languages"]


def W_json(x):
    return json.loads(json.dumps(x, default=str))


# (c) the sheet has the heading, after A7's, with the verdict text
def test_sheet_renders_the_a8_heading_after_a7(scenario):
    sig, md = scenario().sheet()
    assert "## A8 tg2" in md and md.index("## A7 tg1") < md.index("## A8 tg2")
    assert "**" + sig["axes"]["A8"]["verdict"] + "**" in md


# (c) Outcome = acc_strict@budget: a non-converged pass is a 0; so are a DNF and a harness DNF
def test_outcome_is_passed_and_converged_and_dnf_is_zero(scenario):
    ids = ids_of("s1")
    sc = scenario(outcomes={("x", "s1"): {ids[0]: dict(passed=True, converged=False), ids[1]: False}},
                  dnf={("x", "s1"): [ids[2], ids[3]]}, hdnf={("n16", "s2"): {ids[4]: "harness_fault_dnf", ids[5]: "grade_fault"}})
    sig, _ = scenario_sheet(sc)
    rec, want = sig["axes"]["A8"], expected(sc.w)
    m = maps(sc.w)
    assert [m["x"][i]["s1"] for i in ids[:4]] == [0, 0, 0, 0] and [m["n16"][i]["s2"] for i in ids[4:6]] == [0, 0]
    for k in ("verdict", "delta", "lo", "hi", "loss_bound", "n_items"):
        assert rec[k] == W_json(want[k]), k


def scenario_sheet(sc, **kw):
    return sc.sheet(**kw)


# (c) HOLD: a language at −25 pp → `hold`, a blocking flag; −20 pp exactly does not fire; a loss in another language never does
def test_a_language_at_minus_25_pp_holds_and_blocks(scenario):
    sc = scenario(outcomes=fails("x", "rust", 5))                       # 5 of 20 rust items fail in X in both sessions: −25 pp
    sig, md = sc.sheet()
    rec = sig["axes"]["A8"]
    assert rec["hold"]["hold"] is True and rec["hold"]["languages"] == ["rust"] and rec["hold"]["per_language"]["rust"] == pytest.approx(-0.25)
    hold = [f for f in sig["flags"] if f["flag"] == "hold"]
    assert len(hold) == 1 and hold[0]["blocking"] is True and "rust" in json.dumps(hold[0])
    assert "hold" in md.lower()


def test_minus_20_pp_exactly_does_not_hold(scenario):
    sig, _ = scenario(outcomes=fails("x", "java", 4)).sheet()           # 4 of 20: −20 pp exactly
    assert sig["axes"]["A8"]["hold"]["hold"] is False
    assert not [f for f in sig["flags"] if f["flag"] == "hold"]


# (c) LOSS / UNDECIDED and the session interaction ride the same flag machinery as A7's, for A8
def test_a_clear_loss_is_flagged_for_a8(scenario):
    sig, _ = scenario(outcomes={("x", s): {i: False for i in ids_of("s1")[:30]} for s in CONF}).sheet()
    assert sig["axes"]["A8"]["verdict"] == "LOSS"
    assert [f for f in sig["flags"] if f["flag"] == "loss" and f["member"] == "A8" and f["blocking"]]


def test_an_undecided_verdict_is_flagged_for_a8(scenario):
    sc = scenario(outcomes={("x", "s1"): {i: False for i in ids_of("s1")[:2]}})
    sig, _ = sc.sheet()
    want = expected(sc.w)
    flags = {(f["flag"], f["member"]) for f in sig["flags"]}
    assert (want["verdict"] == "UNDECIDED") == (("undecided", "A8") in flags)
    assert (want["verdict"] == "PASS") == (("undecided", "A8") not in flags and ("loss", "A8") not in flags)


# (c) descriptive beside the verdict: per-language loss bound at PER_SESSION_ALPHA (unadjusted, no verdict of its own)
def test_per_language_loss_bounds_are_descriptive(scenario):
    sc = scenario(outcomes=fails("x", "cpp", 2))
    sig, md = sc.sheet()
    m = maps(sc.w)
    nums = [v for v in leaves(sig["axes"]["A8"]) if isinstance(v, float)]
    for lang in W.LANGS:
        items = [i for i in m["x"] if W.lang_of(i) == lang]
        want = m76_rule.loss_bound({i: m["x"][i] for i in items}, {i: m["n16"][i] for i in items}, alpha=m76_rule.PER_SESSION_ALPHA)
        assert any(v == pytest.approx(want["loss_bound"]) for v in nums), lang
    assert re.search(r"per.?language[^\n]*descriptive|descriptive[^\n]*per.?language", json.dumps(sig["axes"]["A8"]) + md, re.I)


# (c) the noise floor: N16 s1 vs s2 discordance, and X vs N16
def test_noise_floor_counts_the_discordant_items(scenario):
    ids = ids_of("s1")
    sc = scenario(outcomes={("n16", "s1"): {ids[0]: False, ids[1]: False}, ("x", "s2"): {ids[1]: False, ids[2]: False}})
    sig, _ = sc.sheet()
    nf = sig["axes"]["A8"]["noise_floor"]
    m = maps(sc.w)
    n16_disc = sum(1 for i in m["n16"] if m["n16"][i]["s1"] != m["n16"][i]["s2"])
    vs = sum(1 for i in m["x"] for s in CONF if m["x"][i][s] != m["n16"][i][s])
    assert n16_disc in set(leaves(nf)) and vs in set(leaves(nf))


# (c) the reload control: X reload vs X s1 and N16 reload vs N16 s1 on the 20 shared items, seeds asserted equal per item
def test_reload_control_on_the_shared_items(scenario):
    sc = scenario(outcomes={("x", "reload"): {i: False for i in ids_of("reload")[:3]}})
    sig, md = sc.sheet()
    text = json.dumps(sig["axes"]["A8"]) + md
    assert "reload" in text and "seeds differ" not in text
    shared = {i for i in ids_of("reload")}
    assert len(shared) == 20 and shared <= set(ids_of("s1"))
    discordant = sum(1 for i in shared if sc.w._outcome("x", "reload", i)["passed"] != sc.w._outcome("x", "s1", i)["passed"])
    assert discordant == 3 and discordant in set(leaves(sig["axes"]["A8"].get("reload_control", sig["axes"]["A8"])))


# (a) B10: a reload whose seeds are not the plan's (`rowschema.sample_seed(id, 0, plan seed)`) is a B8-A8 REASON — the reload session is
# rejected, so the reload control is "not computed"; the sheet's "refused: seeds differ" stays a defensive line (not reachable here);
# the confirmatory verdict is unaffected by a diagnostic session
def test_a_reload_with_seeds_off_the_plan_is_rejected_and_the_control_not_computed(scenario):
    sc = scenario()
    rid = ids_of("reload")[2]
    for arm in PAIR:                      # both arms alike (the pair's equal-seed rule holds); only the plan's seed differs
        sc.w.edit_row(arm, "reload", rid, sampler_seed=1)
    sc.rebuild()
    reload = {p["pair"]: p for p in sc.doc["pairs"]}["reload"]
    assert reload["accepted"] is False and any("seed" in r for r in reload["reasons"]), reload["reasons"]
    sig, md = sc.sheet()
    rec = sig["axes"]["A8"]
    assert "refused: seeds differ" not in json.dumps(rec) + md
    assert "not computed" in json.dumps(rec["reload_control"])
    assert rec["verdict"] in ("PASS", "LOSS", "UNDECIDED")


# ------------------------------------------------------------------------------------------------------------------ incomplete
# (c) a partial decider: the axis is "incomplete", no verdict, no hold / loss flag, the sheet still renders its A8 heading
def test_partial_decider_gives_an_incomplete_axis_without_a_verdict(scenario):
    sig, md = scenario(sessions=("pilot",)).sheet()
    rec = sig["axes"]["A8"]
    assert "verdict" not in rec and str(rec["status"]).startswith("incomplete")
    assert not [f for f in sig["flags"] if f["flag"] in ("hold", "loss", "undecided") and f["member"] in ("A8", "A8-s1")]
    assert "## A8 tg2" in md


# (c) B9 / B10: a confirmatory session B8-A8 rejects (a row seed off the plan) leaves the axis incomplete: no verdict, no verdict flag
def test_a_rejected_confirmatory_session_makes_the_axis_incomplete(scenario):
    sc = scenario()
    rid = ids_of("s2")[4]
    for arm in PAIR:
        sc.w.edit_row(arm, "s2", rid, sampler_seed=7)
    sc.rebuild()
    assert sc.doc["status"] == "incomplete"
    sig, _ = sc.sheet()
    assert "verdict" not in sig["axes"]["A8"] and str(sig["axes"]["A8"]["status"]).startswith("incomplete")
    assert not [f for f in sig["flags"] if f["flag"] in ("hold", "loss", "undecided") and f["member"] == "A8"]


# (c) a PAUSED leg is never a result: the confirmatory session is incomplete, so is the axis
def test_a_paused_leg_makes_the_axis_incomplete(scenario):
    sig, _ = scenario(legs={("x", "s2"): dict(state="PAUSED")}).sheet()
    assert "verdict" not in sig["axes"]["A8"] and str(sig["axes"]["A8"]["status"]).startswith("incomplete")


# (c) a language outside TG2_LANGS refuses (the id prefix decides the language)
def test_unknown_language_prefix_refuses(scenario):
    sc = scenario()
    doc = json.loads(json.dumps(sc.doc))
    for p in doc["pairs"]:
        if p["pair"] in CONF:
            p["keys"][0]["key"][1] = "python/zzz"
    sha = hashlib.sha256(V.dumps(doc).encode()).hexdigest()
    with pytest.raises(V.RefusalError):
        S.compute_kv(sc.rows, sc.b8, b8_sha256=sc.b8_sha, b8_a8=doc, b8_a8_sha256=sha)


# ------------------------------------------------------------------------------------------------------------------ S27 additions
def faulted_scenario(scenario):
    ids = ids_of("s1")
    return scenario(reruns={("n16", "s1"): [ids[10]]}), ids[10]


# (c) sensitivity: with a faulted item the sheet prints the verdict with that item removed from both arms (descriptive, labelled)
def test_sensitivity_removes_the_faulted_item_from_both_arms(scenario):
    sc, rid = faulted_scenario(scenario)
    sig, md = sc.sheet()
    rec = sig["axes"]["A8"]
    assert rec["n_items"] == 80 and "no faulted items" not in md
    want = expected(sc.w, drop=(rid,))
    hit = find_dicts(rec, lambda d: d.get("n_items") == 79 and d.get("verdict") == want["verdict"] and d.get("delta") == W_json(want["delta"]))
    assert hit, "no 79-item axis_verdict record beside the verdict"
    assert re.search(r"sensitivity", json.dumps(rec) + md, re.I)


@pytest.mark.parametrize("kw", [
    lambda ids: dict(accounting={("x", "s2"): [ids[3]]}),
    lambda ids: dict(hdnf={("x", "s1"): {ids[3]: "harness_fault_dnf"}}),
    lambda ids: dict(reruns={("x", "s2"): [ids[3]]}),
])
def test_every_fault_kind_in_either_arm_or_session_is_removed(scenario, kw):
    ids = ids_of("s1")
    sc = scenario(**kw(ids))
    sig, _ = sc.sheet()
    assert find_dicts(sig["axes"]["A8"], lambda d: d.get("n_items") == 79)


# (c) with no faulted item the sheet says so
def test_sensitivity_without_faulted_items(scenario):
    sig, md = scenario().sheet()
    assert "no faulted items" in md or "no faulted items" in json.dumps(sig["axes"]["A8"])


# (c) the verdict keeps a faulted item (the sensitivity is beside it, never instead)
def test_the_verdict_keeps_faulted_items(scenario):
    sc, rid = faulted_scenario(scenario)
    sig, _ = sc.sheet()
    want = expected(sc.w)
    assert sig["axes"]["A8"]["verdict"] == want["verdict"] and sig["axes"]["A8"]["n_items"] == 80


# (c) an accounting-fault row keeps its outcome and leaves the decode aggregate (and is listed per arm)
def test_accounting_fault_keeps_its_outcome_and_leaves_the_decode_aggregate(scenario):
    ids = ids_of("s1")
    sc = scenario(accounting={("x", "s1"): [ids[5]]}, outcomes={("x", "s1"): {ids[5]: False}}, tokens={("x", "s1"): {ids[5]: 9_000_000}})
    sig, md = sc.sheet()
    want = expected(sc.w)
    assert sig["axes"]["A8"]["verdict"] == want["verdict"] and sig["axes"]["A8"]["delta"] == W_json(want["delta"])   # the outcome stays: a 0
    dec = sig["decode"]["A8"]
    assert dec["s1"]["primary"]["n"] == 79 and dec["s2"]["primary"]["n"] == 80
    assert ids[5] in json.dumps(sig["axes"]["A8"]) + md                                                          # listed
    assert "9000000" not in json.dumps(sig["decode"]["A8"])                                                      # its tokens left the aggregate


# (c) speed-invalid tiers mark the leg's speed figures descriptive-invalid; quality is unaffected
def test_speed_invalid_leg_leaves_quality_unaffected(scenario):
    sc = scenario(legs={("x", "s1"): dict(speed_valid=False, speed_reason="ALERT: watcher gap")})
    sig, md = sc.sheet()
    want = expected(sc.w)
    assert sig["axes"]["A8"]["verdict"] == want["verdict"] and sig["axes"]["A8"]["delta"] == W_json(want["delta"])
    assert re.search(r"invalid", json.dumps(sig["decode"]["A8"]["s1"]) + md, re.I)


# ------------------------------------------------------------------------------------------------------------------ latency
# (c) absent -> `latency: incomplete` (descriptive, never a refusal); present -> a summary per leg window
def test_latency_summary(scenario):
    sc = scenario()
    sig, md = sc.sheet()
    assert re.search(r"latency[^\n]*incomplete", md, re.I) and sig["axes"]["A8"]["verdict"]
    sc.w.write_latency()
    sc.rebuild()
    sig2, md2 = sc.sheet()
    assert not re.search(r"latency[^\n]*incomplete", md2, re.I) and "latency" in md2.lower()


# ------------------------------------------------------------------------------------------------------------------ no-A8 / A8 projections (§7.1, §7.2)
# (b) with no B8-A8.json the sheet is untouched: no A8 section, no "pending", and the same record and text as the call without the argument
def test_no_b8_a8_means_no_a8_in_the_sheet(scenario):
    sc = scenario(with_a8=False)
    sig, md = sc.sheet(a8=False)
    assert "A8" not in sig["axes"] and "A8" not in (sig.get("decode") or {}) and "A8" not in md and "pending (no B8-A8" not in md
    assert not [f for f in sig["flags"] if "A8" in json.dumps(f)]


# (c) spelling the new arguments as None is the same sheet as not passing them
def test_explicit_none_equals_the_default(scenario):
    sc = scenario(with_a8=False)
    sig, md = sc.sheet(a8=False)
    sig2 = S.compute_kv(sc.rows, sc.b8, b8_sha256=sc.b8_sha, b8_a8=None, b8_a8_sha256=None)
    assert json.dumps(sig, sort_keys=True) == json.dumps(sig2, sort_keys=True) and md == S.render_kv(sig2)


def projection(sig, md):
    """The sheet without what B8-A8 may change: the A8 section, the header shas / counts, the flags, the Holm-adjusted column."""
    sig = copy.deepcopy(sig)
    sig["axes"].pop("A8", None)
    (sig.get("decode") or {}).pop("A8", None)
    sig["header"] = {k: v for k, v in sig["header"].items() if "sha" not in k and "n_inputs" not in k and "a8" not in k.lower()}
    for k in ("inputs", "inputs_a8", "flags"):          # the candidate adds `inputs_a8` beside B8's `inputs` (p426_signals.compute_kv)
        sig.pop(k, None)
    for m in ((sig.get("panel") or {}).get("members") or {}).values():
        m.pop("holm_p", None)
    return sig


# (b) with B8-A8.json: B8.json stays, and A1–A7 sections / raw panel statistics are identical; only the A8 parts differ
def test_a8_record_changes_only_the_a8_parts_of_the_sheet(scenario):
    sc = scenario()
    base, _ = sc.sheet(a8=False)
    with_a8, md = sc.sheet()
    assert json.dumps(projection(base, ""), sort_keys=True, default=str) == json.dumps(projection(with_a8, md), sort_keys=True, default=str)
    old_flags = {json.dumps(f, sort_keys=True) for f in base["flags"]}
    new_flags = {json.dumps(f, sort_keys=True) for f in with_a8["flags"]}
    assert old_flags <= new_flags and all("A8" in f or "hold" in f for f in new_flags - old_flags)
    assert (sc.rows / "m76" / "B8.json").read_bytes() == sc.b8_bytes


# (b) the A1–A7 lines of the sheet text are the same, line for line
def test_a8_record_leaves_the_a1_to_a7_text_alone(scenario):
    sc = scenario()
    _, md0 = sc.sheet(a8=False)
    _, md1 = sc.sheet()
    old, new = md0.splitlines(), md1.splitlines()
    assert "## A8 tg2" in md1
    kept, inside = [], False
    for ln in new:                                  # the A8 section runs from its heading to the next heading
        if ln.startswith("## "):
            inside = ln.startswith("## A8 tg2")
        if not inside:
            kept.append(ln)
    # what else B8-A8 adds mentions A8 (its header line, its flags); every other line is the old sheet's, in order
    it = iter(kept)
    for ln in old:
        for cand in it:
            if cand == ln:
                break
            assert cand == "" or "A8" in cand or "hold" in cand.lower(), cand
        else:
            pytest.fail(f"an old sheet line is missing or moved: {ln!r}")


# ------------------------------------------------------------------------------------------------------------------ binding (§4.4)
# (c) the signals verify `b8_a8.base_b8_sha256 == b8_sha256`
def test_b8_a8_of_another_b8_refuses(scenario):
    sc = scenario()
    with pytest.raises(V.RefusalError):
        S.compute_kv(sc.rows, sc.b8, b8_sha256="0" * 64, b8_a8=sc.doc, b8_a8_sha256=sc.doc_sha)


# (c) and re-hash every input B8-A8 names: a file changed after B8-A8 was built refuses
def test_a_changed_a8_input_refuses(scenario):
    sc = scenario()
    path = sc.w.adir("x", "s1", "receipt.json")
    path.write_text(path.read_text() + " ")
    with pytest.raises(V.RefusalError):
        sc.sheet()
