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
