import json
from pathlib import Path
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


def test_explicit_menu_is_ordered_and_does_not_change_other_clients(sample_source):
    from dataclasses import replace
    from configgen.emitters.owui import emit_owui_settings
    from configgen.emitters.opencode import emit_opencode

    source = replace(sample_source, openwebui_models=("Qwen-A",))
    assert [m["id"] for m in json.loads(emit_owui(source))] == [
        "Qwen-A",
        "mlx-community/Task-C",
    ]
    policy = json.loads(emit_owui_settings(source))
    assert policy["main_model_ids"] == ["Qwen-A"]
    assert "Gemma-B" in policy["excluded_model_ids"]
    assert emit_opencode(source) == emit_opencode(sample_source)


def test_explicit_menu_rejects_invalid_membership(sample_source):
    import pytest
    from dataclasses import replace
    from configgen.emitters.owui import emit_owui_settings

    for menu in [(), ("Missing",), ("Qwen-A", "Qwen-A"), ("mlx-community/Task-C",)]:
        with pytest.raises(ValueError):
            emit_owui_settings(replace(sample_source, openwebui_models=menu))


def test_task_is_hidden_from_selector_but_remains_active(sample_source):
    rows = json.loads(emit_owui(sample_source))
    task = next(m for m in rows if m["id"] == "mlx-community/Task-C")
    assert task["meta"]["hidden"] is True
    assert task["is_active"] is True
    assert all(m["meta"]["hidden"] is False for m in rows if m is not task)


def test_retired_model_ids_are_folded_into_excluded_model_ids(sample_source):
    from dataclasses import replace
    from configgen.emitters.owui import emit_owui_settings

    source = replace(sample_source, retired_model_ids=("Gone-1", "Gone-2"))
    policy = json.loads(emit_owui_settings(source))
    assert {"Gone-1", "Gone-2"} <= set(policy["excluded_model_ids"])
    assert len(policy["excluded_model_ids"]) == len(set(policy["excluded_model_ids"]))
    assert "Gone-1" not in policy["main_model_ids"]


def test_excluded_model_ids_are_the_surviving_non_menu_ids_then_the_retired_ids_in_registry_order(sample_source):
    # spec v3.1 AC2: a deterministic order (consumed as a set); retired ids keep their `retired_model_ids` order, not sorted
    from dataclasses import replace
    from configgen.emitters.owui import emit_owui_settings

    base = replace(sample_source, openwebui_models=("Qwen-A",))
    surviving = json.loads(emit_owui_settings(replace(base, retired_model_ids=())))["excluded_model_ids"]
    assert surviving == ["Gemma-B"]
    retired = ("Zed-gone", "Alpha-gone", "Mid-gone")
    policy = json.loads(emit_owui_settings(replace(base, retired_model_ids=retired)))
    assert policy["excluded_model_ids"] == surviving + list(retired)


def test_shipped_policy_excluded_model_ids_follow_the_registry_order():
    from configgen.emitters.owui import emit_owui_settings
    from configgen.source import load_source

    source = load_source(str(Path(__file__).resolve().parents[2] / "main_models.yaml"))
    menu = set(source.openwebui_models)
    surviving = [m.name for m in source.models if m.role != "task" and m.name not in menu]
    surviving += [n for n in source.router_only_models if n not in surviving]
    got = json.loads(emit_owui_settings(source))["excluded_model_ids"]
    assert got == surviving + list(source.retired_model_ids)
    assert len(source.retired_model_ids) == 6 and got[-6:] == list(source.retired_model_ids)


def test_retired_model_ids_are_not_emitted_as_models_and_not_duplicated(sample_source):
    from dataclasses import replace
    from configgen.emitters.owui import emit_owui_settings

    source = replace(sample_source, retired_model_ids=("Gemma-B", "Gone-1"),
                     openwebui_models=("Qwen-A",))
    policy = json.loads(emit_owui_settings(source))
    assert policy["excluded_model_ids"].count("Gemma-B") == 1  # already excluded by the menu
    assert "Gone-1" in policy["excluded_model_ids"]
    assert "Gone-1" not in [m["id"] for m in json.loads(emit_owui(source))]


def test_load_source_reads_shipped_retired_model_ids():
    from configgen.source import load_source

    source = load_source(str(Path(__file__).resolve().parents[2] / "main_models.yaml"))
    assert len(source.retired_model_ids) == 6
    assert not set(source.retired_model_ids) & {m.name for m in source.models}


def test_load_source_rejects_malformed_retired_model_ids(tmp_path):
    import pytest
    from configgen.source import load_source

    p = tmp_path / "m.yaml"
    p.write_text("models: []\nopenwebui:\n  retired_model_ids: nope\n")
    with pytest.raises(ValueError, match="retired_model_ids"):
        load_source(str(p))


def test_all_shipped_chat_models_default_to_search_and_code_interpreter():
    from pathlib import Path
    from configgen.source import load_source

    source = load_source(str(Path(__file__).resolve().parents[2] / "main_models.yaml"))
    for model in json.loads(emit_owui(source)):
        if model["meta"]["hidden"]:
            continue
        assert model["meta"]["defaultFeatureIds"] == [
            "web_search",
            "code_interpreter",
        ], model["id"]
        assert model["meta"]["capabilities"]["web_search"] is True
        assert model["meta"]["capabilities"]["code_interpreter"] is True
        assert model["meta"]["builtinTools"]["web_search"] is True
        assert model["meta"]["builtinTools"]["code_interpreter"] is True
