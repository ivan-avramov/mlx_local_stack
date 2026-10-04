"""v7 (M57, AC11): the fused-attention dispatch policy is provenance.

`attention_policy` changes WHICH attention kernel runs, so rows at different policies never pool
and never compare. Resolution mirrors the C35 draft tripwire: the live worker's command line is
the serving truth, the registry the fallback, and a disagreement refuses the run.
"""
import pytest
import yaml

import bench.provenance as P


def _registry(tmp_path, policy=None):
    entry = {"name": "modelX", "hf_path": "caslca/modelX-4bit"}
    if policy is not None:
        entry["attention_policy"] = policy
    p = tmp_path / "ap_reg.yaml"
    p.write_text(yaml.safe_dump({"models": [entry]}))
    return str(p)


_WORKER = "python mlx_vlm.server --model caslca/modelX-4bit --port 8091"


def test_ac11_fingerprint_version_is_7():
    assert P.FINGERPRINT_VERSION == 7


def test_ac11_registry_default_is_auto_when_field_absent_or_empty(tmp_path):
    for pol in (None, ""):
        st = P.registry_attention_policy("modelX", _registry(tmp_path, pol),
                                         worker_lookup=lambda: None)
        assert st == {"attention_policy": "auto", "attention_policy_source": "registry"}


def test_ac11_registry_value_is_read_when_no_worker(tmp_path):
    st = P.registry_attention_policy("modelX", _registry(tmp_path, "fused_v1"),
                                     worker_lookup=lambda: None)
    assert st == {"attention_policy": "fused_v1", "attention_policy_source": "registry"}


def test_ac11_worker_flag_is_observed_source_worker(tmp_path):
    st = P.registry_attention_policy("modelX", _registry(tmp_path, "fused_v1"),
                                     worker_lookup=lambda: _WORKER + " --attention-policy fused_v1")
    assert st == {"attention_policy": "fused_v1", "attention_policy_source": "worker"}


def test_ac11_worker_without_flag_means_auto(tmp_path):
    st = P.registry_attention_policy("modelX", _registry(tmp_path, None),
                                     worker_lookup=lambda: _WORKER)
    assert st == {"attention_policy": "auto", "attention_policy_source": "worker"}


def test_ac11_mismatch_registry_fused_worker_auto_refuses(tmp_path):
    with pytest.raises(RuntimeError, match="C35 tripwire.*attention_policy"):
        P.registry_attention_policy("modelX", _registry(tmp_path, "fused_v1"),
                                    worker_lookup=lambda: _WORKER)


def test_ac11_mismatch_registry_auto_worker_fused_refuses(tmp_path):
    with pytest.raises(RuntimeError, match="C35 tripwire.*attention_policy"):
        P.registry_attention_policy("modelX", _registry(tmp_path, None),
                                    worker_lookup=lambda: _WORKER + " --attention-policy fused_v1")


def test_ac11_worker_for_another_model_says_nothing(tmp_path):
    st = P.registry_attention_policy(
        "modelX", _registry(tmp_path, "fused_v1"),
        worker_lookup=lambda: "python mlx_vlm.server --model caslca/other --attention-policy auto")
    assert st == {"attention_policy": "fused_v1", "attention_policy_source": "registry"}


def test_ac11_unknown_model_or_unreadable_registry_is_unknown(tmp_path):
    st = P.registry_attention_policy("nope", _registry(tmp_path), worker_lookup=lambda: None)
    assert st["attention_policy"] == "unknown"
    st = P.registry_attention_policy("modelX", str(tmp_path / "missing.yaml"),
                                     worker_lookup=lambda: None)
    assert st["attention_policy"] == "unknown"


def test_ac11_runtime_block_carries_policy_and_source(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "apc_state", lambda: {"apc_enabled": "0", "source": "process"})
    monkeypatch.setattr(P, "registry_draft", lambda m, path=None: {"draft_kind": "off"})
    monkeypatch.setattr(P, "session_retention_state",
                        lambda: {"session_retain_prompt_end": "on", "session_retain_source": "worker"})
    monkeypatch.setattr(P, "_worker_cmdline", lambda: None)
    block = P._runtime_block(None, model="modelX", registry_path=_registry(tmp_path, "fused_v1"))
    assert block["attention_policy"] == "fused_v1"
    assert block["attention_policy_source"] == "registry"


def _man(v, policy=None, source=None):
    rt = {}
    if policy is not None:
        rt["attention_policy"] = policy
    if source is not None:
        rt["attention_policy_source"] = source
    return {"sampling_profile": "deployed", "fingerprint_version": v, "sampling": {}, "kv": {},
            "runtime": rt}


def test_ac11_only_policy_not_source_enters_the_fingerprint():
    fp = P.config_fingerprint(_man(7, "fused_v1", "worker"))
    assert fp["runtime"]["attention_policy"] == "fused_v1"
    assert "attention_policy_source" not in fp["runtime"]
    assert "attention_policy" not in P.config_fingerprint(_man(6, "fused_v1"))["runtime"]
    assert P.is_compatible(_man(7, "auto", "worker"), _man(7, "auto", "registry")) is True
    assert P.is_compatible(_man(7, "auto", "worker"), _man(7, "fused_v1", "worker")) is False


def test_ac11_pre_v7_manifests_normalise_to_auto_default_pre_v7():
    assert P.attention_policy_of(_man(6)) == ("auto", "default-pre-v7")
    assert P.attention_policy_of(_man(2)) == ("auto", "default-pre-v7")
    assert P.attention_policy_of({"runtime": {}}) == ("auto", "default-pre-v7")   # v1: no version key
    # a pre-v7 manifest cannot smuggle a value in
    assert P.attention_policy_of(_man(6, "fused_v1")) == ("auto", "default-pre-v7")
    assert P.attention_policy_of(_man(7, "fused_v1", "worker")) == ("fused_v1", "worker")


def test_ac11_pre_v7_compatible_with_v7_auto_incompatible_with_v7_fused():
    old = _man(6)
    assert P.is_compatible(old, _man(7, "auto", "worker")) is True
    assert P.is_compatible(_man(7, "auto", "registry"), old) is True
    assert P.is_compatible(old, _man(7, "fused_v1", "worker")) is False
    assert P.is_compatible(_man(7, "fused_v1", "registry"), old) is False
    assert P.is_compatible(_man(5), _man(7, "fused_v1", "worker")) is False


def test_ac11_unknown_policy_on_a_v7_row_is_a_wildcard():
    assert P.is_compatible(_man(7, "unknown"), _man(7, "fused_v1", "worker")) is True
