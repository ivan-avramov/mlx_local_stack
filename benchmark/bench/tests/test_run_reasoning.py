"""TDD tests for bench.run_reasoning CLI."""
import json
import os
import bench.run_reasoning as R
from bench.model_params import params_for


class FakeDriver:
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return {
            "content": "ANSWER: 99999",
            "prompt_tokens": 100,
            "prefill_s": 0.5,
            "prefill_tps": 200,
            "decode_tps": 50.0,
            "peak_mem_gb": 20.0,
            "wall_s": 1.0,
        }


class FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    system_peak_gb = 30.0
    peak_rss_gb = 20.0


CANNED_RECORDS_PASS_FAIL = [
    {"ctx": 8000, "accuracy": 1.0, "samples": 5, "chain_len": 4, "errors": 0},
    {"ctx": 16000, "accuracy": 0.4, "samples": 5, "chain_len": 4, "errors": 0},
]

CANNED_RECORDS_ALL_PASS = [
    {"ctx": 8000, "accuracy": 1.0, "samples": 5, "chain_len": 4, "errors": 0},
    {"ctx": 16000, "accuracy": 0.9, "samples": 5, "chain_len": 4, "errors": 0},
]

CANNED_RECORDS_ALL_FAIL = [
    {"ctx": 8000, "accuracy": 0.2, "samples": 5, "chain_len": 4, "errors": 0},
]


def _run_main(monkeypatch, tmp_path, canned_records, extra_argv=None):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: None)
    monkeypatch.setattr(R, "run_reasoning_ladder",
                        lambda *a, **kw: canned_records)
    argv = ["--model", "mymodel", "--grid", "8000,16000", "--no-preload"]
    if extra_argv:
        argv += extra_argv
    return R.main(argv)


def test_main_returns_0(monkeypatch, tmp_path):
    rc = _run_main(monkeypatch, tmp_path, CANNED_RECORDS_PASS_FAIL)
    assert rc == 0


def test_main_writes_reasoning_json(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_RECORDS_PASS_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "reasoning.json")))
    assert out["model"] == "mymodel"
    assert out["axis"] == "reasoning"
    assert out["task"] == "vartrack"
    assert len(out["records"]) == 2


def test_main_computes_effective_ctx_pass_fail(monkeypatch, tmp_path):
    """reasoning_effective_ctx = largest ctx with accuracy >= threshold."""
    _run_main(monkeypatch, tmp_path, CANNED_RECORDS_PASS_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "reasoning.json")))
    # rung 0 passes (acc=1.0), rung 1 fails (acc=0.4 < 0.85)
    assert out["reasoning_effective_ctx"] == 8000


def test_main_computes_effective_ctx_all_pass(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_RECORDS_ALL_PASS)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "reasoning.json")))
    # Both pass → largest is 16000
    assert out["reasoning_effective_ctx"] == 16000


def test_main_computes_effective_ctx_all_fail(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_RECORDS_ALL_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "reasoning.json")))
    # None pass → None
    assert out["reasoning_effective_ctx"] is None


def test_main_json_has_grid_and_threshold(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_RECORDS_PASS_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "reasoning.json")))
    assert "grid" in out
    assert "threshold" in out


def test_main_no_preload_flag(monkeypatch, tmp_path):
    """--no-preload should not raise."""
    rc = _run_main(monkeypatch, tmp_path, CANNED_RECORDS_PASS_FAIL, ["--no-preload"])
    assert rc == 0


def test_calibrate_cpt_returns_positive():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0


def test_main_passes_params_to_ladder(monkeypatch, tmp_path):
    """main() builds params via params_for and passes a params dict to run_reasoning_ladder."""
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params") or (a[4] if len(a) > 4 else None)
        return CANNED_RECORDS_PASS_FAIL

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: None)
    monkeypatch.setattr(R, "run_reasoning_ladder", fake_ladder)
    R.main(["--model", "gemma-4-26B-A4B-it-QAT-MLX-4bit",
            "--grid", "8000,16000", "--no-preload"])
    assert captured["params"] is not None
    # Gemma model → GEMMA params set
    expected = params_for("gemma-4-26B-A4B-it-QAT-MLX-4bit")
    assert captured["params"]["temperature"] == expected["temperature"]
    assert captured["params"]["max_tokens"] == expected["max_tokens"]
    assert captured["params"]["thinking_budget"] == expected["thinking_budget"]


def test_main_max_tokens_override(monkeypatch, tmp_path):
    """--max-tokens overrides params_for value."""
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params")
        return CANNED_RECORDS_PASS_FAIL

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: None)
    monkeypatch.setattr(R, "run_reasoning_ladder", fake_ladder)
    R.main(["--model", "gemma-4-26B-A4B-it-QAT-MLX-4bit",
            "--grid", "8000,16000", "--no-preload", "--max-tokens", "1234"])
    assert captured["params"]["max_tokens"] == 1234


def test_main_thinking_budget_override(monkeypatch, tmp_path):
    """--thinking-budget overrides params_for value."""
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params")
        return CANNED_RECORDS_PASS_FAIL

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: None)
    monkeypatch.setattr(R, "run_reasoning_ladder", fake_ladder)
    R.main(["--model", "gemma-4-26B-A4B-it-QAT-MLX-4bit",
            "--grid", "8000,16000", "--no-preload", "--thinking-budget", "4096"])
    assert captured["params"]["thinking_budget"] == 4096
