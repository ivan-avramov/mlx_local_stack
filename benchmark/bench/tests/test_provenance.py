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
