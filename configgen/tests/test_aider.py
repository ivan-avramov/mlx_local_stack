import json, yaml
from configgen.emitters.aider import emit_aider

def test_aider_three_files(sample_source):
    out = emit_aider(sample_source)

    # Verify all three keys exist
    assert set(out.keys()) == {"settings", "metadata", "conf"}

    # Parse and verify settings (YAML list of dicts)
    settings = yaml.safe_load(out["settings"])
    assert isinstance(settings, list)
    names = {e["name"] for e in settings}
    assert "openai/Qwen-A" in names and "openai/Gemma-B" in names and "openai/mlx-community/Task-C" in names

    # Verify Qwen-A entry (main model)
    qwen = next(e for e in settings if e["name"] == "openai/Qwen-A")
    assert qwen["edit_format"] == "diff"  # from ModelSpec
    assert qwen["use_repo_map"] is True
    assert qwen["streaming"] is True
    assert qwen["extra_params"]["max_tokens"] == 102400
    assert qwen["extra_params"]["timeout"] == 5400
    assert qwen["extra_params"]["temperature"] == 0.4
    assert qwen["extra_params"]["top_p"] == 0.95
    assert "extra_body" in qwen["extra_params"]
    # Family-correct sampling: qwen should have presence_penalty, NOT repetition_penalty
    assert qwen["extra_params"]["extra_body"]["presence_penalty"] == 0.0
    assert "repetition_penalty" not in qwen["extra_params"]["extra_body"]
    assert qwen["weak_model_name"] == "openai/mlx-community/Task-C"

    # Verify Gemma-B entry (main model)
    gemma = next(e for e in settings if e["name"] == "openai/Gemma-B")
    assert gemma["edit_format"] == "whole"  # from ModelSpec
    assert gemma["extra_params"]["max_tokens"] == 32768
    # Family-correct sampling: gemma should have repetition_penalty, NOT presence_penalty
    assert gemma["extra_params"]["extra_body"]["repetition_penalty"] == 1.08
    assert "presence_penalty" not in gemma["extra_params"]["extra_body"]
    assert gemma["weak_model_name"] == "openai/mlx-community/Task-C"

    # Verify Task-C entry (task model)
    task = next(e for e in settings if e["name"] == "openai/mlx-community/Task-C")
    assert task["edit_format"] == "whole"
    assert task["use_repo_map"] is False
    assert task["streaming"] is True
    assert task["extra_params"]["api_base"] == "http://localhost:8092/v1"
    assert task["extra_params"]["api_key"] == "not-needed"
    assert "weak_model_name" not in task  # task model has no weak model

    # Verify conf (YAML dict)
    conf = yaml.safe_load(out["conf"])
    assert conf["model"] == "openai/Qwen-A"  # from agent_defaults
    assert conf["openai-api-base"] == "http://localhost:8000/v1"
    assert conf["openai-api-key"] == "not-needed"

    # Verify metadata (JSON dict)
    meta = json.loads(out["metadata"])
    assert set(meta.keys()) == {"openai/Qwen-A", "openai/Gemma-B"}  # task model NOT in metadata
    # max_input_tokens = context - output (NOT just context)
    assert meta["openai/Qwen-A"]["max_input_tokens"] == 262144 - 102400
    assert meta["openai/Qwen-A"]["max_output_tokens"] == 102400
    assert meta["openai/Gemma-B"]["max_input_tokens"] == 196608 - 32768
    assert meta["openai/Gemma-B"]["max_output_tokens"] == 32768

    # Vision/PDF flags + litellm bookkeeping (aider/litellm gate image attachment on
    # supports_vision — Qwen-A's fixture capabilities include "vision")
    assert meta["openai/Qwen-A"]["supports_vision"] is True
    assert meta["openai/Qwen-A"]["supports_pdf_input"] is True
    assert meta["openai/Qwen-A"]["litellm_provider"] == "openai"
    assert meta["openai/Qwen-A"]["mode"] == "chat"
