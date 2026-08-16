import json
from ..source import Source
from ..transforms import sampling_openai, sampling_extra, input_limit

def emit_opencode_bench(source: Source) -> str:
    """opencode config for BENCHMARKING: shipped models AND `role: candidate` models.

    Same gap as the aider bench carrier. The client config filters on role == "main", so a candidate
    under test is absent — and an absent model cannot be selected with `opencode run --model`, let
    alone at its tuned sampling. P1a established that opencode DOES forward both standard params and
    non-standard extras (`thinking_budget`, `enable_thinking`), so the options block below is the
    carrier that makes a candidate's agentic row measured at `deployed` rather than at opencode's
    defaults. Deliberately NOT in TARGETS — see configgen/tests/test_opencode_bench.py.
    """
    return _emit(source, roles=("main", "candidate"))


def emit_opencode(source: Source) -> str:
    return _emit(source, roles=("main",))


def _emit(source: Source, *, roles: tuple[str, ...]) -> str:
    main = [m for m in source.models if m.role in roles]
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
