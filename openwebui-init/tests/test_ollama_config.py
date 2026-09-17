"""apply_ollama_config: the flattened-key migration, field preservation, readback."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# init.py reads its container environment at import time; dummies for a CPU test.
for _k, _v in {"OWUI_URL": "http://owui.invalid", "OWUI_ADMIN_EMAIL": "x@example.invalid",
               "OWUI_ADMIN_PASSWORD": "x"}.items():
    os.environ.setdefault(_k, _v)

import init  # noqa: E402


class R:
    def __init__(self, code, payload):
        self.status_code = code
        self._p = payload

    def json(self):
        return self._p


def _stub(monkeypatch, calls, existing=None, mutate=None):
    """Wire requests.get/post to an in-memory config store."""
    current = existing if existing is not None else {
        "ENABLE_OLLAMA_API": True,
        "OLLAMA_BASE_URLS": ["http://host.docker.internal:11434"],
        "OLLAMA_API_CONFIGS": {},
    }

    def get(url, headers=None):
        calls["get_url"] = url
        return R(200, dict(current))

    def post(url, headers=None, json=None):
        calls["post_url"] = url
        calls["sent"] = json
        echoed = dict(json)
        if mutate:
            echoed.update(mutate)
        return R(200, echoed)

    monkeypatch.setattr(init.requests, "get", get)
    monkeypatch.setattr(init.requests, "post", post)


def test_ollama_api_is_disabled(monkeypatch):
    """OWUI's own seed_defaults sets the flattened `ollama.enable` to true.

    openwebui_config.json only carries the legacy NESTED `ollama` blob, which
    current OWUI no longer reads, so the file seed cannot turn this off.
    """
    calls = {}
    _stub(monkeypatch, calls)
    init.apply_ollama_config({})
    assert calls["sent"]["ENABLE_OLLAMA_API"] is False


def test_the_connection_is_preserved_so_it_is_one_toggle_away(monkeypatch):
    """OllamaConfigForm requires both other fields; a partial POST is a 422.

    Preserving them also leaves the connection defined but inert, so an
    operator who installs Ollama later re-enables it in the UI.
    """
    calls = {}
    _stub(monkeypatch, calls, existing={
        "ENABLE_OLLAMA_API": True,
        "OLLAMA_BASE_URLS": ["http://elsewhere:11434"],
        "OLLAMA_API_CONFIGS": {"0": {"enable": True}},
    })
    init.apply_ollama_config({})
    assert calls["sent"]["OLLAMA_BASE_URLS"] == ["http://elsewhere:11434"]
    assert calls["sent"]["OLLAMA_API_CONFIGS"] == {"0": {"enable": True}}


def test_it_targets_the_ollama_router_endpoints(monkeypatch):
    calls = {}
    _stub(monkeypatch, calls)
    init.apply_ollama_config({})
    assert calls["get_url"].endswith("/ollama/config")
    assert calls["post_url"].endswith("/ollama/config/update")


def test_readback_drift_warns_but_does_not_abort(monkeypatch):
    """Same precedent as apply_web_search_config: the image is unpinned, so an
    upstream rename must not take the whole stack down over one connection."""
    calls = {}
    _stub(monkeypatch, calls, mutate={"ENABLE_OLLAMA_API": True})
    init.apply_ollama_config({})  # must not raise
