"""Tests for bench.provenance — stamping every results file with the EXACT config it was
produced under, so results can never be silently compared across boxes / code versions /
quant or KV configs (the apples-to-apples + quality-vs-bits requirement)."""
import bench.provenance as P


def test_config_fingerprint_is_output_determining_slice():
    man = {"sampling_profile": "official",
           "sampling": {"temperature": 1.0, "top_p": 0.95, "min_p": 0.0, "irrelevant": "x"},
           "kv": {"kv_bits": 0}, "quant": {"effective_bits": 6.0}, "box": "M5"}
    fp = P.config_fingerprint(man)
    assert fp["sampling_profile"] == "official"
    assert fp["sampling"]["temperature"] == 1.0
    assert fp["kv_bits"] == 0
    assert "irrelevant" not in fp["sampling"]   # only the output-determining keys
    assert "box" not in fp                       # box/time don't affect comparability


def test_is_compatible_detects_sampling_profile_temperature_kv_mismatch():
    prod = {"sampling_profile": "production", "sampling": {"temperature": 0.7}, "kv": {"kv_bits": 0}}
    offi = {"sampling_profile": "official", "sampling": {"temperature": 1.0}, "kv": {"kv_bits": 0}}
    kv4 = {"sampling_profile": "official", "sampling": {"temperature": 1.0}, "kv": {"kv_bits": 4}}
    assert P.is_compatible(prod, prod) is True
    assert P.is_compatible(prod, offi) is False    # the contamination we hit (temp 0.7 vs 1.0)
    assert P.is_compatible(offi, kv4) is False      # KV config change


def test_is_compatible_treats_missing_manifest_as_incompatible():
    # A results file with NO manifest (or unparseable) has unknown provenance -> not compatible.
    assert P.is_compatible(None, {"sampling_profile": "official"}) is False


def test_registry_kv_extracts_entry(tmp_path):
    yml = tmp_path / "reg.yaml"
    yml.write_text(
        "models:\n"
        "  - name: foo-4bit\n"
        "    hf_path: org/foo-4bit\n"
        "    kv_quant_scheme: turboquant\n"
        "    kv_bits: 4\n"
        "    quantized_kv_start: 0\n"
        "    prefill_step_size: 512\n"
        "  - name: bar-8bit\n"
        "    hf_path: org/bar-8bit\n"
        "    kv_bits: 0\n"
    )
    kv = P.registry_kv("foo-4bit", str(yml))
    assert kv["kv_bits"] == 4
    assert kv["kv_quant_scheme"] == "turboquant"
    assert kv["quantized_kv_start"] == 0
    assert kv["prefill_step_size"] == 512
    assert kv["hf_path"] == "org/foo-4bit"
    # bf16-KV entry (kv_bits 0 / unset) -> reported as 0
    assert P.registry_kv("bar-8bit", str(yml))["kv_bits"] == 0
    assert P.registry_kv("missing", str(yml)) is None


def test_current_manifest_lite_reflects_sampling_overrides(tmp_path):
    # OFAT sweeps pass --temperature (etc.) as overrides ON TOP of the profile. Those overrides
    # MUST flow into the manifest fingerprint, or clean-stale would silently resume results
    # produced at a DIFFERENT temperature -- the same contamination class as the budget bug.
    reg = tmp_path / "reg.yaml"
    reg.write_text("models:\n  - name: gemma-4-26B-A4B-it-OptiQ-4bit\n    hf_path: org/g\n    kv_bits: 0\n")
    base = P.current_manifest_lite("gemma-4-26B-A4B-it-OptiQ-4bit", "coding", str(reg))
    over = P.current_manifest_lite("gemma-4-26B-A4B-it-OptiQ-4bit", "coding", str(reg),
                                   overrides={"temperature": 0.5})
    assert base["sampling"]["temperature"] == 0.7          # coding keeps production temp
    assert over["sampling"]["temperature"] == 0.5          # override applied
    assert P.is_compatible(base, over) is False            # temp change -> clean-stale regenerates


def test_build_manifest_assembles_full_config():
    m = P.build_manifest(
        model="qwen-8bit",
        box="M5",
        ts=1719100000,
        git_shas={"stack_head": "f35b5e1", "submodules": {"src/mlx-vlm": "ea4c635"}},
        kv={"kv_bits": 0, "kv_quant_scheme": None},
        quant={"effective_bits": 8.0, "footprint_gb": 34.7, "mixed": False},
        sampling={"temperature": 0.6, "min_p": 0.0, "thinking_budget": 49152},
    )
    assert m["model"] == "qwen-8bit"
    assert m["box"] == "M5"
    assert m["timestamp"] == 1719100000
    assert m["git"]["submodules"]["src/mlx-vlm"] == "ea4c635"
    assert m["kv"]["kv_bits"] == 0
    assert m["quant"]["effective_bits"] == 8.0
    assert m["sampling"]["temperature"] == 0.6


# ----------------------------------------------------- v4 (2026-08-17, V3 guard parity)
def test_v4_fingerprints_the_kv_extra_slice_and_v3_rows_still_compare_on_v3():
    """v4 adds hf_path / kv_quant_scheme / quantized_kv_start / prefill_step_size to the resume
    guard. Non-destructive by the min-version rule: a v3 manifest paired with a v4 one compares
    on the v3 slice, so no historical row reads stale. Two v4 manifests differing only in a new
    key ARE stale — that is the point."""
    def man(v, scheme):
        return {"sampling_profile": "deployed", "fingerprint_version": v,
                "sampling": {"temperature": 0.4},
                "kv": {"kv_bits": 4, "kv_quant_scheme": scheme, "hf_path": "org/m"},
                "runtime": {}}
    fp4 = P.config_fingerprint(man(4, "turboquant"))
    assert fp4["kv_extra"]["kv_quant_scheme"] == "turboquant"
    assert fp4["kv_extra"]["hf_path"] == "org/m"
    assert "kv_extra" not in P.config_fingerprint(man(3, "turboquant"))
    assert P.is_compatible(man(3, "uniform"), man(4, "turboquant")) is True   # min-version: v3 slice
    assert P.is_compatible(man(4, "uniform"), man(4, "turboquant")) is False  # both v4: guarded


def test_registry_kv_records_kv_prealloc_tokens_but_the_resume_fingerprint_ignores_it(tmp_path):
    """Prealloc moved wall-clock (24.7 vs 27.8 s OFAT) but is text-invariant, so it must be
    RECORDED (compare refuses hardware metrics across it) without joining the resume fingerprint
    (a prealloc change must not let --clean-stale delete quality rows)."""
    yml = tmp_path / "reg.yaml"
    yml.write_text("models:\n  - name: m-4bit\n    hf_path: org/m\n    kv_bits: 4\n"
                   "    kv_prealloc_tokens: 131072\n")
    assert P.registry_kv("m-4bit", str(yml))["kv_prealloc_tokens"] == 131072
    a = {"fingerprint_version": 4, "sampling": {}, "runtime": {},
         "kv": {"kv_bits": 4, "kv_prealloc_tokens": 131072}}
    b = {"fingerprint_version": 4, "sampling": {}, "runtime": {},
         "kv": {"kv_bits": 4, "kv_prealloc_tokens": 262144}}
    assert P.is_compatible(a, b) is True


def test_gather_records_the_registry_hash_and_dirt_state(tmp_path):
    """Operator ruling 5 (2026-08-17): the worker's registry is permanently dirty (caps), and a
    manifest that cannot say WHICH registry bytes produced it has the same provenance gap the
    dirty-registry scp era had. Record-only — never fingerprinted (the caps/sampling it could
    change are fingerprinted directly)."""
    yml = tmp_path / "reg.yaml"
    yml.write_text("models:\n  - name: m-4bit\n    hf_path: org/m\n    kv_bits: 0\n")
    man = P.gather("m-4bit", str(yml), profile="deployed")
    reg = man["registry"]
    import hashlib
    assert reg["sha256"] == hashlib.sha256(yml.read_bytes()).hexdigest()
    # a non-repo path cannot be git-checked: dirty must be "unknown", not a guess
    assert reg["dirty"] == "unknown"


def test_box_falls_back_to_config_sh_when_env_is_absent(tmp_path, monkeypatch):
    """The box guard was ANTI-CORRELATED for the whole campaign (50/54 manifests said "local")
    because MLX_BOX only exists in shells that sourced config.sh. The fallback reads the config
    file directly so a bare `nohup python run.py` still stamps the right box."""
    cfg_dir = tmp_path / "mlx_local_stack"
    cfg_dir.mkdir()
    (cfg_dir / "config.sh").write_text('# machine-local\nexport MLX_BOX="m5max"\n')
    monkeypatch.delenv("MLX_BOX", raising=False)
    monkeypatch.delenv("HOSTNAME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert P._box() == "m5max"
    monkeypatch.setenv("MLX_BOX", "explicit-wins")
    assert P._box() == "explicit-wins"


# --- O34 (ruled 2026-08-20): manifests must carry $HOME-form hf_path, never the absolute home ---

def test_registry_kv_normalizes_home_prefixed_hf_path_to_HOME_form(tmp_path, monkeypatch):
    import os
    home = os.path.expanduser("~")
    yml = tmp_path / "reg.yaml"
    yml.write_text(
        "models:\n"
        "  - name: local-4bit\n"
        f"    hf_path: {home}/ws/models/local-4bit\n"
        "    kv_bits: 4\n"
        "  - name: hub-4bit\n"
        "    hf_path: org/hub-4bit\n"
        "    kv_bits: 4\n"
    )
    assert P.registry_kv("local-4bit", str(yml))["hf_path"] == "$HOME/ws/models/local-4bit"
    # hub ids and non-home paths pass through untouched
    assert P.registry_kv("hub-4bit", str(yml))["hf_path"] == "org/hub-4bit"


def test_home_normalization_matches_the_hand_sanitized_committed_form(tmp_path):
    # The committed corpus manifests were hand-sanitized to $HOME-form; the writer must
    # produce the SAME string so a resume no longer sees a false config change (2026-08-20:
    # a byte-identical relaunch was flagged STALE purely on $HOME vs absolute form).
    import os
    home = os.path.expanduser("~")
    assert P._home_normalized(home + "/x") == "$HOME/x"
    assert P._home_normalized(home) == "$HOME"
    assert P._home_normalized("/opt/models/x") == "/opt/models/x"
    assert P._home_normalized(None) is None


# --- P8 (2026-09-02): $HOME-form hf_path must still resolve to the real dir for quant_info ---
#
# registry_kv() emits hf_path in $HOME-form (O34, correct for the WRITTEN manifest); gather()
# then fed that literal string to _resolve_snapshot, whose os.path.isdir("$HOME/...") is False,
# so every LOCAL-PATH model since 2026-08-20 was stamped `quant: {}` while hub ids were fine.

import json as _json
import os as _os
import shutil as _shutil
import struct as _struct
import uuid as _uuid

import pytest as _pytest


def _write_min_safetensors(path):
    """A valid header-only safetensors with one quantized module (scales -> params counted)."""
    header = {
        "layers.0.scales": {"dtype": "F16", "shape": [8, 1], "data_offsets": [0, 16]},
        "layers.0.biases": {"dtype": "F16", "shape": [8, 1], "data_offsets": [16, 32]},
        "layers.0.weight": {"dtype": "U32", "shape": [8, 8], "data_offsets": [32, 288]},
    }
    hj = _json.dumps(header).encode()
    with open(path, "wb") as f:
        f.write(_struct.pack("<Q", len(hj)))
        f.write(hj)
        f.write(b"\x00" * 288)


@_pytest.fixture
def home_snapshot_dir():
    """A minimal MLX snapshot placed UNDER $HOME (pytest's tmp_path is under /private/var, which
    _home_normalized leaves alone). ~/.cache is the pre-approved out-of-repo exception."""
    base = _os.path.expanduser("~/.cache/mlx_local_stack_test_tmp")
    d = _os.path.join(base, "snap-" + _uuid.uuid4().hex[:8])
    _os.makedirs(d)
    with open(_os.path.join(d, "config.json"), "w") as f:
        _json.dump({"model_type": "test", "quantization": {"group_size": 64, "bits": 4}}, f)
    _write_min_safetensors(_os.path.join(d, "model.safetensors"))
    try:
        yield d
    finally:
        _shutil.rmtree(base, ignore_errors=True)


def test_resolve_snapshot_expands_home_form(home_snapshot_dir):
    home_form = P._home_normalized(home_snapshot_dir)
    assert home_form.startswith("$HOME/")          # precondition: it IS the O34 form
    assert P._resolve_snapshot(home_form) == home_snapshot_dir
    # absolute and ~-form still resolve; a bogus hub id still falls through to None
    assert P._resolve_snapshot(home_snapshot_dir) == home_snapshot_dir
    assert P._resolve_snapshot("~" + home_snapshot_dir[len(_os.path.expanduser("~")):]) \
        == home_snapshot_dir
    assert P._resolve_snapshot("org/definitely-not-cached-" + _uuid.uuid4().hex) is None


def test_gather_stamps_quant_for_a_local_home_path_model(tmp_path, home_snapshot_dir):
    yml = tmp_path / "reg.yaml"
    yml.write_text(
        "models:\n"
        "  - name: local-4bit\n"
        f"    hf_path: {home_snapshot_dir}\n"
        "    kv_bits: 0\n"
    )
    man = P.gather("local-4bit", str(yml), profile="deployed")
    # the WRITTEN form stays $HOME-form (O34) ...
    assert man["kv"]["hf_path"] == P._home_normalized(home_snapshot_dir)
    # ... but quant is computed from the real dir, not left as {}
    assert man["quant"]["nominal_bits"] == 4
    assert man["quant"]["effective_bits"] == 4.0
    assert man["quant"]["mixed"] is False
