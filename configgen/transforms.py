from .source import ModelSpec

_OPENAI_KEYS = ("temperature", "top_p", "max_tokens")
_QWEN_EXTRA = ("top_k", "min_p", "presence_penalty", "enable_thinking", "thinking_budget")
_GEMMA_EXTRA = ("top_k", "min_p", "repetition_penalty", "enable_thinking", "thinking_budget")
# NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit's model card recommends ONLY temperature/top_p
# (both OpenAI keys, carried by sampling_openai) and specifies nothing else — deliberately
# NOT mirroring qwen/gemma's top_k/min_p/repetition_penalty (see benchmark/bench/model_params.py  # allow-shorthand
# NEMOTRON comment: "No invented top_k/min_p ... a guessed one is a measurement of a config  # allow-shorthand
# nobody chose"). presence_penalty is carried as a SERVING requirement (keeps this stack's
# suffix-decode fallback disabled at 0.0), not a vendor sampling opinion.
# A SET, not a tuple like qwen/gemma above: qwen/gemma's tuple ORDER is pinned to already-committed  # allow-shorthand
# golden config output (their real generation_defaults key order differs from the tuple's), so
# switching them to registry order would drift `configgen check`. Nemotron has no such committed  # allow-shorthand
# tuple-order history, so its branch below iterates the registry's OWN order instead — the bench
# carriers (benchmark/opencode_bench.json, benchmark/aider_bench.model.settings.yml) already
# rendered this model in registry order via the pre-C64 family-less fallback, and the family
# branch below must not reorder them out from under that provenance (C64/F4).
_NEMOTRON_EXTRA = {"presence_penalty", "enable_thinking", "thinking_budget"}
_OWUI_FEATURES = ("web_search", "code_interpreter", "vision", "image_generation",
                  "file_upload", "file_context", "citations", "status_updates",
                  "usage", "builtin_tools")
_DEFAULT_FEATURES = ("web_search", "code_interpreter")

def input_limit(m: ModelSpec) -> int:
    return m.context - m.output

def sampling_openai(m: ModelSpec) -> dict:
    return {k: m.sampling[k] for k in _OPENAI_KEYS if k in m.sampling}

def sampling_extra(m: ModelSpec) -> dict:
    if m.family == "qwen":
        keys = _QWEN_EXTRA
    elif m.family == "gemma":
        keys = _GEMMA_EXTRA
    elif m.family == "nemotron":  # allow-shorthand
        # role=main routes this model through emit_opencode_bench/emit_aider_bench too (they
        # union in role="candidate"/"main" and call this same function) — so a generation_defaults
        # key added later that isn't in _NEMOTRON_EXTRA is silently dropped from BENCH provenance,
        # not just client configs. Extend the set deliberately if that ever happens (C64/F6).
        return {k: m.sampling[k] for k in m.sampling if k in _NEMOTRON_EXTRA}
    else:
        # No family: carry whatever non-OpenAI sampling the registry declares, rather than
        # dropping it. Only role=main REQUIRES a family, so this is the candidate path — and a
        # candidate is exactly what gets benchmarked, where sampling must be production-verbatim.
        # Returning {} here silently discarded presence_penalty / thinking_budget / enable_thinking;
        # mlx-serve would refill them from generation_defaults (FU-2), but then the effective
        # config is absent from the file we keep as provenance. Whitelist-free by design: the
        # registry is the source of truth, so an unknown-to-us key is carried, not swallowed.
        keys = tuple(k for k in m.sampling if k not in _OPENAI_KEYS)
    return {k: m.sampling[k] for k in keys if k in m.sampling}

def owui_meta(m: ModelSpec) -> dict:
    caps = set(m.capabilities)
    capabilities = {f: True for f in _OWUI_FEATURES if f in caps or f in ("usage","status_updates","file_context","citations","builtin_tools")}
    default_features = [f for f in _DEFAULT_FEATURES if f in caps]
    return {"capabilities": capabilities, "defaultFeatureIds": default_features}
