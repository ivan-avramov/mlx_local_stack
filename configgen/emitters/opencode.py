import json
from ..source import Source
from ..transforms import sampling_openai, sampling_extra, input_limit

def emit_opencode(source: Source) -> str:
    main = [m for m in source.models if m.role == "main"]
    task = next((m for m in source.models if m.role == "task"), None)
    local_models = {}
    for m in main:
        local_models[m.name] = {
            "name": m.display_name, "tool_call": True, "reasoning": True, "attachment": True,
            "limit": {"context": input_limit(m), "output": m.output},
            "options": {**sampling_openai(m), **sampling_extra(m)},
        }
    # NO `_generated` marker here, deliberately. opencode validates its config strictly and rejects
    # the WHOLE FILE on an unknown top-level key: on 1.18.15 the cosmetic provenance note produced
    # `Unrecognized key: _generated`, the config never loaded, and zero requests reached :8000 —
    # which read exactly like opencode#5674 ("custom endpoints unusable") and nearly got the
    # campaign's declared primary harness written off over a defect in our own emitter. JSON has no
    # comments and opencode offers no sanctioned slot for one, so the "generated, do not hand-edit"
    # note lives in opencode_config/README.md instead. Pinned by
    # configgen/tests/test_opencode.py:test_no_unrecognized_top_level_keys.
    doc = {"$schema": "https://opencode.ai/config.json",
           "provider": {"mlx-local": {
               "npm": "@ai-sdk/openai-compatible", "name": "mlx-serve (local)",
               "options": {"baseURL": "http://localhost:8000/v1", "apiKey": "not-needed"},
               "models": local_models}}}
    if task:
        doc["provider"]["mlx-task"] = {
            "npm": "@ai-sdk/openai-compatible", "name": "mlx task model (local)",
            "options": {"baseURL": f"http://localhost:{task.port}/v1", "apiKey": "not-needed"},
            "models": {task.name: {"name": task.display_name, "tool_call": False,
                                    "attachment": False,
                                    "limit": {"context": input_limit(task), "output": task.output}}}}
        doc["small_model"] = f"mlx-task/{task.name}"
    default = source.agent_defaults.get("opencode")
    if default:
        doc["model"] = f"mlx-local/{default}"
    doc.setdefault("plugin", ["superpowers@git+https://github.com/obra/superpowers.git"])
    return json.dumps(doc, indent=2) + "\n"
