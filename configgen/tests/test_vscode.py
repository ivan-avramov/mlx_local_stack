import json
from dataclasses import replace

from configgen.emitters.vscode import emit_vscode
from configgen.source import Source

def test_vscode_registration_only(sample_source):
    arr = json.loads(emit_vscode(sample_source))
    models = arr[0]["models"]
    ids = {m["id"] for m in models}
    assert ids == {"Qwen-A", "Gemma-B"}            # task excluded
    q = next(m for m in models if m["id"] == "Qwen-A")
    assert q["maxInputTokens"] == 262144 - 102400 and q["maxOutputTokens"] == 102400
    assert set(q) == {"id", "name", "url", "toolCalling", "vision", "thinking", "maxInputTokens", "maxOutputTokens"}


def test_nemotron_family_included_as_main_but_not_as_candidate(nemotron_source):
    # C64/F5: NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit. vscode is registration-only (no sampling
    # carrier), so family itself has nothing to assert on here -- the only thing with teeth is the
    # role filter this promotion depends on, so this checks BOTH sides of it.
    name = "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"
    main_ids = {m["id"] for m in json.loads(emit_vscode(nemotron_source))[0]["models"]}
    assert name in main_ids

    cand = replace(nemotron_source.models[0], role="candidate", family=None)
    cand_ids = {m["id"] for m in json.loads(emit_vscode(Source(models=[cand], agent_defaults={})))[0]["models"]}
    assert name not in cand_ids
