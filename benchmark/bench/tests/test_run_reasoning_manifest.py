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


def test_gather_failure_at_entry_refuses_before_any_model_request(monkeypatch, tmp_path):
    """Operator ruling 2026-10-06 (Codex review 10 B1): provenance is no longer best-effort. A
    gather that fails at ENTRY refuses the run (rc 3) before the ladder runs or anything is
    written, so a multi-hour ladder is never spent on a result that could not be published."""
    _patch(monkeypatch, tmp_path)
    import os
    import bench.provenance as P
    calls = []
    monkeypatch.setattr(R, "run_reasoning_ladder", lambda *a, **kw: calls.append(1) or CANNED_PASS_FAIL)

    def boom_gather(*a, **kw):
        raise RuntimeError("provenance backend down")
    monkeypatch.setattr(P, "gather", boom_gather)
    rc = R.main(["--model", "M", "--no-preload", "--sampling-profile", "production"])
    assert rc == 3
    assert calls == []
    assert not os.path.exists(os.path.join(str(tmp_path), "M", "reasoning.json"))
    assert not os.path.exists(os.path.join(str(tmp_path), "M", "reasoning.manifest.json"))


def test_gather_failure_at_exit_leaves_the_result_staged_and_exits_3(monkeypatch, tmp_path):
    """The preflight passed but the end-of-run gather failed: the finished ladder is NOT lost
    (it stays `.pending-<pid>`), nothing is published under a canonical name, rc 3."""
    _patch(monkeypatch, tmp_path)
    import os
    import bench.provenance as P
    real = P.gather
    n = {"calls": 0}

    def flaky_gather(*a, **kw):
        n["calls"] += 1
        if n["calls"] == 1:
            return real(*a, **kw)
        raise RuntimeError("provenance backend down")
    monkeypatch.setattr(P, "gather", flaky_gather)
    rc = R.main(["--model", "M", "--no-preload", "--sampling-profile", "production"])
    assert rc == 3
    d = os.path.join(str(tmp_path), "M")
    assert not os.path.exists(os.path.join(d, "reasoning.json"))
    assert not os.path.exists(os.path.join(d, "reasoning.manifest.json"))
    assert [f for f in os.listdir(d) if f.startswith("reasoning.json.pending-")]