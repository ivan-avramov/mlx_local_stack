"""TDD tests for bench.run_retrieval CLI."""
import json
import os

import bench.run_retrieval as R
from bench.model_params import params_for


class FakeDriver:
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return {"content": "ABCD1234", "prompt_tokens": 100, "prefill_s": 0.5,
                "prefill_tps": 200, "decode_tps": 50.0, "peak_mem_gb": 20.0, "wall_s": 1.0}


class FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    system_peak_gb = 30.0
    peak_rss_gb = 20.0


CANNED_PASS_FAIL = [
    {"ctx": 8000, "accuracy": 1.0, "per_depth_acc": [1, 1, 1, 1, 1], "samples": 5, "needles": 5, "errors": 0},
    {"ctx": 32000, "accuracy": 0.4, "per_depth_acc": [1, 1, 0, 0, 0], "samples": 5, "needles": 5, "errors": 0},
]
CANNED_DIP_RECOVER = [
    {"ctx": 8000, "accuracy": 1.0, "per_depth_acc": [1, 1, 1, 1, 1], "samples": 5, "needles": 5, "errors": 0},
    {"ctx": 32000, "accuracy": 0.4, "per_depth_acc": [1, 1, 0, 0, 0], "samples": 5, "needles": 5, "errors": 0},
    {"ctx": 64000, "accuracy": 0.9, "per_depth_acc": [1, 1, 1, 1, 0.5], "samples": 5, "needles": 5, "errors": 0},
]
CANNED_ALL_FAIL = [
    {"ctx": 8000, "accuracy": 0.2, "per_depth_acc": [1, 0, 0, 0, 0], "samples": 5, "needles": 5, "errors": 0},
]


def _run_main(monkeypatch, tmp_path, canned, extra_argv=None):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_retrieval_ladder", lambda *a, **kw: canned)
    argv = ["--model", "mymodel", "--grid", "8000,32000", "--no-preload"]
    if extra_argv:
        argv += extra_argv
    return R.main(argv)


def test_main_returns_0(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, tmp_path, CANNED_PASS_FAIL) == 0


def test_main_writes_retrieval_json(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_PASS_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert out["model"] == "mymodel"
    assert out["axis"] == "retrieval"
    assert out["task"] == "multi_needle_niah"
    assert len(out["records"]) == 2


def test_effective_ctx_largest_passing(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_PASS_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert out["retrieval_effective_ctx"] == 8000


def test_effective_ctx_dip_then_recover(monkeypatch, tmp_path):
    """Full curve: a mid-context dip does not cap the effective length; the largest
    passing rung wins (distinguishes retrieval from the reasoning climb-to-cliff)."""
    _run_main(monkeypatch, tmp_path, CANNED_DIP_RECOVER)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert out["retrieval_effective_ctx"] == 64000


def test_effective_ctx_none_when_all_fail(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_ALL_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert out["retrieval_effective_ctx"] is None


def test_json_has_grid_threshold_depths(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_PASS_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert "grid" in out and "threshold" in out and "depths" in out
    assert out["depths"] == [0.1, 0.3, 0.5, 0.7, 0.9]


def test_calibrate_cpt_positive():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0


def test_params_via_params_for(monkeypatch, tmp_path):
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params")
        return CANNED_PASS_FAIL

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_retrieval_ladder", fake_ladder)
    R.main(["--model", "Qwen3.6-27B-UD-MLX-6bit", "--grid", "8000,32000", "--no-preload"])
    expected = params_for("Qwen3.6-27B-UD-MLX-6bit")
    assert captured["params"]["thinking_budget"] == expected["thinking_budget"]
    assert captured["params"]["max_tokens"] == expected["max_tokens"]


def test_thinking_budget_override(monkeypatch, tmp_path):
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params")
        return CANNED_PASS_FAIL

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_retrieval_ladder", fake_ladder)
    R.main(["--model", "Qwen3.6-27B-UD-MLX-6bit", "--grid", "8000", "--no-preload",
            "--thinking-budget", "4096"])
    assert captured["params"]["thinking_budget"] == 4096
