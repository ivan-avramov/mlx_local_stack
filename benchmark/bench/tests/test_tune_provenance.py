"""D3: `tune` is stamped in the manifest (top-level `tune` field, omitted when absent/deployed)
and threaded through the generation loop's provenance seams (`stamp_manifests`,
`provenance_precheck`, `generate.run`) so a tuned run's manifest/jsonl land beside each other at
`<bench>.<tune>.*`, never colliding with — or being resumed against — the deployed baseline.
`tune` is explicitly NOT part of the fingerprint (docs/superpowers/specs/2026-08-17-tune-encoding-
migration-design.md): the resolved config already carries the delta, so `tune` is a key, not
provenance.
"""
import json

import bench.benchmarks as B
import bench.client as C
import bench.generate as G
import bench.provenance as P


def test_gather_stamps_tune_when_given(tmp_path, monkeypatch):
    reg = tmp_path / "reg.yaml"
    reg.write_text("models:\n  - name: m\n    hf_path: org/m\n    kv_bits: 0\n")
    man = P.gather("m", str(reg), tune="kv4")
    assert man["tune"] == "kv4"


def test_gather_omits_tune_field_when_absent(tmp_path):
    reg = tmp_path / "reg.yaml"
    reg.write_text("models:\n  - name: m\n    hf_path: org/m\n    kv_bits: 0\n")
    man = P.gather("m", str(reg))
    assert "tune" not in man


def test_tune_is_not_part_of_the_fingerprint(tmp_path):
    """Two manifests differing ONLY in `tune` must compare compatible — tune names the delta,
    the resolved config (already fingerprinted) is what makes results actually comparable."""
    reg = tmp_path / "reg.yaml"
    reg.write_text("models:\n  - name: m\n    hf_path: org/m\n    kv_bits: 0\n")
    a = P.gather("m", str(reg), tune="kv4")
    b = P.gather("m", str(reg))
    assert P.is_compatible(a, b) is True
    assert P.is_compatible(b, a) is True


def test_write_stamps_the_manifest_at_the_tuned_path(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    reg = tmp_path / "reg.yaml"
    reg.write_text("models:\n  - name: m\n    hf_path: org/m\n    kv_bits: 0\n")
    P.write("m", "aime", str(reg), tune="kv4")
    p = tmp_path / "m" / "aime.kv4.manifest.json"
    assert p.exists()
    man = json.loads(p.read_text())
    assert man["tune"] == "kv4"
    # the untouched deployed-tune manifest path must not exist
    assert not (tmp_path / "m" / "aime.manifest.json").exists()


def test_write_without_tune_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    reg = tmp_path / "reg.yaml"
    reg.write_text("models:\n  - name: m\n    hf_path: org/m\n    kv_bits: 0\n")
    P.write("m", "aime", str(reg))
    man = json.loads((tmp_path / "m" / "aime.manifest.json").read_text())
    assert "tune" not in man


def test_provenance_precheck_checks_the_tuned_jsonl_not_the_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    d = tmp_path / "m"
    d.mkdir(parents=True)
    (d / "aime.kv4.jsonl").write_text('{"id":"x"}\n')
    (d / "aime.kv4.manifest.json").write_text(json.dumps(
        {"sampling_profile": "production", "sampling": {"temperature": 0.7}, "kv": {"kv_bits": 0}}))
    monkeypatch.setattr(P, "current_manifest_lite", lambda m, profile, **k:
                        {"sampling_profile": "official", "sampling": {"temperature": 1.0}, "kv": {"kv_bits": 0}})
    acts = G.provenance_precheck(["m"], ["aime"], profile="official", clean_stale=True, tune="kv4")
    assert ("m", "aime", "cleaned") in acts
    assert not (d / "aime.kv4.jsonl").exists()
    # a plain (untuned) precheck over the same pair must find nothing to clean (no baseline file)
    acts2 = G.provenance_precheck(["m"], ["aime"], profile="official", clean_stale=True)
    assert acts2 == []


def _fake_probe_result():
    return {"content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
            "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0,
            "finish_reason": "stop", "wall_s": 0.1, "raw_timings": {}}


def test_generate_run_with_a_tune_writes_rows_and_manifest_at_the_tuned_path(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    monkeypatch.setattr(C, "probe", lambda model, messages, params, timeout=3600, tools=None:
                        _fake_probe_result())
    G.run(["m"], ["aime"], {}, tune="kv4")
    tuned = tmp_path / "m" / "aime.kv4.jsonl"
    assert tuned.exists()
    row = json.loads(tuned.read_text().splitlines()[0])
    assert row["id"] == "t1"
    assert not (tmp_path / "m" / "aime.jsonl").exists()
    man_path = tmp_path / "m" / "aime.kv4.manifest.json"
    assert man_path.exists()
    assert json.loads(man_path.read_text()).get("tune") == "kv4"
