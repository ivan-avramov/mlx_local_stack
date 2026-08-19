"""Unit tests for the D6 session-mitigation probe (`m1/session_mitigation_probe.py`).

No mlx server is started here -- subprocess, HTTP, and the worker log are all mocked/canned. What
IS exercised for real: the four verdict functions (each criterion's pass AND fail side), the
refuse-if-port-busy guards (top-level campaign-port refusal + per-worker probe-port refusal),
`/metrics` payload parsing against a canned envelope matching the real fork schema, and that
teardown runs even when the worker body raises.
"""
import json
import subprocess

import pytest

from m1 import session_mitigation_probe as P


# --------------------------------------------------------------------------- verdict: footprint


def test_footprint_pass_when_saving_exceeds_threshold():
    v = P.verdict_footprint(off_peak_gb=30.0, on_peak_gb=24.0, n_sessions=3, min_saving_gb=1.0)
    assert v["saved_total_gb"] == pytest.approx(6.0)
    assert v["saved_per_session_gb"] == pytest.approx(2.0)
    assert v["pass"] is True


def test_footprint_fail_when_saving_below_threshold():
    v = P.verdict_footprint(off_peak_gb=25.0, on_peak_gb=24.5, n_sessions=3, min_saving_gb=1.0)
    assert v["saved_per_session_gb"] == pytest.approx(0.5 / 3, abs=1e-3)
    assert v["pass"] is False


def test_footprint_fail_when_on_is_actually_worse():
    v = P.verdict_footprint(off_peak_gb=25.0, on_peak_gb=27.0, n_sessions=3)
    assert v["saved_total_gb"] < 0
    assert v["pass"] is False


# --------------------------------------------------------------------------- verdict: resume tax


def test_resume_tax_pass_under_budget():
    v = P.verdict_resume_tax(off_ttft_s=0.500, on_ttft_s=1.200, max_added_ms=2000.0)
    assert v["added_ms"] == pytest.approx(700.0)
    assert v["pass"] is True


def test_resume_tax_fail_over_budget():
    v = P.verdict_resume_tax(off_ttft_s=0.500, on_ttft_s=3.000, max_added_ms=2000.0)
    assert v["added_ms"] == pytest.approx(2500.0)
    assert v["pass"] is False


def test_resume_tax_fails_closed_on_missing_ttft():
    v = P.verdict_resume_tax(off_ttft_s=None, on_ttft_s=1.0)
    assert v["pass"] is False
    assert v["added_ms"] is None
    assert "note" in v


# --------------------------------------------------------------------------- verdict: refloor spike


def test_refloor_spike_pass_under_gate():
    v = P.verdict_refloor_spike(peak_before_gb=20.0, peak_after_gb=25.0, gate_gb=46.0, warn_gb=42.0)
    assert v["spike_gb"] == pytest.approx(5.0)
    assert v["pass"] is True
    assert v["warn"] is False
    assert "warning" not in v


def test_refloor_spike_fail_over_gate():
    v = P.verdict_refloor_spike(peak_before_gb=40.0, peak_after_gb=48.0, gate_gb=46.0, warn_gb=42.0)
    assert v["pass"] is False


def test_refloor_spike_warns_before_failing():
    v = P.verdict_refloor_spike(peak_before_gb=38.0, peak_after_gb=43.0, gate_gb=46.0, warn_gb=42.0)
    assert v["pass"] is True
    assert v["warn"] is True
    assert "warning" in v


# --------------------------------------------------------------------------- verdict: eviction thrash


def test_eviction_no_thrash_passes():
    ratios = {"a": [0.9, 0.85], "b": [0.95, 0.7]}
    v = P.verdict_eviction_thrash(ratios, threshold=0.5)
    assert v["n_below_threshold"] == 0
    assert v["pass"] is True


def test_eviction_thrash_fails_when_alternating_evicts():
    # every revisit comes back with ~0 reuse -> the OTHER session evicted it every turn
    ratios = {"a": [0.02, 0.0], "b": [0.01, 0.03]}
    v = P.verdict_eviction_thrash(ratios, threshold=0.5)
    assert v["n_below_threshold"] == 4
    assert v["pass"] is False


def test_eviction_thrash_fails_closed_on_no_data():
    v = P.verdict_eviction_thrash({"a": [], "b": []}, threshold=0.5)
    assert v["n_checked"] == 0
    assert v["pass"] is False  # no data is not evidence of no thrash


def test_eviction_reuse_ratios_excludes_first_turn_per_session():
    turns = [
        {"chat_id": "a", "prompt_tokens": 100, "cached_tokens": 0},   # a's first turn: excluded
        {"chat_id": "b", "prompt_tokens": 100, "cached_tokens": 0},   # b's first turn: excluded
        {"chat_id": "a", "prompt_tokens": 200, "cached_tokens": 180},  # a's revisit: 0.9
        {"chat_id": "b", "prompt_tokens": 200, "cached_tokens": 20},   # b's revisit: 0.1
    ]
    ratios = P.eviction_reuse_ratios(turns, ("a", "b"))
    assert ratios["a"] == pytest.approx([0.9])
    assert ratios["b"] == pytest.approx([0.1])


# --------------------------------------------------------------------------- overall verdict


def test_overall_enable_when_all_pass():
    report = {
        "footprint": {"pass": True}, "resume_tax": {"pass": True},
        "refloor_spike": {"pass": True}, "eviction_thrash": {"pass": True},
    }
    ov = P.overall_verdict(report)
    assert ov["verdict"] == "ENABLE"
    assert ov["failing_points"] == []


def test_overall_do_not_enable_names_failing_points():
    report = {
        "footprint": {"pass": True}, "resume_tax": {"pass": False},
        "refloor_spike": {"pass": True}, "eviction_thrash": {"pass": False},
    }
    ov = P.overall_verdict(report)
    assert ov["verdict"] == "DO-NOT-ENABLE"
    assert ov["failing_points"] == ["eviction_thrash", "resume_tax"]


def test_overall_no_phases_run_is_distinct_from_enable():
    ov = P.overall_verdict({})
    assert ov["verdict"] == "NO-PHASES-RUN"
    assert ov["checks"] == {}


def test_overall_partial_phases_only_checks_what_ran():
    report = {"footprint": {"pass": True}}
    ov = P.overall_verdict(report)
    assert ov["checks"] == {"footprint_drop": True}
    assert ov["verdict"] == "ENABLE"


# --------------------------------------------------------------------------- /metrics parsing


_CANNED_METRICS_PAYLOAD = {
    "latest": {
        "timestamp_unix": 1755500000.0,
        "endpoint": "/v1/chat/completions",
        "model": "caslca/Ornith-1.0-35B-mlx-uniform-4bit",
        "stream": False,
        "backend": "cached_session",
        "prompt_tokens": 3120,
        "completion_tokens": 84,
        "generated_tokens": 84,
        "reasoning_tokens": 0,
        "total_tokens": 3204,
        "prompt_eval_time_s": 1.834,
        "prefill_tok_s": 1701.2,
        "ttft_s": 1.91,
        "decode_elapsed_s": 0.84,
        "request_elapsed_s": 2.75,
        "request_tok_s": 30.5,
        "decode_tok_s": 100.0,
        "peak_memory_gb": 24.71,
        "finish_reason": "stop",
        "session_id": "d6-probe-on-s0",
        "cached_tokens": 3005,
    },
    "recent": [],
    "summary": {"uptime_s": 12.0, "requests_started": 1, "requests_completed": 1,
                "requests_failed": 0, "in_flight": 0},
    "server": {"loaded_model": "caslca/Ornith-1.0-35B-mlx-uniform-4bit"},
}


def test_parse_metrics_latest_extracts_the_fields_the_probe_uses():
    m = P.parse_metrics_latest(_CANNED_METRICS_PAYLOAD)
    assert m["session_id"] == "d6-probe-on-s0"
    assert m["cached_tokens"] == 3005
    assert m["prompt_tokens"] == 3120
    assert m["ttft_s"] == pytest.approx(1.91)
    assert m["prompt_eval_time_s"] == pytest.approx(1.834)
    assert m["peak_memory_gb"] == pytest.approx(24.71)
    assert m["finish_reason"] == "stop"


def test_parse_metrics_latest_tolerates_missing_latest():
    m = P.parse_metrics_latest({"latest": None, "summary": {}})
    assert m["cached_tokens"] == 0
    assert m["peak_memory_gb"] == 0.0
    assert m["session_id"] is None
    assert m["ttft_s"] is None


def test_parse_metrics_latest_tolerates_empty_payload():
    m = P.parse_metrics_latest({})
    assert m["prompt_tokens"] == 0
    assert m["finish_reason"] is None


# --------------------------------------------------------------------------- log-event parsing


def test_count_log_events_parses_evictions_and_shrinks():
    log_text = (
        "2026-08-18 20:00:00 - mlx_vlm.server - INFO - Headroom eviction: dropped "
        "chat_id=d6-probe-evict-a (active=30.10 GiB >= 15% of 48.00 GiB budget)\n"
        "2026-08-18 20:00:05 - mlx_vlm.server - INFO - Session cache shrink-on-retire: "
        "PreallocKVCache offset=1024 freed 250.00 MiB (300.00 -> 50.00 MiB)\n"
        "2026-08-18 20:00:06 - mlx_vlm.server - INFO - Headroom eviction: dropped "
        "chat_id=d6-probe-evict-b (active=31.00 GiB >= 15% of 48.00 GiB budget)\n"
    )
    events = P.count_log_events(log_text)
    assert events["n_evictions"] == 2
    assert events["evicted_chat_ids"] == ["d6-probe-evict-a", "d6-probe-evict-b"]
    assert events["n_shrinks"] == 1


def test_count_log_events_empty_on_quiet_log():
    events = P.count_log_events("nothing interesting here\n")
    assert events == {"n_evictions": 0, "evicted_chat_ids": [], "n_shrinks": 0}


def test_count_log_events_tolerates_none():
    assert P.count_log_events(None) == {"n_evictions": 0, "evicted_chat_ids": [], "n_shrinks": 0}


# --------------------------------------------------------------------------- refuse-if-port-busy


def test_refuse_if_campaign_busy_raises_without_force():
    with pytest.raises(SystemExit, match="one-resident-model"):
        P.refuse_if_campaign_busy(force=False, ports=(8000, 8091), checker=lambda p: p == 8000)


def test_refuse_if_campaign_busy_allows_force():
    busy = P.refuse_if_campaign_busy(force=True, ports=(8000, 8091), checker=lambda p: p == 8000)
    assert busy == [8000]


def test_refuse_if_campaign_busy_quiet_box_returns_empty():
    busy = P.refuse_if_campaign_busy(force=False, ports=(8000, 8091), checker=lambda p: False)
    assert busy == []


def test_worker_handle_start_refuses_busy_probe_port(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "_port_listening", lambda port, **kw: True)
    cfg = P.WorkerConfig(
        hf_path="whatever/model", port=8093, cache_session_max=8,
        chat_id_header=P.CHAT_ID_HEADER, shrink_on=True, evict_headroom_frac=0.0,
        log_path=tmp_path / "w.log", python_exe=tmp_path / "python", mlx_vlm_root=tmp_path,
    )
    handle = P.WorkerHandle(cfg, popen=lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("Popen should never be called when the port is busy")))
    with pytest.raises(RuntimeError, match="probe port 8093 already in use"):
        handle.start()


# --------------------------------------------------------------------------- worker command construction


def _kv_config(**overrides):
    base = dict(
        hf_path="caslca/Ornith-1.0-35B-mlx-uniform-4bit", port=8093, cache_session_max=5,
        chat_id_header=P.CHAT_ID_HEADER, shrink_on=True, evict_headroom_frac=0.0,
        log_path="/tmp/x.log", python_exe="/tmp/py", mlx_vlm_root="/tmp/fork",
        max_kv_cache_size=262144, kv_prealloc_tokens=262144, kv_bits=0,
        kv_quant_scheme=None, quantized_kv_start=0, prefill_step_size=512,
    )
    base.update(overrides)
    import pathlib
    base["log_path"] = pathlib.Path(base["log_path"])
    base["python_exe"] = pathlib.Path(base["python_exe"])
    base["mlx_vlm_root"] = pathlib.Path(base["mlx_vlm_root"])
    return P.WorkerConfig(**base)


def test_build_worker_command_carries_kv_and_d6_flags():
    cmd = P.build_worker_command(_kv_config())
    assert "--model" in cmd and "caslca/Ornith-1.0-35B-mlx-uniform-4bit" in cmd
    assert "--max-kv-size" in cmd and "262144" in cmd
    assert "--kv-prealloc-tokens" in cmd and "262144" in cmd
    assert "--cache-session-shrink" in cmd
    assert cmd[cmd.index("--cache-session-shrink") + 1] == "on"
    assert "--cache-session-evict-headroom-frac" in cmd
    assert cmd[cmd.index("--cache-session-evict-headroom-frac") + 1] == "0.0"
    assert "--cache-chat-id-header" in cmd
    assert cmd[cmd.index("--cache-chat-id-header") + 1] == P.CHAT_ID_HEADER


def test_build_worker_command_shrink_off():
    cmd = P.build_worker_command(_kv_config(shrink_on=False))
    assert cmd[cmd.index("--cache-session-shrink") + 1] == "off"


def test_build_worker_command_omits_falsy_kv_bits_and_scheme():
    cmd = P.build_worker_command(_kv_config(kv_bits=0, kv_quant_scheme=None))
    assert "--kv-bits" not in cmd
    assert "--kv-quant-scheme" not in cmd


def test_build_worker_command_includes_kv_bits_and_scheme_when_set():
    cmd = P.build_worker_command(_kv_config(kv_bits=4, kv_quant_scheme="turboquant"))
    assert "--kv-bits" in cmd and "4" in cmd
    assert "--kv-quant-scheme" in cmd and "turboquant" in cmd
    assert cmd[cmd.index("--kv-quant-scheme") + 1] == "turboquant"


# --------------------------------------------------------------------------- teardown-on-exception


class _FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid
        self.returncode = None
        self.terminated = False
        self.killed = False
        self._alive = True

    def poll(self):
        return None if self._alive else self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self._alive = False
        self.returncode = -9

    def wait(self, timeout=None):
        # terminate() alone "succeeds" in this fake -- mirrors a cooperative process.
        if self.terminated:
            self._alive = False
            self.returncode = 0
            return self.returncode
        raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)


def test_worker_handle_stop_verifies_pid_gone():
    handle = P.WorkerHandle.__new__(P.WorkerHandle)
    handle.proc = _FakeProc()
    handle.teardown_failed = False
    ok = handle.stop()
    assert ok is True
    assert handle.teardown_failed is False
    assert handle.proc.terminated is True


def test_worker_handle_stop_escalates_to_kill_when_terminate_does_not_land():
    class _StubbornProc(_FakeProc):
        def wait(self, timeout=None):
            if self.killed:
                self._alive = False
                self.returncode = -9
                return self.returncode
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)

    handle = P.WorkerHandle.__new__(P.WorkerHandle)
    handle.proc = _StubbornProc()
    handle.teardown_failed = False
    ok = handle.stop()
    assert ok is True
    assert handle.proc.killed is True


def test_worker_handle_stop_flags_teardown_failure_when_pid_survives():
    class _ImmortalProc(_FakeProc):
        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)

        def poll(self):
            return None  # never exits, no matter what

    handle = P.WorkerHandle.__new__(P.WorkerHandle)
    handle.proc = _ImmortalProc()
    handle.teardown_failed = False
    ok = handle.stop()
    assert ok is False
    assert handle.teardown_failed is True


def test_running_worker_tears_down_even_when_body_raises(monkeypatch, tmp_path):
    stopped = []

    class _FakeHandle:
        def __init__(self, cfg):
            self.cfg = cfg

        def start(self):
            return None

        def wait_ready(self, base_url, timeout_s=None):
            return {"status": "healthy", "loaded_model": self.cfg.hf_path}

        def stop(self, timeout_s=15.0):
            stopped.append(self.cfg.port)
            return True

    cfg = _kv_config(port=8093)
    with pytest.raises(ValueError):
        with P.running_worker(cfg, handle_cls=_FakeHandle):
            raise ValueError("boom mid-phase")

    assert stopped == [8093]


def test_running_worker_tears_down_on_the_happy_path_too(tmp_path):
    stopped = []

    class _FakeHandle:
        def __init__(self, cfg):
            self.cfg = cfg

        def start(self):
            return None

        def wait_ready(self, base_url, timeout_s=None):
            return {"status": "healthy", "loaded_model": self.cfg.hf_path}

        def stop(self, timeout_s=15.0):
            stopped.append(self.cfg.port)
            return True

    cfg = _kv_config(port=8093)
    with P.running_worker(cfg, handle_cls=_FakeHandle) as h:
        assert h.cfg.port == 8093
    assert stopped == [8093]


# --------------------------------------------------------------------------- filler prompt sizing


def test_filler_system_prompt_is_distinct_per_session():
    a = P._filler_system_prompt(0, target_tokens=500)
    b = P._filler_system_prompt(1, target_tokens=500)
    assert a != b
    assert "session 0" in a
    assert "session 1" in b


def test_filler_system_prompt_roughly_matches_target_length():
    text = P._filler_system_prompt(0, target_tokens=1000)
    # ~4 chars/token heuristic -- just needs to be in the right ballpark, not exact
    assert 3500 <= len(text) <= 4200
