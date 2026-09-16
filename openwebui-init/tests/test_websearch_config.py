"""apply_web_search_config: the DDGS backend list is validated before it is pushed."""

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


def test_default_backend_is_the_explicit_general_web_list():
    assert init.validate_ddgs_backend(init.DDGS_BACKEND) == "google,duckduckgo,brave"


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


def test_apply_pushes_engine_and_backend_and_verifies_readback(monkeypatch):
    calls = {}

    class R:
        def __init__(self, code, payload):
            self.status_code = code
            self._p = payload

        def json(self):
            return self._p

    def get(url, headers=None):
        return R(200, {"web": {"WEB_SEARCH_ENGINE": "searxng", "DDGS_BACKEND": "auto", "OTHER": 1}})

    def post(url, headers=None, json=None):
        calls["sent"] = json["web"]
        return R(200, {"web": json["web"]})

    monkeypatch.setattr(init.requests, "get", get)
    monkeypatch.setattr(init.requests, "post", post)
    init.apply_web_search_config({})
    sent = calls["sent"]
    assert sent["WEB_SEARCH_ENGINE"] == "duckduckgo"
    assert sent["DDGS_BACKEND"] == "google,duckduckgo,brave"
    assert sent["ENABLE_WEB_SEARCH"] is True
    assert sent["OTHER"] == 1, "unrelated saved fields are preserved (endpoint replaces `web` wholesale)"


def test_apply_fails_when_readback_differs(monkeypatch):
    class R:
        def __init__(self, code, payload):
            self.status_code = code
            self._p = payload

        def json(self):
            return self._p

    monkeypatch.setattr(init.requests, "get", lambda url, headers=None: R(200, {"web": {}}))
    monkeypatch.setattr(init.requests, "post",
                        lambda url, headers=None, json=None: R(200, {"web": {**json["web"], "DDGS_BACKEND": "auto"}}))
    with pytest.raises(RuntimeError, match="DDGS_BACKEND"):
        init.apply_web_search_config({})
