import json
from configgen.emitters.owui import emit_owui


def test_explicit_thinking_settings(sample_source):
    from dataclasses import replace

    m = sample_source.models[0]
    source = replace(
        sample_source,
        models=[replace(m, sampling={**m.sampling, "reasoning_effort": "medium"})],
    )
    params = json.loads(emit_owui(source))[0]["params"]
    assert params["enable_thinking"] is True
    assert params["reasoning_effort"] == "medium"


def test_deployment_excludes_candidates_and_orders_default_first(sample_source):
    from dataclasses import replace
    from configgen.emitters.owui import emit_owui_settings

    candidate = replace(sample_source.models[0], name="Bench-only", role="candidate")
    source = replace(
        sample_source,
        models=[*sample_source.models, candidate],
        router_only_models=("Router-only",),
        agent_defaults={"openwebui": "Gemma-B"},
    )
    config = json.loads(emit_owui_settings(source))
    assert config["main_model_ids"] == ["Qwen-A", "Gemma-B"]
    assert config["excluded_model_ids"] == ["Bench-only", "Router-only"]
    assert config["task_model_id"] == "mlx-community/Task-C"
    assert config["defaults"]["DEFAULT_MODELS"] == "Gemma-B"
    assert config["defaults"]["MODEL_ORDER_LIST"] == [
        "Gemma-B",
        "Qwen-A",
        "mlx-community/Task-C",
    ]


def test_nemotron_family_params(nemotron_source_tainted):
    # C64/F2-F3/F5: NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit, role=main, family=nemotron.  # allow-shorthand
    # Taint-based: nemotron_source_tainted injects top_k/repetition_penalty into sampling, which
    # pre-F2/F3 leaked straight through (owui._params filtered m.sampling directly instead of
    # routing through the family whitelist in sampling_openai/sampling_extra).
    arr = json.loads(emit_owui(nemotron_source_tainted))
    by = {m["id"]: m for m in arr}
    m = by["NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"]
    assert m["params"]["function_calling"] == "native"
    assert m["params"]["presence_penalty"] == 0.0
    assert m["params"]["thinking_budget"] == 81920
    assert "repeat_penalty" not in m["params"]
    assert "top_k" not in m["params"] and "min_p" not in m["params"]


def test_owui_params_and_meta(sample_source):
    arr = json.loads(emit_owui(sample_source))
    by = {m["id"]: m for m in arr}
    assert by["Gemma-B"]["params"]["repeat_penalty"] == 1.08  # Ollama alias
    assert "repetition_penalty" not in by["Gemma-B"]["params"]
    assert by["Qwen-A"]["params"]["presence_penalty"] == 0.0
    assert by["Qwen-A"]["meta"]["capabilities"]["web_search"] is True
    assert "web_search" in by["Qwen-A"]["meta"]["defaultFeatureIds"]
    assert "mlx-community/Task-C" in by  # task model included in OWUI


def test_owui_required_keys_and_shape(sample_source):
    arr = json.loads(emit_owui(sample_source))
    by = {m["id"]: m for m in arr}
    # init.py's apply_model_configs reads model["id"] plus model.get() on
    # name/params/meta/access_grants -- all must be present on every entry.
    for entry in arr:
        assert {"id", "name", "params", "meta", "access_grants"} <= set(entry)
        assert isinstance(
            entry["access_grants"], list
        )  # OWUI ModelForm requires a list

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
