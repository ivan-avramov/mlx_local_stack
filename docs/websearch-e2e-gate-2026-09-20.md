# Web-search end-to-end gate — 2026-09-20

Closes the two open items from `websearch-searxng-qualification-2026-09-16.md` (C97 (a)
and (b)) with a measurement, and corrects that report on two points it could not see
from the search API alone. Harness: `scripts/websearch/owui_e2e_gate.py`; public
aggregate: `websearch-e2e-gate-2026-09-20.json`. Private evidence (full chats, tool
outputs, third-party text): `$STACK_WORKDIR/websearch/e2e-gate-20260920/{smoke,smoke2,run1}`.

## Verdict

**GATE PASS, 10/10.** Every item: `search_web` called with a non-empty result list,
Open WebUI attached citation sources, the answer carried `[n]` inline citations, every
worker round converged under the resolved 81,920 budget, and the corpus's mechanical
expectation was met. This is a pass/fail check that the shipped configuration delivers
cited web evidence into answers; it ranks nothing and it does not grade relevance.

| item | category | wall s | worker rounds | search | fetch | sources | max prompt tok | completion tok |
|---|---|---|---|---|---|---|---|---|
| fact-02 | factual | 20 | 2 | 1 | 0 | 1 | 6,266 | 245 |
| fact-04 | factual | 25 | 2 | 1 | 0 | 1 | 5,979 | 246 |
| docs-03 | docs | 30 | 2 | 1 | 0 | 1 | 6,452 | 621 |
| docs-05 | docs | 35 | 2 | 1 | 0 | 1 | 6,187 | 806 |
| news-02 | news | 25 | 2 | 1 | 0 | 1 | 6,521 | 285 |
| news-04 | news | 55 | 3 | 1 | 2 (space.com, spacex.com) | 3 | 10,176 | 814 |
| reg-01 | regional | 30 | 2 | 1 | 0 | 1 | 6,741 | 340 |
| reg-03 | regional | 60 | 3 | 1 | 1 (translink.ca) | 2 | 10,563 | 874 |
| nl-03 | longnl | 35 | 2 | 1 | 0 | 1 | 6,140 | 620 |
| nl-04 | longnl | 30 | 2 | 1 | 0 | 1 | 6,519 | 357 |

Wall per item mean 34.7 s, max 60.3 s, total 347 s; 10 `search_web` calls, 3 `fetch_url`
calls, 0 fetch failures. Selection: seed 20260920, two per category, stratified over the
same 25-query corpus as the two engine studies. Model
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` at the registry-of-record tune
(native16 KV, MTP ON, t0.5/medium), Open WebUI 0.11.3, SearXNG pool
`duckduckgo web`/`startpage`/`google`. Run 2026-09-20 23:53–23:59 PDT
(timestamps in the artifacts are UTC, 2026-09-21T06:53–06:59Z).

## What the shipped path actually is (correction to the 09-16 report)

The 09-16 report reasoned about Open WebUI's **forced-RAG** web search: task-model query
generation → SearXNG → page loader → 1000-char chunks → `rag.top_k` → a `<source>`
context block under the RAG template. **The shipped C-menu models do not take that
path.** All four run `function_calling: native` (`openwebui-init/models_config.json`),
and in `open_webui/utils/middleware.py` the forced search runs only when
`function_calling == 'legacy'`. On the native path Open WebUI registers two builtin
tools and the model decides when to call them:

- `search_web(query, count)` → JSON list of `{title, link, snippet}` straight from
  SearXNG (~200-char snippets), capped at `web.search.result_count` (10);
- `fetch_url(url)` → the loader's extracted page text (no chunking, no embedding, no
  `top_k`; truncated only if `web.fetch.max_content_length` is set — it is unset).

Consequences:

- **`rag.top_k` and `web.loader.concurrent_requests` are irrelevant to shipped web
  search.** The "retrieval squeeze" the 09-16 report fixed does not exist on this path;
  what reaches the model is the snippet list plus whatever pages it chooses to fetch.
  The 3 KB → 12 KB argument only ever applied to legacy mode and to document chat.
- The `<source>` block C97 (b) asked about is not what the model sees; it sees tool
  results as tool messages. The gate reads those back from the persisted chat
  (`output` items: `function_call` / `function_call_output` / `message`) — the same
  object the UI renders — so the evidence is the exact tool text the model received.
- The task model (`mlx-community/Qwen2.5-1.5B-Instruct-4bit`) is **not** on the shipped
  web-search path (it generated queries only in legacy mode).
- **Search is at the model's discretion.** The first smoke (plain "capital city of
  Australia", web-search toggle on) answered from weights with no tool call and
  therefore FAILED the gate. The gate prefixes every query with
  `Search the web and cite your sources: ` and records that prefix; it tests the
  pipeline when the user asks for search, not the model's policy on when to search.

## The seed file does not set what the 09-16 report said it set

Live readback (`GET /api/v1/retrieval/config`) shows `TOP_K: 3` and
`WEB_LOADER_CONCURRENT_REQUESTS: 10` — the Open WebUI defaults — while
`openwebui_config.json` says 12 and 5. Open WebUI 0.11 stores config as a **flat
per-key table** (`rag.top_k`, `web.loader.concurrent_requests`, …; `Config.get_many` in
`open_webui/models/config.py`). `runserver.sh` copies `openwebui_config.json` to
`open-webui-data/config.json`, whose legacy **nested** export lands as top-level blob
rows (`rag`, `ui`, `models`, …) that the retrieval code never reads. The settings that
ARE live (`web.search.engine = searxng`, `concurrent_requests = 1`, result count 10) are
the ones `openwebui-init/init.py` applies through the HTTP API. So the 09-16 table's
`rag.top_k 3 → 12` and `web.loader.concurrent_requests 1 → 5` rows describe the seed
file, not the running instance; both are inert, and on the native path they would be
inert even if applied. Decision item C98.

This also means any other `openwebui_config.json` value not reconciled through the API
may be non-live. C93's reconciliation verified model params, defaults and task routing
through the API, so those are safe; the rest has not been audited.

## Observed mechanisms

- Two worker rounds per item is the floor: round 1 emits the `search_web` call
  (prompt ≈ 6 K tokens: system prompt + tool schemas + query), round 2 answers from the
  snippet list. Items that fetched pages took a third round at ≈ 10 K prompt tokens.
- The model fetched pages for 2/10 items (news, regional fares) and stayed on snippets
  for the rest, including both `docs` items — it cited `docs.python.org`/`sqlite.org`
  URLs from snippets without reading them. Adequate for the gate's expectations;
  whether snippet-only answers are *good enough* for documentation questions is a
  judge-panel question, not a gate question.
- Fetch failures did occur in the operator's own 09-16 chat (AccuWeather returned
  "Access Denied" to `fetch_url`; the model fell back to snippets and still answered
  with citations). The gate saw 0/3 failures; the failure mode is real and handled, not
  absent.
- Prompt tokens per round (6–10.5 K) are dominated by the system prompt and tool
  schemas, not by search results; at 256 K context this is negligible.

## Limits

- n = 10, one network, one evening; `expectation_hit` is a keyword/domain proxy.
- Gate chats were created as the admin user and deleted after export; the operator's
  own chats were not touched. Ten gate queries hit the engines at ~35 s spacing —
  well inside the pool's measured burst tolerance, so nothing here stresses rate limits.
- Convergence is judged from the router's per-round `completion` counts against the
  resolved budget; no round approached it (max 874 tokens).
- No comparison arm (legacy mode, other engines, other models) — this is a gate.

## Reproducing

```sh
# offline checks
.venv-bench/bin/python -m pytest scripts/websearch/test_owui_e2e_gate.py -q
# 1-item smoke, then the seeded stratified run (stack up, OWUI admin creds in env or defaults)
python3 scripts/websearch/owui_e2e_gate.py --out "$STACK_WORKDIR/websearch/<dir>/smoke" --label smoke --ids fact-05
python3 scripts/websearch/owui_e2e_gate.py --out "$STACK_WORKDIR/websearch/<dir>/run1" --label run1 --per-category 2 --seed 20260920
```

Exit 0 = gate PASS; 1 = an item failed; 2 = INVALID (self-test/config precondition);
3 = transport/wedge abort (never graded).
