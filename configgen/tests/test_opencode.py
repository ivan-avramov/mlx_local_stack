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


def test_no_unrecognized_top_level_keys(sample_source):
    """opencode validates its config STRICTLY and rejects the whole file on an unknown top-level key.

    Measured 2026-08-13 on opencode 1.18.15: the emitter's cosmetic `_generated` provenance marker
    produced `Error: Configuration is invalid ... Unrecognized key: _generated`, so the config never
    loaded, ZERO requests reached :8000, and every P1a gate failed rc=1. It read like the known
    upstream bug opencode#5674 ("custom endpoints unusable") and would have cancelled the campaign's
    declared primary harness over a defect in our own emitter.

    Only keys opencode's schema accepts may appear at the top level. `$schema` is allowed; a bare
    `_`-prefixed comment key is NOT — JSON has no comments, and opencode offers no sanctioned slot
    for one, so the provenance note lives in opencode_config/README.md instead.
    """
    d = json.loads(emit_opencode(sample_source))
    allowed = {"$schema", "provider", "model", "small_model", "plugin"}
    assert set(d) <= allowed, f"unrecognized top-level key(s): {sorted(set(d) - allowed)}"
    assert "_generated" not in d


def test_generated_marker_is_absent_from_every_nesting_level(sample_source):
    """The key breaks the parse wherever opencode's schema is strict, so don't just move it inward."""
    def walk(node, path="$"):
        if isinstance(node, dict):
            assert "_generated" not in node, f"_generated found at {path}"
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(json.loads(emit_opencode(sample_source)))
