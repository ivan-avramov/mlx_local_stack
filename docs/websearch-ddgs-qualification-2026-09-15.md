# DDGS as the Open WebUI web-search provider — qualification report (2026-09-15)

Status: **BOUNDED HOST DIAGNOSIS COMPLETE — stock DDGS is not customer-qualified.** Ten-second-spaced DDGS searches passed the corpus, but bursts failed; SearXNG's alternate DuckDuckGo implementation passed the targeted corpus and burst. See §5–§7.
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

## 3. DDGS selection semantics [measured — 17 selection tests plus 6 guardrail tests, both versions pass]

`scripts/websearch/test_ddgs_selection.py` uses fake HTTP responses and a synthetic result extractor for the general-web engines; registry,
`_get_engines`, thread pool, provider dedup, aggregator and ranker run for real. These tests
establish selection/handling semantics, not live-provider parsing or reliability.

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

## 4. Execution and methodology [measured]

The operator authorized host execution, changes and restarts, and shut down the daily-driver stack. Host access worked; the earlier cloud/bridge allowlist restriction did not apply. No inference was run and no model configuration or ranking changed.

The original proposal was three complete paired version rounds, at least30 minutes apart. The initial smoke failed, so the bulk campaign was held and replaced by bounded cooldown, cadence and implementation diagnostics. These are not three completed release-qualification rounds.

- Baseline9.14.4 and candidate9.16.0 each ran in an explicit isolated Python3.12.13 venv under `$STACK_WORKDIR/websearch/venvs/`. Shared runtime pins: `primp==2.0.0`, `lxml==6.1.1`, `pydantic==2.13.4`, matching these packages in the cached OWUI image. Version-specific dependencies remain distinct and are recorded in the aggregate.
- An initial9.16.0 `uv run --no-project` smoke used an overlay that exposed the stack environment, with primp2.0.1. It is preserved as preliminary evidence and excluded from matched version comparisons. `--no-project` alone is not sufficient environment isolation here.
- Five-query pilots selected one query per category with seed20260915: `docs-05`, `fact-01`, `nl-02`, `news-01`, `reg-03`. Full diagnostic corpora used all25 queries. Burst phases repeated the same eight declared query IDs with four concurrent searches.
- The backend pool was `google,duckduckgo,brave`, count10, default DDGS timeout5s. The copied OWUI adapter SHA256 was independently matched to the cached container's actual file. A Linux/container adapter control was also run; failures are not exclusively a native-Mac observation.
- New guardrails atomically cap engine HTTP client invocations, refuse output-directory reuse, record dependency/source provenance and stop admitting searches after a wall budget. Redirects inside the HTTP client are not separate counted calls; in-flight threads are not cancelled by the admission deadline. Five new tests initially failed, then passed; an additional real-DDGS/fake-transport test verifies budget enforcement before transport. Total23 tests pass on each version.
- Result-domain scoring was corrected: Wikipedia URLs are allowed. `useful` is still a keyword/domain proxy; `fresh` remains null pending source review. Date-like text is recorded only as a freshness hint. HTTP result counts, proxy scores and source correctness are separate quantities.
- Both full DDGS diagnostic runs used an automatic assessment wrapper with a known-positive self-test, five-minute assessment interval and terminal records. They completed in about151s and283s respectively, before the first periodic interval. Failed-provider responses were retained, not graded as model failures.
- All live phases were sequential on one network. Prior traffic, cooldown, query reuse and order can affect blocking. The five-second versus ten-second observations do not establish an official rate limit or isolate every causal variable.

Private evidence root: `$STACK_WORKDIR/websearch/host-qualification-20260915`. Protocol, amendment, source snapshots, package versions, raw rows, source-page checks and assessment records are retained there. [Portable aggregate and artifact hashes](websearch-ddgs-qualification-2026-09-15.json).

## 5. Live results [measured]

A success below means at least three HTTP result URLs. All such successes in these runs also passed the mechanical expectation check; that coincidence is not proof of factual correctness or freshness.

| Path and conditions | Sequential searches | Four-way burst | Interpretation |
|---|---:|---:|---|
| DDGS9.14.4, isolated Mac, pool,1s gap | 0/5 | not run | Google200 with no parsed results; DuckDuckGo202 and Brave429 in pool. |
| DDGS9.16.0, isolated Mac, pool,1s gap | 0/5 | not run | Google429, DuckDuckGo202 and Brave429. |
| DDGS9.16.0 through OWUI adapter,10s gap, pilot | 5/5 | not run | Every success came from DuckDuckGo; this triggered the larger cadence check. |
| DDGS9.16.0 through OWUI adapter,5s gap, full corpus | **3/25** | **0/8** | Does not meet the proposed availability or burst gates. |
| DDGS9.16.0 through OWUI adapter,10s gap, full corpus | **25/25** | **1/8** | Viable sequential retrieval in this window; stock concurrent behavior still fails. |
| SearXNG Google,1s gap | pilot5/5; subsequent **0/25** | not run | First full-corpus call hit CAPTCHA;24 subsequent calls reported suspended engine. |
| SearXNG `duckduckgo web`,1s gap | pilot5/5; full **25/25** | **8/8** | Strongest implementation signal in this bounded study; not production certification. |

The isolated individual-engine smokes gave Google0/5, DuckDuckGo1/5 and Brave0/5 for each DDGS version. The earlier preliminary smoke had Brave5/5 before later429s. A five-minute quiet period did not restore Brave in the next smoke. These results do not justify ranking one DDGS version as globally more reliable.

The cached OWUI9.14.4 adapter in a temporary Linux container also returned0/5 for Google and0/5 for DuckDuckGo. This was provider-function validation, not a full authenticated chat session. No model inference or complete search→fetch→model test was performed after the provider/burst failure gate.

For the full DDGS pool at10s spacing, the25 successful sequential calls had p95 elapsed0.937s, all with DuckDuckGo results. The subsequent burst returned1/8, p95 elapsed0.887s including failures. At5s spacing, sequential p95 was0.908s despite only3/25 successes. **These elapsed times exclude the intentional gaps and any future request-queue delay; rapid failures are not speed wins.** SearXNG `duckduckgo web` had sequential p95 0.930s and burst p95 0.813s.

Traffic: **141 DDGS search invocations /283 engine HTTP-client calls**, plus **68 SearXNG API search calls** and four source-page checks. SearXNG's internal outgoing calls were not instrumented, so68 must not be reported as its upstream HTTP count. No API key, paid service, model call or proxy workaround was used. Temporary containers were stopped; the daily-driver stack remains down.

### Result quality and fetching [bounded qualitative review]

One assistant reviewed the fixed five-category sample, unblinded. Official NGINX and TransLink results were topical and their content was retrievable; factual and quantization results were on topic. This is a source-discovery screen, not independent human grading of every claim.

Google's Apple-news results mixed a stale2024 snippet with apparently current entries. A plain HTTP/text fetch of Apple Newsroom returned its navigation shell rather than news articles; a selected dated CNBC article returned403. Thus even this small screen exposes page-reading/freshness limitations. A search API success does not certify OWUI extraction or a model's answer. All corpus news freshness labels remain unverified, not silently passed by the previous year/token heuristic.

## 6. Mechanisms and recommendation

**Measured:** explicit lists avoided encyclopedia backend requests. Failure persisted across two DDGS versions, and a container control ruled out a solely native-Mac issue for the baseline. Ten-second-spaced DDGS searches succeeded, while five-second pacing and bursts did not. SearXNG Google demonstrated that a5/5 smoke can be followed immediately by CAPTCHA/suspension. Its alternate DuckDuckGo engine passed25 sequential plus8 burst searches.

**Source-inspected:** SearXNG `duckduckgo web` bootstraps a website-provided `links.duckduckgo.com/d.js` URL; DDGS uses the HTML endpoint. SearXNG Google differs in request parameters, user-agent handling, HTTP-client impersonation and parser. These are unofficial/keyless implementations, not evidence that SearXNG uses a paid API. The cached SearXNG version is2026.9.15+94218a3ac; image IDs and repository digests are in the aggregate. Engine source snapshots are retained privately with hashes.

**Not isolated:** which particular header, client, parser, endpoint or network-history difference caused each refusal. Ten seconds is an observed successful cadence, not a published DuckDuckGo entitlement or a guaranteed setting for other networks. Shared office egress remains untested.

**Re-evaluated recommendation:** use local SearXNG with only `duckduckgo web` as the provisional current baseline. Its successful runs selected this engine alone, not a multi-provider pool. The proposed sole path is `OWUI → local SearXNG → DuckDuckGo`; DDGS need not run alongside it as a search provider. The dependency preference does not justify prioritizing an unimplemented DDGS repair over the better measured implementation. Investigate that repair later only if packaging/maintenance savings warrant it.

Pin the tested OWUI and SearXNG images from the aggregate, retain ten results and tested `en-US` locale, and leave domain filtering empty. Use a clean SearXNG search URL and restrict the effective SearXNG engine registry to `duckduckgo web`. The cached OWUI adapter discards the query string when a legacy URL contains `<query>`; do not rely on an engine filter there. SearXNG `use_default_settings.engines.keep_only` must be accompanied by removal of overrides that re-add other engines. No automatic Google, Brave or encyclopedia-engine fallback is qualified.

This recommendation is pending operator adoption and broader qualification. No runtime setting or dependency pin changed during reevaluation. The earlier init default still selects the provisional DDGS pool on next startup; **it is not a qualified production default**. First validate saved configuration and the authenticated OWUI search/fetch/model flow, then repeat across time and networks. A new DDGS engine or scheduling policy is not a prerequisite.

## 7. Remaining acceptance work [untested]

- A repaired/chosen implementation must pass sustained normal and burst workloads, with queued-user latency measured if requests are paced.
- Repeat across independent residential/office networks and a longer time horizon; do not generalize this one-network window.
- Validate provider health/error reporting, fail-closed backend validation against the actual installed registry, retries/deadlines and shared-egress behavior.
- Run the actual packaged/authenticated OWUI search/fetch/model workflow after the provider gate passes; preserve existing model tunings and avoid a new model-discovery campaign.
- Retain B/C picks unchanged. This study measured search infrastructure, not model quality.
