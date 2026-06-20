import json, os
import bench.run_capacity as R
from bench.model_params import params_for

class FakeDriver:
    def preload(self, model, timeout=900): return 1.0
    def complete(self, model, messages, params, timeout=3600):
        # calibration call asks for a known filler; return a prompt_tokens so cpt computes
        return {"content": "XKRZ0A7Q, XKRZ1B7Q, XKRZ2C7Q, XKRZ3D7Q, XKRZ4E7Q",
                "prompt_tokens": 100, "prefill_s": 1.0, "prefill_tps": 100,
                "decode_tps": 9.5, "peak_mem_gb": 40.0}

class FakeSampler:
    def __init__(self, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    system_peak_gb = 45.0
    peak_rss_gb = 35.0   # gate metric: under 46 → fits

def test_calibrate_returns_positive_cpt():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0

def test_main_writes_results(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    # idle=10GB; RSS=35 (gate metric, fits); system_peak=45 → sys_footprint=35 (secondary)
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: 12345)
    rc = R.main(["--model", "m", "--grid", "160000,192000"])
    assert rc == 0
    sc = json.load(open(os.path.join(tmp_path, "m", "capacity_retrieval.json")))
    assert sc["model"] == "m" and sc["axis"] == "capacity_retrieval"
    assert sc["gate_metric"] == "mlx_peak_gb (mx.get_peak_memory, the prefill spike)"
    assert len(sc["records"]) == 2
    assert sc["idle_baseline_gb"] == 10.0
    # verify capacity_ladder.jsonl has one line per rung
    lines = open(os.path.join(tmp_path, "m", "capacity_ladder.jsonl")).readlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["server_peak_gb"] == 40.0 and first["fits"] is True  # MLX-peak gate (40<=46)
    assert first["peak_rss_gb"] == 35.0                               # steady-state reported
    assert first["model_footprint_gb"] == round(45.0 - 10.0, 2)       # 35.0 coarse cross-check


def test_main_passes_bounded_params_to_ladder(tmp_path, monkeypatch):
    """main() builds params from params_for, then bounds max_tokens=256, thinking_budget=256."""
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params") or (a[5] if len(a) > 5 else None)
        return [{"ctx": 160000, "server_peak_gb": 40.0, "peak_rss_gb": 35.0,
                 "system_peak_gb": 45.0, "model_footprint_gb": 35.0,
                 "prefill_s": 1.0, "prefill_tps": 200, "decode_tps": 9.5,
                 "prompt_tokens": 1000, "retrieval_acc": 1.0, "fits": True}]

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: 12345)
    monkeypatch.setattr(R, "run_ladder", fake_ladder)
    R.main(["--model", "gemma-4-26B-A4B-it-QAT-MLX-4bit",
            "--grid", "160000", "--no-preload"])
    assert captured["params"] is not None
    # Must be bounded regardless of model's production max_tokens
    assert captured["params"]["max_tokens"] == 256
    assert captured["params"]["thinking_budget"] == 256
    # Production sampling params must still be present
    base = params_for("gemma-4-26B-A4B-it-QAT-MLX-4bit")
    assert captured["params"]["temperature"] == base["temperature"]
    assert captured["params"]["top_p"] == base["top_p"]
