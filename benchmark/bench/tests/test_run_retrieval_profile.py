"""M41 T1: run_retrieval must carry an explicit sampling profile (mirrors
test_run_reasoning_profile.py), a --request-timeout that reaches the ladder, an
--out-tag that changes the output filename, and a best-effort provenance manifest."""
import json
import os

import pytest

import bench.run_retrieval as R

from .test_run_retrieval import FakeDriver, FakeSampler, CANNED_PASS_FAIL


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: None)
    monkeypatch.setattr(R, "run_retrieval_ladder", lambda *a, **kw: CANNED_PASS_FAIL)


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


def test_request_timeout_reaches_ladder(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    seen = {}
    monkeypatch.setattr(R, "run_retrieval_ladder",
                        lambda *a, **kw: seen.update(kw) or CANNED_PASS_FAIL)
    R.main(["--model", "M", "--no-preload", "--sampling-profile", "production",
            "--request-timeout", "1234"])
    assert seen.get("request_timeout") == 1234


def test_cli_request_timeout_default_is_derived_not_sdk(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    seen = {}
    monkeypatch.setattr(R, "run_retrieval_ladder",
                        lambda *a, **kw: seen.update(kw) or CANNED_PASS_FAIL)
    R.main(["--model", "M", "--no-preload", "--sampling-profile", "production"])
    assert seen.get("request_timeout", 0) >= 9600


def test_out_tag_changes_filename(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    R.main(["--model", "M", "--no-preload", "--sampling-profile", "production",
            "--out-tag", "t07"])
    assert not os.path.exists(os.path.join(tmp_path, "M", "retrieval.json"))
    out = json.load(open(os.path.join(tmp_path, "M", "retrieval.t07.json")))
    assert out["model"] == "M"


def test_manifest_written_beside_output(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    calls = {}
    import bench.provenance as P

    def fake_gather(model, *a, **kw):
        calls["args"] = (model, kw)
        return {"model": model, "fake": True}
    monkeypatch.setattr(P, "gather", fake_gather)

    def boom(*a, **kw):
        raise AssertionError("provenance.write must NOT be used here — it bypasses RESULTS")
    monkeypatch.setattr(P, "write", boom)

    rc = R.main(["--model", "M", "--no-preload", "--sampling-profile", "production"])
    assert rc == 0
    model, kw = calls["args"]
    assert model == "M"
    assert kw["profile"] == "production"
    assert kw["runtime"]["probe"] == "retrieval"
    man_path = tmp_path / "M" / "retrieval.manifest.json"
    assert man_path.exists()
    assert json.loads(man_path.read_text())["fake"] is True


def test_manifest_tag_filename(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    import bench.provenance as P
    monkeypatch.setattr(P, "gather", lambda model, *a, **kw: {"model": model})
    R.main(["--model", "M", "--no-preload", "--sampling-profile", "production",
            "--out-tag", "t07"])
    assert (tmp_path / "M" / "retrieval.t07.manifest.json").exists()


def test_manifest_never_blocks_a_finished_ladder(monkeypatch, tmp_path):
    """provenance failures are best-effort: main() must still return 0 and the ladder
    output must still be written."""
    _patch(monkeypatch, tmp_path)
    import bench.provenance as P

    def boom_gather(*a, **kw):
        raise RuntimeError("provenance backend down")
    monkeypatch.setattr(P, "gather", boom_gather)
    rc = R.main(["--model", "M", "--no-preload", "--sampling-profile", "production"])
    assert rc == 0
    assert os.path.exists(os.path.join(tmp_path, "M", "retrieval.json"))
    assert not os.path.exists(os.path.join(tmp_path, "M", "retrieval.manifest.json"))
