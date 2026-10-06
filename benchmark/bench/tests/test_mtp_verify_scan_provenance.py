"""v8 (M58, AC10 / AC12): the MTP verification scan is provenance.

`mtp_verify_scan` (`per_query` | `joint_v1` | `joint_v1+ab`) changes WHICH attention call the
verifier makes, so rows at different values never pool and never compare. The live worker's
command line is the serving truth (flags absent = `per_query`), the registry the fallback, and a
disagreement refuses. Controls carry PER-CONTROL introduction versions, so the v7 M57 rows on disk
stay compatible with a v8 `per_query` row.
"""
import json

import pytest
import yaml

import bench.compare as CMP
import bench.compare_predictor as CP
import bench.generate as G
import bench.provenance as P
from bench.tests.test_compare import _rows as _cmp_rows
from bench.tests.test_compare_predictor import _rows as _cp_rows, _write_rows

pytestmark = pytest.mark.real_mtp_scan      # exercise the real resolution (see conftest)
KEY = "mtp_verify_scan"
_WORKER = ["python", "-m", "mlx_vlm.server", "--model", "caslca/modelX-4bit", "--port", "8091"]


def _registry(tmp_path, scan=None, ab=None):
    entry = {"name": "modelX", "hf_path": "caslca/modelX-4bit"}
    if scan is not None:
        entry[KEY] = scan
    if ab is not None:
        entry["mtp_verify_ab"] = ab
    p = tmp_path / "mv_reg.yaml"
    p.write_text(yaml.safe_dump({"models": [entry]}))
    return str(p)


def _resolve(tmp_path, scan=None, ab=None, argv=None):
    return P.registry_mtp_verify_scan(
        "modelX", _registry(tmp_path, scan, ab),
        worker_lookup=(lambda: [argv]) if argv is not None else (lambda: None))


def _man(v, scan=None, source=None, policy="auto", **extra_rt):
    rt = dict(extra_rt)
    if v >= 7:
        rt.update({"lazy_prompt_embeddings": False, "attention_policy": policy})
    if scan is not None:
        rt[KEY] = scan
    if source is not None:
        rt[KEY + "_source"] = source
    return {"sampling_profile": "deployed", "fingerprint_version": v, "sampling": {}, "kv": {},
            "runtime": rt}


# --------------------------------------------------------------------------- the version table
def test_ac10_fingerprint_version_is_8():
    assert P.FINGERPRINT_VERSION == 8


def test_ac10_controls_carry_per_control_introduction_versions():
    assert P._SERVING_CONTROLS == {"attention_policy": (7, "auto"),
                                   "lazy_prompt_embeddings": (7, False),
                                   "mtp_verify_scan": (8, "per_query")}


@pytest.mark.parametrize("v", [1, 2, 4, 5, 6, 7])
def test_ac10_pre_v8_manifests_read_per_query_default_pre_v8(v):
    assert P.control_of(_man(v), KEY) == ("per_query", "default-pre-v8")
    # a pre-v8 manifest cannot smuggle a value in
    assert P.control_of(_man(v, "joint_v1"), KEY) == ("per_query", "default-pre-v8")


def test_ac10_older_controls_keep_their_own_default_pre_v7_source():
    assert P.control_of(_man(6), "attention_policy") == ("auto", "default-pre-v7")
    assert P.control_of(_man(6), "lazy_prompt_embeddings") == (False, "default-pre-v7")
    assert P.control_of(_man(7, policy="fused_v1"), "attention_policy") == ("fused_v1", None)


def test_ac10_v8_manifest_reports_what_it_recorded_and_unknown_when_missing():
    assert P.control_of(_man(8, "joint_v1", "worker"), KEY) == ("joint_v1", "worker")
    assert P.control_of(_man(8, "joint_v1+ab", "worker"), KEY)[0] == "joint_v1+ab"
    assert P.control_of(_man(8), KEY)[0] == "unknown"
    assert P.control_of(_man(8, "joint_v2", "worker"), KEY)[0] == "unknown"   # unrecognised
    assert P.control_of(_man(8, "ab", "worker"), KEY)[0] == "unknown"


# --------------------------------------------------------------------------- resolution
def test_ac10_registry_default_is_per_query_when_field_absent_or_empty(tmp_path):
    for scan in (None, "", "per_query"):
        assert _resolve(tmp_path, scan) == {KEY: "per_query", KEY + "_source": "registry"}


def test_ac10_registry_joint_v1_is_read_when_no_worker(tmp_path):
    assert _resolve(tmp_path, "joint_v1") == {KEY: "joint_v1", KEY + "_source": "registry"}


def test_ac10_registry_never_yields_the_ab_value(tmp_path):
    # `joint_v1+ab` rows are gate rows: observed from a live worker, never from the registry
    assert _resolve(tmp_path, "joint_v1", ab=True)[KEY] == "joint_v1"


def test_ac10_worker_without_flags_means_per_query_source_worker(tmp_path):
    assert _resolve(tmp_path, None, argv=_WORKER) == {KEY: "per_query", KEY + "_source": "worker"}


def test_ac10_worker_flags_are_observed(tmp_path):
    joint = _WORKER + ["--mtp-verify-scan", "joint_v1"]
    assert _resolve(tmp_path, "joint_v1", argv=joint) == {KEY: "joint_v1", KEY + "_source": "worker"}
    ab = joint + ["--mtp-verify-ab"]
    assert _resolve(tmp_path, "joint_v1", ab=True, argv=ab) == {
        KEY: "joint_v1+ab", KEY + "_source": "worker"}
    eq = _WORKER + ["--mtp-verify-scan=joint_v1"]
    assert _resolve(tmp_path, "joint_v1", argv=eq)[KEY] == "joint_v1"


@pytest.mark.parametrize("scan,argv_extra", [
    ("joint_v1", []),                                              # registry joint, worker per_query
    (None, ["--mtp-verify-scan", "joint_v1"]),                     # registry per_query, worker joint
    ("joint_v1", ["--mtp-verify-scan", "joint_v1", "--mtp-verify-ab"]),   # AB not declared
])
def test_ac10_worker_registry_mismatch_refuses(tmp_path, scan, argv_extra):
    with pytest.raises(P.ServingStateError, match="C35 tripwire.*mtp_verify_scan"):
        _resolve(tmp_path, scan, argv=_WORKER + argv_extra)


def test_ac10_ab_overlay_agreeing_with_an_ab_worker_is_accepted(tmp_path):
    argv = _WORKER + ["--mtp-verify-scan", "joint_v1", "--mtp-verify-ab"]
    assert _resolve(tmp_path, "joint_v1", ab=True, argv=argv)[KEY] == "joint_v1+ab"
    with pytest.raises(P.ServingStateError):      # overlay says AB, worker is not AB
        _resolve(tmp_path, "joint_v1", ab=True,
                 argv=_WORKER + ["--mtp-verify-scan", "joint_v1"])


def test_ac10_ambiguous_workers_refuse(tmp_path):
    with pytest.raises(P.ServingStateError):
        P.registry_mtp_verify_scan("modelX", _registry(tmp_path),
                                   worker_lookup=lambda: [_WORKER, _WORKER])


def test_ac10_unknown_model_or_unreadable_registry_is_unknown(tmp_path):
    st = P.registry_mtp_verify_scan("nope", _registry(tmp_path), worker_lookup=lambda: None)
    assert st[KEY] == "unknown"
    st = P.registry_mtp_verify_scan("modelX", str(tmp_path / "missing.yaml"),
                                    worker_lookup=lambda: None)
    assert st[KEY] == "unknown"


def test_ac10_runtime_block_carries_key_and_source(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "apc_state", lambda: {"apc_enabled": "0", "source": "process"})
    monkeypatch.setattr(P, "registry_draft", lambda m, path=None: {"draft_kind": "mtp"})
    monkeypatch.setattr(P, "session_retention_state",
                        lambda: {"session_retain_prompt_end": "on", "session_retain_source": "worker"})
    block = P._runtime_block(None, model="modelX",
                             registry_path=_registry(tmp_path, "joint_v1"))
    assert block[KEY] == "joint_v1" and block[KEY + "_source"] == "registry"


def test_ac10_assert_serving_state_includes_the_key_and_refuses_when_unresolved(tmp_path, monkeypatch):
    reg = _registry(tmp_path, "joint_v1")
    out = P.assert_serving_state("modelX", reg)
    assert out[KEY] == "joint_v1" and out[KEY + "_source"] == "registry"
    with pytest.raises(P.ServingStateError, match=KEY):
        P.assert_serving_state("nope", reg)
    # a worker/registry mismatch propagates out of assert_serving_state (default lookup stubbed)
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [_WORKER])
    with pytest.raises(P.ServingStateError, match="C35 tripwire.*mtp_verify_scan"):
        P.assert_serving_state("modelX", reg)


def test_ac10_generate_run_refuses_on_scan_disagreement_before_any_request(tmp_path, monkeypatch):
    import bench.benchmarks as B
    import bench.client as C
    import bench.paths as paths
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    reg = _registry(tmp_path, "joint_v1")
    monkeypatch.setattr(paths, "registry_path", lambda: __import__("pathlib").Path(reg))
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    calls = []
    monkeypatch.setattr(C, "probe", lambda *a, **k: calls.append("probe"))
    monkeypatch.setattr(C, "preload", lambda m, **k: calls.append("preload") or 0.0)
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [_WORKER])      # worker serves per_query
    with pytest.raises(P.ServedConfigError):
        G.run(["modelX"], ["aime"], {})
    assert calls == [] and not list(tmp_path.glob("modelX/*"))


# --------------------------------------------------------------------------- the fingerprint
def test_ac10_only_value_not_source_enters_the_v8_fingerprint():
    fp = P.config_fingerprint(_man(8, "joint_v1", "worker"))
    assert fp["runtime"][KEY] == "joint_v1"
    assert KEY + "_source" not in fp["runtime"]
    assert KEY not in P.config_fingerprint(_man(7, "joint_v1", "worker"))["runtime"]
    assert P.is_compatible(_man(8, "joint_v1", "worker"), _man(8, "joint_v1", "registry")) is True


def test_ac10_v8_rows_at_different_values_never_pool():
    for a, b in [("per_query", "joint_v1"), ("joint_v1", "joint_v1+ab"),
                 ("per_query", "joint_v1+ab")]:
        assert P.is_compatible(_man(8, a, "worker"), _man(8, b, "worker")) is False
        assert P.is_compatible(_man(8, b, "worker"), _man(8, a, "worker")) is False


# --------------------------------------------------------------------------- AC12 v7 compat
def test_ac12_v7_manifest_is_compatible_with_v8_per_query_both_ways():
    v7 = _man(7, policy="fused_v1")
    cur = _man(8, "per_query", "worker", policy="fused_v1")
    assert P.is_compatible(v7, cur) is True
    assert P.is_compatible(cur, v7) is True


@pytest.mark.parametrize("value", ["joint_v1", "joint_v1+ab"])
def test_ac12_v7_manifest_is_incompatible_with_v8_non_default(value):
    v7 = _man(7, policy="fused_v1")
    cur = _man(8, value, "worker", policy="fused_v1")
    assert P.is_compatible(v7, cur) is False
    assert P.is_compatible(cur, v7) is False


@pytest.mark.parametrize("old", [1, 2, 3, 4, 5, 6, 7])
def test_ac12_v1_to_v7_versus_v8(old):
    cur_default = _man(8, "per_query", "worker")
    cur_joint = _man(8, "joint_v1", "worker")
    assert P.is_compatible(_man(old), cur_default) is True
    assert P.is_compatible(_man(old), cur_joint) is False


def test_ac12_unknown_never_pools_with_anything_including_itself():
    unk = _man(8)                                       # value missing
    for other in (_man(8, "per_query", "worker"), _man(8, "joint_v1", "worker"), _man(8), _man(7),
                  _man(6)):
        assert P.is_compatible(unk, other) is False
        assert P.is_compatible(other, unk) is False
    assert P.is_compatible(_man(8, "bogus", "worker"), _man(8, "bogus", "worker")) is False


def _write_existing(tmp_path, model, bench, manifest):
    d = tmp_path / model
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{bench}.jsonl").write_text('{"id":"x"}\n')
    (d / f"{bench}.manifest.json").write_text(json.dumps(manifest))


def test_ac12_clean_stale_never_archives_a_v7_row_for_the_missing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_existing(tmp_path, "m", "aime", _man(7, policy="fused_v1"))
    monkeypatch.setattr(P, "current_manifest_lite", lambda m, profile, **k:
                        _man(8, "per_query", "worker", policy="fused_v1"))
    acts = G.provenance_precheck(["m"], ["aime"], profile="deployed", clean_stale=True)
    assert acts == []
    assert (tmp_path / "m" / "aime.jsonl").exists()
    assert (tmp_path / "m" / "aime.manifest.json").exists()


def test_ac12_resume_refuses_a_v7_row_under_joint_v1(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_existing(tmp_path, "m", "aime", _man(7, policy="fused_v1"))
    monkeypatch.setattr(P, "current_manifest_lite", lambda m, profile, **k:
                        _man(8, "joint_v1", "worker", policy="fused_v1"))
    acts = G.provenance_precheck(["m"], ["aime"], profile="deployed", clean_stale=False)
    assert acts == [("m", "aime", "stale")]
    assert (tmp_path / "m" / "aime.jsonl").exists()


def test_ac12_resume_refuses_a_v8_row_with_a_missing_value(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_existing(tmp_path, "m", "aime", _man(8, policy="fused_v1"))   # no scan value
    monkeypatch.setattr(P, "current_manifest_lite", lambda m, profile, **k:
                        _man(8, "per_query", "worker", policy="fused_v1"))
    assert G.provenance_precheck(["m"], ["aime"], profile="deployed") == [("m", "aime", "stale")]


# --------------------------------------------------------------------------- compare.py
def _manifest(model, bench, *, tune=None, version=8, scan=None, source="worker", draft="off"):
    p = G.result_path(model, bench, tune=tune).with_suffix(".manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    rt = {"apc_enabled": "0", "draft_kind": draft}
    if version >= 7:
        rt.update({"lazy_prompt_embeddings": False, "attention_policy": "auto"})
    if scan is not None:
        rt[KEY] = scan
        rt[KEY + "_source"] = source
    p.write_text(json.dumps({
        "box": "M5", "sampling_profile": "deployed", "fingerprint_version": version,
        "sampling": {"temperature": 0.4, "thinking_budget": 16384, "max_tokens": 102400},
        "kv": {"kv_bits": 0, "max_kv_cache_size": 131072}, "runtime": rt}))


def test_ac10_compare_refuses_across_values_quality_and_speed(write_rows, tmp_results):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest("A", "math500", scan="per_query")
    _manifest("B", "math500", scan="joint_v1")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and KEY in r["reason"]
    assert CMP.compare("A", "B", "math500", metric="decode_tps")["comparable"] is False


def test_ac10_compare_matched_value_compares_and_pre_v8_reads_per_query(write_rows, tmp_results):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest("A", "math500", version=7)
    _manifest("B", "math500", scan="per_query")
    assert CMP.compare("A", "B", "math500")["comparable"] is True
    _manifest("B", "math500", scan="joint_v1")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and KEY in r["reason"]


@pytest.mark.parametrize("bad", [None, "unknown", "joint_v9"])
def test_ac10_compare_refuses_a_v8_row_with_a_missing_or_unknown_value(write_rows, tmp_results, bad):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest("A", "math500", scan=bad)
    _manifest("B", "math500", scan="per_query")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and KEY in r["reason"]
    # unknown-vs-unknown is not a wildcard either
    _manifest("B", "math500", scan=bad)
    assert CMP.compare("A", "B", "math500")["comparable"] is False


# --------------------------------------------------------------------------- compare_predictor
_IDS = ["a", "b", "c", "d", "e"]


def _pair(tmp_results, *, scan_a="per_query", scan_b="joint_v1", draft_a="off", draft_b="off",
          version_a=8, version_b=8):
    _write_rows("M", "math500", "ta", _cp_rows(_IDS))
    _write_rows("M", "math500", "tb", _cp_rows(_IDS))
    _manifest("M", "math500", tune="ta", scan=scan_a, draft=draft_a, version=version_a)
    _manifest("M", "math500", tune="tb", scan=scan_b, draft=draft_b, version=version_b)


def test_ac10_predictor_must_differ_keys_gain_the_key():
    assert KEY in CP._MUST_DIFFER_KEYS


def test_ac10_predictor_scan_mode_accepts_the_pair_and_pre_v8_baseline(tmp_results):
    _pair(tmp_results)
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ=KEY)
    assert r["comparable"] is True, r
    assert r["must_differ"] == KEY
    _pair(tmp_results, scan_a=None, version_a=7)
    assert CP.compare_predictor("M", "math500", "ta", "tb", must_differ=KEY)["comparable"] is True


def test_ac10_predictor_scan_mode_refuses_same_and_unresolved(tmp_results):
    _pair(tmp_results, scan_a="joint_v1", scan_b="joint_v1")
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ=KEY)
    assert r["comparable"] is False and "SAME" in r["reason"]
    _pair(tmp_results, scan_a=None)
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ=KEY)
    assert r["comparable"] is False and "unrecorded" in r["reason"]


def test_ac10_predictor_scan_mode_requires_draft_kind_to_match(tmp_results):
    _pair(tmp_results, draft_a="off", draft_b="mtp")
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ=KEY)
    assert r["comparable"] is False and "draft_kind" in r["reason"]


def test_ac10_predictor_default_mode_requires_the_scan_to_match(tmp_results):
    _pair(tmp_results, draft_a="off", draft_b="mtp")      # scan differs, draft differs
    r = CP.compare_predictor("M", "math500", "ta", "tb")
    assert r["comparable"] is False and KEY in r["reason"]
    _pair(tmp_results, scan_a="per_query", scan_b="per_query", draft_a="off", draft_b="mtp")
    assert CP.compare_predictor("M", "math500", "ta", "tb")["comparable"] is True


def test_ac10_predictor_unknown_scan_is_refused_in_default_mode(tmp_results):
    _pair(tmp_results, scan_a=None, scan_b="per_query", draft_a="off", draft_b="mtp")
    r = CP.compare_predictor("M", "math500", "ta", "tb")
    assert r["comparable"] is False and KEY in r["reason"]


def test_ac10_predictor_cli_choice(tmp_results):
    _pair(tmp_results)
    assert CP.main(["--model", "M", "--bench", "math500", "--tune-a", "ta", "--tune-b", "tb",
                    "--must-differ", KEY]) == 0


# --------------------------------------------------------------------------- worker facts
def test_worker_serving_facts_reads_the_three_flags_from_the_matching_worker(tmp_path):
    argv = _WORKER + ["--draft-kind", "mtp", "--mtp-verify-scan", "joint_v1", "--mtp-verify-ab"]
    got = P.worker_serving_facts("modelX", _registry(tmp_path), worker_lookup=lambda: [argv])
    assert got == {"model": "caslca/modelX-4bit", "draft_kind": "mtp",
                   "mtp_verify_scan": "joint_v1", "mtp_verify_ab": True}
    plain = P.worker_serving_facts("modelX", _registry(tmp_path), worker_lookup=lambda: [_WORKER])
    assert plain["mtp_verify_scan"] is None and plain["mtp_verify_ab"] is False


def test_worker_serving_facts_none_without_a_matching_worker_and_refuses_ambiguity(tmp_path):
    reg = _registry(tmp_path)
    assert P.worker_serving_facts("modelX", reg, worker_lookup=lambda: None) is None
    other = ["python", "-m", "mlx_vlm.server", "--model", "caslca/other"]
    assert P.worker_serving_facts("modelX", reg, worker_lookup=lambda: [other]) is None
    assert P.worker_serving_facts("nope", reg, worker_lookup=lambda: [_WORKER]) is None
    with pytest.raises(P.ServingStateError):
        P.worker_serving_facts("modelX", reg, worker_lookup=lambda: [_WORKER, _WORKER])
