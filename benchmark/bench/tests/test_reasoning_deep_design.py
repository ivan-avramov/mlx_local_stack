"""M11 deep-rung design (operator ruling 2026-08-30, P52 option a): fewer samples at deep rungs and a
pre-registered early stop when the first N deep samples all hit the thinking budget."""
import json
import bench.run_reasoning as R
from bench.reasoning import run_reasoning_ladder

from .test_run_reasoning import FakeSampler

PARAMS = {"max_tokens": 1024, "thinking_budget": 100}


class TokDriver:
    """completion_tokens per call comes from `plan` (cycled); content is always the right answer
    shape so scoring never masks the sample-count logic."""
    def __init__(self, plan):
        self.plan = list(plan); self.calls = 0

    def preload(self, model, timeout=900): return 1.0

    def complete(self, model, messages, params, timeout=3600, tools=None):
        tok = self.plan[self.calls % len(self.plan)]; self.calls += 1
        return {"content": "ANSWER: 99999", "prompt_tokens": 10, "completion_tokens": tok,
                "finish_reason": "stop", "prefill_s": 0.1, "prefill_tps": 100,
                "decode_tps": 50.0, "peak_mem_gb": 1.0, "wall_s": 0.5}


def _ladder(driver, **kw):
    base = dict(model="M", chars_per_token=4.0, model_pid=None, params=PARAMS,
                grid=(8000, 96000, 128000), threshold=0.0, samples=5, chain_len=2,
                sampler_factory=FakeSampler)
    base.update(kw)
    return run_reasoning_ladder(driver, **base)


def test_deep_samples_apply_from_deep_from():
    d = TokDriver([10])
    recs = _ladder(d, deep_from=96000, deep_samples=3)
    assert [r["samples"] for r in recs] == [5, 3, 3]
    assert d.calls == 11


def test_early_stop_when_first_two_deep_samples_hit_budget():
    d = TokDriver([100])          # every sample hits the 100-token budget
    recs = _ladder(d, grid=(8000, 96000), deep_from=96000, deep_samples=3,
                   early_stop_budget_hits=2)
    deep = recs[1]
    assert deep["samples"] == 2 and deep["early_stop"] is True and deep["budget_hits"] == 2
    assert d.calls == 5 + 2


def test_no_early_stop_when_a_deep_sample_converges():
    d = TokDriver([100, 10, 100])  # second sample converges
    recs = _ladder(d, grid=(96000,), deep_from=96000, deep_samples=3, early_stop_budget_hits=2)
    assert recs[0]["samples"] == 3 and recs[0]["early_stop"] is False
    assert recs[0]["budget_hits"] == 2


def test_shallow_rungs_unaffected_by_early_stop_rule():
    d = TokDriver([100])
    recs = _ladder(d, grid=(8000,), deep_from=96000, deep_samples=3, early_stop_budget_hits=2)
    assert recs[0]["samples"] == 5 and recs[0]["budget_hits"] == 5


def _patch_cli(monkeypatch, tmp_path, driver):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: driver)
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: None)
    monkeypatch.setattr(R, "params_for", lambda model, profile="production", registry_path=None:
                        dict(PARAMS, temperature=0.5))


def test_cli_shallow_rows_resume_across_a_deep_redesign(monkeypatch, tmp_path):
    """Rungs below deep_from persist under the base key, so a later run that ADDS the deep flags
    still resumes them; deep rows carry the deep fields in their key."""
    d1 = TokDriver([10]); _patch_cli(monkeypatch, tmp_path, d1)
    common = ["--model", "M", "--grid", "8000,16000,96000", "--no-preload", "--sampling-profile",
              "deployed", "--samples", "1", "--chain-len", "2", "--threshold", "0.0"]
    R.main(common)                                  # full design: 3 rungs persisted
    d2 = TokDriver([10]); _patch_cli(monkeypatch, tmp_path, d2)
    R.main(common + ["--resume", "--deep-from", "96000", "--deep-samples", "1",
                     "--early-stop-budget-hits", "2"])
    # cpt calibration + ONLY the 96000 rung re-run (its key changed); 8000/16000 resumed
    assert d2.calls == 1 + 1
    rows = [json.loads(l) for l in (tmp_path / "M" / "reasoning.partial.jsonl").read_text().splitlines()]
    deep_keys = [json.loads(r["key"]) for r in rows if r["record"]["ctx"] == 96000]
    assert any("deep_samples" in k for k in deep_keys)
    assert all("deep_samples" not in json.loads(r["key"]) for r in rows if r["record"]["ctx"] < 96000)
