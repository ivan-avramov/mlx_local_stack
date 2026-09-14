import re
import bench.capacity_ladder as L

class FakeDriver:
    """complete() returns a scripted MLX peak (peak_mem_gb) per call -- the memory metric."""
    def __init__(self, mlx_peaks):
        self.peaks = iter(mlx_peaks)
    def complete(self, model, messages, params, timeout=3600):
        # Extract the actual planted needles from the prompt instead of hardcoding
        found = re.findall(r"is ([A-Z0-9]{8})\.", messages[-1]["content"])
        return {"content": ", ".join(found),
                "prompt_tokens": 1000, "completion_tokens": 10, "finish_reason": "stop", "prefill_s": 5.0, "prefill_tps": 200,
                "decode_tps": 9.5, "peak_mem_gb": next(self.peaks)}

class FakeSampler:
    """Provides the steady-state RSS / system peak (reported, NOT the gate)."""
    def __init__(self, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    peak_rss_gb = 20.0
    system_peak_gb = 25.0

_PARAMS = {"max_tokens": 256, "temperature": 0.0}


def test_ladder_all_fit():
    recs = L.run_ladder(FakeDriver([30.0, 33.0, 36.0, 40.0]), "m", chars_per_token=4.0,
                        idle_baseline_gb=0.0, model_pid=99999, params=_PARAMS,
                        sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000, 224000, 256000]
    assert all(r["within_memory_target"] for r in recs)
    assert recs[3]["server_peak_gb"] == 40.0

def test_ladder_oom_recorded():
    # driver raises (hard OOM) on the 2nd rung → recorded unscored error + error, then stops
    class OOMDriver:
        def __init__(self): self.n = 0
        def complete(self, *a, **k):
            self.n += 1
            if self.n >= 2:
                raise RuntimeError("HTTP Error 500: Internal Server Error")
            return {"content": "XKRZ0A7Q", "prompt_tokens": 1000, "completion_tokens": 10, "finish_reason": "stop", "peak_mem_gb": 30.0,
                    "prefill_s": 5.0, "prefill_tps": 200, "decode_tps": 9.5}
    recs = L.run_ladder(OOMDriver(), "m", chars_per_token=4.0, idle_baseline_gb=0.0,
                        model_pid=99999, params=_PARAMS, sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000]
    assert recs[0]["within_memory_target"] is True
    assert recs[1]["within_memory_target"] is None and "error" in recs[1]


class DraftDriver:
    """Reports speculative-decoding counters in raw_timings on every completion."""
    def complete(self, model, messages, params, timeout=3600):
        found = re.findall(r"is ([A-Z0-9]{8})\.", messages[-1]["content"])
        return {"content": ", ".join(found),
                "prompt_tokens": 1000, "completion_tokens": 10, "finish_reason": "stop", "prefill_s": 5.0, "prefill_tps": 200,
                "decode_tps": 9.5, "peak_mem_gb": 30.0,
                "raw_timings": {"draft_kind": "mtp", "draft_rounds": 2,
                                "draft_n": 20, "draft_n_accepted": 15}}


def test_ladder_draft_and_acceptance_present_when_raw_timings_has_draft():
    recs = L.run_ladder(DraftDriver(), "m", chars_per_token=4.0, idle_baseline_gb=0.0,
                        model_pid=99999, params=_PARAMS, grid=(160000,),
                        sampler_factory=FakeSampler)
    assert recs[0]["draft"] == {"draft_kind": "mtp", "draft_rounds": 2,
                                "draft_n": 20, "draft_n_accepted": 15}
    assert recs[0]["acceptance"] == round(15 / 20, 4)


def test_ladder_draft_and_acceptance_none_when_no_raw_timings():
    recs = L.run_ladder(FakeDriver([30.0]), "m", chars_per_token=4.0, idle_baseline_gb=0.0,
                        model_pid=99999, params=_PARAMS, grid=(160000,),
                        sampler_factory=FakeSampler)
    assert recs[0]["draft"] is None
    assert recs[0]["acceptance"] is None


def test_ladder_oom_rung_has_draft_and_acceptance_none():
    class OOMDriver:
        def complete(self, *a, **k):
            raise RuntimeError("HTTP Error 500: Internal Server Error")
    recs = L.run_ladder(OOMDriver(), "m", chars_per_token=4.0, idle_baseline_gb=0.0,
                        model_pid=99999, params=_PARAMS, grid=(160000,),
                        sampler_factory=FakeSampler)
    assert recs[0]["within_memory_target"] is None
    assert recs[0]["draft"] is None
    assert recs[0]["acceptance"] is None


# ---------------------------------------------------------------------------
# M41 FIX1 F1: one progress line per rung (review defect 1)
# ---------------------------------------------------------------------------

def test_ladder_prints_one_progress_line_per_rung(capsys):
    L.run_ladder(FakeDriver([30.0, 33.0, 36.0, 40.0]), "m", chars_per_token=4.0,
                 idle_baseline_gb=0.0, model_pid=99999, params=_PARAMS,
                 sampler_factory=FakeSampler)
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("[capacity] rung ")]
    assert len(lines) == 4
    assert "ctx=160000" in lines[0]
    assert "server_peak_gb=" in lines[0]
    assert "within_memory_target=" in lines[0]
    assert "prefill_s=" in lines[0]
    assert "error=" in lines[0]


def test_ladder_prints_progress_line_on_error_rung(capsys):
    class OOMDriver:
        def complete(self, *a, **k):
            raise RuntimeError("HTTP Error 500: Internal Server Error")
    L.run_ladder(OOMDriver(), "m", chars_per_token=4.0, idle_baseline_gb=0.0,
                model_pid=99999, params=_PARAMS, grid=(160000,),
                sampler_factory=FakeSampler)
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("[capacity] rung ")]
    assert len(lines) == 1
    assert "error=RuntimeError" in lines[0]


# ---------------------------------------------------------------------------
# M41 FIX1 F2: request_timeout threading + error_kind on the request failure row
# ---------------------------------------------------------------------------

def test_ladder_request_timeout_forwarded_to_driver():
    seen = []

    class TimeoutRecordingDriver:
        def complete(self, model, messages, params, timeout=3600):
            seen.append(timeout)
            return {"content": "", "prompt_tokens": 1000, "completion_tokens": 10, "finish_reason": "stop", "prefill_s": 5.0,
                    "prefill_tps": 200, "decode_tps": 9.5, "peak_mem_gb": 30.0}

    L.run_ladder(TimeoutRecordingDriver(), "m", chars_per_token=4.0,
                 idle_baseline_gb=0.0, model_pid=99999, params=_PARAMS,
                 grid=(160000,), sampler_factory=FakeSampler, request_timeout=1234)
    assert seen == [1234]


def test_ladder_error_kind_timeout():
    class TimeoutDriver:
        def complete(self, *a, **k):
            raise TimeoutError("timed out")
    recs = L.run_ladder(TimeoutDriver(), "m", chars_per_token=4.0, idle_baseline_gb=0.0,
                        model_pid=99999, params=_PARAMS, grid=(160000,),
                        sampler_factory=FakeSampler)
    assert recs[0]["error_kind"] == "timeout"


def test_ladder_error_kind_oom_or_disconnect():
    class OOMDriver:
        def complete(self, *a, **k):
            raise RuntimeError("HTTP Error 500: Internal Server Error")
    recs = L.run_ladder(OOMDriver(), "m", chars_per_token=4.0, idle_baseline_gb=0.0,
                        model_pid=99999, params=_PARAMS, grid=(160000,),
                        sampler_factory=FakeSampler)
    assert recs[0]["error_kind"] == "request_error"


def test_ladder_params_forwarded_to_driver():
    """params dict is forwarded verbatim to driver.complete."""
    received = []

    class RecordParamsDriver:
        def complete(self, model, messages, params, timeout=3600):
            received.append(dict(params))
            return {"content": "XKRZ0A7Q, XKRZ1B7Q, XKRZ2C7Q, XKRZ3D7Q, XKRZ4E7Q",
                    "prompt_tokens": 1000, "completion_tokens": 10, "finish_reason": "stop", "prefill_s": 5.0, "prefill_tps": 200,
                    "decode_tps": 9.5, "peak_mem_gb": 30.0}

    custom_params = {"max_tokens": 256, "temperature": 0.6, "thinking_budget": 256,
                     "top_p": 0.95}
    L.run_ladder(RecordParamsDriver(), "m", chars_per_token=4.0,
                 idle_baseline_gb=0.0, model_pid=99999, params=custom_params,
                 grid=(160000,), sampler_factory=FakeSampler)
    assert len(received) == 1
    assert received[0]["temperature"] == 0.6
    assert received[0]["max_tokens"] == 256
    assert received[0]["thinking_budget"] == 256
