import bench.capacity_ladder as L

class FakeDriver:
    def __init__(self, footprints):  # footprint per call, GB
        self.footprints = list(footprints); self.calls = 0
    def complete(self, model, messages, params, timeout=3600):
        self.calls += 1
        return {"content": "XKRZ0A7Q, XKRZ1B7Q, XKRZ2C7Q, XKRZ3D7Q, XKRZ4E7Q",
                "prompt_tokens": 1000, "prefill_s": 5.0, "prefill_tps": 200,
                "decode_tps": 9.5, "peak_mem_gb": 40.0}

class FakeSampler:
    """sampler_factory returns one of these per rung; peak_rss_gb (the GATE metric) is
    scripted via a shared seq. system_peak_gb is a fixed secondary value."""
    seq = None
    def __init__(self, **kw): self._rss = next(FakeSampler.seq)
    def __enter__(self): return self
    def __exit__(self, *a): pass
    system_peak_gb = 20.0
    @property
    def peak_rss_gb(self): return self._rss

def test_ladder_stops_at_gate(monkeypatch):
    # peak_rss seq 30,38,48,99 → 3rd rung (224K) RSS=48 > 46GB gate → stops there
    FakeSampler.seq = iter([30.0, 38.0, 48.0, 99.0])
    recs = L.run_ladder(FakeDriver([]), "m", chars_per_token=4.0,
                        idle_baseline_gb=0.0, model_pid=99999,
                        sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000, 224000]  # stopped after the fail
    assert recs[0]["fits"] and recs[1]["fits"]
    assert recs[2]["fits"] is False
    assert recs[2]["peak_rss_gb"] == 48.0          # gate metric
    assert recs[0]["retrieval_acc"] == 1.0  # all 5 needles echoed by FakeDriver

def test_ladder_all_fit(monkeypatch):
    FakeSampler.seq = iter([30.0, 33.0, 36.0, 40.0])
    recs = L.run_ladder(FakeDriver([]), "m", chars_per_token=4.0,
                        idle_baseline_gb=0.0, model_pid=99999,
                        sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000, 224000, 256000]
    assert all(r["fits"] for r in recs)
    assert recs[3]["peak_rss_gb"] == 40.0
