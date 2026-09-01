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
import pytest

import bench.compare as CMP
import bench.generate as G


def _rows(ids, *, ok=True, samples=1, budget=16384, ct=100, pt=500):
    out = []
    for i in ids:
        for s in range(samples):
            hit = ok if isinstance(ok, bool) else (i in ok)
            out.append({"id": i, "sample": s, "schema_version": 2,
                        "content": r"\boxed{42}" if hit else r"\boxed{7}",
                        "answer_gold": "42", "completion_tokens": ct, "prompt_tokens": pt,
                        "thinking_budget": budget, "finish_reason": "stop"})
    return out


def _manifest(tmp, model, bench, *, temp=0.4, budget=16384, box="M2", apc="0", draft=None,
              sampling_extra=None, kv=None, git=None, runtime_extra=None):
    p = G.result_path(model, bench).with_suffix(".manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    sampling = {"temperature": temp, "thinking_budget": budget, "max_tokens": 102400}
    if sampling_extra:
        sampling.update(sampling_extra)
    doc = {
        "box": box, "sampling_profile": "deployed", "fingerprint_version": 2,
        "sampling": sampling,
        "kv": kv if kv is not None else {"kv_bits": 4},
        "runtime": {"apc_enabled": apc, **({"draft_kind": draft} if draft else {}),
                    **(runtime_extra or {})}}
    if git is not None:
        doc["git"] = git
    p.write_text(json.dumps(doc))


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


def test_refuses_across_DRAFT_STATE_for_quality_as_well_as_speed(write_rows, tmp_results):
    """THE refusal that was missing, and the one that let the corpus's central defect through.

    Suffix decoding was ON for exactly the two winners and OFF for every other candidate, so every
    cross-model comparison was a (model x serving-path) composite — and `compare` never objected,
    because it checks box and APC but nothing about draft state. Unlike APC (a cache, fatal only for
    speed), suffix CHANGES THE GENERATED TEXT: ON and OFF are different fixed points at the deployed
    config, measured byte-for-byte by bench/probe_determinism.py. So it is fatal for QUALITY metrics
    too, not just speed.
    """
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500", draft="suffix")
    _manifest(tmp_results, "B", "math500", draft="off")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False, r
    assert "draft" in r["reason"] or "suffix" in r["reason"], r["reason"]
    assert CMP.compare("A", "B", "math500", metric="decode_tps")["comparable"] is False


def test_matched_draft_state_compares_normally(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500", draft="off")
    _manifest(tmp_results, "B", "math500", draft="off")
    assert CMP.compare("A", "B", "math500")["comparable"] is True


def test_an_UNOBSERVED_draft_state_warns_instead_of_refusing(write_rows, tmp_results):
    """Every pre-v3 row on disk has no draft_kind. Refusing on those would make the entire historical
    corpus incomparable overnight — a bigger loss than the composite it would prevent, and the rows
    can still be read with the warning attached. Two OBSERVED, differing values still refuse."""
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500", draft="suffix")
    _manifest(tmp_results, "B", "math500")          # pre-v3: no draft_kind at all
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is True
    assert any("draft" in w for w in r["warnings"]), r["warnings"]


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


def test_refuses_peak_mem_gb_as_a_paired_metric_outright(write_rows, tmp_results):
    """Operator ruling 2026-08-17. Rows persist peak_mem_gb as the server's SESSION-CUMULATIVE
    mx.get_peak_memory (verified monotone non-decreasing across all 8 OFAT arms), so a paired
    per-item delta on it measures process history, not an effect. The gate metric lives in the
    capacity ladder's server_peak_gb, measured per rung on a fresh process. Refused on BOTH sides
    matched or not — there is no admissible pairing of this field.
    """
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500"); _manifest(tmp_results, "B", "math500")
    r = CMP.compare("A", "B", "math500", metric="peak_mem_gb")
    assert r["comparable"] is False
    assert "cumulative" in r["reason"] and "capacity" in r["reason"]


# ----------------------------------------------------- V3 guard parity (2026-08-17)
# The verifier's audit found 18 fingerprint keys `compare` never looked at. The fix is a
# CLASSIFICATION, not a blanket must-match: under the (model, tune) taxonomy each model
# legitimately runs its own tune (temperature, top_p, kv_bits...), so tune axes WARN;
# harness/serving knobs that make a delta non-attributable REFUSE; box-bound structural
# knobs refuse for HARDWARE metrics only. The parity test at the bottom pins the invariant
# that every fingerprint key has exactly one documented home.

def test_refuses_when_enable_thinking_differs(write_rows, tmp_results):
    """Thinking ON is a RULED axis — a side that ran with it off measured a different regime."""
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500", sampling_extra={"enable_thinking": True})
    _manifest(tmp_results, "B", "math500", sampling_extra={"enable_thinking": False})
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "enable_thinking" in r["reason"]


def test_tune_axes_warn_but_never_refuse(write_rows, tmp_results):
    """top_p/top_k/min_p/penalties/kv_bits are per-model TUNE axes, same standing as
    temperature: a rule demanding equality would refuse every comparison the campaign needs."""
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500", sampling_extra={"top_p": 0.95, "top_k": 20},
              kv={"kv_bits": 4})
    _manifest(tmp_results, "B", "math500", sampling_extra={"top_p": 0.9, "top_k": 40},
              kv={"kv_bits": 8})
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is True
    joined = " ".join(r["warnings"])
    assert "top_p" in joined and "top_k" in joined and "kv_bits" in joined


def test_refuses_across_OBSERVED_differing_code_shas_but_not_unrecorded_ones(write_rows, tmp_results):
    """The deployed code is output-determining (measured: 2475 -> 3526 completion tokens on an
    identical prompt across one src/mlx-vlm bump). Two OBSERVED, differing shas refuse; manifests
    that never recorded a git block (the pre-provenance corpus) stay readable with a warning."""
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500",
              git={"submodules": {"src/mlx-vlm": "aaa", "src/mlx-serve": "s1"}})
    _manifest(tmp_results, "B", "math500",
              git={"submodules": {"src/mlx-vlm": "bbb", "src/mlx-serve": "s1"}})
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "mlx-vlm" in r["reason"]
    # unrecorded on both sides -> comparable, warned
    _manifest(tmp_results, "A", "math500")
    _manifest(tmp_results, "B", "math500")
    r2 = CMP.compare("A", "B", "math500")
    assert r2["comparable"] is True
    assert any("code" in w.lower() or "sha" in w.lower() for w in r2["warnings"])


def test_refuses_across_differing_agentic_scaffold_knobs(write_rows, tmp_results):
    """client/edit_format/max_turns/deadline_s/loop_guard are harness knobs, not model tunes:
    aider-diff vs opencode-tools rows measure different protocols (the 3.75-malformed lesson)."""
    write_rows("A", "aider", _rows(["a", "b"]))
    write_rows("B", "aider", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "aider", runtime_extra={"client": "aider", "edit_format": "diff"})
    _manifest(tmp_results, "B", "aider", runtime_extra={"client": "opencode", "edit_format": "tools"})
    r = CMP.compare("A", "B", "aider")
    assert r["comparable"] is False and "client" in r["reason"]


def test_prealloc_and_prefill_step_refuse_hardware_metrics_only(write_rows, tmp_results):
    """kv_prealloc_tokens moved wall-clock measurably (24.7s vs 27.8s OFAT) but is text-invariant,
    so it refuses speed/memory pairings and leaves quality pairings alone (warned for prefill)."""
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500",
              kv={"kv_bits": 4, "kv_prealloc_tokens": 131072, "prefill_step_size": 512})
    _manifest(tmp_results, "B", "math500",
              kv={"kv_bits": 4, "kv_prealloc_tokens": 262144, "prefill_step_size": 512})
    assert CMP.compare("A", "B", "math500", metric="wall_s")["comparable"] is False
    assert CMP.compare("A", "B", "math500")["comparable"] is True


def test_cap_difference_refuses_only_when_the_cap_could_have_BOUND(write_rows, tmp_results):
    """Operator ruling 7: the cap is an EXTERNAL ceiling — rows whose generation never hit
    `max_tokens > cap - prompt` are cap-invariant (the silent 0.8 clamp never engaged), so a
    non-binding cap difference warns instead of refusing. A binding one refuses: the smaller-cap
    side ran at a resolved thinking budget nobody chose."""
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    # binding: max_tokens 102400 > 65536 - prompt  -> refuse
    _manifest(tmp_results, "A", "math500", kv={"kv_bits": 4, "max_kv_cache_size": 65536})
    _manifest(tmp_results, "B", "math500", kv={"kv_bits": 4, "max_kv_cache_size": 131072})
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "cap" in r["reason"].lower()
    # non-binding: max_tokens 16384 fits under both caps at these prompts -> warn only
    _manifest(tmp_results, "A", "math500", kv={"kv_bits": 4, "max_kv_cache_size": 65536},
              sampling_extra={"max_tokens": 16384})
    _manifest(tmp_results, "B", "math500", kv={"kv_bits": 4, "max_kv_cache_size": 131072},
              sampling_extra={"max_tokens": 16384})
    r2 = CMP.compare("A", "B", "math500")
    assert r2["comparable"] is True
    assert any("cap" in w.lower() for w in r2["warnings"])


def test_every_fingerprint_key_is_classified_in_compare_no_silent_gaps():
    """THE parity invariant. `draft_kind` sat in the fingerprint for two versions while nothing
    populated or guarded it — a declared-but-unenforced key reads as covered. This test makes the
    next such gap a red suite instead of a corpus defect: every fingerprinted key must belong to
    exactly one documented tier in `compare`."""
    import bench.provenance as P
    assert set(P._FINGERPRINT_SAMPLING) == set(CMP._MUST_MATCH_SAMPLING) | set(CMP._TUNE_SAMPLING_WARN)
    assert set(CMP._MUST_MATCH_SAMPLING) & set(CMP._TUNE_SAMPLING_WARN) == set()
    assert set(P._FINGERPRINT_RUNTIME) == set(CMP._MUST_MATCH_RUNTIME) | set(CMP._SERVING_PATH_RUNTIME)
    kv_fingerprinted = {"kv_bits", "max_kv_cache_size"} | set(P._FINGERPRINT_KV_EXTRA)
    kv_classified = (set(CMP._TUNE_KV_WARN) | set(CMP._CAP_BINDING_KV)
                     | set(CMP._CROSS_MODEL_IDENTITY_KV))
    assert kv_fingerprinted == kv_classified, (kv_fingerprinted, kv_classified)
# ------------------------------------------------------- KV-CAP partition + penalty escalation
# (merged 2026-08-18 from the old driver box's O29/O28 work). The cap-mismatch DECISION now lives
# in the ruling-7 binding rule above (refuse iff the clamp could have engaged); what survives from
# the O29 close is `cap_partition()` — the tool that names WHICH rows a smaller cap could have
# touched, so a targeted `--ids` re-run replaces a whole-axis one (exactly the procedure the
# 2026-08-18 ifeval pilot ran by hand).
def _manifest_cap(tmp, model, bench, *, cap, budget=81920, temp=0.4):
    p = G.result_path(model, bench).with_suffix(".manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps({
        "box": "M5", "sampling_profile": "deployed", "fingerprint_version": 3,
        "sampling": {"temperature": temp, "thinking_budget": budget, "max_tokens": 102400},
        "kv": {"kv_bits": 4, "max_kv_cache_size": cap},
        "runtime": {"apc_enabled": "0", "draft_kind": "off"}}))


def test_matched_caps_produce_no_cap_warning(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest_cap(tmp_results, "A", "math500", cap=131072)
    _manifest_cap(tmp_results, "B", "math500", cap=131072)
    r = CMP.compare("A", "B", "math500")
    assert not any("max_kv_cache_size" in x for x in r["warnings"]), r["warnings"]


def test_cap_partition_names_the_SENSITIVE_items_so_a_targeted_rerun_is_possible():
    """The operator's point, mechanised: a row that finished well under the smaller arm's resolved
    budget cannot have been touched by the cap. Only truncated / near-budget rows need re-running."""
    rows = [
        {"id": "safe", "sample": 0, "completion_tokens": 1200, "finish_reason": "stop"},
        {"id": "near", "sample": 0, "completion_tokens": 52000, "finish_reason": "stop"},
        {"id": "hit", "sample": 0, "completion_tokens": 52269, "finish_reason": "length"},
    ]
    part = CMP.cap_partition(rows, resolved_budget=52268)
    assert part["independent"] == ["safe"], part
    assert sorted(part["sensitive"]) == ["hit", "near"], part
    assert part["n_independent"] == 1 and part["n_sensitive"] == 2


def test_cap_partition_margin_is_explicit_and_defensible():
    """`near` at 99% of budget is sensitive even though it says finish_reason=stop: the model was
    steering into a ceiling it could feel. The margin is a JUDGEMENT and must be a named parameter,
    not a magic number buried in a comparison."""
    rows = [{"id": "x", "sample": 0, "completion_tokens": 40000, "finish_reason": "stop"}]
    assert CMP.cap_partition(rows, resolved_budget=52268, margin=0.10)["independent"] == ["x"]
    assert CMP.cap_partition(rows, resolved_budget=52268, margin=0.50)["sensitive"] == ["x"]


def test_cap_partition_IGNORES_the_storage_truncation_flag():
    """A row's `truncated` field means its persisted REASONING TEXT was head/tail excerpted for storage
    (traces.py), NOT that generation was truncated. Reading it as a truncation signal classified 249 of
    541 real ifeval rows as cap-sensitive when the true figure is ~5%. Pinned because the field name
    invites exactly that misreading — and it caught me."""
    rows = [{"id": "long_trace", "sample": 0, "completion_tokens": 2418,
             "finish_reason": "stop", "truncated": True}]
    part = CMP.cap_partition(rows, resolved_budget=52388)
    assert part["independent"] == ["long_trace"], part
    assert part["n_sensitive"] == 0


def test_a_penalty_mismatch_ESCALATES_to_refusal_under_a_non_off_draft_state(write_rows, tmp_results):
    """The synthesis of the two boxes' guards (merged 2026-08-18). Under the (model, tune) taxonomy
    a penalty is a tune axis and WARNS (test_tune_axes_warn_but_never_refuse) — but a nonzero
    penalty makes `logits_processors` non-empty and mlx-vlm's `_suffix_structured_fallback`
    (generate/ar.py:163) then skips speculation for that request, while the registry-derived
    `draft_kind` still reads 'suffix' for both arms. So with a NON-OFF draft state a penalty
    mismatch is a hidden (model x serving-path) composite and must refuse."""
    import json
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    for model, pen in (("A", 0.0), ("B", 0.3)):
        p = G.result_path(model, "math500").with_suffix(".manifest.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "box": "M5", "sampling_profile": "deployed", "fingerprint_version": 3,
            "sampling": {"temperature": 0.4, "thinking_budget": 81920, "max_tokens": 102400,
                         "presence_penalty": pen},
            "kv": {"kv_bits": 4, "max_kv_cache_size": 131072},
            "runtime": {"apc_enabled": "0", "draft_kind": "suffix"}}))
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False, r
    assert "presence_penalty" in r["reason"] and "suffix" in r["reason"], r["reason"]


def test_model_at_tune_syntax_resolves_tuned_rows_and_manifest(write_rows, tmp_results):
    """`Model@tune` must read that model's TUNE-stamped rows/manifest: under the
    (model, tune) taxonomy a candidate's only certified rows may be tuned (the
    Qwen3.8-27B family Stage-2 arms exist only at t0.6), and compare read only the  # allow-shorthand
    untuned baseline paths — blocking the exact verdict Stage-2 exists to produce."""
    import json as _json
    ids = ["a", "b", "c"]
    write_rows("A", "math500", _rows(ids))
    _manifest(tmp_results, "A", "math500", temp=0.3, budget=81920)
    # B exists ONLY at tune t0.6
    pb = G.result_path("B", "math500", tune="t0.6")
    pb.parent.mkdir(parents=True, exist_ok=True)
    with pb.open("w", encoding="utf-8") as f:
        for r in _rows(ids, budget=81920):
            f.write(_json.dumps(r) + "\n")
    mb = pb.with_suffix(".manifest.json")
    mb.write_text(_json.dumps({
        "box": "M2", "sampling_profile": "deployed", "fingerprint_version": 2,
        "sampling": {"temperature": 0.6, "thinking_budget": 81920, "max_tokens": 102400},
        "kv": {"kv_bits": 4}, "runtime": {"apc_enabled": "0"}}))
    # untuned lookup refuses on missing provenance
    r0 = CMP.compare("A", "B", "math500")
    assert not r0["comparable"] and "manifest" in r0["reason"]
    # @tune lookup finds the tuned rows + manifest and proceeds to a verdict
    r1 = CMP.compare("A", "B@t0.6", "math500")
    assert r1["comparable"], r1.get("reason")


def test_refuses_when_reasoning_effort_differs(write_rows, tmp_results):
    """M24: the Qwen3.8-27B family's template effort knob changes the regime the same way
    enable_thinking does — arms at different effort never pool, and absent (template default,
    xhigh there) vs explicit is a difference."""
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    _manifest(tmp_results, "A", "math500", sampling_extra={"reasoning_effort": "xhigh"})
    _manifest(tmp_results, "B", "math500", sampling_extra={"reasoning_effort": "medium"})
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "reasoning_effort" in r["reason"]


# ------------------------------------------------- acc_strict pairing (C29)
def _err_rows(ids, *, budget=16384):
    """DNF rows: a harness error with no text — what a probe_timeout writes."""
    return [{"id": i, "sample": 0, "schema_version": 2, "error": "timed out",
             "error_kind": "probe_timeout", "thinking_budget": budget} for i in ids]


def test_acc_strict_counts_DNFs_as_failures_in_the_paired_delta(write_rows, tmp_results):
    """C29: the paired strict delta must charge DNFs, not silently drop them.

    A is clean; B solves the same items but DNFs on half of them. On `acc` (generated-only,
    by design) the two are identical. On `acc_strict` a DNF is a failed item, so B must be
    HALF of A. Reading the graded item list for a strict metric hides exactly the rows that
    carry the effect — on a DNF-asymmetric axis that inverts the verdict.
    """
    ids = ["a", "b", "c", "d"]
    write_rows("A", "math500", _rows(ids))
    write_rows("B", "math500", _rows(["a", "b"]) + _err_rows(["c", "d"]))
    _manifest(tmp_results, "A", "math500"); _manifest(tmp_results, "B", "math500")

    strict = CMP.compare("A", "B", "math500", metric="acc_strict", intersect=True)
    assert strict["comparable"] is True, strict.get("reason")
    assert strict["n_items"] == 4, "strict pairs over ALL items, DNFs included"
    assert strict["a"] == 1.0
    assert strict["b"] == 0.5, "B DNF'd half its items; acc_strict charges them as failures"
    assert strict["delta"]["delta"] > 0


# ------------------------------------------- probe_timeout as provenance (C28)
def test_refuses_when_probe_timeout_differs_AND_could_have_bound(write_rows, tmp_results):
    """C28: the client bound decides which draws become DNFs, so it is output-determining —
    but only for runs that actually reached it. A row that ran to the bound proves it bound."""
    ids = ["a", "b", "c"]
    write_rows("A", "math500", _rows(ids))
    rows_b = _rows(["a", "b"]) + [{"id": "c", "sample": 0, "schema_version": 2,
                                   "error": "timed out", "error_kind": "probe_timeout",
                                   "wall_s": 3600.0, "thinking_budget": 16384}]
    write_rows("B", "math500", rows_b)
    _manifest(tmp_results, "A", "math500", runtime_extra={"probe_timeout_s": 5400})
    _manifest(tmp_results, "B", "math500", runtime_extra={"probe_timeout_s": 3600})
    r = CMP.compare("A", "B", "math500", intersect=True)
    assert r["comparable"] is False
    assert "probe_timeout" in r["reason"]


def test_allows_differing_probe_timeout_when_it_never_bound(write_rows, tmp_results):
    """Bound-invariant rows must still pool, or the corpus is condemned by a knob that changed
    nothing — the max_kv_cache_size ruling-7 precedent."""
    ids = ["a", "b", "c"]
    write_rows("A", "math500", _rows(ids))
    write_rows("B", "math500", _rows(ids))
    _manifest(tmp_results, "A", "math500", runtime_extra={"probe_timeout_s": 5400})
    _manifest(tmp_results, "B", "math500", runtime_extra={"probe_timeout_s": 3600})
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is True, r.get("reason")
    assert any("probe_timeout" in w for w in r["warnings"])


# =========================================================== pooled_compare (M12, 2026-09)
# "Pooling for power": one paired compare across MULTIPLE benches on acc_strict at a matched
# budget, running the SAME per-bench comparability gate compare() uses -- so a pooled result can
# never be more permissive than the single-bench path, only more powerful (bigger N).
def _acc_strict_bench(write_rows, tmp_results, bench, model_a, model_b, ids, *,
                      a_ok=True, b_ok=True, a_err=(), b_err=(), budget=16384):
    """Write a matched-budget, acc_strict-gradeable pair of runs for one bench: `a_ok`/`b_ok`
    are the correct-answer id sets (True = all correct), `a_err`/`b_err` name ids that DNF
    (a harness error row, no text) instead of generating."""
    def build(ok, err):
        good = [i for i in ids if i not in err]
        rows = _rows(good, ok=ok, budget=budget)
        rows += _err_rows(list(err), budget=budget)
        return rows
    write_rows(model_a, bench, build(a_ok, a_err))
    write_rows(model_b, bench, build(b_ok, b_err))
    _manifest(tmp_results, model_a, bench, budget=budget)
    _manifest(tmp_results, model_b, bench, budget=budget)


def test_pooled_n_and_delta_arithmetic(write_rows, tmp_results):
    """(a) n = n1 + n2, and the pooled acc_strict means are the plain per-model average over
    the FULL pooled item set (5 humanevalplus-style + 10 mbppplus-style items here)."""
    ids1 = [f"h{i}" for i in range(5)]
    ids2 = [f"m{i}" for i in range(10)]
    # bench1: A all correct (5/5=1.0), B all wrong (0/5=0.0)
    _acc_strict_bench(write_rows, tmp_results, "math500", "A", "B", ids1,
                      a_ok=True, b_ok=set())
    # bench2: A correct on 6/10, B correct on 4/10 (both clean, no DNFs)
    _acc_strict_bench(write_rows, tmp_results, "aime", "A", "B", ids2,
                      a_ok=set(ids2[:6]), b_ok=set(ids2[:4]))

    r = CMP.pooled_compare("A", "B", ["math500", "aime"])
    assert r["comparable"] is True, r.get("reason")
    assert r["n_items"] == 15
    # exact pooled means: A = (5*1.0 + 10*0.6)/15 = 11/15 ; B = (5*0.0 + 10*0.4)/15 = 4/15
    assert r["a"] == pytest.approx(11 / 15)
    assert r["b"] == pytest.approx(4 / 15)
    assert r["delta"]["delta"] == pytest.approx(11 / 15 - 4 / 15)
    assert set(r["per_bench"]) == {"math500", "aime"}
    assert r["per_bench"]["math500"]["n_items"] == 5
    assert r["per_bench"]["aime"]["n_items"] == 10


def test_pooled_ci_excludes_zero_when_each_bench_alone_is_inconclusive(write_rows, tmp_results):
    """(b) The exact stats-level fixture (test_stats.py's
    test_paired_delta_pooled_ci_excludes_zero...), replayed through pooled_compare: A correct on
    8/12, B on 5/12, in EACH of two 12-item benches. Alone that is inconclusive at n=12 (grid-
    quantized lo lands on 0.0); pooled to n=24 the CI clears 0."""
    for bench in ("math500", "aime"):
        ids = [f"{bench[0]}{i}" for i in range(12)]
        _acc_strict_bench(write_rows, tmp_results, bench, "A", "B", ids,
                          a_ok=set(ids[:8]), b_ok=set(ids[:5]))

    alone_math = CMP.compare("A", "B", "math500", metric="acc_strict")
    alone_aime = CMP.compare("A", "B", "aime", metric="acc_strict")
    assert alone_math["delta"]["verdict"] == "inconclusive", alone_math
    assert alone_aime["delta"]["verdict"] == "inconclusive", alone_aime

    pooled = CMP.pooled_compare("A", "B", ["math500", "aime"])
    assert pooled["comparable"] is True, pooled.get("reason")
    assert pooled["n_items"] == 24
    assert pooled["delta"]["lo"] > 0, pooled["delta"]
    assert pooled["delta"]["verdict"] == "a_better", pooled["delta"]


def test_pooled_bootstrap_is_stratified_each_draw_keeps_each_benchs_n(write_rows, tmp_results):
    """(c) With a fixed seed, `pooled_compare` must feed `stats.paired_delta` a `strata` map
    that assigns every (bench, item_id) key to its OWN bench, at the ids' correct counts —
    which is what forces every bootstrap replicate to keep n1 from bench1 and n2 from bench2
    fixed (the mechanics of that are pinned directly in test_stats.py; this pins the WIRING)."""
    ids1 = [f"h{i}" for i in range(4)]
    ids2 = [f"m{i}" for i in range(9)]
    _acc_strict_bench(write_rows, tmp_results, "math500", "A", "B", ids1, a_ok=True, b_ok=True)
    _acc_strict_bench(write_rows, tmp_results, "aime", "A", "B", ids2, a_ok=True, b_ok=True)

    captured = {}
    real_paired_delta = CMP.stats.paired_delta

    def spy(a_per_item, b_per_item, **kwargs):
        if kwargs.get("strata") is not None:
            captured["strata"] = kwargs["strata"]
            captured["ids"] = set(a_per_item)
        return real_paired_delta(a_per_item, b_per_item, **kwargs)

    import unittest.mock as mock
    with mock.patch.object(CMP.stats, "paired_delta", side_effect=spy):
        r = CMP.pooled_compare("A", "B", ["math500", "aime"])
    assert r["comparable"] is True, r.get("reason")
    assert "strata" in captured, "pooled_compare must call paired_delta WITH strata"
    strata = captured["strata"]
    assert {k for k, v in strata.items() if v == "math500"} == {("math500", i) for i in ids1}
    assert {k for k, v in strata.items() if v == "aime"} == {("aime", i) for i in ids2}
    n_by_bench = {}
    for k in captured["ids"]:
        n_by_bench[strata[k]] = n_by_bench.get(strata[k], 0) + 1
    assert n_by_bench == {"math500": 4, "aime": 9}


def test_pooled_refuses_when_either_bench_refuses(write_rows, tmp_results):
    """(d) refusal propagation: one bench with mismatched item id sets must refuse the WHOLE
    pooled compare, naming that bench, even though the other bench is perfectly fine."""
    _acc_strict_bench(write_rows, tmp_results, "math500", "A", "B",
                      ["a", "b"], a_ok=True, b_ok=True)
    # aime: item sets differ -> compare() would refuse this bench outright
    write_rows("A", "aime", _rows(["x", "y"]))
    write_rows("B", "aime", _rows(["x", "z"]))
    _manifest(tmp_results, "A", "aime"); _manifest(tmp_results, "B", "aime")

    r = CMP.pooled_compare("A", "B", ["math500", "aime"])
    assert r["comparable"] is False
    assert "aime" in r["reason"]
    assert "item" in r["reason"]


def test_pooled_refuses_a_cross_bench_budget_mismatch(write_rows, tmp_results):
    """(e) Each bench is internally matched (A==B within it) but the two benches themselves ran
    at different thinking_budget -- pooling those would mix truncation regimes into one delta."""
    _acc_strict_bench(write_rows, tmp_results, "math500", "A", "B",
                      ["a", "b"], a_ok=True, b_ok=True, budget=16384)
    _acc_strict_bench(write_rows, tmp_results, "aime", "A", "B",
                      ["x", "y"], a_ok=True, b_ok=True, budget=81920)
    r = CMP.pooled_compare("A", "B", ["math500", "aime"])
    assert r["comparable"] is False
    assert "budget" in r["reason"] or "thinking_budget" in r["reason"]


def test_pooled_needs_at_least_two_benches(write_rows, tmp_results):
    _acc_strict_bench(write_rows, tmp_results, "math500", "A", "B", ["a"], a_ok=True, b_ok=True)
    r = CMP.pooled_compare("A", "B", ["math500"])
    assert r["comparable"] is False


def test_pooled_accepts_tune_applied_to_both_models(write_rows, tmp_results):
    """`tune=` behaves like suffixing '@tune' onto a bare model name for BOTH models, the same
    resolution `Model@tune` already gets in the single-bench path."""
    ids = ["a", "b", "c"]
    for bench in ("math500", "aime"):
        for model in ("A", "B"):
            p = G.result_path(model, bench, tune="t0.6")
            p.parent.mkdir(parents=True, exist_ok=True)
            import json as _json
            with p.open("w", encoding="utf-8") as f:
                for row in _rows(ids, budget=81920):
                    f.write(_json.dumps(row) + "\n")
            mp = p.with_suffix(".manifest.json")
            mp.write_text(_json.dumps({
                "box": "M5", "sampling_profile": "deployed", "fingerprint_version": 3,
                "sampling": {"temperature": 0.4, "thinking_budget": 81920, "max_tokens": 102400},
                "kv": {"kv_bits": 4}, "runtime": {"apc_enabled": "0", "draft_kind": "off"}}))
    # untuned lookup has no rows at all -> refuses
    r0 = CMP.pooled_compare("A", "B", ["math500", "aime"])
    assert r0["comparable"] is False
    r1 = CMP.pooled_compare("A", "B", ["math500", "aime"], tune="t0.6")
    assert r1["comparable"] is True, r1.get("reason")
    assert r1["n_items"] == 6
