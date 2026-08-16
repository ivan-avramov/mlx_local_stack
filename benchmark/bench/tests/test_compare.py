"""`compare` — refuse the comparison, or report it with its resolution. Never a bare delta.

Every head-to-head in the campaign so far mixed something: N (aider 5 vs 16 vs 34), item subsets
(the distill's first-16 vs Ornith's harder 34), boxes, or budgets. The load-bearing agentic
comparison — distill 75% vs Ornith 61.8% — is not matched-item-set, and the doc says so while
still ranking on it.

The comparability rules encode which mismatches are FATAL and which are the intended design:
  * different item-id sets            -> fatal (this is the defect being fixed)
  * different thinking_budget/max_tokens -> fatal (strict-style metrics move with the budget)
  * different box, for a speed/memory metric -> fatal (the apples-to-apples rule)
  * different APC state               -> fatal for speed, fine for quality
  * DIFFERENT per-model temperature   -> EXPECTED, never fatal. Ornith runs t0.4 and the distill
    t0.3 because those are each model's tuned operating point; a rule that demanded equal
    sampling would refuse every comparison the campaign actually needs.
"""
import bench.compare as CMP
import bench.generate as G


def _rows(ids, *, ok=True, samples=1, budget=16384, ct=100):
    out = []
    for i in ids:
        for s in range(samples):
            hit = ok if isinstance(ok, bool) else (i in ok)
            out.append({"id": i, "sample": s, "schema_version": 2,
                        "content": r"\boxed{42}" if hit else r"\boxed{7}",
                        "answer_gold": "42", "completion_tokens": ct,
                        "thinking_budget": budget, "finish_reason": "stop"})
    return out


def _manifest(tmp, model, bench, *, temp=0.4, budget=16384, box="M2", apc="0"):
    p = G.result_path(model, bench).with_suffix(".manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps({
        "box": box, "sampling_profile": "deployed", "fingerprint_version": 2,
        "sampling": {"temperature": temp, "thinking_budget": budget, "max_tokens": 102400},
        "kv": {"kv_bits": 4}, "runtime": {"apc_enabled": apc}}))


# --------------------------------------------------------------------- refusals
def test_refuses_when_item_sets_differ(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a", "b", "c"]))
    write_rows("B", "math500", _rows(["a", "b", "d"]))
    _manifest(tmp_results, "A", "math500"); _manifest(tmp_results, "B", "math500")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False
    assert "item" in r["reason"] and ("c" in r["reason"] or "d" in r["reason"])


def test_intersect_pairs_a_nested_item_set_instead_of_refusing(write_rows, tmp_results):
    """Opt-in `intersect` for the NESTED case, which the campaign actually hit.

    Nemotron's ifeval run covers 200 items; Ornith's covers those 200 plus 341 more, and the
    distill's 148 are a subset of Nemotron's. So three completed, individually valid runs produced
    ZERO usable head-to-heads: the refusal is correct by default (an unmatched comparison is the
    defect it exists to prevent) but there is a genuine matched comparison available on the
    intersection, and AGENTS.md already REQUIRES intersection pairing for the converged metric.
    Without this, hours of worker time sit unusable for want of a set operation.
    """
    write_rows("A", "math500", _rows(["a", "b", "c", "d"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500"); _manifest(tmp_results, "B", "math500")

    assert CMP.compare("A", "B", "math500")["comparable"] is False   # default stays a refusal

    r = CMP.compare("A", "B", "math500", intersect=True)
    assert r["comparable"] is True
    assert r["n_items"] == 2, "must pair on the 2 shared items, not 4"
    assert r["mde"] == __import__("bench.stats", fromlist=["x"]).mde(2)
    joined = " ".join(r["warnings"])
    assert "intersect" in joined.lower()
    assert "2" in joined and "c" not in r.get("reason", "")
    # The dropped count must be stated, or a reader cannot tell how much was discarded.
    assert "dropped" in joined.lower()


def test_intersect_still_refuses_a_budget_mismatch(write_rows, tmp_results):
    """`intersect` relaxes ONE rule. It must not become a general override.

    The budget guard is what keeps acc_strict honest across rows, and the campaign holds rows at
    16384/32768/81920 — so an `intersect` that also waived it would silently enable exactly the
    cross-budget comparison acc_strict's ranking status depends on being impossible.
    """
    write_rows("A", "math500", _rows(["a", "b"], budget=16384))
    write_rows("B", "math500", _rows(["a", "b"], budget=81920))
    _manifest(tmp_results, "A", "math500", budget=16384)
    _manifest(tmp_results, "B", "math500", budget=81920)
    r = CMP.compare("A", "B", "math500", intersect=True)
    assert r["comparable"] is False
    assert "budget" in r["reason"]


def test_intersect_refuses_when_there_is_no_overlap(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["c", "d"]))
    _manifest(tmp_results, "A", "math500"); _manifest(tmp_results, "B", "math500")
    r = CMP.compare("A", "B", "math500", intersect=True)
    assert r["comparable"] is False
    assert "no shared items" in r["reason"].lower() or "shared" in r["reason"].lower()


def test_refuses_when_thinking_budget_differs(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a", "b"], budget=16384))
    write_rows("B", "math500", _rows(["a", "b"], budget=81920))
    _manifest(tmp_results, "A", "math500", budget=16384)
    _manifest(tmp_results, "B", "math500", budget=81920)
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "budget" in r["reason"]


def test_refuses_a_speed_metric_across_boxes(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500", box="M2")
    _manifest(tmp_results, "B", "math500", box="M5")
    assert CMP.compare("A", "B", "math500", metric="decode_tps")["comparable"] is False
    # ...but a QUALITY metric is box-independent, so the same pair compares fine.
    assert CMP.compare("A", "B", "math500")["comparable"] is True


def test_refuses_when_a_manifest_is_missing(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a"]))
    write_rows("B", "math500", _rows(["a"]))
    _manifest(tmp_results, "A", "math500")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "provenance" in r["reason"]


def test_refuses_when_one_side_has_no_rows(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a"]))
    _manifest(tmp_results, "A", "math500")
    assert CMP.compare("A", "B", "math500")["comparable"] is False


# --------------------------------------------------------------------- the intended design
def test_different_per_model_temperature_is_fine(write_rows, tmp_results):
    """Ornith t0.4 vs distill t0.3 are the tuned operating points, not a confound."""
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500", temp=0.4)
    _manifest(tmp_results, "B", "math500", temp=0.3)
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is True
    assert any("temperature" in w for w in r["warnings"]), "recorded as a note, not a refusal"


def test_apc_difference_warns_for_quality_and_refuses_for_speed(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500", apc="0")
    _manifest(tmp_results, "B", "math500", apc="1")
    assert CMP.compare("A", "B", "math500")["comparable"] is True
    assert CMP.compare("A", "B", "math500", metric="decode_tps")["comparable"] is False


# --------------------------------------------------------------------- verdicts
def test_a_small_delta_at_n15_is_inconclusive_not_a_ranking(write_rows, tmp_results):
    """The exact situation that produced 'dense 86.7% vs MoE 80%': 1 item of 15."""
    ids = [f"i{j}" for j in range(15)]
    write_rows("A", "math500", _rows(ids, ok=set(ids[:13])))     # 13/15
    write_rows("B", "math500", _rows(ids, ok=set(ids[:12])))     # 12/15
    _manifest(tmp_results, "A", "math500"); _manifest(tmp_results, "B", "math500")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is True
    assert r["delta"]["verdict"] == "inconclusive"
    assert r["mde"] > 0.30, "N=15 cannot resolve better than ~32pp"
    assert r["n_for_margin"] > 100, "and it must say how many items WOULD resolve the margin"


def test_a_large_consistent_delta_is_called(write_rows, tmp_results):
    ids = [f"i{j}" for j in range(20)]
    write_rows("A", "math500", _rows(ids, ok=True))              # 20/20
    write_rows("B", "math500", _rows(ids, ok=set()))             # 0/20
    _manifest(tmp_results, "A", "math500"); _manifest(tmp_results, "B", "math500")
    r = CMP.compare("A", "B", "math500")
    assert r["delta"]["verdict"] == "a_better" and r["delta"]["delta"] > 0.9


def test_identical_single_sample_runs_are_equivalent(write_rows, tmp_results):
    ids = [f"i{j}" for j in range(10)]
    write_rows("A", "math500", _rows(ids, ok=set(ids[:8])))
    write_rows("B", "math500", _rows(ids, ok=set(ids[:8])))
    _manifest(tmp_results, "A", "math500"); _manifest(tmp_results, "B", "math500")
    assert CMP.compare("A", "B", "math500")["delta"]["verdict"] == "equivalent"


def test_pass_at_1_converged_pairs_on_the_intersection(write_rows, tmp_results):
    """Conditioning on convergence conditions on a MODEL-DEPENDENT (easier) subset, so the
    comparison must be paired on the items BOTH models converged on — and say how many that is."""
    ids = ["a", "b", "c"]
    write_rows("A", "math500", _rows(ids))                       # all converge
    rows_b = _rows(ids)
    rows_b[2]["completion_tokens"] = 20000                       # c did not converge for B
    write_rows("B", "math500", rows_b)
    _manifest(tmp_results, "A", "math500"); _manifest(tmp_results, "B", "math500")
    r = CMP.compare("A", "B", "math500", metric="pass_at_1_converged")
    assert r["comparable"] is True
    assert r["n_items"] == 2, "paired on the convergence intersection {a, b}"
    assert any("converged" in w for w in r["warnings"])
