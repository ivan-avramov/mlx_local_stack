"""Instrumentation for the DDGS library: record every engine HTTP request per search.

Works against ddgs 9.14.x and 9.16.x. Nothing here changes what DDGS requests or
returns; it only observes. One ``DDGS`` instance per search (as Open WebUI's
adapter does) is what makes engine->search attribution exact: ``_get_engines``
is wrapped to stamp the owning search id onto each engine instance, and
``BaseSearchEngine.request`` / ``search`` are wrapped to log against that id.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import ddgs.base as ddgs_base
import ddgs.ddgs as ddgs_mod

_lock = threading.Lock()
_current_sid = threading.local()  # allow-pii-pattern (stdlib thread-local, not a hostname)


@dataclass
class RequestRecord:
    sid: str
    engine: str
    provider: str
    host: str
    url: str
    status: int | None
    elapsed: float
    nbytes: int
    error: str | None


@dataclass
class EngineRecord:
    sid: str
    engine: str
    provider: str
    parsed: int | None  # results after post-processing; None on exception
    elapsed: float
    error: str | None


@dataclass
class Trace:
    requests: list[RequestRecord] = field(default_factory=list)
    engines: list[EngineRecord] = field(default_factory=list)

    def for_sid(self, sid: str) -> tuple[list[RequestRecord], list[EngineRecord]]:
        with _lock:
            return (
                [r for r in self.requests if r.sid == sid],
                [e for e in self.engines if e.sid == sid],
            )

    def clear(self) -> None:
        with _lock:
            self.requests.clear()
            self.engines.clear()


TRACE = Trace()
_installed = False


def set_search_id(sid: str | None) -> None:
    """Tag the *calling* thread; ``_get_engines`` copies it onto engine instances."""
    _current_sid.value = sid


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    orig_get_engines = ddgs_mod.DDGS._get_engines
    orig_request = ddgs_base.BaseSearchEngine.request
    orig_search = ddgs_base.BaseSearchEngine.search

    def get_engines(self, category, backend):
        instances = orig_get_engines(self, category, backend)
        sid = getattr(_current_sid, "value", None)
        for inst in instances:
            inst._qual_sid = sid
        return instances

    def request(self, method, url, *args, **kwargs):
        sid = getattr(self, "_qual_sid", None) or "?"
        t0 = time.perf_counter()
        status = None
        nbytes = 0
        err = None
        try:
            # replicate BaseSearchEngine.request but keep the raw response for logging
            resp = self.http_client.request(method, url, *args, **kwargs)
            status = resp.status_code
            nbytes = len(resp.content or b"")
            return resp.text if status == 200 else None
        except Exception as ex:  # noqa: BLE001
            err = f"{type(ex).__name__}: {ex}"[:300]
            raise
        finally:
            with _lock:
                TRACE.requests.append(
                    RequestRecord(
                        sid=sid,
                        engine=getattr(self, "name", type(self).__name__),
                        provider=getattr(self, "provider", "?"),
                        host=urlsplit(url).hostname or "?",
                        url=url,
                        status=status,
                        elapsed=time.perf_counter() - t0,
                        nbytes=nbytes,
                        error=err,
                    )
                )

    def search(self, query, *args, **kwargs):
        sid = getattr(self, "_qual_sid", None) or "?"
        t0 = time.perf_counter()
        parsed = None
        err = None
        try:
            out = orig_search(self, query, *args, **kwargs)
            parsed = len(out) if out else 0
            return out
        except Exception as ex:  # noqa: BLE001
            err = f"{type(ex).__name__}: {ex}"[:300]
            raise
        finally:
            with _lock:
                TRACE.engines.append(
                    EngineRecord(
                        sid=sid,
                        engine=getattr(self, "name", type(self).__name__),
                        provider=getattr(self, "provider", "?"),
                        parsed=parsed,
                        elapsed=time.perf_counter() - t0,
                        error=err,
                    )
                )

    ddgs_mod.DDGS._get_engines = get_engines
    ddgs_base.BaseSearchEngine.request = request
    ddgs_base.BaseSearchEngine.search = search
