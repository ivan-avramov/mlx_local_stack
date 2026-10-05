"""M57 amendment 1, stack items S1-S5 (review round 1)."""
import json
import sys
import types

import pytest
import yaml

import bench.compare as CMP
import bench.compare_predictor as CP
import bench.generate as G
import bench.provenance as P
from bench.tests.test_compare import _rows as _cmp_rows
from bench.tests.test_compare_predictor import _rows as _cp_rows, _write_rows

_W = "python mlx_vlm.server --model caslca/modelX-4bit --port 8091"


def _registry(tmp_path, **extra):
    entry = {"name": "modelX", "hf_path": "caslca/modelX-4bit", **extra}
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump({"models": [entry]}))
    return str(p)


def _man(v, **rt):
    return {"sampling_profile": "deployed", "fingerprint_version": v, "sampling": {}, "kv": {},
            "runtime": rt}


def _v7(policy="auto", lazy=False):
    return _man(7, attention_policy=policy, lazy_prompt_embeddings=lazy)


# ------------------------------------------------------------------ S1 unresolved never pools
def test_s1_unknown_policy_incompatible_with_known_and_pre_v7():
    assert P.is_compatible(_v7("unknown"), _v7("fused_v1")) is False
    assert P.is_compatible(_v7("fused_v1"), _v7("unknown")) is False
    assert P.is_compatible(_v7("unknown"), _v7("auto")) is False
    assert P.is_compatible(_man(6), _v7("unknown")) is False
    assert P.is_compatible(_v7("unknown"), _v7("unknown")) is False   # T2: no same-run exception


def test_s1_missing_policy_key_on_a_v7_row_is_unresolved_too():
    assert P.is_compatible(_man(7), _v7("auto")) is False


def test_s1_compare_refuses_unresolved_policy(write_rows, tmp_results):
    for m, pol in (("A", "unknown"), ("B", "fused_v1")):
        write_rows(m, "math500", _cmp_rows(["a", "b"]))
        _manifest_cmp(m, policy=pol)
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "attention_policy" in r["reason"]


def _manifest_cmp(model, bench="math500", *, policy="auto", lazy=False, version=7):
    p = G.result_path(model, bench).with_suffix(".manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "box": "M5", "sampling_profile": "deployed", "fingerprint_version": version,
        "sampling": {"temperature": 0.4, "thinking_budget": 16384, "max_tokens": 102400},
        "kv": {"kv_bits": 0, "max_kv_cache_size": 131072},
        "runtime": {"apc_enabled": "0", "draft_kind": "off", "attention_policy": policy,
                    "lazy_prompt_embeddings": lazy}}))


# ------------------------------------------------------------------ S2 every older version
@pytest.mark.parametrize("old", [1, 2, 3, 4, 5, 6])
def test_s2_every_older_version_vs_v7(old):
    assert P.is_compatible(_man(old), _v7("auto")) is True
    assert P.is_compatible(_v7("auto"), _man(old)) is True
    assert P.is_compatible(_man(old), _v7("fused_v1")) is False
    assert P.is_compatible(_v7("fused_v1"), _man(old)) is False
    assert P.is_compatible(_man(old), _v7("auto", lazy=True)) is False


# ------------------------------------------------------------------ S4 worker attribution
def test_s4_exact_model_arg_not_substring(tmp_path):
    longer = "python mlx_vlm.server --model caslca/modelX-4bit-extra --attention-policy fused_v1"
    st = P.registry_attention_policy("modelX", _registry(tmp_path), worker_lookup=lambda: longer)
    assert st == {"attention_policy": "auto", "attention_policy_source": "registry"}


def test_s4_ambiguous_workers_refuse(tmp_path):
    with pytest.raises(RuntimeError, match="more than one"):
        P.registry_attention_policy("modelX", _registry(tmp_path),
                                    worker_lookup=lambda: [_W, _W + " --attention-policy fused_v1"])


def test_s4_other_worker_plus_match_picks_the_match(tmp_path):
    other = "python mlx_vlm.server --model caslca/other"
    st = P.registry_attention_policy(
        "modelX", _registry(tmp_path, attention_policy="fused_v1"),
        worker_lookup=lambda: [other, _W + " --attention-policy fused_v1"])
    assert st == {"attention_policy": "fused_v1", "attention_policy_source": "worker"}


def test_s4_model_equals_form_is_read(tmp_path):
    cmd = "python mlx_vlm.server --model=caslca/modelX-4bit --attention-policy fused_v1"
    st = P.registry_attention_policy("modelX", _registry(tmp_path, attention_policy="fused_v1"),
                                     worker_lookup=lambda: cmd)
    assert st["attention_policy_source"] == "worker"


def test_s4_default_lookup_returns_all_workers(monkeypatch):
    class Pr:
        def __init__(self, c):
            self.info = {"pid": 1, "cmdline": c.split()}
    fake = types.SimpleNamespace(process_iter=lambda attrs: [
        Pr("python mlx_vlm.server --model a"), Pr("vim x"), Pr("python mlx_vlm.server --model b")])
    monkeypatch.setitem(sys.modules, "psutil", fake)
    assert P._worker_cmdlines() == [["python", "mlx_vlm.server", "--model", "a"],
                                    ["python", "mlx_vlm.server", "--model", "b"]]


# ------------------------------------------------------------------ S5 lazy_prompt_embeddings
def test_s5_registry_default_false(tmp_path):
    st = P.registry_lazy_prompt_embeddings("modelX", _registry(tmp_path), worker_lookup=lambda: None)
    assert st == {"lazy_prompt_embeddings": False, "lazy_prompt_embeddings_source": "registry"}


def test_s5_registry_true(tmp_path):
    st = P.registry_lazy_prompt_embeddings("modelX", _registry(tmp_path, lazy_prompt_embeddings=True),
                                           worker_lookup=lambda: None)
    assert st["lazy_prompt_embeddings"] is True


def test_s5_worker_bare_flag_true_absent_false(tmp_path):
    reg = _registry(tmp_path, lazy_prompt_embeddings=True)
    st = P.registry_lazy_prompt_embeddings("modelX", reg,
                                           worker_lookup=lambda: _W + " --lazy-prompt-embeddings")
    assert st == {"lazy_prompt_embeddings": True, "lazy_prompt_embeddings_source": "worker"}
    st = P.registry_lazy_prompt_embeddings("modelX", _registry(tmp_path), worker_lookup=lambda: _W)
    assert st == {"lazy_prompt_embeddings": False, "lazy_prompt_embeddings_source": "worker"}


def test_s5_flag_followed_by_other_flag_still_true(tmp_path):
    reg = _registry(tmp_path, lazy_prompt_embeddings=True)
    st = P.registry_lazy_prompt_embeddings(
        "modelX", reg, worker_lookup=lambda: _W + " --lazy-prompt-embeddings --port 1")
    assert st["lazy_prompt_embeddings"] is True


def test_s5_mismatch_refuses_both_ways(tmp_path):
    with pytest.raises(RuntimeError, match="C35 tripwire.*lazy_prompt_embeddings"):
        P.registry_lazy_prompt_embeddings("modelX", _registry(tmp_path, lazy_prompt_embeddings=True),
                                          worker_lookup=lambda: _W)
    with pytest.raises(RuntimeError, match="C35 tripwire.*lazy_prompt_embeddings"):
        P.registry_lazy_prompt_embeddings("modelX", _registry(tmp_path),
                                          worker_lookup=lambda: _W + " --lazy-prompt-embeddings")


def test_s5_ambiguous_workers_refuse(tmp_path):
    with pytest.raises(RuntimeError, match="more than one"):
        P.registry_lazy_prompt_embeddings("modelX", _registry(tmp_path),
                                          worker_lookup=lambda: [_W, _W])


def test_s5_unknown_model_is_unknown(tmp_path):
    st = P.registry_lazy_prompt_embeddings("nope", _registry(tmp_path), worker_lookup=lambda: None)
    assert st["lazy_prompt_embeddings"] == "unknown"


def test_s5_pre_v7_reads_false_default_pre_v7():
    assert P.control_of(_man(6, lazy_prompt_embeddings=True), "lazy_prompt_embeddings") == (
        False, "default-pre-v7")
    assert P.control_of(_v7(lazy=True), "lazy_prompt_embeddings")[0] is True


def test_s5_fingerprint_and_compat():
    fp = P.config_fingerprint(_v7(lazy=True))
    assert fp["runtime"]["lazy_prompt_embeddings"] is True
    assert "lazy_prompt_embeddings" not in P.config_fingerprint(_man(6))["runtime"]
    assert P.is_compatible(_v7(lazy=False), _v7(lazy=True)) is False
    assert P.is_compatible(_v7(lazy=False), _v7(lazy=False)) is True
    assert P.is_compatible(_v7(lazy="unknown"), _v7(lazy=False)) is False


def test_s5_runtime_block_carries_both(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "apc_state", lambda: {"apc_enabled": "0", "source": "process"})
    monkeypatch.setattr(P, "registry_draft", lambda m, path=None: {"draft_kind": "off"})
    monkeypatch.setattr(P, "session_retention_state", lambda: {})
    monkeypatch.setattr(P, "_worker_cmdlines", lambda: [])
    block = P._runtime_block(None, model="modelX",
                             registry_path=_registry(tmp_path, lazy_prompt_embeddings=True))
    assert block["lazy_prompt_embeddings"] is True
    assert block["lazy_prompt_embeddings_source"] == "registry"


def test_s5_compare_refuses_across_lazy(write_rows, tmp_results):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest_cmp("A", lazy=False)
    _manifest_cmp("B", lazy=True)
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "lazy_prompt_embeddings" in r["reason"]
    assert CMP.compare("A", "B", "math500", metric="decode_tps")["comparable"] is False


def test_s5_compare_pre_v7_equals_lazy_false(write_rows, tmp_results):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest_cmp("A", version=6)
    _manifest_cmp("B", lazy=False)
    assert CMP.compare("A", "B", "math500")["comparable"] is True


# ------------------------------------------------------------------ S3/S5 compare_predictor
_IDS = ["a", "b", "c"]


def _pair(*, draft=("off", "off"), pol=("auto", "auto"), lazy=(False, False), version=7):
    _write_rows("M", "math500", "ta", _cp_rows(_IDS))
    _write_rows("M", "math500", "tb", _cp_rows(_IDS))
    for i, tune in enumerate(("ta", "tb")):
        p = G.result_path("M", "math500", tune=tune).with_suffix(".manifest.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        rt = {"apc_enabled": "0"}
        for k, v in (("draft_kind", draft[i]), ("attention_policy", pol[i]),
                     ("lazy_prompt_embeddings", lazy[i])):
            if v is not None:
                rt[k] = v
        p.write_text(json.dumps({
            "box": "M5", "sampling_profile": "deployed", "fingerprint_version": version,
            "sampling": {"temperature": 0.4, "thinking_budget": 16384, "max_tokens": 102400},
            "kv": {"max_kv_cache_size": 131072}, "runtime": rt}))


def test_s5_predictor_lazy_is_a_selectable_must_differ_key(tmp_results):
    _pair(lazy=(False, True))
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="lazy_prompt_embeddings")
    assert r["comparable"] is True, r
    assert r["must_differ"] == "lazy_prompt_embeddings"


def test_s5_predictor_lazy_mode_requires_other_controls_to_match(tmp_results):
    _pair(lazy=(False, True), pol=("auto", "fused_v1"))
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="lazy_prompt_embeddings")
    assert r["comparable"] is False and "attention_policy" in r["reason"]
    _pair(lazy=(False, True), draft=("off", "mtp"))
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="lazy_prompt_embeddings")
    assert r["comparable"] is False and "draft_kind" in r["reason"]


def test_s5_predictor_default_mode_requires_lazy_to_match(tmp_results):
    _pair(draft=("off", "mtp"), lazy=(False, True))
    r = CP.compare_predictor("M", "math500", "ta", "tb")
    assert r["comparable"] is False and "lazy_prompt_embeddings" in r["reason"]


def test_s5_predictor_cli_accepts_lazy(tmp_results):
    _pair(lazy=(False, True))
    assert CP.main(["--model", "M", "--bench", "math500", "--tune-a", "ta", "--tune-b", "tb",
                    "--must-differ", "lazy_prompt_embeddings"]) == 0


@pytest.mark.parametrize("bad", [None, "unknown"])
def test_s3_attention_mode_refuses_two_unknown_or_missing_draft_kind(tmp_results, bad):
    _pair(draft=(bad, bad), pol=("auto", "fused_v1"))
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="attention_policy")
    assert r["comparable"] is False and "draft_kind" in r["reason"]


@pytest.mark.parametrize("bad", [None, "unknown"])
def test_s3_attention_mode_refuses_one_unknown_draft_kind(tmp_results, bad):
    _pair(draft=("off", bad), pol=("auto", "fused_v1"))
    r = CP.compare_predictor("M", "math500", "ta", "tb", must_differ="attention_policy")
    assert r["comparable"] is False and "draft_kind" in r["reason"]


def test_s3_default_mode_refuses_unknown_draft_kind_and_unresolved_policy(tmp_results):
    _pair(draft=("unknown", "mtp"))
    r = CP.compare_predictor("M", "math500", "ta", "tb")
    assert r["comparable"] is False and "draft_kind" in r["reason"]
    _pair(draft=("off", "mtp"), pol=("unknown", "unknown"))
    r = CP.compare_predictor("M", "math500", "ta", "tb")
    assert r["comparable"] is False and "attention_policy" in r["reason"]


def test_s3_lazy_unknown_on_both_sides_refused_in_every_mode(tmp_results):
    _pair(draft=("off", "mtp"), lazy=("unknown", "unknown"))
    r = CP.compare_predictor("M", "math500", "ta", "tb")
    assert r["comparable"] is False and "lazy_prompt_embeddings" in r["reason"]
