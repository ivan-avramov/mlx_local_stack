"""B6: runaway tax (+ C269 sensitivity), speed (primary / sensitivity / acceptance / wall), noise floor, coverage.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
"""
from __future__ import annotations

import math

import pytest

from bench.tests.p613 import a7world as W
from bench.tests.p613 import sigview as V

IDS8 = W.DEFAULT_IDS["s1"]
CATS = ("budget_hit", "turn_cap", "exec_timeout", "client_inactivity", "looping", "stalled")


def fail(kind=None, flags=(), converged=False):
    return {"passed": False, "converged": converged, "nonconv_kind": kind, "nonconv_flags": list(flags)}


def tax(sig, session, arm, cat):
    return V.counts_at(V.scope(sig, session), arm, cat)


# ===================================================================================================== runaway tax
TAX_OFF = {"python/a1": fail("budget_hit", ["budget_hit"]), "python/a2": fail(None, ["turn_cap"]),
           "python/a3": fail("looping", ["looping", "budget_hit"])}
TAX_ON = {"go/g1": fail("client_inactivity"), "go/g2": fail("stalled", ["stalled", "exec_timeout"])}


# class: new-behaviour (each category its own count; an item with two flags counts in both; kind OR flags)
@pytest.mark.parametrize("arm,cat,expected", [
    ("off", "budget_hit", 2), ("off", "turn_cap", 1), ("off", "looping", 1),
    ("on", "client_inactivity", 1), ("on", "stalled", 1), ("on", "exec_timeout", 1),
])
def test_tax_category_counts(pipeline, arm, cat, expected):
    _, _, sig = pipeline(rows={("off", "s1"): TAX_OFF, ("on", "s1"): TAX_ON})
    assert expected in tax(sig, "s1", arm, cat), (arm, cat, tax(sig, "s1", arm, cat))


# class: new-behaviour (the per-session union counts an item once: OFF 3 items, ON 2 items)
@pytest.mark.parametrize("arm,expected", [("off", 3), ("on", 2)])
def test_tax_union_deduplicates_items(pipeline, arm, expected):
    _, _, sig = pipeline(rows={("off", "s1"): TAX_OFF, ("on", "s1"): TAX_ON})
    assert expected in tax(sig, "s1", arm, "union"), tax(sig, "s1", arm, "union")


# class: new-behaviour (a category absent in an arm is reported as zero or not at all, never a phantom count)
def test_tax_absent_category_is_not_counted(pipeline):
    _, _, sig = pipeline(rows={("off", "s1"): TAX_OFF, ("on", "s1"): TAX_ON})
    assert all(v == 0 for v in tax(sig, "s1", "on", "budget_hit"))
    assert all(v == 0 for v in tax(sig, "s1", "off", "client_inactivity"))
    assert all(v == 0 for v in tax(sig, "s1", "off", "stalled"))


# class: new-behaviour (tax is per session: s2 is clean)
def test_tax_is_per_session(pipeline):
    _, _, sig = pipeline(rows={("off", "s1"): TAX_OFF, ("on", "s1"): TAX_ON})
    for arm in ("on", "off"):
        assert all(v == 0 for v in tax(sig, "s2", arm, "union"))


# class: new-behaviour (client_inactivity carries its own category; the item's client_abort block is surfaced)
def test_client_abort_block_is_surfaced(pipeline):
    patch = fail("client_inactivity")
    patch["client_abort"] = {"kind": "inactivity", "silent_s": 1234.5}
    _, _, sig = pipeline(rows={("on", "s1"): {"go/g1": patch}})
    assert 1234.5 in V.numbers(V.scope(sig, "s1")) or "client_abort" in V.text(V.scope(sig, "s1"))


# ===================================================================================================== C269 sensitivity
# s1: OFF fails a4,a5; ON fails g1 (client_inactivity) => base delta +1/8; without the g1 pair: +2/7.
# s2: OFF fails h2 (client_inactivity), ON fails h3 => base 0; without the h2 pair (EITHER arm's ci excludes it): -1/7.
def c269_rows():
    off1 = {i: {"passed": i not in ("python/a4", "python/a5"), "converged": True} for i in IDS8}
    on1 = {i: {"passed": i != "go/g1", "converged": i != "go/g1"} for i in IDS8}
    on1["go/g1"].update(nonconv_kind="client_inactivity")
    ids2 = W.DEFAULT_IDS["s2"]
    off2 = {i: {"passed": i != "go/h2", "converged": i != "go/h2"} for i in ids2}
    off2["go/h2"].update(nonconv_kind="client_inactivity")
    on2 = {i: {"passed": i != "go/h3", "converged": True} for i in ids2}
    return {("off", "s1"): off1, ("on", "s1"): on1, ("off", "s2"): off2, ("on", "s2"): on2}


# class: new-behaviour (paired delta without the client_inactivity pairs; the base delta stays beside it)
def test_c269_sensitivity_drops_the_client_inactivity_pair(pipeline):
    _, _, sig = pipeline(rows=c269_rows())
    s1 = V.scope(sig, "s1")
    base = V.paired([1, 1, 1, 1, 1, 0, 1, 1], [1, 1, 1, 0, 0, 1, 1, 1], IDS8)      # plan order a1..a5, g1..g3
    keep = [i for i in IDS8 if i != "go/g1"]
    sens = V.paired([1] * 7, [1, 1, 1, 0, 0, 1, 1], keep)
    assert base["delta"] == pytest.approx(0.125) and sens["delta"] == pytest.approx(2 / 7)
    for r in (base, sens):
        for k in ("delta", "lo", "hi"):
            assert V.has_num(sig, "s1", r[k], sess_tree=s1), (k, r[k])


# class: new-behaviour (either arm's client_inactivity removes the pair: here the OFF arm's)
def test_c269_either_arm_excludes_the_pair(pipeline):
    _, _, sig = pipeline(rows=c269_rows())
    s2 = V.scope(sig, "s2")
    ids = W.DEFAULT_IDS["s2"]
    keep = [i for i in ids if i != "go/h2"]
    sens = V.paired([0 if i == "go/h3" else 1 for i in keep], [1] * 7, keep)
    assert sens["delta"] == pytest.approx(-1 / 7)
    for k in ("delta", "lo", "hi"):
        assert V.has_num(sig, "s2", sens[k], sess_tree=s2), k


# class: new-behaviour (no client_inactivity anywhere: the sensitivity equals the base, so a delta is reported at least once)
def test_c269_sensitivity_without_inactivity_equals_base(pipeline):
    ids = IDS8
    rows = {("on", "s1"): {i: {"passed": i != "python/a3"} for i in ids}}
    _, _, sig = pipeline(rows=rows)
    r = V.paired([1, 1, 0, 1, 1, 1, 1, 1], [1] * 8, ids)
    assert V.has_num(sig, "s1", r["delta"], sess_tree=V.scope(sig, "s1"))


# ===================================================================================================== speed
# class: new-behaviour (primary: per item (gen - requests) / decode_s; paired ON / OFF ratio; geometric mean 1.5)
def test_speed_geomean_ratio_primary(pipeline):
    _, _, sig = pipeline()
    s1 = V.scope(sig, "s1")
    assert V.has_num(sig, "s1", 1.5, tol=1e-9, pct=False, sess_tree=s1)


# class: new-behaviour (hand-computed: ratios 2, 0.5, 4 and five 1s -> geometric mean 4^(1/8))
def test_speed_geomean_of_unequal_ratios(pipeline):
    on = {"python/a1": {"rate": 40.0}, "python/a2": {"rate": 10.0}, "python/a3": {"rate": 80.0}}
    off = {i: {"rate": 20.0} for i in IDS8}
    on.update({i: {"rate": 20.0} for i in IDS8 if i not in on})
    _, _, sig = pipeline(speed={("on", "s1"): on, ("off", "s1"): off})
    gm = 4 ** (1 / 8)
    assert V.has_num(sig, "s1", gm, tol=1e-9, pct=False, sess_tree=V.scope(sig, "s1"))


# class: new-behaviour (the interval brackets the point; a plain geomean_ratio_ci over the items in plan or id order)
def test_speed_interval_matches_geomean_ratio_ci(pipeline, signals):
    mult = {"python/a1": 2.0, "python/a2": 0.5, "python/a3": 4.0, "python/a4": 1.0, "python/a5": 3.0, "go/g1": 1.0,
            "go/g2": 0.8, "go/g3": 1.25}
    on = {i: {"rate": 20.0 * m} for i, m in mult.items()}
    _, _, sig = pipeline(speed={("on", "s1"): on, ("off", "s1"): {i: {"rate": 20.0} for i in IDS8}})
    s1 = V.scope(sig, "s1")
    pool = V.numbers(s1)
    plan_order = [mult[i] for i in IDS8]
    id_order = [mult[i] for i in sorted(IDS8)]
    candidates = [signals.geomean_ratio_ci(o) for o in (plan_order, id_order)]
    assert any(any(abs(v - c["lo"]) < 1e-9 for v in pool) and any(abs(v - c["hi"]) < 1e-9 for v in pool)
               for c in candidates), [(c["lo"], c["hi"]) for c in candidates]
    assert any(abs(v - candidates[0]["point"]) < 1e-9 for v in pool)


# class: new-behaviour (the sensitivity pools requests: sum(g-1) / sum((g-1)/tps), skipping tps <= 0 and g < 1)
def test_speed_sensitivity_uses_request_records(pipeline):
    reqs = [{"generated_tokens": 11, "decode_tok_s": 5.0, "draft_n": None, "draft_n_accepted": None, "error": None},
            {"generated_tokens": 21, "decode_tok_s": 10.0, "draft_n": None, "draft_n_accepted": None, "error": None},
            {"generated_tokens": 50, "decode_tok_s": 0.0, "draft_n": None, "draft_n_accepted": None, "error": None},
            {"generated_tokens": 0, "decode_tok_s": 7.0, "draft_n": None, "draft_n_accepted": None, "error": None}]
    # totals: 32 generated over 2 completed requests in 10 s  => primary 30 / 10 = 3.0 tok/s;  sensitivity 30 / (2 + 2) = 7.5
    spec = {"requests": reqs, "generated_tokens": 32, "n_requests": 2, "decode_s": 10.0}
    _, _, sig = pipeline(speed={("on", "s1"): {"python/a1": spec}})
    s1 = V.scope(sig, "s1")
    primary = (3.0 / 20.0 * 1.5 ** 7) ** (1 / 8)
    sens = (7.5 / 20.0 * 1.5 ** 7) ** (1 / 8)
    assert V.has_num(sig, "s1", primary, tol=1e-9, pct=False, sess_tree=s1), "primary uses the totals"
    assert V.has_num(sig, "s1", sens, tol=1e-9, pct=False, sess_tree=s1), "sensitivity uses the request records"


# class: new-behaviour (an item with no completed request in an arm is dropped and listed; n shrinks)
def test_speed_drops_items_without_a_usable_rate(pipeline):
    dead = {"requests": [], "generated_tokens": 0, "n_requests": 0, "decode_s": 0.0}
    _, _, sig = pipeline(speed={("on", "s1"): {"python/a2": dead}})
    s1 = V.scope(sig, "s1")
    assert frozenset({"python/a2"}) in V.id_lists(s1), "the dropped item is listed"
    assert V.has_num(sig, "s1", 1.5, tol=1e-9, pct=False, sess_tree=s1)      # the other 7 items still give 1.5
    assert 7 in V.numbers(s1) or 7.0 in V.numbers(s1)


# class: new-behaviour (the *.ready.json decoys carry absurd totals and must be ignored)
def test_ready_records_are_not_item_records(pipeline):
    _, _, sig = pipeline()
    pool = V.numbers(V.scope(sig, "s1"))
    assert all(v < 1e6 for v in pool), "a decoy .ready.json total leaked into the sheet"


# class: new-behaviour (acceptance = sum accepted / sum proposed within the session, ON only)
def test_acceptance_is_sum_over_sum(pipeline):
    spec = {"python/a1": {"accepted": 50, "proposed": 100}}
    _, _, sig = pipeline(speed={("on", "s1"): spec})
    assert V.has_num(sig, "s1", 610 / 800, tol=1e-9, pct=True, sess_tree=V.scope(sig, "s1"))
    assert V.has_num(sig, "s2", 0.8, tol=1e-9, pct=True, sess_tree=V.scope(sig, "s2"))


# class: new-behaviour (per-leg wall from leg.json: ended - started, seconds, descriptive)
def test_wall_per_leg(pipeline, make_world, verify, signals):
    w = make_world(legs={("on", "s1"): {"started": "2026-11-03T03:00:00Z", "ended": "2026-11-03T05:00:00Z"}})
    sig = signals.compute_a7(w.root, verify.verify_a7(w.root))
    # amended (delivery 3): `walls` is keyed by attempt name, not by session
    assert sig["walls"]["tg1-p426-on-s1.a1"]["wall_s"] == 7200.0
    assert sig["walls"]["tg1-p426-off-s1.a1"]["wall_s"] == 5415.0, "the OFF leg: 1 h 30 min 15 s"


# class: new-behaviour (power-invalid pair: quality stays; speed numbers kept but labelled descriptive, no inference, no flag)
def test_power_invalid_pair_keeps_quality_and_marks_speed_descriptive(pipeline):
    ids = IDS8
    on = {i: {"passed": i != "python/a4", "converged": True} for i in ids}
    off = {i: {"passed": True, "converged": True} for i in ids}
    poor = {i: {"rate": 10.0} for i in ids}                       # ratio 0.5: would raise the decode flag if inferred
    _, b8, sig = pipeline(rows={("on", "s1"): on, ("off", "s1"): off}, speed={("on", "s1"): poor},
                          legs={("on", "s1"): {"speed_valid": False}})
    s1 = sig["sessions"]["s1"]
    assert [p["speed_valid"] for p in b8["pairs"] if p["pair"] == "s1"] == [False]
    assert s1["paired_strict"]["delta"] == pytest.approx(-0.125), "quality delta kept"
    assert s1["speed"]["inference"] is False and "descriptive" in s1["speed"]["order_note"]
    assert s1["speed"]["primary"]["geomean_ratio"] == pytest.approx(0.5), "numbers kept, labelled descriptive"
    assert "power-invalid" in s1["labels"]
    assert "decode_ratio_below_1.3" not in [f["flag"] for f in sig["flags"]]
    assert sig["sessions"]["s2"]["speed"]["inference"] is True


# ===================================================================================================== noise floor (C273)
def old_ns():
    flip = {"python/a2": {"passed": False}}
    many = {i: {"passed": False} for i in IDS8[:6]}
    return {"v8_sha_note": "old", "attempts": [
        {"arm": "off", "session": "s1", "n": 1, "rows": flip},                       # same schedule, VALID, 1 flip / 8
        {"arm": "off", "session": "pilot", "n": 1, "rows": {}},                      # same schedule, VALID, 0 flips / 5
        {"arm": "on", "session": "s1", "n": 1, "state": "INVALID", "rows": many},    # INVALID in the old namespace: excluded
        {"arm": "on", "session": "pilot", "n": 1, "note": "different schedule", "rows": many},   # schedule differs: excluded
        {"arm": "on", "session": "s1", "n": 2, "rows": many},                        # no a2 in the new namespace: excluded
    ]}


# class: new-behaviour (same-epoch: reload vs pilot per arm, items whose (passed, converged) differ / 5)
def test_same_epoch_noise_floor_per_arm(pipeline):
    ids = W.DEFAULT_IDS["pilot"]
    off_reload = {"python/a3": {"passed": False}}
    on_reload = {"python/a1": {"converged": False, "nonconv_kind": "budget_hit"}, "python/a2": {"passed": False}}
    _, _, sig = pipeline(rows={("off", "reload"): off_reload, ("on", "reload"): on_reload})
    noise = V.subtree(sig, "noise")
    assert noise, "a noise-floor section"
    pool = V.numbers(noise)
    assert (0.2 in pool or 20.0 in pool) and (0.4 in pool or 40.0 in pool) or {1, 2, 5} <= set(pool)
    assert "reload" in V.text(noise).lower() and "pilot" in V.text(noise).lower()


# class: new-behaviour (a clean box: 0 / 5 for both arms)
def test_same_epoch_noise_floor_zero(pipeline):
    _, _, sig = pipeline()
    pool = V.numbers(V.subtree(sig, "noise"))
    assert 0 in pool and 5 in pool


# class: new-behaviour (cross-epoch: equal schedule sha and VALID in both namespaces; flips / common items; both v8 shas printed)
def test_cross_epoch_noise_floor(pipeline):
    w, _, sig = pipeline(old_namespace=old_ns())
    noise = V.subtree(sig, "noise")
    # amended (delivery 3): spec §4.9 names `on-s1.a2` as a qualifying attempt (compared by leg name); the INVALID `on-s1.a1`
    # and the different-schedule `on-pilot.a1` do not qualify
    matches = {(m["arm"], m["superseded"], m["flips"], m["common"]) for m in sig["noise_floor"]["cross_epoch"]["matches"]}
    assert matches == {("off", "tg1-p426-off-s1.a1", 1, 8), ("off", "tg1-p426-off-pilot.a1", 0, 5),
                       ("on", "tg1-p426-on-s1.a2", 6, 8)}
    excluded = {m["superseded"] for m in sig["noise_floor"]["cross_epoch"]["excluded"]}
    assert {"tg1-p426-on-s1.a1", "tg1-p426-on-pilot.a1"} <= excluded
    blob = V.text(noise)
    new_sha = w.load("wave2", "run", "v8_base.json")["sha256"]
    old_sha = w.load(W.OLD_NS, "run", "v8_base.json")["sha256"]
    assert new_sha != old_sha and new_sha in blob and old_sha in blob, "both v8_base sha256 values are printed"


# class: new-behaviour (no old namespace: the cross-epoch block says so instead of inventing numbers)
def test_cross_epoch_absent_namespace(pipeline):
    _, _, sig = pipeline()
    assert V.subtree(sig, "noise")


# class: new-behaviour (the superseded namespace is never a pair member and never enters the s1 / s2 numbers)
def test_superseded_namespace_does_not_leak_into_sessions(pipeline):
    _, _, a = pipeline()
    _, _, b = pipeline(old_namespace=old_ns())
    # amended (delivery 3): compare the session records themselves; `scope()` also collects noise-floor records tagged "s1"
    assert V.text(a["sessions"]["s1"]) == V.text(b["sessions"]["s1"])
    assert V.text(a["sessions"]["s2"]) == V.text(b["sessions"]["s2"])


# ===================================================================================================== coverage
# class: new-behaviour (coverage: an INVALID leg is listed as invalid by name)
def test_coverage_lists_invalid_leg(pipeline):
    _, _, sig = pipeline(legs={("on", "s1"): {"state": "INVALID"}})
    cov = V.subtree(sig, "coverage")
    assert cov
    assert "tg1-p426-on-s1" in V.text(cov) and "INVALID" in V.text(cov)


# class: new-behaviour (coverage: the eight legs are listed with their states; the spec requires no count leaf — amended)
def test_coverage_lists_valid_legs(pipeline):
    _, _, sig = pipeline()
    a7 = sig["coverage"]["A7"]
    names = sorted(f"{d['leg']}.a{d['attempt']}" for d in a7["done"])
    want = sorted(W.attempt_name(arm, s) for arm in ("off", "on") for s in ("s1", "s2", "pilot", "reload"))
    assert names == want and all(d["state"] == "VALID" for d in a7["done"])
    assert a7["invalid"] == [] and a7["pending"] == [] and a7["state_mismatch"] == []
