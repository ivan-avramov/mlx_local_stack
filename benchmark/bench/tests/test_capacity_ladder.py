import bench.capacity_ladder as L

class FakeDriver:
    """complete() returns a scripted MLX peak (peak_mem_gb) per call -- the GATE metric."""
    def __init__(self, mlx_peaks):
        self.peaks = iter(mlx_peaks)
    def complete(self, model, messages, params, timeout=3600):
        return {"content": "XKRZ0A7Q, XKRZ1B7Q, XKRZ2C7Q, XKRZ3D7Q, XKRZ4E7Q",
                "prompt_tokens": 1000, "prefill_s": 5.0, "prefill_tps": 200,
                "decode_tps": 9.5, "peak_mem_gb": next(self.peaks)}

class FakeSampler:
    """Provides the steady-state RSS / system peak (reported, NOT the gate)."""
    def __init__(self, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    peak_rss_gb = 20.0
    system_peak_gb = 25.0

def test_ladder_stops_at_gate():
    # MLX peaks 30,38,48,99 → 3rd rung (224K) peak=48 > 46GB gate → stops there
    recs = L.run_ladder(FakeDriver([30.0, 38.0, 48.0, 99.0]), "m", chars_per_token=4.0,
                        idle_baseline_gb=0.0, model_pid=99999, sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000, 224000]  # stopped after the fail
    assert recs[0]["fits"] and recs[1]["fits"]
    assert recs[2]["fits"] is False
    assert recs[2]["server_peak_gb"] == 48.0       # gate metric = MLX peak (the spike)
    assert recs[0]["peak_rss_gb"] == 20.0          # steady-state ALSO reported
    assert recs[0]["retrieval_acc"] == 1.0  # all 5 needles echoed by FakeDriver

def test_ladder_all_fit():
    recs = L.run_ladder(FakeDriver([30.0, 33.0, 36.0, 40.0]), "m", chars_per_token=4.0,
                        idle_baseline_gb=0.0, model_pid=99999, sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000, 224000, 256000]
    assert all(r["fits"] for r in recs)
    assert recs[3]["server_peak_gb"] == 40.0

def test_ladder_oom_recorded():
    # driver raises (hard OOM) on the 2nd rung → recorded fits=False + error, then stops
    class OOMDriver:
        def __init__(self): self.n = 0
        def complete(self, *a, **k):
            self.n += 1
            if self.n >= 2:
                raise RuntimeError("HTTP Error 500: Internal Server Error")
            return {"content": "XKRZ0A7Q", "prompt_tokens": 1000, "peak_mem_gb": 30.0,
                    "prefill_s": 5.0, "prefill_tps": 200, "decode_tps": 9.5}
    recs = L.run_ladder(OOMDriver(), "m", chars_per_token=4.0, idle_baseline_gb=0.0,
                        model_pid=99999, sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000]
    assert recs[0]["fits"] is True
    assert recs[1]["fits"] is False and "error" in recs[1]
