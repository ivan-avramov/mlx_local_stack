"""
title: Profile · Math
author: ivan-avramov
version: 0.2.0
required_open_webui_version: 0.9.2
description: |
  Math / formal-logic profile for calculus, proofs, and step-by-step
  derivations. Low temperature for determinism. Family-aware: avoids
  repetition_penalty entirely on every family — math benefits from
  re-stating equations and lemmas, and penalizing repetition actively
  hurts proof writing. Highest thinking budget where the family supports
  it, to give multi-step proofs room.

  Use cases:
    - Calculus problems
    - Formal proofs
    - Step-by-step derivations
    - Symbolic logic

  Mutually exclusive with all other Profile filters and with the Advanced
  Params filter. Composable with the Thinking filter (turn it ON for math).

  Per-family params (see _PARAMS_BY_FAMILY for full table):
    - Gemma 4 / 3: T=0.4, top_p=0.9, top_k=64
    - Qwen 3.x:    T=0.6, top_p=0.95, top_k=20, presence_penalty=0.0
    - Qwen 2.5:    T=0.3, top_p=0.85, top_k=20
    - Llama 3.x:   T=0.3, top_p=0.9
    - DeepSeek:    T=0.6, top_p=0.95 (R1's sweet spot for reasoning)
    - Mistral 3.x: T=0.2, top_p=0.95

  Unrecognized families error with a clear message — use Advanced Params
  for those, or extend _FAMILY_DETECTION + _PARAMS_BY_FAMILY below.
"""

from typing import Optional

from pydantic import BaseModel, Field

_PROFILE_NAME = "Math"
_PROFILE_MARKER = "_mlx_active_profile"
_ADVANCED_MARKER = "_mlx_advanced_active"

# >>> FAMILY_DEFAULTS
# Inlined by openwebui-init/_splicer.py at upload time from
# openwebui-init/_family_defaults.py. The empty list is a placeholder so
# that an unspliced upload fails fast at family detection.
_FAMILY_DETECTION = []
# <<< FAMILY_DEFAULTS

_PARAMS_BY_FAMILY = {
    "gemma_4":       {"temperature": 0.4, "top_p": 0.9,  "top_k": 64, "thinking_budget": 16000, "max_tokens": 16384},
    "gemma_3":       {"temperature": 0.4, "top_p": 0.9,  "top_k": 64, "max_tokens": 16384},
    "qwen3":         {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0, "thinking_budget": 16000, "max_tokens": 16384},
    "qwen3_moe":     {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0, "thinking_budget": 16000, "max_tokens": 16384},
    "qwen2_5":       {"temperature": 0.3, "top_p": 0.85, "top_k": 20, "max_tokens": 16384},
    "llama_3":       {"temperature": 0.3, "top_p": 0.9,  "max_tokens": 16384},
    "deepseek_r1":   {"temperature": 0.6, "top_p": 0.95, "thinking_budget": 16000, "max_tokens": 16384},
    "deepseek_v3":   {"temperature": 0.6, "top_p": 0.95, "thinking_budget": 16000, "max_tokens": 16384},
    "mistral_small": {"temperature": 0.2, "top_p": 0.95, "max_tokens": 16384},
}


def _detect_family(model_id: str) -> Optional[str]:
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
        self.icon= '''data:image/svg+xml;base64,PCEtLSBAbGljZW5zZSBsdWNpZGUtc3RhdGljIHYxLjE0LjAgLSBJU0MgLS0+CjxzdmcKICBjbGFzcz0ibHVjaWRlIGx1Y2lkZS1waSIKICB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciCiAgd2lkdGg9IjI0IgogIGhlaWdodD0iMjQiCiAgdmlld0JveD0iMCAwIDI0IDI0IgogIGZpbGw9Im5vbmUiCiAgc3Ryb2tlPSJ0ZWFsIgogIHN0cm9rZS13aWR0aD0iMi41IgogIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIKICBzdHJva2UtbGluZWpvaW49InJvdW5kIgo+CiAgPGxpbmUgeDE9IjkiIHgyPSI5IiB5MT0iNCIgeTI9IjIwIiAvPgogIDxwYXRoIGQ9Ik00IDdjMC0xLjcgMS4zLTMgMy0zaDEzIiAvPgogIDxwYXRoIGQ9Ik0xOCAyMGMtMS43IDAtMy0xLjMtMy0zVjQiIC8+Cjwvc3ZnPgo='''

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.enabled:
            return body

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
