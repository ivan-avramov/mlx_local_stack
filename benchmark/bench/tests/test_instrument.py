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

def test_find_model_server_pid_picks_highest_rss(monkeypatch):
    import psutil
    class _M:
        def __init__(self, rss): self.rss = rss
    class _P:
        def __init__(self, pid, cmd, rss):
            self.info = {"pid": pid, "cmdline": cmd, "memory_info": _M(rss)}
    procs = [_P(1, ["python", "other"], 10),
             _P(2, ["python", "mlx_vlm.server", "--model", "x"], 5_000_000_000),
             _P(3, ["python", "mlx_vlm.server", "--model", "y"], 20_000_000_000)]
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter(procs))
    assert I.find_model_server_pid() == 3   # highest-RSS match wins
    monkeypatch.setattr(psutil, "process_iter",
                        lambda attrs=None: iter([_P(1, ["python", "other"], 10)]))
    assert I.find_model_server_pid() is None  # no match
