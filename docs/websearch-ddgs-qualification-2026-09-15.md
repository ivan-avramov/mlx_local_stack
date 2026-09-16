# DDGS as the Open WebUI web-search provider — qualification report (2026-09-15)

Status: **DRAFT — offline parts complete; live measurement pending** (see §6).
Scope: can `ddgs` (the library Open WebUI's `duckduckgo` engine wraps) provide useful
general-web search per customer installation with no SearXNG sidecar, no API keys and
no central subscription. Sections are labelled **[measured]**, **[inferred]** or
**[untested]** throughout.

## 1. Inventory [measured]

| item | value | evidence |
|---|---|---|
| Open WebUI | v0.11.3, image `ghcr.io/open-webui/open-webui:main`, pulled 2026-09-15 05:45 | `logs/compose.log` banner; `docker-compose.yml` (`pull_policy: always`) |
| DDGS in the container | **9.14.4** | (a) `ddgs==9.14.4` pinned in OWUI `pyproject.toml`/`backend/requirements.txt` at both `v0.11.3` (2a960a5) and `main` (0a7c158, 2026-09-04); (b) today's traceback cites `ddgs/ddgs.py` lines 454 (`raise DDGSException`) and 458 (`text`) — those line numbers exist only in 9.14.4 (9.16.0: 223/227); (c) a `yandex.com` request at 19:43 — Yandex is `disabled = True` in 9.16.0 |
| Saved web-search config (DB `config` table, copied `webui.db`, secrets redacted) | `web.search.enable=true`, `web.search.engine="duckduckgo"`, `web.search.ddgs_backend="auto"`, `result_count=10`, `concurrent_requests=5`, `domain.filter_list=[]`, `trust_env=true`, `searxng_query_url="http://searxng:8080/search?q=<query>&format=json"` | sqlite read of a copy of `open-webui-data/webui.db` (+WAL) |
| What `init.py` pushes each start | `WEB_SEARCH_ENGINE="searxng"`, SearXNG URL/language, count 10, concurrency 5 | `openwebui-init/init.py:apply_web_search_config` |
| Compose env | `RAG_WEB_SEARCH_RESULT_COUNT=10`, `RAG_WEB_SEARCH_CONCURRENT_REQUESTS=10` (legacy names; the DB values above are what is effective) | `docker-compose.yml` |
| DDGS releases | 9.14.4 (2026-05-15) … 9.15.0 (08-16), **9.16.0 (2026-08-26, latest)**; upstream `main` HEAD 70a5635 *is* the 9.16.0 release commit | PyPI JSON; `git log` of deedy5/ddgs |
| 9.16.0 runtime deps | `click>=8.1.8`, `primp>=1.3.1`, `lxml>=4.9.4` (9.14.4 additionally used `httpx` + `fake_useragent` for its DuckDuckGo engine) | PyPI metadata; `git diff v9.14.4 v9.16.0` |

The live saved engine is already `duckduckgo` (someone switched it in the admin UI); the
persisted value survives `init.py`'s per-start `searxng` push because `init.py` is what
writes it and the UI write came later. Any on-disk change must therefore go through
`init.py` (re-applied every start), not only through env defaults.

Today's live log (queries redacted), all under `auto` with 9.14.4 [measured]:
19:30 — Google `/search` 200 → `DDGSException: No results found` (twice; the 200 page
parsed to zero results); 19:43 — `grokipedia.com/api/typeahead` 502, `en.wikipedia.org`
opensearch 200, `yandex.com/search/site` 200.

"Juno adapter": nothing named Juno exists in this repository (`git grep -i juno` hits only
benchmark result rows); the adapter inspected is Open WebUI's own
`backend/open_webui/retrieval/web/duckduckgo.py`.

## 2. Adapter behaviour (Open WebUI main 0a7c158 / v0.11.3) [measured — source]

- `routers/retrieval.py:2619` → `asyncio.to_thread(search_duckduckgo, query, WEB_SEARCH_RESULT_COUNT, WEB_SEARCH_DOMAIN_FILTER_LIST, concurrent_requests=WEB_SEARCH_CONCURRENT_REQUESTS, backend=DDGS_BACKEND)`.
- `search_duckduckgo` creates **one `DDGS()` per call** (default `timeout=5`), sets `ddgs.threads = concurrent_requests`, calls `ddgs.text(query, safesearch='moderate', max_results=count, backend=backend or 'auto')`, maps `href/title/body` → `SearchResult(link,title,snippet)`. `region` is never passed (DDGS default `us-en`). Proxy comes from `urllib.request.getproxies()`.
- **`ddgs.threads = …` is a no-op.** `_search_sync` reads the class attribute `DDGS.threads`; the adapter sets an instance attribute. Additionally `from ddgs import DDGS` yields a lazy proxy class, so even `DDGS.threads = n` on the imported name would not reach `ddgs.ddgs.DDGS`. Verified by `test_owui_style_instance_threads_assignment_is_a_no_op` on both versions.
- `WEB_SEARCH_CONCURRENT_REQUESTS` is otherwise an `asyncio.Semaphore` over the *queries* of one chat-turn fan-out (`process_web_search`), not a requests-per-second limiter. The builtin `search_web` tool (`tools/builtin.py:293`) calls `_search_web` directly with no semaphore.
- `DDGS_BACKEND` is a free string (env default `auto`; DB key `web.search.ddgs_backend`; settable via `POST /api/v1/retrieval/config/update`). The UI dropdown is the only thing restricting it to single values.

## 3. DDGS selection semantics, verified offline on 9.14.4 and 9.16.0 [measured — 17 fake-transport tests, both versions pass]

`scripts/websearch/test_ddgs_selection.py` replaces only the HTTP layer; registry,
`_get_engines`, thread pool, provider dedup, aggregator and ranker run for real.

| property | result |
|---|---|
| Explicit `google,duckduckgo,brave` | only `www.google.com`, `html.duckduckgo.com`, `search.brave.com` are contacted; **no wikipedia.org / grokipedia.com request** in either version. Result-domain filtering is unnecessary. |
| Ordering | explicit lists are **not shuffled** (shuffle only applies to `auto`) and the priority sort is stable → the list is an **ordered preference**. |
| Batching | pool width `max_workers = min(#unique providers, ceil(max_results/10)+1)` = **2 at count 10**. The first two listed engines run concurrently; the third runs only if they leave the quota unfilled (< 10 unique hrefs). So "all listed backends run" is false, and "strict sequential fallback" is also false: it is batch-wise fallback in list order. |
| Invalid entry | `google,duckduckgo,brave,bogus` → `bogus` dropped with a WARNING; eligibility not widened. |
| All entries invalid | falls back to `auto` with only a WARNING ("backend is not set. Using 'auto'") → Wikipedia/Grokipedia are contacted first. This is the one silent-widening path: a typo, or a future release disabling every listed engine (`yandex` became invalid in 9.16.0 exactly this way). |
| `auto` | Wikipedia (priority 2) and Grokipedia (1.9) run first; each yields ≤ 1 result, so the shuffled web engines always run too; the ranker pins any `wikipedia.org` href to the top. |
| Provider dedup | `duckduckgo` and `yahoo` are both `provider=bing`; once one answers the other is skipped. `startpage` is `provider=google`. |
| Result dedup | by `href`; identical hrefs from several engines merge, the longer `body` kept, and multi-engine hits sort first. |
| Deadline | `wait(timeout=5, FIRST_EXCEPTION)` per batch; an engine slower than the timeout has its results **dropped**, yet the executor still joins the thread on exit, so the call blocks for the slow engine's full duration and returns only the fast engine's results (`test_slow_engine_results_are_dropped_after_pool_timeout`). |
| Retries | none anywhere (engine → `HttpClient` → `primp`). A non-200 is "no results" for that engine and the next batch proceeds. All-empty raises `DDGSException("No results found.")`; a timeout message raises `TimeoutException`. |
| Network cache | 9.14.4 has an opt-in DHT/libp2p result cache (`api_url=` only; OWUI never passes it — inert). Removed entirely in 9.16.0. |
| Version deltas | 9.16.0: Google engine moved to `/wml/search` (Nokia S60 UA, new XPaths, `sca_esv=1`); DuckDuckGo engine drops `fake_useragent`/httpx for the shared `primp` client; Yandex disabled; DHT code removed. `_get_engines`/`_search_sync` selection logic is otherwise identical between the two versions. |

## 4. Test plan [proposed; harness built and unit-tested]

Harness: `scripts/websearch/ddgs_qualify.py` (README alongside). Isolated `uv run
--no-project --with ddgs==<ver>` venvs; nothing installed into the container.

- Versions: 9.14.4 (installed baseline) vs 9.16.0 (pinned candidate).
- Backend specs: `google`, `duckduckgo`, `brave`, `google,duckduckgo,brave`; `auto` as a round-1 control.
- 25 queries, 5 per category (factual / official docs / current news / regional / long NL), each with a mechanical expectation (domain suffix or tokens in the top 5).
- 3 rounds ≥ 30 min apart; per round per version 25×5 sequential searches at a 1 s gap + one 8-search burst at 4-wide per spec.
- Budget: ≤ ~300 HTTP requests per version-round (individual 1/search, combined ≤ 3, auto ≤ ~5) → ≤ ~1,800 total, < 200 MB; ~20 min wall per round.
- Acceptance per (version, spec) on the tested network: ≥ 90 % of searches return ≥ 3 results; ≥ 80 % useful (expectation hit in top 5, ≥ 3 http results, not reference-only); p95 ≤ 6 s; timeouts + throttles ≤ 5 %; burst success ≥ 80 %; round-3 not > 10 pp below round 1; zero reference-backend hosts with the explicit list; combined ≥ best individual on usefulness.

## 5. Live measurements [pending]

Not yet run: neither execution environment available to this session can reach the
engines (both return `403 blocked-by-allowlist` for google.com, duckduckgo.com,
search.brave.com, wikipedia.org, grokipedia.com; PyPI/GitHub are allowed). The Mac
host can (today's OWUI log shows Google 200s). Results will be filled in from
`$STACK_WORKDIR/websearch/<round>-<version>/summary.json`.

## 6. Recommendations so far

- Candidate to qualify further: **ddgs 9.16.0 pinned**, backend `google,duckduckgo,brave` (ordered). [inferred from source; live usefulness untested]
- Minimal adapter fixes worth proposing upstream / carrying: (1) set `ddgs.ddgs.DDGS.threads` (class) or drop the dead assignment; (2) pass `region` from `SEARXNG_LANGUAGE`-style config; (3) validate `DDGS_BACKEND` against `ddgs.engines.ENGINES["text"]` at config time so an all-invalid string cannot silently become `auto`.
- Stock multi-backend behaviour = ordered batch-wise fallback with width 2 at count 10. Whether explicit primary/fallback sequencing is justified depends on the measured per-engine block rates (§5).
- Evidence still needed before customer release: the live rounds above on at least this network; the same run from ≥ 2 other residential/office networks; a longer-horizon repeat (engines change their anti-bot behaviour without notice — DDGS itself has shipped three Google rewrites in five months).
