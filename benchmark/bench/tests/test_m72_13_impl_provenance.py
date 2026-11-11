"""v9 (M72 1.3, A8): the TQ4 attention mode is provenance; its route counters ride the manifest.

`tq4_attention` (`off` | `m72_v1` | `m72_exact`) selects WHICH kernels serve TurboQuant 4 layers, so rows at
different values never pool and never compare. The live worker's `--tq4-attention` flag is the serving truth
(absent = `off`), the registry the fallback, a disagreement refuses. The worker's `/health` route counters are
recorded at manifest creation (`manifest["tq4_route_counts_at_creation"]`) and at the C106 exit re-verification
(`tq4_route_counts_at_exit` in the exit block, stored as `manifest["router_exit"]`), outside the fingerprint.
"""
import pytest
import yaml

import bench.provenance as P

KEY = "tq4_attention"
_WORKER = ["python", "-m", "mlx_vlm.server", "--model", "caslca/modelX-4bit", "--port", "8091"]


def _registry(tmp_path, mode=None, port=8091):
    entry = {"name": "modelX", "hf_path": "caslca/modelX-4bit"}
    if mode is not None:
        entry[KEY] = mode
    doc = {"models": [entry]}
    if port is not None:
        doc["mlx_port"] = port
    p = tmp_path / "tq4_reg.yaml"
    p.write_text(yaml.safe_dump(doc))
    return str(p)


def _resolve(tmp_path, mode=None, argv=None):
    return P.registry_tq4_attention(
        "modelX", _registry(tmp_path, mode),
        worker_lookup=(lambda: [argv]) if argv is not None else (lambda: None))


def _man(v, mode=None, **rt):
    runtime = dict(rt)
    if v >= 7:
        runtime.update({"lazy_prompt_embeddings": False, "attention_policy": "auto"})
    if v >= 8:
        runtime["mtp_verify_scan"] = "per_query"
    if mode is not None:
        runtime[KEY] = mode
    return {"sampling_profile": "deployed", "fingerprint_version": v, "sampling": {}, "kv": {},
            "runtime": runtime}


# --------------------------------------------------------------------------- the version table
def test_fingerprint_version_is_9_and_the_control_is_introduced_at_9():
    assert P.FINGERPRINT_VERSION == 9
    assert P._SERVING_CONTROLS[KEY] == (9, "off")
    assert P._CONTROL_VALUES[KEY] == ("off", "m72_v1", "m72_exact")


@pytest.mark.parametrize("v", [1, 5, 7, 8])
def test_pre_v9_manifests_read_off(v):
    assert P.control_of(_man(v), KEY) == ("off", "default-pre-v9")
    assert P.control_of(_man(v, "m72_v1"), KEY) == ("off", "default-pre-v9")


def test_v9_manifest_reports_its_value_and_unknown_when_missing_or_unrecognised():
    assert P.control_of(_man(9, "m72_exact"), KEY)[0] == "m72_exact"
    assert P.control_of(_man(9), KEY)[0] == "unknown"
    assert P.control_of(_man(9, "m72_v2"), KEY)[0] == "unknown"


# --------------------------------------------------------------------------- the fingerprint
def test_fingerprint_carries_the_mode():
    assert P.config_fingerprint(_man(9, "m72_v1"))["runtime"][KEY] == "m72_v1"
    assert KEY not in (P.config_fingerprint(_man(8)).get("runtime") or {})


@pytest.mark.parametrize("a,b,ok", [
    ("off", "off", True),
    ("m72_v1", "m72_v1", True),
    ("m72_exact", "m72_exact", True),
    ("off", "m72_v1", False),
    ("m72_v1", "m72_exact", False),
    ("off", "m72_exact", False),
])
def test_rows_at_different_modes_never_pool(a, b, ok):
    assert P.is_compatible(_man(9, a), _man(9, b)) is ok


def test_v8_rows_pool_with_v9_off_rows_only():
    assert P.is_compatible(_man(8), _man(9, "off"))
    assert not P.is_compatible(_man(8), _man(9, "m72_v1"))
    assert not P.is_compatible(_man(8), _man(9, "m72_exact"))


def test_unknown_never_pools_even_with_itself():
    assert not P.is_compatible(_man(9), _man(9))


def test_route_counts_are_outside_the_fingerprint():
    a, b = _man(9, "m72_v1"), _man(9, "m72_v1")
    a["tq4_route_counts_at_creation"] = {"mode": "m72_v1", "route_counts": {"p2s": 1}}
    b["tq4_route_counts_at_creation"] = {"mode": "m72_v1", "route_counts": {"p2s": 99, "mma": 7}}
    a["router_exit"] = {"pid": 1, "tq4_route_counts_at_exit": {"mode": "m72_v1", "route_counts": {"p2s": 2}}}
    b["router_exit"] = {"pid": 1, "tq4_route_counts_at_exit": {"mode": "m72_v1", "route_counts": {"p2s": 9}}}
    assert P.config_fingerprint(a) == P.config_fingerprint(b)
    assert P.is_compatible(a, b)


# --------------------------------------------------------------------------- the resolver
def test_absent_everywhere_is_off_from_the_registry(tmp_path):
    assert _resolve(tmp_path) == {KEY: "off", KEY + "_source": "registry"}


@pytest.mark.parametrize("mode", ["m72_v1", "m72_exact"])
def test_registry_value_without_a_worker(tmp_path, mode):
    assert _resolve(tmp_path, mode) == {KEY: mode, KEY + "_source": "registry"}


@pytest.mark.parametrize("mode", ["m72_v1", "m72_exact"])
def test_worker_flag_is_the_serving_truth(tmp_path, mode):
    got = _resolve(tmp_path, mode, argv=_WORKER + ["--tq4-attention", mode])
    assert got == {KEY: mode, KEY + "_source": "worker"}


def test_worker_without_the_flag_serves_off(tmp_path):
    assert _resolve(tmp_path, None, argv=_WORKER) == {KEY: "off", KEY + "_source": "worker"}


@pytest.mark.parametrize("reg,flag", [("m72_v1", None), (None, "m72_v1"), ("m72_v1", "m72_exact")])
def test_worker_registry_disagreement_refuses(tmp_path, reg, flag):
    argv = _WORKER + (["--tq4-attention", flag] if flag else [])
    with pytest.raises(P.ServingStateError, match="tq4_attention"):
        _resolve(tmp_path, reg, argv=argv)


def test_out_of_set_value_refuses(tmp_path):
    with pytest.raises(P.ServingStateError, match="tq4_attention"):
        _resolve(tmp_path, "m72_v2")


def test_model_absent_is_unknown(tmp_path):
    got = P.registry_tq4_attention("other", _registry(tmp_path, "m72_v1"),
                                   worker_lookup=lambda: None)
    assert got[KEY] == "unknown"


def test_runtime_block_records_the_mode_and_refuses_an_override(tmp_path, monkeypatch):
    reg = _registry(tmp_path, "m72_v1")
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [])
    monkeypatch.setattr(P, "apc_state", lambda **k: {"apc_enabled": "0", "source": "env"})
    block = P._runtime_block(None, model="modelX", registry_path=reg)
    assert block[KEY] == "m72_v1" and block[KEY + "_source"] == "registry"
    with pytest.raises(P.ServingStateError):
        P._runtime_block({KEY: "off"}, model="modelX", registry_path=reg)


def test_assert_serving_state_includes_the_mode_and_refuses_a_change(tmp_path, monkeypatch):
    reg = _registry(tmp_path, "m72_exact")
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [])
    out = P.assert_serving_state("modelX", reg)
    assert out[KEY] == "m72_exact"
    with pytest.raises(P.ServingStateError, match="tq4_attention changed"):
        P.assert_serving_state("modelX", reg, expect={"mtp_verify_scan": "per_query",
                                                      KEY: "m72_v1"})


# --------------------------------------------------------------------------- route counters
COUNTS = {"p2s": 16, "mma": 40, "d2": 3, "native:prefill": 1, "native:verify": 40}


def test_route_counts_read_from_the_worker_health(tmp_path, monkeypatch):
    reg = _registry(tmp_path, "m72_v1", port=8091)
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [])
    seen = []

    def health(port):
        seen.append(port)
        return {"status": "healthy", KEY: {"mode": "m72_v1", "route_counts": COUNTS}}

    got = P.tq4_route_counts("modelX", reg, health=health)
    assert seen == [8091]
    assert got == {"mode": "m72_v1", "route_counts": COUNTS, "source": "worker-health"}


def test_route_counts_absent_when_the_mode_is_off(tmp_path, monkeypatch):
    reg = _registry(tmp_path, None)
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [])

    def health(port):  # never called
        raise AssertionError("no /health read when the mode is off")

    assert P.tq4_route_counts("modelX", reg, health=health)["route_counts"] is None


@pytest.mark.parametrize("body,source", [
    ({"status": "healthy"}, "health-without-tq4-block"),
    ({KEY: {"mode": "m72_v1"}}, "health-without-tq4-block"),
])
def test_route_counts_record_why_they_are_missing(tmp_path, monkeypatch, body, source):
    reg = _registry(tmp_path, "m72_v1")
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [])
    got = P.tq4_route_counts("modelX", reg, health=lambda port: body)
    assert got["route_counts"] is None and got["source"] == source


def test_route_counts_unreachable_worker_is_recorded(tmp_path, monkeypatch):
    reg = _registry(tmp_path, "m72_v1")
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [])

    def down(port):
        raise ConnectionRefusedError("nobody listens")

    got = P.tq4_route_counts("modelX", reg, health=down)
    assert got["route_counts"] is None and got["source"].startswith("unavailable")


def test_route_counts_refuse_a_mode_mismatch(tmp_path, monkeypatch):
    reg = _registry(tmp_path, "m72_v1")
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [])
    with pytest.raises(P.ServingStateError):
        P.tq4_route_counts("modelX", reg, health=lambda port: {
            KEY: {"mode": "m72_exact", "route_counts": COUNTS}})


def test_gather_records_the_route_counts_only_under_a_mode(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(P, "registry_kv", lambda m, path: {"kv_bits": 4})
    monkeypatch.setattr(P, "_resolve_snapshot", lambda hf: None)
    monkeypatch.setattr(P.model_params, "params_for", lambda m, profile, **k: {})
    monkeypatch.setattr(P, "router_block", lambda base: {"pid": 1, "port": 8000})
    monkeypatch.setattr(P, "_TQ4_MANIFESTS", {})
    monkeypatch.setattr(P, "_registry_state", lambda path: {})

    def runtime(mode):
        def block(rt, model, registry_path):
            return {"mtp_verify_scan": "per_query", KEY: mode}
        return block

    monkeypatch.setattr(P, "tq4_route_counts", lambda m, path: calls.append(m) or {
        "mode": "m72_v1", "route_counts": COUNTS, "source": "worker-health"})
    monkeypatch.setattr(P, "_runtime_block", runtime("m72_v1"))
    man = P.gather("modelX", str(tmp_path / "r.yaml"))
    assert man["tq4_route_counts_at_creation"]["route_counts"] == COUNTS and calls == ["modelX"]
    assert "tq4_route_counts" not in man
    assert P._TQ4_MANIFESTS == {8000: ("modelX", str(tmp_path / "r.yaml"))}
    monkeypatch.setattr(P, "_TQ4_MANIFESTS", {})
    monkeypatch.setattr(P, "_runtime_block", runtime("off"))
    off = P.gather("modelX", str(tmp_path / "r.yaml"))
    assert not [k for k in off if k.startswith("tq4_route_counts")]
    assert P._TQ4_MANIFESTS == {}


# --------------------------------------------------------------------------- route counters at exit (C106 / M50)
EXIT_COUNTS = {"p2s": 99, "mma": 400, "d2": 3000}


def _gather_under(monkeypatch, tmp_path, mode, counts):
    monkeypatch.setattr(P, "registry_kv", lambda m, path: {"kv_bits": 4})
    monkeypatch.setattr(P, "_resolve_snapshot", lambda hf: None)
    monkeypatch.setattr(P.model_params, "params_for", lambda m, profile, **k: {})
    monkeypatch.setattr(P, "router_block", lambda base: {"pid": 7, "port": 8000, "config_sha256": "a" * 64})
    monkeypatch.setattr(P, "_registry_state", lambda path: {})
    monkeypatch.setattr(P, "_runtime_block",
                        lambda rt, model, registry_path: {"mtp_verify_scan": "joint_v1", KEY: mode})
    monkeypatch.setattr(P, "tq4_route_counts", lambda m, path: {
        "mode": mode, "route_counts": dict(counts), "source": "worker-health"})
    return P.gather("modelX", str(tmp_path / "r.yaml"))


def _exit_check(monkeypatch, *, pid=7, sha="a" * 64):
    monkeypatch.setattr(P, "assert_served_config", lambda *a, **k: {
        "pid": pid, "config": "~/r.yaml", "port": 8000, "config_sha256": sha})
    return P.assert_served_config_unchanged({"pid": 7, "port": 8000, "config_sha256": "a" * 64},
                                            "http://localhost:8000")


def test_exit_block_records_the_route_counters_at_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_TQ4_MANIFESTS", {})
    man = _gather_under(monkeypatch, tmp_path, "m72_v1", COUNTS)
    monkeypatch.setattr(P, "tq4_route_counts", lambda m, path: {
        "mode": "m72_v1", "route_counts": dict(EXIT_COUNTS), "source": "worker-health"})
    exit_blk = _exit_check(monkeypatch)
    assert exit_blk["verified_at"] == "exit" and exit_blk["pid"] == 7
    assert exit_blk["tq4_route_counts_at_exit"]["route_counts"] == EXIT_COUNTS
    assert man["tq4_route_counts_at_creation"]["route_counts"] == COUNTS
    man["router_exit"] = exit_blk
    assert P.config_fingerprint(man) == P.config_fingerprint(
        {**man, "tq4_route_counts_at_creation": None, "router_exit": None})


def test_exit_block_is_unchanged_without_a_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_TQ4_MANIFESTS", {})
    _gather_under(monkeypatch, tmp_path, "off", COUNTS)

    def never(m, path):
        raise AssertionError("no route counters read without a mode")

    monkeypatch.setattr(P, "tq4_route_counts", never)
    exit_blk = _exit_check(monkeypatch)
    assert set(exit_blk) == {"pid", "config", "port", "config_sha256", "verified_at"}


def test_exit_snapshot_failure_is_recorded_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_TQ4_MANIFESTS", {})
    _gather_under(monkeypatch, tmp_path, "m72_exact", COUNTS)

    def mismatch(m, path):
        raise P.ServingStateError("the worker's /health reports tq4_attention 'm72_v1'")

    monkeypatch.setattr(P, "tq4_route_counts", mismatch)
    got = _exit_check(monkeypatch)["tq4_route_counts_at_exit"]
    assert got["route_counts"] is None and got["source"].startswith("refused: ServingStateError")


def test_exit_drift_still_refuses_before_any_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_TQ4_MANIFESTS", {})
    _gather_under(monkeypatch, tmp_path, "m72_v1", COUNTS)
    calls = []
    monkeypatch.setattr(P, "tq4_route_counts", lambda m, path: calls.append(m) or {})
    with pytest.raises(P.ServedConfigError, match="router pid changed"):
        _exit_check(monkeypatch, pid=8)
    with pytest.raises(P.ServedConfigError, match="content changed"):
        _exit_check(monkeypatch, sha="b" * 64)
    assert calls == []
