"""generate.run must thread a configurable per-probe HTTP timeout to client.probe.

The default 3600s client timeout is shorter than a slow dense model's worst-case generation
(e.g. Qwen3.6-27B at ~13.5 tok/s reaching an ~80K-token thinking budget ≈ 100 min), so long
items time out before they can converge OR reach their budget. The run must be able to raise
this without touching client defaults or probe_with_recovery's signature.
"""
import json

import bench.benchmarks as B
import bench.client as C
import bench.generate as G
import bench.provenance as P


def _write_existing(tmp_path, model, bench, manifest):
    d = tmp_path / model
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{bench}.jsonl").write_text('{"id":"x","temperature":0.7}\n')
    if manifest is not None:
        (d / f"{bench}.manifest.json").write_text(json.dumps(manifest))
    return d


def test_provenance_precheck_cleans_stale_on_config_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_existing(tmp_path, "m", "aime",
                    {"sampling_profile": "production", "sampling": {"temperature": 0.7}, "kv": {"kv_bits": 0}})
    monkeypatch.setattr(P, "current_manifest_lite", lambda m, profile, **k:
                        {"sampling_profile": "official", "sampling": {"temperature": 1.0}, "kv": {"kv_bits": 0}})
    acts = G.provenance_precheck(["m"], ["aime"], profile="official", clean_stale=True)
    assert ("m", "aime", "cleaned") in acts
    assert not (tmp_path / "m" / "aime.jsonl").exists()


def test_provenance_precheck_warns_and_keeps_when_not_cleaning(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write_existing(tmp_path, "m", "aime",
                    {"sampling_profile": "production", "sampling": {"temperature": 0.7}, "kv": {"kv_bits": 0}})
    monkeypatch.setattr(P, "current_manifest_lite", lambda m, profile, **k:
                        {"sampling_profile": "official", "sampling": {"temperature": 1.0}, "kv": {"kv_bits": 0}})
    acts = G.provenance_precheck(["m"], ["aime"], profile="official", clean_stale=False)
    assert ("m", "aime", "stale") in acts
    assert (tmp_path / "m" / "aime.jsonl").exists()        # not deleted by default


def test_provenance_precheck_compatible_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    same = {"sampling_profile": "official", "sampling": {"temperature": 1.0}, "kv": {"kv_bits": 0}}
    _write_existing(tmp_path, "m", "aime", same)
    monkeypatch.setattr(P, "current_manifest_lite", lambda m, profile, **k: same)
    acts = G.provenance_precheck(["m"], ["aime"], profile="official", clean_stale=True)
    assert acts == []                                       # matching config -> resume, untouched
    assert (tmp_path / "m" / "aime.jsonl").exists()


def _fake_probe_result():
    return {"content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
            "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0,
            "finish_reason": "stop", "wall_s": 0.1, "raw_timings": {}}


def test_generate_run_threads_probe_timeout(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)

    def fake_probe(model, messages, params, timeout=3600, tools=None):
        captured["timeout"] = timeout
        return _fake_probe_result()

    monkeypatch.setattr(C, "probe", fake_probe)
    G.run(["m"], ["aime"], {}, probe_timeout=9000)
    assert captured["timeout"] == 9000


def test_generate_run_default_probe_timeout_is_client_default(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)

    def fake_probe(model, messages, params, timeout=3600, tools=None):
        captured["timeout"] = timeout
        return _fake_probe_result()

    monkeypatch.setattr(C, "probe", fake_probe)
    G.run(["m"], ["aime"], {})          # no override
    assert captured["timeout"] == 3600


def test_generate_run_persists_draft_counters(tmp_path, monkeypatch):
    """M6b engagement tripwire (C24): the server's per-request draft counters ride
    the response timings block; every generated row must persist them compactly —
    nulls under plain decode included, so an OFF arm is distinguishable from a
    row generated before the field existed."""
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)

    r = _fake_probe_result()
    r["raw_timings"] = {"draft_kind": "mtp", "draft_rounds": 3, "draft_n": 7,
                        "draft_n_accepted": 5, "predicted_per_second": 44.0}
    monkeypatch.setattr(C, "probe", lambda m, msgs, params, timeout=3600, tools=None: r)
    G.run(["m"], ["aime"], {})
    import json
    row = json.loads((tmp_path / "m" / "aime.jsonl").read_text().splitlines()[0])
    assert row["draft"] == {"draft_kind": "mtp", "draft_rounds": 3, "draft_n": 7,
                            "draft_n_accepted": 5}
