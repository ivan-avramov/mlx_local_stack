"""M57 AC11: `compare.py` refuses across `attention_policy`; `compare_predictor.py` accepts exactly
ONE named must-differ key (`draft_kind` default, or `attention_policy`) and every other rule stays.
"""
import json

import bench.compare as CMP
import bench.compare_predictor as CP
import bench.generate as G
from bench.tests.test_compare import _rows as _cmp_rows
from bench.tests.test_compare_predictor import _rows as _cp_rows, _write_rows


def _manifest(model, bench, *, tune=None, version=7, policy=None, draft="off",
              source="worker", **_):
    p = G.result_path(model, bench, tune=tune).with_suffix(".manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    rt = {"apc_enabled": "0", "draft_kind": draft}
    if policy is not None:
        rt["attention_policy"] = policy
        rt["attention_policy_source"] = source
    p.write_text(json.dumps({
        "box": "M5", "sampling_profile": "deployed", "fingerprint_version": version,
        "sampling": {"temperature": 0.4, "thinking_budget": 16384, "max_tokens": 102400},
        "kv": {"kv_bits": 0, "max_kv_cache_size": 131072}, "runtime": rt}))


# ------------------------------------------------------------------------------ compare.py
def test_ac11_compare_refuses_across_attention_policy_quality_and_speed(write_rows, tmp_results):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest("A", "math500", policy="auto")
    _manifest("B", "math500", policy="fused_v1")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False
    assert "attention_policy" in r["reason"]
    assert CMP.compare("A", "B", "math500", metric="decode_tps")["comparable"] is False


def test_ac11_compare_matched_policy_compares(write_rows, tmp_results):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest("A", "math500", policy="fused_v1")
    _manifest("B", "math500", policy="fused_v1", source="registry")
    assert CMP.compare("A", "B", "math500")["comparable"] is True


def test_ac11_compare_pre_v7_row_reads_as_auto(write_rows, tmp_results):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest("A", "math500", version=6)                       # pre-v7: no attention_policy
    _manifest("B", "math500", policy="auto")
    assert CMP.compare("A", "B", "math500")["comparable"] is True
    _manifest("B", "math500", policy="fused_v1")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "attention_policy" in r["reason"]


def test_ac11_compare_unobserved_policy_warns(write_rows, tmp_results):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest("A", "math500", policy="unknown")
    _manifest("B", "math500", policy="fused_v1")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is True
    assert any("attention_policy" in w for w in r["warnings"])


# ----------------------------------------------------------------------- compare_predictor.py
_IDS = ["a", "b", "c", "d", "e"]


def _pair(tmp_results, *, draft_a="off", draft_b="off", pol_a="auto", pol_b="fused_v1",
          version_a=7, version_b=7):
    _write_rows("M", "math500", "ta", _cp_rows(_IDS))
    _write_rows("M", "math500", "tb", _cp_rows(_IDS))
    _manifest("M", "math500", tune="ta", draft=draft_a, policy=pol_a, version=version_a)
    _manifest("M", "math500", tune="tb", draft=draft_b, policy=pol_b, version=version_b)


def test_ac11_predictor_attention_mode_accepts_policy_pair(tmp_results):
    _pair(tmp_results)
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="attention_policy")
    assert r["comparable"] is True, r
    assert r["must_differ"] == "attention_policy"


def test_ac11_predictor_attention_mode_accepts_pre_v7_baseline_vs_fused(tmp_results):
    _pair(tmp_results, pol_a=None, version_a=6)
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="attention_policy")
    assert r["comparable"] is True, r


def test_ac11_predictor_attention_mode_refuses_same_policy(tmp_results):
    _pair(tmp_results, pol_a="fused_v1", pol_b="fused_v1")
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="attention_policy")
    assert r["comparable"] is False
    assert "attention_policy" in r["reason"] and "SAME" in r["reason"]


def test_ac11_predictor_attention_mode_refuses_unobserved_policy(tmp_results):
    _pair(tmp_results, pol_a="unknown")
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="attention_policy")
    assert r["comparable"] is False and "unrecorded" in r["reason"]


def test_ac11_predictor_attention_mode_requires_draft_kind_to_MATCH(tmp_results):
    _pair(tmp_results, draft_a="off", draft_b="mtp")
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="attention_policy")
    assert r["comparable"] is False
    assert "draft_kind" in r["reason"]


def test_ac11_predictor_default_mode_requires_policy_to_MATCH(tmp_results):
    _pair(tmp_results, draft_a="off", draft_b="mtp", pol_a="auto", pol_b="fused_v1")
    r = CP.compare_predictor("M", "math500", "ta", "tb")
    assert r["comparable"] is False
    assert "attention_policy" in r["reason"]


def test_ac11_predictor_default_mode_unchanged_when_policy_matches(tmp_results):
    _pair(tmp_results, draft_a="off", draft_b="mtp", pol_a="auto", pol_b="auto")
    r = CP.compare_predictor("M", "math500", "ta", "tb")
    assert r["comparable"] is True, r
    assert r["must_differ"] == "draft_kind"


def test_ac11_predictor_default_mode_still_refuses_same_draft(tmp_results):
    _pair(tmp_results, draft_a="off", draft_b="off", pol_a="auto", pol_b="fused_v1")
    r = CP.compare_predictor("M", "math500", "ta", "tb")
    assert r["comparable"] is False and "draft_kind" in r["reason"]


def test_ac11_predictor_attention_mode_other_checks_still_apply(tmp_results):
    _pair(tmp_results)
    _manifest("M", "math500", tune="tb", policy="fused_v1")
    p = G.result_path("M", "math500", tune="tb").with_suffix(".manifest.json")
    doc = json.loads(p.read_text())
    doc["sampling"]["temperature"] = 0.9
    p.write_text(json.dumps(doc))
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="attention_policy")
    assert r["comparable"] is False and "temperature" in r["reason"]


def test_ac11_predictor_rejects_unknown_must_differ_key(tmp_results):
    import pytest
    _pair(tmp_results)
    with pytest.raises(ValueError, match="must_differ"):
        CP.compare_predictor("M", "math500", "ta", "tb", must_differ="max_tokens")


def test_ac11_predictor_cli_option(tmp_results, capsys):
    _pair(tmp_results)
    rc = CP.main(["--model", "M", "--bench", "math500", "--tune-a", "ta", "--tune-b", "tb",
                  "--must-differ", "attention_policy"])
    assert rc == 0
    rc = CP.main(["--model", "M", "--bench", "math500", "--tune-a", "ta", "--tune-b", "tb"])
    assert rc == 1                                  # default draft_kind: same draft -> refused
    assert "draft_kind" in capsys.readouterr().err
