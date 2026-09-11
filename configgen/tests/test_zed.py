import json, re
from dataclasses import replace

from configgen.emitters.zed import emit_zed
from configgen.source import Source

def _zed_names(source):
    text = emit_zed(source)
    body = re.sub(r'^\s*//.*$', '', text, flags=re.M)
    d = json.loads(body)
    ms = d["language_models"]["openai_compatible"]["mlx-local"]["available_models"]
    return {m["name"] for m in ms}

def test_zed_full_window_no_sampling(sample_source):
    text = emit_zed(sample_source)
    body = re.sub(r'^\s*//.*$', '', text, flags=re.M)   # strip // comments
    d = json.loads(body)
    ms = d["language_models"]["openai_compatible"]["mlx-local"]["available_models"]
    # Task model excluded
    names = {m["name"] for m in ms}
    assert names == {"Qwen-A", "Gemma-B"}                # task excluded
    q = next(m for m in ms if m["name"] == "Qwen-A")
    assert q["max_tokens"] == 262144                     # FULL window, not minus output
    assert q["max_output_tokens"] == 102400
    assert "temperature" not in q
    # Verify no sampling keys present
    sampling_keys = {"temperature", "top_p", "top_k", "min_p", "presence_penalty", "enable_thinking", "thinking_budget"}
    for m in ms:
        assert not any(k in m for k in sampling_keys), f"Found sampling key in {m['name']}"


def test_nemotron_family_included_as_main_but_not_as_candidate(nemotron_source):
    # C64/F5: NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit. zed is registration-only (no sampling
    # carrier), so family itself has nothing to assert on here -- the only thing with teeth is the
    # role filter this promotion depends on, so this checks BOTH sides of it.
    name = "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"
    assert name in _zed_names(nemotron_source)

    cand = replace(nemotron_source.models[0], role="candidate", family=None)
    assert name not in _zed_names(Source(models=[cand], agent_defaults={}))
