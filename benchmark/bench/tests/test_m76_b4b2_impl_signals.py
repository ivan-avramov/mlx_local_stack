"""M76 B4b-2 signals (`p426_signals`): the A8 section — the verdict only from `m76_rule.axis_verdict("A8", …, languages=…)`, the
HOLD flag, DNF / harness DNF = 0, the reload seed assert, the sensitivity line, accounting-fault items out of the decode
aggregate, the flags and the rendered section (spec v1.5 §4, §7.4, §9.5–§9.7)."""
from __future__ import annotations

import json

import pytest

from bench import m76_rule
from bench import p426_signals as S
from bench import p426_verify as V
from bench.tests.test_m76_b4b2_impl_world import A8World, dumps

LANGS = ("rust", "javascript", "java", "cpp")


def section(w, base="b" * 64):
    doc = V.verify_a8_kv(w.root, base)
    return S._kv_a8_section(w.root.parent, doc, "n16", "x"), doc


def ids_of(w, lang, s="s1"):
    return [i for i in w.ids(s) if i.startswith(lang + "/")]


def maps(w, rows):
    """The strict maps B7 must see: item → {s1, s2: 0/1} per arm (1 unless the patch fails / DNFs the slot)."""
    out = {}
    for arm in ("n16", "x"):
        out[arm] = {}
        for i in w.ids("s1"):
            out[arm][i] = {}
            for s in ("s1", "s2"):
                p = (rows.get((arm, s)) or {}).get(i) or {}
                out[arm][i][s] = 0 if (p.get("_dnf") or p.get("passed") is False or p.get("converged") is False) else 1
    return out


def test_the_verdict_is_axis_verdict_with_languages(tmp_path):
    probe = A8World(tmp_path / "p", sessions=("s1",))
    rows = {("x", "s1"): {i: dict(passed=False) for i in ids_of(probe, "java")[:2]},
            ("n16", "s2"): {ids_of(probe, "cpp")[0]: dict(converged=False)}}
    w = A8World(tmp_path / "w", rows=rows)
    (rec, decode), _doc = section(w)
    m = maps(w, rows)
    want = m76_rule.axis_verdict("A8", 1, m["x"], m["n16"], languages={i: i.split("/")[0] for i in m["x"]})
    for k in ("verdict", "delta", "lo", "hi", "loss_bound", "alpha", "interaction_flag", "size_warnings", "hold", "n_items"):
        assert rec[k] == S._jsonable(want[k]), k
    assert rec["alpha"] == 0.001 and rec["n_items"] == 80 and rec["n_sessions"] == 2 and rec["size_warnings"] == []
    assert rec["descriptive"]["statistic"].startswith("paired_session_delta")
    assert set(rec["per_language"]) == set(LANGS) and "verdict" not in rec["per_language"]["java"]
    assert rec["per_language"]["java"]["delta"] == pytest.approx(-2 / 20 / 2)
    assert set(decode) == {"s1", "s2", "pilot", "reload"} and decode["s1"]["primary"]["n"] == 80


def test_hold_fires_below_minus_twenty_pp_and_blocks(tmp_path):
    probe = A8World(tmp_path / "p", sessions=("s1",))
    fails = {i: dict(passed=False) for i in ids_of(probe, "rust")[:5]}           # rust 5 / 20 in both sessions: −25 pp
    w = A8World(tmp_path / "w", rows={("x", "s1"): fails, ("x", "s2"): fails})
    (rec, _d), _doc = section(w)
    assert rec["hold"]["hold"] is True and rec["hold"]["languages"] == ["rust"] and rec["blocking"] is True
    assert rec["hold"]["per_language"]["rust"] == pytest.approx(-0.25)
    sig = dict(header=dict(label="X − N16"), axes=dict(A8=rec))
    flags = [f for f in S.kv_flags(sig) if f["flag"] == "hold"]
    assert len(flags) == 1 and flags[0]["blocking"] is True and flags[0]["member"] == "A8" and "rust -25.0 pp" in flags[0]["text"]
    assert "hold" in S.KV_BLOCKING


def test_exactly_minus_twenty_pp_does_not_hold(tmp_path):
    probe = A8World(tmp_path / "p", sessions=("s1",))
    fails = {i: dict(passed=False) for i in ids_of(probe, "rust")[:4]}           # −20 pp exactly
    w = A8World(tmp_path / "w", rows={("x", "s1"): fails, ("x", "s2"): fails})
    (rec, _d), _doc = section(w)
    assert rec["hold"]["hold"] is False
    assert not [f for f in S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A8=rec))) if f["flag"] == "hold"]


@pytest.mark.parametrize("kind", ["transport", "harness"])
def test_a_dnf_slot_scores_zero(tmp_path, kind):
    probe = A8World(tmp_path / "p", sessions=("s1",))
    rid = ids_of(probe, "javascript")[3]
    rows = {("x", "s1"): {rid: dict(_dnf=kind)}}
    w = A8World(tmp_path / "w", rows=rows)
    (rec, _d), doc = section(w)
    assert doc["status"] == "complete"
    m = maps(w, rows)
    assert m["x"][rid] == {"s1": 0, "s2": 1}
    want = m76_rule.axis_verdict("A8", 1, m["x"], m["n16"], languages={i: i.split("/")[0] for i in m["x"]})
    assert rec["delta"] == want["delta"] == pytest.approx(-1 / 160)
    assert rec["counts"]["s1"]["x"]["harness_dnf" if kind == "harness" else "transport_dnf"] == [rid]


def test_the_sensitivity_line(tmp_path):
    w = A8World(tmp_path / "clean")
    (rec, _d), _doc = section(w)
    assert rec["sensitivity"]["status"] == "no faulted items" and rec["sensitivity"]["label"] == S.KV_A8_SENSITIVITY
    rid = ids_of(w, "cpp")[0]
    w2 = A8World(tmp_path / "faulted", rows={("n16", "s2"): {rid: dict(_rerun=True, passed=False)}})
    (rec2, _d), _doc = section(w2)
    sens = rec2["sensitivity"]
    assert sens["status"] == "computed" and sens["removed"] == [rid] and sens["n_items"] == 79
    m = maps(w2, {("n16", "s2"): {rid: dict(passed=False)}})
    keep = [i for i in m["x"] if i != rid]
    want = m76_rule.axis_verdict("A8", 1, {i: m["x"][i] for i in keep}, {i: m["n16"][i] for i in keep},
                                 languages={i: i.split("/")[0] for i in keep})
    assert sens["delta"] == want["delta"] and sens["verdict"] == want["verdict"]
    assert rec2["verdict"] == S._jsonable(m76_rule.axis_verdict("A8", 1, m["x"], m["n16"],
                                                                 languages={i: i.split("/")[0] for i in m["x"]}))["verdict"]
    flags = S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A8=rec2)))
    assert not [f for f in flags if "sensitivity" in f["text"]]                 # never a verdict, never a flag


def test_an_accounting_fault_leaves_the_decode_aggregate_and_keeps_its_outcome(tmp_path):
    w = A8World(tmp_path / "w")
    rid = ids_of(w, "rust")[2]
    w2 = A8World(tmp_path / "a", rows={("x", "s1"): {rid: dict(_accounting=True, passed=False)}})
    (rec, decode), _doc = section(w2)
    assert decode["s1"]["primary"]["n"] == 79 and decode["s1"]["accounting_excluded"] == [rid]
    assert rid not in decode["s1"]["primary"]["per_item"] and decode["s2"]["primary"]["n"] == 80
    assert rec["walls"]["s1"]["per_language"]["rust"]["n"] == 19 and rec["walls"]["s2"]["per_language"]["rust"]["n"] == 20
    assert rec["delta"] == pytest.approx(-1 / 160)                              # the outcome stays (x s1 fails it)
    assert rec["sensitivity"]["removed"] == [rid]


def test_the_reload_control_asserts_equal_seeds(tmp_path):
    w = A8World(tmp_path / "w")
    (rec, _d), _doc = section(w)
    rc = rec["reload_control"]
    assert rc["status"] == "computed" and rc["n"] == 20 and rc["x_reload_vs_s1"]["discordant"] == 0
    rid = ids_of(w, "java", "reload")[1]
    same = {rid: dict(sampler_seed=7)}                                    # both arms agree but not with the plan
    w2 = A8World(tmp_path / "s", rows={("x", "reload"): same, ("n16", "reload"): same})
    (rec2, _d), doc2 = section(w2)
    # change review r1 B10: a row seed off the plan's is a B8-A8 REASON, so the reload is never accepted to reach the control
    reload2 = next(p for p in doc2["pairs"] if p["pair"] == "reload")
    assert not reload2["accepted"] and any("sampler_seed" in r for r in reload2["reasons"])
    assert rec2["reload_control"]["status"].startswith("not computed")
    w3 = A8World(tmp_path / "one", rows={("x", "reload"): same})        # one arm only: B8-A8 rejects the reload's key
    (rec3, _d), doc3 = section(w3)
    assert rec3["reload_control"]["status"].startswith("not computed")


def test_incomplete_b8_a8_gives_no_verdict_and_no_flag(tmp_path):
    w = A8World(tmp_path, sessions=("pilot", "s1"))
    (rec, decode), doc = section(w)
    assert doc["status"] == "incomplete" and "verdict" not in rec and rec["status"].startswith("incomplete") and decode is None
    assert S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A8=rec))) == []
    md = S._render_a8(rec, "X − N16")
    assert md[0].startswith("- incomplete") and any("re-check s1" in x and ": ok" in x for x in md)


def test_a_rejected_confirmatory_session_is_incomplete(tmp_path):
    w = A8World(tmp_path)
    c = w.chain("x", "s2")
    c["tg2_leg"] = "s1"
    w.put_chain("x", "s2", c)
    (rec, _d), doc = section(w)
    # change review r1 B9: B8-A8 is complete only when every confirmatory session is accepted
    assert doc["status"] == "incomplete" and "verdict" not in rec and rec["status"].startswith("incomplete")


def test_session_interaction_flags_a8(tmp_path):
    rec = dict(verdict="PASS", interaction_flag=True, interaction=dict(pvalue=0.01), hold=dict(hold=False), size_warnings=[])
    flags = S.kv_flags(dict(header=dict(label="X − N16"), axes=dict(A8=rec)))
    assert [f["flag"] for f in flags] == ["session_interaction"] and flags[0]["member"] == "A8"


def test_a_language_outside_tg2_refuses():
    with pytest.raises(V.RefusalError, match="not a tg2 language"):
        S._a8_language("python/grep")


def test_the_latency_summary_per_leg_window(tmp_path):
    w = A8World(tmp_path)
    w.latency(rows=[dict(t="2026-11-20T02:00:00Z", fresh_ms=100.0, repeat_ms=40.0, true_ms=30.0, threatlocker_cpu=3.0),
                    dict(t="2026-11-20T03:00:00Z", fresh_ms=300.0, repeat_ms=60.0, true_ms=50.0, threatlocker_cpu=9.0),
                    dict(t="2026-11-20T11:00:00Z", fresh_ms=900.0, repeat_ms=90.0, true_ms=80.0, threatlocker_cpu=1.0)])
    (rec, _d), _doc = section(w)
    win = rec["latency"]["windows"]
    assert win["s1/x"] == dict(n=2, median_fresh_ms=200.0, median_repeat_ms=50.0, median_true_ms=40.0, max_threatlocker_cpu=9.0)
    assert win["s2/n16"]["n"] == 1 and win["pilot/x"]["n"] == 0


def test_a_speed_invalid_leg_labels_its_decode(tmp_path):
    w = A8World(tmp_path)
    c = w.chain("n16", "s2")
    c["p426_holds"] = [dict(start="a", end="b", reason="PAUSE file")]
    w.put_chain("n16", "s2", c)
    (rec, decode), _doc = section(w)
    assert decode["s2"]["label"].startswith("descriptive-invalid") and decode["s2"]["inference"] is False
    assert decode["s1"]["label"] == "descriptive" and rec["walls"]["s2"]["label"].startswith("descriptive-invalid")


def test_the_sheet_renders_the_a8_section_after_a7(tmp_path):
    w = A8World(tmp_path)
    (rec, decode), _doc = section(w)
    sig = S.kv_sheet_skeleton(("n16", "x"))
    sig["axes"].update(A1=dict(looks=[], final_look=None), A5=dict(status="pending"), A7=dict(status="pending"), A8=rec)
    sig["decode"] = {"A8": decode}
    sig["panel"] = dict(status="pending (panel not run)")
    sig["flags"] = S.kv_flags(sig)
    md = S.render_kv(sig)
    assert md.index("## A7 tg1") < md.index("## A8 tg2") < md.index("## A2 / A3 / A4 / M1")
    assert "- A8 s1 (descriptive): treatment / reference" in md and "sensitivity (pre-registered" in md
    assert "HOLD (C339, blocking" in md and "reload control (diagnostic)" in md and "re-check s2" in md
    sig2 = S.kv_sheet_skeleton(("n16", "x"))
    sig2["axes"].update(A1=dict(looks=[], final_look=None), A5=dict(status="pending"), A7=dict(status="pending"))
    sig2["panel"], sig2["flags"] = dict(status="pending (panel not run)"), []
    assert "A8" not in S.render_kv(sig2)                                       # absent → omitted (never "pending")


def test_compute_kv_refuses_a_b8_a8_of_another_b8(tmp_path, monkeypatch):
    w = A8World(tmp_path)
    doc = V.verify_a8_kv(w.root, "b" * 64)
    with pytest.raises(V.RefusalError, match="another B8.json"):
        V.check_b8_a8(w.root.parent, doc, "c" * 64, V.STACK_REPO)          # change review r1 B14: the repo root explicit
    (w.root / "B8-A8.json").write_text(dumps(doc))
    assert json.loads((w.root / "B8-A8.json").read_text())["base_b8_sha256"] == "b" * 64
