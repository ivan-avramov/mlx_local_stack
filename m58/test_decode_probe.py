"""Tests for decode_probe.py: mock HTTP router, fake provenance, no model, no :8000."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import decode_probe as dp  # noqa: E402
from bench import client, model_params  # noqa: E402


class ServedConfigError(RuntimeError):
    pass


class PreflightError(RuntimeError):
    pass


class FakeProv(SimpleNamespace):
    pass


def make_prov(drift_at_exit=False, scan="joint_v1", loaded_scan=None):
    calls = {"exit": 0, "state": [], "gather": [], "entry": 0}
    block = {"pid": 11, "config": "$HOME/reg.yaml", "config_sha256": "ab" * 32, "port": 8000}

    def entry(base=None):
        calls["entry"] += 1
        return dict(block)

    def state(model, registry_path=None, expect=None):
        calls["state"].append(expect)
        v = scan if expect is None else (loaded_scan or scan)
        if expect is not None and expect["mtp_verify_scan"] != v:
            raise ServedConfigError("scan changed")
        return {"mtp_verify_scan": v}

    def unchanged(e, base=None, **k):
        calls["exit"] += 1
        if drift_at_exit:
            raise ServedConfigError("served file content changed")
        return {**block, "verified_at": "exit"}

    def gather(model, **kw):
        calls["gather"].append(kw)
        return {"runtime": {"draft_kind": "mtp"}, "registry": {"sha256": "cd" * 32}, "router": kw.get("router")}

    p = FakeProv(ServedConfigError=ServedConfigError, ProvenancePreflightError=PreflightError,
                 assert_served_config=entry, assert_serving_state=state,
                 preflight_gather=lambda *a, **k: {}, gather=gather,
                 assert_served_config_unchanged=unchanged,
                 served_config_drift_record=lambda e, b, err: {"entry_sha256": e["config_sha256"],
                                                               "exit_sha256": "zz", "error": str(err)})
    p.calls = calls
    return p


class Mock:
    def __init__(self, ctoks=1600, fail_on=None, tps=30.0, ptoks=None):
        self.requests, self.ctoks, self.fail_on, self.tps, self.ptoks = [], ctoks, fail_on, tps, ptoks
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/v1/models/load":
                    return self._send({"ok": True})
                outer.requests.append(body)
                n = len(outer.requests)
                if outer.fail_on == n:
                    self.send_response(500); self.end_headers(); return
                ct = outer.ctoks[n - 1] if isinstance(outer.ctoks, list) else outer.ctoks
                pt = outer.ptoks or 50000
                self._send({"choices": [{"message": {"content": "x"}, "finish_reason": "length"}],
                            "usage": {"prompt_tokens": pt, "completion_tokens": ct},
                            "timings": {"predicted_per_second": outer.tps, "predicted_ms": 1000.0,
                                        "prompt_ms": 5000.0, "draft_kind": "mtp", "draft_rounds": 500,
                                        "draft_n": 1000, "draft_n_accepted": 800,
                                        "verify_blocks_joint_v1": 7, "sdpa_auto": 3}})

            def _send(self, d):
                b = json.dumps(d).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers()
                self.wfile.write(b)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


@pytest.fixture
def env(monkeypatch, tmp_path):
    mocks = []

    def setup(prov=None, **kw):
        m = Mock(**kw); mocks.append(m)
        monkeypatch.setattr(client, "BASE", m.url)
        monkeypatch.setattr(dp, "provenance", prov or make_prov())
        monkeypatch.setattr(model_params, "params_for", lambda model, profile="x", registry_path=None:
                            {"temperature": 0.3, "top_p": 0.9, "thinking_budget": 8000})
        monkeypatch.setattr(model_params, "registry_context_limit", lambda *a, **k: 300000)
        return m
    yield setup
    for m in mocks:
        m.close()


def args(tmp_path, *extra, out="o.json"):
    return ["run", "--model", "M", "--sampling-profile", "deployed", "--tag", "T", "--contexts", "2048,4096",
            "--prompts-per-rung", "2", "--seed-base", "5", "--cpt", "4.0", "--no-preload", "--no-power",
            "--out", str(tmp_path / out), "--watch-log", str(tmp_path / "w.log"), *extra]


def test_seed_and_params_propagate(env, tmp_path):
    m = env()
    assert dp.main(args(tmp_path)) == 0
    assert len(m.requests) == 4
    for body, (c, i) in zip(m.requests, [(2048, 0), (2048, 1), (4096, 0), (4096, 1)]):
        assert body["seed"] == dp.rowschema.sample_seed(f"decode:{c}:{i}", 0, base=5)
        assert body["max_tokens"] == 1536 and body["thinking_budget"] == 8000
        assert body["temperature"] == 0.3 and body["enable_thinking"] is True
    assert m.requests[0]["seed"] != m.requests[1]["seed"]
    d = json.load(open(tmp_path / "o.json"))
    assert d["status"] == "complete" and (tmp_path / "o.json.manifest.json").exists()
    assert d["rows"][0]["counters"]["verify_blocks_joint_v1"] == 7
    assert d["rows"][0]["decode_tps"] == 30.0 and d["rows"][0]["prefill_s"] == 5.0
    assert "1/4 ctx=2048" in open(tmp_path / "w.log").read()


def test_derived_timeout():
    assert dp.derive_timeout(262144, 1536, 8.0, 100.0, 900.0) == pytest.approx(262144 / 100 + 1536 / 8 + 900)


def test_timeout_reaches_client(env, tmp_path, monkeypatch):
    env()
    seen = []
    real = client.probe
    monkeypatch.setattr(client, "probe", lambda *a, **k: (seen.append(k["timeout"]), real(*a, **k))[1])
    assert dp.main(args(tmp_path)) == 0
    assert seen[0] == pytest.approx(2048 / 100 + 1536 / 8 + 900)
    assert seen[2] == pytest.approx(4096 / 100 + 1536 / 8 + 900)


def test_short_rows_marked_and_not_pooled(env, tmp_path):
    env(ctoks=[1600, 300, 1600, 1600], tps=[30.0][0])
    assert dp.main(args(tmp_path)) == 0
    d = json.load(open(tmp_path / "o.json"))
    assert [r["short"] for r in d["rows"]] == [False, True, False, False]
    s = d["summary"]["2048"]
    assert s["n"] == 2 and s["n_pooled"] == 1 and s["n_short"] == 1


def test_transport_error_aborts_journal_and_c106(env, tmp_path):
    prov = make_prov()
    env(prov, fail_on=2)
    assert dp.main(args(tmp_path)) == 2
    d = json.load(open(tmp_path / "o.json"))
    assert d["status"] == "aborted" and len(d["rows"]) == 1 and "ctx=2048 i=1" in d["error"]
    assert prov.calls["exit"] == 1


def test_malformed_response_aborts(env, tmp_path):
    env(tps=0)  # predicted_per_second invalid
    assert dp.main(args(tmp_path)) == 2
    assert json.load(open(tmp_path / "o.json"))["status"] == "aborted"


def test_exit_drift_stamps_and_fails(env, tmp_path):
    env(make_prov(drift_at_exit=True))
    assert dp.main(args(tmp_path)) == 2
    d = json.load(open(tmp_path / "o.json"))
    assert d["status"] == "aborted" and d["served_config_drift"]["exit_sha256"] == "zz"
    assert not (tmp_path / "o.json.manifest.json").exists()


def test_entry_refusal_writes_nothing(env, tmp_path):
    prov = make_prov()

    def boom(base=None):
        raise ServedConfigError("M50 no owner")
    prov.assert_served_config = boom
    m = env(prov)
    assert dp.main(args(tmp_path)) == 2
    assert not (tmp_path / "o.json").exists() and m.requests == []


def test_loaded_scan_change_refuses_before_requests(env, tmp_path):
    m = env(make_prov(scan="per_query", loaded_scan="joint_v1"))
    assert dp.main(args(tmp_path)) == 2
    assert m.requests == []
    assert dp.json.load(open(tmp_path / "o.json"))["status"] == "aborted"


def test_serving_state_called_with_entry_expect(env, tmp_path):
    prov = make_prov()
    env(prov)
    dp.main(args(tmp_path))
    assert prov.calls["state"][0] is None and prov.calls["state"][1] == {"mtp_verify_scan": "joint_v1"}


def test_resume_refused_on_drift_and_signature(env, tmp_path):
    env(make_prov(drift_at_exit=False), fail_on=3)
    assert dp.main(args(tmp_path)) == 2           # aborted after 2 rows
    # same router: resume works
    m = env()
    assert dp.main(args(tmp_path, "--resume")) == 0
    assert len(m.requests) == 2
    # complete journal: refuse
    assert dp.main(args(tmp_path, "--resume")) == 2


def test_resume_refused_when_registry_sha_changed(env, tmp_path):
    env(fail_on=2)
    assert dp.main(args(tmp_path)) == 2
    prov = make_prov()
    orig = prov.assert_served_config
    prov.assert_served_config = lambda b=None: {**orig(b), "config_sha256": "ee" * 32}
    m = env(prov)
    assert dp.main(args(tmp_path, "--resume")) == 2
    assert m.requests == []


def test_resume_refused_on_signature_change_and_existing_out(env, tmp_path):
    env(fail_on=2)
    dp.main(args(tmp_path))
    m = env()
    assert dp.main(args(tmp_path)) == 2                                   # exists, no --resume
    assert dp.main(args(tmp_path, "--resume", "--seed-base", "6")) == 2   # signature differs
    assert m.requests == []


def test_sampling_profile_required_deployed():
    with pytest.raises(SystemExit):
        dp.main(["run", "--model", "M", "--tag", "t", "--out", "x"])
    with pytest.raises(SystemExit):
        dp.main(["run", "--model", "M", "--tag", "t", "--out", "x", "--sampling-profile", "production"])


def test_context_headroom_refused(env, tmp_path, monkeypatch):
    m = env()
    monkeypatch.setattr(model_params, "registry_context_limit", lambda *a, **k: 4000)
    assert dp.main(args(tmp_path)) == 2 and m.requests == []


def test_heartbeat_line():
    w = dp.Watch(4, None, power=lambda: {"ac": "140W"})
    w.walls = [10.0, 20.0]; w.done = 2
    assert "HEARTBEAT 2/4" in w.heartbeat()


def _doc(tag, scan, tps_by_key, short=(), ptok=100):
    rows = [{"ctx": c, "i": i, "decode_tps": t, "short": (c, i) in short, "prompt_tokens": ptok,
             "rounds": 10, "acceptance": 0.8} for (c, i), t in tps_by_key.items()]
    return {"status": "complete", "tag": tag, "serving_state": {"mtp_verify_scan": scan},
            "signature": {"model": "M"}, "rows": rows}


def test_compare_pairing_and_delta():
    keys = {(65536, 0): 20.0, (65536, 1): 22.0, (65536, 2): 24.0, (131072, 0): 10.0}
    A = _doc("A", "per_query", keys)
    B = _doc("B", "joint_v1", {k: v * 1.1 for k, v in keys.items()})
    res = dp.compare_docs([A], [B], n_boot=500)
    r = res["rungs"]["65536"]
    assert r["n_pairs"] == 3 and r["median_delta_pct"] == pytest.approx(10.0)
    assert r["paired_deltas_pct"] == [10.0, 10.0, 10.0]
    assert r["ci95_median_ratio_pct"][0] == pytest.approx(10.0, abs=0.01)
    assert res["a_scan"] == ["per_query"] and res["b_scan"] == ["joint_v1"]


def test_compare_skips_short_missing_and_prompt_mismatch():
    A = _doc("A", "per_query", {(1, 0): 10.0, (1, 1): 10.0, (1, 2): 10.0}, short={(1, 1)})
    B = _doc("B", "joint_v1", {(1, 0): 11.0, (1, 1): 11.0})
    B["rows"][0]["prompt_tokens"] = 101
    res = dp.compare_docs([A], [B], n_boot=50)
    assert {s["why"] for s in res["skipped"]} == {"prompt_tokens differ", "short row", "missing in B"}
    assert res["rungs"] == {}


def test_compare_refuses_incomplete_signature_and_drift():
    A, B = _doc("A", "x", {(1, 0): 1.0}), _doc("B", "y", {(1, 0): 1.0})
    B["status"] = "aborted"
    with pytest.raises(ValueError):
        dp.compare_docs([A], [B])
    B["status"] = "complete"; B["signature"] = {"model": "N"}
    with pytest.raises(ValueError):
        dp.compare_docs([A], [B])
    B["signature"] = A["signature"]; B["served_config_drift"] = {}
    with pytest.raises(ValueError):
        dp.compare_docs([A], [B])
