"""apply_web_search_config: provider selection, DDGS validation scope, readback."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# init.py reads its container environment at import time; dummies for a CPU test.
for _k, _v in {"OWUI_URL": "http://owui.invalid", "OWUI_ADMIN_EMAIL": "x@example.invalid",
               "OWUI_ADMIN_PASSWORD": "x"}.items():
    os.environ.setdefault(_k, _v)
os.environ.pop("OWUI_DDGS_BACKEND", None)
os.environ.pop("OWUI_WEB_SEARCH_ENGINE", None)

import init  # noqa: E402


class R:
    def __init__(self, code, payload):
        self.status_code = code
        self._p = payload

    def json(self):
        return self._p


def _stub(monkeypatch, calls, existing=None, mutate=None):
    """Wire requests.get/post to an in-memory config store."""
    def get(url, headers=None):
        return R(200, {"web": dict(existing or {})})

    def post(url, headers=None, json=None):
        calls["sent"] = json["web"]
        echoed = dict(json["web"])
        if mutate:
            echoed.update(mutate)
        return R(200, {"web": echoed})

    monkeypatch.setattr(init.requests, "get", get)
    monkeypatch.setattr(init.requests, "post", post)


# --------------------------------------------------------------- provider default
def test_default_engine_is_the_qualified_searxng_sidecar(monkeypatch):
    """DDGS managed 1/8 on burst; SearXNG's qualified pool is the shipped default."""
    calls = {}
    _stub(monkeypatch, calls, existing={"OTHER": 1})
    init.apply_web_search_config({})
    assert calls["sent"]["WEB_SEARCH_ENGINE"] == "searxng"
    assert calls["sent"]["ENABLE_WEB_SEARCH"] is True
    assert calls["sent"]["OTHER"] == 1, \
        "unrelated saved fields are preserved (endpoint replaces `web` wholesale)"


def test_searxng_query_url_points_at_the_compose_service(monkeypatch):
    calls = {}
    _stub(monkeypatch, calls)
    init.apply_web_search_config({})
    assert calls["sent"]["SEARXNG_QUERY_URL"] == \
        "http://searxng:8080/search?q=<query>&format=json"


def test_search_concurrency_is_one(monkeypatch):
    """Simultaneous queries are what trip engine rate limits."""
    calls = {}
    _stub(monkeypatch, calls)
    init.apply_web_search_config({})
    assert calls["sent"]["WEB_SEARCH_CONCURRENT_REQUESTS"] == 1


# --------------------------------------------------- DDGS validation is scoped
def test_ddgs_backend_is_not_validated_when_searxng_is_selected(monkeypatch):
    """A broken DDGS list must not block a stack that does not use DDGS."""
    calls = {}
    _stub(monkeypatch, calls)
    monkeypatch.setattr(init, "WEB_SEARCH_ENGINE", "searxng")
    monkeypatch.setattr(init, "DDGS_BACKEND", "totally-bogus-engine")
    init.apply_web_search_config({})  # must not raise
    assert "DDGS_BACKEND" not in calls["sent"], \
        "DDGS settings are not pushed for a non-DDGS engine"


def test_ddgs_backend_is_validated_when_duckduckgo_is_selected(monkeypatch):
    calls = {}
    _stub(monkeypatch, calls)
    monkeypatch.setattr(init, "WEB_SEARCH_ENGINE", "duckduckgo")
    monkeypatch.setattr(init, "DDGS_BACKEND", "totally-bogus-engine")
    with pytest.raises(RuntimeError, match="unknown/disallowed"):
        init.apply_web_search_config({})


def test_duckduckgo_mode_still_pushes_the_backend_list(monkeypatch):
    calls = {}
    _stub(monkeypatch, calls)
    monkeypatch.setattr(init, "WEB_SEARCH_ENGINE", "duckduckgo")
    monkeypatch.setattr(init, "DDGS_BACKEND", "google,duckduckgo,brave")
    init.apply_web_search_config({})
    assert calls["sent"]["DDGS_BACKEND"] == "google,duckduckgo,brave"


# ---------------------------------------------------------- backend list rules
def test_normalises_case_and_spaces():
    assert init.validate_ddgs_backend(" Google , duckduckgo,BRAVE ") == "google,duckduckgo,brave"


@pytest.mark.parametrize("bad", ["", "auto", "all", "google,auto", "yandex", "google,bogus", "bing"])
def test_rejects_lists_ddgs_would_widen_or_that_are_not_general_web(bad):
    with pytest.raises(RuntimeError):
        init.validate_ddgs_backend(bad)


@pytest.mark.parametrize("ref", ["wikipedia", "google,grokipedia"])
def test_rejects_reference_backends(ref):
    with pytest.raises(RuntimeError, match="reference backends"):
        init.validate_ddgs_backend(ref)


# ------------------------------------------------------------------- readback
def test_readback_mismatch_warns_but_does_not_abort_bring_up(capsys, monkeypatch):
    """The OWUI image is unpinned and re-pulled every run. An upstream rename of
    a web-search key must not take the whole stack down with it."""
    calls = {}
    _stub(monkeypatch, calls, mutate={"WEB_SEARCH_ENGINE": "something-else"})
    init.apply_web_search_config({})  # must not raise
    out = capsys.readouterr().out
    assert "WARNING" in out and "WEB_SEARCH_ENGINE" in out


def test_transport_failure_still_aborts(monkeypatch):
    """A failed push is a real error; only a value mismatch is tolerated."""
    monkeypatch.setattr(init.requests, "get", lambda url, headers=None: R(200, {"web": {}}))
    monkeypatch.setattr(init.requests, "post",
                        lambda url, headers=None, json=None: R(500, {}))
    with pytest.raises(RuntimeError):
        init.apply_web_search_config({})
