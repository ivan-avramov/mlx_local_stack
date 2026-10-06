"""M57: run_capacity / run_retrieval / run_reasoning resolve the serving controls BEFORE the first
model request, re-resolve once after the model is loaded, and never swallow a ServedConfigError
(incl. ServingStateError) at the end-of-run provenance.gather."""
import pathlib

import pytest
import yaml

import bench.paths as paths
import bench.provenance as P
import bench.run_capacity as RC
import bench.run_reasoning as RR
import bench.run_retrieval as RT

MODEL = "mymodel"
ARGV = ["python", "-m", "mlx_vlm.server", "--model", "caslca/mymodel-4bit"]
GOOD = ARGV + ["--attention-policy", "fused_v1"]


class FakeDriver:
    def __init__(self):
        self.calls = []

    def preload(self, model, timeout=900):
        self.calls.append("preload")
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        self.calls.append("complete")
        return {"content": "XKRZ0A7Q", "prompt_tokens": 1000, "completion_tokens": 10,
                "finish_reason": "stop", "prefill_s": 1.0, "prefill_tps": 100, "decode_tps": 9.5,
                "peak_mem_gb": 40.0, "wall_s": 1.0}


class FakeSampler:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass
    system_peak_gb = 45.0
    peak_rss_gb = 35.0


def _setup(monkeypatch, tmp_path, mod, ladder_name, canned, worker_script):
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.safe_dump({"models": [{
        "name": MODEL, "hf_path": "caslca/mymodel-4bit", "attention_policy": "fused_v1"}]}))
    monkeypatch.setattr(paths, "registry_path", lambda: pathlib.Path(reg))
    results = tmp_path / "results"
    results.mkdir()
    drv = FakeDriver()
    ladder_calls = []
    monkeypatch.setattr(mod, "MlxServeDriver", lambda: drv)
    monkeypatch.setattr(mod, "MemorySampler", FakeSampler)
    monkeypatch.setattr(mod, "RESULTS", str(results))
    monkeypatch.setattr(mod, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(mod, "await_model_pid", lambda: 1234)
    monkeypatch.setattr(mod, ladder_name,
                        lambda *a, **k: ladder_calls.append(1) or canned)
    script = list(worker_script)

    def lookup(doc):
        return script.pop(0) if len(script) > 1 else script[0]
    monkeypatch.setattr(P, "_worker_argvs", lookup)
    return drv, ladder_calls, results


_CAP_ROW = [{"ctx": 160000, "server_peak_gb": 40.0, "peak_rss_gb": 35.0, "system_peak_gb": 45.0,
             "model_footprint_gb": 35.0, "prefill_s": 1.0, "prefill_tps": 200, "decode_tps": 9.5,
             "prompt_tokens": 1000, "completion_tokens": 10, "finish_reason": "stop",
             "retrieval_acc": 1.0, "fits": True, "within_memory_target": True}]
_RET_ROW = [{"ctx": 8000, "accuracy": 1.0, "per_depth_acc": [1], "samples": 1, "needles": 1, "errors": 0}]
_REA_ROW = [{"ctx": 8000, "accuracy": 1.0, "samples": 1, "chain_len": 4, "errors": 0}]

DRIVERS = {
    "capacity": (RC, "run_ladder", _CAP_ROW, ["--grid", "160000"]),
    "retrieval": (RT, "run_retrieval_ladder", _RET_ROW, ["--grid", "8000"]),
    "reasoning": (RR, "run_reasoning_ladder", _REA_ROW, ["--grid", "8000"]),
}


def _argv(extra):
    return ["--model", MODEL, "--sampling-profile", "production", *extra]


def _files(root):
    return [p for p in root.rglob("*") if p.is_file() and p.name != "reg.yaml"]


@pytest.mark.parametrize("name", list(DRIVERS))
def test_refuses_before_the_first_request_on_a_disagreement_known_at_start(monkeypatch, tmp_path, name):
    mod, lad, canned, extra = DRIVERS[name]
    drv, ladder_calls, results = _setup(monkeypatch, tmp_path, mod, lad, canned, [[ARGV]])  # auto vs fused_v1
    with pytest.raises(P.ServedConfigError):
        mod.main(_argv(extra))
    assert drv.calls == [] and ladder_calls == []
    assert _files(results) == []
    assert list(results.iterdir()) == []              # not even the model directory


@pytest.mark.parametrize("name", list(DRIVERS))
def test_refuses_after_load_when_the_worker_that_came_up_disagrees(monkeypatch, tmp_path, name):
    mod, lad, canned, extra = DRIVERS[name]
    # before the load: no worker yet (however many lookups the entry checks + the provenance
    # preflight make); once the driver has loaded: a worker WITHOUT the declared flag
    drv, ladder_calls, results = _setup(monkeypatch, tmp_path, mod, lad, canned, [[]])
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [ARGV] if drv.calls else [])
    with pytest.raises(P.ServedConfigError):
        mod.main(_argv(extra))
    assert "preload" in drv.calls or "complete" in drv.calls     # the load did happen
    assert ladder_calls == []                                    # but no measured request
    assert _files(results) == []


@pytest.mark.parametrize("name", list(DRIVERS))
def test_normal_run_unaffected_when_worker_and_registry_agree(monkeypatch, tmp_path, name):
    mod, lad, canned, extra = DRIVERS[name]
    drv, ladder_calls, results = _setup(monkeypatch, tmp_path, mod, lad, canned, [[GOOD]])
    assert mod.main(_argv(extra)) == 0
    assert ladder_calls == [1]


@pytest.mark.parametrize("name", list(DRIVERS))
def test_no_worker_at_all_falls_back_to_the_registry(monkeypatch, tmp_path, name):
    mod, lad, canned, extra = DRIVERS[name]
    drv, ladder_calls, results = _setup(monkeypatch, tmp_path, mod, lad, canned, [[]])
    assert mod.main(_argv(extra)) == 0
    assert ladder_calls == [1]


@pytest.mark.parametrize("name", list(DRIVERS))
def test_end_of_run_gather_no_longer_swallows_a_served_config_error(monkeypatch, tmp_path, name):
    mod, lad, canned, extra = DRIVERS[name]
    _, ladder_calls, _ = _setup(monkeypatch, tmp_path, mod, lad, canned, [[GOOD]])
    real, n = P.gather, {"calls": 0}

    def boom_late(*a, **k):               # the entry preflight passes; the END-of-run gather raises
        n["calls"] += 1
        if n["calls"] == 1:
            return real(*a, **k)
        raise P.ServingStateError("C35 tripwire: attention_policy changed")
    monkeypatch.setattr(P, "gather", boom_late)
    with pytest.raises(P.ServedConfigError):
        mod.main(_argv(extra))
    assert ladder_calls == [1]            # it really was the end-of-run gather that refused


@pytest.mark.parametrize("name", list(DRIVERS))
def test_ordinary_gather_failure_at_entry_refuses_every_driver_before_the_ladder(monkeypatch, tmp_path, name):
    """Operator ruling 2026-10-06 (Codex review 10 B1): an ordinary gather failure is a refusal
    at entry (rc 3, ladder never called), distinct from a ServedConfigError (which raises)."""
    mod, lad, canned, extra = DRIVERS[name]
    _, ladder_calls, _ = _setup(monkeypatch, tmp_path, mod, lad, canned, [[GOOD]])

    def boom(*a, **k):
        raise ValueError("ordinary")
    monkeypatch.setattr(P, "gather", boom)
    rc = mod.main(_argv(extra))
    assert rc == 3
    assert ladder_calls == []
    assert not list((tmp_path / "results").iterdir())     # nothing created, not even the model dir
