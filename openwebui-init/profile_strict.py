"""
title: Profile · Strict
author: ivan-avramov
version: 0.2.0
required_open_webui_version: 0.9.2
description: |
  Locks sampling for deterministic implementation tasks under explicit
  constraints (multi-rule coding prompts, refactoring, algorithm
  implementation). Family-aware: applies the right repetition-control
  knob for each model family — Gemma uses repetition_penalty, Qwen 3.x
  uses presence_penalty (rep_penalty is forbidden by the Qwen team),
  Llama uses frequency_penalty.

  Mutually exclusive with all other Profile filters and with the Advanced
  Params filter. Composable with the Thinking filter.

  Per-family params (see _PARAMS_BY_FAMILY for full table):
    - Gemma 4 / 3: T=0.2, top_p=0.9, top_k=64, rep_pen=1.05
    - Qwen 3.x:    T=0.6, top_p=0.95, top_k=20, presence_penalty=0.0
    - Qwen 2.5:    T=0.2, top_p=0.9, top_k=20, rep_pen=1.05
    - Llama 3.x:   T=0.2, top_p=0.9, frequency_penalty=0.0
    - DeepSeek R1: T=0.5 (R1 min), top_p=0.95
    - DeepSeek V3: T=0.3, top_p=0.95
    - Mistral 3.x: T=0.15, top_p=1.0 (don't push higher; model degrades)

  Unrecognized families error with a clear message — use Advanced Params
  for those, or extend _FAMILY_DETECTION + _PARAMS_BY_FAMILY below.
"""

from typing import Optional

from pydantic import BaseModel, Field

_PROFILE_NAME = "Strict"
_PROFILE_MARKER = "_mlx_active_profile"
_ADVANCED_MARKER = "_mlx_advanced_active"

# Family detection table (same across all profile filters).
# Most-specific substring first; first match wins. Quantizer prefix
# (mlx-community/, unsloth/, lmstudio-community/) is stripped before
# matching — UD/dynamic vs uniform quantization does NOT change
# recommended sampling params per Unsloth and upstream docs.
# >>> FAMILY_DEFAULTS
# Inlined by openwebui-init/_splicer.py at upload time from
# openwebui-init/_family_defaults.py. The empty list is a placeholder so
# that an unspliced upload fails fast at family detection.
_FAMILY_DETECTION = []
# <<< FAMILY_DEFAULTS

# Per-family params for THIS profile. Families not listed here error
# with a "profile not configured for family" message.
_PARAMS_BY_FAMILY = {
    "gemma_4":       {"temperature": 0.2, "top_p": 0.9,  "top_k": 64, "repetition_penalty": 1.05, "thinking_budget": 10000, "max_tokens": 16384},
    "gemma_3":       {"temperature": 0.2, "top_p": 0.9,  "top_k": 64, "repetition_penalty": 1.05, "max_tokens": 16384},
    "qwen3":         {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0,    "thinking_budget": 10000, "max_tokens": 16384},
    "qwen3_moe":     {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0,    "thinking_budget": 10000, "max_tokens": 16384},
    "qwen2_5":       {"temperature": 0.2, "top_p": 0.9,  "top_k": 20, "repetition_penalty": 1.05, "max_tokens": 16384},
    "llama_3":       {"temperature": 0.2, "top_p": 0.9,  "frequency_penalty": 0.0,                "max_tokens": 16384},
    "deepseek_r1":   {"temperature": 0.5, "top_p": 0.95,                                          "thinking_budget": 10000, "max_tokens": 16384},
    "deepseek_v3":   {"temperature": 0.3, "top_p": 0.95,                                          "thinking_budget": 10000, "max_tokens": 16384},
    "mistral_small": {"temperature": 0.15, "top_p": 1.0,                                          "max_tokens": 16384},
}


def _detect_family(model_id: str) -> Optional[str]:
    """Detect model family from a HuggingFace model id.

    Strips the community/quantizer prefix (e.g. ``mlx-community/``,
    ``unsloth/``) before matching. Returns the family_id or None if no
    substring matches.
    """
    m = (model_id or "").lower()
    if "/" in m:
        m = m.rsplit("/", 1)[-1]
    for substring, family_id in _FAMILY_DETECTION:
        if substring in m:
            return family_id
    return None


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(
            True,
            description="Master switch. Disable to make the filter a no-op without uninstalling.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.toggle = True
        self.icon= '''data:image/svg+xml;base64,PCEtLSBAbGljZW5zZSBsdWNpZGUtc3RhdGljIHYxLjE0LjAgLSBJU0MgLS0+CjxzdmcKICBjbGFzcz0ibHVjaWRlIGx1Y2lkZS1kcmFmdGluZy1jb21wYXNzIgogIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICB3aWR0aD0iMjQiCiAgaGVpZ2h0PSIyNCIKICB2aWV3Qm94PSIwIDAgMjQgMjQiCiAgZmlsbD0ibm9uZSIKICBzdHJva2U9InRlYWwiCiAgc3Ryb2tlLXdpZHRoPSIyLjUiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJtMTIuOTkgNi43NCAxLjkzIDMuNDQiIC8+CiAgPHBhdGggZD0iTTE5LjEzNiAxMmExMCAxMCAwIDAgMS0xNC4yNzEgMCIgLz4KICA8cGF0aCBkPSJtMjEgMjEtMi4xNi0zLjg0IiAvPgogIDxwYXRoIGQ9Im0zIDIxIDguMDItMTQuMjYiIC8+CiAgPGNpcmNsZSBjeD0iMTIiIGN5PSI1IiByPSIyIiAvPgo8L3N2Zz4K'''

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.enabled:
            return body

        # Mutual exclusion: profile vs Advanced and profile vs profile.
        if body.get(_ADVANCED_MARKER):
            raise ValueError(
                f"Profile '{_PROFILE_NAME}' conflicts with the Advanced "
                f"Params filter. Advanced is manual mode and refuses to run "
                f"alongside profiles. Disable one in chat tools."
            )
        if body.get(_PROFILE_MARKER):
            other = body[_PROFILE_MARKER]
            raise ValueError(
                f"Profile '{_PROFILE_NAME}' conflicts with already-active "
                f"profile '{other}'. Only one profile can run per request — "
                f"disable one in chat tools."
            )

        # Family detection.
        model_id = str(body.get("model", ""))
        family = _detect_family(model_id)
        if family is None:
            raise ValueError(
                f"Profile '{_PROFILE_NAME}': model '{model_id}' is from an "
                f"unrecognized family. Use the Advanced Params filter for "
                f"manual control, or add this family to the profile's "
                f"_FAMILY_DETECTION and _PARAMS_BY_FAMILY tables."
            )
        if family not in _PARAMS_BY_FAMILY:
            raise ValueError(
                f"Profile '{_PROFILE_NAME}' is not configured for family "
                f"'{family}' (model '{model_id}'). Use the Advanced Params "
                f"filter, or add params for this family to _PARAMS_BY_FAMILY."
            )

        params = _PARAMS_BY_FAMILY[family]
        body[_PROFILE_MARKER] = f"{_PROFILE_NAME} ({family})"
        for key, value in params.items():
            body[key] = value
        return body
