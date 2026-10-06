"""M57 amendment 2, stack items T1-T4 (review round 2)."""
import json

import pytest
import yaml

import bench.benchmarks as B
import bench.client as C
import bench.generate as G
import bench.paths as paths
import bench.provenance as P

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")   # M58: synthetic models



def _registry(tmp_path, name="m", **extra):
    entry = {"name": name, "hf_path": "caslca/modelX-4bit", **extra}
    p = tmp_path / "r2.yaml"
    p.write_text(yaml.safe_dump({"models": [entry]}))
    return str(p)


_ARGV = ["python", "-m", "mlx_vlm.server", "--model", "caslca/modelX-4bit", "--port", "8091"]


def _man(v, **rt):
    return {"sampling_profile": "deployed", "fingerprint_version": v, "sampling": {}, "kv": {},
            "runtime": rt}


# ------------------------------------------------------------------ T1 refusals stop a run
def test_t1_refusals_are_ServedConfigError_subclasses(tmp_path):
    reg = _registry(tmp_path, attention_policy="fused_v1")
    with pytest.raises(P.ServedConfigError):
        P.registry_attention_policy("m", reg, worker_lookup=lambda: [_ARGV])          # mismatch
    with pytest.raises(P.ServedConfigError):
        P.registry_attention_policy("m", reg, worker_lookup=lambda: [_ARGV, _ARGV])   # ambiguity
    with pytest.raises(P.ServedConfigError):
        P.registry_lazy_prompt_embeddings("m", _registry(tmp_path, lazy_prompt_embeddings=True),
                                          worker_lookup=lambda: [_ARGV])


def _setup_run(tmp_path, monkeypatch, **reg_extra):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    reg = _registry(tmp_path, **reg_extra)
    monkeypatch.setattr(paths, "registry_path", lambda: __import__("pathlib").Path(reg))
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    calls = {"probe": 0, "preload": 0}

    def probe(*a, **k):
        calls["probe"] += 1
        return {"content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
                "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0,
                "finish_reason": "stop", "wall_s": 0.1, "raw_timings": {}}
    monkeypatch.setattr(C, "probe", probe)
    monkeypatch.setattr(C, "preload", lambda m, **k: calls.__setitem__("preload", calls["preload"] + 1) or 0.0)
    return calls


def test_t1_generate_run_refuses_on_worker_registry_disagreement(tmp_path, monkeypatch):
    calls = _setup_run(tmp_path, monkeypatch, attention_policy="fused_v1")
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [_ARGV])    # worker serves auto
    with pytest.raises(P.ServedConfigError):
        G.run(["m"], ["aime"], {})
    assert calls["probe"] == 0 and calls["preload"] == 0
    assert not list(tmp_path.glob("m/*"))                           # no manifest, no rows


def test_t1_generate_run_refuses_on_lazy_disagreement(tmp_path, monkeypatch):
    calls = _setup_run(tmp_path, monkeypatch, lazy_prompt_embeddings=True)
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [_ARGV])
    with pytest.raises(P.ServedConfigError):
        G.run(["m"], ["aime"], {})
    assert calls["probe"] == 0 and not list(tmp_path.glob("m/*"))


def test_t1_generate_run_refuses_on_ambiguous_workers(tmp_path, monkeypatch):
    calls = _setup_run(tmp_path, monkeypatch)
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [_ARGV, _ARGV])
    with pytest.raises(P.ServedConfigError):
        G.run(["m"], ["aime"], {})
    assert calls["probe"] == 0 and not list(tmp_path.glob("m/*"))


def test_t1_generate_run_still_runs_when_worker_matches(tmp_path, monkeypatch):
    calls = _setup_run(tmp_path, monkeypatch, attention_policy="fused_v1")
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [_ARGV + ["--attention-policy", "fused_v1"]])
    G.run(["m"], ["aime"], {})
    assert calls["probe"] == 1
    man = json.loads((tmp_path / "m" / "aime.manifest.json").read_text())
    assert man["runtime"]["attention_policy"] == "fused_v1"
    assert man["runtime"]["attention_policy_source"] == "worker"


# ------------------------------------------------------------------ T2 no same-run exception
def test_t2_two_unknown_values_are_incompatible():
    a = _man(7, attention_policy="unknown", lazy_prompt_embeddings=False)
    assert P.is_compatible(a, dict(a)) is False
    b = _man(7, attention_policy="auto", lazy_prompt_embeddings="unknown")
    assert P.is_compatible(b, dict(b)) is False
    assert P.is_compatible(_man(7), _man(7)) is False     # absent keys read unknown


# ------------------------------------------------------------------ T3 argv, exact tokens
SPACED = ["python", "-m", "mlx_vlm.server", "--model", "/models/my models/m 4bit", "--port", "1"]


def _spaced_registry(tmp_path, **extra):
    entry = {"name": "m", "hf_path": "/models/my models/m 4bit", **extra}
    p = tmp_path / "sp.yaml"
    p.write_text(yaml.safe_dump({"models": [entry]}))
    return str(p)


def test_t3_model_path_with_spaces_matches_and_disagreement_refuses(tmp_path):
    reg = _spaced_registry(tmp_path, attention_policy="fused_v1")
    with pytest.raises(P.ServedConfigError, match="attention_policy"):
        P.registry_attention_policy("m", reg, worker_lookup=lambda: [SPACED])
    st = P.registry_attention_policy("m", reg,
                                     worker_lookup=lambda: [SPACED + ["--attention-policy", "fused_v1"]])
    assert st == {"attention_policy": "fused_v1", "attention_policy_source": "worker"}


def test_t3_equals_forms_for_model_and_flags(tmp_path):
    reg = _spaced_registry(tmp_path, attention_policy="fused_v1", lazy_prompt_embeddings=True)
    argv = ["python", "-m", "mlx_vlm.server", "--model=/models/my models/m 4bit",
            "--attention-policy=fused_v1", "--lazy-prompt-embeddings"]
    assert P.registry_attention_policy("m", reg, worker_lookup=lambda: [argv])[
        "attention_policy_source"] == "worker"
    assert P.registry_lazy_prompt_embeddings("m", reg, worker_lookup=lambda: [argv]) == {
        "lazy_prompt_embeddings": True, "lazy_prompt_embeddings_source": "worker"}


def test_t3_flag_value_that_looks_like_the_flag_is_not_a_flag(tmp_path):
    reg = _spaced_registry(tmp_path)
    argv = SPACED + ["--served-name", "--lazy-prompt-embeddings-x"]
    st = P.registry_lazy_prompt_embeddings("m", reg, worker_lookup=lambda: [argv])
    assert st["lazy_prompt_embeddings"] is False


def test_t3_observation_failure_refuses_but_no_worker_falls_back(tmp_path):
    reg = _registry(tmp_path)

    def boom():
        raise OSError("psutil blew up")
    with pytest.raises(P.ServedConfigError, match="observ"):
        P.registry_attention_policy("m", reg, worker_lookup=boom)
    with pytest.raises(P.ServedConfigError, match="observ"):
        P.registry_lazy_prompt_embeddings("m", reg, worker_lookup=boom)
    for none in (lambda: None, lambda: [], lambda: [["python", "-m", "mlx_vlm.server", "--model", "other"]]):
        st = P.registry_attention_policy("m", reg, worker_lookup=none)
        assert st["attention_policy_source"] == "registry"


# ------------------------------------------------------------------ T4 sdpa counters
def test_t4_row_keeps_sdpa_counters_when_the_server_sends_them(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    r = {"content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
         "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0, "finish_reason": "stop",
         "wall_s": 0.1, "raw_timings": {"sdpa_forced": 12, "sdpa_auto": 3}}
    monkeypatch.setattr(C, "probe", lambda *a, **k: r)
    G.run(["m"], ["aime"], {})
    row = json.loads((tmp_path / "m" / "aime.jsonl").read_text().splitlines()[0])
    assert row["sdpa"] == {"sdpa_forced": 12, "sdpa_auto": 3}


def test_t4_row_has_no_sdpa_key_when_the_server_omits_them(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    r = {"content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
         "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0, "finish_reason": "stop",
         "wall_s": 0.1, "raw_timings": {}}
    monkeypatch.setattr(C, "probe", lambda *a, **k: r)
    G.run(["m"], ["aime"], {})
    row = json.loads((tmp_path / "m" / "aime.jsonl").read_text().splitlines()[0])
    assert "sdpa" not in row


def test_t4_client_probe_keeps_sdpa_in_raw_timings(monkeypatch):
    body = {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7},
            "timings": {"prompt_n": 5, "predicted_per_second": 9.0, "sdpa_forced": 4, "sdpa_auto": 1}}
    absent = dict(body, timings={"prompt_n": 5, "predicted_per_second": 9.0})
    monkeypatch.setattr(C, "_post", lambda path, payload, timeout=3600: body)
    out = C.probe("m", [{"role": "user", "content": "p"}], {})
    assert out["raw_timings"]["sdpa_forced"] == 4 and out["raw_timings"]["sdpa_auto"] == 1
    monkeypatch.setattr(C, "_post", lambda path, payload, timeout=3600: absent)
    out2 = C.probe("m", [{"role": "user", "content": "p"}], {})
    assert "sdpa_forced" not in out2["raw_timings"]
