"""P426 stack code round 2 K5: a stable per-request identity for the leg wrapper's row ↔ log reconciliation.

With `MLX_BENCH_SESSION_PREFIX` set (the leg wrapper sets it), `client.probe` sends a unique `x-session-id` — the server's
documented conversation key, logged as `session=` on the `Request completed` line — and returns it; every runner persists it
on the row (vision: both turns). Unset, nothing changes (no header, `session_id` None).
"""

import json
import sys
from pathlib import Path

import bench.benchmarks as B
import bench.client as C
import bench.generate as G
import bench.reasoning as R

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench.tests.test_generate_run import _fake_probe_result  # noqa: E402

import pytest  # noqa: E402

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")  # M58: synthetic models

OK_BODY = {
    "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    "timings": {},
}


def _capture(monkeypatch):
    seen = {}

    def post(path, payload, timeout=3600, headers=None):
        seen["headers"] = dict(headers or {})
        return json.loads(json.dumps(OK_BODY))

    monkeypatch.setattr(C, "_post", post)
    return seen


def test_probe_sends_and_returns_a_unique_session_id_under_the_prefix(monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.setenv("MLX_BENCH_SESSION_PREFIX", "p426-math500-p426-on-b1")
    a = C.probe("m", [{"role": "user", "content": "x"}], {})
    b = C.probe("m", [{"role": "user", "content": "x"}], {})
    assert a["session_id"].startswith("p426-math500-p426-on-b1-") and a["session_id"] != b["session_id"]
    assert seen["headers"]["x-session-id"] == b["session_id"]


def test_without_the_prefix_nothing_changes(monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.delenv("MLX_BENCH_SESSION_PREFIX", raising=False)
    r = C.probe("m", [{"role": "user", "content": "x"}], {})
    assert r["session_id"] is None and "x-session-id" not in seen["headers"]


def test_generate_rows_persist_the_session_id(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    r = dict(_fake_probe_result(), session_id="p426-x-0001")
    monkeypatch.setattr(C, "probe", lambda m, msgs, params, timeout=3600, tools=None: r)
    G.run(["m"], ["aime"], {})
    row = json.loads((tmp_path / "m" / "aime.jsonl").read_text().splitlines()[0])
    assert row["session_id"] == "p426-x-0001"


def test_reasoning_rows_persist_the_session_id():
    from bench.tests.test_reasoning import FakeSampler

    class Driver:
        def complete(self, model, messages, params, timeout=3600):
            return {"content": "ANSWER: 1", "completion_tokens": 3, "finish_reason": "stop", "session_id": "p426-r-1"}

    recs = R.run_reasoning_ladder(Driver(), "m", 4.0, model_pid=None, params={}, grid=(2000,), threshold=0.0,
                                  samples=1, chain_len=2, sampler_factory=FakeSampler)
    assert recs[0]["rows"][0]["session_id"] == "p426-r-1"


def test_the_driver_passes_the_session_id_through(monkeypatch):
    from bench.driver import MlxServeDriver

    monkeypatch.setattr(C, "probe", lambda *a, **k: dict(_fake_probe_result(), session_id="p426-d-1"))
    assert MlxServeDriver().complete("m", [], {})["session_id"] == "p426-d-1"
