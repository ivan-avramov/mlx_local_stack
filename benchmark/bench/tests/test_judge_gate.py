"""Tests for the M38 judge-panel reliability gate + ranking (bench.judge_gate)."""
import json

import bench.judge_gate as G

JUDGES = ["j1", "j2", "j3"]


# ------------------------------------------------------------------------------- Cohen's kappa
def test_cohen_kappa_perfect_agreement():
    assert G.cohen_kappa(["A", "B", "tie", "A"], ["A", "B", "tie", "A"]) == 1.0


def test_cohen_kappa_known_value():
    kappa = G.cohen_kappa(["A", "B", "tie", "A", "A", "A"], ["A", "B", "tie", "B", "B", "B"])
    assert abs(kappa - 1 / 3) < 1e-9


def test_cohen_kappa_empty_returns_none():
    assert G.cohen_kappa([], []) is None


def test_cohen_kappa_length_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        G.cohen_kappa(["A"], ["A", "B"])


# --------------------------------------------------------------------------- Krippendorff alpha
def test_krippendorff_alpha_hand_verified_example():
    units = {"u1": ["A", "A"], "u2": ["A", "B"], "u3": ["B", "B"]}
    alpha = G.krippendorff_alpha(units)
    assert abs(alpha - 4 / 9) < 1e-9


def test_krippendorff_alpha_perfect_agreement():
    units = {"u1": ["A", "A", "A"], "u2": ["B", "B", "B"],
             "u3": ["tie", "tie", "tie"], "u4": ["A", "A", "A"]}
    assert G.krippendorff_alpha(units) == 1.0


def test_krippendorff_alpha_low_when_judges_disagree():
    units = {f"u{i}": ["A", "B", "tie"] for i in range(4)}
    assert G.krippendorff_alpha(units) < 0.5


def test_krippendorff_alpha_drops_missing_and_excludes_unpairable_units():
    # u2 has only one valid value (None dropped) -> excluded entirely, not counted as 0 or 1.
    units = {"u1": ["A", "A"], "u2": ["A", None], "u3": ["B", "B"]}
    a_with = G.krippendorff_alpha({"u1": ["A", "A"], "u3": ["B", "B"]})
    a_full = G.krippendorff_alpha(units)
    assert a_with == a_full


def test_krippendorff_alpha_no_pairable_data_returns_none():
    assert G.krippendorff_alpha({"u1": ["A"], "u2": [None, None]}) is None


# ------------------------------------------------------------------------ compute_gate helpers
def _rows_for_pair(pair_id, judges, raw_ab, raw_ba):
    """raw_ab/raw_ba: a single choice applied to every judge, or {judge: choice}."""
    rows = []
    for j in judges:
        ab = raw_ab[j] if isinstance(raw_ab, dict) else raw_ab
        ba = raw_ba[j] if isinstance(raw_ba, dict) else raw_ba
        rows.append({"pair_id": pair_id, "order": "AB", "judge": j, "choice": ab})
        rows.append({"pair_id": pair_id, "order": "BA", "judge": j, "choice": ba})
    return rows


def _agree(pair_id, judges, winner):
    """All judges agree across both orders on `winner` ("A"/"B"/"tie") -> zero flips."""
    raw = {"A": ("A", "B"), "B": ("B", "A"), "tie": ("tie", "tie")}[winner]
    return _rows_for_pair(pair_id, judges, raw[0], raw[1])


def _anchor_pair(pair_id, anchor_type, expected, item_id=None):
    return {"pair_id": pair_id, "anchor_type": anchor_type, "item_id": item_id or pair_id,
            "a_key": "x::orig", "b_key": "x::xform", "a_text": "a", "b_text": "b",
            "expected": expected}


# ------------------------------------------------------------------------- degrade_accuracy
def test_gate_degrade_accuracy_pass():
    pairs = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    rows = []
    for p in pairs:
        rows += _agree(p["pair_id"], JUDGES, "A")
    gate = G.compute_gate(pairs, rows, JUDGES)
    m = gate["metrics"]["degrade_accuracy"]
    assert m["value"] == 1.0 and m["pass"] is True


def test_gate_degrade_accuracy_fail():
    pairs = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    rows = []
    for p in pairs:
        rows += _agree(p["pair_id"], JUDGES, "B")   # panel always picks B, expected was A
    gate = G.compute_gate(pairs, rows, JUDGES)
    m = gate["metrics"]["degrade_accuracy"]
    assert m["value"] == 0.0 and m["pass"] is False


# ------------------------------------------------------------------------- order_flip_rate
# -------------------------------------------------------- F9: order_is_flip mutant coverage
def test_order_is_flip_treats_unparsed_as_flip_not_agreement():
    """A mutant that treats an unparsed (None) order as "not a flip" would silently let a
    judge whose responses never parse read as perfectly order-consistent — the opposite of
    what the reliability gate exists to catch."""
    both_present_agree = {("AB", "j1"): "A", ("BA", "j1"): "B"}   # normalizes to A/A -> no flip
    assert G.order_is_flip(both_present_agree, "j1") is False

    one_missing = {("AB", "j1"): "A"}                              # BA never parsed -> None
    assert G.order_is_flip(one_missing, "j1") is True

    other_missing = {("BA", "j1"): "B"}                             # AB never parsed -> None
    assert G.order_is_flip(other_missing, "j1") is True

    both_missing = {}
    assert G.order_is_flip(both_missing, "j1") is True


def test_gate_order_flip_rate_pass():
    pairs = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    rows = []
    for p in pairs:
        rows += _agree(p["pair_id"], JUDGES, "A")
    gate = G.compute_gate(pairs, rows, JUDGES)
    m = gate["metrics"]["order_flip_rate"]
    assert m["worst"] == 0.0 and m["pass"] is True


def test_gate_order_flip_rate_fail_isolated_from_degrade_accuracy():
    pairs = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    rows = []
    for i, p in enumerate(pairs):
        if i < 4:
            # j1 flips (raw AB="A", raw BA="A" -> normalized BA="B" -> disagreement);
            # j2/j3 still agree "A" -> panel majority stays "A" (2 of 3 votes).
            rows += _rows_for_pair(p["pair_id"], ["j1"], "A", "A")
            rows += _agree(p["pair_id"], ["j2", "j3"], "A")
        else:
            rows += _agree(p["pair_id"], JUDGES, "A")
    gate = G.compute_gate(pairs, rows, JUDGES)
    assert gate["metrics"]["degrade_accuracy"]["value"] == 1.0   # unaffected
    flip = gate["metrics"]["order_flip_rate"]
    assert flip["value"]["j1"] == 0.4 and flip["worst"] == 0.4
    assert flip["pass"] is False


# --------------------------------------------------------------------- panel_kappa_between_orders
def test_gate_panel_kappa_pass_on_full_agreement():
    pairs = [_anchor_pair("d0", "degrade", "A"), _anchor_pair("d1", "degrade", "B"),
             _anchor_pair("d2", "degrade", "tie")]
    rows = (_agree("d0", JUDGES, "A") + _agree("d1", JUDGES, "B") + _agree("d2", JUDGES, "tie"))
    gate = G.compute_gate(pairs, rows, JUDGES)
    m = gate["metrics"]["panel_kappa_between_orders"]
    assert m["value"] == 1.0 and m["pass"] is True


def test_gate_panel_kappa_fail_when_orders_disagree():
    pairs = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(6)]
    rows = []
    for i, p in enumerate(pairs):
        if i < 3:
            rows += _agree(p["pair_id"], JUDGES, ["A", "B", "tie"][i])
        else:
            # raw AB="A" and raw BA="A" (unflipped) for every judge -> normalized BA="B" ->
            # panel_ab majority "A", panel_ba majority "B": the two orders' panels disagree.
            rows += _rows_for_pair(p["pair_id"], JUDGES, "A", "A")
    gate = G.compute_gate(pairs, rows, JUDGES)
    m = gate["metrics"]["panel_kappa_between_orders"]
    assert m["value"] < G.THRESHOLDS["panel_kappa_between_orders"]
    assert m["pass"] is False


# --------------------------------------------------------------------------- krippendorff_alpha
def test_gate_krippendorff_alpha_pass_on_full_agreement():
    pairs = [_anchor_pair("d0", "degrade", "A"), _anchor_pair("d1", "degrade", "B"),
             _anchor_pair("d2", "degrade", "tie"), _anchor_pair("d3", "degrade", "A")]
    rows = sum((_agree(p["pair_id"], JUDGES, w) for p, w in
                zip(pairs, ["A", "B", "tie", "A"])), [])
    gate = G.compute_gate(pairs, rows, JUDGES)
    m = gate["metrics"]["krippendorff_alpha"]
    assert m["value"] == 1.0 and m["pass"] is True


def test_gate_krippendorff_alpha_fail_when_judges_disagree():
    # every judge lands on a DIFFERENT per-pair verdict -> judges disagree with each other.
    pairs = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(4)]
    rows = []
    for p in pairs:
        rows += _rows_for_pair(p["pair_id"], ["j1"], "A", "B")    # j1 -> "A"
        rows += _rows_for_pair(p["pair_id"], ["j2"], "B", "A")    # j2 -> "B"
        rows += _rows_for_pair(p["pair_id"], ["j3"], "tie", "tie")  # j3 -> "tie"
    gate = G.compute_gate(pairs, rows, JUDGES)
    m = gate["metrics"]["krippendorff_alpha"]
    assert m["value"] < G.THRESHOLDS["krippendorff_alpha"]
    assert m["pass"] is False


# ---------------------------------------------------------- F7: raw vs order-collapsed alpha
def test_gate_krippendorff_alpha_raw_catches_flips_collapsed_hides_them():
    # every judge FLIPS on every pair (raw AB="A", raw BA="A" -> normalized BA="B"): the
    # order-collapsed view folds every judge's disagreement into "tie", which reads as
    # perfect judge-to-judge agreement (alpha_collapsed == 1.0) even though the panel is
    # unreliable. The gate must be thresholded on alpha_raw, which sees the flip.
    pairs = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(6)]
    rows = []
    for p in pairs:
        rows += _rows_for_pair(p["pair_id"], JUDGES, "A", "A")   # unflipped raw -> BA norm "B"
    gate = G.compute_gate(pairs, rows, JUDGES)
    m = gate["metrics"]["krippendorff_alpha"]
    assert m["alpha_collapsed"] == 1.0
    assert m["alpha_raw"] < G.THRESHOLDS["krippendorff_alpha"]
    assert m["value"] == m["alpha_raw"]        # the gate's "value" IS alpha_raw
    assert m["pass"] is False                  # gated on alpha_raw, not the misleading collapsed one


def test_krippendorff_units_raw_has_twice_the_raters_of_collapsed():
    pairs = [_anchor_pair("d0", "degrade", "A")]
    rows = _agree("d0", JUDGES, "A")
    verdicts_by_pair = G.group_verdicts_by_pair(rows)
    collapsed = G.krippendorff_units_collapsed(pairs, verdicts_by_pair, JUDGES)
    raw = G.krippendorff_units_raw(pairs, verdicts_by_pair, JUDGES)
    assert len(collapsed["d0"]) == len(JUDGES)
    assert len(raw["d0"]) == 2 * len(JUDGES)


# ---------------------------------------------------------------- verbosity / identity metrics
def test_gate_verbosity_longer_preference_rate_direct():
    """Spec correction 2026-09-12: length bias = preferring the PADDED copy. Preferring the
    original (expected side) is correct and must never fail the check; ties are not bias."""
    verbosity_pairs = [_anchor_pair(f"v{i}", "verbosity", "A") for i in range(10)]
    rows = []
    for p in verbosity_pairs:
        rows += _agree(p["pair_id"], JUDGES, "A")            # always the original -> 0.0 bias
    gate = G.compute_gate(verbosity_pairs, rows, JUDGES)
    m = gate["metrics"]["verbosity_longer_preference_rate"]
    assert m["value"] == 0.0 and m["threshold"] == 0.10 and m["pass"] is True
    assert m["diagnostic_shorter_preference_rate"] == 1.0

    rows2 = []
    for i, p in enumerate(verbosity_pairs):
        rows2 += _agree(p["pair_id"], JUDGES, "B" if i < 2 else "A")   # 2/10 prefer padded
    gate2 = G.compute_gate(verbosity_pairs, rows2, JUDGES)
    m2 = gate2["metrics"]["verbosity_longer_preference_rate"]
    assert m2["value"] == 0.2 and m2["pass"] is False

    rows3 = []
    for i, p in enumerate(verbosity_pairs):
        rows3 += _agree(p["pair_id"], JUDGES, "tie" if i < 5 else "A")  # ties are not bias
    m3 = G.compute_gate(verbosity_pairs, rows3, JUDGES)["metrics"]["verbosity_longer_preference_rate"]
    assert m3["value"] == 0.0 and m3["pass"] is True


def test_gate_identity_tie_rate_pass_and_fail():
    pairs = [_anchor_pair(f"i{i}", "identity", "tie") for i in range(10)]
    rows_pass = []
    for i, p in enumerate(pairs):
        rows_pass += _agree(p["pair_id"], JUDGES, "tie" if i < 9 else "A")   # 0.9 >= 0.8
    gate = G.compute_gate(pairs, rows_pass, JUDGES)
    assert gate["metrics"]["identity_tie_rate"]["value"] == 0.9
    assert gate["metrics"]["identity_tie_rate"]["pass"] is True

    rows_fail = []
    for i, p in enumerate(pairs):
        rows_fail += _agree(p["pair_id"], JUDGES, "tie" if i < 5 else "A")   # 0.5 < 0.8
    gate2 = G.compute_gate(pairs, rows_fail, JUDGES)
    assert gate2["metrics"]["identity_tie_rate"]["pass"] is False


# ----------------------------------------------------------------------------------- overall
def test_gate_overall_pass_when_every_metric_passes():
    degrade = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    verbosity = [_anchor_pair(f"v{i}", "verbosity", "A") for i in range(10)]
    identity = [_anchor_pair(f"t{i}", "identity", "tie") for i in range(10)]
    pairs = degrade + verbosity + identity
    rows = []
    for p in degrade:
        rows += _agree(p["pair_id"], JUDGES, "A")
    for p in verbosity:
        rows += _agree(p["pair_id"], JUDGES, "A")
    for p in identity:
        rows += _agree(p["pair_id"], JUDGES, "tie")
    gate = G.compute_gate(pairs, rows, JUDGES)
    assert gate["overall"] == "PASS"
    assert all(m["pass"] for m in gate["metrics"].values())


def test_gate_overall_fail_if_any_single_metric_fails():
    degrade = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    verbosity = [_anchor_pair(f"v{i}", "verbosity", "A") for i in range(10)]
    identity = [_anchor_pair(f"t{i}", "identity", "tie") for i in range(10)]
    pairs = degrade + verbosity + identity
    rows = []
    for p in degrade:
        rows += _agree(p["pair_id"], JUDGES, "A")
    for p in verbosity:
        rows += _agree(p["pair_id"], JUDGES, "A")
    for i, p in enumerate(identity):
        rows += _agree(p["pair_id"], JUDGES, "tie" if i < 5 else "A")   # identity fails (0.5)
    gate = G.compute_gate(pairs, rows, JUDGES)
    assert gate["overall"] == "FAIL"
    assert gate["metrics"]["identity_tie_rate"]["pass"] is False


# --------------------------------------------------------------------------------- ranking
def _candidate_pair(i, winner):
    return {"pair_id": f"cand-{i}", "anchor_type": None, "item_id": f"dom-{i}",
            "a_key": f"Alpha::dom-{i}", "b_key": f"Beta::dom-{i}",
            "a_text": "a", "b_text": "b", "expected": None}


def test_compute_ranking_known_preference_rate():
    winners = ["A"] * 16 + ["tie"] * 2 + ["B"] * 2
    pairs = [_candidate_pair(i, w) for i, w in enumerate(winners)]
    rows = []
    for p, w in zip(pairs, winners):
        rows += _agree(p["pair_id"], JUDGES, w)
    ranking = G.compute_ranking(pairs, rows, JUDGES, seed=0)
    key = "Alpha__Beta"
    assert key in ranking["pairs"]
    r = ranking["pairs"][key]
    assert abs(r["preference_rate_model_1"] - 0.85) < 1e-9
    assert r["n_items"] == 20
    assert r["verdict"] == "m1_better"
    assert r["mde"] > 0
    assert "p_holm" in r


def test_compute_ranking_equivalent_when_rate_near_half():
    winners = ["A"] * 10 + ["B"] * 10
    pairs = [_candidate_pair(i, w) for i, w in enumerate(winners)]
    rows = []
    for p, w in zip(pairs, winners):
        rows += _agree(p["pair_id"], JUDGES, w)
    ranking = G.compute_ranking(pairs, rows, JUDGES, seed=0)
    r = ranking["pairs"]["Alpha__Beta"]
    assert abs(r["preference_rate_model_1"] - 0.5) < 1e-9
    assert r["verdict"] in ("equivalent_95ci_within_5pp", "inconclusive")


# --------------------------------------------------------- F9: TOST-branch mutant coverage
def test_compute_ranking_deterministic_tie_is_equivalent_not_inconclusive():
    """All items tie -> every bootstrap replicate is also exactly 0.5 (zero variance), so the
    CI is a single point strictly inside +-5pp. This is DETERMINISTIC (unlike the mixed-winner
    case above, which can land on either side of the margin) — a test that would fail outright
    if the TOST equivalence branch were ever deleted (verdict would fall through to
    "inconclusive" instead)."""
    winners = ["tie"] * 20
    pairs = [_candidate_pair(i, w) for i, w in enumerate(winners)]
    rows = []
    for p, w in zip(pairs, winners):
        rows += _agree(p["pair_id"], JUDGES, w)
    ranking = G.compute_ranking(pairs, rows, JUDGES, seed=0)
    r = ranking["pairs"]["Alpha__Beta"]
    assert r["preference_rate_model_1"] == 0.5
    assert r["ci"] == [0.5, 0.5]
    assert r["verdict"] == "equivalent_95ci_within_5pp"


# ------------------------------------------------------------- F9: stats.holm mutant coverage
def _candidate_pair_named(pair_id, item_id, model_a, model_b, winner):
    return {"pair_id": pair_id, "anchor_type": None, "item_id": item_id,
            "a_key": f"{model_a}::{item_id}", "b_key": f"{model_b}::{item_id}",
            "a_text": "a", "b_text": "b", "expected": None}


def test_compute_ranking_holm_adjusts_pvalues_across_pairs():
    """3 models -> 3 pairs, one with an overwhelming, unambiguous winner (tiny raw p) and two
    near coin-flips (raw p close to 1). Holm must inflate the smallest raw p by multiplying by
    its rank weight — asserting p_holm != p_value (and p_holm >= p_value) for that pair fails
    outright if `stats.holm` were ever replaced by an identity function."""
    pairs, rows = [], []
    # Alpha vs Beta: Alpha wins every one of 20 items -> tiny p-value.
    for i in range(20):
        p = _candidate_pair_named(f"ab-{i}", f"item-ab-{i}", "Alpha", "Beta", "A")
        pairs.append(p)
        rows += _agree(p["pair_id"], JUDGES, "A")
    # Alpha vs Gamma, Beta vs Gamma: near coin-flips -> raw p close to 1.
    for pair_name, (m1, m2) in [("ag", ("Alpha", "Gamma")), ("bg", ("Beta", "Gamma"))]:
        for i in range(20):
            winner = "A" if i % 2 == 0 else "B"
            p = _candidate_pair_named(f"{pair_name}-{i}", f"item-{pair_name}-{i}", m1, m2, winner)
            pairs.append(p)
            rows += _agree(p["pair_id"], JUDGES, winner)

    ranking = G.compute_ranking(pairs, rows, JUDGES, seed=0)
    winner_pair = ranking["pairs"]["Alpha__Beta"]
    assert winner_pair["p_value"] < 0.01
    assert winner_pair["p_holm"] >= winner_pair["p_value"]
    assert winner_pair["p_holm"] != winner_pair["p_value"]
    for key, r in ranking["pairs"].items():
        assert r["p_holm"] >= r["p_value"]   # Holm never makes a p-value SMALLER


# ------------------------------------------------------------------------------- usage_summary
def test_usage_summary_computes_means_and_runaway_share():
    rows_by_model = {"Alpha": [
        {"completion_tokens": 100, "wall_s": 10.0, "nonconv_kind": None},
        {"completion_tokens": 300, "wall_s": 30.0, "nonconv_kind": "repetition"},
    ]}
    out = G.usage_summary(rows_by_model)
    assert out["Alpha"]["tokens_per_task"] == 200
    assert out["Alpha"]["latency_s"] == 20.0
    assert out["Alpha"]["runaway_share"] == 0.5
    assert out["Alpha"]["n"] == 2


# ------------------------------------------------------------------------------------ main CLI
def _write_jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_main_gate_pass_writes_ranking(tmp_path):
    degrade = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    verbosity = [_anchor_pair(f"v{i}", "verbosity", "A") for i in range(10)]
    identity = [_anchor_pair(f"t{i}", "identity", "tie") for i in range(10)]
    winners = ["A"] * 16 + ["tie"] * 2 + ["B"] * 2
    candidates = [_candidate_pair(i, w) for i, w in enumerate(winners)]
    pairs = degrade + verbosity + identity + candidates
    rows = []
    for p in degrade:
        rows += _agree(p["pair_id"], JUDGES, "A")
    for p in verbosity:
        rows += _agree(p["pair_id"], JUDGES, "A")
    for p in identity:
        rows += _agree(p["pair_id"], JUDGES, "tie")
    for p, w in zip(candidates, winners):
        rows += _agree(p["pair_id"], JUDGES, w)

    pairs_path = tmp_path / "pairs.jsonl"
    verdicts_path = tmp_path / "verdicts.jsonl"
    _write_jsonl(pairs_path, pairs)
    _write_jsonl(verdicts_path, rows)
    out = tmp_path / "out"

    rc = G.main(["--pairs", str(pairs_path), "--verdicts", str(verdicts_path),
                "--judges", *JUDGES, "--out", str(out)])
    assert rc == 0
    gate = json.load(open(out / "gate.json"))
    assert gate["overall"] == "PASS"
    ranking = json.load(open(out / "ranking.json"))
    assert "Alpha__Beta" in ranking["pairs"]


def test_main_gate_fail_refuses_ranking(tmp_path):
    degrade = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    rows = []
    for p in degrade:
        rows += _agree(p["pair_id"], JUDGES, "B")   # degrade_accuracy = 0.0 -> gate FAILs

    pairs_path = tmp_path / "pairs.jsonl"
    verdicts_path = tmp_path / "verdicts.jsonl"
    _write_jsonl(pairs_path, degrade)
    _write_jsonl(verdicts_path, rows)
    out = tmp_path / "out"

    rc = G.main(["--pairs", str(pairs_path), "--verdicts", str(verdicts_path),
                "--judges", *JUDGES, "--out", str(out)])
    assert rc == 1
    gate = json.load(open(out / "gate.json"))
    assert gate["overall"] == "FAIL"
    assert not (out / "ranking.json").exists()


# ------------------------------------------------------------ null-verdict visibility follow-up
# A truncated/refused judge call (choice:null with null_reason) is graded as BOTH a tie (0.5,
# via panel_verdict) and an order flip (via order_is_flip) — documented intent, previously
# invisible. null_verdict_stats + the gate's "null_verdicts" block + main()'s WARN line surface
# it so a client-side max_tokens/output_config regression cannot silently fail the gate.
def _null_row(pair_id, judge, order, null_reason=None):
    return {"pair_id": pair_id, "order": order, "judge": judge, "choice": None,
            "null_reason": null_reason}


def test_null_verdict_stats_counts_by_judge_and_reason():
    anchors = [_anchor_pair("d0", "degrade", "A"), _anchor_pair("d1", "degrade", "A")]
    rows = (
        _agree("d0", JUDGES, "A")                                   # all clean, no nulls
        + [_null_row("d1", "j1", "AB", "max_tokens"), _null_row("d1", "j1", "BA", "max_tokens")]
        + [_null_row("d1", "j2", "AB", "refusal"), _null_row("d1", "j2", "BA", "refusal")]
        + [_null_row("d1", "j3", "AB"), _null_row("d1", "j3", "BA")]   # no reason -> unparseable
    )
    stats = G.null_verdict_stats(anchors, rows, JUDGES)
    assert stats["by_judge"] == {"j1": 2, "j2": 2, "j3": 2}
    assert stats["by_reason"] == {"max_tokens": 2, "refusal": 2, "unparseable": 2}
    assert stats["n_null"] == 6


def test_null_verdict_stats_share_overall_and_per_judge():
    anchors = [_anchor_pair("d0", "degrade", "A")]
    # 1 pair * 3 judges * 2 orders = 6 anchor verdict rows; only j1's BA call is null.
    rows = _agree("d0", ["j2", "j3"], "A") + [
        {"pair_id": "d0", "order": "AB", "judge": "j1", "choice": "A"},
        _null_row("d0", "j1", "BA", "max_tokens"),
    ]
    stats = G.null_verdict_stats(anchors, rows, JUDGES)
    assert stats["n_anchor_rows"] == 6
    assert stats["n_null"] == 1
    assert abs(stats["share"] - (1 / 6)) < 1e-9
    assert stats["by_judge_share"]["j1"] == 0.5   # 1 of j1's 2 rows
    assert stats["by_judge_share"]["j2"] == 0.0
    assert stats["by_judge_share"]["j3"] == 0.0


def test_null_verdict_stats_no_anchor_rows_is_none_share():
    stats = G.null_verdict_stats([], [], JUDGES)
    assert stats["n_anchor_rows"] == 0
    assert stats["share"] is None
    assert all(v is None for v in stats["by_judge_share"].values())


def test_compute_gate_includes_null_verdicts_block():
    pairs = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    rows = []
    for i, p in enumerate(pairs):
        if i == 0:
            rows += [{"pair_id": p["pair_id"], "order": "AB", "judge": "j1", "choice": "A"},
                     _null_row(p["pair_id"], "j1", "BA", "max_tokens")]
            rows += _agree(p["pair_id"], ["j2", "j3"], "A")
        else:
            rows += _agree(p["pair_id"], JUDGES, "A")
    gate = G.compute_gate(pairs, rows, JUDGES)
    nv = gate["null_verdicts"]
    assert nv["by_judge"]["j1"] == 1
    assert nv["by_reason"]["max_tokens"] == 1
    assert nv["n_anchor_rows"] == 10 * 3 * 2


# -------------------------------------------------------------------------- main() WARN on null
def test_main_warns_when_judge_null_share_exceeds_5pct(tmp_path, capsys):
    # 10 anchors * 2 orders = 20 rows for j1; null out 2 of them (10%) -> exceeds 5%.
    degrade = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    rows = []
    for i, p in enumerate(degrade):
        if i < 2:
            rows += [_null_row(p["pair_id"], "j1", "AB", "max_tokens"),
                     _null_row(p["pair_id"], "j1", "BA", "max_tokens")]
            rows += _agree(p["pair_id"], ["j2", "j3"], "A")
        else:
            rows += _agree(p["pair_id"], JUDGES, "A")
    pairs_path, verdicts_path = tmp_path / "pairs.jsonl", tmp_path / "verdicts.jsonl"
    _write_jsonl(pairs_path, degrade)
    _write_jsonl(verdicts_path, rows)
    G.main(["--pairs", str(pairs_path), "--verdicts", str(verdicts_path),
           "--judges", *JUDGES, "--out", str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert "WARN" in captured.out
    assert "j1" in captured.out


def test_main_no_warn_when_null_share_under_threshold(tmp_path, capsys):
    degrade = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    rows = []
    for p in degrade:
        rows += _agree(p["pair_id"], JUDGES, "A")   # zero nulls anywhere
    pairs_path, verdicts_path = tmp_path / "pairs.jsonl", tmp_path / "verdicts.jsonl"
    _write_jsonl(pairs_path, degrade)
    _write_jsonl(verdicts_path, rows)
    G.main(["--pairs", str(pairs_path), "--verdicts", str(verdicts_path),
           "--judges", *JUDGES, "--out", str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert "WARN" not in captured.out


# --------------------------------------------------------- reviewer follow-up: missing asserts
def test_compute_ranking_p_value_method_present():
    winners = ["A"] * 16 + ["tie"] * 2 + ["B"] * 2
    pairs = [_candidate_pair(i, w) for i, w in enumerate(winners)]
    rows = []
    for p, w in zip(pairs, winners):
        rows += _agree(p["pair_id"], JUDGES, w)
    ranking = G.compute_ranking(pairs, rows, JUDGES, seed=0)
    r = ranking["pairs"]["Alpha__Beta"]
    assert r["p_value_method"] == G.P_VALUE_METHOD


def test_main_gate_pass_writes_usage_into_ranking_via_models_flag(tmp_path):
    degrade = [_anchor_pair(f"d{i}", "degrade", "A") for i in range(10)]
    verbosity = [_anchor_pair(f"v{i}", "verbosity", "A") for i in range(10)]
    identity = [_anchor_pair(f"t{i}", "identity", "tie") for i in range(10)]
    winners = ["A"] * 16 + ["tie"] * 2 + ["B"] * 2
    candidates = [_candidate_pair(i, w) for i, w in enumerate(winners)]
    pairs = degrade + verbosity + identity + candidates
    rows = []
    for p in degrade:
        rows += _agree(p["pair_id"], JUDGES, "A")
    for p in verbosity:
        rows += _agree(p["pair_id"], JUDGES, "A")
    for p in identity:
        rows += _agree(p["pair_id"], JUDGES, "tie")
    for p, w in zip(candidates, winners):
        rows += _agree(p["pair_id"], JUDGES, w)

    results_dir = tmp_path / "results"
    for model in ("Alpha", "Beta"):
        d = results_dir / model
        d.mkdir(parents=True)
        with open(d / "cjudge.m38.jsonl", "w") as f:
            f.write(json.dumps({"id": "dom-00", "completion_tokens": 100, "wall_s": 10.0,
                                "nonconv_kind": None, "converged": True}) + "\n")

    pairs_path, verdicts_path = tmp_path / "pairs.jsonl", tmp_path / "verdicts.jsonl"
    _write_jsonl(pairs_path, pairs)
    _write_jsonl(verdicts_path, rows)
    out = tmp_path / "out"

    rc = G.main(["--pairs", str(pairs_path), "--verdicts", str(verdicts_path),
                "--judges", *JUDGES, "--out", str(out),
                "--models", "Alpha", "Beta", "--results-dir", str(results_dir)])
    assert rc == 0
    ranking = json.load(open(out / "ranking.json"))
    assert "usage" in ranking
    assert ranking["usage"]["Alpha"]["tokens_per_task"] == 100
    assert ranking["usage"]["Beta"]["n"] == 1
