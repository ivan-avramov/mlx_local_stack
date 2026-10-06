"""C121 B3: `scaffold_policy_sha256` is part of the comparison identity. Same hash compares; a
different hash refuses; a legacy opencode manifest (no hash) reads "pre-C121" and refuses against
a post-C121 row; non-opencode manifests are unaffected."""
import json

import bench.compare as CMP
import bench.generate as G
from bench import provenance
from bench.tests.test_compare import _rows as _cmp_rows
from bench.tests.test_opencode_probe_seeding import fake_model_mtp_scan  # noqa: F401


def _manifest(model, bench, *, policy=None, client="opencode", version=7):
    p = G.result_path(model, bench).with_suffix(".manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    rt = {"apc_enabled": "0", "draft_kind": "off", "lazy_prompt_embeddings": False, "attention_policy": "auto",
          "client": client}
    if policy is not None:
        rt["scaffold_policy_sha256"] = policy
    p.write_text(json.dumps({
        "box": "M5", "sampling_profile": "deployed", "fingerprint_version": version,
        "sampling": {"temperature": 0.4, "thinking_budget": 16384, "max_tokens": 102400},
        "kv": {"kv_bits": 0, "max_kv_cache_size": 131072}, "runtime": rt}))


def _pair(write_rows, a, b, client="opencode"):
    write_rows("A", "math500", _cmp_rows(["a", "b"]))
    write_rows("B", "math500", _cmp_rows(["a", "b"]))
    _manifest("A", "math500", policy=a, client=client)
    _manifest("B", "math500", policy=b, client=client)


def test_scaffold_policy_of_reads_pre_c121_for_a_legacy_opencode_manifest():
    assert provenance.scaffold_policy_of({"runtime": {"client": "opencode"}}) == "pre-C121"
    assert provenance.scaffold_policy_of({"runtime": {"client": "opencode", "scaffold_policy_sha256": "x"}}) == "x"
    assert provenance.scaffold_policy_of({"runtime": {"client": "bench"}}) == "n/a"


def test_compare_refuses_differing_scaffold_policy_hashes(write_rows, tmp_results):
    _pair(write_rows, "aaa", "bbb")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "scaffold_policy_sha256" in r["reason"]


def test_compare_refuses_legacy_vs_post_c121(write_rows, tmp_results):
    _pair(write_rows, None, "bbb")
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False and "pre-C121" in r["reason"]


def test_compare_passes_on_the_same_hash(write_rows, tmp_results):
    _pair(write_rows, "aaa", "aaa")
    assert CMP.compare("A", "B", "math500")["comparable"] is True


def test_compare_ignores_the_field_for_non_opencode_manifests(write_rows, tmp_results):
    _pair(write_rows, None, None, client="bench")
    assert CMP.compare("A", "B", "math500")["comparable"] is True


def test_is_compatible_refuses_differing_or_legacy_scaffold_policy():
    base = {"fingerprint_version": 7, "sampling_profile": "deployed", "sampling": {}, "kv": {},
            "runtime": {"client": "opencode", "lazy_prompt_embeddings": False, "attention_policy": "auto"}}

    def m(h):
        d = json.loads(json.dumps(base))
        if h:
            d["runtime"]["scaffold_policy_sha256"] = h
        return d
    assert provenance.is_compatible(m("a"), m("a")) is True
    assert provenance.is_compatible(m("a"), m("b")) is False
    assert provenance.is_compatible(m(None), m("a")) is False


# ---------------------------------------------------------------- C4: generate never cleans opencode rows
def test_clean_stale_never_deletes_legacy_opencode_rows(tmp_path, monkeypatch, fake_model_mtp_scan):
    G.RESULTS  # noqa: B018
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    d = tmp_path / "m"; d.mkdir()
    (d / "opencode.jsonl").write_text('{"id": "python/x", "sample": 0}\n')
    (d / "opencode.manifest.json").write_text(json.dumps(
        {"sampling_profile": "deployed", "sampling": {}, "kv": {}, "fingerprint_version": 7,
         "runtime": {"client": "opencode", "attention_policy": "auto", "lazy_prompt_embeddings": False}}))
    monkeypatch.setattr(provenance, "current_manifest_lite", lambda m, profile, **k:
                        {"sampling_profile": "deployed", "sampling": {}, "kv": {}, "fingerprint_version": 7,
                         "runtime": {"attention_policy": "auto", "lazy_prompt_embeddings": False}})
    acts = G.provenance_precheck(["m"], ["opencode"], profile="deployed", clean_stale=True)
    assert (d / "opencode.jsonl").exists() and (d / "opencode.manifest.json").exists()
    assert ("m", "opencode", "cleaned") not in acts
