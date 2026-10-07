"""M59 native benchmark carrier; candidates retain deployed sampling."""

import json

from configgen import targets
from configgen.emitters import opencode
from configgen.tests.test_opencode_bench import _source_with_candidate
from configgen.transforms import sampling_openai, sampling_extra, input_limit


def test_native_bench_document():
    """Verify native bench document."""
    source = _source_with_candidate()
    assert hasattr(opencode, "emit_opencode_bench_v2"), "native bench emitter is missing"
    doc = json.loads(opencode.emit_opencode_bench_v2(source))
    assert set(doc) == {
        "$schema",
        "plugins",
        "compaction",
        "agents",
        "update",
        "share",
        "permissions",
        "providers",
    }
    assert "_generated" not in json.dumps(doc)
    assert doc["plugins"] == [
        "-opencode.provider.vllm",
        "-opencode.provider.ollama",
        "-opencode.provider.lmstudio",
        "-opencode.config.compatibility",
    ]
    assert doc["compaction"] == {"auto": False}
    assert doc["agents"] == {"title": {"disabled": True}}
    assert doc["update"] == "disable" and doc["share"] == "disabled"
    assert doc["permissions"] == [
        dict(action=a, resource="*", effect="deny")
        for a in ("external_directory", "question", "websearch", "webfetch", "execute")
    ]
    assert doc["providers"]["vllm"]["settings"]["baseURL"] == "http://127.0.0.1:9/v1"
    local = doc["providers"]["mlx-local"]
    assert local["package"] == "@opencode/ai/providers/openai-compatible"
    assert local["settings"] == {"baseURL": "http://localhost:8000/v1", "apiKey": "not-needed"}
    assert set(local["models"]) == {"Qwen-A", "Cand-N"}
    for m in source.models[:2]:
        block = local["models"][m.name]
        assert block["body"] == {**sampling_openai(m), **sampling_extra(m), "seed": 0}
        assert block["compatibility"] == {"maxTokensField": "max_tokens"}
        assert block["limit"] == dict(context=m.context, input=input_limit(m), output=m.output)
        assert block["capabilities"] == dict(tools=True, input=["text"], output=["text"])
    source.models[0].capabilities.append("vision")
    assert json.loads(opencode.emit_opencode_bench_v2(source))["providers"]["mlx-local"]["models"][
        "Qwen-A"
    ]["capabilities"]["input"] == ["text", "image"]
    assert "Cand-N" not in opencode.emit_opencode(source)


def test_bench_registration():
    """Verify bench registration."""
    assert any(
        n == "opencode-bench-v2" and p == "benchmark/opencode_bench_v2.json"
        for n, _, p in targets.BENCH_TARGETS
    ), "v2 bench target is missing"
    assert all(n != "opencode-bench-v2" for n, _, _ in targets.TARGETS)
