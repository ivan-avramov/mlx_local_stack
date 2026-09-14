import json
import pytest
from configgen.emitters.opencode import emit_opencode, emit_opencode_bench

def test_opencode_structure(sample_source):
    d = json.loads(emit_opencode(sample_source))
    ml = d["provider"]["mlx-local"]["models"]
    assert set(ml) == {"Qwen-A", "Gemma-B"}                 # task model NOT here
    assert d["provider"]["mlx-task"]["models"]["mlx-community/Task-C"]
    assert d["model"] == "mlx-local/Qwen-A"                 # from agent_defaults
    assert d["small_model"].endswith("Task-C")
    assert ml["Qwen-A"]["options"]["temperature"] == 0.4
    assert ml["Qwen-A"]["options"]["presence_penalty"] == 0.0   # qwen extra
    assert ml["Gemma-B"]["options"]["repetition_penalty"] == 1.08  # gemma extra
    assert ml["Qwen-A"]["limit"]["context"] == 262144
    assert ml["Qwen-A"]["limit"]["input"] == 262144 - 102400


def test_nemotron_family_renders_as_main_with_vendor_sparse_extras(nemotron_source_tainted):
    # C64/F5: NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit, role=main, family=nemotron. Taint-based:  # allow-shorthand
    # the fixture injects top_k/repetition_penalty, so the absence asserts below have teeth.
    d = json.loads(emit_opencode(nemotron_source_tainted))
    ml = d["provider"]["mlx-local"]["models"]
    m = ml["NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"]
    assert m["options"]["temperature"] == 0.5
    assert m["options"]["presence_penalty"] == 0.0
    assert m["options"]["thinking_budget"] == 81920
    assert m["options"]["enable_thinking"] is True
    assert "top_k" not in m["options"] and "min_p" not in m["options"]
    assert "repetition_penalty" not in m["options"]


def test_no_unrecognized_top_level_keys(sample_source):
    """opencode validates its config STRICTLY and rejects the whole file on an unknown top-level key.

    Measured 2026-08-13 on opencode 1.18.15: the emitter's cosmetic `_generated` provenance marker
    produced `Error: Configuration is invalid ... Unrecognized key: _generated`, so the config never
    loaded, ZERO requests reached :8000, and every P1a gate failed rc=1. It read like the known
    upstream bug opencode#5674 ("custom endpoints unusable") and would have cancelled the campaign's
    declared primary harness over a defect in our own emitter.

    Only keys opencode's schema accepts may appear at the top level. `$schema` is allowed; a bare
    `_`-prefixed comment key is NOT — JSON has no comments, and opencode offers no sanctioned slot
    for one, so the provenance note lives in opencode_config/README.md instead.
    """
    d = json.loads(emit_opencode(sample_source))
    allowed = {"$schema", "provider", "model", "small_model", "plugin"}
    assert set(d) <= allowed, f"unrecognized top-level key(s): {sorted(set(d) - allowed)}"
    assert "_generated" not in d


def test_generated_marker_is_absent_from_every_nesting_level(sample_source):
    """The key breaks the parse wherever opencode's schema is strict, so don't just move it inward."""
    def walk(node, path="$"):
        if isinstance(node, dict):
            assert "_generated" not in node, f"_generated found at {path}"
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(json.loads(emit_opencode(sample_source)))


@pytest.mark.parametrize("emit", [emit_opencode, emit_opencode_bench])
def test_text_only_model_does_not_advertise_attachments(emit, nemotron_source, sample_source):
    text_only = json.loads(emit(nemotron_source))["provider"]["mlx-local"]["models"]
    assert text_only["NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"]["attachment"] is False
    vision = json.loads(emit(sample_source))["provider"]["mlx-local"]["models"]
    assert vision["Qwen-A"]["attachment"] is True
    assert vision["Gemma-B"]["attachment"] is True


@pytest.mark.parametrize("emit", [emit_opencode, emit_opencode_bench])
def test_resolved_provider_preserves_vision_input(emit, sample_source, nemotron_source):
    # OpenCode v1.18.30 provider/provider.ts resolves custom models' image
    # capability from modalities.input independently of attachment. Without
    # a catalogue entry, omitted image capability defaults to false and
    # provider/transform.ts replaces image parts with unsupported-input text.
    def accepts_image(model):
        return "image" in model.get("modalities", {}).get("input", [])

    doc = json.loads(emit(sample_source))
    for model in doc["provider"]["mlx-local"]["models"].values():
        assert accepts_image(model), "vision input would be replaced before delivery"
        assert model["modalities"]["output"] == ["text"]
        assert "text" in model["modalities"]["input"]
    task = doc["provider"]["mlx-task"]["models"]["mlx-community/Task-C"]
    assert task["modalities"] == {"input": ["text"], "output": ["text"]}
    text_only = json.loads(emit(nemotron_source))["provider"]["mlx-local"]["models"]
    for model in text_only.values():
        assert not accepts_image(model)
        assert model["modalities"] == {"input": ["text"], "output": ["text"]}


@pytest.mark.parametrize("emit", [emit_opencode, emit_opencode_bench])
@pytest.mark.parametrize("effective_output_limit", [32768, 102400])
def test_context_budget_reserves_output_once(emit, effective_output_limit, sample_source):
    # Installed OpenCode v1.18.30 session/overflow.ts: an explicit input limit
    # reserves the smaller of 20K and output; otherwise it subtracts output
    # from context. Supplying window-output as context reserves output twice.
    doc = json.loads(emit(sample_source))
    limit = doc["provider"]["mlx-local"]["models"]["Qwen-A"]["limit"]
    reserved = min(20000, effective_output_limit)
    usable = (limit["input"] - reserved if limit.get("input")
              else limit["context"] - effective_output_limit)
    prompt_budget = 262144 - 102400
    assert usable == prompt_budget - reserved
    assert limit["context"] == 262144
    assert limit["output"] == 102400
    task = doc["provider"]["mlx-task"]["models"]["mlx-community/Task-C"]["limit"]
    assert task["context"] == 30000
    assert task["input"] + task["output"] == task["context"]
