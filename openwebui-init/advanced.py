"""
title: Advanced Params
author: ivan-avramov
version: 0.3.0
required_open_webui_version: 0.9.2
description: |
  Per-chat surgical override of any sampling/thinking knob the mlx-vlm
  server applies. Exposes every supported param as a UserValve so each
  user can tune them in the chat UI.

  Mutually exclusive with the Thinking filter and all Profile filters.
  This filter is "manual mode" — when active, you control every knob
  yourself; profiles and thinking presets cannot run simultaneously.

  Knobs the mlx-vlm server actually applies (verified against server.py):
    - enable_thinking, thinking_budget, thinking_start_token
    - temperature, top_p, top_k, min_p, max_tokens, seed
    - repetition_penalty (also accepted as repeat_penalty alias)
    - logit_bias

  Semantics:
    - Any UserValve set to a non-None value is injected into the outbound
      request body, OVERRIDING anything the model's Advanced Params or
      Custom Parameters set for that key.
    - UserValves left at None are passthrough — the model's existing
      values (if any) reach the server unchanged.
    - The `unset_fields` valve takes a comma-separated list of parameter
      names to strip entirely from the outbound body, so the server falls
      back to its own defaults. Use this when the model's Advanced Params
      pinned a value you don't want sent for this chat.

  Family-specific footgun warnings (read before overriding):
    - Qwen 3.x / 3.5 / 3.6: DO NOT set `repetition_penalty` to anything
      other than 1.0. The Qwen team explicitly warns that non-1.0
      repetition_penalty causes language mixing and quality degradation.
      Use `presence_penalty` (range 0.0-2.0; 1.5 default) for repetition
      control instead. The Profile filters auto-route to the correct knob
      per family; this filter does NOT — you are responsible for picking
      the right one. The repetition_penalty valve is exposed here only
      for experimentation.
    - Qwen 3.x: DO NOT set `temperature=0`. Greedy decoding causes
      endless repetitions per the Qwen team. Minimum is ~0.6.
    - Gemma 3/4: DO NOT crank `repetition_penalty` above ~1.10. Above
      that, formatting fidelity (tables, code fences) degrades.
    - DeepSeek R1: keep `temperature` strictly in 0.5-0.7. Outside that
      range the model produces endless repetition or incoherence.
    - Mistral Small 3.x: keep `temperature` ≤ 0.7. Officially tuned for
      0.15; pushing higher degrades the model.
    - Llama 3.x: do not set `top_k` unless you know what you're doing —
      Meta's default is -1 (disabled).
"""

from typing import Optional

from pydantic import BaseModel, Field

# Marker keys used by the mlx-vlm filter family to enforce mutual exclusion.
_PROFILE_MARKER = "_mlx_active_profile"
_THINKING_MARKER = "_mlx_thinking_active"
_ADVANCED_MARKER = "_mlx_advanced_active"


class Filter:
    class Valves(BaseModel):
        """Admin-side global toggles for this filter."""

        enabled: bool = Field(
            True,
            description="Master switch. Disable to make the filter a no-op without uninstalling.",
        )

    class UserValves(BaseModel):
        """Per-user / per-chat overrides. Settable from the chat UI."""

        # --- Thinking ---
        enable_thinking: Optional[bool] = Field(
            None,
            description="Enable the model's <think> reasoning channel. Leave unset to defer to server default.",
        )
        thinking_budget: Optional[int] = Field(
            None,
            description=(
                "Hard cap on thinking tokens. Server auto-budget is 80%% of "
                "max_tokens; set this to override. Recommend 8000-12000 to "
                "break self-reverification loops on multi-constraint prompts."
            ),
            ge=1,
        )
        thinking_start_token: Optional[str] = Field(
            None,
            description="Override the chat-template's thinking start token. Advanced: leave unset unless you know you need it.",
        )

        # --- Sampling ---
        temperature: Optional[float] = Field(
            None,
            description="Sampling temperature. 0.3-0.5 reduces loop risk on multi-constraint prompts; 0.7-1.0 is more creative.",
            ge=0.0,
            le=2.0,
        )
        top_p: Optional[float] = Field(
            None, description="Nucleus sampling threshold (0,1].", gt=0.0, le=1.0
        )
        top_k: Optional[int] = Field(
            None, description="Top-K sampling. 0 disables.", ge=0
        )
        min_p: Optional[float] = Field(
            None,
            description="Min-P sampling threshold. 0 disables.",
            ge=0.0,
            le=1.0,
        )
        max_tokens: Optional[int] = Field(
            None,
            description="Max output tokens (includes thinking). Caps total work.",
            ge=1,
        )
        seed: Optional[int] = Field(
            None,
            description=(
                "Random seed for reproducibility. Best-effort under continuous "
                "batching — interleaved batches share PRNG state."
            ),
        )

        # --- Repetition ---
        repetition_penalty: Optional[float] = Field(
            None,
            description=(
                "Down-weights tokens already in the recent context. 1.08-1.15 "
                "is the loop-mitigation knob — directly attacks 'one last "
                "thing' / 'wait, let me re-verify' phrase reinforcement on "
                "multi-constraint prompts. Leave unset (or 1.0) for no penalty."
            ),
            gt=0.0,
            le=2.0,
        )

        # --- Strip parameters entirely (server falls back to its own default) ---
        unset_fields: str = Field(
            "",
            description=(
                "Comma-separated parameter names to REMOVE from the outbound "
                "request before send. Use this to disable a value the model's "
                "Advanced Params or Custom Parameters pinned, so the server "
                "falls back to its own default. Example: 'temperature,top_p'. "
                "Names match the request keys: temperature, top_p, top_k, "
                "min_p, max_tokens, seed, repetition_penalty, repeat_penalty, "
                "enable_thinking, thinking_budget, thinking_start_token, "
                "frequency_penalty, presence_penalty, stop, logit_bias."
            ),
        )

    # Names of UserValves that are meta-controls, not request-body fields.
    _META_VALVES = frozenset({"unset_fields"})

    # Repetition-penalty has two valid wire names. When the user unsets one,
    # strip both so the server doesn't pick up a stale alias.
    _ALIAS_GROUPS = (frozenset({"repetition_penalty", "repeat_penalty"}),)

    def __init__(self):
        self.valves = self.Valves()
        self.toggle = True
        self.icon= '''data:image/svg+xml;base64,PCEtLSBAbGljZW5zZSBsdWNpZGUtc3RhdGljIHYxLjE0LjAgLSBJU0MgLS0+CjxzdmcKICBjbGFzcz0ibHVjaWRlIGx1Y2lkZS1zbGlkZXJzLWhvcml6b250YWwiCiAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0idGVhbCIKICBzdHJva2Utd2lkdGg9IjIuNSIKICBzdHJva2UtbGluZWNhcD0icm91bmQiCiAgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIKPgogIDxwYXRoIGQ9Ik0xMCA1SDMiIC8+CiAgPHBhdGggZD0iTTEyIDE5SDMiIC8+CiAgPHBhdGggZD0iTTE0IDN2NCIgLz4KICA8cGF0aCBkPSJNMTYgMTd2NCIgLz4KICA8cGF0aCBkPSJNMjEgMTJoLTkiIC8+CiAgPHBhdGggZD0iTTIxIDE5aC01IiAvPgogIDxwYXRoIGQ9Ik0yMSA1aC03IiAvPgogIDxwYXRoIGQ9Ik04IDEwdjQiIC8+CiAgPHBhdGggZD0iTTggMTJIMyIgLz4KPC9zdmc+Cg=='''

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """Mutate the outbound chat-completion body before it hits the server.

        Mutual exclusion: this filter is incompatible with both the Thinking
        filter and any Profile filter. If either marker is already on the
        body, raise so the user sees the conflict clearly.
        """
        if not self.valves.enabled:
            return body

        # Mutual exclusion: Advanced is "manual mode" and refuses to run
        # alongside Thinking or any Profile.
        if body.get(_PROFILE_MARKER):
            other = body[_PROFILE_MARKER]
            raise ValueError(
                f"Advanced Params filter conflicts with active profile "
                f"'{other}'. Advanced is manual mode — disable the profile "
                f"in chat tools, or disable Advanced Params."
            )
        if body.get(_THINKING_MARKER):
            raise ValueError(
                "Advanced Params filter conflicts with the Thinking filter. "
                "Advanced is manual mode — disable the Thinking filter in "
                "chat tools (Advanced has its own enable_thinking valve), or "
                "disable Advanced Params."
            )
        body[_ADVANCED_MARKER] = True

        # Pull the per-user valves. OpenWebUI provides them on __user__.
        user_valves = None
        if __user__ and isinstance(__user__, dict):
            user_valves = __user__.get("valves")
        if user_valves is None:
            return body

        # Normalize to a dict regardless of whether OpenWebUI hands us a
        # Pydantic instance or a plain dict. exclude_none=True drops fields
        # the user left unset (passthrough).
        if hasattr(user_valves, "model_dump"):
            overrides = user_valves.model_dump(exclude_none=True)
        elif hasattr(user_valves, "dict"):
            overrides = user_valves.dict(exclude_none=True)
        elif isinstance(user_valves, dict):
            overrides = {k: v for k, v in user_valves.items() if v is not None}
        else:
            return body

        # Step 1: strip fields the user explicitly named. Done first so a
        # field listed in unset_fields AND set as a UserValve still ends up
        # set (the override pass below will re-add it with the user's value).
        unset_raw = overrides.get("unset_fields", "") or ""
        unset_names = {
            name.strip().lower() for name in unset_raw.split(",") if name.strip()
        }
        for name in unset_names:
            body.pop(name, None)
            # Strip alias counterparts so a stale wire name doesn't survive.
            for group in self._ALIAS_GROUPS:
                if name in group:
                    for alias in group:
                        body.pop(alias, None)

        # Step 2: override body with each non-None UserValve. Skip meta
        # valves (e.g. unset_fields) — they're filter controls, not
        # request-body fields.
        for key, value in overrides.items():
            if key in self._META_VALVES:
                continue
            body[key] = value

        return body
