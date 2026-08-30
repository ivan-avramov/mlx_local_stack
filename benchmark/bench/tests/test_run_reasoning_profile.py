"""O36: run_reasoning must carry an explicit sampling profile; deployed is the new-axis profile."""
import pytest
import bench.run_reasoning as R

from .test_run_reasoning import FakeDriver, FakeSampler, CANNED_RECORDS_ALL_PASS


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: None)
    monkeypatch.setattr(R, "run_reasoning_ladder", lambda *a, **kw: CANNED_RECORDS_ALL_PASS)


def test_sampling_profile_is_required(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as e:
        R.main(["--model", "M", "--no-preload"])
    assert e.value.code == 2


def test_sampling_profile_reaches_params_for(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    seen = {}

    def fake_params_for(model, profile="production", registry_path=None):
        seen["profile"] = profile
        return {"temperature": 0.5, "top_p": 0.95, "max_tokens": 1024, "thinking_budget": 512}

    monkeypatch.setattr(R, "params_for", fake_params_for)
    R.main(["--model", "M", "--no-preload", "--sampling-profile", "deployed"])
    assert seen["profile"] == "deployed"


def test_request_timeout_reaches_driver(monkeypatch, tmp_path):
    """O41: deep rungs need a DERIVED timeout; the ladder must pass it to driver.complete."""
    from bench.reasoning import run_reasoning_ladder
    seen = []

    class D:
        def complete(self, model, messages, params, timeout=3600, tools=None):
            seen.append(timeout)
            return {"content": "ANSWER: 1", "prompt_tokens": 10, "prefill_s": 0.1,
                    "prefill_tps": 100, "decode_tps": 50.0, "peak_mem_gb": 1.0, "wall_s": 0.5}

    run_reasoning_ladder(D(), "M", 4.0, model_pid=None, params={"max_tokens": 64},
                         grid=(8000,), threshold=0.0, samples=1, chain_len=2,
                         sampler_factory=FakeSampler, request_timeout=9600)
    assert seen and all(t == 9600 for t in seen)


def test_cli_request_timeout_default_is_derived_not_sdk(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    monkeypatch.setattr(R, "params_for", lambda model, profile="production", registry_path=None:
                        {"temperature": 0.5, "max_tokens": 1024, "thinking_budget": 512})
    seen = {}
    monkeypatch.setattr(R, "run_reasoning_ladder",
                        lambda *a, **kw: seen.update(kw) or CANNED_RECORDS_ALL_PASS)
    R.main(["--model", "M", "--no-preload", "--sampling-profile", "deployed"])
    assert seen.get("request_timeout", 0) >= 9600
