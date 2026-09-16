"""Verbatim copy of Open WebUI's DDGS adapter, importable without the rest of Open WebUI.

``duckduckgo.py`` is byte-identical to
``backend/open_webui/retrieval/web/duckduckgo.py`` at open-webui commit
0a7c15832fb30b1903753e83f81dc7d27e5b0944 (main, 2026-09-04; file last changed in
873fb741c, 2026-08-31; sha256
8846a1bec2268ab3a152896f4046711e7e4aa5553f6ee5dd72322195886a46d3). The v0.11.3
tag carries the same file. Re-copy and update this note when upstream changes it.

The adapter imports ``open_webui.retrieval.web.main`` for ``SearchResult`` and
``get_filtered_results``; that module drags in the whole app, so a minimal shim
with the same two names is registered in ``sys.modules`` before the copy is
imported. With an empty domain filter list (the shipped configuration) the real
``get_filtered_results`` returns its input unchanged, which is what the shim does.
"""

from __future__ import annotations

import sys
import types

from pydantic import BaseModel


class SearchResult(BaseModel):
    link: str
    title: str | None
    snippet: str | None


def get_filtered_results(results, filter_list):
    if not filter_list:
        return results
    raise NotImplementedError("the vendored shim only supports an empty WEB_SEARCH_DOMAIN_FILTER_LIST")


def _register_shim() -> None:
    for name in ("open_webui", "open_webui.retrieval", "open_webui.retrieval.web"):
        sys.modules.setdefault(name, types.ModuleType(name))
    shim = types.ModuleType("open_webui.retrieval.web.main")
    shim.SearchResult = SearchResult
    shim.get_filtered_results = get_filtered_results
    sys.modules["open_webui.retrieval.web.main"] = shim


_register_shim()

from .duckduckgo import search_duckduckgo  # noqa: E402

__all__ = ["SearchResult", "get_filtered_results", "search_duckduckgo"]
