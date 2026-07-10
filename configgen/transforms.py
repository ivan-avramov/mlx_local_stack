from .source import ModelSpec

_OPENAI_KEYS = ("temperature", "top_p", "max_tokens")
_QWEN_EXTRA = ("top_k", "min_p", "presence_penalty", "enable_thinking", "thinking_budget")
_GEMMA_EXTRA = ("top_k", "min_p", "repetition_penalty", "enable_thinking", "thinking_budget")
_OWUI_FEATURES = ("web_search", "code_interpreter", "vision", "image_generation",
                  "file_upload", "file_context", "citations", "status_updates",
                  "usage", "builtin_tools")
_DEFAULT_FEATURES = ("web_search", "code_interpreter")

def input_limit(m: ModelSpec) -> int:
    return m.context - m.output

def sampling_openai(m: ModelSpec) -> dict:
    return {k: m.sampling[k] for k in _OPENAI_KEYS if k in m.sampling}

def sampling_extra(m: ModelSpec) -> dict:
    keys = _QWEN_EXTRA if m.family == "qwen" else _GEMMA_EXTRA
    return {k: m.sampling[k] for k in keys if k in m.sampling}

def owui_meta(m: ModelSpec) -> dict:
    caps = set(m.capabilities)
    capabilities = {f: True for f in _OWUI_FEATURES if f in caps or f in ("usage","status_updates","file_context","citations","builtin_tools")}
    default_features = [f for f in _DEFAULT_FEATURES if f in caps]
    return {"capabilities": capabilities, "defaultFeatureIds": default_features}
