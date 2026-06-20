import bench.instrument as I

def test_sampler_tracks_footprint(monkeypatch):
    seq = iter([10.0, 10.0, 55.0, 30.0])  # baseline=10, peak=55
    monkeypatch.setattr(I, "system_used_gb", lambda: next(seq))
    s = I.MemorySampler(interval=0.001)
    with s:
        import time; time.sleep(0.02)
    assert s.model_footprint_gb == 45.0   # 55 - 10 baseline
    assert s.system_peak_gb == 55.0

def test_perfrecord_defaults():
    r = I.PerfRecord(ctx=256000)
    assert r.ctx == 256000 and r.bottleneck == "unknown"
