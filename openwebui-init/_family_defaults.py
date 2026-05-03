"""
Single source of truth for model-family knowledge used by the OpenWebUI
filter family.

OpenWebUI functions are single-file blobs — they cannot import this module
at runtime. `_splicer.py` inlines values from here into each profile filter
source before upload.

Three categories live here:

  FAMILY_DETECTION    — substring -> family-id mapping for model routing.
                        Inlined into every profile_*.py at upload time.

  VENDOR_RECOMMENDED  — vendor-card recommended sampling defaults per
                        family. Reference for the chat-mode safety floor
                        in models_config.json and for documentation.
                        Not inlined; consumed by tooling.

  FOOTGUNS            — model-creator-mandated constraints (temperature
                        floors/ceilings, repetition-penalty pins, etc.).
                        Reference for the Advanced Params docstring and
                        for future linting. Not inlined; consumed by
                        tooling.

When a vendor publishes a new family, add a row to all three.
"""

# Substring matched against the lowercased trailing path segment of the
# model id (after rsplit('/', 1)). Order matters: most specific first.
FAMILY_DETECTION = [
    # Qwen 3.x dense and MoE variants
    ("qwen3.6-35b-a3b", "qwen3_moe"),
    ("qwen3.6-27b", "qwen3"),
    ("qwen3.6", "qwen3"),
    ("qwen3.5", "qwen3"),
    ("qwen3-", "qwen3"),
    ("qwen3_", "qwen3"),
    # Qwen 2.5 — distinct from 3.x: allows repetition_penalty
    ("qwen2.5-coder", "qwen2_5"),
    ("qwen2.5-vl", "qwen2_5"),
    ("qwen2.5", "qwen2_5"),
    ("qwen2_5", "qwen2_5"),
    # Gemma 4 / 3
    ("gemma-4", "gemma_4"),
    ("gemma_4", "gemma_4"),
    ("gemma-3", "gemma_3"),
    ("gemma_3", "gemma_3"),
    # Llama 3.x
    ("llama-3.3", "llama_3"),
    ("llama-3.2", "llama_3"),
    ("llama-3.1", "llama_3"),
    ("llama-3", "llama_3"),
    ("llama_3", "llama_3"),
    # DeepSeek
    ("deepseek-r1", "deepseek_r1"),
    ("deepseek-v3", "deepseek_v3"),
    # Mistral Small 3.x
    ("mistral-small-3", "mistral_small"),
    ("mistral_small_3", "mistral_small"),
    ("mistral-small", "mistral_small"),
]

# Vendor-card recommendations. These are the values the model creator
# publishes for general-purpose use; they are the right starting point for
# the per-model `params` block in models_config.json. Profiles freely
# override these for their workflow flavor.
#
# `_source` records where the value came from so we can re-verify when a
# new model card ships. Keys present here are exactly the keys the
# mlx-vlm server applies; absent keys mean "no vendor recommendation —
# server default applies".
VENDOR_RECOMMENDED = {
    "qwen3": {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "max_tokens": 32768,
        "thinking_budget": 24000,
        "_source": (
            "Qwen3 model card. Non-thinking defaults. Thinking mode "
            "prefers T=0.6 / top_p=0.95. max_tokens up to 81920 for hard "
            "reasoning per 'thinking sufficiency' guidance."
        ),
    },
    "qwen3_moe": {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "max_tokens": 32768,
        "thinking_budget": 24000,
        "_source": "Qwen3-MoE shares the Qwen3 dense recommendations.",
    },
    "qwen2_5": {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": 32768,
        "_source": (
            "Qwen2.5 model card. repetition_penalty 1.05-1.10 is "
            "tolerated (unlike Qwen 3.x)."
        ),
    },
    "gemma_4": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 64,
        "min_p": 0.0,
        "max_tokens": 131072,
        "_source": "Gemma 4 model card (Google).",
    },
    "gemma_3": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 64,
        "min_p": 0.0,
        "max_tokens": 131072,
        "_source": "Gemma 3 model card (Google).",
    },
    "llama_3": {
        "temperature": 0.6,
        "top_p": 0.9,
        "max_tokens": 8192,
        "_source": (
            "Llama 3 chat defaults (Meta). top_k intentionally unset — "
            "Meta's default is -1 / disabled."
        ),
    },
    "deepseek_r1": {
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 32768,
        "thinking_budget": 24000,
        "_source": (
            "DeepSeek R1 card. Hard band T=0.5-0.7; outside that range "
            "produces endless repetition or incoherence."
        ),
    },
    "deepseek_v3": {
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 8192,
        "_source": "DeepSeek V3 card.",
    },
    "mistral_small": {
        "temperature": 0.15,
        "top_p": 1.0,
        "max_tokens": 32768,
        "_source": (
            "Mistral Small 3.x card. Officially tuned for T=0.15. "
            "Soft ceiling at T=0.7 — pushing higher degrades the model."
        ),
    },
}

# Constraint metadata — model-creator-mandated rules that are
# expensive to violate. The Advanced Params docstring renders these as
# footgun warnings. None means unbounded.
FOOTGUNS = {
    "qwen3": {
        "temperature_min": 0.6,
        "temperature_max": None,
        "repetition_penalty_pinned_to": 1.0,
        "preferred_rep_control": "presence_penalty",
        "note": (
            "Qwen team forbids repetition_penalty != 1.0 (causes language "
            "mixing). Greedy decoding (T=0) causes endless repetitions. "
            "Use presence_penalty for repetition control instead."
        ),
    },
    "qwen3_moe": {
        "temperature_min": 0.6,
        "temperature_max": None,
        "repetition_penalty_pinned_to": 1.0,
        "preferred_rep_control": "presence_penalty",
        "note": "Same constraints as Qwen3 dense.",
    },
    "qwen2_5": {
        "temperature_min": 0.0,
        "temperature_max": None,
        "preferred_rep_control": "repetition_penalty",
        "note": (
            "Qwen 2.5 is more tolerant than 3.x: repetition_penalty up to "
            "~1.10 is fine for English-only short tasks."
        ),
    },
    "gemma_4": {
        "temperature_min": 0.0,
        "temperature_max": None,
        "repetition_penalty_max": 1.10,
        "preferred_rep_control": "repetition_penalty",
        "note": (
            "Cranking repetition_penalty above ~1.10 degrades formatting "
            "fidelity (tables, code fences). Multi-constraint prompts can "
            "trigger self-reverification thinking loops; cap "
            "thinking_budget at 8K-12K to mitigate."
        ),
    },
    "gemma_3": {
        "temperature_min": 0.0,
        "temperature_max": None,
        "repetition_penalty_max": 1.10,
        "preferred_rep_control": "repetition_penalty",
        "note": "Same as Gemma 4 for repetition_penalty.",
    },
    "llama_3": {
        "temperature_min": 0.0,
        "temperature_max": None,
        "preferred_rep_control": "frequency_penalty",
        "top_k_warning": (
            "Do not set top_k unless you know what you're doing. Meta's "
            "default is -1 / disabled."
        ),
        "note": "",
    },
    "deepseek_r1": {
        "temperature_min": 0.5,
        "temperature_max": 0.7,
        "preferred_rep_control": None,
        "note": (
            "Temperature MUST stay in 0.5-0.7. Outside that band R1 "
            "produces endless repetition or incoherence."
        ),
    },
    "deepseek_v3": {
        "temperature_min": 0.0,
        "temperature_max": None,
        "preferred_rep_control": None,
        "note": "",
    },
    "mistral_small": {
        "temperature_min": 0.0,
        "temperature_max": 0.7,
        "preferred_rep_control": None,
        "note": (
            "Officially tuned for T=0.15. Soft ceiling at T=0.7; pushing "
            "higher degrades the model."
        ),
    },
}
