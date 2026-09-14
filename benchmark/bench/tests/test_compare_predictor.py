"""`compare_predictor` — the M40 paired same-model, same-items, ON-vs-OFF predictor tool.

`compare.py` REFUSES whenever draft_kind differs; this tool exists to do the opposite check —
REQUIRE draft_kind to differ and everything else output-determining to match — for a same-model
two-tune (predictor ON vs OFF) pair. Tests mirror test_compare.py's fixture style (mock rows and
manifests directly; no real generation).
"""
import json

import pytest

import bench.compare_predictor as CP
import bench.generate as G


def _rows(ids, *, ok=True, samples=1, budget=16384, ct=100, pt=500, wall=10.0, draft=None,
         decode_tps=None):
    """Rows mirroring test_compare.py's `_rows` helper, extended with `wall_s`, an optional
    `draft` field (generate.py's per-request draft-acceptance sidecar) and `decode_tps`."""
    out = []
    for i in ids:
        for s in range(samples):
            hit = ok if isinstance(ok, bool) else (i in ok)
            row = {"id": i, "sample": s, "schema_version": 2,
                  "content": r"\boxed{42}" if hit else r"\boxed{7}",
                  "answer_gold": "42", "completion_tokens": ct, "prompt_tokens": pt,
                  "thinking_budget": budget, "finish_reason": "stop", "wall_s": wall}
            if draft is not None:
                row["draft"] = draft
            if decode_tps is not None:
                row["decode_tps"] = decode_tps
            out.append(row)
    return out


def _write_rows(model, bench, tune, rows):
    p = G.result_path(model, bench, tune=tune)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def _write_manifest(model, bench, tune, *, temp=0.4, budget=16384, max_tokens=102400,
                    cap=131072, draft="off", reasoning_effort=None, box="M5",
                    sampling_extra=None, kv_extra=None, runtime_extra=None, git=None,
                    registry_sha=None):
    p = G.result_path(model, bench, tune=tune).with_suffix(".manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    sampling = {"temperature": temp, "thinking_budget": budget, "max_tokens": max_tokens,
               "reasoning_effort": reasoning_effort}
    if sampling_extra:
        sampling.update(sampling_extra)
    kv = {"max_kv_cache_size": cap}
    if kv_extra:
        kv.update(kv_extra)
    runtime = {"apc_enabled": "0"}
    if draft is not None:
        runtime["draft_kind"] = draft
    if runtime_extra:
        runtime.update(runtime_extra)
    doc = {"box": box, "sampling_profile": "deployed", "fingerprint_version": 3,
          "sampling": sampling, "kv": kv, "runtime": runtime}
    if git is not None:
        doc["git"] = git
    if registry_sha is not None:
        doc["registry"] = {"sha256": registry_sha}
    p.write_text(json.dumps(doc))


def _happy_pair(tmp_results, *, ok_b=True, samples=1, wall_a=10.0, wall_b=8.0,
               ct_a=100, ct_b=80, decode_a=None, decode_b=None, draft_field_b=None):
    ids = ["a", "b", "c", "d", "e"]
    _write_rows("M", "math500", "m37med",
               _rows(ids, ok=True, samples=samples, ct=ct_a, wall=wall_a, decode_tps=decode_a))
    _write_rows("M", "math500", "m40on",
               _rows(ids, ok=ok_b, samples=samples, ct=ct_b, wall=wall_b, decode_tps=decode_b,
                    draft=draft_field_b))
    _write_manifest("M", "math500", "m37med", draft="off")
    _write_manifest("M", "math500", "m40on", draft="mtp")


# --------------------------------------------------------------------------- refusal paths
def test_refuses_when_manifest_missing(tmp_results):
    _write_rows("M", "math500", "m37med", _rows(["a"]))
    _write_manifest("M", "math500", "m37med", draft="off")
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "manifest" in r["reason"]


def test_refuses_when_draft_kind_is_the_same(tmp_results):
    _write_rows("M", "math500", "m37med", _rows(["a", "b"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b"]))
    _write_manifest("M", "math500", "m37med", draft="off")
    _write_manifest("M", "math500", "m40on", draft="off")
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "SAME" in r["reason"] or "same" in r["reason"]


def test_refuses_when_draft_kind_unrecorded(tmp_results):
    _write_rows("M", "math500", "m37med", _rows(["a"]))
    _write_rows("M", "math500", "m40on", _rows(["a"]))
    _write_manifest("M", "math500", "m37med", draft=None)
    _write_manifest("M", "math500", "m40on", draft="mtp")
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "unrecorded" in r["reason"]


def test_refuses_when_another_output_determining_field_differs(tmp_results):
    """draft_kind correctly differs, but max_tokens ALSO differs — not a clean ON/OFF pair."""
    _write_rows("M", "math500", "m37med", _rows(["a", "b"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b"]))
    _write_manifest("M", "math500", "m37med", draft="off", max_tokens=102400)
    _write_manifest("M", "math500", "m40on", draft="mtp", max_tokens=81920)
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "max_tokens" in r["reason"]


def test_refuses_when_temperature_differs(tmp_results):
    """Unlike compare.py (WARN, per-model tune axis), a predictor pair is the SAME model's SAME
    tune otherwise — temperature must match here."""
    _write_rows("M", "math500", "m37med", _rows(["a", "b"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b"]))
    _write_manifest("M", "math500", "m37med", draft="off", temp=0.5)
    _write_manifest("M", "math500", "m40on", draft="mtp", temp=0.6)
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "temperature" in r["reason"]


def test_refuses_when_item_id_sets_differ(tmp_results):
    _write_rows("M", "math500", "m37med", _rows(["a", "b", "c"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b", "d"]))
    _write_manifest("M", "math500", "m37med", draft="off")
    _write_manifest("M", "math500", "m40on", draft="mtp")
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "item id" in r["reason"]


def test_refuses_when_sample_sets_differ(tmp_results):
    a_rows = _rows(["a", "b"], samples=1)
    b_rows = _rows(["a", "b"], samples=2)
    _write_rows("M", "math500", "m37med", a_rows)
    _write_rows("M", "math500", "m40on", b_rows)
    _write_manifest("M", "math500", "m37med", draft="off")
    _write_manifest("M", "math500", "m40on", draft="mtp")
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "sample" in r["reason"]


def test_rejects_a_bad_key(tmp_results):
    with pytest.raises(ValueError):
        CP.compare_predictor("M", "math500", "m37med", "m40on", key="decode_tps")


# -------------------------------------------------------- cold-review fix 1: sampling WARN tier
def test_refuses_when_top_p_differs(tmp_results):
    _write_rows("M", "math500", "m37med", _rows(["a", "b"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b"]))
    _write_manifest("M", "math500", "m37med", draft="off", sampling_extra={"top_p": 0.9})
    _write_manifest("M", "math500", "m40on", draft="mtp", sampling_extra={"top_p": 0.95})
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "top_p" in r["reason"]


# -------------------------------------------------------------- cold-review fix 2: KV WARN tier
@pytest.mark.parametrize("field,val_a,val_b", [
    ("kv_bits", 4, 8),
    ("hf_path", "org/model-a", "org/model-b"),
    ("kv_prealloc_tokens", 131072, 65536),
    ("cache_session_shrink", False, True),
    ("kv_quant_scheme", "uniform", "turboquant"),
])
def test_refuses_when_a_kv_field_differs(tmp_results, field, val_a, val_b):
    _write_rows("M", "math500", "m37med", _rows(["a", "b"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b"]))
    _write_manifest("M", "math500", "m37med", draft="off", kv_extra={field: val_a})
    _write_manifest("M", "math500", "m40on", draft="mtp", kv_extra={field: val_b})
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert field in r["reason"]


# --------------------------------------------------------- cold-review fix 3: runtime + probes
def test_refuses_when_apc_enabled_differs(tmp_results):
    _write_rows("M", "math500", "m37med", _rows(["a", "b"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b"]))
    _write_manifest("M", "math500", "m37med", draft="off", runtime_extra={"apc_enabled": "0"})
    _write_manifest("M", "math500", "m40on", draft="mtp", runtime_extra={"apc_enabled": "1"})
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "apc_enabled" in r["reason"]


def test_refuses_when_box_differs(tmp_results):
    _write_rows("M", "math500", "m37med", _rows(["a", "b"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b"]))
    _write_manifest("M", "math500", "m37med", draft="off", box="M2")
    _write_manifest("M", "math500", "m40on", draft="mtp", box="M5")
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "box" in r["reason"]


def test_probe_timeout_refuses_when_a_row_could_have_bound(tmp_results):
    rows_a = _rows(["a", "b"], wall=59.0)   # near the smaller bound (60 * 0.9 = 54)
    rows_b = _rows(["a", "b"], wall=10.0)
    _write_rows("M", "math500", "m37med", rows_a)
    _write_rows("M", "math500", "m40on", rows_b)
    _write_manifest("M", "math500", "m37med", draft="off", runtime_extra={"probe_timeout_s": 60})
    _write_manifest("M", "math500", "m40on", draft="mtp", runtime_extra={"probe_timeout_s": 120})
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "probe_timeout_s" in r["reason"]


def test_probe_timeout_mismatch_allowed_when_never_bound(tmp_results):
    _happy_pair(tmp_results)   # wall_s 8-10s, nowhere near any plausible probe_timeout_s
    _write_manifest("M", "math500", "m37med", draft="off", runtime_extra={"probe_timeout_s": 3600})
    _write_manifest("M", "math500", "m40on", draft="mtp", runtime_extra={"probe_timeout_s": 7200})
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is True
    assert any("probe_timeout_s" in w for w in r["warnings"])


# ------------------------------------------------- cold-review fix 4: item-set asymmetry (safe)
def test_refuses_cleanly_instead_of_crashing_when_acc_item_sets_go_asymmetric(tmp_results):
    """An error row on ONE arm only still matches the other arm's (id, sample) key (so `_gate`
    passes), but grade.grade's non-strict `items` DROPS error rows entirely — leaving the "acc"
    per-item vectors asymmetric. This used to raise an uncaught ValueError from
    stats.paired_delta; it must refuse cleanly instead."""
    ids = ["a", "b", "c", "d", "e"]
    _write_rows("M", "math500", "m37med", _rows(ids))
    rows_b = _rows(ids)
    for r in rows_b:
        if r["id"] == "c":
            r["error"] = True
    _write_rows("M", "math500", "m40on", rows_b)
    _write_manifest("M", "math500", "m37med", draft="off")
    _write_manifest("M", "math500", "m40on", draft="mtp")
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "acc" in r["reason"] and "tune_a" in r["reason"]


def test_refuses_cleanly_when_a_per_item_set_is_entirely_empty(tmp_results):
    ids = ["a", "b", "c"]
    _write_rows("M", "math500", "m37med", _rows(ids))
    rows_b = _rows(ids)
    for r in rows_b:
        r["error"] = True
    _write_rows("M", "math500", "m40on", rows_b)
    _write_manifest("M", "math500", "m37med", draft="off")
    _write_manifest("M", "math500", "m40on", draft="mtp")
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "no scored items" in r["reason"]


# ------------------------------------------------- cold-review fix 5: penalty/speculation trap
def test_refuses_when_penalty_nonzero_even_when_matched_on_both_sides(tmp_results):
    """A MATCHED nonzero penalty is just as broken as a mismatched one: it silently disables
    speculation on the non-off arm regardless of whether the off arm shares the same value."""
    _write_rows("M", "math500", "m37med", _rows(["a", "b"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b"]))
    _write_manifest("M", "math500", "m37med", draft="off",
                    sampling_extra={"presence_penalty": 0.1})
    _write_manifest("M", "math500", "m40on", draft="mtp",
                    sampling_extra={"presence_penalty": 0.1})
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "presence_penalty" in r["reason"] and "nonzero" in r["reason"]


def test_warns_when_non_off_arm_has_no_draft_telemetry(tmp_results):
    _happy_pair(tmp_results)   # default draft_field_b=None: mtp tune with no draft sidecar
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is True
    assert any("m40on" in w and "draft_n telemetry" in w for w in r["warnings"])


# ------------------------------------------------------- cold-review fix 6: serving-path check
def test_refuses_when_serving_path_shas_differ(tmp_results):
    _write_rows("M", "math500", "m37med", _rows(["a", "b"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b"]))
    git_a = {"submodules": {"src/mlx-vlm": "a" * 40, "src/mlx-serve": "b" * 40}}
    git_b = {"submodules": {"src/mlx-vlm": "c" * 40, "src/mlx-serve": "b" * 40}}
    _write_manifest("M", "math500", "m37med", draft="off", git=git_a)
    _write_manifest("M", "math500", "m40on", draft="mtp", git=git_b)
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is False
    assert "code" in r["reason"] or "serving path" in r["reason"]


def test_warns_when_a_serving_path_sha_is_recorded_on_one_side_only(tmp_results):
    _happy_pair(tmp_results)
    git_a = {"submodules": {"src/mlx-vlm": "a" * 40}}
    _write_manifest("M", "math500", "m37med", draft="off", git=git_a)
    _write_manifest("M", "math500", "m40on", draft="mtp")   # no git block at all
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is True
    assert any("recorded on only one side" in w for w in r["warnings"])


# --------------------------------------------------------- cold-review fix 7: no silent gaps
def test_every_fingerprint_key_is_classified_here_no_silent_gaps():
    """Mirror of test_compare.py's test_every_fingerprint_key_is_classified_in_compare_no_silent_
    gaps: every fingerprinted sampling/runtime/kv key must belong to this module's must-match
    tuples (draft_kind excepted, since it must DIFFER, not match)."""
    import bench.provenance as P
    assert set(P._FINGERPRINT_SAMPLING) == set(CP._SAMPLING_MUST_MATCH)
    assert set(P._FINGERPRINT_RUNTIME) == set(CP._RUNTIME_MUST_MATCH) | {"draft_kind"}
    kv_fingerprinted = {"kv_bits", "max_kv_cache_size"} | set(P._FINGERPRINT_KV_EXTRA)
    assert kv_fingerprinted == set(CP._KV_MUST_MATCH)
    # kv_prealloc_tokens is deliberately OUTSIDE the correctness fingerprint (text-invariant per
    # provenance.py) but checked here anyway since this tool reports hardware-ish ratios too.
    assert set(CP._KV_HARDWARE_EXTRA) == {"kv_prealloc_tokens", "cache_session_shrink"}
    assert not (set(CP._KV_HARDWARE_EXTRA) & kv_fingerprinted)


# ------------------------------------------------------------------------ the happy path
def test_equivalent_result_reports_pass_verdict_and_full_payload(tmp_results):
    _happy_pair(tmp_results, ok_b=True, decode_a=20.0, decode_b=25.0,
               draft_field_b={"draft_kind": "mtp", "draft_rounds": 4, "draft_n": 20,
                              "draft_n_accepted": 15})
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is True
    assert r["verdict"] == "PASS"
    assert r["delta"]["acc_strict"]["delta"] == pytest.approx(0.0)
    assert r["delta"]["acc_strict"]["verdict"] == "equivalent"
    assert r["delta"]["acc_strict"]["discordant"] == 0
    assert r["delta"]["acc_strict"]["a"] == pytest.approx(1.0)
    assert r["delta"]["acc_strict"]["b"] == pytest.approx(1.0)
    assert r["delta"]["acc"]["delta"] == pytest.approx(0.0)
    # tokens/wall ratios: B uses ct=80/wall=8.0, A uses ct=100/wall=10.0 -> ratio 0.8
    assert r["tokens_per_task_ratio_b_over_a"]["point"] == pytest.approx(0.8)
    assert r["tokens_per_task_ratio_b_over_a"]["n_reps_used"] == r["tokens_per_task_ratio_b_over_a"]["iters"]
    assert r["wall_ratio_b_over_a"]["point"] == pytest.approx(0.8)
    assert r["decode_tps"]["mean"]["m37med"] == pytest.approx(20.0)
    assert r["decode_tps"]["mean"]["m40on"] == pytest.approx(25.0)
    assert r["decode_tps"]["ratio_b_over_a"]["point"] == pytest.approx(1.25)
    assert r["convergence"]["m37med"]["n_generated"] == 5
    assert r["convergence"]["m40on"]["n_generated"] == 5
    assert r["draft_acceptance"]["m37med"] is None       # OFF tune: no draft field on its rows
    assert r["draft_acceptance"]["m40on"]["mean_of_ratios"] == pytest.approx(0.75)
    assert r["draft_acceptance"]["m40on"]["pooled_ratio"] == pytest.approx(0.75)
    assert set(r["nonconv_kinds"]) == {"m37med", "m40on"}
    assert r["draft_a"] == "off" and r["draft_b"] == "mtp"
    assert r["n_items"] == 5
    assert r["registry_sha"] == {"m37med": None, "m40on": None}
    assert isinstance(r["warnings"], list)


def test_registry_sha_reported_when_present(tmp_results):
    _happy_pair(tmp_results)
    _write_manifest("M", "math500", "m37med", draft="off", registry_sha="deadbeef")
    _write_manifest("M", "math500", "m40on", draft="mtp", registry_sha="cafef00d")
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is True
    assert r["registry_sha"] == {"m37med": "deadbeef", "m40on": "cafef00d"}


def test_much_worse_b_reports_fail_verdict(tmp_results):
    # OFF (A) is perfect; ON (B) fails everything -> delta(B-A) far below -5pp.
    _happy_pair(tmp_results, ok_b=False)
    r = CP.compare_predictor("M", "math500", "m37med", "m40on")
    assert r["comparable"] is True
    assert r["verdict"] == "FAIL"
    assert r["delta"]["acc_strict"]["delta"] < -0.05
    assert r["delta"]["acc_strict"]["verdict"] in ("tune_a_better",)


def test_key_selects_which_delta_drives_the_verdict(tmp_results):
    """Force acc and acc_strict to disagree: B's item 'a' is truncated (finish_reason=length),
    so acc_strict zeroes it while acc (graded-only) still credits it since the text itself is
    still `\\boxed{42}`. Picking a different --key can therefore change the verdict."""
    ids = ["a", "b", "c", "d", "e"]
    _write_rows("M", "math500", "m37med", _rows(ids, ok=True, ct=100, budget=16384))
    b_rows = _rows(ids, ok=True, ct=100, budget=16384)
    for r in b_rows:
        if r["id"] == "a":
            r["finish_reason"] = "length"
    _write_rows("M", "math500", "m40on", b_rows)
    _write_manifest("M", "math500", "m37med", draft="off")
    _write_manifest("M", "math500", "m40on", draft="mtp")

    r_strict = CP.compare_predictor("M", "math500", "m37med", "m40on", key="acc_strict")
    r_acc = CP.compare_predictor("M", "math500", "m37med", "m40on", key="acc")
    assert r_strict["delta"]["acc_strict"]["delta"] < 0      # truncated row charged as wrong
    assert r_acc["delta"]["acc"]["delta"] == pytest.approx(0.0)   # acc: still boxed{42}, correct
    assert r_strict["verdict"] != r_acc["verdict"] or (
        r_strict["delta"]["acc_strict"]["delta"] != r_acc["delta"]["acc"]["delta"])


# ------------------------------------------------------------------------ unit-level helpers
def test_verdict_pass_before_fail_precedence_at_matched_margin(tmp_results):
    """A CI entirely within margin whose hi also happens to be < 0 must read PASS, not FAIL —
    precedence, not just boundary correctness."""
    chosen = {"lo": -0.01, "hi": -0.01, "delta": -0.01}
    assert CP._verdict(chosen, margin=0.05) == "PASS"


def test_verdict_strict_inequality_at_the_margin_boundary():
    chosen_at_boundary = {"lo": -0.05, "hi": 0.03, "delta": 0.0}
    assert CP._verdict(chosen_at_boundary, margin=0.05) != "PASS"
    chosen_inside = {"lo": -0.049, "hi": 0.03, "delta": 0.0}
    assert CP._verdict(chosen_inside, margin=0.05) == "PASS"


def test_draft_acceptance_reports_mean_and_pooled_ratio():
    rows = [
        {"id": "a", "draft": {"draft_n": 10, "draft_n_accepted": 5}},    # ratio 0.5
        {"id": "b", "draft": {"draft_n": 100, "draft_n_accepted": 90}},  # ratio 0.9
    ]
    out = CP._draft_acceptance(rows)
    assert out["mean_of_ratios"] == pytest.approx(0.7)
    assert out["pooled_ratio"] == pytest.approx(round(95 / 110, 4))
    assert out["n_rows"] == 2


def test_paired_ratio_records_n_reps_used_at_full_count_when_no_zero_means():
    pa, pb = {"x": [1.0]}, {"x": [2.0]}
    out = CP._paired_ratio(pa, pb, iters=50, seed=0)
    assert out["n_reps_used"] == 50


def test_paired_ratio_drops_zero_denominator_replicates_and_records_it():
    pa, pb = {"x": [0.0, 1.0]}, {"x": [1.0, 1.0]}
    out = CP._paired_ratio(pa, pb, iters=400, seed=0)
    assert 0 < out["n_reps_used"] < 400


# --------------------------------------------------------------------------- CLI (main)
def test_main_writes_json_next_to_b_rows_and_prints_verdict(tmp_results, capsys):
    _happy_pair(tmp_results)
    rc = CP.main(["--model", "M", "--bench", "math500", "--tune-a", "m37med",
                 "--tune-b", "m40on"])
    assert rc == 0
    out_path = CP._out_path("M", "math500", "m37med", "m40on")
    assert out_path.name == "math500.m40on.vs.m37med.json"
    assert out_path.exists()
    doc = json.loads(out_path.read_text())
    assert doc["verdict"] == "PASS"
    captured = capsys.readouterr()
    assert "PASS" in captured.out


def test_main_refusal_exits_nonzero_and_writes_nothing(tmp_results, capsys):
    _write_rows("M", "math500", "m37med", _rows(["a", "b", "c"]))
    _write_rows("M", "math500", "m40on", _rows(["a", "b", "d"]))
    _write_manifest("M", "math500", "m37med", draft="off")
    _write_manifest("M", "math500", "m40on", draft="mtp")
    rc = CP.main(["--model", "M", "--bench", "math500", "--tune-a", "m37med",
                 "--tune-b", "m40on"])
    assert rc == 1
    out_path = CP._out_path("M", "math500", "m37med", "m40on")
    assert not out_path.exists()
    captured = capsys.readouterr()
    assert "REFUSED" in captured.err
