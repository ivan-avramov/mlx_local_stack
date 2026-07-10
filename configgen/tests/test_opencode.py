import json
from configgen.emitters.opencode import emit_opencode

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
    assert ml["Qwen-A"]["limit"]["context"] == 262144 - 102400
