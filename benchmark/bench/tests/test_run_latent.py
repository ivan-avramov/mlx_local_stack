"""TDD tests for bench.run_latent CLI."""
import json
import os

import bench.run_latent as R
from bench.model_params import params_for


class FakeDriver:
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return {"content": "ANSWER: Mara", "prompt_tokens": 100, "prefill_s": 0.5,
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


CANNED = [
    {"ctx": 8000, "accuracy": 1.0, "samples": 5, "errors": 0},
    {"ctx": 16000, "accuracy": 0.2, "samples": 5, "errors": 0},
]


def _run_main(monkeypatch, tmp_path, canned, extra_argv=None):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_latent_ladder", lambda *a, **kw: canned)
    argv = ["--model", "mymodel", "--grid", "8000,16000", "--no-preload"]
    if extra_argv:
        argv += extra_argv
    return R.main(argv)


def test_main_writes_latent_json(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, tmp_path, CANNED) == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "latent.json")))
    assert out["model"] == "mymodel"
    assert out["axis"] == "reasoning"
    assert out["task"] == "latent_nolima_style"
    assert out["reasoning_effective_ctx"] == 8000


def test_main_params_via_params_for(monkeypatch, tmp_path):
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params")
        return CANNED

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_latent_ladder", fake_ladder)
    R.main(["--model", "gemma-4-26B-A4B-it-QAT-MLX-4bit", "--grid", "8000", "--no-preload"])
    assert captured["params"]["thinking_budget"] == params_for("gemma-4-26B-A4B-it-QAT-MLX-4bit")["thinking_budget"]


def test_calibrate_cpt_positive():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0
