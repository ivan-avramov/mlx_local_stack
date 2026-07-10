import pytest
from configgen.source import Source, ModelSpec

@pytest.fixture
def sample_source():
    return Source(
        models=[
            ModelSpec(name="Qwen-A", hf_path="ns/Qwen-A", role="main", family="qwen",
                      display_name="Qwen A", context=262144, output=102400,
                      capabilities=["tools","vision","web_search"],
                      sampling={"temperature":0.4,"top_p":0.95,"top_k":20,"min_p":0.0,
                                "presence_penalty":0.0,"max_tokens":102400,
                                "thinking_budget":81920,"enable_thinking":True},
                      edit_format="diff", port=None),
            ModelSpec(name="Gemma-B", hf_path="ns/Gemma-B", role="main", family="gemma",
                      display_name="Gemma B", context=196608, output=32768,
                      capabilities=["tools","vision","web_search"],
                      sampling={"temperature":0.7,"top_p":0.95,"top_k":64,"min_p":0.0,
                                "repetition_penalty":1.08,"max_tokens":32768,
                                "thinking_budget":16384,"enable_thinking":True},
                      edit_format="whole", port=None),
            ModelSpec(name="mlx-community/Task-C", hf_path="mlx-community/Task-C", role="task",
                      family=None, display_name="Task C", context=30000, output=2048,
                      capabilities=[], sampling={}, edit_format="whole", port=8092),
        ],
        agent_defaults={"opencode":"Qwen-A","aider":"Qwen-A"},
    )
