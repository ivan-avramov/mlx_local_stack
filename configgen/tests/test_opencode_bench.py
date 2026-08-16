"""The opencode BENCH carrier — the one opencode config that includes candidates.

Same gap the aider bench carrier closes, for the scaffold the campaign actually ships. A model that
is absent from the config cannot even be SELECTED (`opencode run --model mlx-local/<name>` resolves
against it), so a `role: candidate` model has no agentic row through opencode at all — which is why
the B recommendation has been aider-scaffold-specific from the start.

P1a (2026-08-13, opencode 1.18.15) established that opencode forwards BOTH standard params and
non-standard extras: `options.max_tokens: 7` cut completion 45 -> 8, and `options.thinking_budget: 16`
cut it 740 -> 261 while `enable_thinking: false` shifted the PROMPT token count 18,093 -> 18,095,
which only the worker's chat template could do. So the `options` block is a real carrier and a
candidate benchmarked through it runs at `deployed`, not at opencode's defaults.
"""
import json

from configgen import targets
from configgen.emitters.opencode import emit_opencode, emit_opencode_bench
from configgen.source import ModelSpec, Source


def _source_with_candidate() -> Source:
    return Source(
        models=[
            ModelSpec(name="Qwen-A", hf_path="ns/Qwen-A", role="main", family="qwen",
                      display_name="Qwen A", context=262144, output=102400,
                      capabilities=["tools"],
                      sampling={"temperature": 0.4, "top_p": 0.95, "max_tokens": 102400,
                                "thinking_budget": 81920, "enable_thinking": True},
                      edit_format="diff", port=None),
            ModelSpec(name="Cand-N", hf_path="ns/Cand-N", role="candidate", family=None,
                      display_name="Candidate N", context=262144, output=102400,
                      capabilities=["tools", "thinking"],
                      sampling={"temperature": 1.0, "top_p": 0.95, "presence_penalty": 0.0,
                                "max_tokens": 102400, "thinking_budget": 81920,
                                "enable_thinking": True},
                      edit_format="diff", port=None),
            ModelSpec(name="mlx-community/Task-C", hf_path="mlx-community/Task-C", role="task",
                      family=None, display_name="Task C", context=30000, output=2048,
                      capabilities=[], sampling={}, edit_format="whole", port=8092),
        ],
        agent_defaults={"opencode": "Qwen-A"},
    )


def test_bench_config_includes_the_candidate_at_its_tuned_sampling():
    doc = json.loads(emit_opencode_bench(_source_with_candidate()))
    models = doc["provider"]["mlx-local"]["models"]
    assert "Cand-N" in models, "the candidate is the whole reason this file exists"
    assert "Qwen-A" in models, "shipped models must remain, for paired runs in one config"
    opts = models["Cand-N"]["options"]
    assert opts["temperature"] == 1.0
    assert opts["max_tokens"] == 102400
    # The extras path is the one P1a proved works and the one the campaign depends on.
    assert opts["thinking_budget"] == 81920
    assert opts["enable_thinking"] is True
    assert opts["presence_penalty"] == 0.0
    assert models["Cand-N"]["tool_call"] is True, "the tool-call path is what this probe measures"


def test_client_config_still_excludes_the_candidate():
    doc = json.loads(emit_opencode(_source_with_candidate()))
    assert "Cand-N" not in doc["provider"]["mlx-local"]["models"]
    for _n, emit, _d in targets.TARGETS:
        out = emit(_source_with_candidate())
        parts = out.values() if isinstance(out, dict) else [out]
        for text in parts:
            assert "Cand-N" not in text


def test_bench_config_has_no_unrecognized_top_level_keys():
    """opencode 1.18.15 rejects the WHOLE FILE on an unknown top-level key.

    A cosmetic `_generated` provenance note once did exactly that: the config never loaded, zero
    requests reached :8000, and it read like opencode#5674 rather than a defect in our own emitter.
    The bench carrier must not reintroduce it.
    """
    doc = json.loads(emit_opencode_bench(_source_with_candidate()))
    allowed = {"$schema", "provider", "model", "small_model", "plugin", "agent", "mcp"}
    assert set(doc) <= allowed, f"unrecognized top-level keys: {set(doc) - allowed}"


def test_bench_target_is_registered_and_not_a_client_target():
    paths = [d for _n, _e, d in targets.BENCH_TARGETS]
    assert "benchmark/opencode_bench.json" in paths
    client = []
    for _n, _e, d in targets.TARGETS:
        client.extend(d.values() if isinstance(d, dict) else [d])
    assert "benchmark/opencode_bench.json" not in client
