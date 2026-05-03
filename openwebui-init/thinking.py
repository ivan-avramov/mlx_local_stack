"""
title: Thinking
author: ivan-avramov
version: 0.1.0
required_open_webui_version: 0.9.2
description: |
  Per-chat enable_thinking toggle for the local mlx-vlm server.

  Composable with Profile filters: a profile sets sampling and budget
  params for a workflow; this filter independently controls whether
  thinking is enabled for the chat. Toggle them together as needed.

  Mutually exclusive with the Advanced Params filter: that filter takes
  full manual control of every knob and refuses to coexist with this
  toggle.
"""

from typing import Optional

from pydantic import BaseModel, Field

# Marker keys used by the mlx-vlm filter family to enforce mutual exclusion.
_THINKING_MARKER = "_mlx_thinking_active"
_ADVANCED_MARKER = "_mlx_advanced_active"


class Filter:
    class Valves(BaseModel):
        """Admin-side global toggles for this filter."""

        enabled: bool = Field(
            True,
            description="Master switch. Disable to make the filter a no-op without uninstalling.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.toggle = True
        self.icon= '''data:image/svg+xml;base64,PCEtLSBAbGljZW5zZSBsdWNpZGUtc3RhdGljIHYxLjE0LjAgLSBJU0MgLS0+CjxzdmcKICBjbGFzcz0ibHVjaWRlIGx1Y2lkZS1icmFpbiIKICB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciCiAgd2lkdGg9IjI0IgogIGhlaWdodD0iMjQiCiAgdmlld0JveD0iMCAwIDI0IDI0IgogIGZpbGw9Im5vbmUiCiAgc3Ryb2tlPSJ0ZWFsIgogIHN0cm9rZS13aWR0aD0iMi41IgogIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIKICBzdHJva2UtbGluZWpvaW49InJvdW5kIgo+CiAgPHBhdGggZD0iTTEyIDE4VjUiIC8+CiAgPHBhdGggZD0iTTE1IDEzYTQuMTcgNC4xNyAwIDAgMS0zLTQgNC4xNyA0LjE3IDAgMCAxLTMgNCIgLz4KICA8cGF0aCBkPSJNMTcuNTk4IDYuNUEzIDMgMCAxIDAgMTIgNWEzIDMgMCAxIDAtNS41OTggMS41IiAvPgogIDxwYXRoIGQ9Ik0xNy45OTcgNS4xMjVhNCA0IDAgMCAxIDIuNTI2IDUuNzciIC8+CiAgPHBhdGggZD0iTTE4IDE4YTQgNCAwIDAgMCAyLTcuNDY0IiAvPgogIDxwYXRoIGQ9Ik0xOS45NjcgMTcuNDgzQTQgNCAwIDEgMSAxMiAxOGE0IDQgMCAxIDEtNy45NjctLjUxNyIgLz4KICA8cGF0aCBkPSJNNiAxOGE0IDQgMCAwIDEtMi03LjQ2NCIgLz4KICA8cGF0aCBkPSJNNi4wMDMgNS4xMjVhNCA0IDAgMCAwLTIuNTI2IDUuNzciIC8+Cjwvc3ZnPgo='''


    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """Inject enable_thinking into the request body

        Mutual exclusion: refuses to run if the Advanced Params filter is
        active, since Advanced is manual mode and has its own enable_thinking
        valve. Composable with Profile filters — they handle different
        params.
        """
        if not self.valves.enabled:
            return body

        if body.get(_ADVANCED_MARKER):
            raise ValueError(
                "Thinking filter conflicts with the Advanced Params filter. "
                "Advanced is manual mode (it controls enable_thinking via "
                "its own valve). Disable Advanced Params, or disable "
                "Thinking."
            )

        body["enable_thinking"] = True
        body[_THINKING_MARKER] = True
        return body
