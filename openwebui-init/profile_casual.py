"""
title: Profile · Casual
author: ivan-avramov
version: 0.2.0
required_open_webui_version: 0.9.2
description: |
  Casual / conversational profile for quick everyday Q&A and
  factual-recall synthesis. Family-aware tuning, optimized for snappy
  responses — caps max_tokens low to prevent runaway. Deliberately does
  NOT set thinking_budget on most families so the chat-level Thinking
  filter (or model default) governs whether the model thinks at all.

  Use cases:
    - "Why doesn't the moon fall to earth?"
    - "What do people think about the new BMW iX?"
    - Short factual or synthesis Q&A from training data
    - Anything that should feel snappy

  Mutually exclusive with all other Profile filters and with the Advanced
  Params filter. Composable with the Thinking filter — for true "casual",
  also turn Thinking off so the model answers directly.

  Per-family params (see _PARAMS_BY_FAMILY for full table):
    - Gemma 4 / 3: T=1.0, top_p=0.95, top_k=64
    - Qwen 3.x:    T=0.7, top_p=0.8, top_k=20, presence_penalty=1.5
    - Qwen 2.5:    T=0.7, top_p=0.8, top_k=20, rep_pen=1.05
    - Llama 3.x:   T=0.7, top_p=0.9
    - DeepSeek:    T=0.5 (R1's lower bound), top_p=0.95
    - Mistral 3.x: T=0.3, top_p=0.95

  Unrecognized families error with a clear message — use Advanced Params
  for those, or extend _FAMILY_DETECTION + _PARAMS_BY_FAMILY below.
"""

from typing import Optional

from pydantic import BaseModel, Field

_PROFILE_NAME = "Casual"
_PROFILE_MARKER = "_mlx_active_profile"
_ADVANCED_MARKER = "_mlx_advanced_active"

# >>> FAMILY_DEFAULTS
# Inlined by openwebui-init/_splicer.py at upload time from
# openwebui-init/_family_defaults.py. The empty list is a placeholder so
# that an unspliced upload fails fast at family detection.
_FAMILY_DETECTION = []
# <<< FAMILY_DEFAULTS

_PARAMS_BY_FAMILY = {
    "gemma_4":       {"temperature": 1.0, "top_p": 0.95, "top_k": 64, "max_tokens": 4096},
    "gemma_3":       {"temperature": 1.0, "top_p": 0.95, "top_k": 64, "max_tokens": 4096},
    "qwen3":         {"temperature": 0.7, "top_p": 0.8,  "top_k": 20, "presence_penalty": 1.5,    "max_tokens": 4096},
    "qwen3_moe":     {"temperature": 0.7, "top_p": 0.8,  "top_k": 20, "presence_penalty": 1.5,    "max_tokens": 4096},
    "qwen2_5":       {"temperature": 0.7, "top_p": 0.8,  "top_k": 20, "repetition_penalty": 1.05, "max_tokens": 4096},
    "llama_3":       {"temperature": 0.7, "top_p": 0.9,  "max_tokens": 4096},
    "deepseek_r1":   {"temperature": 0.5, "top_p": 0.95, "max_tokens": 4096},
    "deepseek_v3":   {"temperature": 0.5, "top_p": 0.95, "max_tokens": 4096},
    "mistral_small": {"temperature": 0.3, "top_p": 0.95, "max_tokens": 4096},
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
        self.icon= '''data:image/svg+xml;base64,PCEtLSBAbGljZW5zZSBsdWNpZGUtc3RhdGljIHYxLjE0LjAgLSBJU0MgLS0+CjxzdmcKICBjbGFzcz0ibHVjaWRlIGx1Y2lkZS1zb2ZhIgogIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICB3aWR0aD0iMjQiCiAgaGVpZ2h0PSIyNCIKICB2aWV3Qm94PSIwIDAgMjQgMjQiCiAgZmlsbD0ibm9uZSIKICBzdHJva2U9InRlYWwiCiAgc3Ryb2tlLXdpZHRoPSIyLjUiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMjAgOVY2YTIgMiAwIDAgMC0yLTJINmEyIDIgMCAwIDAtMiAydjMiIC8+CiAgPHBhdGggZD0iTTIgMTZhMiAyIDAgMCAwIDIgMmgxNmEyIDIgMCAwIDAgMi0ydi01YTIgMiAwIDAgMC00IDB2MS41YS41LjUgMCAwIDEtLjUuNWgtMTFhLjUuNSAwIDAgMS0uNS0uNVYxMWEyIDIgMCAwIDAtNCAweiIgLz4KICA8cGF0aCBkPSJNNCAxOHYyIiAvPgogIDxwYXRoIGQ9Ik0yMCAxOHYyIiAvPgogIDxwYXRoIGQ9Ik0xMiA0djkiIC8+Cjwvc3ZnPgo='''

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
