import json
import hashlib
from ..source import Source
from ..transforms import owui_meta, sampling_openai, sampling_extra

# Base builtin tools always exposed for any model. web_search/image_generation
# are added conditionally below (see _BUILTIN_OPTIONAL) so a capability-less
# model (e.g. the lightweight task model) doesn't advertise them -- this
# matches the committed models_config.json, where the task-model entry's
# builtinTools omits web_search/image_generation while every main model has
# both.
_BUILTIN_BASE = {"time": True, "memory": True, "chats": True, "notes": True,
                 "knowledge": True, "channels": True, "code_interpreter": True}
_BUILTIN_OPTIONAL = ("web_search", "image_generation")

# OWUI forwards additional OpenAI-compatible parameters, including enable_thinking.
# The FAMILY whitelist itself is NOT reimplemented
# here (C64/F2-F3 fix) -- `sampling_openai`/`sampling_extra` are the single source of truth for
# which keys leave the registry for a given family, so this only picks OWUI's subset of THOSE,
# rather than filtering `m.sampling` directly (which used to leak any stray family-mismatched key,
# e.g. a top_k left on a nemotron entry, straight into openwebui-init/models_config.json).  # allow-shorthand
_OWUI_SUPPORTED = ("temperature", "top_p", "top_k", "min_p", "presence_penalty",
                   "max_tokens", "thinking_budget", "enable_thinking")


def _params(m) -> dict:
    allowed = {**sampling_openai(m), **sampling_extra(m)}
    p = {"function_calling": "native"}
    for k in _OWUI_SUPPORTED:
        if k in allowed:
            p[k] = allowed[k]
    if "reasoning_effort" in m.sampling:
        p["reasoning_effort"] = m.sampling["reasoning_effort"]
    if "repetition_penalty" in allowed:
        # OWUI/Ollama use `repeat_penalty`, not the mlx-serve/HF name.
        p["repeat_penalty"] = allowed["repetition_penalty"]
    return p


def _meta(m) -> dict:
    om = owui_meta(m)
    builtin = dict(_BUILTIN_BASE)
    for k in _BUILTIN_OPTIONAL:
        if om["capabilities"].get(k):
            builtin[k] = True
    return {"profile_image_url": "/static/favicon.png", "description": None,
            **om, "builtinTools": builtin, "defaultFilterIds": [],
            "mlx_local_stack_managed": True}


def emit_owui(source: Source) -> str:
    out = []
    for m in source.models:
        # OWUI intentionally carries BOTH main and task (it routes title/tag calls to the task
        # model), so this excludes only `candidate` rather than filtering to role == "main" the
        # way the other four emitters do. Candidates are registered so the bench harness can serve
        # them; publishing an unvetted model into models_config.json — which AGENTS.md calls the
        # SOURCE OF TRUTH pushed to OWUI — would put it in front of a human daily driver.
        if m.role == "candidate":
            continue
        capabilities = ["completion"] + (["vision"] if "vision" in m.capabilities else [])
        out.append({
            "id": m.name, "object": "model", "owned_by": "openai",
            "capabilities": capabilities, "connection_type": "local",
            "name": m.name, "params": _params(m), "meta": _meta(m),
            "access_grants": [], "is_active": True,
        })
    return json.dumps(out, indent=2) + "\n"


def emit_owui_settings(source: Source) -> str:
    """Deployment policy consumed by both startup and the manual publisher."""
    main = [m.name for m in source.models if m.role == "main"]
    tasks = [m.name for m in source.models if m.role == "task"]
    if len(tasks) > 1:
        raise ValueError("OpenWebUI supports one dedicated task model")
    default = source.agent_defaults.get("openwebui", source.agent_defaults.get("opencode"))
    if default is None:
        default = main[0] if main else ""
    if default and default not in main:
        raise ValueError("OpenWebUI default must have role=main")
    order = ([default] if default else []) + [m for m in main if m != default] + tasks
    return json.dumps({
        "schema": 1,
        "models_sha256": hashlib.sha256(emit_owui(source).encode()).hexdigest(),
        "main_model_ids": main,
        "task_model_id": tasks[0] if tasks else None,
        "excluded_model_ids": [m.name for m in source.models if m.role == "candidate"]
                              + list(source.router_only_models),
        "defaults": {"DEFAULT_MODELS": default, "DEFAULT_PINNED_MODELS": default,
                     "MODEL_ORDER_LIST": order},
    }, indent=2) + "\n"
