from dataclasses import replace

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

@pytest.fixture
def nemotron_source():
    """C64: NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit promoted to role=main, family=nemotron.  # allow-shorthand

    Sampling mirrors the real registry entry's generation_defaults verbatim (vendor-sparse: no
    top_k/min_p/repetition_penalty — see benchmark/bench/model_params.py NEMOTRON comment).  # allow-shorthand
    """
    return Source(
        models=[
            ModelSpec(name="NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit",
                      hf_path="mlx-community/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit",
                      role="main", family="nemotron",  # allow-shorthand
                      display_name="NVIDIA Nemotron 3.5 Lightning 30B-A3B",  # allow-shorthand
                      context=262144, output=102400,
                      capabilities=["tools", "thinking"],
                      sampling={"temperature": 0.5, "top_p": 0.95, "presence_penalty": 0.0,
                                "max_tokens": 102400, "thinking_budget": 81920,
                                "enable_thinking": True},
                      edit_format="diff", port=None),
        ],
        agent_defaults={},
    )

@pytest.fixture
def nemotron_source_tainted(nemotron_source):
    """C64/F5: same model, PLUS two stray keys the vendor card never recommends (`top_k`,
    `repetition_penalty`), as if a future generation_defaults edit copy-pasted them from a
    qwen/gemma entry. Gives the per-emitter tests TEETH: pre-F2/F3, `top_k` leaked straight  # allow-shorthand
    into openwebui-init/models_config.json because owui._params filtered `m.sampling` directly
    instead of routing through the family whitelist; pre-nemotron-branch, both stray keys would
    pass through configgen/transforms.py's family-less whitelist-free fallback unchanged.  # allow-shorthand
    """
    m = nemotron_source.models[0]
    tainted = replace(m, sampling={**m.sampling, "top_k": 20, "repetition_penalty": 1.05})
    return Source(models=[tainted], agent_defaults={})
