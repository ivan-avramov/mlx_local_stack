"""The ONE place the M64 shared search service is chosen (C165 2d, spec 5.5).

`service()` returns the stub until the D2 build step (the M64-owned SearXNG container behind a pinned MCP server)
replaces it; every arm entry, the A4 gate leg and the chain take their service from here, so an arm that configures D2
refuses to run (`ArmRefused`) everywhere until then and nothing else needs to change when the real service lands."""
from __future__ import annotations

from . import arm_adapter as aa


def service():
    return aa.UnavailableSearchService()
