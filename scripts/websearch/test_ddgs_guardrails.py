"""Offline regression checks for qualification guardrails, never live search."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddgs_instrument as inst
import ddgs_qualify as hq
from test_ddgs_selection import fake  # noqa: F401 -- reuse the fake-transport fixture


def test_request_budget_is_atomic_and_never_overbooks():
    inst.TRACE.clear()
    inst.TRACE.configure_budget(7)
    def reserve(_):
        try:
            inst.TRACE.reserve_request()
            return True
        except inst.RequestBudgetExceeded:
            return False
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert sum(pool.map(reserve, range(50))) == 7
        assert inst.TRACE.requests_started == 7
        assert inst.TRACE.budget_exhausted
    finally:
        inst.TRACE.clear()


def test_budget_stops_real_ddgs_batches_before_transport(fake):
    for host in ("www.google.com", "html.duckduckgo.com", "search.brave.com"):
        fake.set(host, n=4)
    inst.TRACE.configure_budget(1)
    try:
        row = hq.run_one({"id": "cap", "category": "factual", "q": "query tokens"},
                         "google,duckduckgo,brave", max_results=10, timeout=5,
                         adapter="ddgs", concurrent_requests=None, label="test",
                         mode="seq", round_no=1)
        assert len(fake.calls) == 1
        assert len(row["requests"]) == 1
        assert any("RequestBudgetExceeded" in (e["error"] or "") for e in row["engine_parse"])
    finally:
        inst.TRACE.clear()


def test_wikipedia_result_urls_are_not_a_usefulness_penalty():
    q = {"q": "capital city of Australia", "expect_tokens": ["canberra"]}
    results = [{"title": "Canberra", "href": f"https://en.wikipedia.org/wiki/Canberra#{i}",
                "body": "capital city of Australia"} for i in range(3)]
    assert hq.score(q, results)["useful"]


def test_keyword_date_is_only_a_hint_not_verified_freshness():
    q = {"q": "news today", "fresh": True, "expect_tokens": ["news"]}
    result = hq.score(q, [{"title": "News archive 2026", "href": "https://example.org",
                           "body": "Opening hours"}])
    assert result["fresh"] is None
    assert result["freshness_hint"] is True


def test_seeded_smoke_covers_all_categories():
    queries = json.loads((hq.HERE / "queries.json").read_text())["queries"]
    first = hq.select_queries(queries, 5, 20260915)
    assert first == hq.select_queries(queries, 5, 20260915)
    assert len({q["category"] for q in first}) == 5
    assert first != queries[:5]


def test_existing_output_is_refused(tmp_path):
    out = tmp_path / "run"
    hq.prepare_output(out)
    (out / "searches.jsonl").write_text("old evidence\n")
    with pytest.raises(FileExistsError):
        hq.prepare_output(out)
    assert (out / "searches.jsonl").read_text() == "old evidence\n"
