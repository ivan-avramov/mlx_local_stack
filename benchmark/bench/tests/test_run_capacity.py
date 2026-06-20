import json, os
import bench.run_capacity as R

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
