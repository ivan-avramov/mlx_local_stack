"""generate.run must thread a configurable per-probe HTTP timeout to client.probe.

The default 3600s client timeout is shorter than a slow dense model's worst-case generation
(e.g. Qwen3.6-27B at ~13.5 tok/s reaching an ~80K-token thinking budget ≈ 100 min), so long
items time out before they can converge OR reach their budget. The run must be able to raise
this without touching client defaults or probe_with_recovery's signature.
"""
import bench.benchmarks as B
import bench.client as C
import bench.generate as G


def _fake_probe_result():
    return {"content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
            "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0,
            "finish_reason": "stop", "wall_s": 0.1, "raw_timings": {}}


def test_generate_run_threads_probe_timeout(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)

    def fake_probe(model, messages, params, timeout=3600, tools=None):
        captured["timeout"] = timeout
        return _fake_probe_result()

    monkeypatch.setattr(C, "probe", fake_probe)
    G.run(["m"], ["aime"], {}, probe_timeout=9000)
    assert captured["timeout"] == 9000


def test_generate_run_default_probe_timeout_is_client_default(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)

    def fake_probe(model, messages, params, timeout=3600, tools=None):
        captured["timeout"] = timeout
        return _fake_probe_result()

    monkeypatch.setattr(C, "probe", fake_probe)
    G.run(["m"], ["aime"], {})          # no override
    assert captured["timeout"] == 3600
