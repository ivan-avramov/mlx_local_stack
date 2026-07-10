import json, re
from configgen.emitters.zed import emit_zed

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
