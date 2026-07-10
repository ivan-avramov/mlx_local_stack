import pytest
from configgen.source import load_source

def _write(tmp_path, body):
    p = tmp_path / "main_models.yaml"; p.write_text(body); return str(p)

VALID = """
agent_defaults:
  opencode: Qwen-A
models:
  - name: Qwen-A
    hf_path: ns/Qwen-A
    max_kv_cache_size: 262144
    generation_defaults: {temperature: 0.4, max_tokens: 102400, enable_thinking: true}
    presentation:
      role: main
      family: qwen
      display_name: "Qwen A"
      context: 262144
      output: 102400
      capabilities: [tools, web_search]
"""

def test_loads_model_and_defaults(tmp_path):
    s = load_source(_write(tmp_path, VALID))
    m = s.models[0]
    assert m.name == "Qwen-A" and m.family == "qwen" and m.edit_format == "diff"
    assert m.context == 262144 and m.output == 102400
    assert m.sampling["temperature"] == 0.4
    assert s.agent_defaults["opencode"] == "Qwen-A"

def test_task_role_gets_port_8092(tmp_path):
    body = VALID.replace("role: main", "role: task").replace("      family: qwen\n", "")
    s = load_source(_write(tmp_path, body))
    assert s.models[0].role == "task" and s.models[0].port == 8092

def test_missing_presentation_field_raises(tmp_path):
    body = VALID.replace('      display_name: "Qwen A"\n', "")
    with pytest.raises(ValueError, match="display_name"):
        load_source(_write(tmp_path, body))

def test_agent_default_unknown_model_raises(tmp_path):
    body = VALID.replace("opencode: Qwen-A", "opencode: Nope")
    with pytest.raises(ValueError, match="Nope"):
        load_source(_write(tmp_path, body))

def test_unknown_family_raises(tmp_path):
    body = VALID.replace("family: qwen", "family: llama")
    with pytest.raises(ValueError, match="family"):
        load_source(_write(tmp_path, body))

def test_models_without_presentation_are_skipped(tmp_path):
    # a router-only entry with no presentation block is ignored by the generator
    body = VALID + "  - name: Router-Only\n    hf_path: ns/x\n    kv_bits: 4\n"
    s = load_source(_write(tmp_path, body))
    assert [m.name for m in s.models] == ["Qwen-A"]

def test_duplicate_name_raises(tmp_path):
    body = VALID + "  - name: Qwen-A\n    hf_path: ns/other\n    presentation:\n      role: task\n      display_name: \"Qwen A2\"\n      context: 262144\n      output: 102400\n"
    with pytest.raises(ValueError, match="duplicate"):
        load_source(_write(tmp_path, body))

def test_unknown_role_raises(tmp_path):
    body = VALID.replace("role: main", "role: bogus")
    with pytest.raises(ValueError, match="role"):
        load_source(_write(tmp_path, body))

def test_loads_task_model_block(tmp_path):
    # The task model (mlx_vlm on :8092) must NOT live under `models:` (that would make
    # the :8000 router serve it / OWUI auto-list it). It lives in a top-level
    # `task_model:` block, parsed with the same per-entry logic as `models:` entries.
    body = VALID + """
task_model:
  name: mlx-community/Task-Model
  hf_path: mlx-community/Task-Model
  presentation:
    role: task
    display_name: "Task Model"
    context: 30000
    output: 2048
"""
    s = load_source(_write(tmp_path, body))
    task_specs = [m for m in s.models if m.role == "task"]
    assert len(task_specs) == 1
    assert task_specs[0].name == "mlx-community/Task-Model"
    assert task_specs[0].port == 8092
    # still one main model from the `models:` block
    assert len(s.models) == 2
