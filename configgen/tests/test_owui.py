import json
from configgen.emitters.owui import emit_owui

def test_owui_params_and_meta(sample_source):
    arr = json.loads(emit_owui(sample_source))
    by = {m["id"]: m for m in arr}
    assert by["Gemma-B"]["params"]["repeat_penalty"] == 1.08      # Ollama alias
    assert "repetition_penalty" not in by["Gemma-B"]["params"]
    assert by["Qwen-A"]["params"]["presence_penalty"] == 0.0
    assert by["Qwen-A"]["meta"]["capabilities"]["web_search"] is True
    assert "web_search" in by["Qwen-A"]["meta"]["defaultFeatureIds"]
    assert "mlx-community/Task-C" in by                            # task model included in OWUI

def test_owui_required_keys_and_shape(sample_source):
    arr = json.loads(emit_owui(sample_source))
    by = {m["id"]: m for m in arr}
    # init.py's apply_model_configs reads model["id"] plus model.get() on
    # name/params/meta/access_grants -- all must be present on every entry.
    for entry in arr:
        assert {"id", "name", "params", "meta", "access_grants"} <= set(entry)
        assert isinstance(entry["access_grants"], list)   # OWUI ModelForm requires a list

    # function_calling: native carried for all models (opencode/aider parity)
    assert by["Qwen-A"]["params"]["function_calling"] == "native"
    assert by["Gemma-B"]["params"]["function_calling"] == "native"

    # gemma sampling has no presence_penalty; qwen params have no repeat_penalty
    assert "presence_penalty" not in by["Gemma-B"]["params"]
    assert "repeat_penalty" not in by["Qwen-A"]["params"]

    # task model's meta mirrors its empty capability list (no web_search default,
    # matches the committed models_config.json's lightweight task-model entry)
    task = by["mlx-community/Task-C"]
    assert task["meta"]["defaultFeatureIds"] == []
    assert "web_search" not in task["meta"]["capabilities"]
