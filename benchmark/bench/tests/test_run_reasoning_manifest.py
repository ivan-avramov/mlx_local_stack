"""M41 T3.2: run_reasoning writes a best-effort provenance manifest beside the ladder
output, the same way run_retrieval.py (T1.6) and run_capacity.py do."""
import json

import bench.run_reasoning as R

from .test_run_reasoning import FakeDriver, FakeSampler, CANNED_RECORDS_ALL_PASS


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: None)
    monkeypatch.setattr(R, "run_reasoning_ladder", lambda *a, **kw: CANNED_RECORDS_ALL_PASS)


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

    rc = R.main(["--model", "M", "--no-preload", "--sampling-profile", "production",
                "--grid", "8000", "--chain-len", "3"])
    assert rc == 0
    model, kw = calls["args"]
    assert model == "M"
    assert kw["profile"] == "production"
    assert kw["runtime"]["probe"] == "reasoning"
    assert kw["runtime"]["chain_len"] == 3
    man_path = tmp_path / "M" / "reasoning.manifest.json"
    assert man_path.exists()
    assert json.loads(man_path.read_text())["fake"] is True


def test_manifest_tag_filename(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    import bench.provenance as P
    monkeypatch.setattr(P, "gather", lambda model, *a, **kw: {"model": model})
    R.main(["--model", "M", "--no-preload", "--sampling-profile", "production",
            "--out-tag", "t07"])
    assert (tmp_path / "M" / "reasoning.t07.manifest.json").exists()


def test_manifest_overrides_are_cli_deltas_only(monkeypatch, tmp_path):
    """M41 FIX1 F4 (review defect 10): the manifest's `overrides` must reflect only the
    CLI flags the operator actually passed, NOT the full resolved params dict -- a run
    with only `--temp 0.7` must not report top_p/top_k/etc as if they were overrides."""
    _patch(monkeypatch, tmp_path)
    calls = {}
    import bench.provenance as P

    def fake_gather(model, *a, **kw):
        calls["args"] = (model, kw)
        return {"model": model, "fake": True}
    monkeypatch.setattr(P, "gather", fake_gather)

    rc = R.main(["--model", "M", "--no-preload", "--sampling-profile", "production",
                "--temp", "0.7"])
    assert rc == 0
    _, kw = calls["args"]
    assert kw["overrides"] == {"temperature": 0.7}


def test_manifest_overrides_empty_when_no_cli_deltas(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    calls = {}
    import bench.provenance as P

    def fake_gather(model, *a, **kw):
        calls["args"] = (model, kw)
        return {"model": model, "fake": True}
    monkeypatch.setattr(P, "gather", fake_gather)

    rc = R.main(["--model", "M", "--no-preload", "--sampling-profile", "production"])
    assert rc == 0
    _, kw = calls["args"]
    assert kw["overrides"] == {}


def test_manifest_never_blocks_a_finished_ladder(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    import bench.provenance as P

    def boom_gather(*a, **kw):
        raise RuntimeError("provenance backend down")
    monkeypatch.setattr(P, "gather", boom_gather)
    rc = R.main(["--model", "M", "--no-preload", "--sampling-profile", "production"])
    assert rc == 0
    import os
    assert os.path.exists(os.path.join(str(tmp_path), "M", "reasoning.json"))
    assert not os.path.exists(os.path.join(str(tmp_path), "M", "reasoning.manifest.json"))
