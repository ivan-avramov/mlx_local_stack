"""Z2: a late (end-of-run) serving-state refusal in run_retrieval / run_reasoning must not leave a
new result under its normal name beside an older manifest."""
import pathlib

import pytest
import yaml

import bench.paths as paths
import bench.provenance as P
import bench.run_reasoning as RR
import bench.run_retrieval as RT
from bench.tests.test_serving_state_drivers import FakeDriver, FakeSampler

MODEL = "mymodel"
ARGV = ["python", "-m", "mlx_vlm.server", "--model", "caslca/mymodel-4bit"]

CASES = {
    "retrieval": (RT, "run_retrieval_ladder", [{"ctx": 8000, "accuracy": 1.0, "per_depth_acc": [1],
                                                "samples": 1, "needles": 1, "errors": 0}]),
    "reasoning": (RR, "run_reasoning_ladder", [{"ctx": 8000, "accuracy": 1.0, "samples": 1,
                                                "chain_len": 4, "errors": 0}]),
}


def _setup(monkeypatch, tmp_path, mod, ladder, canned):
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.safe_dump({"models": [{
        "name": MODEL, "hf_path": "caslca/mymodel-4bit", "attention_policy": "fused_v1"}]}))
    monkeypatch.setattr(paths, "registry_path", lambda: pathlib.Path(reg))
    results = tmp_path / "results"
    (results / MODEL).mkdir(parents=True)
    state = {"late": False}
    monkeypatch.setattr(mod, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(mod, "MemorySampler", FakeSampler)
    monkeypatch.setattr(mod, "RESULTS", str(results))
    monkeypatch.setattr(mod, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(mod, "await_model_pid", lambda: 1234)

    def run_ladder(*a, **k):
        state["late"] = True            # the serving state changes after the second check
        return canned
    monkeypatch.setattr(mod, ladder, run_ladder)
    # worker absent (registry fallback) until the ladder has run, then a worker serving auto
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [ARGV] if state["late"] else [])
    return results / MODEL


@pytest.mark.parametrize("name", list(CASES))
def test_late_refusal_moves_the_new_result_aside_and_leaves_the_old_pair(monkeypatch, tmp_path, name):
    mod, ladder, canned = CASES[name]
    out = _setup(monkeypatch, tmp_path, mod, ladder, canned)
    stem = name
    (out / f"{stem}.json").write_text('{"old": true}')
    (out / f"{stem}.manifest.json").write_bytes(b'{"old": "manifest"}\n')
    journal = out / f"{stem}.partial.jsonl"
    if name == "reasoning":
        journal.write_text('{"rung": 1}\n')
    with pytest.raises(P.ServedConfigError):
        mod.main(["--model", MODEL, "--sampling-profile", "production", "--grid", "8000"])
    assert (out / f"{stem}.manifest.json").read_bytes() == b'{"old": "manifest"}\n'
    assert (out / f"{stem}.json").read_text() == '{"old": true}'      # nothing overwritten
    refused = sorted(p.name for p in out.glob(f"{stem}.json.refused-*"))
    assert len(refused) == 1
    assert '"records"' in (out / refused[0]).read_text()               # it is the NEW result
    if name == "reasoning":
        assert not journal.exists()
        assert len(list(out.glob(f"{stem}.partial.jsonl.refused-*"))) == 1


@pytest.mark.parametrize("name", list(CASES))
def test_late_refusal_with_no_prior_result_leaves_no_normal_name(monkeypatch, tmp_path, name):
    mod, ladder, canned = CASES[name]
    out = _setup(monkeypatch, tmp_path, mod, ladder, canned)
    with pytest.raises(P.ServedConfigError):
        mod.main(["--model", MODEL, "--sampling-profile", "production", "--grid", "8000"])
    assert not (out / f"{name}.json").exists()
    assert not (out / f"{name}.manifest.json").exists()
    assert len(list(out.glob(f"{name}.json.refused-*"))) == 1


@pytest.mark.parametrize("name", list(CASES))
def test_successful_run_writes_the_same_files_as_before(monkeypatch, tmp_path, name):
    mod, ladder, canned = CASES[name]
    out = _setup(monkeypatch, tmp_path, mod, ladder, canned)
    monkeypatch.setattr(P, "_worker_argvs",
                        lambda doc: [ARGV + ["--attention-policy", "fused_v1"]])
    assert mod.main(["--model", MODEL, "--sampling-profile", "production", "--grid", "8000"]) == 0
    assert (out / f"{name}.json").exists() and (out / f"{name}.manifest.json").exists()
    assert not list(out.glob("*refused*")) and not list(out.glob("*.tmp*"))
