import json
from configgen.emitters.vscode import emit_vscode

def test_vscode_registration_only(sample_source):
    arr = json.loads(emit_vscode(sample_source))
    models = arr[0]["models"]
    ids = {m["id"] for m in models}
    assert ids == {"Qwen-A", "Gemma-B"}            # task excluded
    q = next(m for m in models if m["id"] == "Qwen-A")
    assert q["maxInputTokens"] == 262144 - 102400 and q["maxOutputTokens"] == 102400
    assert set(q) == {"id", "name", "url", "toolCalling", "vision", "thinking", "maxInputTokens", "maxOutputTokens"}
