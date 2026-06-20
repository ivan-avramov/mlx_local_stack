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
    model_footprint_gb = 30.0
    system_peak_gb = 45.0
    peak_rss_gb = 0.0

def test_calibrate_returns_positive_cpt():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0

def test_main_writes_results(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    rc = R.main(["--model", "m", "--grid", "160000,192000"])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "m", "capacity_retrieval.json")))
    assert out["model"] == "m" and out["axis"] == "capacity_retrieval"
    assert len(out["records"]) == 2
