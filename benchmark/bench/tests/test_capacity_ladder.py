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
    """sampler_factory returns one of these per L; footprint scripted via a shared list."""
    seq = None
    def __init__(self, **kw): self.fp = next(FakeSampler.seq)
    def __enter__(self): return self
    def __exit__(self, *a): pass
    model_footprint_gb = 0.0
    system_peak_gb = 0.0
    peak_rss_gb = 0.0
    def __getattribute__(self, k):
        if k == "model_footprint_gb": return object.__getattribute__(self, "fp")
        return object.__getattribute__(self, k)

def test_ladder_stops_at_gate(monkeypatch):
    FakeSampler.seq = iter([30.0, 38.0, 48.0, 99.0])  # 3rd L (224K) trips 46GB gate
    recs = L.run_ladder(FakeDriver([]), "m", chars_per_token=4.0,
                        sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000, 224000]  # stopped after the fail
    assert recs[0]["fits"] and recs[1]["fits"]
    assert recs[2]["fits"] is False
    assert recs[0]["retrieval_acc"] == 1.0  # all 5 needles echoed by FakeDriver

def test_ladder_all_fit(monkeypatch):
    FakeSampler.seq = iter([30.0, 33.0, 36.0, 40.0])
    recs = L.run_ladder(FakeDriver([]), "m", chars_per_token=4.0,
                        sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000, 224000, 256000]
    assert all(r["fits"] for r in recs)
