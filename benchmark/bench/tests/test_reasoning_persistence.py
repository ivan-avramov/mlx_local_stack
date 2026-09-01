"""Per-rung persistence + resume for the reasoning ladder, and O41 escalation of transport errors."""
import json
import pytest
import bench.run_reasoning as R
from bench.reasoning import run_reasoning_ladder

from .test_run_reasoning import FakeDriver, FakeSampler


class CountingDriver(FakeDriver):
    def __init__(self):
        self.calls = 0

    def complete(self, model, messages, params, timeout=3600, tools=None):
        self.calls += 1
        return super().complete(model, messages, params, timeout)


class BoomDriver(FakeDriver):
    def complete(self, *a, **k):
        raise ConnectionError("worker gone")


def test_on_rung_callback_fires_per_rung():
    seen = []
    run_reasoning_ladder(CountingDriver(), "M", 4.0, model_pid=None, params={"max_tokens": 64},
                         grid=(8000, 16000), threshold=0.0, samples=1, chain_len=2,
                         sampler_factory=FakeSampler, on_rung=seen.append)
    assert [r["ctx"] for r in seen] == [8000, 16000]


def test_resume_skips_requests_for_completed_rungs_and_keeps_threshold_break():
    d = CountingDriver()
    done = {8000: {"ctx": 8000, "accuracy": 1.0, "samples": 1, "chain_len": 2, "errors": 0},
            16000: {"ctx": 16000, "accuracy": 0.2, "samples": 1, "chain_len": 2, "errors": 0}}
    recs = run_reasoning_ladder(d, "M", 4.0, model_pid=None, params={"max_tokens": 64},
                                grid=(8000, 16000, 24000), threshold=0.85, samples=1, chain_len=2,
                                sampler_factory=FakeSampler, resume=done)
    assert d.calls == 0                      # nothing re-requested
    assert [r["ctx"] for r in recs] == [8000, 16000]  # break at the resumed failing rung


def test_transport_error_escalates_not_graded():
    with pytest.raises(ConnectionError):
        run_reasoning_ladder(BoomDriver(), "M", 4.0, model_pid=None, params={"max_tokens": 64},
                             grid=(8000,), threshold=0.0, samples=1, chain_len=2,
                             sampler_factory=FakeSampler)


def _patch_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: CountingDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: None)
    monkeypatch.setattr(R, "params_for", lambda model, profile="production", registry_path=None:
                        {"temperature": 0.5, "max_tokens": 64, "thinking_budget": 32})


def test_cli_writes_partial_per_rung_and_resumes(monkeypatch, tmp_path):
    _patch_cli(monkeypatch, tmp_path)
    argv = ["--model", "M", "--grid", "8000,16000", "--no-preload", "--sampling-profile", "deployed",
            "--samples", "1", "--chain-len", "2", "--threshold", "0.0"]
    R.main(argv)
    partial = tmp_path / "M" / "reasoning.partial.jsonl"
    lines = [json.loads(l) for l in partial.read_text().splitlines()]
    assert [l["record"]["ctx"] for l in lines] == [8000, 16000]
    assert all("key" in l for l in lines)
    # second run with --resume: no new requests are made
    calls = {}
    class Spy(CountingDriver):
        def complete(self, *a, **k):
            calls["n"] = calls.get("n", 0) + 1
            return super().complete(*a, **k)
    monkeypatch.setattr(R, "MlxServeDriver", lambda: Spy())
    R.main(argv + ["--resume"])
    assert calls.get("n", 0) == 1   # only the cpt calibration request
    # a different grid/params key is NOT resumed
    R.main(["--model", "M", "--grid", "8000,16000,24000", "--no-preload", "--sampling-profile",
            "deployed", "--samples", "1", "--chain-len", "2", "--threshold", "0.0", "--resume"])
    assert calls["n"] > 1


def test_cli_temp_override_is_in_the_design_key_and_out_tag_names_outputs(monkeypatch, tmp_path):
    """NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit ladder (2026-08-31): a temperature OFAT on the reasoning axis must (a) carry the
    override into the request params AND the persistence key (different temps never pool) and
    (b) write to reasoning.<tag>.json / reasoning.<tag>.partial.jsonl so the deployed-tune
    result is never overwritten."""
    _patch_cli(monkeypatch, tmp_path)
    seen = {}
    class Spy(CountingDriver):
        def complete(self, model, messages, params, timeout=3600, tools=None):
            seen.setdefault("temps", []).append(params.get("temperature"))
            return super().complete(model, messages, params, timeout)
    monkeypatch.setattr(R, "MlxServeDriver", lambda: Spy())
    R.main(["--model", "M", "--grid", "8000", "--no-preload", "--sampling-profile", "deployed",
            "--samples", "1", "--chain-len", "2", "--threshold", "0.0", "--temp", "0.7",
            "--out-tag", "t07"])
    assert 0.7 in seen["temps"]                      # the ladder requests carry the override
    assert not (tmp_path / "M" / "reasoning.json").exists()
    assert not (tmp_path / "M" / "reasoning.partial.jsonl").exists()
    out = json.loads((tmp_path / "M" / "reasoning.t07.json").read_text())
    assert out["records"][0]["ctx"] == 8000 and out["params"]["temperature"] == 0.7
    partial = (tmp_path / "M" / "reasoning.t07.partial.jsonl").read_text().splitlines()
    assert '"temperature": 0.7' in json.loads(partial[0])["key"]
