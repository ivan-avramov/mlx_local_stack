import json
from ..source import Source
from ..transforms import owui_meta

# Base builtin tools always exposed for any model. web_search/image_generation
# are added conditionally below (see _BUILTIN_OPTIONAL) so a capability-less
# model (e.g. the lightweight task model) doesn't advertise them -- this
# matches the committed models_config.json, where the task-model entry's
# builtinTools omits web_search/image_generation while every main model has
# both.
_BUILTIN_BASE = {"time": True, "memory": True, "chats": True, "notes": True,
                 "knowledge": True, "channels": True, "code_interpreter": True}
_BUILTIN_OPTIONAL = ("web_search", "image_generation")

_PARAM_KEYS = ("temperature", "top_p", "top_k", "min_p", "presence_penalty",
               "max_tokens", "thinking_budget")


def _params(m) -> dict:
    s = m.sampling
    p = {"function_calling": "native"}
    for k in _PARAM_KEYS:
        if k in s:
            p[k] = s[k]
    if "repetition_penalty" in s:
        # OWUI/Ollama use `repeat_penalty`, not the mlx-serve/HF name.
        p["repeat_penalty"] = s["repetition_penalty"]
    return p


def _meta(m) -> dict:
    om = owui_meta(m)
    builtin = dict(_BUILTIN_BASE)
    for k in _BUILTIN_OPTIONAL:
        if om["capabilities"].get(k):
            builtin[k] = True
    return {"profile_image_url": "/static/favicon.png", "description": None,
            **om, "builtinTools": builtin, "defaultFilterIds": []}


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
