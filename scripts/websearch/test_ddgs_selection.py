"""Offline verification of DDGS backend-selection semantics (no network).

The HTTP layer is replaced by a fake that answers per host; every other line of
DDGS (engine registry, ``_get_engines``, the thread pool, provider dedup, the
result aggregator, the ranker) runs for real. Run under each DDGS version being
qualified, e.g.:

    uv run --no-project --with ddgs==9.16.0 --with pytest --with pydantic \
        -m pytest scripts/websearch/test_ddgs_selection.py -q
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ddgs  # noqa: E402
import ddgs.base as ddgs_base  # noqa: E402
import ddgs.ddgs as ddgs_real  # noqa: E402
import ddgs.http_client as ddgs_http  # noqa: E402
from ddgs import DDGS  # noqa: E402
from ddgs.engines import ENGINES  # noqa: E402
from ddgs.exceptions import DDGSException  # noqa: E402

import ddgs_instrument  # noqa: E402

V = tuple(int(x) for x in ddgs.__version__.split("."))
GOOGLE_HOST = "www.google.com"
DDG_HOST = "html.duckduckgo.com"
BRAVE_HOST = "search.brave.com"
WEB_HOSTS = {GOOGLE_HOST, DDG_HOST, BRAVE_HOST}


class FakeResp:
    def __init__(self, status: int, text: str) -> None:
        self.status_code = status
        self.text = text
        self.content = text.encode()


class Fake:
    """Per-host canned behaviour: number of results, HTTP status, delay, or shared hrefs."""

    def __init__(self) -> None:
        self.per_host: dict[str, dict] = {}
        self.calls: list[str] = []

    def set(self, host: str, *, n: int = 10, status: int = 200, delay: float = 0.0, hrefs=None,
            raw: str | None = None) -> None:
        self.per_host[host] = {"n": n, "status": status, "delay": delay, "hrefs": hrefs, "raw": raw}

    def set_reference_backends(self) -> None:
        """Canned answers in the JSON shapes the Wikipedia/Grokipedia engines parse themselves."""
        self.set("en.wikipedia.org", raw=json.dumps(
            ["q", ["Query Tokens"], [""], ["https://en.wikipedia.org/wiki/Query_Tokens"]]))
        self.set("grokipedia.com", raw=json.dumps(
            {"results": [{"title": "Query tokens", "snippet": "intro\n\nbody", "slug": "Query_tokens"}]}))

    def request(self, method, url, *args, **kwargs):
        from urllib.parse import urlsplit

        host = urlsplit(url).hostname
        self.calls.append(host)
        cfg = self.per_host.get(host, {"n": 0, "status": 200, "delay": 0.0, "hrefs": None, "raw": None})
        if cfg["delay"]:
            time.sleep(cfg["delay"])
        if cfg["raw"] is not None:
            if host == "en.wikipedia.org" and "prop=extracts" in url:  # second wikipedia call: the body
                return FakeResp(200, json.dumps({"query": {"pages": {"1": {"extract": "body text"}}}}))
            return FakeResp(cfg["status"], cfg["raw"])
        hrefs = cfg["hrefs"] or [f"https://{host}/r{i}" for i in range(cfg["n"])]
        return FakeResp(cfg["status"], json.dumps([{"title": f"t {i} {host}", "href": h, "body": f"body {i}"}
                                                   for i, h in enumerate(hrefs)]))


@pytest.fixture()
def fake(monkeypatch):
    f = Fake()
    ddgs_instrument.install()
    ddgs_instrument.TRACE.clear()

    def http_request(self, method, url, *args, **kwargs):
        return f.request(method, url, *args, **kwargs)

    monkeypatch.setattr(ddgs_http.HttpClient, "request", http_request)
    if V < (9, 16, 0):  # 9.14.x DuckDuckGo engine uses a second client
        import ddgs.http_client2 as http2

        monkeypatch.setattr(http2.HttpClient2, "request", http_request)

    def extract_results(self, html_text):
        out = []
        for item in json.loads(html_text):
            r = self.result_type()
            for k, v in item.items():
                setattr(r, k, v)
            out.append(r)
        return out

    monkeypatch.setattr(ddgs_base.BaseSearchEngine, "extract_results", extract_results)
    monkeypatch.setattr(ddgs_real.DDGS, "threads", None)
    return f


def search(fake: Fake, backend: str, max_results: int = 10, timeout: int = 5, threads_instance=None):
    ddgs_instrument.set_search_id("t")
    try:
        with DDGS(timeout=timeout) as d:
            if threads_instance is not None:
                d.threads = threads_instance  # what the OWUI adapter does
            return d.text("query tokens", max_results=max_results, backend=backend)
    finally:
        ddgs_instrument.set_search_id(None)


def hosts(fake: Fake) -> set[str]:
    return set(fake.calls)


# --------------------------------------------------------------------------- registry facts
def test_registry_matches_expectations_for_this_version():
    text = ENGINES["text"]
    assert {"google", "duckduckgo", "brave", "wikipedia", "grokipedia"} <= set(text)
    assert "bing" not in text  # disabled in both versions
    if V >= (9, 16, 0):
        assert "yandex" not in text, "9.16.0 disables Yandex"
        assert text["google"].search_url == "https://www.google.com/wml/search"
    else:
        assert "yandex" in text
        assert text["google"].search_url == "https://www.google.com/search"
    assert text["wikipedia"].priority > text["grokipedia"].priority > text["google"].priority
    assert text["duckduckgo"].provider == "bing" and text["yahoo"].provider == "bing"
    assert text["startpage"].provider == "google"


# --------------------------------------------------------------------------- explicit list
def test_explicit_list_never_contacts_reference_backends(fake):
    for h in WEB_HOSTS:
        fake.set(h, n=4)
    res = search(fake, "google,duckduckgo,brave")
    assert hosts(fake) <= WEB_HOSTS
    assert hosts(fake) == WEB_HOSTS, "each engine returned <10, so all three had to run"
    assert not any(h.endswith(("wikipedia.org", "grokipedia.com")) for h in fake.calls)
    assert len(res) == 10  # 12 available, capped at max_results


def test_explicit_list_stops_after_first_batch_when_it_fills_max_results(fake):
    """Aggregation is batch-wise, not 'run every listed backend': with max_results=10 the
    pool has ceil(10/10)+1 = 2 workers, so the first two engines in list order fill the quota
    and the third is never requested."""
    for h in WEB_HOSTS:
        fake.set(h, n=10)
    res = search(fake, "google,duckduckgo,brave")
    assert len(hosts(fake)) == 2 and hosts(fake) <= WEB_HOSTS
    assert len(res) == 10


def test_explicit_list_order_is_the_preference_order(fake):
    """For an explicit list ``_get_engines`` does NOT shuffle (that only happens for auto) and the
    priority sort is stable, so the listed order is the order engines are tried, in batches of
    ``max_workers``. The list is therefore an ordered preference, not an unordered set."""
    for h in WEB_HOSTS:
        fake.set(h, n=10)
    for _ in range(10):
        fake.calls.clear()
        search(fake, "google,duckduckgo,brave")
        assert set(fake.calls) == {GOOGLE_HOST, DDG_HOST}, fake.calls
    for _ in range(10):
        fake.calls.clear()
        search(fake, "brave,duckduckgo,google")
        assert set(fake.calls) == {BRAVE_HOST, DDG_HOST}, fake.calls


def test_invalid_entry_in_list_is_dropped_not_widened(fake, caplog):
    for h in WEB_HOSTS:
        fake.set(h, n=4)
    with caplog.at_level(logging.WARNING, logger="ddgs.ddgs"):
        search(fake, "google,duckduckgo,brave,bogus")
    assert hosts(fake) == WEB_HOSTS
    assert any("bogus" in r.getMessage() and "do not exist" in r.getMessage() for r in caplog.records)


def test_all_invalid_silently_falls_back_to_auto_and_reaches_reference_backends(fake, caplog):
    """This is the eligibility-widening hazard: a wholly invalid backend string (typo,
    or a name that a future DDGS release disables) becomes 'auto', which puts Wikipedia and
    Grokipedia first. Only a WARNING is logged; the caller cannot tell from the result."""
    fake.set_reference_backends()
    with caplog.at_level(logging.WARNING, logger="ddgs.ddgs"):
        res = search(fake, "yandex,bogus" if V >= (9, 16, 0) else "bogus,bogus2")
    assert any("Using 'auto'" in r.getMessage() for r in caplog.records)
    assert any(h.endswith(("wikipedia.org", "grokipedia.com")) for h in fake.calls)
    assert res


def test_auto_prioritises_wikipedia_and_grokipedia(fake):
    """auto = Wikipedia, Grokipedia first (priority 2 / 1.9), then the shuffled web engines. Each
    reference engine yields at most ONE result, so auto always goes on to the web engines; what
    it does not do is leave them out."""
    fake.set_reference_backends()
    for h in WEB_HOSTS:
        fake.set(h, n=10)
    res = search(fake, "auto")
    assert fake.calls[:3] == ["en.wikipedia.org", "en.wikipedia.org", "grokipedia.com"], fake.calls
    assert res[0]["href"].startswith("https://en.wikipedia.org/"), "ranker pins wikipedia.org to the top"
    assert len(res) == 10


# --------------------------------------------------------------------------- concurrency
def test_owui_style_instance_threads_assignment_is_a_no_op(fake):
    for h in WEB_HOSTS:
        fake.set(h, n=10)
    search(fake, "google,duckduckgo,brave", threads_instance=1)
    assert len(hosts(fake)) == 2, "instance attribute ignored: pool still 2 wide"
    fake.calls.clear()
    # ``from ddgs import DDGS`` yields a lazy proxy class until first instantiation; setting
    # ``threads`` on it never reaches the real class either. Only ddgs.ddgs.DDGS.threads works.
    DDGS.threads = 1
    search(fake, "google,duckduckgo,brave")
    assert len(hosts(fake)) == 2, "proxy-class attribute ignored too"
    fake.calls.clear()
    ddgs_real.DDGS.threads = 1  # the real class attribute is what _search_sync reads
    try:
        search(fake, "google,duckduckgo,brave")
    finally:
        ddgs_real.DDGS.threads = None
    assert len(hosts(fake)) == 1, "class attribute honoured: strictly sequential, first engine filled the quota"


def test_pool_width_grows_with_max_results(fake):
    for h in WEB_HOSTS:
        fake.set(h, n=10)
    search(fake, "google,duckduckgo,brave", max_results=20)  # ceil(20/10)+1 = 3 workers
    assert hosts(fake) == WEB_HOSTS


# --------------------------------------------------------------------------- dedup & providers
def test_results_deduplicated_by_href_and_frequency_ranked(fake):
    shared = [f"https://example.org/p{i}" for i in range(6)]
    fake.set(GOOGLE_HOST, hrefs=shared)
    fake.set(BRAVE_HOST, hrefs=shared[:3] + [f"https://other.org/q{i}" for i in range(3)])
    res = search(fake, "google,brave")
    hrefs = [r["href"] for r in res]
    assert len(hrefs) == len(set(hrefs)) == 9
    # the ranker buckets on query tokens (all bodies identical here), then keeps aggregator
    # order = descending frequency, so the three hrefs seen twice come first.
    assert set(hrefs[:3]) == set(shared[:3])


def test_same_provider_is_not_queried_twice_after_a_success(fake):
    fake.set(DDG_HOST, n=4)
    fake.set("search.yahoo.com", n=4)
    search(fake, "duckduckgo,yahoo")  # both provider=bing
    assert len(hosts(fake)) == 1, "a second bing-backed engine is skipped once bing answered"


# --------------------------------------------------------------------------- failures
def test_http_non_200_counts_as_no_results_and_next_engine_runs(fake):
    fake.set(GOOGLE_HOST, status=429)
    fake.set(DDG_HOST, status=200, n=4)
    fake.set(BRAVE_HOST, status=200, n=4)
    res = search(fake, "google,duckduckgo,brave")
    assert hosts(fake) == WEB_HOSTS and len(res) == 8


def test_all_engines_empty_raises_no_results(fake):
    for h in WEB_HOSTS:
        fake.set(h, n=0)
    with pytest.raises(DDGSException, match="No results found"):
        search(fake, "google,duckduckgo,brave")


def test_slow_engine_results_are_dropped_after_pool_timeout(fake):
    """``wait(timeout=self._timeout)`` abandons unfinished futures; their results are never
    collected, but ThreadPoolExecutor still joins them on exit, so the call blocks for the
    slow engine's full duration and returns only the fast engine's results."""
    fake.set(GOOGLE_HOST, n=4, delay=2.0)
    fake.set(BRAVE_HOST, n=4)
    t0 = time.perf_counter()
    res = search(fake, "google,brave", timeout=1)
    elapsed = time.perf_counter() - t0
    assert {r["href"].split("/")[2] for r in res} == {BRAVE_HOST}
    assert elapsed >= 2.0


# --------------------------------------------------------------------------- OWUI adapter
def test_owui_adapter_passes_backend_string_through(fake):
    from owui_vendor import SearchResult, search_duckduckgo

    for h in WEB_HOSTS:
        fake.set(h, n=4)
    ddgs_instrument.set_search_id("t")
    out = search_duckduckgo("query tokens", 10, [], concurrent_requests=5, backend="google,duckduckgo,brave")
    assert hosts(fake) == WEB_HOSTS
    assert all(isinstance(r, SearchResult) for r in out) and len(out) == 10


def test_owui_adapter_none_backend_means_auto(fake):
    from owui_vendor import search_duckduckgo

    fake.set_reference_backends()
    for h in WEB_HOSTS:
        fake.set(h, n=10)
    search_duckduckgo("query tokens", 10, [], concurrent_requests=5, backend=None)
    assert fake.calls[:3] == ["en.wikipedia.org", "en.wikipedia.org", "grokipedia.com"]


# --------------------------------------------------------------------------- harness plumbing
def test_harness_row_and_summary_under_fake_transport(fake):
    import ddgs_qualify as hq

    for h in WEB_HOSTS:
        fake.set(h, n=4)
    q = {"id": "docs-x", "category": "docs", "q": "query tokens", "expect_tokens": ["body"]}
    row = hq.run_one(q, "google,duckduckgo,brave", max_results=10, timeout=5, adapter="ddgs",
                     concurrent_requests=None, label="t", mode="seq", round_no=1)
    assert row["engines_attempted"] == ["brave", "duckduckgo", "google"]
    assert row["engines_succeeded"] == ["brave", "duckduckgo", "google"]
    assert set(row["hosts"]) == WEB_HOSTS and row["reference_backend_contacted"] is False
    assert row["score"]["n_results"] == 10 and row["score"]["useful"] is True
    assert {r["status"] for r in row["requests"]} == {200}
    row2 = hq.run_one(q, "google,duckduckgo,brave", max_results=10, timeout=5, adapter="owui",
                      concurrent_requests=5, label="t", mode="seq", round_no=1)
    assert row2["adapter"] == "owui" and row2["score"]["n_results"] == 10
    s = hq.summarize([row, row2])
    key = f"{ddgs.__version__}|ddgs|google,duckduckgo,brave|seq"
    assert s[key]["useful"] == 1 and s[key]["engines_succeeded"] == {"brave": 1, "duckduckgo": 1, "google": 1}
