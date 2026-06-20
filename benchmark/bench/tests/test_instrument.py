import bench.instrument as I

def test_sampler_tracks_absolute_peak(monkeypatch):
    # Sampler now tracks absolute peaks only; footprint-vs-idle is the caller's job.
    seq = iter([10.0, 10.0, 55.0, 30.0])  # seed value then poll values; peak=55
    monkeypatch.setattr(I, "system_used_gb", lambda: next(seq))
    s = I.MemorySampler(interval=0.001)
    with s:
        import time; time.sleep(0.02)
    assert s.system_peak_gb == 55.0

def test_perfrecord_defaults():
    r = I.PerfRecord(ctx=256000)
    assert r.ctx == 256000 and r.bottleneck == "unknown"
