"""
title: Profile · Creative
author: ivan-avramov
version: 0.2.0
required_open_webui_version: 0.9.2
description: |
  Creative-writing profile for essays, fiction, and non-technical
  long-form prose. Family-aware: high temperature with widened top_p for
  vocabulary variety on most families, but capped on Mistral 3.x (model
  degrades above 0.7) and DeepSeek R1 (must stay in 0.5–0.7).

  On Gemma a mild rep_penalty is applied since Gemma's prose loops
  occasionally on long-form generation; Qwen 3.x uses presence_penalty
  set high (2.0) for maximum vocabulary variety; Llama uses
  frequency_penalty.

  Use cases:
    - Essays ("write an essay on the benefits of smartphone use in adolescents")
    - Fiction
    - Non-technical brainstorming
    - Anything where variety > determinism

  Mutually exclusive with all other Profile filters and with the Advanced
  Params filter. Composable with the Thinking filter — usually OFF for
  pure creative flow.

  Per-family params (see _PARAMS_BY_FAMILY for full table):
    - Gemma 4 / 3: T=1.2, top_p=0.97, top_k=80, rep_pen=1.1
    - Qwen 3.x:    T=1.0, top_p=0.95, top_k=40, presence_penalty=2.0
    - Qwen 2.5:    T=0.9, top_p=0.95, top_k=20, rep_pen=1.1
    - Llama 3.x:   T=0.9, top_p=0.95, frequency_penalty=0.3
    - DeepSeek:    no entry — R1 is bounded to 0.5-0.7 (use Casual instead)
    - Mistral 3.x: T=0.7, top_p=0.95 (capped — model degrades above 0.7)

  Unrecognized families error with a clear message — use Advanced Params
  for those, or extend _FAMILY_DETECTION + _PARAMS_BY_FAMILY below.
"""

from typing import Optional

from pydantic import BaseModel, Field

_PROFILE_NAME = "Creative"
_PROFILE_MARKER = "_mlx_active_profile"
_ADVANCED_MARKER = "_mlx_advanced_active"

# >>> FAMILY_DEFAULTS
# Inlined by openwebui-init/_splicer.py at upload time from
# openwebui-init/_family_defaults.py. The empty list is a placeholder so
# that an unspliced upload fails fast at family detection.
_FAMILY_DETECTION = []
# <<< FAMILY_DEFAULTS

# Note: deepseek_r1 deliberately excluded — R1 is bounded to T=0.5-0.7
# per the DeepSeek team. Use Casual profile instead, or Advanced for
# experimentation. deepseek_v3 also excluded — V3 is tuned for tasks,
# not creative; falls outside the profile's intent.
_PARAMS_BY_FAMILY = {
    "gemma_4":       {"temperature": 1.2, "top_p": 0.97, "top_k": 80, "repetition_penalty": 1.1, "max_tokens": 8192},
    "gemma_3":       {"temperature": 1.2, "top_p": 0.97, "top_k": 80, "repetition_penalty": 1.1, "max_tokens": 8192},
    "qwen3":         {"temperature": 1.0, "top_p": 0.95, "top_k": 40, "presence_penalty": 2.0,    "max_tokens": 8192},
    "qwen3_moe":     {"temperature": 1.0, "top_p": 0.95, "top_k": 40, "presence_penalty": 2.0,    "max_tokens": 8192},
    "qwen2_5":       {"temperature": 0.9, "top_p": 0.95, "top_k": 20, "repetition_penalty": 1.1,  "max_tokens": 8192},
    "llama_3":       {"temperature": 0.9, "top_p": 0.95, "frequency_penalty": 0.3, "max_tokens": 8192},
    "mistral_small": {"temperature": 0.7, "top_p": 0.95, "max_tokens": 8192},
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
        self.icon= '''data:image/svg+xml;base64,PCEtLSBAbGljZW5zZSBsdWNpZGUtc3RhdGljIHYxLjE0LjAgLSBJU0MgLS0+CjxzdmcKICBjbGFzcz0ibHVjaWRlIGx1Y2lkZS1wYWxldHRlIgogIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICB3aWR0aD0iMjQiCiAgaGVpZ2h0PSIyNCIKICB2aWV3Qm94PSIwIDAgMjQgMjQiCiAgZmlsbD0ibm9uZSIKICBzdHJva2U9InRlYWwiCiAgc3Ryb2tlLXdpZHRoPSIyLjUiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMTIgMjJhMSAxIDAgMCAxIDAtMjAgMTAgOSAwIDAgMSAxMCA5IDUgNSAwIDAgMS01IDVoLTIuMjVhMS43NSAxLjc1IDAgMCAwLTEuNCAyLjhsLjMuNGExLjc1IDEuNzUgMCAwIDEtMS40IDIuOHoiIC8+CiAgPGNpcmNsZSBjeD0iMTMuNSIgY3k9IjYuNSIgcj0iLjUiIGZpbGw9ImN1cnJlbnRDb2xvciIgLz4KICA8Y2lyY2xlIGN4PSIxNy41IiBjeT0iMTAuNSIgcj0iLjUiIGZpbGw9ImN1cnJlbnRDb2xvciIgLz4KICA8Y2lyY2xlIGN4PSI2LjUiIGN5PSIxMi41IiByPSIuNSIgZmlsbD0iY3VycmVudENvbG9yIiAvPgogIDxjaXJjbGUgY3g9IjguNSIgY3k9IjcuNSIgcj0iLjUiIGZpbGw9ImN1cnJlbnRDb2xvciIgLz4KPC9zdmc+Cg=='''

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
                f"'{family}' (model '{model_id}'). DeepSeek R1 is bounded "
                f"to T=0.5-0.7 — use Casual profile or Advanced Params. "
                f"Otherwise add params for this family to _PARAMS_BY_FAMILY."
            )

        params = _PARAMS_BY_FAMILY[family]
        body[_PROFILE_MARKER] = f"{_PROFILE_NAME} ({family})"
        for key, value in params.items():
            body[key] = value
        return body
