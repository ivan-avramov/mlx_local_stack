"""M72 1.3 A8 (stack side): ``tq4_attention`` is provenance.

The TQ4 attention mode changes WHICH kernels serve attention (and, for ``m72_v1``, makes MTP ON non-exact), so rows served under
different values never pool and never compare. The resolution mirrors the M57 / M58 serving controls: the live worker's command
line (``--tq4-attention <mode>``, absent = the default) is the serving truth, the registry the fallback, a disagreement refuses,
a value outside the closed set refuses. The fingerprint version is bumped; rows from before the bump read the default.

Every test is classed in its comment: [new] exercises new behaviour, [invariant] preserves an invariant of today's code.
Names follow the sibling controls (``attention_policy``, ``mtp_verify_scan``): the runtime key and its ``_source`` are
``tq4_attention`` / ``tq4_attention_source``.
"""

import pytest
import yaml

import bench.provenance as P

KEY = "tq4_attention"
MODES = ("m72_v1", "m72_exact")
_WORKER = ["python", "-m", "mlx_vlm.server", "--model", "caslca/modelX-4bit", "--port", "8091"]


def _registry(tmp_path, mode=None, **extra):
    entry = {"name": "modelX", "hf_path": "caslca/modelX-4bit", **extra}
    if mode is not None:
        entry[KEY] = mode
    p = tmp_path / "tq4_reg.yaml"
    p.write_text(yaml.safe_dump({"models": [entry]}))
    return str(p)


def _stub_block_inputs(monkeypatch):
    monkeypatch.setattr(P, "apc_state", lambda: {"apc_enabled": "0", "source": "process"})
    monkeypatch.setattr(P, "registry_draft", lambda m, path=None: {"draft_kind": "mtp"})
    monkeypatch.setattr(
        P,
        "session_retention_state",
        lambda: {"session_retain_prompt_end": "on", "session_retain_source": "worker"},
    )


def _default():
    return P._SERVING_CONTROLS[KEY][1]


def _man(v, tq4=None, scan="per_query", **rt_extra):
    rt = dict(rt_extra)
    if v >= 7:
        rt.update({"lazy_prompt_embeddings": False, "attention_policy": "auto"})
    if v >= 8:
        rt["mtp_verify_scan"] = scan
    if tq4 is not None:
        rt[KEY] = tq4
    return {"sampling_profile": "deployed", "fingerprint_version": v, "sampling": {}, "kv": {}, "runtime": rt}


# ------------------------------------------------------------------ the version table
# [new] the fingerprint version is bumped and the control is introduced at (or after) the bump, with a default that is no mode
def test_fingerprint_version_is_bumped_and_the_control_is_registered():
    assert P.FINGERPRINT_VERSION >= 9
    intro, default = P._SERVING_CONTROLS[KEY]
    assert intro >= 9 and intro <= P.FINGERPRINT_VERSION
    assert default not in MODES


# [invariant] the earlier controls keep their introduction versions and defaults
def test_earlier_controls_are_unchanged():
    assert P._SERVING_CONTROLS["attention_policy"] == (7, "auto")
    assert P._SERVING_CONTROLS["lazy_prompt_embeddings"] == (7, False)
    assert P._SERVING_CONTROLS["mtp_verify_scan"] == (8, "per_query")


# ------------------------------------------------------------------ registry / worker resolution (through the runtime block)
# [new] the registry value is read (source registry); absent reads the default
@pytest.mark.parametrize("mode", MODES)
def test_runtime_block_reads_the_registry_value(monkeypatch, tmp_path, mode):
    _stub_block_inputs(monkeypatch)
    block = P._runtime_block(None, model="modelX", registry_path=_registry(tmp_path, mode))
    assert block[KEY] == mode and block[KEY + "_source"] == "registry"


def test_runtime_block_absent_key_reads_the_default(monkeypatch, tmp_path):
    _stub_block_inputs(monkeypatch)
    block = P._runtime_block(None, model="modelX", registry_path=_registry(tmp_path))
    assert block[KEY] == _default() and block[KEY + "_source"] == "registry"


# [new] the live worker's flag is the serving truth (source worker); a worker without the flag reads the default
@pytest.mark.parametrize("mode", MODES)
def test_worker_flag_is_observed(monkeypatch, tmp_path, mode):
    _stub_block_inputs(monkeypatch)
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [_WORKER + ["--tq4-attention", mode]])
    block = P._runtime_block(None, model="modelX", registry_path=_registry(tmp_path, mode))
    assert block[KEY] == mode and block[KEY + "_source"] == "worker"


def test_worker_without_the_flag_reads_the_default(monkeypatch, tmp_path):
    _stub_block_inputs(monkeypatch)
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [_WORKER])
    block = P._runtime_block(None, model="modelX", registry_path=_registry(tmp_path))
    assert block[KEY] == _default() and block[KEY + "_source"] == "worker"


# [new] worker / registry disagreement refuses (C35 shape), both directions and mode against mode
@pytest.mark.parametrize(
    "registry_mode,worker_extra",
    [("m72_v1", []), (None, ["--tq4-attention", "m72_v1"]), ("m72_v1", ["--tq4-attention", "m72_exact"])],
    ids=["registry-on-worker-off", "registry-off-worker-on", "v1-vs-exact"],
)
def test_disagreement_refuses(monkeypatch, tmp_path, registry_mode, worker_extra):
    _stub_block_inputs(monkeypatch)
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [_WORKER + worker_extra])
    with pytest.raises(P.ServingStateError, match="C35 tripwire.*tq4_attention"):
        P._runtime_block(None, model="modelX", registry_path=_registry(tmp_path, registry_mode))


# [new] a value outside the closed set never becomes provenance
@pytest.mark.parametrize("value", ["m72_v2", "M72_V1", "on", "true"])
def test_unrecognised_registry_value_refuses(monkeypatch, tmp_path, value):
    _stub_block_inputs(monkeypatch)
    with pytest.raises(P.ServingStateError, match="tq4_attention"):
        P._runtime_block(None, model="modelX", registry_path=_registry(tmp_path, value))


# [new] assert_serving_state carries the control; an observed control is never overridable by a caller (D3 shape)
def test_assert_serving_state_includes_the_control(tmp_path):
    out = P.assert_serving_state("modelX", _registry(tmp_path, "m72_exact"))
    assert out[KEY] == "m72_exact" and out[KEY + "_source"] == "registry"


def test_runtime_override_of_the_control_is_refused(monkeypatch, tmp_path):
    _stub_block_inputs(monkeypatch)
    with pytest.raises(P.ServingStateError):
        P._runtime_block({KEY: "m72_v1"}, model="modelX", registry_path=_registry(tmp_path))


# [new] the manifest carries the version and the recorded control
def test_manifest_records_the_mode(monkeypatch, tmp_path):
    _stub_block_inputs(monkeypatch)
    runtime = P._runtime_block(None, model="modelX", registry_path=_registry(tmp_path, "m72_v1"))
    man = P.build_manifest(
        model="modelX", box="b", ts=1, git_shas={}, kv={}, quant={}, sampling={}, runtime=runtime
    )
    assert man["fingerprint_version"] == P.FINGERPRINT_VERSION
    assert man["runtime"][KEY] == "m72_v1"
    assert P.config_fingerprint(man)["runtime"][KEY] == "m72_v1"


# ------------------------------------------------------------------ pooling / comparison
def _v():
    return P.FINGERPRINT_VERSION


# [new] rows from before the bump ARE the default: compatible with a bumped row at the default, never with a mode row
def test_pre_bump_rows_read_the_default():
    old = _man(8)
    assert P.control_of(old, KEY)[0] == _default()
    assert P.is_compatible(old, _man(_v(), tq4=_default())) and P.is_compatible(_man(_v(), tq4=_default()), old)
    for mode in MODES:
        assert not P.is_compatible(old, _man(_v(), tq4=mode))
        assert not P.is_compatible(_man(_v(), tq4=mode), old)


# [new] different modes never pool; the same mode does
def test_modes_never_pool():
    assert not P.is_compatible(_man(_v(), tq4="m72_v1"), _man(_v(), tq4="m72_exact"))
    assert not P.is_compatible(_man(_v(), tq4="m72_exact"), _man(_v(), tq4=_default()))
    for mode in (*MODES, _default()):
        assert P.is_compatible(_man(_v(), tq4=mode), _man(_v(), tq4=mode))


# [new] an unresolved value on a row new enough to carry it reads unknown and pools with nothing, itself included (T2)
def test_unresolved_value_never_pools():
    absent = _man(_v())
    assert P.control_of(absent, KEY)[0] == "unknown"
    assert not P.is_compatible(absent, absent)
    assert not P.is_compatible(absent, _man(_v(), tq4=_default()))
    bad = _man(_v(), tq4="m72_v2")
    assert P.control_of(bad, KEY)[0] == "unknown"
    assert not P.is_compatible(bad, bad)


# [invariant] the v7 / v8 rows on disk stay compatible with each other (the earlier per-control versions are untouched)
def test_v7_and_v8_rows_stay_compatible():
    assert P.is_compatible(_man(7), _man(8))
    assert P.is_compatible(_man(8), _man(8))
